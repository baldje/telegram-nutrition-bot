# app/handlers/payments.py
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import uuid4

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import httpx
import qrcode
from io import BytesIO

from app.database.crud import UserCRUD, PaymentCRUD, SubscriptionCRUD
from app.utils.config import config
from app.utils.navigation import Navigation

logger = logging.getLogger(__name__)
router = Router()

TEST_MODE = True  # Режим тестирования без БД


class PaymentStates(StatesGroup):
    """Состояния для процесса оплаты"""
    CHOOSING_TARIFF = State()
    WAITING_PAYMENT = State()


# Тарифы подписки (в копейках)
TARIFFS = {
    "month": {
        "price": config.payment.TARIFF_MONTH,
        "duration": timedelta(days=30),
        "label": "Месячная подписка",
        "description": "Полный доступ на 1 месяц",
        "emoji": "📅"
    },
    "3months": {
        "price": config.payment.TARIFF_3MONTHS,
        "duration": timedelta(days=90),
        "label": "3 месяца подписки",
        "description": "Выгодный тариф на 3 месяца",
        "emoji": "📊"
    },
    "year": {
        "price": config.payment.TARIFF_YEAR,
        "duration": timedelta(days=365),
        "label": "Годовая подписка",
        "description": "Подписка на целый год со скидкой",
        "emoji": "🏆"
    }
}


class TinkoffPaymentService:
    """Сервис для работы с Тинькофф эквайрингом"""

    def __init__(self):
        self.terminal_key = config.payment.TINKOFF_TERMINAL_KEY
        self.secret_key = config.payment.TINKOFF_SECRET_KEY
        self.api_url = config.payment.TINKOFF_API_URL.rstrip('/')

    def _generate_token(self, data: dict) -> str:
        """
        Генерация токена для подписи запроса по спецификации Т-Банка

        Правила:
        1. Берем ТОЛЬКО корневые параметры (без вложенных объектов)
        2. Добавляем Password
        3. Сортируем по алфавиту
        4. Конкатенируем ТОЛЬКО значения (без ключей)
        5. SHA-256
        """
        # Список корневых параметров, которые могут участвовать в токене
        root_params = [
            'TerminalKey', 'Amount', 'OrderId', 'Description',
            'CustomerKey', 'SuccessURL', 'FailURL'
        ]

        # Собираем только те параметры, которые есть в запросе
        token_data = {}
        for key in root_params:
            if key in data and data[key] is not None:
                token_data[key] = str(data[key])

        # Добавляем пароль (секретный ключ)
        token_data['Password'] = self.secret_key

        # Сортируем по ключам (алфавитный порядок)
        sorted_data = dict(sorted(token_data.items()))

        # Конкатенируем ТОЛЬКО значения (без ключей)
        values_string = ''.join(sorted_data.values())

        # Применяем SHA-256
        import hashlib
        token = hashlib.sha256(values_string.encode('utf-8')).hexdigest().lower()

        logger.debug(f"🔑 Token generation data: {sorted_data}")
        logger.debug(f"📝 Values string: {values_string}")
        logger.debug(f"✅ Generated token: {token}")

        return token

    async def create_payment(
            self,
            amount: int,
            order_id: str,
            description: str,
            user_id: int,
            email: Optional[str] = None,
            phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Создание платежа в Тинькофф"""

        # Формируем чек (вложенный объект)
        receipt = None
        if email or phone:
            receipt = {
                "Email": email,
                "Phone": phone,
                "Taxation": "osn",
                "Items": [{
                    "Name": description[:64],
                    "Price": amount,
                    "Quantity": 1,
                    "Amount": amount,
                    "Tax": "none"
                }]
            }

        # DATA объект с доп. информацией
        data_object = {
            "Phone": phone,
            "Email": email
        } if phone or email else None

        success_url = f"https://t.me/{config.bot.username}?start=payment_success_{order_id}"
        fail_url = f"https://t.me/{config.bot.username}?start=payment_failed_{order_id}"

        # Основные параметры платежа
        payload = {
            "TerminalKey": self.terminal_key,
            "Amount": amount,
            "OrderId": order_id,
            "Description": description,
            "CustomerKey": str(user_id),
            "SuccessURL": success_url,
            "FailURL": fail_url
        }

        # Добавляем вложенные объекты (они НЕ участвуют в формировании токена)
        if receipt:
            payload["Receipt"] = receipt
        if data_object and any(data_object.values()):
            payload["DATA"] = data_object

        # Генерируем токен ТОЛЬКО из корневых параметров
        token = self._generate_token(payload)
        payload["Token"] = token

        # 🔍 ОТЛАДКА: посмотрим, что отправляем
        logger.info(f"📦 URL запроса: {self.api_url}/Init")
        logger.info(f"📦 Payload: {json.dumps(payload, ensure_ascii=False, default=str)}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/Init",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                # 🔍 ОТЛАДКА: посмотрим, что пришло в ответ
                logger.info(f"📥 Response status: {response.status_code}")
                logger.info(f"📥 Response body: {response.text}")

                response.raise_for_status()
                result = response.json()

                if result.get('Success'):
                    logger.info(f"✅ Платеж создан: {order_id}, ID: {result.get('PaymentId')}")
                    return {
                        "success": True,
                        "payment_id": result['PaymentId'],
                        "status": result['Status'],
                        "payment_url": result.get('PaymentURL'),
                        "order_id": result.get('OrderId')
                    }
                else:
                    error_msg = result.get('Message', 'Неизвестная ошибка')
                    logger.error(f"❌ Ошибка Т-Банк: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "details": result
                    }

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}",
                "details": e.response.text
            }
        except Exception as e:
            logger.error(f"❌ Ошибка при создании платежа: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Получение статуса платежа"""
        payload = {
            "TerminalKey": self.terminal_key,
            "PaymentId": payment_id
        }

        payload["Token"] = self._generate_token(payload)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/GetState",
                    json=payload
                )

                result = response.json()

                if result.get('Success'):
                    return {
                        "success": True,
                        "status": result.get('Status')
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('Message', 'Неизвестная ошибка')
                    }

        except Exception as e:
            logger.error(f"Status check error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_status_description(self, status: str) -> str:
        """Описание статуса платежа"""
        status_map = {
            'NEW': '🟡 Создан',
            'FORM_SHOWED': '🟡 Форма оплаты открыта',
            'DEADLINE_EXPIRED': '🔴 Время оплаты истекло',
            'CANCELED': '🔴 Отменен',
            'AUTHORIZING': '🟡 Авторизация',
            'AUTHORIZED': '🟡 Авторизован',
            'CONFIRMED': '✅ Подтвержден',
            'REJECTED': '🔴 Отклонен',
            'REFUNDED': '🟡 Возвращен',
            'COMPLETED': '✅ Завершен успешно'
        }

        return status_map.get(status, f"Статус: {status}")

    def is_success_status(self, status: str) -> bool:
        """Проверка успешного статуса платежа"""
        return status in ['CONFIRMED', 'COMPLETED']


def format_tariffs_message() -> str:
    """Форматирование сообщения с тарифами"""
    text = "💎 *Доступные тарифы подписки*\n\n"

    for key, tariff in TARIFFS.items():
        price_rub = tariff['price'] / 100
        text += f"{tariff['emoji']} *{tariff['label']}*\n"
        text += f"💰 *{price_rub:.0f} ₽* / {tariff['duration'].days} дней\n"
        text += f"📝 {tariff['description']}\n\n"

    return text


def format_subscription_message(subscription_data: Optional[Dict]) -> str:
    """Форматирование сообщения о подписке"""
    if not subscription_data:
        return (
            "❌ *У вас нет активной подписки*\n\n"
            "Для доступа ко всем функциям оформите подписку:\n"
            "👉 /subscribe - посмотреть тарифы\n\n"
            "🌟 *Преимущества подписки:*\n"
            "• Анализ фото еды\n"
            "• Персональные тренировки\n"
            "• Расширенная статистика\n"
            "• Приоритетная поддержка"
        )

    expires_str = subscription_data['expires_at'].strftime('%d.%m.%Y %H:%M')
    tariff_label = subscription_data['tariff_info'].get('label', 'Неизвестный')
    emoji = subscription_data['tariff_info'].get('emoji', '🏷️')

    return (
        f"{emoji} *Ваша подписка активна*\n\n"
        f"🏷️ Тариф: {tariff_label}\n"
        f"📅 Истекает: {expires_str}\n"
        f"⏳ Осталось дней: {subscription_data['days_left']}\n"
        f"🔄 Автопродление: {'Вкл' if subscription_data['auto_renew'] else 'Выкл'}\n\n"
        f"Чтобы продлить: /subscribe"
    )


@router.message(Command("subscribe", "tariffs", "buy"))
async def show_tariffs_handler(message: Message, state: FSMContext):
    """Показать тарифы подписки"""
    text = format_tariffs_message()

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_premium_inline_menu()
    )
    await state.set_state(PaymentStates.CHOOSING_TARIFF)


async def handle_payment_without_db(callback: CallbackQuery, state: FSMContext, tariff_key: str):
    """Обработка платежа без БД (для тестирования)"""
    tariff = TARIFFS[tariff_key]
    user_id = callback.from_user.id

    try:
        # Генерируем order_id
        timestamp = int(datetime.now().timestamp())
        order_id = f"test_{user_id}_{timestamp}"

        # Создаем платеж
        tinkoff_service = TinkoffPaymentService()
        payment_result = await tinkoff_service.create_payment(
            amount=tariff['price'],
            order_id=order_id,
            description=tariff['label'],
            user_id=user_id,
            email="test@test.com",
            phone="+70000000000"
        )

        if not payment_result.get('success'):
            await callback.message.answer(f"❌ Ошибка: {payment_result.get('error')}")
            return

        # Сохраняем в state
        await state.update_data(
            payment_id=payment_result['payment_id'],
            order_id=order_id,
            tariff_key=tariff_key,
            user_id=user_id
        )

        # Отправляем ссылку с красивой клавиатурой
        price_rub = tariff['price'] / 100
        if payment_result.get('payment_url'):
            await callback.message.answer(
                f"💳 *Оплата тарифа: {tariff['label']}*\n\n"
                f"💰 Сумма: *{price_rub:.0f} ₽*\n\n"
                f"Нажми кнопку ниже для перехода к оплате:",
                parse_mode="HTML",
                reply_markup=Navigation.get_payment_keyboard(payment_result['payment_url'])
            )
        else:
            await callback.message.answer(
                "❌ Не удалось создать ссылку для оплаты. Попробуйте позже.",
                reply_markup=Navigation.get_back_button()
            )

        await state.set_state(PaymentStates.WAITING_PAYMENT)

    except Exception as e:
        logger.error(f"Payment error: {e}")
        await callback.message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=Navigation.get_back_button()
        )

    await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def process_tariff_selection(callback: CallbackQuery, state: FSMContext, db=None):
    """Обработка выбора тарифа"""
    tariff_key = callback.data.replace("tariff_", "")

    if tariff_key not in TARIFFS:
        await callback.answer("❌ Неизвестный тариф", show_alert=True)
        return

    # Если БД не передана или TEST_MODE=True - используем упрощенный режим
    if TEST_MODE or db is None:
        logger.warning("⚠️ Тестовый режим без БД")
        await handle_payment_without_db(callback, state, tariff_key)
        return

    # Здесь код с БД (когда заработает)
    await callback.answer("⏳ Создаем платеж...")
    await callback.message.answer(
        "ℹ️ Полноценный режим с БД в разработке. Используется тестовый режим.",
        reply_markup=Navigation.get_back_button()
    )
    await handle_payment_without_db(callback, state, tariff_key)


@router.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: CallbackQuery, state: FSMContext, db=None):
    """Проверка статуса платежа (колбэк)"""
    data = await state.get_data()
    payment_id = data.get('payment_id')

    if not payment_id:
        await callback.message.answer(
            "📭 Нет активного платежа для проверки.",
            reply_markup=Navigation.get_back_button()
        )
        await callback.answer()
        return

    tinkoff_service = TinkoffPaymentService()

    try:
        status_result = await tinkoff_service.get_payment_status(payment_id)

        if not status_result.get('success'):
            await callback.message.answer(
                "❌ Не удалось проверить статус платежа. Попробуйте позже.",
                reply_markup=Navigation.get_back_button()
            )
            await callback.answer()
            return

        status = status_result.get('status')
        status_desc = tinkoff_service.get_status_description(status)

        text = f"📊 *Статус платежа:* {status_desc}\n\n"

        if tinkoff_service.is_success_status(status):
            text += "✅ Платеж успешно завершен!\n"
            text += "Спасибо за покупку!"
            await state.clear()
        elif status in ['CANCELED', 'REJECTED', 'AUTH_FAIL', 'DEADLINE_EXPIRED']:
            text += "❌ Платеж не прошел.\n"
            text += "Попробуйте снова: /subscribe"
            await state.clear()
        else:
            text += "🔄 Платеж обрабатывается.\n"
            text += "Проверьте статус позже."

        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_back_button()
        )

    except Exception as e:
        logger.error(f"Status check error: {e}")
        await callback.message.answer(
            "❌ Ошибка при проверке статуса платежа. Попробуйте позже.",
            reply_markup=Navigation.get_back_button()
        )

    await callback.answer()


@router.message(Command("check_payment"))
async def check_payment_status_handler(message: Message, state: FSMContext, db=None):
    """Проверка статуса платежа"""
    data = await state.get_data()
    payment_id = data.get('payment_id')

    if not payment_id:
        await message.answer(
            "📭 У вас нет активных платежей для проверки.\n"
            "Для оформления подписки: /subscribe",
            reply_markup=Navigation.get_main_menu()
        )
        return

    tinkoff_service = TinkoffPaymentService()

    try:
        status_result = await tinkoff_service.get_payment_status(payment_id)

        if not status_result.get('success'):
            await message.answer(
                "❌ Не удалось проверить статус платежа. Попробуйте позже.",
                reply_markup=Navigation.get_back_button()
            )
            return

        status = status_result.get('status')
        status_desc = tinkoff_service.get_status_description(status)

        text = f"📊 *Статус платежа:* {status_desc}\n\n"

        if tinkoff_service.is_success_status(status):
            text += "✅ Платеж успешно завершен!\n"
            text += "Спасибо за покупку!"
            await state.clear()
        elif status in ['CANCELED', 'REJECTED', 'AUTH_FAIL', 'DEADLINE_EXPIRED']:
            text += "❌ Платеж не прошел.\n"
            text += "Попробуйте снова: /subscribe"
            await state.clear()
        else:
            text += "🔄 Платеж обрабатывается.\n"
            text += "Проверьте статус позже."

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_back_button()
        )

    except Exception as e:
        logger.error(f"Status check error: {e}")
        await message.answer(
            "❌ Ошибка при проверке статуса платежа. Попробуйте позже.",
            reply_markup=Navigation.get_back_button()
        )


@router.message(Command("my_subscription", "mysub"))
async def show_my_subscription_handler(message: Message, db=None):
    """Показать информацию о подписке"""
    if TEST_MODE or db is None:
        await message.answer(
            "📋 *Информация о подписке*\n\n"
            "В тестовом режиме информация о подписке не сохраняется.\n"
            "После оплаты проверьте статус через /check_payment",
            parse_mode="HTML",
            reply_markup=Navigation.get_main_menu()
        )
        return

    # Здесь код с БД
    await message.answer(
        "ℹ️ Полноценный режим с БД в разработке.",
        reply_markup=Navigation.get_main_menu()
    )


@router.message(Command("payment_history", "payments"))
async def show_payment_history_handler(message: Message, db=None):
    """Показать историю платежей"""
    if TEST_MODE or db is None:
        await message.answer(
            "📭 В тестовом режиме история платежей не сохраняется.\n"
            "Оформите подписку: /subscribe",
            reply_markup=Navigation.get_main_menu()
        )
        return


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_callback(callback: CallbackQuery, state: FSMContext, db=None):
    """Отмена платежа (колбэк)"""
    await state.clear()
    await callback.message.answer(
        "✅ Платеж отменен.\n"
        "Для оформления новой подписки: /subscribe",
        reply_markup=Navigation.get_main_menu()
    )
    await callback.answer("Платеж отменен")


@router.callback_query(F.data == "premium_info")
async def premium_info_callback(callback: CallbackQuery):
    """Информация о премиум"""
    await callback.message.edit_text(
        "💎 *Что входит в премиум*\n\n"
        "• 📸 Анализ фото еды с помощью ИИ\n"
        "• 🏋️‍♂️ Персональные тренировки\n"
        "• 📊 Расширенная статистика прогресса\n"
        "• 🥗 Индивидуальные рекомендации по питанию\n"
        "• ♾️ Безлимитное количество запросов\n"
        "• ⚡ Приоритетная поддержка 24/7\n\n"
        "Выберите тариф:",
        parse_mode="HTML",
        reply_markup=Navigation.get_premium_inline_menu()
    )
    await callback.answer()


@router.message(Command("premium"))
async def premium_features_info_handler(message: Message, db=None):
    """Информация о премиум функциях"""
    text = (
        "💎 *Премиум функции*\n\n"
        "• 📸 Анализ фото еды с помощью ИИ\n"
        "• 🏋️‍♂️ Персональные тренировки\n"
        "• 📊 Расширенная статистика\n"
        "• 🥗 Индивидуальные рекомендации\n"
        "• ♾️ Безлимитные запросы\n\n"
        "👉 Оформите подписку: /subscribe"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_premium_inline_menu()
    )