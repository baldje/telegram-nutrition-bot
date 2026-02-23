# app/utils/calculations.py
def calculate_calories(gender, age, height, weight, goal, activity='минимальная'):
    # Проверка на None
    if any(v is None for v in [gender, age, height, weight]):
        raise ValueError("Не все обязательные данные предоставлены")

    # Проверка типов
    if not isinstance(age, (int, float)) or not isinstance(height, (int, float)) or not isinstance(weight,
                                                                                                   (int, float)):
        raise ValueError("Возраст, рост и вес должны быть числами")

    # Базальная метаболическая скорость (BMR)
    if gender == 'мужской':
        bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:
        bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

    # Коэффициент активности
    activity_factors = {
        'минимальная': 1.2,
        'легкая': 1.375,
        'умеренная': 1.55,
        'высокая': 1.725,
        'экстремальная': 1.9
    }

    activity_factor = activity_factors.get(activity.lower(), 1.2)
    maintenance = bmr * activity_factor

    # Корректировка под цель
    goal_factors = {
        'похудение': 0.85,
        'набор массы': 1.15,
        'поддержание': 1.0,
        'рельеф': 0.9,
        'здоровье': 1.0
    }

    goal_factor = goal_factors.get(goal, 1.0)
    target = maintenance * goal_factor

    return {
        'bmr': round(bmr),
        'maintenance': round(maintenance),
        'target': round(target),
        'daily': round(maintenance)  # для начала используем maintenance
    }