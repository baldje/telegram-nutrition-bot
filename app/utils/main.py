# app/handlers/start.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import logging

logger = logging.getLogger(__name__)

start_router = Router()


@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    try:
        # Очищаем состояние
        await state.clear()

        # Проверяем реферальные параметры
        args = message.text.split()
        if len(args) > 1:
            ref_param = args[1]
            logger.info(f"Реферальный параметр: {ref_param} от пользователя {message.from_user.id}")
            # Здесь будет логика обработки рефералов

        # Создаем клавиатуру
        builder = ReplyKeyboardBuilder()
        builder.button(text="✅ Да, хочу тест")
        builder.button(text="ℹ️ Что умеет бот")
        builder.adjust(2)

        await message.answer(
            "Привет! Я бот Лизы — помогу тебе с питанием, фото-анализом и тренировками.\n"
            "3 дня теста бесплатно. Начнём?",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )

        logger.info(f"Пользователь {message.from_user.id} запустил бота")

    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@start_router.message(F.text == "✅ Да, хочу тест")
async def start_trial(message: Message, state: FSMContext):
    """Начало триального периода"""
    try:
        await message.answer(
            "Отлично! 🎉\n"
            "Давай настроим твой персональный план.\n\n"
            "Сколько тебе лет?",
            reply_markup=ReplyKeyboardBuilder().button(text="Пропустить").as_markup(resize_keyboard=True)
        )

        # Устанавливаем состояние онбординга
        await state.set_state("onboarding_age")
        logger.info(f"Пользователь {message.from_user.id} начал онбординг")

    except Exception as e:
        logger.error(f"Ошибка в start_trial: {e}")
        await message.answer("❌ Ошибка при запуске теста")


@start_router.message(F.text == "ℹ️ Что умеет бот")
async def bot_features(message: Message):
    """Описание возможностей бота"""
    features_text = (
        "🤖 <b>Что я умею:</b>\n\n"
        "🍽 <b>Питание</b>\n"
        "• Персональные планы питания\n"
        "• Анализ фото еды\n"
        "• Советы по КБЖУ\n"
        "• Списки покупок\n\n"

        "💪 <b>Тренировки</b>\n"
        "• Планы тренировок\n"
        "• Отслеживание прогресса\n"
        "• Медали и достижения\n"
        "• Еженедельные челленджи\n\n"

        "🏆 <b>Мотивация</b>\n"
        "• Рейтинги участников\n"
        "• Статусы и уровни\n"
        "• Напоминания\n\n"

        "🎯 <b>Начни с 3-дневного теста бесплатно!</b>"
    )

    await message.answer(features_text, parse_mode="HTML")


@start_router.message(F.text == "Пропустить")
async def skip_step(message: Message, state: FSMContext):
    """Пропуск шага онбординга"""
    current_state = await state.get_state()

    if current_state == "onboarding_age":
        await state.update_data(age=None)
        await message.answer(
            "Какой у тебя рост в см?",
            reply_markup=ReplyKeyboardBuilder().button(text="Пропустить").as_markup(resize_keyboard=True)
        )
        await state.set_state("onboarding_height")

    # Добавьте обработку других состояний по аналогии


# Добавим тестовый обработчик для проверки GPT
@start_router.message(Command("test_gpt"))
async def cmd_test_gpt(message: Message):
    """Тестовая команда для проверки GPT"""
    try:
        from app.utils.openai_client import ask_gpt

        await message.answer("🔄 Тестируем подключение к GPT...")

        response = await ask_gpt("Привет! Ответь коротко - как начать правильно питаться?")

        await message.answer(f"🤖 GPT отвечает:\n\n{response}")
        logger.info(f"GPT тест выполнен для пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка теста GPT: {e}")
        await message.answer("❌ Ошибка при обращении к GPT")