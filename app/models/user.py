from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    full_name = Column(String(255))

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
    referrer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    referral_code = Column(String(100), unique=True)
    balance = Column(Float, default=0.0)
    discount_percent = Column(Integer, default=0)  # Текущая скидка в %

    # Юридическое согласие (НОВОЕ)
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
    consent_history = relationship('UserConsent', back_populates='user', cascade="all, delete-orphan")  # НОВОЕ


class UserConsent(Base):  # НОВАЯ МОДЕЛЬ
    """Модель для хранения истории согласий пользователя"""
    __tablename__ = 'user_consents'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # Тип согласия
    consent_type = Column(String(50), nullable=False)  # 'privacy', 'offer', 'marketing', 'privacy_offer'
    document_version = Column(String(20), default='1.0')

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
    discount_applied = Column(Integer, default=0)  # НОВОЕ: примененная скидка

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