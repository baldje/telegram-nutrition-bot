# app/database/models.py
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100))
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    is_premium = Column(Boolean, default=False)
    balance = Column(Integer, default=0)  # Баланс в копейках
    referral_code = Column(String(20), unique=True, nullable=True)
    referrer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    trial_started_at = Column(DateTime, nullable=True)
    subscription_until = Column(DateTime, nullable=True)
    subscription_status = Column(String(20), default='inactive')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    payments = relationship("Payment", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    referrals = relationship("User", backref="referrer", remote_side=[id])

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class FoodEntry(Base):
    __tablename__ = 'food_entries'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    food_name = Column(String(200), nullable=False)
    calories = Column(Float)
    proteins = Column(Float)
    fats = Column(Float)
    carbs = Column(Float)
    photo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь
    user = relationship("User")

    def __repr__(self):
        return f"<FoodEntry(id={self.id}, food={self.food_name})>"


class UserGoals(Base):
    __tablename__ = 'user_goals'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)
    daily_calories = Column(Float, default=2000)
    daily_proteins = Column(Float, default=150)
    daily_fats = Column(Float, default=70)
    daily_carbs = Column(Float, default=250)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связь
    user = relationship("User")

    def __repr__(self):
        return f"<UserGoals(user_id={self.user_id}, calories={self.daily_calories})>"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String(100), unique=True, index=True)  # ID от Тинькофф
    order_id = Column(String(100), unique=True, index=True)  # Наш внутренний ID
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    amount = Column(Float)  # Сумма в рублях
    tariff = Column(String(50))  # Тариф подписки
    status = Column(String(50), default="NEW")  # Статус платежа
    payment_url = Column(Text, nullable=True)  # URL для оплаты
    description = Column(String(255), nullable=True)  # Описание
    additional_data = Column(JSON, nullable=True)  # Доп. данные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.status})>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    tariff = Column(String(50))  # Тип тарифа
    expires_at = Column(DateTime)  # Дата окончания
    payment_id = Column(String(100), nullable=True)  # Последний платеж
    is_active = Column(Boolean, default=True)  # Активна ли
    auto_renew = Column(Boolean, default=False)  # Автопродление
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="subscription")

    def is_valid(self) -> bool:
        """Проверка валидности подписки"""
        if not self.is_active:
            return False
        return datetime.utcnow() < self.expires_at

    def days_left(self) -> int:
        """Оставшееся количество дней"""
        if not self.is_valid():
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, is_active={self.is_active}, expires_at={self.expires_at})>"


class UserTraining(Base):
    __tablename__ = "user_trainings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    training_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь
    user = relationship("User")

    def __repr__(self):
        return f"<UserTraining(id={self.id}, user_id={self.user_id}, date={self.training_date})>"