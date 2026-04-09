from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import logging
from datetime import datetime

from app.database.crud import UserCRUD, TrainerCRUD, FoodDiaryCRUD
from app.utils.navigation import Navigation

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "👨‍🏫 Мой тренер")
async def my_trainer_info(message: Message, db=None):
    if not db:
        return
    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
    if not user:
        return

    trainers = await TrainerCRUD.get_client_trainers(db.session, user.id)
    if not trainers:
        await message.answer(
            "👨‍🏫 *У вас нет тренера*\n\n"
            "Вы можете:\n"
            "• Перейти по ссылке-приглашению\n"
            "• Отправить `/trainer @username_тренера`",
            parse_mode="HTML",
            reply_markup=Navigation.get_back_button()
        )
        return

    trainer = trainers[0]
    today_entries = await FoodDiaryCRUD.get_day_entries(db.session, user.id, datetime.now().date())
    total_cal = sum(e.calories or 0 for e in today_entries)

    text = (
        f"👨‍🏫 *Ваш тренер*\n\n"
        f"👤 {trainer.full_name or trainer.username}\n"
        f"📊 Ваша статистика сегодня: {total_cal} ккал\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отвязаться", callback_data="client_remove_trainer")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "client_remove_trainer")
async def client_remove_trainer_confirm(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="client_remove_trainer_yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("⚠️ Отвязаться от тренера?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "client_remove_trainer_yes")
async def client_remove_trainer(callback: CallbackQuery, db=None):
    from sqlalchemy import select
    from app.database.models import TrainerClient

    user = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
    rel = (await db.session.execute(
        select(TrainerClient).where(
            TrainerClient.client_id == user.id,
            TrainerClient.status == 'active'
        )
    )).scalar_one_or_none()

    if rel:
        await db.session.delete(rel)
        await db.session.commit()
        await callback.message.delete()
        await callback.message.answer("✅ Вы отвязались от тренера", reply_markup=Navigation.get_main_menu())
    else:
        await callback.message.edit_text("❌ Связь не найдена")
    await callback.answer()