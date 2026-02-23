# app/services/nutrition.py
import logging
from app.utils.openai_client import ask_gpt

logger = logging.getLogger(__name__)


class NutritionService:
    @staticmethod
    async def generate_daily_plan(user_data: dict) -> str:
        """Генерация дневного плана питания"""
        prompt = f"""
        Создай план питания на день для пользователя:
        Цель: {user_data.get('goal')}
        Пол: {user_data.get('gender')}
        Возраст: {user_data.get('age')}
        Рост: {user_data.get('height')} см
        Вес: {user_data.get('weight')} кг
        Любимые продукты: {user_data.get('favorite_foods')}
        Исключения: {user_data.get('excluded_foods')}

        Предложи 3 основных приема пищи и 2 перекуса с примерной калорийностью и БЖУ.
        Формат: понятный список с блюдами.
        """

        try:
            response = await ask_gpt(prompt)
            return response
        except Exception as e:
            logger.error(f"Ошибка генерации плана: {e}")
            return "Сегодня попробуй:\n• Завтрак: овсянка с фруктами\n• Обед: курица с овощами\n• Ужин: рыба с салатом"

    @staticmethod
    async def analyze_food_photo(photo_description: str) -> str:
        """Анализ фото еды через GPT"""
        prompt = f"""
        Проанализируй это описание еды и дай рекомендации по питанию:
        {photo_description}

        Оцени:
        1. Сбалансированность приема пищи
        2. Примерную калорийность и БЖУ
        3. Рекомендации по улучшению
        4. Идеи для следующего приема пищи

        Будь дружелюбным и поддерживающим!
        """

        try:
            response = await ask_gpt(prompt)
            return response
        except Exception as e:
            logger.error(f"Ошибка анализа фото: {e}")
            return "Не могу проанализировать фото сейчас. Попробуй позже или опиши еду текстом."