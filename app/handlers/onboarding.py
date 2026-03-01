# app/handlers/onboarding.py
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
import logging
from datetime import datetime, timedelta

from app.utils.states import OnboardingStates, NutritionStates
from app.database.crud import UserCRUD
from app.database import AsyncSessionLocal
from app.utils.keyboards import get_goal_keyboard, get_gender_keyboard, get_yes_no_keyboard
from app.utils.openai_client import generate_meal_plan
from app.utils.calculations import calculate_calories
from app.utils.navigation import Navigation

logger = logging.getLogger(__name__)
onboarding_router = Router()


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
async def get_db_session():
    """Создать и вернуть новую сессию БД"""
    return AsyncSessionLocal()


@onboarding_router.message(Command("start", "subscribe", "analyze", "help", "cancel"))
async def cmd_during_onboarding(message: Message, state: FSMContext):
    """Обработка команд во время онбординга"""
    current_state = await state.get_state()
    logger.info(f"🚨 Получена команда {message.text} во время состояния {current_state}")

    # Сбрасываем состояние
    await state.clear()

    # Перенаправляем на соответствующий обработчик
    if message.text == "/start":
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
    elif message.text == "/subscribe":
        from app.handlers.payments import show_tariffs_handler
        await show_tariffs_handler(message, state)
    elif message.text == "/analyze":
        from app.handlers.photo_handler import cmd_analyze
        await cmd_analyze(message, state)
    elif message.text == "/help":
        await message.answer(
            "📚 Список команд:\n/start - Начать\n/subscribe - Подписка\n/analyze - Анализ фото\n/help - Помощь",
            reply_markup=Navigation.get_back_button()
        )
    elif message.text == "/cancel":
        await message.answer(
            "❌ Действие отменено. Можете начать заново с /start",
            reply_markup=Navigation.get_main_menu()
        )

# ---------- ШАГ 1: ЦЕЛЬ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_goal))
async def process_goal(message: Message, state: FSMContext):
    # ТЕСТОВОЕ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЮ
    await message.answer("✅ Функция process_goal вызвана! Сейчас обработаю твой выбор...")
    # ЭКСТРЕННЫЙ ЛОГ
    print("🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥")
    print(f"🔥🔥🔥 process_goal ВЫЗВАН! Текст: {message.text}")
    print("🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥")
    import sys
    sys.stdout.flush()
    logger.error(f"🔥🔥🔥🔥🔥🔥🔥 process_goal ВЫЗВАН для пользователя {message.from_user.id} с текстом {message.text}")

    # Проверяем на команды
    if message.text.startswith('/'):
        logger.info(f"🚫 Игнорируем команду {message.text} в состоянии выбора цели")
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    logger.info(f"🔥 process_goal ВЫЗВАНА!")
    logger.info(f"📝 Текст: {message.text}")
    logger.info(f"👤 User ID: {message.from_user.id}")

    goal = message.text.strip().lower()
    valid_goals = ['похудение', 'набор массы', 'поддержание', 'рельеф', 'здоровье']

    if goal not in valid_goals:
        logger.warning(f"❌ Невалидная цель: {goal}")
        await message.answer(
            "Пожалуйста, выбери цель из предложенных вариантов:\n"
            "• Похудение\n"
            "• Набор массы\n"
            "• Поддержание\n"
            "• Рельеф\n"
            "• Здоровье"
        )
        return

    # Сохраняем цель
    await update_user_data(message.from_user.id, goal=goal)
    await state.update_data(goal=goal)

    # Отправляем следующий вопрос
    await message.answer(
        "Отлично! Теперь укажи свой пол:",
        reply_markup=get_gender_keyboard()
    )

    # Меняем состояние
    await state.set_state(OnboardingStates.waiting_gender)

async def update_user_data(telegram_id: int, **kwargs):
    """Обновить данные пользователя в БД"""
    async with AsyncSessionLocal() as session:
        try:
            logger.info(f"🔄 Обновление пользователя {telegram_id} с данными: {kwargs}")

            # 1. Ищем пользователя
            user = await UserCRUD.get_by_telegram_id(session, telegram_id)

            # 2. Если пользователя нет - СОЗДАЕМ!
            if not user:
                logger.info(f"👤 Пользователь {telegram_id} не найден, создаем нового...")

                user = await UserCRUD.create(
                    session=session,
                    telegram_id=telegram_id,
                    username=None,
                    full_name=None
                )
                logger.info(f"✅ Создан новый пользователь: {telegram_id}, ID: {user.id}")

            # 3. Обновляем данные пользователя
            logger.info(f"📝 Обновляем данные пользователя {telegram_id}: {kwargs}")

            # Фильтруем None значения
            filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

            if filtered_kwargs:
                user = await UserCRUD.update_onboarding(session, user, **filtered_kwargs)
                logger.info(f"💾 Данные сохранены для пользователя {telegram_id}")
            else:
                logger.info(f"ℹ️ Нет данных для сохранения (все значения None)")

            return True

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Ошибка обновления пользователя {telegram_id}: {e}", exc_info=True)
            return False


async def split_and_send_messages(message: Message, text: str, parse_mode: str = 'HTML'):
    """Разбивает длинный текст на несколько сообщений и отправляет их"""
    MAX_TELEGRAM_LENGTH = 4096

    if len(text) <= MAX_TELEGRAM_LENGTH:
        await message.answer(text, parse_mode=parse_mode)
        return

    # Разбиваем текст на части
    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n\n')

    for paragraph in paragraphs:
        if len(paragraph) > MAX_TELEGRAM_LENGTH:
            sentences = paragraph.split('. ')
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > MAX_TELEGRAM_LENGTH:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "
                else:
                    current_chunk += sentence + ". "
        else:
            if len(current_chunk) + len(paragraph) + 2 > MAX_TELEGRAM_LENGTH:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Отправляем части с индикаторами прогресса
    total_chunks = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        if total_chunks > 1:
            chunk_with_indicator = f"📄 Часть {i}/{total_chunks}\n\n{chunk}"
            if i == total_chunks:
                chunk_with_indicator += "\n\n✅ План питания загружен полностью!"
        else:
            chunk_with_indicator = chunk

        await message.answer(chunk_with_indicator, parse_mode=parse_mode)




# ---------- ШАГ 2: ПОЛ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_gender))
async def process_gender(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    gender = message.text.strip().lower()
    if gender not in ['мужской', 'женский']:
        await message.answer("Пожалуйста, выбери пол из предложенных вариантов:")
        return

    await update_user_data(message.from_user.id, gender=gender)
    await state.update_data(gender=gender)

    # Спрашиваем возраст
    await message.answer(
        "Сколько тебе лет? (или напиши 'пропустить')",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_age)


# ---------- ШАГ 3: ВОЗРАСТ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_age))
async def process_age(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    logger.info(f"🔥 Получен возраст: {message.text}")

    if message.text.lower() == 'пропустить':
        age = None
    else:
        try:
            age = int(message.text)
            if not 10 <= age <= 100:
                await message.answer("Пожалуйста, введи реальный возраст (10-100 лет):")
                return
        except ValueError:
            await message.answer("Пожалуйста, введи число:")
            return

    await update_user_data(message.from_user.id, age=age)
    await state.update_data(age=age)
    await message.answer(
        "Какой у тебя рост (в см)?",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_height)


# ---------- ШАГ 4: РОСТ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_height))
async def process_height(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    try:
        height = int(message.text)
        if not 100 <= height <= 250:
            await message.answer("Пожалуйста, введи реальный рост (100-250 см):")
            return
    except ValueError:
        await message.answer("Пожалуйста, введи число:")
        return

    await update_user_data(message.from_user.id, height=height)
    await state.update_data(height=height)
    await message.answer(
        "Какой у тебя вес (в кг)?",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_weight)


# ---------- ШАГ 5: ВЕС ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_weight))
async def process_weight(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    try:
        weight = float(message.text.replace(',', '.'))
        if not 30 <= weight <= 300:
            await message.answer("Пожалуйста, введи реальный вес (30-300 кг):")
            return
    except ValueError:
        await message.answer("Пожалуйста, введи число:")
        return

    await update_user_data(message.from_user.id, weight=weight)
    await state.update_data(weight=weight)
    await message.answer(
        "Какие твои любимые продукты? (Перечисли через запятую)",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_favorite_foods)


# ---------- ШАГ 6: ЛЮБИМЫЕ ПРОДУКТЫ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_favorite_foods))
async def process_favorite_foods(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    favorite_foods = message.text.strip()
    await update_user_data(message.from_user.id, favorite_foods=favorite_foods)
    await state.update_data(favorite_foods=favorite_foods)
    await message.answer(
        "Есть ли продукты, которые ты не ешь? (аллергии, непереносимость, просто не любишь)",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_excluded_foods)


# ---------- ШАГ 7: ИСКЛЮЧАЕМЫЕ ПРОДУКТЫ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_excluded_foods))
async def process_excluded_foods(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    excluded_foods = message.text.strip()
    await update_user_data(message.from_user.id, excluded_foods=excluded_foods)
    await state.update_data(excluded_foods=excluded_foods)
    await message.answer(
        "Есть ли проблемы со здоровьем, которые нужно учесть? (если нет, напиши 'нет')",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_health_issues)


# ---------- ШАГ 8: ПРОБЛЕМЫ СО ЗДОРОВЬЕМ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_health_issues))
async def process_health_issues(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    if message.text == "🔙 В главное меню":
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=Navigation.get_main_menu()
        )
        return

    health_issues = message.text.strip()
    await update_user_data(message.from_user.id, health_issues=health_issues)
    await state.update_data(health_issues=health_issues)
    await message.answer(
        "Ты сейчас тренируешься? Если да, то как часто?",
        reply_markup=get_yes_no_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_training_current)


# ---------- ШАГ 9: ТРЕНИРОВКИ СЕЙЧАС ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_training_current))
async def process_training_current(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    training_current = message.text.strip()
    await update_user_data(message.from_user.id, training_current=training_current)
    await state.update_data(training_current=training_current)
    await message.answer(
        "Хочешь ли ты получать планы тренировок?",
        reply_markup=get_yes_no_keyboard()
    )
    await state.set_state(OnboardingStates.waiting_training_wants)


# ---------- ШАГ 10: ЖЕЛАНИЕ ТРЕНИРОВАТЬСЯ ----------
@onboarding_router.message(StateFilter(OnboardingStates.waiting_training_wants))
async def process_training_wants(message: Message, state: FSMContext):
    # Проверяем на команды
    if message.text.startswith('/'):
        from app.handlers.start_handler import cmd_start
        await cmd_start(message, state)
        return

    if message.text == "❌ Отменить действие":
        await message.answer(
            "❌ Онбординг отменен. Начни заново с /start",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()
        return

    wants_training = message.text.strip().lower() == 'да'
    await update_user_data(message.from_user.id, wants_training=wants_training)

    # Сообщаем что начали генерацию
    status_msg = await message.answer("⏳ Генерирую твой персональный план питания...")

    data = await state.get_data()

    # Проверить обязательные данные
    required_fields = ['gender', 'height', 'weight']
    missing_fields = [field for field in required_fields if data.get(field) is None]

    if missing_fields:
        await status_msg.delete()
        await message.answer(
            f"⚠️ Не хватает данных: {', '.join(missing_fields)}. Пожалуйста, заполни их.",
            reply_markup=Navigation.get_main_menu()
        )
        return

    # Для возраста используем значение по умолчанию если None
    age = data.get('age')
    age_for_calc = age if age is not None else 30
    if age is None:
        logger.info(f"⚠️ Возраст не указан, используем значение по умолчанию: 30")

    # Рассчитать калории
    try:
        calories = calculate_calories(
            gender=data['gender'],
            age=age_for_calc,
            height=data['height'],
            weight=data['weight'],
            goal=data.get('goal', 'поддержание'),
            activity=data.get('training_current', 'минимальная')
        )
    except Exception as e:
        logger.error(f"Ошибка расчёта калорий: {e}")
        calories = {'daily': 2000, 'target': 2000, 'maintenance': 2200}

    # Отправляем запрос на генерацию плана питания
    try:
        meal_plan = await generate_meal_plan(
            calories=calories,
            favorite_foods=data.get('favorite_foods'),
            excluded_foods=data.get('excluded_foods'),
            health_issues=data.get('health_issues'),
            goal=data.get('goal'),
            gender=data['gender'],
            age=age_for_calc,
            height=data['height'],
            weight=data['weight']
        )
    except Exception as e:
        logger.error(f"Ошибка генерации плана питания: {e}")
        meal_plan = "🍽 План питания временно недоступен."

    await status_msg.delete()

    # Формируем и отправляем ПЛАН ПИТАНИЯ
    response = f"""
📊 <b>Твой персональный план</b>

🎯 <b>Цель:</b> {data.get('goal', 'не указана')}
👤 <b>Пол:</b> {data.get('gender', 'не указан')}
📏 <b>Рост:</b> {data.get('height', 'не указан')} см
⚖️ <b>Вес:</b> {data.get('weight', 'не указан')} кг
🎂 <b>Возраст:</b> {'не указан' if data.get('age') is None else data.get('age')}

⚖️ <b>Рекомендуемая норма:</b> {calories['daily']} ккал/день
📈 <b>Для цели:</b> {calories['target']} ккал/день

🍽 <b>План питания:</b>
{meal_plan}
"""

    # Отправляем план питания
    await split_and_send_messages(message, response, parse_mode='HTML')

    # Если пользователь хочет тренировки - генерируем и отправляем отдельно
    if wants_training:
        training_status = await message.answer("⏳ Теперь генерирую программу тренировок...")

        try:
            from app.utils.openai_client import generate_training_plan

            training_plan = await generate_training_plan(
                goal=data.get('goal'),
                gender=data['gender'],
                age=age_for_calc,
                weight=data['weight'],
                height=data['height'],
                activity_level=data.get('training_current', 'начинающий'),
                health_issues=data.get('health_issues')
            )

            await training_status.delete()

            training_message = f"💪 <b>Программа тренировок</b>\n\n{training_plan}"
            await split_and_send_messages(message, training_message, parse_mode='HTML')

        except Exception as e:
            logger.error(f"Ошибка генерации тренировок: {e}")
            await training_status.delete()
            await message.answer(
                "⚠️ Не удалось сгенерировать программу тренировок. Попробуй позже.",
                reply_markup=Navigation.get_main_menu()
            )

    # Завершающее сообщение
    await message.answer(
        "✅ Твой 3-дневный тест начался!\n"
        "Доступ открыт до " + (datetime.utcnow() + timedelta(days=3)).strftime('%d.%m.%Y'),
        reply_markup=Navigation.get_main_menu()
    )

    await state.clear()


# ---------- ДЛЯ ОТЛАДКИ ----------
@onboarding_router.message()
async def debug_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logger.info(f"🔍 DEBUG: Пользователь {message.from_user.id} отправил: '{message.text}', состояние: {current_state}")

    # Если есть активное состояние, но оно не обработано - сообщим об этом
    if current_state:
        await message.answer(
            f"⚠️ Что-то пошло не так. Текущее состояние: {current_state}.\n"
            f"Напиши /start чтобы начать заново.",
            reply_markup=Navigation.get_main_menu()
        )