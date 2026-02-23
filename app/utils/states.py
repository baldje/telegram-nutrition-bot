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
    waiting_photo = State()
    waiting_feedback = State()

class PaymentStates(StatesGroup):
    waiting_payment = State()