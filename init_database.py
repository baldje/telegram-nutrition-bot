import asyncio
from app.database.init_db import init_sync, init_async

if __name__ == "__main__":
    print("🚀 Инициализация базы данных...")
    init_sync()
    asyncio.run(init_async())
    print("🎉 Инициализация завершена!")