# app/main.py
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.utils.config import config
from app.database import init_redis, redis_client, close_redis, async_engine, Base, AsyncSessionLocal
import logging
import asyncio
import time

# ИМПОРТИРУЕМ ВСЕ РОУТЕРЫ
from app.handlers import (
    start_router,
    onboarding_router,
    photo_router,
    payments_router,
    main_router,
    legal_router,
    referral_router,
    food_diary_router,
    trainer_router,
    client_trainer_router,
)

# ИМПОРТИРУЕМ MIDDLEWARE
from app.utils.middlewares import SubscriptionMiddleware, LegalMiddleware
from app.utils.db_middleware import DatabaseMiddleware

# Инициализируем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    try:
        logger.info("🚀 Запуск бота...")
        time.sleep(5)

        # Инициализация Redis
        await init_redis()
        logger.info("✅ Redis подключен успешно")

        # Создание таблиц БД
        logger.info("🔄 Создание таблиц БД...")
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Таблицы БД созданы/проверены")

        # Создаем storage
        storage = RedisStorage(redis=redis_client)

        # Создаем бота и диспатчер
        bot = Bot(
            token=config.bot.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher(storage=storage)

        # ✅ ДОБАВЛЯЕМ MIDDLEWARE В ПРАВИЛЬНОМ ПОРЯДКЕ
        # 1. Сначала middleware для БД (на все типы обновлений)
        dp.update.middleware(DatabaseMiddleware(AsyncSessionLocal))
        logger.info("  ✅ DatabaseMiddleware зарегистрирован")

        # 2. Потом middleware для проверки согласия (на сообщения и колбэки)
        dp.message.middleware(LegalMiddleware())
        dp.callback_query.middleware(LegalMiddleware())
        logger.info("  ✅ LegalMiddleware зарегистрирован")

        # 3. Потом middleware для подписок (на сообщения и колбэки)
        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())
        logger.info("  ✅ SubscriptionMiddleware зарегистрирован")

        # ✅ РЕГИСТРАЦИЯ РОУТЕРОВ В ПРАВИЛЬНОМ ПОРЯДКЕ
        logger.info("🔄 Регистрация роутеров...")

        # Порядок важен: сначала самые специфичные, потом общие
        routers = [
            ("start", start_router),           # 1. Старт
            ("legal", legal_router),           # 2. Юридические (до согласия)
            ("referral", referral_router),     # 3. Реферальные
            ("payments", payments_router),     # 4. Платежи
            ("onboarding", onboarding_router), # 5. Онбординг
            ("food_diary", food_diary_router), # 6. Дневник питания
            ("photo", photo_router),           # 7. Фото
            ("trainer", trainer_router),       # 8. 👈 ТРЕНЕР (ДОБАВЛЕН)
            ("client_trainer_router", client_trainer_router),
            ("main", main_router),              # 9. Общий (последний)
        ]

        for name, router in routers:
            dp.include_router(router)
            logger.info(f"  ➕ {name}")

        logger.info("✅ Все роутеры зарегистрированы")
        logger.info(f"📋 Список роутеров: {', '.join([name for name, _ in routers])}")

        # Проверяем подключение
        me = await bot.get_me()
        logger.info(f"✅ Бот подключен: @{me.username} (ID: {me.id})")
        logger.info("🎯 Бот запущен и готов к работе!")

        # Запускаем бота
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")
        raise
    finally:
        await close_redis()
        logger.info("👋 Redis соединение закрыто")


if __name__ == "__main__":
    asyncio.run(main())