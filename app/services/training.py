# app/services/training.py
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TrainingService:
    TRAINING_PLANS = {
        "beginner": {
            "day1": "Кардио: 20 мин ходьбы + упражнения на пресс",
            "day2": "Силовая: приседания, отжимания, планка",
            "day3": "Отдых или легкая растяжка"
        },
        # ... другие планы
    }

    @staticmethod
    def calculate_user_level(medals: int, cups: int) -> dict:
        """Расчет статуса пользователя"""
        levels = [
            {"name": "Новичок", "min_medals": 0, "max_medals": 1},
            {"name": "Уверенный", "min_medals": 2, "max_medals": 3},
            {"name": "Продвинутый", "min_medals": 4, "max_medals": 5},
            {"name": "Сильный игрок", "min_medals": 6, "max_medals": 7},
            {"name": "Профи", "min_medals": 8, "max_medals": 9},
            {"name": "Легенда", "min_medals": 10, "max_medals": None}
        ]

        for level in levels:
            if level["max_medals"] is None and medals >= level["min_medals"]:
                return level
            elif level["min_medals"] <= medals <= level["max_medals"]:
                return level

        return levels[0]

    @staticmethod
    async def check_achievements(user):
        """Проверка и выдача достижений"""
        achievements = []

        # Проверка недельной серии
        if user.current_streak >= 7 and user.last_training.date() == datetime.utcnow().date():
            achievements.append({
                "type": "medal",
                "message": "Неделя без пропусков! Ты получаешь медаль 🏅!"
            })

        # Проверка месячной серии
        if user.current_streak >= 30:
            achievements.append({
                "type": "cup",
                "message": "Месяц тренировок — держи кубок 🏆!"
            })

        return achievements