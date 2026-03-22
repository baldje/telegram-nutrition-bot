# app/handlers/food_diary.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging
from datetime import datetime, date, timedelta

from app.utils.navigation import Navigation
from app.database.crud import UserCRUD, FoodDiaryCRUD, NutritionCalculator
from app.utils.states import NutritionStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📔 Дневник питания")
async def food_diary_menu(message: Message, state: FSMContext):
    """Главное меню дневника питания"""
    await state.clear()
    await message.answer(
        "📔 *Дневник питания*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )


# ===== ВЫБОР ТИПА ПРИЕМА ПИЩИ =====

@router.message(F.text.in_(["🌅 Завтрак", "☀️ Обед", "🌙 Ужин", "🍎 Перекус"]))
async def choose_meal_type(message: Message, state: FSMContext):
    """Выбор типа приема пищи"""
    meal_map = {
        "🌅 Завтрак": ("breakfast", "🌅 Завтрак"),
        "☀️ Обед": ("lunch", "☀️ Обед"),
        "🌙 Ужин": ("dinner", "🌙 Ужин"),
        "🍎 Перекус": ("snack", "🍎 Перекус")
    }

    meal_type, meal_display = meal_map[message.text]
    await state.update_data(
        meal_type=meal_type,
        meal_display=meal_display
    )

    # Спрашиваем способ добавления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Описать текстом", callback_data="add_text")],
        [InlineKeyboardButton(text="📸 Отправить фото", callback_data="add_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])

    await message.answer(
        f"🍽 *{meal_display}*\n\n"
        f"Как хотите добавить запись?",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "add_text")
async def add_text_handler(callback: CallbackQuery, state: FSMContext):
    """Добавление текстом"""
    await callback.message.delete()
    data = await state.get_data()
    meal_display = data.get('meal_display', '🍎 Перекус')

    await callback.message.answer(
        f"📝 *Опишите, что вы съели на {meal_display.lower()}*",
        parse_mode="HTML",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(NutritionStates.waiting_text)
    await callback.answer()


@router.callback_query(F.data == "add_photo")
async def add_photo_handler(callback: CallbackQuery, state: FSMContext):
    """Добавление фото"""
    await callback.message.delete()
    data = await state.get_data()
    meal_display = data.get('meal_display', '🍎 Перекус')

    await callback.message.answer(
        f"📸 *Отправьте фото еды для {meal_display.lower()}*",
        parse_mode="HTML",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(NutritionStates.waiting_photo)
    await callback.answer()


@router.callback_query(F.data == "cancel_add")
async def cancel_add_handler(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "📔 *Дневник питания*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )
    await callback.answer()


# ===== СТАТИСТИКА =====

@router.message(F.text == "📊 Сегодня")
async def show_today_history(message: Message, db=None):
    """Показать историю за сегодня"""
    if not db:
        return

    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        return

    entries = await FoodDiaryCRUD.get_day_entries(db.session, user.id, date.today())

    if not entries:
        await message.answer(
            "📭 *Сегодня пока нет записей*\n\n"
            "Добавьте запись через меню Питание!",
            parse_mode="HTML",
            reply_markup=Navigation.get_food_diary_menu()
        )
        return

    text = "📊 *История питания за сегодня*\n\n"
    total_cal = 0

    for entry in entries:
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
        text += f"{meal_emoji} *{meal_ru}* ({time_str}):\n"
        text += f"  📝 {entry.description[:100]}\n"

        # Обрабатываем None значения
        calories_val = entry.calories or 0
        protein_val = entry.protein or 0
        fat_val = entry.fat or 0
        carbs_val = entry.carbs or 0
        text += f"  🔥 {calories_val} ккал | 🥩 {protein_val:.0f}г | 🧈 {fat_val:.0f}г | 🍚 {carbs_val:.0f}г\n\n"

        total_cal += calories_val

    text += f"*Всего за день: {total_cal} ккал*"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )


@router.message(F.text == "📅 Неделя")
async def show_week_history(message: Message, db=None):
    """Показать историю за неделю"""
    if not db:
        return

    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        return

    entries = await FoodDiaryCRUD.get_week_entries(db.session, user.id)

    # Получаем норму пользователя
    has_norm = all([user.weight, user.height, user.age, user.goal])
    if has_norm:
        daily = NutritionCalculator.get_daily_nutrition(user)

    # Группируем по дням
    days = {}
    for entry in entries:
        day = entry.meal_date.date()
        if day not in days:
            days[day] = {'calories': 0, 'meals': 0}
        days[day]['calories'] += entry.calories or 0
        days[day]['meals'] += 1

    if not days:
        text = "📭 *Нет записей за последнюю неделю*\n\n"
        if has_norm:
            text += f"🎯 *Ваша дневная норма:* {daily['calories']} ккал"

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_food_diary_menu()
        )
        return

    text = "📊 *Статистика за неделю*\n\n"
    total_week_cal = 0
    days_over_norm = 0

    for day, stats in sorted(days.items(), reverse=True):
        day_str = day.strftime('%d.%m')
        day_cal = stats['calories']
        total_week_cal += day_cal

        if has_norm:
            if day_cal > daily['calories']:
                days_over_norm += 1
                over = day_cal - daily['calories']
                text += f"📅 {day_str}: {day_cal} ккал ⚠️ *+{over}*\n"
            elif day_cal < daily['calories'] * 0.8:
                under = daily['calories'] - day_cal
                text += f"📅 {day_str}: {day_cal} ккал ⬇️ *-{under}*\n"
            else:
                text += f"📅 {day_str}: {day_cal} ккал ✅\n"
        else:
            text += f"📅 {day_str}: {day_cal} ккал ({stats['meals']} приемов)\n"

    avg_cal = total_week_cal // len(days) if days else 0
    text += f"\n*Среднее за день: {avg_cal} ккал*"

    if has_norm:
        text += f"\n\n📊 *Анализ недели:*\n"
        if days_over_norm == 0:
            text += f"✅ Отлично! Вы не превышали норму ни разу\n"
        elif days_over_norm <= 2:
            text += f"⚠️ Вы превышали норму {days_over_norm} раз(а). Старайтесь не переедать\n"
        else:
            text += f"❌ Вы превышали норму {days_over_norm} раз(а). Рекомендуем следить за питанием\n"

        if avg_cal > daily['calories']:
            text += f"📈 Средняя калорийность выше нормы на {avg_cal - daily['calories']} ккал\n"
        elif avg_cal < daily['calories']:
            text += f"📉 Средняя калорийность ниже нормы на {daily['calories'] - avg_cal} ккал\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )


@router.message(F.text == "📊 Моя норма")
async def show_my_nutrition_norm(message: Message, db=None):
    """Показать суточную норму КБЖУ"""
    if not db:
        return

    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return

    # Проверяем, прошел ли пользователь онбординг
    if not all([user.weight, user.height, user.age, user.goal]):
        await message.answer(
            "⚠️ *Для расчета нормы нужно заполнить анкету*\n\n"
            "Пройдите онбординг: /start",
            parse_mode="HTML",
            reply_markup=Navigation.get_main_menu()
        )
        return

    # Рассчитываем нормы
    daily = NutritionCalculator.get_daily_nutrition(user)

    # Получаем сегодняшние записи для сравнения
    entries = await FoodDiaryCRUD.get_day_entries(db.session, user.id, date.today())
    consumed = {
        'calories': sum(e.calories or 0 for e in entries),
        'protein': sum(e.protein or 0 for e in entries),
        'fat': sum(e.fat or 0 for e in entries),
        'carbs': sum(e.carbs or 0 for e in entries)
    }

    remaining = NutritionCalculator.get_remaining_for_day(user, consumed)

    text = (
        f"📊 *Ваша суточная норма*\n\n"
        f"🎯 Цель: *{user.goal}*\n"
        f"⚖️ Вес: {user.weight} кг\n\n"
        f"*Всего на день:*\n"
        f"• 🔥 Калории: {daily['calories']} ккал\n"
        f"• 🥩 Белки: {daily['protein']} г\n"
        f"• 🧈 Жиры: {daily['fat']} г\n"
        f"• 🍚 Углеводы: {daily['carbs']} г\n\n"
        f"📌 Базальный метаболизм: {daily['bmr']} ккал\n"
        f"📈 С учетом активности: {daily['tdee']} ккал\n\n"
    )

    # Добавляем информацию о сегодняшнем прогрессе
    if entries:
        text += f"📊 *Прогресс за сегодня:*\n"
        text += f"🔥 Съедено: {consumed['calories']} / {daily['calories']} ккал\n"

        if consumed['calories'] > daily['calories']:
            over = consumed['calories'] - daily['calories']
            text += f"⚠️ *Превышение на {over} ккал!*\n\n"
        elif remaining['calories'] < 200:
            text += f"🔔 *Осталось мало калорий ({remaining['calories']} ккал)*\n\n"
        else:
            text += f"✅ Осталось {remaining['calories']} ккал\n\n"
    else:
        text += f"📭 Сегодня пока нет записей\n"
        text += f"✨ Ваша норма на сегодня: {daily['calories']} ккал\n\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )


@router.message(F.text == "📊 Прогресс дня")
async def show_daily_progress(message: Message, db=None):
    """Показать прогресс по КБЖУ за сегодня"""
    if not db:
        return

    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        return

    # Проверяем данные для расчета
    if not all([user.weight, user.height, user.age, user.goal]):
        await message.answer(
            "⚠️ *Для расчета прогресса нужно заполнить анкету*\n\n"
            "Пройдите онбординг: /start",
            parse_mode="HTML",
            reply_markup=Navigation.get_main_menu()
        )
        return

    # Получаем съеденное за сегодня
    entries = await FoodDiaryCRUD.get_day_entries(db.session, user.id, date.today())

    # Суммируем съеденное
    consumed = {
        'calories': sum(e.calories or 0 for e in entries),
        'protein': sum(e.protein or 0 for e in entries),
        'fat': sum(e.fat or 0 for e in entries),
        'carbs': sum(e.carbs or 0 for e in entries)
    }

    # Рассчитываем остаток и прогресс
    remaining = NutritionCalculator.get_remaining_for_day(user, consumed)

    # Создаем прогресс-бары
    def progress_bar(percent, length=10):
        filled = min(percent // 10, 10)
        return "🟩" * filled + "⬜" * (length - filled)

    # Определяем статус
    if consumed['calories'] > remaining['total_calories']:
        status = "⚠️ *ПРЕВЫШЕНИЕ НОРМЫ!*"
        status_emoji = "❌"
    elif remaining['calories'] < 200:
        status = "🔔 *Почти достигли нормы*"
        status_emoji = "⚡"
    elif remaining['calories'] > remaining['total_calories'] * 0.5:
        status = "✅ *Хороший прогресс*"
        status_emoji = "👍"
    else:
        status = "💪 *Еще есть время*"
        status_emoji = "💪"

    text = (
        f"📊 *Прогресс дня*\n\n"
        f"{status}\n\n"
        f"🔥 *Калории:* {consumed['calories']}/{remaining['total_calories']} ккал\n"
        f"{progress_bar(remaining['progress']['calories'])} {remaining['progress']['calories']}%\n\n"
        f"🥩 *Белки:* {consumed['protein']:.1f}/{remaining['total_protein']} г\n"
        f"{progress_bar(remaining['progress']['protein'])} {remaining['progress']['protein']}%\n\n"
        f"🧈 *Жиры:* {consumed['fat']:.1f}/{remaining['total_fat']} г\n"
        f"{progress_bar(remaining['progress']['fat'])} {remaining['progress']['fat']}%\n\n"
        f"🍚 *Углеводы:* {consumed['carbs']:.1f}/{remaining['total_carbs']} г\n"
        f"{progress_bar(remaining['progress']['carbs'])} {remaining['progress']['carbs']}%\n\n"
    )

    # Добавляем рекомендации
    if consumed['calories'] > remaining['total_calories']:
        over = consumed['calories'] - remaining['total_calories']
        text += f"⚠️ *Вы превысили норму на {over} ккал!*\n"
        text += f"💡 Завтра постарайтесь быть внимательнее\n\n"
    elif remaining['calories'] < 200:
        text += f"🔔 *Осталось совсем мало калорий*\n"
        text += f"💡 Если голодны, выберите легкий перекус (овощи, кефир)\n\n"
    elif remaining['calories'] > remaining['total_calories'] * 0.5:
        text += f"💡 *У вас еще {remaining['calories']} ккал в запасе*\n"
        text += f"🍽 Можно добавить полноценный прием пищи\n\n"
    else:
        text += f"💡 *Нужно добрать:*\n"
        if remaining['protein'] > 30:
            text += f"• 🥩 {remaining['protein']:.0f}г белка (курица, рыба, яйца)\n"
        if remaining['carbs'] > 50:
            text += f"• 🍚 {remaining['carbs']:.0f}г углеводов (гречка, рис, овсянка)\n"
        if remaining['fat'] > 20:
            text += f"• 🧈 {remaining['fat']:.0f}г жиров (орехи, авокадо, масло)\n"
        text += f"\n"

    text += f"📝 Записей за сегодня: {len(entries)}"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )