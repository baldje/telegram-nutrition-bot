from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.utils.config import config

# Base для моделей
Base = declarative_base()

# Асинхронный Redis клиент для aiogram
redis_client = Redis.from_url(config.redis.url, decode_responses=True)  # ← УБРАТЬ [citation...]

# Синхронный движок (для миграций)
engine = create_engine(config.database.url)

# Асинхронный движок
async_engine = create_async_engine(
    config.database.url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=True,
    pool_pre_ping=True
)

# Sessionmaker
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession)

async def init_redis():
    """Инициализация Redis"""
    try:
        await redis_client.ping()
        print("✅ Redis подключен успешно!")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis: {e}")
        raise

async def close_redis():
    """Корректное закрытие Redis соединения"""
    await redis_client.close()

async def get_async_db():
    """Корректный генератор асинхронной сессии"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

__all__ = [
    'Base',
    'init_redis',
    'close_redis',
    'redis_client',
    'get_async_db',
    'engine',
    'async_engine',
    'AsyncSessionLocal'
]