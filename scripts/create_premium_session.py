#!/usr/bin/env python3
"""
Однократный вход под аккаунтом с Telegram Premium для отправки нативного Todo.
Запустите один раз (на сервере или локально), войдите по номеру и коду — сессия сохранится.
После этого укажите путь к файлу сессии в .env: PREMIUM_SESSION_PATH=/path/to/premium_todo
"""
import asyncio
import os
import sys

# родительская папка проекта (где .env и bot.py)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID", "").strip().strip("'\"")
API_HASH = (os.getenv("TELEGRAM_API_HASH", "") or "").strip().strip("'\"")
SESSION_NAME = os.getenv("PREMIUM_SESSION_PATH", "").strip().strip("'\"") or "premium_todo"
if SESSION_NAME.endswith(".session"):
    SESSION_NAME = SESSION_NAME[:-8]


async def main():
    if not API_ID or not API_HASH:
        print("Добавьте в .env: TELEGRAM_API_ID и TELEGRAM_API_HASH (с my.telegram.org)")
        return
    try:
        from telethon import TelegramClient
    except ImportError:
        print("Установите: pip install telethon")
        return

    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    await client.start(
        phone=lambda: input("Номер телефона (с +): "),
        password=lambda: input("Пароль 2FA (если включён, иначе Enter): ") or None,
    )
    me = await client.get_me()
    print(f"Вход выполнен: @{me.username or me.id}. Сессия сохранена в {SESSION_NAME}.session")
    print("В .env укажите: PREMIUM_SESSION_PATH=" + os.path.join(ROOT, SESSION_NAME))
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
