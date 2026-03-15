# app/handlers/photo_handler.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.utils.openai_photo_analyzer import analyze_food_photo
from app.utils.states import NutritionStates
from app.database.crud import UserCRUD

logger = logging.getLogger(__name__)
photo_router = Router()


# ========== ПРИОРИТЕТНЫЙ ОБРАБОТЧИК ТЕКСТОВЫХ ОПИСАНИЙ ==========

@photo_router.message(F.text)
async def handle_food_text_priority(message: Message, state: FSMContext):
    """Приоритетный обработчик текстовых описаний еды"""

    # Получаем текущее состояние
    current_state = await state.get_state()

    # Если пользователь в онбординге - пропускаем
    if current_state and current_state.startswith("OnboardingStates"):
        logger.info(f"⏭️ Пропускаем текст в photo_handler, идет онбординг: {current_state}")
        return

    text = message.text.lower().strip()

    # Игнорируем команды
    if text.startswith('/'):
        return

    # Игнорируем слишком короткие сообщения
    if len(text) < 3:
        return

    # Ключевые слова для определения описания еды (расширенный список)
    food_keywords = [
        # Глаголы приема пищи
        "съел", "съела", "съели", "съесть", "ел", "ела", "ели", "ем", "едим",
        "поел", "поела", "поели", "поесть", "кушал", "кушала", "кушали",
        "перекусил", "перекусила", "перекусили", "перекусить", "отведал",
        "завтракал", "завтракала", "завтракали", "завтракать",
        "обедал", "обедала", "обедали", "пообедать",
        "ужинал", "ужинала", "ужинали", "поужинать",
        "выпил", "выпила", "выпили", "выпить", "пью", "пьем", "пьёт",

        # Существительные (блюда)
        "бургер", "пицца", "салат", "суп", "борщ", "каша", "омлет", "яичница",
        "стейк", "котлета", "сосиска", "колбаса", "бутерброд", "сэндвич",
        "макароны", "спагетти", "гречка", "рис", "плов", "картошка", "картофель",
        "пюре", "овощи", "фрукты", "мясо", "курица", "рыба", "котлета",

        # Напитки
        "кофе", "чай", "сок", "вода", "молоко", "кефир", "йогурт", "смузи",
        "компот", "лимонад", "кола", "пепси", "фанта",

        # Десерты
        "шоколад", "конфета", "печенье", "торт", "пирожное", "пирог", "мороженое",
        "вафля", "пончик", "кекс", "маффин", "десерт",

        # Фрукты и овощи
        "яблоко", "банан", "апельсин", "мандарин", "груша", "виноград",
        "помидор", "огурец", "морковь", "капуста", "свекла",

        # Слова-маркеры
        "блюдо", "еда", "порция", "тарелка", "миска", "стакан", "чашка",
        "грамм", "килограмм", "калорий", "ккал"
    ]

    # Проверяем, похоже ли на описание еды
    is_food_description = any(keyword in text for keyword in food_keywords)

    # Дополнительная проверка: если сообщение короткое - может быть просто название еды
    words = text.split()
    if len(words) <= 2 and not is_food_description:
        single_word_foods = [
            "пицца", "бургер", "салат", "суп", "борщ", "каша", "стейк",
            "омлет", "яичница", "кофе", "чай", "сок", "йогурт", "кефир",
            "яблоко", "банан", "апельсин", "шоколад", "мороженое"
        ]
        if text in single_word_foods or any(word in single_word_foods for word in words):
            is_food_description = True
            logger.info(f"🔍 Распознано название еды: {text}")

    if is_food_description:
        logger.info(f"🍽 ПРИОРИТЕТНЫЙ ОБРАБОТЧИК: текст от {message.from_user.id}: '{message.text}'")
        
        # ОТПРАВЛЯЕМ АНАЛИЗ НАПРЯМУЮ
        from app.utils.openai_photo_analyzer import estimate_calories_from_text
        
        wait_msg = await message.answer("🔍 **Анализирую описание...**")
        
        try:
            analysis = await estimate_calories_from_text(message.text)
            await wait_msg.delete()
            
            if "error" in analysis:
                await message.answer(
                    "❌ **Не удалось оценить калории**\n\n"
                    "Попробуй сформулировать иначе, например:\n"
                    "• *\"Съел тарелку борща со сметаной\"*\n"
                    "• *\"Выпил стакан молока 3.2%\"*\n"
                    "• *\"Перекусил яблоком и бананом\"*",
                    parse_mode="HTML"
                )
                return
            
            response = f"""📝 **Анализ питания**

🍽️ **Что съедено:** {message.text}

⚖️ **Примерная пищевая ценность:**
• 🔥 Калории: **{analysis.get('estimated_calories', '?')}** ккал
• 🥩 Белки: **{analysis.get('protein_grams', '?')}** г
• 🧈 Жиры: **{analysis.get('fat_grams', '?')}** г
• 🍚 Углеводы: **{analysis.get('carbs_grams', '?')}** г

📏 **Размер порции:** ~{analysis.get('serving_size_grams', '?')} г

💡 *Оценка основана на типичных значениях. Для точного анализа отправьте фото.*"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📸 Анализ по фото", callback_data="start_photo_analysis")
                ]
            ])
            
            await message.answer(response, reply_markup=keyboard, parse_mode="HTML")
            logger.info(f"✅ Текстовый анализ для пользователя {message.from_user.id} - ответ отправлен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа текста: {e}")
            await wait_msg.delete()
            await message.answer(
                "❌ Не удалось проанализировать описание.\n"
                "Попробуй сформулировать иначе или отправь фото."
            )
        
        return  # Важно! Не передаем управление дальше

    # Если не похоже на еду - пропускаем, пусть другие обработчики работают
    return


# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

@photo_router.message(Command("analyze"))
async def cmd_analyze(message: Message, state: FSMContext):
    """Команда для анализа фото - понятная инструкция"""

    # Сбрасываем состояние, если оно мешает
    current_state = await state.get_state()
    if current_state:
        logger.info(f"🔄 Сброс состояния {current_state} для команды /analyze")
        await state.clear()

    # Отправляем понятную инструкцию
    await message.answer(
        "📸 **Анализ питания**\n\n"
        "📝 **Как это работает:**\n"
        "1️⃣ Сфотографируй свою еду\n"
        "2️⃣ Отправь фото в этот чат\n"
        "3️⃣ Я определю блюдо и посчитаю калории\n\n"
        "🍽 **Примеры блюд:**\n"
        "• Завтрак: омлет с овощами\n"
        "• Обед: борщ со сметаной\n"
        "• Ужин: стейк с картофелем\n"
        "• Перекус: смузи или йогурт\n\n"
        "✨ **Что я умею:**\n"
        "✅ Распознавать продукты\n"
        "✅ Считать КБЖУ (калории, белки, жиры, углеводы)\n"
        "✅ Оценивать размер порции\n"
        "✅ Давать рекомендации\n\n"
        "📤 **Просто отправь фото прямо сейчас!**\n"
        "Или опиши еду текстом, например:\n"
        "👉 *\"Съел тарелку борща\"*\n"
        "👉 *\"Выпил стакан молока\"*\n"
        "👉 *\"Перекусил яблоком\"*",
        parse_mode="HTML"
    )

    # Устанавливаем состояние ожидания фото
    await state.set_state(NutritionStates.waiting_photo)
    logger.info(f"👤 Пользователь {message.from_user.id} начал анализ фото")


@photo_router.message(NutritionStates.waiting_photo, F.text)
async def handle_text_in_waiting_photo(message: Message, state: FSMContext):
    """Обработка текста, когда ждем фото"""

    text = message.text.lower()

    # Проверяем, может это описание еды?
    food_keywords = ["ел", "съел", "ем", "кушал", "завтрак", "обед", "ужин",
                     "перекус", "пицца", "бургер", "салат", "суп", "стейк"]

    if any(keyword in text for keyword in food_keywords):
        # Если похоже на еду - перенаправляем в текстовый анализ
        logger.info(f"🔄 Перенаправляем текст на анализ еды: {message.text}")
        await state.clear()
        # Вызываем анализ текста через приоритетный обработчик
        await handle_food_text_priority(message, state)
    else:
        # Если не похоже на еду - напоминаем про фото
        await message.answer(
            "📸 **Я жду фото еды!**\n\n"
            "Пожалуйста, отправь фотографию своего блюда, чтобы я мог его проанализировать.\n\n"
            "Или опиши еду текстом, например:\n"
            "• *\"Съел пиццу\"*\n"
            "• *\"Выпил кофе с молоком\"*\n"
            "• *\"Перекусил яблоком\"*\n\n"
            "Если хочешь выйти из режима анализа - напиши /cancel",
            parse_mode="HTML"
        )


@photo_router.message(F.photo)
async def handle_food_photo(message: Message, state: FSMContext):
    """Обработка фото еды от пользователя"""

    # Проверяем состояние - если онбординг, пропускаем
    current_state = await state.get_state()
    if current_state and current_state.startswith("OnboardingStates"):
        logger.info(f"⏭️ Пропускаем фото в photo_handler, идет онбординг: {current_state}")
        return

    # Если не в режиме ожидания фото, но прислали фото - все равно обрабатываем
    if current_state != NutritionStates.waiting_photo:
        logger.info(f"📸 Получено фото вне режима ожидания, но обрабатываем")

    # Проверяем caption на служебные слова
    if message.caption and any(word in message.caption.lower() for word in ["/start", "/help", "/cancel"]):
        return

    # Показываем что начали анализ
    wait_msg = await message.answer("🔍 **Анализирую фото...**\nЭто займет 10-20 секунд.", parse_mode="HTML")

    try:
        # Получаем фото в лучшем качестве
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        photo_bytes_io = await message.bot.download_file(file.file_path)
        photo_bytes = photo_bytes_io.getvalue()

        logger.info(f"📸 Анализ фото от {message.from_user.id}, размер: {len(photo_bytes)} bytes")

        # Анализируем через OpenAI
        analysis = await analyze_food_photo(photo_bytes)

        await wait_msg.delete()

        if not analysis:
            await message.answer(
                "❌ **Не удалось проанализировать фото**\n\n"
                "Возможные причины:\n"
                "• 📸 Слишком темное или размытое фото\n"
                "• 🍽️ На фото не еда\n"
                "• 📏 Еда слишком мелко или далеко\n\n"
                "📝 **Что делать:**\n"
                "1. Сделай фото крупным планом\n"
                "2. Обеспечь хорошее освещение\n"
                "3. Убедись, что еда в фокусе\n"
                "4. Или опиши еду текстом",
                parse_mode="HTML"
            )
            return

        # Извлекаем данные
        description = analysis.get("description", "🍽️ Еда на фото")
        dishes = analysis.get("dishes", [])
        nutrition = analysis.get("nutrition", {})
        confidence = analysis.get("confidence", "medium")

        # Формируем красивый ответ
        response_parts = []

        # Заголовок с эмодзи
        confidence_emoji = "🟢" if confidence == "high" else "🟡" if confidence == "medium" else "🟠"
        response_parts.append(f"{confidence_emoji} **Анализ фото:**\n")
        response_parts.append(f"**{description}**\n")

        # Детальный состав
        if dishes:
            response_parts.append("📋 **Состав блюда:**")
            for i, dish in enumerate(dishes[:3], 1):
                name = dish.get("name", f"Блюдо {i}")
                weight = dish.get("estimated_weight_grams", "?")
                ingredients = dish.get("ingredients", [])

                if ingredients:
                    ingredients_str = ", ".join(ingredients[:3])
                    if len(ingredients) > 3:
                        ingredients_str += "..."
                    response_parts.append(f"  {i}. {name} (~{weight}г): {ingredients_str}")
                else:
                    response_parts.append(f"  {i}. {name} (~{weight}г)")

        # Пищевая ценность
        response_parts.append("\n⚖️ **Пищевая ценность:**")
        response_parts.append(f"  🔥 Калории: **{nutrition.get('total_calories', '?')}** ккал")
        response_parts.append(f"  🥩 Белки: **{nutrition.get('protein_grams', '?')}** г")
        response_parts.append(f"  🧈 Жиры: **{nutrition.get('fat_grams', '?')}** г")
        response_parts.append(f"  🍚 Углеводы: **{nutrition.get('carbs_grams', '?')}** г")

        # Точность анализа
        confidence_text = {
            "high": "высокая",
            "medium": "средняя",
            "low": "примерная"
        }.get(confidence, confidence)
        response_parts.append(f"\n📊 **Точность анализа:** {confidence_text}")

        # Рекомендации
        if nutrition.get('total_calories'):
            cal = nutrition['total_calories']
            if cal > 800:
                response_parts.append(
                    "\n💡 **Рекомендация:** Это сытное блюдо. Возможно, стоит разделить на два приема.")
            elif cal < 200:
                response_parts.append(
                    "\n💡 **Рекомендация:** Легкий перекус. Если это основной прием пищи, добавьте белка и овощей.")

        # Собираем ответ
        response = "\n".join(response_parts)

        # КНОПКИ
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Новый анализ", callback_data="new_analysis"),
            ]
        ])

        # Увеличиваем счетчик
        try:
            db = message.bot.get('db')
            if db:
                await UserCRUD.increment_photo_count(db.session, message.from_user.id)
        except Exception as e:
            logger.error(f"Ошибка при обновлении счетчика: {e}")

        await message.answer(response, reply_markup=keyboard, parse_mode="HTML")

        # Сбрасываем состояние после успешного анализа
        await state.clear()
        logger.info(f"✅ Анализ завершен для пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки фото: {e}", exc_info=True)

        try:
            await wait_msg.delete()
        except:
            pass

        await message.answer(
            "⚠️ **Произошла ошибка при анализе**\n\n"
            "Попробуйте:\n"
            "1️⃣ Отправить фото еще раз\n"
            "2️⃣ Описать еду текстом\n"
            "3️⃣ Начать заново: /start\n\n"
            "Если ошибка повторяется, напишите /support",
            parse_mode="HTML"
        )


# ========== Этот обработчик больше не используется напрямую, 
# ========== но оставляем для обратной совместимости
@photo_router.message(F.text & ~F.command)
async def handle_food_text_legacy(message: Message, state: FSMContext):
    """Анализ еды по текстовому описанию (legacy)"""
    # Перенаправляем в приоритетный обработчик
    await handle_food_text_priority(message, state)


@photo_router.callback_query(F.data == "new_analysis")
async def new_analysis_callback(callback: CallbackQuery, state: FSMContext):
    """Начать новый анализ"""
    await state.clear()
    await callback.message.delete()
    await cmd_analyze(callback.message, state)
    await callback.answer()


@photo_router.callback_query(F.data == "start_photo_analysis")
async def start_photo_analysis_callback(callback: CallbackQuery, state: FSMContext):
    """Переключиться на анализ по фото"""
    await state.set_state(NutritionStates.waiting_photo)
    await callback.message.answer(
        "📸 **Отправьте фото еды**\n\n"
        "Сделайте четкое фото вашего блюда и отправьте его в этот чат.",
        parse_mode="HTML"
    )
    await callback.answer()
