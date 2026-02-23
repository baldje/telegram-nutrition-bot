# app/handlers/legal.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.filters import StateFilter  # вместо flag используем StateFilter для пропуска middleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import UserCRUD
from app.utils.legal_texts import PRIVACY_TEXT, OFFER_TEXT, CONSENT_TEXT, CONSENT_SUCCESS
from app.utils.navigation import Navigation

router = Router()


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    """Показывает политику конфиденциальности"""
    await message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(Command("offer"))
async def cmd_offer(message: Message):
    """Показывает публичную оферту"""
    await message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "🔐 Политика конфиденциальности")
async def text_privacy(message: Message):
    """Показывает политику конфиденциальности из меню"""
    await message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "📄 Публичная оферта")
async def text_offer(message: Message):
    """Показывает публичную оферту из меню"""
    await message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "🔐 Документы")
async def text_documents(message: Message):
    """Показывает меню документов"""
    await message.answer(
        "📚 *Юридические документы*\n\n"
        "Выберите документ для просмотра:",
        reply_markup=Navigation.get_documents_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "show_privacy")
async def callback_show_privacy(callback: CallbackQuery):
    """Показывает политику конфиденциальности"""
    await callback.message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "show_offer")
async def callback_show_offer(callback: CallbackQuery):
    """Показывает публичную оферту"""
    await callback.message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "show_documents")
async def callback_show_documents(callback: CallbackQuery):
    """Показывает документы"""
    await callback.message.answer(
        "🔐 *Юридические документы*\n\n"
        "Ознакомьтесь с документами:",
        reply_markup=Navigation.get_legal_inline_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "accept_terms")
async def callback_accept_terms(callback: CallbackQuery, session: AsyncSession):
    """Принятие условий"""
    user_id = callback.from_user.id

    # Получаем пользователя
    user = await UserCRUD.get_by_telegram_id(session, user_id)
    if not user:
        # Создаем пользователя, если его нет
        user = await UserCRUD.create(
            session,
            user_id,
            callback.from_user.username,
            callback.from_user.full_name
        )

    # Записываем согласие
    await UserCRUD.record_consent(
        session,
        user.id,
        ip_address=None,
        user_agent=None
    )

    # Редактируем исходное сообщение
    await callback.message.edit_text(
        "✅ *Условия приняты!*",
        parse_mode="Markdown",
        reply_markup=None
    )

    # Отправляем приветствие
    await callback.message.answer(
        CONSENT_SUCCESS,
        reply_markup=Navigation.get_main_menu(),
        parse_mode="Markdown"
    )

    await callback.answer()


@router.callback_query(F.data == "decline_terms")
async def callback_decline_terms(callback: CallbackQuery):
    """Отказ от условий"""
    await callback.message.edit_text(
        "❌ *Вы отказались от условий*\n\n"
        "Без принятия условий вы не можете пользоваться ботом.\n"
        "Если передумаете, нажмите /start",
        parse_mode="Markdown",
        reply_markup=None
    )
    await callback.answer()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    """Обработчик команды /start"""
    user_id = message.from_user.id

    # Проверяем реферальный код
    args = message.text.split()
    referral_code = args[1][4:] if len(args) > 1 and args[1].startswith('ref_') else None

    # Получаем или создаем пользователя
    user = await UserCRUD.get_by_telegram_id(session, user_id)
    if not user:
        if referral_code:
            user = await UserCRUD.create_user_with_referral(
                session,
                user_id,
                message.from_user.username,
                message.from_user.full_name,
                referral_code
            )
            await message.answer(
                "🎉 *Добро пожаловать!*\n"
                "Вы перешли по реферальной ссылке и получили скидку 5% на первую подписку!",
                parse_mode="Markdown"
            )
        else:
            user = await UserCRUD.create(
                session,
                user_id,
                message.from_user.username,
                message.from_user.full_name
            )

    # Проверяем согласие
    if user.consent_given:
        await message.answer(
            "👋 *Добро пожаловать в бот питания!*\n\n"
            "📸 Отправьте фото еды для анализа\n"
            "🎁 Используйте /referral для получения скидки",
            reply_markup=Navigation.get_main_menu(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            CONSENT_TEXT,
            reply_markup=Navigation.get_legal_inline_keyboard(),
            parse_mode="Markdown"
        )# app/handlers/legal.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.filters import StateFilter  # вместо flag используем StateFilter для пропуска middleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import UserCRUD
from app.utils.legal_texts import PRIVACY_TEXT, OFFER_TEXT, CONSENT_TEXT, CONSENT_SUCCESS
from app.utils.navigation import Navigation

router = Router()


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    """Показывает политику конфиденциальности"""
    await message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(Command("offer"))
async def cmd_offer(message: Message):
    """Показывает публичную оферту"""
    await message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "🔐 Политика конфиденциальности")
async def text_privacy(message: Message):
    """Показывает политику конфиденциальности из меню"""
    await message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "📄 Публичная оферта")
async def text_offer(message: Message):
    """Показывает публичную оферту из меню"""
    await message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@router.message(F.text == "🔐 Документы")
async def text_documents(message: Message):
    """Показывает меню документов"""
    await message.answer(
        "📚 *Юридические документы*\n\n"
        "Выберите документ для просмотра:",
        reply_markup=Navigation.get_documents_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "show_privacy")
async def callback_show_privacy(callback: CallbackQuery):
    """Показывает политику конфиденциальности"""
    await callback.message.answer(
        PRIVACY_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "show_offer")
async def callback_show_offer(callback: CallbackQuery):
    """Показывает публичную оферту"""
    await callback.message.answer(
        OFFER_TEXT,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "show_documents")
async def callback_show_documents(callback: CallbackQuery):
    """Показывает документы"""
    await callback.message.answer(
        "🔐 *Юридические документы*\n\n"
        "Ознакомьтесь с документами:",
        reply_markup=Navigation.get_legal_inline_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "accept_terms")
async def callback_accept_terms(callback: CallbackQuery, session: AsyncSession):
    """Принятие условий"""
    user_id = callback.from_user.id

    # Получаем пользователя
    user = await UserCRUD.get_by_telegram_id(session, user_id)
    if not user:
        # Создаем пользователя, если его нет
        user = await UserCRUD.create(
            session,
            user_id,
            callback.from_user.username,
            callback.from_user.full_name
        )

    # Записываем согласие
    await UserCRUD.record_consent(
        session,
        user.id,
        ip_address=None,
        user_agent=None
    )

    # Редактируем исходное сообщение
    await callback.message.edit_text(
        "✅ *Условия приняты!*",
        parse_mode="Markdown",
        reply_markup=None
    )

    # Отправляем приветствие
    await callback.message.answer(
        CONSENT_SUCCESS,
        reply_markup=Navigation.get_main_menu(),
        parse_mode="Markdown"
    )

    await callback.answer()


@router.callback_query(F.data == "decline_terms")
async def callback_decline_terms(callback: CallbackQuery):
    """Отказ от условий"""
    await callback.message.edit_text(
        "❌ *Вы отказались от условий*\n\n"
        "Без принятия условий вы не можете пользоваться ботом.\n"
        "Если передумаете, нажмите /start",
        parse_mode="Markdown",
        reply_markup=None
    )
    await callback.answer()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    """Обработчик команды /start"""
    user_id = message.from_user.id

    # Проверяем реферальный код
    args = message.text.split()
    referral_code = args[1][4:] if len(args) > 1 and args[1].startswith('ref_') else None

    # Получаем или создаем пользователя
    user = await UserCRUD.get_by_telegram_id(session, user_id)
    if not user:
        if referral_code:
            user = await UserCRUD.create_user_with_referral(
                session,
                user_id,
                message.from_user.username,
                message.from_user.full_name,
                referral_code
            )
            await message.answer(
                "🎉 *Добро пожаловать!*\n"
                "Вы перешли по реферальной ссылке и получили скидку 5% на первую подписку!",
                parse_mode="Markdown"
            )
        else:
            user = await UserCRUD.create(
                session,
                user_id,
                message.from_user.username,
                message.from_user.full_name
            )

    # Проверяем согласие
    if user.consent_given:
        await message.answer(
            "👋 *Добро пожаловать в бот питания!*\n\n"
            "📸 Отправьте фото еды для анализа\n"
            "🎁 Используйте /referral для получения скидки",
            reply_markup=Navigation.get_main_menu(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            CONSENT_TEXT,
            reply_markup=Navigation.get_legal_inline_keyboard(),
            parse_mode="Markdown"
        )