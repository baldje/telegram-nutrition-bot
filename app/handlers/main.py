# app/handlers/main.py
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import logging

from app.services.onboarding import OnboardingService, OnboardingStates
from app.services.nutrition import NutritionService
from app.services.training import TrainingService
# from app.keyboards.main import MainKeyboard
from datetime import datetime

# ✅ ЭТО САМОЕ ГЛАВНОЕ - создаем роутер
main_router = Router()
logger = logging.getLogger(__name__)


@main_router.message(F.text == "📷 Фото еды")
async def request_food_photo(message: Message):
    await message.answer("Отправь фото своего приема пищи для анализа 📸")


@main_router.message(F.photo)
async def analyze_food_photo(message: Message):
    await message.answer("Анализирую твою еду...")

    # В реальности нужно обработать фото, пока просто заглушка
    analysis = await NutritionService.analyze_food_photo("фото еды пользователя")
    await message.answer(analysis)


async def show_trial_day(message: Message, user):
    """Показ соответствующего дня триала"""
    trial_day = (datetime.utcnow() - user.trial_start).days + 1

    if trial_day == 1:
        plan = await NutritionService.generate_daily_plan(user)
        await message.answer(f"День 1 твоего теста:\n\n{plan}")
    elif trial_day == 2:
        await message.answer(
            "День 2: Отправь фото каждого приема пищи — я дам фидбэк и подсчитаю примерный КБЖУ"
        )
    elif trial_day == 3:
        await message.answer(
            "День 3: Готова неделя питания! Выбери вариант:",
            # reply_markup=MainKeyboard.day3_options()  # закомментировано, так как не импортировано
        )