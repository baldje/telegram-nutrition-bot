# services/payment_service.py
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import httpx
import qrcode
from io import BytesIO

from app.database.crud import PaymentCRUD
from utils.config import settings

logger = logging.getLogger(__name__)


class TinkoffPaymentService:
    """Сервис для работы с Тинькофф эквайрингом"""

    def __init__(self):
        self.terminal_key = settings.TINKOFF_TERMINAL_KEY
        self.secret_key = settings.TINKOFF_SECRET_KEY
        self.api_url = settings.TINKOFF_API_URL.rstrip('/')
        self.success_url = settings.PAYMENT_SUCCESS_URL
        self.fail_url = settings.PAYMENT_FAILURE_URL

    def _generate_token(self, data: dict) -> str:
        """Генерация токена для подписи запроса"""
        # Создаем копию и удаляем Token если есть
        data_copy = {k: v for k, v in data.items() if k != 'Token' and v is not None}

        # Сортируем ключи в алфавитном порядке
        sorted_data = dict(sorted(data_copy.items()))

        # Формируем строку значений
        values = []
        for key, value in sorted_data.items():
            if isinstance(value, dict):
                # Рекурсивно обрабатываем вложенные словари
                sorted_nested = dict(sorted(value.items()))
                nested_values = [str(v) for v in sorted_nested.values()]
                values.append(''.join(nested_values))
            elif isinstance(value, list):
                # Обрабатываем списки
                for item in value:
                    if isinstance(item, dict):
                        sorted_item = dict(sorted(item.items()))
                        item_values = [str(v) for v in sorted_item.values()]
                        values.append(''.join(item_values))
                    else:
                        values.append(str(item))
            else:
                values.append(str(value))

        # Добавляем секретный ключ
        values.append(self.secret_key)

        # Объединяем все значения
        token_string = ''.join(values)

        # Хэшируем SHA256
        return hashlib.sha256(token_string.encode()).hexdigest()

    async def create_payment(
            self,
            amount: int,  # в копейках
            order_id: str,
            description: str,
            user_id: int,
            email: Optional[str] = None,
            phone: Optional[str] = None,
            notification_url: Optional[str] = None,
            receipt_items: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Создание платежа в Тинькофф"""

        # Формируем данные для чека
        receipt = None
        if email or phone:
            if not receipt_items:
                receipt_items = [{
                    "Name": description[:64],
                    "Price": amount,
                    "Quantity": 1,
                    "Amount": amount,
                    "Tax": "none"
                }]

            receipt = {
                "Email": email,
                "Phone": phone,
                "Taxation": "osn",
                "Items": receipt_items
            }

        # Основные параметры платежа
        payload = {
            "TerminalKey": self.terminal_key,
            "Amount": amount,
            "OrderId": order_id,
            "Description": description,
            "CustomerKey": str(user_id),
            "SuccessURL": self.success_url,
            "FailURL": self.fail_url,
            "NotificationURL": notification_url,
            "Receipt": receipt
        }

        # Удаляем пустые значения
        payload = {k: v for k, v in payload.items() if v is not None}

        # Генерируем токен
        payload["Token"] = self._generate_token(payload)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.debug(f"Sending payment request: {json.dumps(payload, ensure_ascii=False)}")

                response = await client.post(
                    f"{self.api_url}/Init",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                )

                response.raise_for_status()
                result = response.json()

                logger.debug(f"Payment response: {json.dumps(result, ensure_ascii=False)}")

                if result.get('Success'):
                    logger.info(f"Payment created successfully: OrderId={order_id}, Amount={amount}")
                    return {
                        "success": True,
                        "payment_id": result['PaymentId'],
                        "status": result['Status'],
                        "payment_url": result.get('PaymentURL'),
                        "order_id": result.get('OrderId'),
                        "amount": result.get('Amount'),
                        "original_response": result
                    }
                else:
                    error_msg = result.get('Message', 'Неизвестная ошибка')
                    error_details = result.get('Details', '')
                    logger.error(f"Payment creation failed: {error_msg} - {error_details}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "details": error_details,
                        "original_response": result
                    }

        except httpx.RequestError as e:
            logger.error(f"Network error during payment creation: {e}")
            return {
                "success": False,
                "error": "Ошибка сети",
                "details": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error during payment creation: {e}")
            return {
                "success": False,
                "error": "Неожиданная ошибка",
                "details": str(e)
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

                response.raise_for_status()
                result = response.json()

                if result.get('Success'):
                    return {
                        "success": True,
                        "status": result.get('Status'),
                        "order_id": result.get('OrderId'),
                        "amount": result.get('Amount'),
                        "original_response": result
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('Message', 'Неизвестная ошибка'),
                        "original_response": result
                    }

        except Exception as e:
            logger.error(f"Error checking payment status: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def cancel_payment(
            self,
            payment_id: str,
            amount: Optional[int] = None
    ) -> Dict[str, Any]:
        """Отмена платежа"""
        payload = {
            "TerminalKey": self.terminal_key,
            "PaymentId": payment_id
        }

        if amount:
            payload["Amount"] = amount

        payload["Token"] = self._generate_token(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/Cancel",
                    json=payload
                )

                result = response.json()

                if result.get('Success'):
                    return {
                        "success": True,
                        "status": result.get('Status'),
                        "original_response": result
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('Message', 'Неизвестная ошибка'),
                        "original_response": result
                    }

        except Exception as e:
            logger.error(f"Error canceling payment: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def confirm_payment(self, payment_id: str) -> Dict[str, Any]:
        """Подтверждение платежа (для двухстадийных платежей)"""
        payload = {
            "TerminalKey": self.terminal_key,
            "PaymentId": payment_id
        }

        payload["Token"] = self._generate_token(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/Confirm",
                    json=payload
                )

                result = response.json()

                if result.get('Success'):
                    return {
                        "success": True,
                        "status": result.get('Status'),
                        "original_response": result
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('Message', 'Неизвестная ошибка'),
                        "original_response": result
                    }

        except Exception as e:
            logger.error(f"Error confirming payment: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def generate_qr_code(self, payment_url: str) -> BytesIO:
        """Генерация QR-кода для оплаты"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(payment_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            bio = BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)

            return bio
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            raise

    def get_status_description(self, status: str) -> str:
        """Описание статуса платежа"""
        status_map = {
            'NEW': '🟡 Создан',
            'FORM_SHOWED': '🟡 Форма оплаты открыта',
            'DEADLINE_EXPIRED': '🔴 Время оплаты истекло',
            'CANCELED': '🔴 Отменен',
            'PREAUTHORIZING': '🟡 Обрабатывается',
            'AUTHORIZING': '🟡 Авторизация',
            'AUTHORIZED': '🟡 Авторизован',
            'AUTH_FAIL': '🔴 Ошибка авторизации',
            'REJECTED': '🔴 Отклонен',
            '3DS_CHECKING': '🟡 Проверка 3D Secure',
            '3DS_CHECKED': '🟡 3D Secure проверен',
            'REVERSING': '🟡 Возврат',
            'REVERSED': '🟡 Возвращен',
            'CONFIRMING': '🟡 Подтверждение',
            'CONFIRMED': '✅ Подтвержден',
            'REFUNDING': '🟡 Возврат средств',
            'PARTIAL_REFUNDED': '🟡 Частичный возврат',
            'REFUNDED': '🟡 Средства возвращены',
            'COMPLETED': '✅ Завершен успешно'
        }

        return status_map.get(status, f"Статус: {status}")

    def is_success_status(self, status: str) -> bool:
        """Проверка успешного статуса платежа"""
        return status in ['CONFIRMED', 'COMPLETED']

    def is_failure_status(self, status: str) -> bool:
        """Проверка неудачного статуса платежа"""
        return status in ['CANCELED', 'REJECTED', 'AUTH_FAIL', 'DEADLINE_EXPIRED']


class SubscriptionService:
    """Сервис для управления подписками"""

    TARIFFS = {
        "month": {
            "price": settings.TARIFF_MONTH,  # в копейках
            "duration": timedelta(days=30),
            "label": "Месячная подписка",
            "description": "Полный доступ на 1 месяц",
            "emoji": "📅"
        },
        "3months": {
            "price": settings.TARIFF_3MONTHS,
            "duration": timedelta(days=90),
            "label": "3 месяца подписки",
            "description": "Выгодный тариф на 3 месяца",
            "emoji": "📊"
        },
        "year": {
            "price": settings.TARIFF_YEAR,
            "duration": timedelta(days=365),
            "label": "Годовая подписка",
            "description": "Подписка на целый год со скидкой",
            "emoji": "🏆"
        }
    }

    def __init__(self, db_session):
        self.db_session = db_session
        self.crud = PaymentCRUD(db_session)
        self.tinkoff_service = TinkoffPaymentService()

    async def create_subscription_payment(
            self,
            user_id: int,
            tariff_key: str,
            user_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Создание платежа для подписки"""

        if tariff_key not in self.TARIFFS:
            raise ValueError(f"Неизвестный тариф: {tariff_key}")

        tariff = self.TARIFFS[tariff_key]

        # Генерируем уникальный order_id
        timestamp = int(datetime.now().timestamp())
        order_id = f"sub_{user_id}_{timestamp}"

        # Получаем данные пользователя для чека
        email = phone = None
        if user_data:
            email = user_data.get('email')
            phone = user_data.get('phone')

        # Описание для платежа
        description = f"Подписка: {tariff['label']}"

        # Создаем платеж в Тинькофф
        payment_result = await self.tinkoff_service.create_payment(
            amount=tariff['price'],
            order_id=order_id,
            description=description,
            user_id=user_id,
            email=email,
            phone=phone
        )

        if not payment_result.get('success'):
            error_msg = payment_result.get('error', 'Неизвестная ошибка')
            raise Exception(f"Ошибка создания платежа: {error_msg}")

        return {
            "success": True,
            "payment_id": payment_result['payment_id'],
            "order_id": order_id,
            "amount": tariff['price'],
            "amount_rub": tariff['price'] / 100,
            "tariff": tariff_key,
            "payment_url": payment_result.get('payment_url'),
            "status": payment_result.get('status'),
            "tariff_info": tariff,
            "original_response": payment_result
        }

    async def activate_subscription(
            self,
            user_id: int,
            tariff_key: str,
            payment_id: str
    ) -> Dict[str, Any]:
        """Активация подписки после успешной оплаты"""

        if tariff_key not in self.TARIFFS:
            return {
                "success": False,
                "error": f"Неизвестный тариф: {tariff_key}"
            }

        tariff = self.TARIFFS[tariff_key]

        try:
            # Получаем текущую подписку пользователя
            current_sub = await self.crud.get_user_subscription(user_id)

            # Рассчитываем дату окончания
            now = datetime.utcnow()
            if current_sub and current_sub.is_valid():
                # Продление существующей подписки
                expires_at = current_sub.expires_at + tariff['duration']
            else:
                # Новая подписка
                expires_at = now + tariff['duration']

            # Создаем или обновляем подписку
            subscription = await self.crud.create_or_update_subscription(
                user_id=user_id,
                tariff=tariff_key,
                expires_at=expires_at,
                payment_id=payment_id,
                is_active=True
            )

            logger.info(f"Subscription activated: user={user_id}, tariff={tariff_key}, expires={expires_at}")

            return {
                "success": True,
                "subscription_id": subscription.id,
                "tariff": tariff_key,
                "expires_at": expires_at,
                "days_left": (expires_at - now).days
            }

        except Exception as e:
            logger.error(f"Failed to activate subscription: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def check_user_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Проверка активной подписки пользователя"""
        try:
            subscription = await self.crud.get_user_subscription(user_id)

            if not subscription or not subscription.is_active:
                return None

            # Проверяем не истекла ли подписка
            now = datetime.utcnow()
            if subscription.expires_at <= now:
                # Деактивируем истекшую подписку
                await self.crud.deactivate_subscription(user_id)
                return None

            tariff_info = self.TARIFFS.get(subscription.tariff, {})

            return {
                "subscription_id": subscription.id,
                "tariff": subscription.tariff,
                "expires_at": subscription.expires_at,
                "created_at": subscription.created_at,
                "days_left": (subscription.expires_at - now).days,
                "is_active": subscription.is_active,
                "auto_renew": subscription.auto_renew,
                "tariff_info": tariff_info
            }

        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return None

    async def has_active_subscription(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная подписка"""
        subscription_data = await self.check_user_subscription(user_id)
        return subscription_data is not None

    def format_subscription_message(self, subscription_data: Optional[Dict]) -> str:
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

    def format_tariffs_message(self) -> str:
        """Форматирование сообщения с тарифами"""
        text = "💎 *Доступные тарифы подписки*\n\n"

        for key, tariff in self.TARIFFS.items():
            price_rub = tariff['price'] / 100
            text += f"{tariff['emoji']} *{tariff['label']}*\n"
            text += f"💰 *{price_rub:.0f} ₽* / {tariff['duration'].days} дней\n"
            text += f"📝 {tariff['description']}\n\n"

        text += "👇 Выберите тариф для оплаты:"

        return text

    async def process_webhook_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка уведомления от Тинькофф (вебхук)"""
        try:
            payment_id = notification_data.get('PaymentId')
            status = notification_data.get('Status')
            order_id = notification_data.get('OrderId')

            if not payment_id or not status:
                return {"success": False, "error": "Invalid notification data"}

            logger.info(f"Processing webhook: payment_id={payment_id}, status={status}")

            # Получаем платеж из БД
            payment = await self.crud.get_payment(payment_id)

            if not payment:
                logger.warning(f"Payment not found in DB: {payment_id}")
                return {"success": False, "error": "Payment not found"}

            # Обновляем статус платежа в БД
            await self.crud.update_payment_status(
                payment_id=payment_id,
                status=status,
                additional_data=notification_data
            )

            # Если платеж успешен - активируем подписку
            if self.tinkoff_service.is_success_status(status):
                activation_result = await self.activate_subscription(
                    user_id=payment.user_id,
                    tariff_key=payment.tariff,
                    payment_id=payment_id
                )

                if activation_result['success']:
                    logger.info(f"Subscription activated via webhook: user={payment.user_id}")
                    return {
                        "success": True,
                        "action": "subscription_activated",
                        "user_id": payment.user_id
                    }
                else:
                    logger.error(f"Failed to activate subscription via webhook: {activation_result['error']}")
                    return {
                        "success": False,
                        "error": activation_result['error']
                    }

            return {
                "success": True,
                "action": "status_updated",
                "status": status
            }

        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def get_payment_info(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о платеже"""
        payment = await self.crud.get_payment(payment_id)

        if not payment:
            return None

        # Получаем актуальный статус из Тинькофф
        status_result = await self.tinkoff_service.get_payment_status(payment_id)

        return {
            "payment_id": payment.payment_id,
            "order_id": payment.order_id,
            "user_id": payment.user_id,
            "amount": payment.amount,
            "tariff": payment.tariff,
            "status": status_result.get('status', payment.status) if status_result['success'] else payment.status,
            "payment_url": payment.payment_url,
            "description": payment.description,
            "created_at": payment.created_at,
            "updated_at": payment.updated_at
        }