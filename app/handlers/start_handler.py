from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import logging
from datetime import datetime, timedelta  # добавил

from app.utils.states import OnboardingStates
from app.utils.navigation import Navigation
from app.database.crud import UserCRUD

logger = logging.getLogger(__name__)
start_router = Router()


def get_goal_keyboard():
    """Клавиатура для выбора цели"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Похудение")],
            [KeyboardButton(text="Набор массы")],
            [KeyboardButton(text="Поддержание")],
            [KeyboardButton(text="Рельеф")],
            [KeyboardButton(text="Здоровье")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db=None):
    """Главное меню"""
    try:
        await state.clear()

        # Проверяем реферальные параметры
        args = message.text.split()
        if len(args) > 1:
            ref_param = args[1]
            logger.info(f"Реферальный параметр: {ref_param} от пользователя {message.from_user.id}")

        # Проверяем, есть ли пользователь в БД
        user = None
        if db:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)

        if not user:
            # Новый пользователь - оригинальный текст
            await message.answer(
                "Привет! Я бот Лизы — помогу тебе с питанием, фото-анализом и тренировками.\n"
                "3 дня теста бесплатно. Начнём?",
                reply_markup=Navigation.get_onboarding_start_keyboard()
            )
        else:
            # Существующий пользователь
            await message.answer(
                f"👋 *С возвращением!*\n\n"
                f"Выбери раздел:",
                parse_mode="Markdown",
                reply_markup=Navigation.get_main_menu()
            )

        logger.info(f"Пользователь {message.from_user.id} запустил бота")

    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@start_router.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer(
        "Главное меню:",
        reply_markup=Navigation.get_main_menu()
    )


@start_router.message(F.text == "❌ Отменить действие")
async def cancel_action(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer(
        "✅ Действие отменено.\n"
        "Выбери, что хочешь сделать:",
        reply_markup=Navigation.get_main_menu()
    )


@start_router.message(F.text == "✅ Да, начать")
async def start_trial(message: Message, state: FSMContext, db=None):
    """Начало триального периода"""
    try:
        await message.answer(
            "🎉 Отлично! Давай создадим твой персональный план.\n\n"
            "🎯 <b>Какую цель ты преследуешь?</b>",
            parse_mode="HTML",
            reply_markup=get_goal_keyboard()
        )

        # Устанавливаем состояние - выбор цели
        await state.set_state(OnboardingStates.waiting_goal)
        logger.info(f"Пользователь {message.from_user.id} начал онбординг с выбора цели")

    except Exception as e:
        logger.error(f"Ошибка в start_trial: {e}")
        await message.answer("❌ Ошибка при запуске теста")


@start_router.message(F.text == "ℹ️ Что умеет бот")
async def bot_features(message: Message):
    """Описание возможностей бота - оригинальный текст"""
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

    await message.answer(features_text, parse_mode="HTML", reply_markup=Navigation.get_back_button())


@start_router.message(F.text == "❌ Не сейчас")
async def not_now(message: Message):
    """Пользователь не хочет начинать сейчас"""
    await message.answer(
        "Хорошо! Если захочешь начать, просто напиши /start",
        reply_markup=Navigation.get_main_menu()
    )


@start_router.message(F.text == "🍽 Питание")
async def nutrition_menu(message: Message):
    """Меню питания"""
    await message.answer(
        "🍽 *Раздел питания*\n\n"
        "Выбери действие:",
        parse_mode="Markdown",
        reply_markup=Navigation.get_nutrition_menu()
    )


@start_router.message(F.text == "💎 Премиум")
async def premium_menu(message: Message):
    """Меню премиум"""
    await message.answer(
        "💎 *Премиум подписка*\n\n"
        "Получи доступ к:\n"
        "• 📸 Анализу фото еды\n"
        "• 📊 Расширенной статистике\n"
        "• ♾️ Безлимитным запросам\n\n"
        "Стоимость от 299 ₽/мес",
        parse_mode="Markdown",
        reply_markup=Navigation.get_premium_inline_menu()
    )


@start_router.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    """Меню помощи"""
    await message.answer(
        "❓ *Помощь*\n\n"
        "Выбери раздел:",
        parse_mode="Markdown",
        reply_markup=Navigation.get_help_menu()
    )


@start_router.message(F.text == "📋 Команды бота")
async def bot_commands(message: Message):
    """Список команд"""
    await message.answer(
        "📋 *Основные команды:*\n\n"
        "/start - Главное меню\n"
        "/subscribe - Оформить подписку\n"
        "/analyze - Анализ фото еды\n"
        "/premium - Премиум функции\n"
        "/status - Статус подписки\n"
        "/cancel - Отменить действие",
        parse_mode="Markdown",
        reply_markup=Navigation.get_back_button()
    )


@start_router.message(F.text == "📞 Связаться с поддержкой")
async def support(message: Message):
    """Поддержка"""
    await message.answer(
        "📞 *Служба поддержки*\n\n"
        "По всем вопросам пишите:\n"
        "✉️ @support_bot\n\n"
        "Среднее время ответа: до 24 часов",
        parse_mode="Markdown",
        reply_markup=Navigation.get_back_button()
    )


@start_router.message(F.text == "📸 Анализ фото")
async def analyze_photo_button(message: Message, state: FSMContext):
    """Кнопка анализа фото"""
    from app.handlers.photo_handler import cmd_analyze
    await cmd_analyze(message, state)


@start_router.message(F.text == "📝 Описать еду")
async def describe_food_button(message: Message):
    """Кнопка описания еды"""
    await message.answer(
        "📝 *Опиши, что ты съел*\n\n"
        "Например:\n"
        "• 'Съел тарелку борща со сметаной'\n"
        "• 'Выпил стакан молока 3.2%'\n"
        "• 'Перекусил яблоком'\n\n"
        "Я оценю калорийность и БЖУ.",
        parse_mode="Markdown",
        reply_markup=Navigation.get_cancel_keyboard()
    )


@start_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        logger.info(f"🔄 Отмена состояния {current_state} для пользователя {message.from_user.id}")
        await state.clear()
        await message.answer(
            "❌ Действие отменено.\n"
            "Выбери, что хочешь сделать:",
            reply_markup=Navigation.get_main_menu()
        )
    else:
        await message.answer(
            "Нет активного действия для отмены.",
            reply_markup=Navigation.get_main_menu()
        )


@start_router.message(Command("status"))
async def cmd_status(message: Message, db=None):
    """Показать статус подписки"""
    if not db:
        await message.answer("❌ Ошибка: нет подключения к базе данных")
        return

    try:
        user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден. Напишите /start для регистрации.",
                reply_markup=Navigation.get_main_menu()
            )
            return

        # Проверяем статус подписки
        now = datetime.utcnow()

        status_text = "❌ Нет активной подписки"
        days_left = 0

        # ✅ ИСПРАВЛЕНО: используем subscription_until
        if user.subscription_until and user.subscription_until > now:
            days_left = (user.subscription_until - now).days
            status_text = f"⭐ Премиум подписка (осталось {days_left} дн.)"
        elif user.trial_started_at:
            trial_end = user.trial_started_at + timedelta(days=3)
            if now < trial_end:
                days_left = (trial_end - now).days
                status_text = f"🆓 Бесплатный триал (осталось {days_left} дн.)"

        # Формируем ответ
        response = f"""
📊 **ТВОЯ СТАТИСТИКА**

👤 **Пользователь:** {user.full_name or user.username or 'Неизвестно'}
📅 **Зарегистрирован:** {user.created_at.strftime('%d.%m.%Y')}
📸 **Проанализировано фото:** {user.photo_analyzes_count or 0}

🔐 **СТАТУС ПОДПИСКИ:**
{status_text}

❓ Хочешь оформить подписку? /subscribe
        """

        await message.answer(response, parse_mode="Markdown", reply_markup=Navigation.get_main_menu())

    except Exception as e:
        logger.error(f"Ошибка в /status: {e}")
        await message.answer("❌ Произошла ошибка при получении статуса")


@start_router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню (из inline)"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=Navigation.get_main_menu()
    )
    await callback.answer()