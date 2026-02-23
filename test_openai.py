import asyncio
from app.utils.openai_client import ask_gpt

async def main():
    print("Отправляю тестовый запрос к OpenAI...")
    try:
        response = await ask_gpt("Привет! Расскажи три полезных привычки для здоровья.")
        print("\n--- Ответ от GPT ---\n")
        print(response)
    except Exception as e:
        print(f"Ошибка при вызове OpenAI: {e}")

if __name__ == "__main__":
    asyncio.run(main())
