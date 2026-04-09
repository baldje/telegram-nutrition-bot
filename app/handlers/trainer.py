from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import date, datetime, timedelta
import os
import asyncio
import calendar
from collections import defaultdict

from app.database.crud import UserCRUD, FoodDiaryCRUD, TrainerCRUD, NutritionCalculator
from app.utils.navigation import Navigation

logger = logging.getLogger(__name__)
router = Router()

BOT_USERNAME = os.getenv("BOT_USERNAME", "health_ntrtn_helperAI_bot")


class TrainerActions(StatesGroup):
    waiting_username = State()
    waiting_client_id = State()
    waiting_comment = State()
    waiting_advice = State()
    waiting_entry_id = State()


# ===== ПАНЕЛЬ ТРЕНЕРА =====

@router.message(F.text == "👨‍🏫 Тренер")
async def trainer_entry(message: Message, db=None):
    if not db:
        return
    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user or user.role != 'trainer':
        await message.answer(
            "👨‍🏫 *Раздел для тренеров*\n\nЭта функция доступна только наставникам.",
            parse_mode="HTML",
            reply_markup=Navigation.get_back_button()
        )
        return
    await trainer_panel(message, db, user)


async def trainer_panel(message: Message, db=None, user=None):
    if not db:
        return
    if user is None:
        user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user or user.role != 'trainer':
        await message.answer("❌ Нет прав тренера")
        return

    from sqlalchemy import select
    from app.database.models import TrainerClient, User as UserModel

    result = await db.session.execute(
        select(UserModel).join(TrainerClient, TrainerClient.client_id == UserModel.id)
        .where(TrainerClient.trainer_id == user.id)
        .where(TrainerClient.status == 'active')
    )
    clients = result.scalars().all()

    today_entries = 0
    today_calories = 0
    for client in clients:
        entries = await FoodDiaryCRUD.get_day_entries(db.session, client.id, date.today())
        today_entries += len(entries)
        today_calories += sum(e.calories or 0 for e in entries)

    result = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == user.id,
            TrainerClient.status == 'pending'
        )
    )
    pending_count = len(result.scalars().all())

    text = (
        f"👨‍🏫 *Панель наставника*\n\n"
        f"👤 {user.full_name or user.username}\n"
        f"👥 Подопечных: {len(clients)}\n"
        f"⏳ Ожидают подтверждения: {pending_count}\n"
        f"📊 Статистика за сегодня:\n"
        f"   • 📝 Записей: {today_entries}\n"
        f"   • 🔥 Калорий: {today_calories} ккал\n\n"
        f"Выберите действие:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить подопечного", callback_data="trainer_add_menu")],
        [InlineKeyboardButton(text="👥 Список подопечных", callback_data="trainer_list_clients")],
        [InlineKeyboardButton(text="⏳ Ожидают подтверждения", callback_data="trainer_pending_requests")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="trainer_stats")],
        [InlineKeyboardButton(text="🔗 Моя ссылка для приглашения", callback_data="trainer_invite_link")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== МЕНЮ ДОБАВЛЕНИЯ =====

@router.callback_query(F.data == "trainer_add_menu")
async def add_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 По username", callback_data="trainer_add_by_username")],
        [InlineKeyboardButton(text="🆔 По Telegram ID", callback_data="trainer_add_by_id")],
        [InlineKeyboardButton(text="🔗 Дать ссылку клиенту", callback_data="trainer_invite_link")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_back")]
    ])
    await callback.message.edit_text(
        "➕ *Как добавить подопечного?*\n\nВыберите способ:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


# ===== ДОБАВЛЕНИЕ ПО USERNAME (оставляем как есть) =====
@router.callback_query(F.data == "trainer_add_by_username")
async def add_by_username_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 *Введите username подопечного*\n\nПример: @ivan_ivanov",
        parse_mode="HTML",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(TrainerActions.waiting_username)
    await callback.answer()


@router.message(TrainerActions.waiting_username, F.text)
async def add_by_username_process(message: Message, state: FSMContext, db=None):
    from sqlalchemy import select
    from app.database.models import User, TrainerClient

    username = message.text.strip().lstrip('@')
    if not username:
        await message.answer("❌ Введите username")
        return

    result = await db.session.execute(select(User).where(User.username == username))
    client = result.scalar_one_or_none()
    if not client:
        await message.answer(f"❌ Пользователь @{username} не найден")
        await state.clear()
        return

    trainer = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if client.id == trainer.id:
        await message.answer("❌ Нельзя добавить себя")
        await state.clear()
        return

    # Проверки существующих связей
    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client.id
        )
    )
    existing = rel.scalar_one_or_none()
    if existing:
        if existing.status == 'active':
            await message.answer("⚠️ Уже ваш подопечный")
        else:
            await message.answer("⏳ Запрос уже отправлен")
        await state.clear()
        return

    new_request = TrainerClient(
        trainer_id=trainer.id,
        client_id=client.id,
        status='pending'
    )
    db.session.add(new_request)
    await db.session.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"confirm_trainer_{trainer.id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_trainer_{trainer.id}")]
    ])

    try:
        await message.bot.send_message(
            client.telegram_id,
            f"👨‍🏫 *Запрос на подключение к тренеру!*\n\n"
            f"Тренер {trainer.full_name or trainer.username} хочет добавить вас в подопечные.\n\n"
            f"✅ Принять — тренер сможет следить за вашим прогрессом\n"
            f"❌ Отклонить — отклонить запрос",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await message.answer(f"✅ Запрос отправлен @{username}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Не удалось отправить запрос")
        await db.session.delete(new_request)
        await db.session.commit()

    await state.clear()


# ===== ПОДТВЕРЖДЕНИЕ ОТ КЛИЕНТА (оставляем как есть) =====
@router.callback_query(F.data.startswith("confirm_trainer_"))
async def confirm_trainer_from_client(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    trainer_id = int(callback.data.split("_")[2])
    client = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    if not client:
        await callback.answer("❌ Ошибка")
        return

    result = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer_id,
            TrainerClient.client_id == client.id,
            TrainerClient.status == 'pending'
        )
    )
    request = result.scalar_one_or_none()
    if not request:
        await callback.answer("❌ Запрос не найден")
        return

    request.status = 'active'
    await db.session.commit()

    trainer = await UserCRUD.get_by_id(db.session, trainer_id)
    await callback.bot.send_message(
        trainer.telegram_id,
        f"🎉 *Клиент подтвердил подключение!*\n\n👤 {client.full_name or client.username} теперь ваш подопечный.",
        parse_mode="HTML"
    )
    await callback.message.edit_text("✅ Подключение подтверждено")
    await callback.answer()


@router.callback_query(F.data.startswith("reject_trainer_"))
async def reject_trainer_from_client(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    trainer_id = int(callback.data.split("_")[2])
    client = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    result = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer_id,
            TrainerClient.client_id == client.id,
            TrainerClient.status == 'pending'
        )
    )
    request = result.scalar_one_or_none()
    if request:
        await db.session.delete(request)
        await db.session.commit()
        await callback.message.edit_text("❌ Вы отклонили запрос")
    await callback.answer()


# ===== СПИСОК ОЖИДАЮЩИХ (тренер) =====
@router.callback_query(F.data == "trainer_pending_requests")
async def pending_requests(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient, User as UserModel

    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    result = await db.session.execute(
        select(TrainerClient, UserModel)
        .join(UserModel, TrainerClient.client_id == UserModel.id)
        .where(TrainerClient.trainer_id == trainer.id, TrainerClient.status == 'pending')
    )
    pending = result.all()

    if not pending:
        await callback.message.edit_text(
            "📭 *Нет ожидающих запросов*",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_back")]])
        )
        return

    text = "⏳ *Ожидают подтверждения:*\n\n"
    keyboard = InlineKeyboardBuilder()
    for req, client in pending:
        name = client.full_name or client.username or str(client.telegram_id)
        text += f"• {name}\n"
        keyboard.row(
            InlineKeyboardButton(text=f"✅ Принять {name[:20]}", callback_data=f"confirm_pending_{req.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_pending_{req.id}")
        )
    keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_back"))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_pending_"))
async def confirm_pending_request(callback: CallbackQuery, db=None):
    """Тренер подтверждает ожидающий запрос"""
    from sqlalchemy import select
    from app.database.models import TrainerClient, User

    request_id = int(callback.data.split("_")[2])

    # 1. Получаем данные ДО изменения или коммита
    result = await db.session.execute(
        select(TrainerClient, User)
        .join(User, TrainerClient.client_id == User.id)
        .where(TrainerClient.id == request_id)
    )
    row = result.first()
    if not row:
        await callback.answer("❌ Запрос не найден", show_alert=True)
        return

    request, client = row

    # 2. СОХРАНЯЕМ НУЖНЫЕ ДАННЫЕ в обычные переменные (чтобы они были доступны после коммита)
    client_telegram_id = client.telegram_id
    client_full_name = client.full_name or client.username or str(client_telegram_id)

    # 3. Обновляем статус (теперь это безопасно)
    request.status = 'active'
    await db.session.commit()

    # 4. Уведомляем клиента, используя сохранённые данные
    try:
        await callback.bot.send_message(
            client_telegram_id,
            f"🎉 *Тренер подтвердил подключение!*\n\n"
            f"Теперь тренер может следить за вашим прогрессом.\n\n"
            f"Нажмите 👨‍🏫 Мой тренер, чтобы увидеть информацию.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить клиента: {e}")

    await callback.answer("✅ Клиент подтвержден")
    await pending_requests(callback, db)


@router.callback_query(F.data.startswith("reject_pending_"))
async def reject_pending_request(callback: CallbackQuery, db=None):
    """Тренер отклоняет ожидающий запрос"""
    from sqlalchemy import select
    from app.database.models import TrainerClient, User

    request_id = int(callback.data.split("_")[2])

    result = await db.session.execute(
        select(TrainerClient, User)
        .join(User, TrainerClient.client_id == User.id)
        .where(TrainerClient.id == request_id)
    )
    row = result.first()
    if not row:
        await callback.answer("❌ Запрос не найден", show_alert=True)
        return

    request, client = row

    # Сохраняем нужные ДО удаления
    client_telegram_id = client.telegram_id
    client_full_name = client.full_name or client.username or str(client_telegram_id)

    # Удаляем запрос
    await db.session.delete(request)
    await db.session.commit()

    try:
        await callback.bot.send_message(
            client_telegram_id,
            f"❌ *Тренер отклонил запрос на подключение*\n\n"
            f"Вы можете попробовать подключиться к другому тренеру.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить клиента: {e}")

    await callback.answer("❌ Запрос отклонен")
    await pending_requests(callback, db)


# ===== СПИСОК АКТИВНЫХ КЛИЕНТОВ =====
@router.callback_query(F.data == "trainer_list_clients")
async def list_clients(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import User as UserModel, TrainerClient

    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    result = await db.session.execute(
        select(UserModel).join(TrainerClient, TrainerClient.client_id == UserModel.id)
        .where(TrainerClient.trainer_id == trainer.id, TrainerClient.status == 'active')
    )
    clients = result.scalars().all()

    if not clients:
        await callback.message.edit_text(
            "📭 *Нет подопечных*",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить", callback_data="trainer_add_menu")]])
        )
        return

    text = "👥 *Мои подопечные*\n\n"
    keyboard = InlineKeyboardBuilder()
    for client in clients:
        entries = await FoodDiaryCRUD.get_day_entries(db.session, client.id, date.today())
        cal = sum(e.calories or 0 for e in entries)
        text += f"{'🟢' if cal else '⚪️'} {client.full_name or client.username} — {cal} ккал сегодня\n"
        keyboard.row(InlineKeyboardButton(text=f"📊 {client.full_name or client.username}", callback_data=f"trainer_client_{client.id}"))
    keyboard.row(InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_back"))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("trainer_client_"))
async def client_detail(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    client_id = int(callback.data.split("_")[2])
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'active'
        )
    )
    if not rel.scalar_one_or_none():
        await callback.answer("⛔ Нет доступа")
        return

    client = await UserCRUD.get_by_id(db.session, client_id)
    today_entries = await FoodDiaryCRUD.get_day_entries(db.session, client_id, date.today())
    total_cal = sum(e.calories or 0 for e in today_entries)

    week_entries = await FoodDiaryCRUD.get_week_entries(db.session, client_id)
    week_cal = sum(e.calories or 0 for e in week_entries)

    text = (
        f"📊 *Статистика подопечного*\n\n"
        f"👤 {client.full_name or client.username}\n"
        f"🎯 Цель: {client.goal or 'не указана'}\n\n"
        f"📅 *Сегодня:* {total_cal} ккал, {len(today_entries)} записей\n"
        f"📊 *За неделю:* {week_cal} ккал\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Дневник", callback_data=f"trainer_diary_menu_{client_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"trainer_remove_{client_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_list_clients")]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== МЕНЮ ВЫБОРА ПЕРИОДА ДЛЯ ДНЕВНИКА =====
@router.callback_query(F.data.startswith("trainer_diary_menu_"))
async def diary_period_menu(callback: CallbackQuery, state: FSMContext):
    client_id = int(callback.data.split("_")[3])
    await state.update_data(diary_client_id=client_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"diary_today_{client_id}"),
         InlineKeyboardButton(text="📆 Вчера", callback_data=f"diary_yesterday_{client_id}")],
        [InlineKeyboardButton(text="📊 Неделя", callback_data=f"diary_week_{client_id}"),
         InlineKeyboardButton(text="📅 Выбрать дату", callback_data=f"diary_calendar_{client_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"trainer_client_{client_id}")]
    ])

    await callback.message.edit_text(
        "📆 *Выберите период для просмотра дневника:*",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


# ===== БЫСТРЫЕ ПЕРИОДЫ =====
@router.callback_query(F.data.startswith("diary_today_"))
async def diary_today(callback: CallbackQuery, db=None):
    client_id = int(callback.data.split("_")[2])
    await show_diary_for_date(callback, db, client_id, date.today())


@router.callback_query(F.data.startswith("diary_yesterday_"))
async def diary_yesterday(callback: CallbackQuery, db=None):
    client_id = int(callback.data.split("_")[2])
    yesterday = date.today() - timedelta(days=1)
    await show_diary_for_date(callback, db, client_id, yesterday)


@router.callback_query(F.data.startswith("diary_week_"))
async def diary_week(callback: CallbackQuery, state: FSMContext, db=None):
    """Показать список дней за последние 7 дней с калориями"""
    from sqlalchemy import select
    from app.database.models import TrainerClient
    from collections import defaultdict

    client_id = int(callback.data.split("_")[2])
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

    # Проверяем доступ
    result = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'active'
        )
    )
    if not result.scalar_one_or_none():
        await callback.answer("⛔ Нет доступа")
        return

    client = await UserCRUD.get_by_id(db.session, client_id)

    # Сохраняем client_id в state для дальнейшего использования
    await state.update_data(week_client_id=client_id)

    # Получаем записи за последние 7 дней
    week_entries = await FoodDiaryCRUD.get_week_entries(db.session, client_id)

    # Группируем по датам
    days_data = defaultdict(lambda: {"calories": 0, "entries_count": 0, "date": None})

    for entry in week_entries:
        entry_date = entry.meal_date.date()
        days_data[entry_date]["calories"] += entry.calories or 0
        days_data[entry_date]["entries_count"] += 1
        days_data[entry_date]["date"] = entry_date

    # Сортируем даты от самой новой к старой
    sorted_days = sorted(days_data.keys(), reverse=True)

    if not sorted_days:
        await callback.message.edit_text(
            f"📊 *Недельная сводка для {client.full_name or client.username}*\n\n"
            f"Нет записей за последние 7 дней.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"trainer_diary_menu_{client_id}")]
            ])
        )
        await callback.answer()
        return

    # Формируем текст и клавиатуру
    text = f"📆 *Выберите день для просмотра*\n\n👤 {client.full_name or client.username}\n\n"
    keyboard = InlineKeyboardBuilder()

    for day_date in sorted_days:
        data = days_data[day_date]
        day_str = day_date.strftime("%d.%m.%Y")
        weekday = day_date.strftime("%A")
        # Перевод дней недели
        weekdays_ru = {
            "Monday": "ПН", "Tuesday": "ВТ", "Wednesday": "СР",
            "Thursday": "ЧТ", "Friday": "ПТ", "Saturday": "СБ", "Sunday": "ВС"
        }
        weekday_ru = weekdays_ru.get(weekday, weekday[:2])
        text += f"• {day_str} ({weekday_ru}): {data['calories']} ккал, {data['entries_count']} записей\n"
        keyboard.row(InlineKeyboardButton(
            text=f"📅 {day_str} ({weekday_ru})",
            callback_data=f"week_day_{day_date.strftime('%Y-%m-%d')}_{client_id}"
        ))

    keyboard.row(InlineKeyboardButton(text="◀️ Назад к выбору периода", callback_data=f"trainer_diary_menu_{client_id}"))

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()


# ===== КАЛЕНДАРЬ ДЛЯ ВЫБОРА ДАТЫ =====
@router.callback_query(F.data.startswith("diary_calendar_"))
async def calendar_start(callback: CallbackQuery, state: FSMContext):
    client_id = int(callback.data.split("_")[2])
    await state.update_data(calendar_client_id=client_id)
    now = datetime.now()
    await show_calendar(callback, now.year, now.month)


async def show_calendar(callback: CallbackQuery, year: int, month: int):
    """Отображает inline-календарь"""
    cal = calendar.monthcalendar(year, month)
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=f"{month_names[month-1]} {year}", callback_data="ignore"))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.row(*[InlineKeyboardButton(text=d, callback_data="ignore") for d in week_days])

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"calendar_date_{date_str}"))
        keyboard.row(*row)

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.row(
        InlineKeyboardButton(text="◀️", callback_data=f"calendar_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="trainer_back"),
        InlineKeyboardButton(text="▶️", callback_data=f"calendar_next_{next_year}_{next_month}")
    )

    await callback.message.edit_text(
        "📅 *Выберите дату:*\n(доступны записи за последние 7 дней)",
        parse_mode="HTML",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("calendar_prev_"))
async def calendar_prev(callback: CallbackQuery):
    _, _, year, month = callback.data.split("_")
    await show_calendar(callback, int(year), int(month))


@router.callback_query(F.data.startswith("calendar_next_"))
async def calendar_next(callback: CallbackQuery):
    _, _, year, month = callback.data.split("_")
    await show_calendar(callback, int(year), int(month))


@router.callback_query(F.data.startswith("calendar_date_"))
async def calendar_date_selected(callback: CallbackQuery, state: FSMContext, db=None):
    date_str = callback.data.split("_")[2]
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    days_ago = (date.today() - selected_date).days
    if days_ago > 7:
        await callback.answer("❌ Можно смотреть только за последние 7 дней", show_alert=True)
        return

    data = await state.get_data()
    client_id = data.get("calendar_client_id")
    if not client_id:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    await show_diary_for_date(callback, db, client_id, selected_date)


# ===== ОТОБРАЖЕНИЕ ДНЕВНИКА ЗА КОНКРЕТНУЮ ДАТУ =====
async def show_diary_for_date(callback: CallbackQuery, db, client_id: int, view_date: date):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'active'
        )
    )
    if not rel.scalar_one_or_none():
        await callback.answer("⛔ Нет доступа")
        return

    client = await UserCRUD.get_by_id(db.session, client_id)
    entries = await FoodDiaryCRUD.get_day_entries(db.session, client_id, view_date)

    if not entries:
        await callback.message.edit_text(
            f"📭 *Дневник {client.full_name or client.username} за {view_date.strftime('%d.%m.%Y')}*\n\nПока нет записей.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"trainer_diary_menu_{client_id}")]
            ])
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📔 *Дневник {client.full_name or client.username} за {view_date.strftime('%d.%m.%Y')}*\n\nЗагружаю...",
        parse_mode="HTML"
    )

    for i, entry in enumerate(entries, 1):
        meal_emoji = {"breakfast": "🌅", "lunch": "☀️", "dinner": "🌙", "snack": "🍎"}.get(entry.meal_type, "🍽")
        meal_ru = {"breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин", "snack": "Перекус"}.get(entry.meal_type, "")
        time_str = entry.meal_date.strftime("%H:%M")

        caption = (
            f"{meal_emoji} *{meal_ru}* ({time_str}) — запись {i}/{len(entries)}\n\n"
            f"📝 {entry.description[:200]}\n\n"
            f"🔥 *{entry.calories}* ккал\n"
            f"🥩 Белки: *{entry.protein:.0f}* г\n"
            f"🧈 Жиры: *{entry.fat:.0f}* г\n"
            f"🍚 Углеводы: *{entry.carbs:.0f}* г"
        )

        if entry.photo_file_id:
            try:
                await callback.message.answer_photo(photo=entry.photo_file_id, caption=caption, parse_mode="HTML")
            except Exception:
                await callback.message.answer(caption, parse_mode="HTML")
        else:
            await callback.message.answer(caption, parse_mode="HTML")
        await asyncio.sleep(0.3)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к выбору периода", callback_data=f"trainer_diary_menu_{client_id}")]
    ])
    await callback.message.answer("✅ *Конец записей*", parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


async def show_week_diary(callback: CallbackQuery, db, client_id: int):
    """Показывает сводку за 7 дней (суммарно)"""
    from sqlalchemy import select
    from app.database.models import TrainerClient

    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'active'
        )
    )
    if not rel.scalar_one_or_none():
        await callback.answer("⛔ Нет доступа")
        return

    client = await UserCRUD.get_by_id(db.session, client_id)
    week_entries = await FoodDiaryCRUD.get_week_entries(db.session, client_id)

    if not week_entries:
        await callback.message.edit_text(
            f"📊 *Недельная сводка для {client.full_name or client.username}*\n\nНет записей за последние 7 дней.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"trainer_diary_menu_{client_id}")]
            ])
        )
        await callback.answer()
        return

    total_cal = sum(e.calories or 0 for e in week_entries)
    text = (
        f"📊 *Недельная сводка*\n\n"
        f"👤 {client.full_name or client.username}\n"
        f"📅 За последние 7 дней:\n"
        f"• 🔥 {total_cal} ккал\n"
        f"• 📝 {len(week_entries)} записей\n"
        f"• 📊 Среднее: {total_cal // 7} ккал/день"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к выбору периода", callback_data=f"trainer_diary_menu_{client_id}")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== УДАЛЕНИЕ КЛИЕНТА =====
@router.callback_query(F.data.startswith("trainer_remove_"))
async def remove_client(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    client_id = int(callback.data.split("_")[2])
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'active'
        )
    )
    relation = rel.scalar_one_or_none()
    if relation:
        await db.session.delete(relation)
        await db.session.commit()
        await callback.answer("✅ Удалён")
        await trainer_panel(callback.message, db)
    else:
        await callback.answer("❌ Связь не найдена")


# ===== ОБЩАЯ СТАТИСТИКА =====
@router.callback_query(F.data == "trainer_stats")
async def trainer_stats(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import User as UserModel, TrainerClient

    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    result = await db.session.execute(
        select(UserModel).join(TrainerClient, TrainerClient.client_id == UserModel.id)
        .where(TrainerClient.trainer_id == trainer.id, TrainerClient.status == 'active')
    )
    clients = result.scalars().all()
    if not clients:
        await callback.answer("Нет подопечных")
        return

    text = "📊 *Общая статистика*\n\n"
    for client in clients:
        entries = await FoodDiaryCRUD.get_day_entries(db.session, client.id, date.today())
        cal = sum(e.calories or 0 for e in entries)
        text += f"👤 {client.full_name or client.username}: {cal} ккал сегодня\n"
    text += f"\n👥 Всего: {len(clients)} подопечных"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_back")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== НАЗАД =====
@router.callback_query(F.data == "trainer_back")
async def trainer_back(callback: CallbackQuery, state: FSMContext, db=None):
    await state.clear()
    user = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    if not user:
        await callback.message.answer("❌ Ошибка")
        return
    await callback.message.delete()
    await trainer_panel(callback.message, db, user)
    await callback.answer()


# ===== ССЫЛКА-ПРИГЛАШЕНИЕ =====
@router.callback_query(F.data == "trainer_invite_link")
async def get_invite_link(callback: CallbackQuery, db=None):
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start=trainer_{trainer.id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить", url=f"https://t.me/share/url?url={link}&text=Привет! Присоединяйся ко мне в Nutrition Bot!")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="trainer_add_menu")]
    ])
    await callback.message.edit_text(
        f"🔗 *Ваша ссылка:*\n`{link}`\n\n"
        "Клиент переходит → автоматический запрос → вы подтверждаете.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


# ===== КОМАНДА /trainer ОТ КЛИЕНТА =====
@router.message(Command("trainer"))
async def connect_to_trainer_by_command(message: Message, db=None):
    from sqlalchemy import select
    from app.database.models import User, TrainerClient

    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("📝 Использование: `/trainer @username_тренера`", parse_mode="HTML")
        return

    username = args[1].lstrip('@')
    result = await db.session.execute(select(User).where(User.username == username, User.role == 'trainer'))
    trainer = result.scalar_one_or_none()
    if not trainer:
        await message.answer(f"❌ Тренер @{username} не найден")
        return

    # Проверки
    rel = await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == user.id
        )
    )
    existing = rel.scalar_one_or_none()
    if existing:
        if existing.status == 'active':
            await message.answer("✅ Уже связаны")
        else:
            await message.answer("⏳ Запрос уже отправлен")
        return

    new_req = TrainerClient(trainer_id=trainer.id, client_id=user.id, status='pending')
    db.session.add(new_req)
    await db.session.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"confirm_client_{user.id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_client_{user.id}")]
    ])

    try:
        await message.bot.send_message(
            trainer.telegram_id,
            f"📨 *Новый запрос от {user.full_name or user.username}*",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await message.answer(f"✅ Запрос отправлен тренеру @{username}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Не удалось отправить запрос")
        await db.session.delete(new_req)
        await db.session.commit()


@router.callback_query(F.data.startswith("confirm_client_"))
async def confirm_client_request(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    client_id = int(callback.data.split("_")[2])
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

    req = (await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'pending'
        )
    )).scalar_one_or_none()

    if not req:
        await callback.answer("❌ Запрос не найден")
        return

    req.status = 'active'
    await db.session.commit()
    client = await UserCRUD.get_by_id(db.session, client_id)
    await callback.bot.send_message(
        client.telegram_id,
        f"🎉 *Тренер принял запрос!* Теперь он следит за вашим прогрессом.",
        parse_mode="HTML"
    )
    await callback.message.edit_text("✅ Клиент добавлен")
    await callback.answer()


@router.callback_query(F.data.startswith("reject_client_"))
async def reject_client_request(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    client_id = int(callback.data.split("_")[2])
    trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

    req = (await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.trainer_id == trainer.id,
            TrainerClient.client_id == client_id,
            TrainerClient.status == 'pending'
        )
    )).scalar_one_or_none()

    if req:
        client = await UserCRUD.get_by_id(db.session, client_id)
        await db.session.delete(req)
        await db.session.commit()
        await callback.bot.send_message(client.telegram_id, "❌ Тренер отклонил запрос", parse_mode="HTML")
        await callback.message.edit_text("❌ Запрос отклонён")
    await callback.answer()


# ===== ПРОСМОТР ВЫБРАННОГО ДНЯ ИЗ НЕДЕЛЬНОЙ СВОДКИ =====
@router.callback_query(F.data.startswith("week_day_"))
async def week_day_selected(callback: CallbackQuery, db=None):
        """Показать все записи за выбранный день из недельной сводки"""
        from sqlalchemy import select
        from app.database.models import TrainerClient

        parts = callback.data.split("_")
        date_str = parts[2]  # YYYY-MM-DD
        client_id = int(parts[3])

        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        trainer = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)

        # Проверяем доступ
        result = await db.session.execute(
            select(TrainerClient).where(
                TrainerClient.trainer_id == trainer.id,
                TrainerClient.client_id == client_id,
                TrainerClient.status == 'active'
            )
        )
        if not result.scalar_one_or_none():
            await callback.answer("⛔ Нет доступа")
            return

        client = await UserCRUD.get_by_id(db.session, client_id)
        entries = await FoodDiaryCRUD.get_day_entries(db.session, client_id, selected_date)

        if not entries:
            await callback.message.edit_text(
                f"📭 *Дневник {client.full_name or client.username} за {selected_date.strftime('%d.%m.%Y')}*\n\n"
                f"Пока нет записей.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад к списку дней", callback_data=f"diary_week_{client_id}")]
                ])
            )
            await callback.answer()
            return

        # Отправляем заголовок
        await callback.message.edit_text(
            f"📔 *Дневник {client.full_name or client.username} за {selected_date.strftime('%d.%m.%Y')}*\n\n"
            f"Загружаю записи...",
            parse_mode="HTML"
        )

        # Отправляем каждую запись отдельно с фото
        for i, entry in enumerate(entries, 1):
            meal_emoji = {
                "breakfast": "🌅",
                "lunch": "☀️",
                "dinner": "🌙",
                "snack": "🍎"
            }.get(entry.meal_type, "🍽")

            meal_ru = {
                "breakfast": "Завтрак",
                "lunch": "Обед",
                "dinner": "Ужин",
                "snack": "Перекус"
            }.get(entry.meal_type, "")

            time_str = entry.meal_date.strftime("%H:%M")

            caption = (
                f"{meal_emoji} *{meal_ru}* ({time_str}) — запись {i}/{len(entries)}\n\n"
                f"📝 {entry.description[:200]}\n\n"
                f"🔥 *{entry.calories}* ккал\n"
                f"🥩 Белки: *{entry.protein:.0f}* г\n"
                f"🧈 Жиры: *{entry.fat:.0f}* г\n"
                f"🍚 Углеводы: *{entry.carbs:.0f}* г"
            )

            if entry.photo_file_id:
                try:
                    await callback.message.answer_photo(
                        photo=entry.photo_file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
                    await callback.message.answer(caption, parse_mode="HTML")
            else:
                await callback.message.answer(caption, parse_mode="HTML")

            await asyncio.sleep(0.3)

        # Кнопка возврата к списку дней
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к списку дней", callback_data=f"diary_week_{client_id}")]
        ])
        await callback.message.answer(
            "✅ *Конец записей*",
            parse_mode="HTML",
            reply_markup=keyboard
        )

        await callback.answer()