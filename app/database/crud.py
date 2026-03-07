from sqlalchemy.future import select
from sqlalchemy import and_, update
from datetime import datetime, timedelta
import uuid
import logging

logger = logging.getLogger(__name__)

from app.database.models import User, Payment, UserTraining, Subscription, UserConsent


class UserCRUD:
    @staticmethod
    async def get_by_telegram_id(session, telegram_id: int):
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session, user_id: int):
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session, telegram_id: int, username: str = None, full_name: str = None):
        # Генерируем уникальный реферальный код
        referral_code = str(uuid.uuid4())[:8].upper()

        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            referral_code=referral_code,
            trial_started_at=datetime.utcnow()
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def create_user_with_referral(session, telegram_id: int, username: str = None,
                                        full_name: str = None, referral_code: str = None):
        """Создает пользователя с учетом реферального кода"""
        user = await UserCRUD.create(session, telegram_id, username, full_name)

        # Если есть реферальный код, обрабатываем
        if referral_code:
            await UserCRUD.process_referral(session, referral_code, user.id)

        return user

    # app/database/crud.py - только обновленный метод process_referral

    @staticmethod
    async def process_referral(session, referral_code: str, new_user_id: int):
        """Обрабатывает реферальный переход"""
        logger.info(f"🔄 Обработка реферального кода: {referral_code} для нового пользователя {new_user_id}")

        # Находим пользователя по реферальному коду
        result = await session.execute(
            select(User).where(User.referral_code == referral_code)
        )
        referrer = result.scalar_one_or_none()

        if referrer:
            logger.info(f"✅ Найден пригласивший: {referrer.id} с кодом {referral_code}")

            # Обновляем нового пользователя
            new_user = await UserCRUD.get_by_id(session, new_user_id)
            if new_user:
                new_user.referrer_id = referrer.id
                logger.info(f"✅ Новому пользователю {new_user_id} установлен referrer_id = {referrer.id}")

                # Начисляем бонус пригласившему (50 рублей)
                referrer.balance += 50.0
                logger.info(f"💰 Пригласившему {referrer.id} начислено 50 ₽. Новый баланс: {referrer.balance}")

                # Получаем количество рефералов
                referrals_result = await session.execute(
                    select(User).where(User.referrer_id == referrer.id)
                )
                referrals = referrals_result.scalars().all()
                referrals_count = len(referrals)
                logger.info(f"👥 У пользователя {referrer.id} теперь {referrals_count} рефералов")

                # Обновляем скидку пригласившего (5% за каждого, максимум 30%)
                new_discount = min(referrals_count * 5, 30)
                referrer.discount_percent = new_discount
                logger.info(f"🎁 Пригласившему {referrer.id} установлена скидка {new_discount}%")

                await session.commit()
                logger.info(f"✅ Реферал успешно обработан: {referrer.id} пригласил {new_user_id}")
                return referrer
        else:
            logger.warning(f"❌ Реферальный код {referral_code} не найден в базе")

        return None

    @staticmethod
    async def get_referrals_count(session, user_id: int) -> int:
        """Получает количество рефералов пользователя"""
        result = await session.execute(
            select(User).where(User.referrer_id == user_id)
        )
        referrals = result.scalars().all()
        return len(referrals)

    @staticmethod
    async def get_user_discount(session, user_id: int) -> int:
        """Получает текущую скидку пользователя"""
        user = await UserCRUD.get_by_id(session, user_id)
        return user.discount_percent if user else 0

    @staticmethod
    async def update_onboarding(session, user: User, **kwargs):
        """Обновить данные онбординга пользователя"""
        updated = False

        # Сохраняем telegram_id ДО обновления (чтобы использовать в логах)
        user_tg_id = user.telegram_id

        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                current_value = getattr(user, key)
                if current_value != value:
                    setattr(user, key, value)
                    updated = True
                    logger.debug(f"Обновлено поле {key}: {current_value} -> {value}")

        if updated:
            session.add(user)
            await session.commit()
            # ИСПОЛЬЗУЕМ сохраненный telegram_id
            logger.info(f"Данные пользователя {user_tg_id} обновлены")
        else:
            logger.debug(f"Нет изменений для пользователя {user_tg_id}")

        return user
    @staticmethod
    async def activate_subscription(session, user: User, period: str, discount: int = 0):
        """Активация подписки пользователя с учетом скидки"""
        period_days = {
            "1_month": 30,
            "3_months": 90,
            "6_months": 180
        }

        days = period_days.get(period, 30)

        if user.subscription_until and user.subscription_until > datetime.utcnow():
            # Продление существующей подписки
            user.subscription_until += timedelta(days=days)
        else:
            # Новая подписка
            user.subscription_until = datetime.utcnow() + timedelta(days=days)

        user.subscription_status = "active"
        await session.commit()
        return user

    @staticmethod
    async def get_referrals(session, user: User):
        result = await session.execute(
            select(User).where(User.referrer_id == user.id)
        )
        return result.scalars().all()

    @staticmethod
    async def add_balance(session, user: User, amount: float):
        """Добавление баланса пользователю"""
        user.balance += amount
        await session.commit()
        return user

    @staticmethod
    async def update_premium_status(session, user_id: int, is_premium: bool):
        """Обновление премиум статуса пользователя"""
        user = await UserCRUD.get_by_id(session, user_id)
        if user:
            user.is_premium = is_premium
            await session.commit()
        return user

    @staticmethod
    async def check_subscription_status(session, user: User) -> dict:
        """Проверка статуса подписки пользователя"""
        now = datetime.utcnow()

        result = {
            'has_access': False,
            'status': 'inactive',
            'days_left': 0,
            'message': ''
        }

        if user.subscription_until and user.subscription_until > now:
            result['has_access'] = True
            result['status'] = 'premium'
            result['days_left'] = (user.subscription_until - now).days
            result['message'] = f"⭐ Премиум подписка активна. Осталось {result['days_left']} дн."
            return result

        # Проверяем триал
        if user.trial_started_at:
            trial_end = user.trial_started_at + timedelta(days=3)
            if now < trial_end:
                result['has_access'] = True
                result['status'] = 'trial'
                result['days_left'] = (trial_end - now).days
                result['message'] = f"🆓 Бесплатный триал. Осталось {result['days_left']} дн."
                return result

        result['message'] = "❌ Нет активной подписки. Оформите подписку: /subscribe"
        return result

    @staticmethod
    async def increment_photo_count(session, user_id: int) -> bool:
        """Увеличить счетчик фото-анализов"""
        user = await UserCRUD.get_by_id(session, user_id)
        if user:
            user.photo_analyzes_count += 1
            user.last_photo_analysis_at = datetime.utcnow()
            await session.commit()
            return True
        return False

    # ===== НОВЫЕ МЕТОДЫ ДЛЯ ЮРИДИЧЕСКОЙ ЧАСТИ =====

    @staticmethod
    async def check_consent(session, telegram_id: int) -> bool:
        """Проверяет, дал ли пользователь согласие"""
        user = await UserCRUD.get_by_telegram_id(session, telegram_id)
        return user.consent_given if user else False

    @staticmethod
    async def record_consent(session, user_id: int, consent_type: str = "privacy_offer",
                             document_version: str = "1.0", ip_address: str = None,
                             user_agent: str = None):
        """Записывает факт согласия пользователя"""
        # Получаем пользователя
        user = await UserCRUD.get_by_id(session, user_id)
        if not user:
            return None

        # Обновляем поле в пользователе
        user.consent_given = True
        user.consent_date = datetime.utcnow()
        user.consent_ip = ip_address

        # Создаем запись в истории
        consent = UserConsent(
            user_id=user_id,
            consent_type=consent_type,
            document_version=document_version,
            accepted=True,
            accepted_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        session.add(consent)

        await session.commit()
        logger.info(f"Пользователь {user_id} принял условия ({consent_type})")
        return user

    @staticmethod
    async def get_consent_history(session, user_id: int):
        """Получает историю согласий пользователя"""
        result = await session.execute(
            select(UserConsent)
            .where(UserConsent.user_id == user_id)
            .order_by(UserConsent.accepted_at.desc())
        )
        return result.scalars().all()


class PaymentCRUD:
    @staticmethod
    async def create(session, user_id: int, amount: int, period: str, payment_id: str = None, discount: int = 0):
        payment = Payment(
            user_id=user_id,
            amount=amount,
            period=period,
            payment_id=payment_id,
            discount_applied=discount
        )

        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    @staticmethod
    async def update_status(session, payment_id: str, status: str):
        result = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        payment = result.scalar_one_or_none()

        if payment:
            payment.status = status
            await session.commit()

        return payment

    @staticmethod
    async def get_by_payment_id(session, payment_id: str):
        result = await session.execute(
            select(Payment).where(Payment.payment_id == payment_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_payments(session, user_id: int, limit: int = 10):
        result = await session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class SubscriptionCRUD:
    @staticmethod
    async def create_or_update(session, user_id: int, tariff: str, expires_at: datetime,
                               payment_id: str = None, is_active: bool = True):
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.tariff = tariff
            existing.expires_at = expires_at
            if payment_id:
                existing.payment_id = payment_id
            existing.is_active = is_active
            subscription = existing
        else:
            subscription = Subscription(
                user_id=user_id,
                tariff=tariff,
                expires_at=expires_at,
                payment_id=payment_id,
                is_active=is_active
            )
            session.add(subscription)

        await session.commit()
        await session.refresh(subscription)
        return subscription


class TrainingCRUD:
    @staticmethod
    async def log_training(session, user_id: int):
        training = UserTraining(user_id=user_id)
        session.add(training)
        await session.commit()
        return training