# app/utils/middlewares.py
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from typing import Any, Awaitable, Callable, Dict, Union
from datetime import datetime, timedelta
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud import UserCRUD
from app.utils.navigation import Navigation
from app.utils.legal_texts import CONSENT_REMINDER

logger = logging.getLogger(__name__)


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для проверки доступа к премиум-функциям"""

    # Команды и кнопки, доступные без подписки
    PUBLIC_COMMANDS = [
        "/start", "/help", "/subscribe", "/premium",
        "/tariffs", "/cancel", "/status", "/support",
        "/privacy", "/offer", "/referral", "/my_discount"
    ]

    PUBLIC_BUTTONS = [
        "🔙 В главное меню", "❌ Отменить действие", "❓ Помощь",
        "💎 Премиум", "ℹ️ Что умеет бот", "❌ Не сейчас",
        "🍽 Питание", "💪 Тренировки", "📋 Команды бота",
        "📞 Связаться с поддержкой", "🔐 Документы", "🎁 Рефералка", "💰 Моя скидка",
        "✅ Да, начать", "🔐 Согласие на обработку данных",  # ДОБАВЛЕНО
        "🔐 Политика конфиденциальности", "📄 Публичная оферта"  # ДОБАВЛЕНО
    ]

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """Обработка middleware для всех типов событий"""

        # Проверяем, что событие - Message или CallbackQuery
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        # Получаем пользователя
        db = data.get('db')
        if not db:
            return await handler(event, data)

        user_id = event.from_user.id
        user = await UserCRUD.get_by_telegram_id(db.session, user_id)

        # Если пользователя нет - пропускаем (будет создан в start)
        if not user:
            return await handler(event, data)

        # Проверяем, является ли запрос публичным
        if await self._is_public_request(event):
            return await handler(event, data)

        # Проверяем доступ к премиум-функциям
        has_access, status_text = await self._check_access(user)

        if has_access:
            # Есть доступ - пропускаем
            return await handler(event, data)
        else:
            # Нет доступа - блокируем
            await self._block_access(event, status_text)
            return

    async def _is_public_request(self, event: Union[Message, CallbackQuery]) -> bool:
        """Проверяет, является ли запрос публичным"""
        if isinstance(event, Message):
            # Проверяем команды
            if event.text and event.text.startswith('/'):
                return event.text.split()[0] in self.PUBLIC_COMMANDS

            # Проверяем текстовые кнопки
            if event.text in self.PUBLIC_BUTTONS:
                return True

        elif isinstance(event, CallbackQuery):
            # Разрешаем callback'и связанные с оплатой, навигацией, юридическими и реферальными
            if event.data in [
                'premium_info', 'back_to_main', 'check_payment', 'cancel_payment',
                'show_privacy', 'show_offer', 'accept_terms', 'decline_terms',
                'show_referral', 'referral_stats', 'my_discount', 'referral_rules',
                'activate_referral', 'how_to_increase_discount', 'pay_with_discount',
                'show_documents'
            ]:
                return True
            if event.data and event.data.startswith(('tariff_', 'copy_ref_')):
                return True

        return False

    async def _check_access(self, user) -> tuple[bool, str]:
        """
        Проверяет доступ к премиум-функциям
        Возвращает (доступ, текст статуса)
        """
        now = datetime.utcnow()

        # 1. Проверяем активную подписку
        if user.subscription_until and user.subscription_until > now:
            days_left = (user.subscription_until - now).days
            return True, f"⭐ Премиум активен (осталось {days_left} дн.)"

        # 2. Проверяем триал (3 дня с момента регистрации)
        if user.trial_started_at:
            trial_end = user.trial_started_at + timedelta(days=3)
            if now < trial_end:
                days_left = (trial_end - now).days
                return True, f"🆓 Бесплатный триал (осталось {days_left} дн.)"

        # 3. Нет доступа
        return False, "❌ Нет активной подписки"

    async def _block_access(self, event: Union[Message, CallbackQuery], status_text: str):
        """Блокирует доступ с пояснением"""
        text = (
            f"{status_text}\n\n"
            f"Для доступа к этой функции оформи подписку:\n"
            f"/subscribe"
        )

        if isinstance(event, Message):
            await event.answer(text, reply_markup=Navigation.get_main_menu())
        elif isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=Navigation.get_main_menu())
            await event.answer()


class LegalMiddleware(BaseMiddleware):
    """
    Middleware для проверки наличия согласия на обработку данных.
    Должен быть добавлен после DatabaseMiddleware и перед SubscriptionMiddleware.
    """

    # Разрешенные команды без согласия
    ALLOWED_COMMANDS = [
        '/start', '/privacy', '/offer', '/referral', '/my_discount'
    ]

    # Разрешенные callback данные
    ALLOWED_CALLBACKS = [
        'show_privacy', 'show_offer', 'accept_terms', 'decline_terms', 'show_documents',
        'show_referral', 'referral_stats', 'my_discount', 'referral_rules',
        'activate_referral', 'how_to_increase_discount', 'pay_with_discount',
        'back_to_main', 'premium_info', 'check_payment', 'cancel_payment',
        'tariff_month', 'tariff_3months', 'tariff_year'
    ]

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        # Получаем сессию из data
        session: AsyncSession = data.get('session')
        state: FSMContext = data.get('state')

        # Определяем тип события
        user_id = None
        event_text = None

        if isinstance(event, Message):
            logger.error(f"🔥🔥🔥 LegalMiddleware: получил сообщение '{event.text}' от {event.from_user.id}")
            user_id = event.from_user.id
            event_text = event.text

            # Проверяем разрешенные команды
            if event_text:
                # Проверяем /start с реферальным кодом
                if event_text.startswith('/start'):
                    return await handler(event, data)
                # Проверяем другие разрешенные команды
                if event_text.split()[0] in self.ALLOWED_COMMANDS:
                    return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            event_text = event.data

            # Проверяем разрешенные callback'и
            if event_text:
                # Проверяем copy_ref_* (начинается с префикса)
                if event_text.startswith('copy_ref_'):
                    return await handler(event, data)
                # Проверяем точное совпадение
                if event_text in self.ALLOWED_CALLBACKS:
                    return await handler(event, data)

        if not user_id:
            return await handler(event, data)

        # Если нет сессии - пропускаем
        if not session:
            logger.warning("Нет сессии БД в LegalMiddleware")
            return await handler(event, data)

        # Проверяем согласие
        try:
            has_consent = await UserCRUD.check_consent(session, user_id)

            logger.error(f"🔥🔥🔥 LegalMiddleware: has_consent = {has_consent} для пользователя {user_id}")

            # Проверяем состояние
            if state:
                current_state = await state.get_state()
                logger.error(f"🔥🔥🔥 LegalMiddleware: состояние пользователя {user_id} = {current_state}")

            if not has_consent:
                # Если согласия нет, отправляем напоминание
                if isinstance(event, Message):
                    await event.answer(
                        CONSENT_REMINDER,
                        reply_markup=Navigation.get_consent_reminder_keyboard(),
                        parse_mode="HTML"
                    )
                elif isinstance(event, CallbackQuery):
                    await event.message.answer(
                        CONSENT_REMINDER,
                        reply_markup=Navigation.get_consent_reminder_keyboard(),
                        parse_mode="HTML"
                    )
                    await event.answer()

                # Не передаем управление дальше
                return
        except Exception as e:
            logger.error(f"Ошибка в LegalMiddleware: {e}")
            return await handler(event, data)

        # Если согласие есть, продолжаем
        logger.error(f"🔥🔥🔥 LegalMiddleware: передаю управление дальше для пользователя {user_id}")
        return await handler(event, data)