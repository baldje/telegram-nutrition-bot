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

# ===== БОЕВОЙ РЕЖИМ =====
TEST_MODE = False  # Режим тестирования вкл!


class PaymentStates(StatesGroup):
    """Состояния для процесса оплаты"""
    CHOOSING_TARIFF = State()
    WAITING_PAYMENT = State()


# Тарифы подписки (в копейках)
TARIFFS = {
    "test_week": {  # ТЕСТОВЫЙ ТАРИФ
        "price": 100,  # 1 рубль
        "duration": timedelta(days=7),
        "label": "🧪 Тестовый доступ (1 рубль)",
        "description": "Только для проверки платежей",
        "emoji": "🧪"
    },
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
        token = hashlib.sha256(values_string.encode('utf-8')).hexdigest()

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

        logger.info(f"📦 URL запроса: {self.api_url}/Init")
        logger.info(f"📦 Payload: {json.dumps(payload, ensure_ascii=False, default=str)}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/Init",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

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
    text = "💎 **Доступные тарифы подписки**\n\n"

    for key, tariff in TARIFFS.items():
        price_rub = tariff['price'] / 100
        text += f"{tariff['emoji']} *{tariff['label']}*\n"
        text += f"💰 *{price_rub:.0f} ₽* / {tariff['duration'].days} дней\n"
        text += f"📝 {tariff['description']}\n\n"

    return text


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


@router.callback_query(F.data == "pay_with_discount")
async def pay_with_discount_callback(callback: CallbackQuery, state: FSMContext, db=None):
    """Оплата со скидкой - показываем тарифы с применением скидки"""
    logger.info(f"💰 Оплата со скидкой вызвана пользователем {callback.from_user.id}")

    await callback.answer("⏳ Загружаем тарифы...")

    user_id = callback.from_user.id
    discount = 0

    # Получаем скидку пользователя из БД
    if db and not TEST_MODE:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, user_id)
            if user:
                discount = user.discount_percent or 0
                logger.info(f"🎁 Скидка пользователя {user_id}: {discount}%")
        except Exception as e:
            logger.error(f"Ошибка получения скидки: {e}")
    else:
        # В тестовом режиме используем тестовую скидку
        discount = 5
        logger.info(f"🎁 Тестовый режим: скидка {discount}%")

    # Формируем сообщение с тарифами и скидкой
    text = f"💎 **Оплата со скидкой {discount}%**\n\n"

    if discount > 0:
        text += "🎉 **Для вас доступны цены со скидкой:**\n\n"

        for key, tariff in TARIFFS.items():
            original_price = tariff['price'] / 100
            discounted_price = int(tariff['price'] * (100 - discount) / 100) / 100

            text += f"{tariff['emoji']} *{tariff['label']}*\n"
            text += f"   💰 ~~{original_price:.0f} ₽~~ → **{discounted_price:.0f} ₽**\n"
            text += f"   📝 {tariff['description']}\n\n"
    else:
        text += "У вас пока нет скидки. Приглашайте друзей и получайте скидку до 30%!\n\n"
        text += format_tariffs_message()

    # Создаем клавиатуру с тарифами
    builder = InlineKeyboardBuilder()

    if discount > 0:
        for key, tariff in TARIFFS.items():
            discounted_price = int(tariff['price'] * (100 - discount) / 100)
            price_rub = discounted_price / 100
            builder.row(InlineKeyboardButton(
                text=f"{tariff['emoji']} {tariff['label']} - {price_rub:.0f} ₽",
                callback_data=f"tariff_with_discount_{key}_{discount}"
            ))
    else:
        for key, tariff in TARIFFS.items():
            price_rub = tariff['price'] / 100
            builder.row(InlineKeyboardButton(
                text=f"{tariff['emoji']} {tariff['label']} - {price_rub:.0f} ₽",
                callback_data=f"tariff_{key}"
            ))

    builder.row(InlineKeyboardButton(text="🎁 Как получить скидку", callback_data="how_to_increase_discount"))
    builder.row(InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main"))

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

    await callback.answer()


async def handle_payment_without_db(callback: CallbackQuery, state: FSMContext, tariff_key: str, discount: int = 0, db=None):
    """Обработка платежа"""
    tariff = TARIFFS[tariff_key]
    user_id = callback.from_user.id

    # Рассчитываем цену со скидкой
    price = tariff['price']
    if discount > 0:
        price = int(price * (100 - discount) / 100)

    try:
        # Генерируем order_id
        timestamp = int(datetime.now().timestamp())
        order_id = f"{user_id}_{timestamp}"
        if discount > 0:
            order_id += f"_discount{discount}"

        # Создаем платеж
        tinkoff_service = TinkoffPaymentService()
        description = tariff['label']
        if discount > 0:
            description += f" (скидка {discount}%)"

        payment_result = await tinkoff_service.create_payment(
            amount=price,
            order_id=order_id,
            description=description,
            user_id=user_id,
            email="test@test.com",
            phone="+70000000000"
        )

        if not payment_result.get('success'):
            await callback.message.answer(f"❌ Ошибка: {payment_result.get('error')}")
            return

        # ===== СОХРАНЯЕМ ПЛАТЕЖ В БД =====
        if db and not TEST_MODE:
            try:
                # Сохраняем платеж в БД
                payment = await PaymentCRUD.create(
                    session=db.session,
                    user_id=user_id,
                    amount=price,
                    period=tariff_key,
                    payment_id=payment_result['payment_id'],
                    discount=discount
                )
                logger.info(f"💾 Платеж сохранен в БД: {payment_result['payment_id']}")
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения платежа: {e}")

        # Сохраняем в state
        await state.update_data(
            payment_id=payment_result['payment_id'],
            order_id=order_id,
            tariff_key=tariff_key,
            user_id=user_id,
            discount_applied=discount
        )

        # Отправляем ссылку с красивой клавиатурой
        price_rub = price / 100
        original_rub = tariff['price'] / 100

        if discount > 0:
            text = (
                f"💳 *Оплата со скидкой {discount}%*\n\n"
                f"📊 *Тариф:* {tariff['label']}\n"
                f"💰 ~~{original_rub:.0f} ₽~~ → **{price_rub:.0f} ₽**\n"
                f"🎁 **Вы сэкономили: {original_rub - price_rub:.0f} ₽**\n\n"
                f"Нажми кнопку ниже для перехода к оплате:"
            )
        else:
            text = (
                f"💳 *Оплата тарифа: {tariff['label']}*\n\n"
                f"💰 Сумма: *{price_rub:.0f} ₽*\n\n"
                f"Нажми кнопку ниже для перехода к оплате:"
            )

        if payment_result.get('payment_url'):
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=Navigation.get_payment_keyboard(payment_result['payment_url'], discount)
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


@router.callback_query(F.data.startswith("tariff_with_discount_"))
async def process_tariff_with_discount(callback: CallbackQuery, state: FSMContext, db=None):
    """Обработка выбора тарифа со скидкой"""
    # Формат: tariff_with_discount_month_5
    parts = callback.data.split('_')

    # Определяем ключ тарифа
    if "3months" in callback.data:
        tariff_key = "3months"
        discount = int(parts[-1])
    elif "year" in callback.data:
        tariff_key = "year"
        discount = int(parts[-1])
    else:
        tariff_key = "month"
        discount = int(parts[-1])

    logger.info(f"💰 Выбран тариф {tariff_key} со скидкой {discount}% пользователем {callback.from_user.id}")

    if tariff_key not in TARIFFS:
        await callback.answer("❌ Неизвестный тариф", show_alert=True)
        return

    await callback.answer("⏳ Создаем платеж...")
    await handle_payment_without_db(callback, state, tariff_key, discount)


@router.callback_query(F.data.startswith("tariff_"))
async def process_tariff_selection(callback: CallbackQuery, state: FSMContext, db=None):
    """Обработка выбора тарифа (без скидки)"""
    tariff_key = callback.data.replace("tariff_", "")

    if tariff_key not in TARIFFS:
        await callback.answer("❌ Неизвестный тариф", show_alert=True)
        return

    await callback.answer("⏳ Создаем платеж...")
    await handle_payment_without_db(callback, state, tariff_key, 0)


@router.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: CallbackQuery, state: FSMContext, db=None):
    """Проверка статуса платежа (колбэк)"""
    data = await state.get_data()
    payment_id = data.get('payment_id')
    tariff_key = data.get('tariff_key')
    discount_applied = data.get('discount_applied', 0)

    if not payment_id:
        await callback.message.answer(
            "📭 Нет активного платежа для проверки.",
            reply_markup=Navigation.get_back_button()
        )
        await callback.answer()
        return

    tinkoff_service = TinkoffPaymentService()
    await callback.answer("⏳ Проверяем статус платежа...")

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
            # Платеж успешен - активируем подписку
            text += "✅ Платеж успешно завершен!\n\n"

            if tariff_key and tariff_key in TARIFFS:
                tariff = TARIFFS[tariff_key]

                # ===== АКТИВИРУЕМ ПОДПИСКУ В БД =====
                if db and not TEST_MODE:
                    try:
                        # Обновляем статус платежа
                        await PaymentCRUD.update_status(
                            session=db.session,
                            payment_id=payment_id,
                            status="completed"
                        )

                        # Активируем подписку пользователя
                        user = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
                        if user:
                            # Устанавливаем дату окончания подписки
                            if user.subscription_until and user.subscription_until > datetime.utcnow():
                                # Если уже есть активная подписка, продлеваем
                                user.subscription_until += tariff['duration']
                            else:
                                # Новая подписка
                                user.subscription_until = datetime.utcnow() + tariff['duration']

                            user.subscription_status = "active"
                            await db.session.commit()

                            # Обновляем подписку в таблице subscriptions
                            await SubscriptionCRUD.create_or_update(
                                session=db.session,
                                user_id=user.id,
                                tariff=tariff_key,
                                expires_at=user.subscription_until,
                                payment_id=payment_id,
                                is_active=True
                            )

                            text += f"🎉 *Подписка активирована!*\n"
                            text += f"📅 Тариф: {tariff['label']}\n"
                            text += f"⏳ Действует до: {user.subscription_until.strftime('%d.%m.%Y')}\n\n"
                            text += "Спасибо за покупку!"

                            logger.info(f"✅ Подписка активирована для пользователя {callback.from_user.id}")
                        else:
                            text += "❌ Пользователь не найден в БД."
                    except Exception as e:
                        logger.error(f"Ошибка активации подписки: {e}")
                        text += "❌ Ошибка активации подписки. Обратитесь в поддержку."
                else:
                    text += "⚠️ *Тестовый режим*\n"
                    text += "В тестовом режиме подписка не активируется в БД.\n"
                    text += f"Тариф: {tariff['label']} на {tariff['duration'].days} дней"

                await state.clear()
            else:
                text += "Тариф не найден. Обратитесь в поддержку."

        elif status in ['CANCELED', 'REJECTED', 'DEADLINE_EXPIRED']:
            text += "❌ Платеж не прошел.\n"
            text += "Попробуйте снова: /subscribe"
            await state.clear()
        else:
            text += "🔄 Платеж еще обрабатывается.\n"
            text += "Попробуйте проверить позже или нажмите кнопку еще раз."

        # Отправляем сообщение
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_back_button()
        )

        # Если платеж успешен, можно также удалить предыдущее сообщение
        if tinkoff_service.is_success_status(status):
            try:
                await callback.message.delete()
            except:
                pass

    except Exception as e:
        logger.error(f"Status check error: {e}")
        await callback.message.answer(
            "❌ Ошибка при проверке статуса платежа. Попробуйте позже.",
            reply_markup=Navigation.get_back_button()
        )

    await callback.answer()


@router.message(Command("check_payment"))
async def check_payment_status_handler(message: Message, state: FSMContext, db=None):
    """Проверка статуса платежа по команде"""
    data = await state.get_data()
    payment_id = data.get('payment_id')
    tariff_key = data.get('tariff_key')
    discount_applied = data.get('discount_applied', 0)

    if not payment_id:
        await message.answer(
            "📭 У вас нет активных платежей для проверки.\n"
            "Для оформления подписки: /subscribe",
            reply_markup=Navigation.get_main_menu()
        )
        return

    tinkoff_service = TinkoffPaymentService()
    await message.answer("⏳ Проверяем статус платежа...")

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
            text += "✅ Платеж успешно завершен!\n\n"

            if tariff_key and tariff_key in TARIFFS:
                tariff = TARIFFS[tariff_key]

                # ===== АКТИВИРУЕМ ПОДПИСКУ В БД =====
                if db and not TEST_MODE:
                    try:
                        # Обновляем статус платежа
                        await PaymentCRUD.update_status(
                            session=db.session,
                            payment_id=payment_id,
                            status="completed"
                        )

                        # Активируем подписку пользователя
                        user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
                        if user:
                            # Устанавливаем дату окончания подписки
                            if user.subscription_until and user.subscription_until > datetime.utcnow():
                                # Если уже есть активная подписка, продлеваем
                                user.subscription_until += tariff['duration']
                            else:
                                # Новая подписка
                                user.subscription_until = datetime.utcnow() + tariff['duration']

                            user.subscription_status = "active"
                            await db.session.commit()

                            # Обновляем подписку в таблице subscriptions
                            await SubscriptionCRUD.create_or_update(
                                session=db.session,
                                user_id=user.id,
                                tariff=tariff_key,
                                expires_at=user.subscription_until,
                                payment_id=payment_id,
                                is_active=True
                            )

                            text += f"🎉 *Подписка активирована!*\n"
                            text += f"📅 Тариф: {tariff['label']}\n"
                            text += f"⏳ Действует до: {user.subscription_until.strftime('%d.%m.%Y')}\n\n"
                            text += "Спасибо за покупку!"

                            logger.info(f"✅ Подписка активирована для пользователя {message.from_user.id}")
                        else:
                            text += "❌ Пользователь не найден в БД."
                    except Exception as e:
                        logger.error(f"Ошибка активации подписки: {e}")
                        text += "❌ Ошибка активации подписки. Обратитесь в поддержку."
                else:
                    text += "⚠️ *Тестовый режим*\n"
                    text += "В тестовом режиме подписка не активируется в БД.\n"
                    text += f"Тариф: {tariff['label']} на {tariff['duration'].days} дней"

                await state.clear()
            else:
                text += "Тариф не найден. Обратитесь в поддержку"
        elif status in ['CANCELED', 'REJECTED', 'DEADLINE_EXPIRED']:
            text += "❌ Платеж не прошел.\n"
            text += "Попробуйте снова: /subscribe"
            await state.clear()
        else:
            text += "🔄 Платеж еще обрабатывается.\n"
            text += "Попробуйте проверить позже или нажмите /check_payment еще раз."

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_main_menu()
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

    try:
        user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
        if not user:
            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=Navigation.get_main_menu()
            )
            return

        if user.subscription_until and user.subscription_until > datetime.utcnow():
            days_left = (user.subscription_until - datetime.utcnow()).days
            text = (
                f"✅ *У вас активна подписка*\n\n"
                f"📅 Действует до: {user.subscription_until.strftime('%d.%m.%Y')}\n"
                f"⏳ Осталось дней: {days_left}\n"
                f"💰 Баланс: {user.balance or 0} ₽\n"
                f"🎁 Скидка: {user.discount_percent or 0}%"
            )
        else:
            text = (
                f"❌ *Нет активной подписки*\n\n"
                f"💰 Баланс: {user.balance or 0} ₽\n"
                f"🎁 Скидка: {user.discount_percent or 0}%\n\n"
                f"Оформите подписку: /subscribe"
            )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=Navigation.get_main_menu()
        )

    except Exception as e:
        logger.error(f"Ошибка получения информации о подписке: {e}")
        await message.answer(
            "❌ Ошибка получения информации.",
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

    # Если есть БД, показываем историю платежей пользователя
    try:
        payments = await PaymentCRUD.get_user_payments(db.session, message.from_user.id)
        if not payments:
            await message.answer(
                "📭 У вас пока нет платежей.",
                reply_markup=Navigation.get_main_menu()
            )
            return

        text = "📊 *История платежей*\n\n"
        for p in payments:
            status_emoji = "✅" if p.status == "completed" else "⏳" if p.status == "pending" else "❌"
            text += f"{status_emoji} {p.created_at.strftime('%d.%m.%Y')}: {p.amount / 100} ₽ ({p.period})\n"

        await message.answer(text, parse_mode="HTML", reply_markup=Navigation.get_main_menu())
    except Exception as e:
        logger.error(f"Ошибка получения истории платежей: {e}")
        await message.answer(
            "❌ Ошибка получения истории.",
            reply_markup=Navigation.get_main_menu()
        )


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
        "• 📊 Расширенная статистика\n\n"
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
        "• 📊 Расширенная статистика\n\n"
        "👉 Оформите подписку: /subscribe"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=Navigation.get_premium_inline_menu()
    )
