from sqlalchemy.future import select
from sqlalchemy import and_, update
from datetime import datetime, timedelta, date
import uuid
import logging

logger = logging.getLogger(__name__)

from app.database.models import (
    User, Payment, UserTraining, Subscription, UserConsent,
    FoodDiary, DailySummary  # 👈 ДОБАВЛЕНЫ FoodDiary и DailySummary
)


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

    # ===== МЕТОДЫ ДЛЯ ЮРИДИЧЕСКОЙ ЧАСТИ =====

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


class FoodDiaryCRUD:
    """CRUD операции для дневника питания"""

    @staticmethod
    async def add_entry(session, user_id: int, meal_type: str, description: str,
                        analysis: dict, photo_file_id: str = None):
        """Добавить запись о приеме пищи"""
        entry = FoodDiary(
            user_id=user_id,
            meal_type=meal_type,
            description=description,
            calories=analysis.get('estimated_calories'),
            protein=analysis.get('protein_grams'),
            fat=analysis.get('fat_grams'),
            carbs=analysis.get('carbs_grams'),
            photo_file_id=photo_file_id
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        # Обновить или создать дневную сводку
        await FoodDiaryCRUD.update_daily_summary(session, user_id, entry.meal_date)

        return entry

    @staticmethod
    async def get_day_entries(session, user_id: int, date: datetime.date):
        """Получить все записи за день"""
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())

        result = await session.execute(
            select(FoodDiary)
            .where(FoodDiary.user_id == user_id)
            .where(FoodDiary.meal_date >= start_of_day)
            .where(FoodDiary.meal_date <= end_of_day)
            .order_by(FoodDiary.meal_date)
        )
        return result.scalars().all()

    @staticmethod
    async def get_week_entries(session, user_id: int):
        """Получить записи за последние 7 дней"""
        week_ago = datetime.utcnow() - timedelta(days=7)

        result = await session.execute(
            select(FoodDiary)
            .where(FoodDiary.user_id == user_id)
            .where(FoodDiary.meal_date >= week_ago)
            .order_by(FoodDiary.meal_date.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def update_daily_summary(session, user_id: int, date: datetime):
        """Обновить дневную сводку"""
        date_only = date.date()
        entries = await FoodDiaryCRUD.get_day_entries(session, user_id, date_only)

        # Рассчитываем суммы
        total_calories = sum(e.calories or 0 for e in entries)
        total_protein = sum(e.protein or 0 for e in entries)
        total_fat = sum(e.fat or 0 for e in entries)
        total_carbs = sum(e.carbs or 0 for e in entries)

        # Ищем существующую сводку
        result = await session.execute(
            select(DailySummary)
            .where(DailySummary.user_id == user_id)
            .where(DailySummary.summary_date == date_only)
        )
        summary = result.scalar_one_or_none()

        if summary:
            # Обновляем существующую
            summary.total_calories = total_calories
            summary.total_protein = total_protein
            summary.total_fat = total_fat
            summary.total_carbs = total_carbs
            summary.meals_count = len(entries)
        else:
            # Создаем новую
            summary = DailySummary(
                user_id=user_id,
                summary_date=date_only,
                total_calories=total_calories,
                total_protein=total_protein,
                total_fat=total_fat,
                total_carbs=total_carbs,
                meals_count=len(entries)
            )
            session.add(summary)

        await session.commit()
        return summary


class NutritionCalculator:
    """Калькулятор питания на основе данных пользователя"""

    # Коэффициенты активности
    ACTIVITY_FACTORS = {
        'low': 1.2,  # Сидячий образ жизни
        'medium': 1.375,  # Умеренная активность
        'high': 1.55,  # Высокая активность
        'very_high': 1.725  # Спортсмены
    }

    # Коэффициенты для целей
    GOAL_FACTORS = {
        'похудение': {
            'calories': 0.85,  # -15% от нормы
            'protein': 1.8,  # г на кг веса
            'fat': 0.8,  # г на кг веса
            'carbs': 2.0  # г на кг веса
        },
        'набор массы': {
            'calories': 1.15,  # +15% к норме
            'protein': 2.0,
            'fat': 1.0,
            'carbs': 3.5
        },
        'поддержание': {
            'calories': 1.0,
            'protein': 1.6,
            'fat': 0.9,
            'carbs': 2.5
        },
        'рельеф': {
            'calories': 0.9,  # -10% от нормы
            'protein': 2.2,  # Больше белка
            'fat': 0.7,
            'carbs': 2.2
        },
        'здоровье': {
            'calories': 1.0,
            'protein': 1.6,
            'fat': 0.9,
            'carbs': 2.5
        }
    }

    # Распределение калорий по приемам пищи (%)
    MEAL_DISTRIBUTION = {
        'breakfast': 0.25,  # 25% - завтрак
        'lunch': 0.35,  # 35% - обед
        'dinner': 0.30,  # 30% - ужин
        'snack': 0.10  # 10% - перекусы
    }

    @staticmethod
    def calculate_bmr(user) -> float:
        """
        Расчет базового метаболизма (BMR) по формуле Миффлина-Сан Жеора
        """
        weight = user.weight or 70
        height = user.height or 170
        age = user.age or 30

        if user.gender == 'мужской':
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        return bmr

    @staticmethod
    def calculate_tdee(user) -> float:
        """
        Расчет общей суточной потребности в калориях (TDEE)
        с учетом активности (по умолчанию средняя)
        """
        bmr = NutritionCalculator.calculate_bmr(user)

        # По умолчанию средняя активность
        activity = getattr(user, 'activity_level', 'medium')
        factor = NutritionCalculator.ACTIVITY_FACTORS.get(activity, 1.375)

        return bmr * factor

    @staticmethod
    def get_daily_nutrition(user) -> dict:
        """
        Расчет суточной нормы КБЖУ с учетом цели
        """
        tdee = NutritionCalculator.calculate_tdee(user)
        goal = user.goal or 'поддержание'

        # Получаем коэффициенты для цели
        goal_factor = NutritionCalculator.GOAL_FACTORS.get(goal, NutritionCalculator.GOAL_FACTORS['поддержание'])

        # Рассчитываем калории
        daily_calories = int(tdee * goal_factor['calories'])

        # Рассчитываем БЖУ в граммах
        weight = user.weight or 70

        protein = int(weight * goal_factor['protein'])
        fat = int(weight * goal_factor['fat'])

        # Углеводы рассчитываем из оставшихся калорий
        protein_calories = protein * 4
        fat_calories = fat * 9
        remaining_calories = daily_calories - protein_calories - fat_calories
        carbs = int(remaining_calories / 4)

        # Проверяем минимальные значения
        protein = max(protein, 50)
        fat = max(fat, 30)
        carbs = max(carbs, 100)

        return {
            'calories': daily_calories,
            'protein': protein,
            'fat': fat,
            'carbs': carbs,
            'goal': goal,
            'tdee': int(tdee),
            'bmr': int(NutritionCalculator.calculate_bmr(user))
        }

    @staticmethod
    def get_meal_nutrition(user, meal_type: str) -> dict:
        """
        Расчет нормы для конкретного приема пищи
        """
        daily = NutritionCalculator.get_daily_nutrition(user)
        distribution = NutritionCalculator.MEAL_DISTRIBUTION.get(meal_type, 0.25)

        return {
            'calories': int(daily['calories'] * distribution),
            'protein': int(daily['protein'] * distribution),
            'fat': int(daily['fat'] * distribution),
            'carbs': int(daily['carbs'] * distribution),
            'meal_type': meal_type,
            'percentage': int(distribution * 100)
        }

    @staticmethod
    def get_remaining_for_day(user, consumed: dict) -> dict:
        """
        Расчет оставшихся КБЖУ на день с учетом съеденного
        """
        daily = NutritionCalculator.get_daily_nutrition(user)

        return {
            'calories': max(0, daily['calories'] - consumed.get('calories', 0)),
            'protein': max(0, daily['protein'] - consumed.get('protein', 0)),
            'fat': max(0, daily['fat'] - consumed.get('fat', 0)),
            'carbs': max(0, daily['carbs'] - consumed.get('carbs', 0)),
            'total_calories': daily['calories'],
            'total_protein': daily['protein'],
            'total_fat': daily['fat'],
            'total_carbs': daily['carbs'],
            'progress': {
                'calories': int((consumed.get('calories', 0) / daily['calories']) * 100) if daily[
                                                                                                'calories'] > 0 else 0,
                'protein': int((consumed.get('protein', 0) / daily['protein']) * 100) if daily['protein'] > 0 else 0,
                'fat': int((consumed.get('fat', 0) / daily['fat']) * 100) if daily['fat'] > 0 else 0,
                'carbs': int((consumed.get('carbs', 0) / daily['carbs']) * 100) if daily['carbs'] > 0 else 0
            }
        }

    @staticmethod
    def get_daily_nutrition_from_dict(data: dict) -> dict:
        """
        Расчет суточной нормы КБЖУ из словаря с данными пользователя
        Используется для показа нормы сразу после онбординга

        data: словарь с полями:
            - goal (str): цель (похудение/набор массы/поддержание/рельеф/здоровье)
            - gender (str): пол (мужской/женский)
            - age (int): возраст
            - height (int): рост в см
            - weight (float): вес в кг
            - activity_level (str): активность (low/medium/high/very_high)
        """
        # Значения по умолчанию
        goal = data.get('goal', 'поддержание')
        gender = data.get('gender', 'женский')
        age = data.get('age', 30)
        height = data.get('height', 165)
        weight = data.get('weight', 60)
        activity_level = data.get('activity_level', 'medium')

        # Коэффициенты активности
        activity_factors = {
            'low': 1.2,
            'medium': 1.375,
            'high': 1.55,
            'very_high': 1.725
        }

        # 1. Расчёт BMR (базальный метаболизм)
        if gender == 'мужской':
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        # 2. Расчёт TDEE с учётом активности
        factor = activity_factors.get(activity_level, 1.375)
        tdee = bmr * factor

        # 3. Корректировка под цель
        goal_factors = {
            'похудение': {
                'calories': 0.85,
                'protein': 1.8,
                'fat': 0.8,
                'carbs': 2.0
            },
            'набор массы': {
                'calories': 1.15,
                'protein': 2.0,
                'fat': 1.0,
                'carbs': 3.5
            },
            'поддержание': {
                'calories': 1.0,
                'protein': 1.6,
                'fat': 0.9,
                'carbs': 2.5
            },
            'рельеф': {
                'calories': 0.9,
                'protein': 2.2,
                'fat': 0.7,
                'carbs': 2.2
            },
            'здоровье': {
                'calories': 1.0,
                'protein': 1.6,
                'fat': 0.9,
                'carbs': 2.5
            }
        }

        goal_factor = goal_factors.get(goal, goal_factors['поддержание'])
        daily_calories = int(tdee * goal_factor['calories'])

        # 4. Расчёт БЖУ в граммах
        protein = int(weight * goal_factor['protein'])
        fat = int(weight * goal_factor['fat'])

        # Углеводы из остатка калорий
        protein_calories = protein * 4
        fat_calories = fat * 9
        remaining_calories = daily_calories - protein_calories - fat_calories
        carbs = int(remaining_calories / 4)

        # Минимальные значения
        protein = max(protein, 50)
        fat = max(fat, 30)
        carbs = max(carbs, 100)

        return {
            'calories': daily_calories,
            'protein': protein,
            'fat': fat,
            'carbs': carbs,
            'goal': goal,
            'tdee': int(tdee),
            'bmr': int(bmr)
        }

class TrainerCRUD:
    """CRUD операции для системы тренеров"""

    @staticmethod
    async def get_trainer_clients(session, trainer_id: int):
        """Получить всех активных подопечных тренера"""
        from app.database.models import TrainerClient
        result = await session.execute(
            select(User)
            .join(TrainerClient, TrainerClient.client_id == User.id)
            .where(TrainerClient.trainer_id == trainer_id)
            .where(TrainerClient.status == 'active')
        )
        return result.scalars().all()

    @staticmethod
    async def get_client_trainers(session, client_id: int):
        """Получить всех активных тренеров подопечного"""
        from app.database.models import TrainerClient
        result = await session.execute(
            select(User)
            .join(TrainerClient, TrainerClient.trainer_id == User.id)
            .where(TrainerClient.client_id == client_id)
            .where(TrainerClient.status == 'active')
        )
        return result.scalars().all()

    @staticmethod
    async def get_relation(session, trainer_id: int, client_id: int):
        """Получить связь тренер-подопечный"""
        from app.database.models import TrainerClient
        result = await session.execute(
            select(TrainerClient)
            .where(TrainerClient.trainer_id == trainer_id)
            .where(TrainerClient.client_id == client_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_request(session, trainer_id: int, client_id: int):
        """
        Создать заявку на связь или переиспользовать старую.
        Возвращает tuple: (relation, action)
        action: created | already_active | already_pending | reactivated
        """
        from app.database.models import TrainerClient

        existing = await TrainerCRUD.get_relation(session, trainer_id, client_id)

        if existing:
            if existing.status == 'active':
                return existing, 'already_active'

            if existing.status == 'pending':
                return existing, 'already_pending'

            if existing.status == 'rejected':
                existing.status = 'pending'
                await session.commit()
                await session.refresh(existing)
                return existing, 'reactivated'

        relation = TrainerClient(
            trainer_id=trainer_id,
            client_id=client_id,
            status='pending'
        )
        session.add(relation)
        await session.commit()
        await session.refresh(relation)
        return relation, 'created'

    @staticmethod
    async def accept_request(session, trainer_id: int, client_id: int):
        """Подтвердить заявку"""
        relation = await TrainerCRUD.get_relation(session, trainer_id, client_id)
        if not relation:
            return None

        relation.status = 'active'
        await session.commit()
        await session.refresh(relation)
        return relation

    @staticmethod
    async def reject_request(session, trainer_id: int, client_id: int):
        """Отклонить заявку"""
        relation = await TrainerCRUD.get_relation(session, trainer_id, client_id)
        if not relation:
            return None

        relation.status = 'rejected'
        await session.commit()
        await session.refresh(relation)
        return relation

    @staticmethod
    async def get_pending_requests_for_client(session, client_id: int):
        """Все входящие заявки клиенту"""
        from app.database.models import TrainerClient
        result = await session.execute(
            select(TrainerClient)
            .where(TrainerClient.client_id == client_id)
            .where(TrainerClient.status == 'pending')
            .order_by(TrainerClient.assigned_at.desc())
        )
        return result.scalars().all()