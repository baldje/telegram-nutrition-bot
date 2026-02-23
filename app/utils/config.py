# app/utils/config.py
"""
config.py

Чистая, предсказуемая и типизированная конфигурация проекта.
Содержит структуру конфигурационных секций и безопасно загружает .env.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


# ---------------------- DATABASE ----------------------
@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda:
    os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:123456@localhost:5433/nutrition_bot"
    )
                     )


# ---------------------- REDIS ----------------------
@dataclass
class RedisConfig:
    url: str = field(default_factory=lambda:
    os.getenv(
        "REDIS_URL",
        "redis://localhost:5912"
    )
                     )


# ---------------------- OPENAI ----------------------
@dataclass
class OpenAIConfig:
    api_key: str = field(default_factory=lambda:
    os.getenv("OPENAI_API_KEY", "").strip()
                         )

    # Актуальная модель на 24 ноября 2025
    model: str = field(default_factory=lambda:
    os.getenv("OPENAI_MODEL", "gpt-5-nano").strip()
                       )

    def validate(self):
        if not self.api_key:
            raise ValueError(
                "❌ OPENAI_API_KEY отсутствует в .env — GPT функционал не будет работать."
            )


# ---------------------- BOT ----------------------
@dataclass
class BotConfig:
    token: str = field(default_factory=lambda:
    os.getenv("BOT_TOKEN", "").strip()
                       )

    username: str = field(default_factory=lambda:
    os.getenv("BOT_USERNAME", "").strip()
                          )

    admin_ids: List[int] = field(default_factory=lambda:
    [int(x.strip()) for x in os.getenv("ADMIN_IDS", "123456789").split(",")]
                                 )

    def validate(self):
        if not self.token:
            raise ValueError("❌ BOT_TOKEN отсутствует в .env — бот не сможет работать.")


# ---------------------- APP SETTINGS ----------------------
@dataclass
class AppConfig:
    trial_days: int = field(default_factory=lambda:
    int(os.getenv("TRIAL_DAYS", "3"))
                            )

    bonus_per_referral: int = field(default_factory=lambda:
    int(os.getenv("BONUS_PER_REFERRAL", "10000"))
                                    )

    partner_reward: int = field(default_factory=lambda:
    int(os.getenv("PARTNER_REWARD", "30000"))
                                )


# ---------------------- WEBHOOK ----------------------
@dataclass
class WebhookConfig:
    url: str = field(default_factory=lambda:
    os.getenv("WEBHOOK_URL", "")
                     )

    path: str = field(default_factory=lambda:
    os.getenv("WEBHOOK_PATH", "/webhook")
                      )

    host: str = field(default_factory=lambda:
    os.getenv("WEBAPP_HOST", "0.0.0.0")
                      )

    port: int = field(default_factory=lambda:
    int(os.getenv("WEBAPP_PORT", "8000"))
                      )


# ---------------------- LOGGING ----------------------
@dataclass
class LoggingConfig:
    level: str = field(default_factory=lambda:
    os.getenv("LOG_LEVEL", "INFO")
                       )

    file: str = field(default_factory=lambda:
    os.getenv("LOG_FILE", "logs/bot.log")
                      )


# ---------------------- PAYMENT ----------------------
@dataclass
class PaymentConfig:
    TINKOFF_TERMINAL_KEY: str = field(default_factory=lambda:
    os.getenv("TINKOFF_TERMINAL_KEY", "").strip()
                                      )

    TINKOFF_SECRET_KEY: str = field(default_factory=lambda:
    os.getenv("TINKOFF_SECRET_KEY", "").strip()
                                    )

    TINKOFF_API_URL: str = field(default_factory=lambda:
    os.getenv("TINKOFF_API_URL", "https://securepay.tinkoff.ru/v2/").strip()
                                 )

    # URL для редиректов
    PAYMENT_SUCCESS_URL: str = field(default_factory=lambda:
    os.getenv("PAYMENT_SUCCESS_URL", "https://t.me/your_bot?start=payment_success").strip()
                                     )

    PAYMENT_FAILURE_URL: str = field(default_factory=lambda:
    os.getenv("PAYMENT_FAILURE_URL", "https://t.me/your_bot?start=payment_failed").strip()
                                     )

    # Тарифы подписки (в копейках)
    TARIFF_MONTH: int = field(default_factory=lambda:
    int(os.getenv("TARIFF_MONTH", "29900"))
                              )  # 299 руб

    TARIFF_3MONTHS: int = field(default_factory=lambda:
    int(os.getenv("TARIFF_3MONTHS", "79900"))
                                )  # 799 руб

    TARIFF_YEAR: int = field(default_factory=lambda:
    int(os.getenv("TARIFF_YEAR", "299000"))
                             )  # 2990 руб

    def validate(self):
        if not self.TINKOFF_TERMINAL_KEY or not self.TINKOFF_SECRET_KEY:
            print("⚠️ TINKOFF_TERMINAL_KEY или TINKOFF_SECRET_KEY отсутствуют — платежи работать не будут.")


# ---------------------- MAIN CONFIG ----------------------
@dataclass
class Config:
    bot: BotConfig = field(default_factory=BotConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    app: AppConfig = field(default_factory=AppConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)

    def __post_init__(self):
        self.bot.validate()
        self.openai.validate()
        self.payment.validate()

        log_dir = os.path.dirname(self.logging.file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)


# Создаём единый глобальный экземпляр конфигурации
config = Config()