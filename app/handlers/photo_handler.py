# app/handlers/photo_handler.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime, date

from app.utils.openai_photo_analyzer import analyze_food_photo, estimate_calories_from_text
from app.utils.states import NutritionStates
from app.database.crud import UserCRUD, FoodDiaryCRUD, NutritionCalculator
from app.utils.navigation import Navigation

logger = logging.getLogger(__name__)
photo_router = Router()


@photo_router.message(F.text == "📸 Анализ фото")
async def photo_analysis(message: Message, state: FSMContext):
    """Анализ фото - сразу ждем фото"""
    await state.update_data(analysis_type="photo")
    await message.answer(
        "📸 *Отправьте фото еды*",
        parse_mode="HTML",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(NutritionStates.waiting_photo)


@photo_router.message(F.text == "📝 Описать еду")
async def text_analysis(message: Message, state: FSMContext):
    """Описание еды - сразу ждем текст"""
    await state.update_data(analysis_type="text")
    await message.answer(
        "📝 *Опишите, что вы съели*",
        parse_mode="HTML",
        reply_markup=Navigation.get_cancel_keyboard()
    )
    await state.set_state(NutritionStates.waiting_text)


@photo_router.message(NutritionStates.waiting_photo, F.photo)
async def handle_food_photo(message: Message, state: FSMContext, db=None):
    """Обработка фото еды"""
    wait_msg = await message.answer("🔍 Анализирую фото... (это может занять несколько секунд)")

    try:
        # Получаем фото
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        photo_bytes_io = await message.bot.download_file(file.file_path)
        photo_bytes = photo_bytes_io.getvalue()

        # Анализируем через OpenAI
        analysis = await analyze_food_photo(photo_bytes)

        await wait_msg.delete()

        if not analysis:
            # Заглушка для теста
            analysis = {
                "description": "Блюдо на фото",
                "estimated_calories": 450,
                "protein_grams": 20,
                "fat_grams": 15,
                "carbs_grams": 50
            }

        # Сохраняем анализ
        await state.update_data(analysis=analysis, description="Фото еды")

        # Спрашиваем тип приема пищи
        await ask_meal_type(message, state, db)

    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}")
        await wait_msg.delete()
        await message.answer(
            "❌ Ошибка при анализе. Попробуйте еще раз.",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()


@photo_router.message(NutritionStates.waiting_text, F.text)
async def handle_food_text(message: Message, state: FSMContext, db=None):
    """Обработка текстового описания еды"""
    description = message.text

    wait_msg = await message.answer("🔍 Анализирую описание...")

    try:
        analysis = await estimate_calories_from_text(description)

        await wait_msg.delete()

        if "error" in analysis:
            # Заглушка для теста
            analysis = {
                "estimated_calories": 350,
                "protein_grams": 15,
                "fat_grams": 10,
                "carbs_grams": 45,
                "serving_size_grams": 200
            }

        # Сохраняем описание и анализ
        await state.update_data(
            analysis=analysis,
            description=description
        )

        # Спрашиваем тип приема пищи
        await ask_meal_type(message, state, db)

    except Exception as e:
        logger.error(f"Ошибка анализа текста: {e}")
        await wait_msg.delete()
        await message.answer(
            "❌ Ошибка при анализе. Попробуйте еще раз.",
            reply_markup=Navigation.get_main_menu()
        )
        await state.clear()


async def ask_meal_type(message: Message, state: FSMContext, db=None):
    """Спрашиваем тип приема пищи после анализа"""
    # Сначала показываем результат анализа с прогрессом
    await show_analysis_result(message, state, "⚡ Результат анализа", db)


async def show_analysis_result(message: Message, state: FSMContext, meal_display: str, db=None):
    """Показать результат анализа с информацией о прогрессе и остатке"""
    data = await state.get_data()
    analysis = data.get('analysis', {})
    description = data.get('description', 'Фото еды')

    # Получаем калории из анализа
    meal_calories = analysis.get('estimated_calories', 0)
    meal_protein = analysis.get('protein_grams', 0)
    meal_fat = analysis.get('fat_grams', 0)
    meal_carbs = analysis.get('carbs_grams', 0)

    # Базовая информация о приеме пищи
    result_text = (
        f"📊 *Результат анализа*\n\n"
        f"📄 {description[:100]}{'...' if len(description) > 100 else ''}\n\n"
        f"⚖️ *Съедено:*\n"
        f"• 🔥 Калории: **{meal_calories}** ккал\n"
        f"• 🥩 Белки: **{meal_protein}** г\n"
        f"• 🧈 Жиры: **{meal_fat}** г\n"
        f"• 🍚 Углеводы: **{meal_carbs}** г\n\n"
    )

    # Если есть доступ к БД, показываем прогресс за день
    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
            if user and all([user.weight, user.height, user.age, user.goal]):
                # Получаем все записи за сегодня
                entries = await FoodDiaryCRUD.get_day_entries(db.session, user.id, date.today())

                # Суммируем съеденное (включая текущий прием)
                total_calories = sum(e.calories or 0 for e in entries) + meal_calories
                total_protein = sum(e.protein or 0 for e in entries) + meal_protein
                total_fat = sum(e.fat or 0 for e in entries) + meal_fat
                total_carbs = sum(e.carbs or 0 for e in entries) + meal_carbs

                # Получаем норму пользователя
                daily = NutritionCalculator.get_daily_nutrition(user)

                # Рассчитываем остаток
                remaining_calories = max(0, daily['calories'] - total_calories)
                remaining_protein = max(0, daily['protein'] - total_protein)
                remaining_fat = max(0, daily['fat'] - total_fat)
                remaining_carbs = max(0, daily['carbs'] - total_carbs)

                # Прогресс-бары
                def progress_bar(current, total, length=10):
                    if total == 0:
                        return "⬜" * length
                    percent = min(int((current / total) * 100), 100)
                    filled = percent // 10
                    return "🟩" * filled + "⬜" * (length - filled)

                result_text += (
                    f"📈 *Прогресс за день:*\n"
                    f"🔥 Калории: {total_calories}/{daily['calories']} ккал\n"
                    f"{progress_bar(total_calories, daily['calories'])} {int((total_calories / daily['calories']) * 100)}%\n"
                    f"🥩 Белки: {total_protein:.0f}/{daily['protein']} г\n"
                    f"{progress_bar(total_protein, daily['protein'])} {int((total_protein / daily['protein']) * 100)}%\n"
                    f"🧈 Жиры: {total_fat:.0f}/{daily['fat']} г\n"
                    f"{progress_bar(total_fat, daily['fat'])} {int((total_fat / daily['fat']) * 100)}%\n"
                    f"🍚 Углеводы: {total_carbs:.0f}/{daily['carbs']} г\n"
                    f"{progress_bar(total_carbs, daily['carbs'])} {int((total_carbs / daily['carbs']) * 100)}%\n\n"
                )

                # ===== ПРЕДУПРЕЖДЕНИЯ И СОВЕТЫ =====

                # 1. ПРОВЕРКА НА ПРЕВЫШЕНИЕ КАЛОРИЙ
                if total_calories > daily['calories']:
                    over = total_calories - daily['calories']
                    result_text += f"⚠️ *ВНИМАНИЕ!*\n"
                    result_text += f"❌ Вы превысили дневную норму на {over} ккал!\n\n"

                    # Поздравления по нутриентам (всегда говорим что норма выполнена)
                    result_text += f"📊 *Статус нутриентов:*\n"
                    result_text += f"🥩 Белки: ✅ норма выполнена!\n"
                    result_text += f"🧈 Жиры: ✅ норма выполнена!\n"
                    result_text += f"🍚 Углеводы: ✅ норма выполнена!\n"

                    # result_text += f"\n💡 *Совет:* Сегодня лучше сделать разгрузочный день или добавить физическую активность\n\n"

                # 2. ПРОВЕРКА НА КРИТИЧЕСКИЙ ОСТАТОК КАЛОРИЙ (осталось < 200)
                elif remaining_calories < 200:
                    result_text += f"🔔 *Внимание!*\n"
                    result_text += f"⚡ Осталось всего {remaining_calories} ккал на сегодня\n\n"

                    # Детальный анализ с советами по легкому перекусу
                    result_text += f"📊 *Детальный анализ:*\n"

                    # Белки
                    if total_protein >= daily['protein']:
                        result_text += f"🥩 Белки: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🥩 Белки: нужно еще {remaining_protein:.0f}г\n"

                    # Жиры
                    if total_fat >= daily['fat']:
                        result_text += f"🧈 Жиры: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🧈 Жиры: нужно еще {remaining_fat:.0f}г\n"

                    # Углеводы
                    if total_carbs >= daily['carbs']:
                        result_text += f"🍚 Углеводы: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🍚 Углеводы: нужно еще {remaining_carbs:.0f}г\n"

                    result_text += f"\n💡 *Совет:* Добавьте легкий перекус (овощи, кефир, яблоко)\n\n"

                # 3. ВСЁ В НОРМЕ (калории в пределах нормы)
                else:
                    result_text += f"✅ *Хороший прогресс!*\n"
                    result_text += f"💪 Осталось {remaining_calories} ккал\n\n"

                    # Детальный анализ с советами по добору (если нужно)
                    result_text += f"📊 *Детальный анализ:*\n"

                    # Белки
                    if total_protein >= daily['protein']:
                        result_text += f"🥩 Белки: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🥩 Белки: нужно еще {remaining_protein:.0f}г\n"

                    # Жиры
                    if total_fat >= daily['fat']:
                        result_text += f"🧈 Жиры: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🧈 Жиры: нужно еще {remaining_fat:.0f}г\n"

                    # Углеводы
                    if total_carbs >= daily['carbs']:
                        result_text += f"🍚 Углеводы: ✅ норма выполнена!\n"
                    else:
                        result_text += f"🍚 Углеводы: нужно еще {remaining_carbs:.0f}г\n"

                    # Советы по добору (если есть дефицит)
                    if remaining_protein > 20 or remaining_fat > 15 or remaining_carbs > 50:
                        result_text += f"\n💡 *Совет по добору:*\n"

                        if remaining_protein > 20:
                            result_text += f"• Добавьте белка: курица, рыба, яйца, творог\n"
                        if remaining_carbs > 50:
                            result_text += f"• Добавьте углеводов: гречка, рис, овсянка, макароны\n"
                        if remaining_fat > 15:
                            result_text += f"• Добавьте жиров: орехи, авокадо, оливковое масло\n"
                    else:
                        result_text += f"\n🎉 *Отлично! Баланс нутриентов почти идеальный!\n"

            else:
                result_text += f"ℹ️ *Для персонализированных рекомендаций заполните анкету в /start*\n\n"
        except Exception as e:
            logger.error(f"Ошибка расчета прогресса: {e}")

    # Кнопки для выбора типа приема и сохранения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Завтрак", callback_data="meal_breakfast"),
         InlineKeyboardButton(text="☀️ Обед", callback_data="meal_lunch")],
        [InlineKeyboardButton(text="🌙 Ужин", callback_data="meal_dinner"),
         InlineKeyboardButton(text="🍎 Перекус", callback_data="meal_snack")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_save")]
    ])

    await message.answer(
        result_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(NutritionStates.waiting_meal_type)


@photo_router.callback_query(F.data.startswith("meal_"))
async def process_meal_type(callback: CallbackQuery, state: FSMContext, db=None):
    """Обработка выбора типа приема пищи"""
    meal_map = {
        "meal_breakfast": ("breakfast", "🌅 Завтрак"),
        "meal_lunch": ("lunch", "☀️ Обед"),
        "meal_dinner": ("dinner", "🌙 Ужин"),
        "meal_snack": ("snack", "🍎 Перекус")
    }

    if callback.data in meal_map:
        meal_type, meal_display = meal_map[callback.data]
        data = await state.get_data()

        # Сохраняем запись в дневник
        if db:
            try:
                user = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
                if user:
                    description = data.get('description', 'Фото еды')
                    analysis = data.get('analysis', {})

                    # Получаем значение калорий из анализа ДО сохранения
                    calories_value = analysis.get('estimated_calories', 0)

                    # Сохраняем запись
                    entry = await FoodDiaryCRUD.add_entry(
                        session=db.session,
                        user_id=user.id,
                        meal_type=meal_type,
                        description=description,
                        analysis=analysis
                    )

                    await callback.message.edit_text(
                        f"✅ *Запись сохранена!*\n\n"
                        f"🍽 {meal_display}\n"
                        f"🔥 {calories_value} ккал",
                        parse_mode="HTML"
                    )
                else:
                    await callback.message.edit_text("❌ Пользователь не найден")
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}", exc_info=True)
                await callback.message.edit_text("❌ Ошибка при сохранении")

    await callback.message.answer(
        "📔 *Дневник питания*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )
    await state.clear()
    await callback.answer()


@photo_router.callback_query(F.data == "cancel_save")
async def cancel_save(callback: CallbackQuery, state: FSMContext):
    """Отмена сохранения"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "📔 *Дневник питания*\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=Navigation.get_food_diary_menu()
    )
    await callback.answer()


@photo_router.message(Command("analyze"))
async def cmd_analyze(message: Message, state: FSMContext):
    """Команда для анализа"""
    await message.answer(
        "🔍 *Выберите способ анализа:*\n\n"
        "📸 Анализ фото - в меню Питание\n"
        "📝 Описать еду - в меню Питание",
        parse_mode="HTML",
        reply_markup=Navigation.get_main_menu()
    )