# app/utils/db_middleware.py
from aiogram import BaseMiddleware
from typing import Any, Awaitable, Callable, Dict
from aiogram.types import TelegramObject


class DatabaseMiddleware(BaseMiddleware):
    """Middleware для передачи сессии БД в хендлеры"""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """
        Передает сессию БД в хендлеры двумя способами:
        - data['session'] - для прямого использования
        - data['db'].session - для обратной совместимости
        """
        async with self.session_factory() as session:
            # Основной способ - передаем session напрямую
            data['session'] = session

            # Для обратной совместимости - сохраняем db объект
            data['db'] = type('DB', (), {'session': session})()

            # Вызываем следующий handler
            return await handler(event, data)