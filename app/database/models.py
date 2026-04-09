# app/database/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text, BigInteger, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base  # Base из __init__.py
from enum import Enum


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)  # ИСПРАВЛЕНО: Integer -> BigInteger
    username = Column(String(255))
    full_name = Column(String(255))

    role = Column(String(20), default='user')

    # Данные онбординга
    goal = Column(String(50))
    gender = Column(String(20))
    age = Column(Integer)
    height = Column(Integer)
    weight = Column(Float)
    favorite_foods = Column(Text)
    excluded_foods = Column(Text)
    health_issues = Column(Text)
    wants_training = Column(Boolean, default=False)

    # Подписка и триал
    subscription_until = Column(DateTime, nullable=True)
    subscription_status = Column(String(20), default='trial')
    trial_used = Column(Boolean, default=False)
    trial_start = Column(DateTime)
    trial_started_at = Column(DateTime, default=datetime.utcnow)

    # Счетчики использования
    photo_analyzes_count = Column(Integer, default=0)
    last_photo_analysis_at = Column(DateTime, nullable=True)

    # Реферальная система
    referrer_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)  # ИСПРАВЛЕНО: Integer -> BigInteger
    referral_code = Column(String(100), unique=True)
    balance = Column(Float, default=0.0)
    discount_percent = Column(Integer, default=0)

    # Юридическая часть
    consent_given = Column(Boolean, default=False)
    consent_date = Column(DateTime, nullable=True)
    consent_ip = Column(String(50), nullable=True)

    # Статистика и достижения
    medals = Column(Integer, default=0)
    cups = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    last_training = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    referrals = relationship('User', backref='referrer', remote_side=[id])
    payments = relationship('Payment', back_populates='user')
    trainings = relationship('UserTraining', back_populates='user')
    consent_history = relationship('UserConsent', back_populates='user', cascade="all, delete-orphan")
    food_entries = relationship('FoodDiary', back_populates='user', cascade="all, delete-orphan")
    daily_summaries = relationship('DailySummary', back_populates='user', cascade="all, delete-orphan")


class UserConsent(Base):
    """Модель для хранения истории согласий пользователя"""
    __tablename__ = 'user_consents'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # Тип согласия
    consent_type = Column(String(50), nullable=False)  # 'privacy', 'offer', 'privacy_offer', 'marketing'
    document_version = Column(String(20), default='1.0')  # Версия документа

    # Статус
    accepted = Column(Boolean, default=True)
    accepted_at = Column(DateTime, default=datetime.utcnow)

    # Техническая информация
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Связь с пользователем
    user = relationship("User", back_populates="consent_history")


class Payment(Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount = Column(Integer, nullable=False)  # в копейках
    period = Column(String(20), nullable=False)  # '1_month', '3_months', '6_months'
    payment_id = Column(String(255))  # ID от платежной системы
    status = Column(String(20), default='pending')  # pending, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    # Скидка, примененная к платежу
    discount_applied = Column(Integer, default=0)

    user = relationship('User', back_populates='payments')


class UserTraining(Base):
    __tablename__ = 'user_trainings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    training_date = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='trainings')


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)

    # Связи
    user = relationship('User', backref='subscriptions')
    payment = relationship('Payment', backref='subscription')


class MealType(str, Enum):
    """Типы приемов пищи"""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class FoodDiary(Base):
    """Дневник питания - записи о приемах пищи"""
    __tablename__ = 'food_diary'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    meal_type = Column(String(20), nullable=False)  # breakfast, lunch, dinner, snack
    meal_date = Column(DateTime, default=datetime.utcnow)

    # Что съел (текстовое описание)
    description = Column(Text, nullable=False)

    # Анализ от OpenAI
    calories = Column(Integer)  # общие калории
    protein = Column(Float)  # белки в граммах
    fat = Column(Float)  # жиры в граммах
    carbs = Column(Float)  # углеводы в граммах

    # Связь с фото (если было)
    photo_file_id = Column(String(255), nullable=True)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="food_entries")


class DailySummary(Base):
    """Ежедневная сводка по питанию"""
    __tablename__ = 'daily_summaries'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    summary_date = Column(Date, nullable=False)

    # Суммарные показатели за день
    total_calories = Column(Integer, default=0)
    total_protein = Column(Float, default=0)
    total_fat = Column(Float, default=0)
    total_carbs = Column(Float, default=0)

    # Количество приемов пищи
    meals_count = Column(Integer, default=0)

    # Завершен ли день (можно ли редактировать)
    is_completed = Column(Boolean, default=False)

    # Заметки на день
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="daily_summaries")


class UserRole(str, Enum):
    """Роли пользователей"""
    USER = "user"  # обычный пользователь
    TRAINER = "trainer"  # тренер/наставник
    ADMIN = "admin"  # администратор


class TrainerClient(Base):
    """Связь тренера и подопечного"""
    __tablename__ = 'trainer_clients'

    id = Column(Integer, primary_key=True)
    trainer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # Статус связи
    status = Column(String(20), default='active')  # active, pending, rejected

    # Дата назначения
    assigned_at = Column(DateTime, default=datetime.utcnow)

    # Заметки тренера о подопечном
    notes = Column(Text, nullable=True)

    # Связи
    trainer = relationship("User", foreign_keys=[trainer_id], backref="clients")
    client = relationship("User", foreign_keys=[client_id], backref="trainers")


class TrainerComment(Base):
    """Комментарии тренера к записям дневника"""
    __tablename__ = 'trainer_comments'

    id = Column(Integer, primary_key=True)
    trainer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    food_entry_id = Column(Integer, ForeignKey('food_diary.id'), nullable=False)

    comment = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    trainer = relationship("User", foreign_keys=[trainer_id])
    food_entry = relationship("FoodDiary", backref="trainer_comments")


class TrainerAdvice(Base):
    """Рекомендации тренера на день"""
    __tablename__ = 'trainer_advices'

    id = Column(Integer, primary_key=True)
    trainer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    client_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    advice_date = Column(Date, nullable=False)
    advice_text = Column(Text, nullable=False)

    # Цели на день (опционально)
    target_calories = Column(Integer, nullable=True)
    target_protein = Column(Float, nullable=True)
    target_fat = Column(Float, nullable=True)
    target_carbs = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    trainer = relationship("User", foreign_keys=[trainer_id])
    client = relationship("User", foreign_keys=[client_id])