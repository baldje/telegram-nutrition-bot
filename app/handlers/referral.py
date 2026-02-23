# app/handlers/referral.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import UserCRUD
from app.utils.legal_texts import REFERRAL_TEXT, DISCOUNT_INFO_TEXT
from app.utils.navigation import Navigation

router = Router()


@router.message(Command("referral"))
async def cmd_referral(message: Message, session: AsyncSession):
    """Показать реферальную программу"""
    user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Сначала нужно зарегистрироваться через /start")
        return

    referrals_count = await UserCRUD.get_referrals_count(session, user.id)
    discount = user.discount_percent or 0

    # Определяем следующую цель
    next_discount = min(((referrals_count // 5) + 1) * 5, 30)
    next_referrals = 5 - (referrals_count % 5) if referrals_count < 30 else 0

    # Склонение слова "друг"
    if next_referrals % 10 == 1 and next_referrals % 100 != 11:
        friends_word = "друга"
    elif 2 <= next_referrals % 10 <= 4 and (next_referrals % 100 < 10 or next_referrals % 100 >= 20):
        friends_word = "друзей"
    else:
        friends_word = "друзей"

    text = REFERRAL_TEXT.format(
        code=user.referral_code,
        referrals_count=referrals_count,
        discount=discount,
        balance=user.balance or 0,
        next_referrals=next_referrals,
        friends_word=friends_word,
        next_discount=next_discount
    )

    await message.answer(
        text,
        reply_markup=Navigation.get_referral_inline_keyboard(user.referral_code),
        parse_mode="Markdown"
    )


@router.message(Command("my_discount"))
@router.message(F.text == "💰 Моя скидка")
async def cmd_my_discount(message: Message, session: AsyncSession):
    """Показать текущую скидку"""
    user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Сначала нужно зарегистрироваться через /start")
        return

    referrals_count = await UserCRUD.get_referrals_count(session, user.id)
    discount = user.discount_percent or 0
    referral_discount = referrals_count * 5

    # Прогресс-бар
    progress = int((referrals_count / 6) * 10)  # Макс 30% = 6 друзей по 5%
    progress_bar = "▰" * progress + "▱" * (10 - progress)

    text = DISCOUNT_INFO_TEXT.format(
        discount=discount,
        progress_bar=progress_bar,
        referrals_count=referrals_count,
        referral_discount=referral_discount,
        balance=user.balance or 0
    )

    await message.answer(
        text,
        reply_markup=Navigation.get_discount_info_keyboard(),
        parse_mode="Markdown"
    )


@router.message(F.text == "🎁 Рефералка")
async def text_referral(message: Message, session: AsyncSession):
    """Показать реферальную программу из меню"""
    await cmd_referral(message, session)


@router.callback_query(F.data == "show_referral")
async def callback_show_referral(callback: CallbackQuery, session: AsyncSession):
    """Показать реферальную программу"""
    user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
    if user:
        await callback.message.answer(
            f"🎁 *Реферальная программа*\n\n"
            f"Ваш код: `{user.referral_code}`\n"
            f"Скидка: {user.discount_percent or 0}%",
            reply_markup=Navigation.get_referral_inline_keyboard(user.referral_code),
            parse_mode="Markdown"
        )
    await callback.answer()


@router.callback_query(F.data == "referral_stats")
async def callback_referral_stats(callback: CallbackQuery, session: AsyncSession):
    """Показать статистику рефералов"""
    user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
    if user:
        referrals_count = await UserCRUD.get_referrals_count(session, user.id)
        await callback.message.answer(
            f"📊 *Статистика рефералов*\n\n"
            f"• Приглашено друзей: {referrals_count}\n"
            f"• Текущая скидка: {user.discount_percent or 0}%\n"
            f"• Баланс: {user.balance or 0} ₽",
            parse_mode="Markdown"
        )
    await callback.answer()


@router.callback_query(F.data == "my_discount")
async def callback_my_discount(callback: CallbackQuery, session: AsyncSession):
    """Показать информацию о скидке"""
    await cmd_my_discount(callback.message, session)
    await callback.answer()


@router.callback_query(F.data == "referral_rules")
async def callback_referral_rules(callback: CallbackQuery):
    """Показать правила реферальной программы"""
    await callback.message.answer(
        "📖 *Правила реферальной программы*\n\n"
        "1. За каждого приглашенного друга вы получаете +5% скидки\n"
        "2. Максимальная скидка - 30%\n"
        "3. Друг получает 5% скидки при регистрации\n"
        "4. На баланс начисляется 50 ₽ за каждого друга\n"
        "5. Скидка действует на все тарифы подписки\n"
        "6. Скидка суммируется с другими акциями\n\n"
        "Чтобы пригласить друга, отправьте ему свою реферальную ссылку",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith('copy_ref_'))
async def callback_copy_ref(callback: CallbackQuery):
    """Обработка копирования реферальной ссылки"""
    code = callback.data.replace('copy_ref_', '')
    await callback.message.answer(
        f"📋 *Ваша реферальная ссылка:*\n"
        f"`https://t.me/ваш_бот?start=ref_{code}`\n\n"
        f"Отправьте эту ссылку друзьям!",
        parse_mode="Markdown"
    )
    await callback.answer("Ссылка скопирована!", show_alert=False)


@router.callback_query(F.data == "how_to_increase_discount")
async def callback_how_to_increase(callback: CallbackQuery, session: AsyncSession):
    """Как увеличить скидку"""
    user = await UserCRUD.get_by_telegram_id(session, callback.from_user.id)
    if user:
        referrals_count = await UserCRUD.get_referrals_count(session, user.id)
        next_target = ((referrals_count // 5) + 1) * 5
        needed = 5 - (referrals_count % 5)

        await callback.message.answer(
            f"📈 *Как увеличить скидку*\n\n"
            f"• Сейчас у вас {user.discount_percent or 0}% скидки\n"
            f"• До {next_target}% осталось пригласить {needed} друзей\n\n"
            f"*Способы получить скидку:*\n"
            f"1. Приглашайте друзей по ссылке\n"
            f"2. Участвуйте в акциях\n"
            f"3. Покупайте годовую подписку",
            parse_mode="Markdown"
        )
    await callback.answer()