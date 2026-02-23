# app/utils/openai_food_analyzer.py — АНАЛИЗ ФОТО ЕДЫ ЧЕРЕЗ OPENAI
import logging
import os
import base64
import json
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Глобальный клиент
_client = None
_MODEL = None


def _get_api_key() -> Optional[str]:
    """Безопасное получение API ключа"""
    try:
        from app.utils.config import config
        if hasattr(config, 'openai') and hasattr(config.openai, 'api_key'):
            return config.openai.api_key
    except Exception:
        pass

    return os.getenv("OPENAI_API_KEY")


def _get_model() -> str:
    """Безопасное получение модели"""
    try:
        from app.utils.config import config
        if hasattr(config, 'openai') and hasattr(config.openai, 'model'):
            return config.openai.model
    except Exception:
        pass

    return os.getenv("OPENAI_MODEL", "gpt-5-nano")


def get_client():
    """Ленивое получение OpenAI клиента"""
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
        return _client

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
        return None


async def analyze_food_photo(image_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Анализирует фото еды и возвращает пищевую ценность

    Returns:
        analysis dict или None
    """
    client = get_client()
    if not client:
        logger.error("❌ OpenAI клиент не инициализирован")
        return None

    prompt = """Ты опытный диетолог. Проанализируй фотографию еды.

ТВОЯ ЗАДАЧА:
1. Определи что изображено на фото
2. Определи блюда и ингредиенты
3. Оцени примерный вес в граммах
4. Рассчитай примерную калорийность и БЖУ

ВЕРНИ ОТВЕТ СТРОГО В JSON:
{
  "analysis": {
    "description": "что изображено",
    "dishes": [
      {
        "name": "название блюда",
        "ingredients": ["ингредиент1", "ингредиент2"],
        "estimated_weight_grams": 250
      }
    ],
    "nutrition": {
      "total_calories": 450,
      "protein_grams": 25.5,
      "fat_grams": 18.2,
      "carbs_grams": 45.3
    },
    "confidence": "high/medium/low",
    "notes": "заметки"
  }
}

Только JSON. Без пояснений.
"""

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

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
            "model": _MODEL,
            "messages": messages,
        }

        logger.info("📸 Отправляем фото еды в OpenAI...")

        try:
            response = await client.chat.completions.create(**params)
        except Exception as e:
            error_str = str(e)
            if "max_completion_tokens" in error_str:
                logger.info("🔄 Повтор с max_completion_tokens=900")
                params["max_completion_tokens"] = 900
                response = await client.chat.completions.create(**params)
            elif "max_tokens" in error_str:
                logger.info("🔄 Повтор с max_tokens=900")
                params["max_tokens"] = 900
                response = await client.chat.completions.create(**params)
            else:
                raise e

        result_text = response.choices[0].message.content.strip()

        # Убираем markdown-обертки
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
        if result_text.endswith("```"):
            result_text = result_text.rsplit("```", 1)[0]

        result_json = json.loads(result_text)

        logger.info("✅ Фото еды успешно проанализировано")

        return result_json.get("analysis")

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON от OpenAI: {e}")
        logger.debug(f"Ответ: {result_text[:300]}")
        return None

    except Exception as e:
        logger.error(f"❌ Ошибка анализа фото еды: {e}")
        return None


async def estimate_calories_from_text(food_description: str) -> Dict[str, Any]:
    """Оценка калорий по текстовому описанию"""
    client = get_client()
    if not client:
        return {"error": "OpenAI недоступен"}

    prompt = f"""Оцени калорийность и БЖУ для блюда:
"{food_description}"

Верни строго JSON:
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
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = await client.chat.completions.create(**params)
        result_text = response.choices[0].message.content.strip()

        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
        if result_text.endswith("```"):
            result_text = result_text.rsplit("```", 1)[0]

        return json.loads(result_text)

    except Exception as e:
        logger.error(f"❌ Ошибка оценки калорий по тексту: {e}")
        return {
            "estimated_calories": 0,
            "protein_grams": 0,
            "fat_grams": 0,
            "carbs_grams": 0,
            "serving_size_grams": 0,
            "error": str(e)
        }
