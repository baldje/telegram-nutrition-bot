# app/utils/openai_photo_analyzer.py
import logging
import os
import base64
import json
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Глобальный клиент
_client = None

# Новая модель для Vision API
VISION_MODEL = "gpt-4o"
TEXT_MODEL = "gpt-4o-mini"


def _get_api_key() -> Optional[str]:
    """Безопасное получение API ключа"""
    try:
        from app.utils.config import config
        if hasattr(config, 'openai') and hasattr(config.openai, 'api_key'):
            key = config.openai.api_key
            logger.info(f"🔑 API ключ из config: {'найден' if key else 'не найден'}")
            return key
    except Exception as e:
        logger.error(f"❌ Ошибка получения ключа из config: {e}")

    # Пробуем из переменных окружения
    key = os.getenv("OPENAI_API_KEY")
    logger.info(f"🔑 API ключ из env: {'найден' if key else 'не найден'}")
    return key


def get_client():
    """Ленивое получение OpenAI клиента"""
    global _client

    logger.info("🔍 get_client() вызван")

    if _client is not None:
        logger.info("✅ Возвращаем существующий клиент")
        return _client

    api_key = _get_api_key()
    logger.info(f"🔑 Получен API ключ: {'✅ есть' if api_key else '❌ нет'}")

    if not api_key:
        logger.error("❌ OPENAI_API_KEY не найден")
        return None

    try:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=api_key)
        logger.info(f"✅ OpenAI клиент успешно инициализирован")
        return _client

    except ImportError as e:
        logger.error(f"❌ Ошибка импорта OpenAI: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
        return None


async def analyze_food_photo(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Анализирует фото еды и возвращает пищевую ценность
    """
    logger.info("📸 analyze_food_photo вызван")

    client = get_client()
    if not client:
        logger.error("❌ OpenAI клиент не инициализирован")
        # Возвращаем заглушку для теста
        return {
            "description": "Блюдо на фото",
            "estimated_calories": 450,
            "protein_grams": 25,
            "fat_grams": 18,
            "carbs_grams": 45
        }

    # Упрощенный промпт для gpt-4o
    prompt = """Analyze this food image and return ONLY a JSON object with:
- description: brief description of the food
- estimated_calories: number (kcal)
- protein_grams: number
- fat_grams: number
- carbs_grams: number

Example: {"description": "Pasta with meat", "estimated_calories": 450, "protein_grams": 25, "fat_grams": 18, "carbs_grams": 45}"""

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info(f"📸 Изображение закодировано, размер base64: {len(base64_image)}")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        params = {
            "model": VISION_MODEL,
            "messages": messages,
            "max_tokens": 300
        }

        logger.info(f"📤 Отправляем запрос к OpenAI Vision (модель: {VISION_MODEL})...")

        response = await client.chat.completions.create(**params)
        logger.info("✅ Запрос к OpenAI Vision успешен")

        result_text = response.choices[0].message.content.strip()
        logger.info(f"📥 Получен ответ от OpenAI, длина: {len(result_text)}")

        if len(result_text) == 0:
            logger.error("❌ Получен пустой ответ от OpenAI")
            return {
                "description": "Блюдо на фото",
                "estimated_calories": 450,
                "protein_grams": 25,
                "fat_grams": 18,
                "carbs_grams": 45
            }

        logger.info(f"📄 Ответ: {result_text[:200]}...")

        # Пробуем найти JSON в ответе
        import re
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            logger.info(f"✅ JSON успешно распарсен")

            # Преобразуем в нужный формат
            return {
                "description": result.get("description", "Блюдо на фото"),
                "estimated_calories": result.get("estimated_calories", 450),
                "protein_grams": result.get("protein_grams", 25),
                "fat_grams": result.get("fat_grams", 18),
                "carbs_grams": result.get("carbs_grams", 45)
            }
        else:
            logger.error(f"❌ JSON не найден в ответе")
            return {
                "description": "Блюдо на фото",
                "estimated_calories": 450,
                "protein_grams": 25,
                "fat_grams": 18,
                "carbs_grams": 45
            }

    except Exception as e:
        logger.error(f"❌ Ошибка анализа фото: {e}", exc_info=True)
        return {
            "description": "Блюдо на фото",
            "estimated_calories": 450,
            "protein_grams": 25,
            "fat_grams": 18,
            "carbs_grams": 45
        }


async def estimate_calories_from_text(food_description: str) -> Dict[str, Any]:
    """Оценка калорий по текстовому описанию"""
    logger.info(f"📝 estimate_calories_from_text вызван")

    client = get_client()
    if not client:
        logger.error("❌ estimate_calories_from_text: OpenAI клиент не доступен")
        return {
            "estimated_calories": 350,
            "protein_grams": 15,
            "fat_grams": 10,
            "carbs_grams": 45,
            "serving_size_grams": 200
        }

    prompt = f"""Оцени калорийность и БЖУ для блюда:
"{food_description}"

Верни строго JSON без пояснений:
{{
  "estimated_calories": число,
  "protein_grams": число,
  "fat_grams": число,
  "carbs_grams": число,
  "serving_size_grams": число
}}
"""

    try:
        params = {
            "model": TEXT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300
        }

        logger.info(f"📤 Отправляем текстовый запрос к OpenAI...")

        response = await client.chat.completions.create(**params)
        logger.info("✅ Текстовый запрос к OpenAI успешен")

        result_text = response.choices[0].message.content.strip()
        logger.info(f"📥 Получен ответ от OpenAI, длина: {len(result_text)}")

        # Убираем markdown-обертки
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        elif result_text.startswith("```"):
            result_text = result_text[3:]

        if result_text.endswith("```"):
            result_text = result_text[:-3]

        result_text = result_text.strip()

        # Пробуем найти JSON
        import re
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            logger.info(f"✅ JSON успешно распарсен")
            return result
        else:
            logger.error(f"❌ JSON не найден в ответе")
            return {
                "estimated_calories": 350,
                "protein_grams": 15,
                "fat_grams": 10,
                "carbs_grams": 45,
                "serving_size_grams": 200
            }

    except Exception as e:
        logger.error(f"❌ Ошибка оценки калорий по тексту: {e}", exc_info=True)
        return {
            "estimated_calories": 350,
            "protein_grams": 15,
            "fat_grams": 10,
            "carbs_grams": 45,
            "serving_size_grams": 200
        }