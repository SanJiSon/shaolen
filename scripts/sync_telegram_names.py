#!/usr/bin/env python3
"""
Разовый скрипт: по Telegram ID получает для всех пользователей из БД
имя (first_name, last_name) и username через Bot API getChat.
Обновляет таблицу users. display_name не трогается.

Запуск из корня проекта:
  python scripts/sync_telegram_names.py

Требует: BOT_TOKEN и DB_PATH в .env или переменных окружения.
"""
import asyncio
import os
import sys
from typing import Optional

import aiosqlite
import httpx
from dotenv import load_dotenv

# Добавляем родительскую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "goals_bot.db")


async def get_telegram_user(bot_token: str, user_id: int) -> Optional[dict]:
    """Получить данные пользователя через getChat. Возвращает dict или None при ошибке."""
    url = f"https://api.telegram.org/bot{bot_token}/getChat"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params={"chat_id": user_id})
            data = r.json()
            if data.get("ok"):
                return data.get("result") or {}
            return None
    except Exception as e:
        print(f"  ⚠ Ошибка getChat для {user_id}: {e}")
        return None


async def main():
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не задан. Добавьте в .env или переменную окружения.")
        sys.exit(1)

    print(f"База: {DB_PATH}")
    print("Загрузка пользователей...")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            rows = await c.fetchall()
    user_ids = [r[0] for r in rows]
    print(f"Найдено пользователей: {len(user_ids)}")

    updated = 0
    failed_ids = []

    for uid in user_ids:
        chat = await get_telegram_user(BOT_TOKEN, uid)
        if chat is None:
            failed_ids.append(uid)
            continue

        first_name = (chat.get("first_name") or "").strip() or None
        last_name = (chat.get("last_name") or "").strip() or None
        username = (chat.get("username") or "").strip() or None

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE users SET first_name = ?, last_name = ?, username = ?
                   WHERE user_id = ?""",
                (first_name, last_name, username, uid),
            )
            await db.commit()

        name = " ".join(filter(None, [first_name, last_name])) or "—"
        un = f"@{username}" if username else "—"
        print(f"  ✓ {uid}: {name} {un}")
        updated += 1

        # Небольшая пауза, чтобы не перегружать API
        await asyncio.sleep(0.05)

    print(f"\nГотово. Обновлено: {updated}, не удалось: {len(failed_ids)}")
    if failed_ids:
        print("  ID без обновления (бот заблокирован или пользователь не запускал бота):", failed_ids[:10])
        if len(failed_ids) > 10:
            print(f"  ... и ещё {len(failed_ids) - 10}")


if __name__ == "__main__":
    asyncio.run(main())
