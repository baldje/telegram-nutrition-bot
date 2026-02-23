# app/services/onboarding.py
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import logging

logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    waiting_goal = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_height = State()
    waiting_weight = State()
    waiting_favorite_foods = State()
    waiting_excluded_foods = State()
    waiting_health_issues = State()
    waiting_training = State()
    waiting_training_plans = State()


class OnboardingService:
    def __init__(self, db_session):
        self.db = db_session

    async def start_onboarding(self, message: Message, state: FSMContext):
        """Начало онбординга"""
        await message.answer(
            "Отлично! Ответь на пару вопросов, чтобы я подобрал для тебя план питания и тренировок.\n\n"
            "1. Какая у тебя цель?",
            reply_markup=self._get_goal_keyboard()
        )
        await state.set_state(OnboardingStates.waiting_goal)

    def _get_goal_keyboard(self):
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание")],
                [KeyboardButton(text="Набор массы")]
            ],
            resize_keyboard=True
        )

    async def process_goal(self, message: Message, state: FSMContext):
        """Обработка выбора цели"""
        goal = message.text
        await state.update_data(goal=goal)

        await message.answer(
            "2. Укажи свой пол, возраст, рост и вес\n\n"
            "Пример: Мужчина, 25 лет, 180 см, 75 кг",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(OnboardingStates.waiting_gender)

    async def process_user_info(self, message: Message, state: FSMContext):
        """Парсинг основной информации"""
        # Здесь можно добавить парсинг текста или разбить на отдельные шаги
        user_info = message.text
        await state.update_data(user_info=user_info)

        await message.answer("3. Что любишь есть? (перечисли через запятую)")
        await state.set_state(OnboardingStates.waiting_favorite_foods)

    # ... остальные методы обработки шагов онбординга