# app/database/__init__.py
import redis
from app.utils.config import config
import logging

logger = logging.getLogger(__name__)

# Redis клиент
redis_client = redis.Redis.from_url(config.redis.url, decode_responses=True)

async def init_redis():
    """Инициализация Redis соединения"""
    try:
        redis_client.ping()
        logger.info("✅ Redis подключен успешно")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Redis: {e}")
        raise

async def get_user_data(user_id: int):
    """Получение данных пользователя из Redis"""
    try:
        user_key = f"user:{user_id}"
        return redis_client.hgetall(user_key)
    except Exception as e:
        logger.error(f"Ошибка получения данных пользователя {user_id}: {e}")
        return {}

async def save_user_data(user_id: int, data: dict):
    """Сохранение данных пользователя в Redis"""
    try:
        user_key = f"user:{user_id}"
        redis_client.hset(user_key, mapping=data)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных пользователя {user_id}: {e}")
        return False