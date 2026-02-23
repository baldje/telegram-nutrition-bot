# app/utils/openai_client.py - ИНТЕГРАЦИЯ С OPENAI
import logging
import os
from typing import Optional
import json

logger = logging.getLogger(__name__)

# Глобальный клиент - НЕ ИНИЦИАЛИЗИРУЕМ СРАЗУ!
_client = None
_MODEL = None


def _get_api_key() -> Optional[str]:
    """Безопасное получение API ключа"""
    try:
        # Пробуем получить из config
        from app.utils.config import config
        if hasattr(config, 'openai') and hasattr(config.openai, 'api_key'):
            return config.openai.api_key
    except:
        pass

    # Пробуем из переменных окружения
    return os.getenv("OPENAI_API_KEY")


def _get_model() -> str:
    """Безопасное получение модели"""
    try:
        from app.utils.config import config
        if hasattr(config, 'openai') and hasattr(config.openai, 'model'):
            return config.openai.model
    except:
        pass

    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_client():
    """Ленивое получение клиента"""
    global _client, _MODEL

    if _client is not None:
        return _client

    api_key = _get_api_key()
    if not api_key:
        logger.warning("⚠️ OPENAI_API_KEY не найден")
        return None

    try:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=api_key)
        _MODEL = _get_model()

        logger.info(f"✅ OpenAI клиент инициализирован (модель: {_MODEL})")

        # Проверка подключения
        logger.info("Проверяем доступность OpenAI...")
        return _client
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
        return None


async def ask_gpt(prompt: str, system_prompt: str = None) -> str:
    """Безопасная отправка запроса"""
    client = get_client()
    if not client:
        logger.error("❌ OpenAI клиент не инициализирован")
        return "⚠️ Сервис временно недоступен"

    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"📤 Отправляем запрос к GPT (модель: {_MODEL})")

        # Сначала пробуем универсальный подход без параметров ограничения
        params = {
            "model": _MODEL,
            "messages": messages,
        }

        # Добавляем temperature только если не gpt-5-nano
        if "gpt-5-nano" not in _MODEL.lower():
            params["temperature"] = 0.7

        logger.debug(f"Параметры запроса: {params}")

        try:
            # Пробуем без ограничений токенов
            response = await client.chat.completions.create(**params)
        except Exception as e:
            error_str = str(e)
            if "max_completion_tokens" in error_str:
                # Если требуется max_completion_tokens, добавляем его
                logger.info("🔄 Пробуем с max_completion_tokens=800...")
                params["max_completion_tokens"] = 800
                response = await client.chat.completions.create(**params)
            elif "max_tokens" in error_str:
                # Если требуется max_tokens, добавляем его
                logger.info("🔄 Пробуем с max_tokens=800...")
                params["max_tokens"] = 800
                response = await client.chat.completions.create(**params)
            else:
                raise e

        result = response.choices[0].message.content

        logger.info(f"📥 Получен ответ от GPT ({len(result)} символов)")

        if not result or len(result.strip()) == 0:
            logger.warning("⚠️ GPT вернул пустой ответ")
            return "⚠️ GPT вернул пустой ответ"

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка GPT: {e}")
        return f"⚠️ Ошибка: {str(e)[:100]}"


async def generate_meal_plan(calories: dict, favorite_foods: str = None,
                             excluded_foods: str = None, health_issues: str = None,
                             goal: str = None, gender: str = None,
                             age: int = None, height: int = None,
                             weight: float = None) -> str:
    """Генерация персонализированного плана питания через GPT"""

    # Проверяем наличие клиента
    client = get_client()
    if not client:
        logger.warning("⚠️ OpenAI не доступен, используем заглушку")
        return await _generate_fallback_plan(calories, favorite_foods, excluded_foods, health_issues, goal)

    # Создаем системный промпт с ограничением длины
    system_prompt = """Ты - профессиональный диетолог и нутрициолог с 10-летним опытом.
Твоя задача - создать персонализированный план питания на русском языке.

ВАЖНОЕ ТРЕБОВАНИЕ: Ограничь ответ 2500 символами!

ТРЕБОВАНИЯ К ОТВЕТУ:
1. Будь КРАТКИМ и по делу - максимум 2500 символов
2. План должен быть ПРАКТИЧНЫМ и реалистичным для приготовления дома
3. Учитывай калорийность каждого приема пищи
4. Предлагай 1-2 варианта для каждого приема пищи (не больше!)
5. Учитывай любимые и исключенные продукты пользователя
6. Добавь краткие советы по режиму питания
7. Форматируй ответ с использованием emoji для наглядности
8. НЕ используй markdown разметку, только обычный текст с emoji

ФОРМАТ ОТВЕТА (будь кратким!):
- Краткое резюме плана (2-3 предложения)
- План по приемам пищи: завтрак, обед, ужин, перекусы
- Краткие практические советы (3-4 пункта)

Если ответ будет длиннее 2500 символов, он будет обрезан."""

    # Создаем пользовательский промпт с требованием краткости
    user_prompt = f"""
Создай КРАТКИЙ и практичный план питания на день. Ограничь ответ 2500 символами!

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
- Цель: {goal or 'не указана'}
- Пол: {gender or 'не указан'}
- Возраст: {age or 'не указан'}
- Рост: {height or 'не указан'} см
- Вес: {weight or 'не указан'} кг
- Целевые калории: {calories.get('target', 'не рассчитано')} ккал/день

ПРЕДПОЧТЕНИЯ:
- Любимые продукты: {favorite_foods or 'не указаны'}
- Исключенные продукты: {excluded_foods or 'нет'}
- Проблемы со здоровьем: {health_issues or 'нет'}

СОЗДАЙ КОМПАКТНЫЙ ПЛАН ПИТАНИЯ НА ДЕНЬ С РАСПРЕДЕЛЕНИЕМ {calories.get('target', 2000)} ККАЛ.
Будь кратким, практичным и учитывай все предпочтения.
"""

    try:
        logger.info("🤖 Начинаем генерацию плана через GPT...")

        # Отправляем запрос
        meal_plan = await ask_gpt(user_prompt, system_prompt)

        if "⚠️" in meal_plan:
            logger.warning("GPT вернул ошибку, используем заглушку")
            return await _generate_fallback_plan(calories, favorite_foods, excluded_foods, health_issues, goal)

        # Проверяем длину и обрезаем если нужно
        MAX_PLAN_LENGTH = 2000  # Оставляем место для заголовка и других элементов

        if len(meal_plan) > MAX_PLAN_LENGTH:
            logger.warning(f"⚠️ План слишком длинный ({len(meal_plan)} символов), обрезаем до {MAX_PLAN_LENGTH}")
            meal_plan = meal_plan[:MAX_PLAN_LENGTH] + "...\n\n⚠️ План был сокращен для удобства чтения."

        # Добавляем заголовок
        formatted_plan = f"🍽️ **ПЕРСОНАЛЬНЫЙ ПЛАН ПИТАНИЯ ОТ НУТРИЦИОЛОГА**\n\n{meal_plan}"

        # Добавляем калории
        formatted_plan += f"\n\n⚖️ **Общая калорийность дня:** {calories.get('target', 2000)} ккал"

        logger.info(f"✅ План успешно сгенерирован через GPT ({len(formatted_plan)} символов)")
        return formatted_plan

    except Exception as e:
        logger.error(f"❌ Ошибка при генерации плана через GPT: {e}")
        return await _generate_fallback_plan(calories, favorite_foods, excluded_foods, health_issues, goal)


async def _generate_fallback_plan(calories: dict, favorite_foods: str = None,
                                  excluded_foods: str = None, health_issues: str = None,
                                  goal: str = None) -> str:
    """Запасной вариант - заглушка"""

    target_calories = calories.get('target', 2000)

    plan = f"""
🍽️ **БАЗОВЫЙ ПЛАН ПИТАНИЯ** (заглушка)

🎯 **Цель:** {goal or 'поддержание формы'}
⚖️ **Калории:** {target_calories} ккал/день

🍳 **ЗАВТРАК (7-9 утра):**
• Овсянка на воде с фруктами (~400 ккал)
• Или омлет из 2 яиц с овощами

🥗 **ОБЕД (13-15 дня):**
• {favorite_foods.split(',')[0].strip() if favorite_foods else 'Куриная грудка'} 150г
• Гречка/рис 100г (в сухом виде)
• Салат из свежих овощей

🍲 **УЖИН (19-20 вечера):**
• Рыба или творог 150г
• Тушёные овощи
• Кефир перед сном (по желанию)

🍎 **ПЕРЕКУСЫ:**
• Фрукты
• Горсть орехов
• Йогурт

💧 **Пей 2+ литра воды в день!**

🚫 **Исключено:** {excluded_foods or 'нет'}
🏥 **Учёт здоровья:** {health_issues or 'нет'}
"""

    return plan

async def generate_training_plan(goal: str, gender: str, age: int, weight: float,
                                 height: int, activity_level: str, health_issues: str = None) -> str:
    """
    Генерация персональной программы тренировок через GPT
    """
    client = get_client()
    if not client:
        return "💪 Программа тренировок временно недоступна."

    system_prompt = """Ты - профессиональный фитнес-тренер с 10-летним опытом. 
Составь персонализированную программу тренировок на русском языке.

ВАЖНО: Ответ должен быть КРАТКИМ и ПРАКТИЧНЫМ (максимум 1500 символов).

ФОРМАТ ОТВЕТА:
📅 День 1 (Силовая)
🔹 Упражнения:
   • Название - подходы x повторения
   • Название - подходы x повторения

📅 День 2 (Кардио)
🔹 20-30 минут активности + упражнения с весом тела

📅 День 3 (Круговая)
🔹 3-4 круга:
   • Упражнение 1 - 15 повторений
   • Упражнение 2 - 15 повторений

💡 Советы по технике безопасности"""

    user_prompt = f"""
Составь программу тренировок на основе данных:

Цель: {goal}
Пол: {gender}
Возраст: {age} лет
Вес: {weight} кг
Рост: {height} см
Уровень: {activity_level or 'начинающий'}
Здоровье: {health_issues or 'нет'}

Требования:
- 3 тренировки в неделю
- Учитывай цель пользователя
- Простые упражнения, которые можно делать дома
- Коротко и понятно
"""

    try:
        result = await ask_gpt(user_prompt, system_prompt)
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации тренировок: {e}")
        return "💪 Программа тренировок временно недоступна."

async def analyze_food_photo(image_bytes: bytes) -> str:
    """Анализ фотографии еды через GPT-4 Vision"""
    client = get_client()
    if not client:
        return "⚠️ Сервис анализа фото временно недоступен"

    try:
        import base64

        # Кодируем изображение в base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты - профессиональный диетолог. Анализируй фотографии еды, определяй продукты и их примерную калорийность. Отвечай на русском языке."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text",
                         "text": "Что на этой фотографии? Оцени примерную калорийность и питательную ценность."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_completion_tokens=500
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}")
        return f"⚠️ Не удалось проанализировать фото: {str(e)[:100]}"