from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    waiting_goal = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_height = State()
    waiting_weight = State()
    waiting_favorite_foods = State()
    waiting_excluded_foods = State()
    waiting_health_issues = State()
    waiting_training_current = State()
    waiting_training_wants = State()

class NutritionStates(StatesGroup):
    """Состояния для анализа питания"""
    waiting_meal_type = State()  # Ожидание выбора типа приема пищи
    waiting_photo = State()      # Ожидание фото
    waiting_text = State()       # Ожидание текстового описания
    confirm_entry = State()      # Подтверждение записи

class PaymentStates(StatesGroup):
    waiting_payment = State()

# app/utils/states.py - добавьте в конец

class FoodDiaryStates(StatesGroup):
    """Состояния для дневника питания"""
    choosing_meal_type = State()
    waiting_food_description = State()
    waiting_food_photo = State()
    confirm_entry = State()
    viewing_history = State()