#!/usr/bin/env python3
"""
Публикация релиза в канал @shaolenai при появлении новой версии.
Версия берётся только из файла VERSION в репозитории; из Telegram-канала версия не читается.
Использует Premium-сессию MTProto (тот же аккаунт должен быть админом канала).
Запуск: вручную после деплоя или по cron/systemd timer:
  python scripts/publish_release_to_telegram.py
"""
import asyncio
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

VERSION_PATH = os.path.join(ROOT, "VERSION")
CHANGELOG_PATH = os.path.join(ROOT, "CHANGELOG.md")
CHANNEL_USERNAME = "shaolenai"


def read_version_line(path: str) -> tuple[str | None, bool]:
    """
    Читает первую строку VERSION.
    Возвращает (версия без '+', уже_опубликована).
    Пример: "1.1.0" -> ("1.1.0", False), "1.1.0+" -> ("1.1.0", True).
    """
    if not os.path.isfile(path):
        return None, False
    with open(path, "r", encoding="utf-8") as f:
        content = (f.read() or "").strip()
    lines = content.splitlines()
    line = lines[0].strip() if lines else ""
    if not line:
        return None, False
    published = line.rstrip().endswith("+")
    version_clean = line.rstrip().rstrip("+").strip()
    return version_clean if version_clean else None, published


def parse_changelog_for_version(path: str, version: str):
    """Находит в CHANGELOG блок для версии v{version} и извлекает текст TELEGRAM_POST."""
    if not os.path.isfile(path) or not version:
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Нормализуем: VERSION может быть "1.1.0", в CHANGELOG — "v1.1.0"
    v_tag = f"v{version}" if not version.startswith("v") else version
    # Ищем блок ## [v1.1.0] — ... до следующего ## или конца
    pattern = rf"^##\s*\[{re.escape(v_tag)}\]\s*[—\-].*?<!--\s*TELEGRAM_POST\s*(.*?)\s*-->"
    m = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def mark_version_published(path: str) -> None:
    """Добавляет признак '+' к первой строке VERSION (версия опубликована)."""
    with open(path, "r", encoding="utf-8") as f:
        lines = (f.read() or "").splitlines()
    if not lines:
        return
    first = lines[0].strip().rstrip("+").strip()
    if not first:
        return
    lines[0] = first + "+"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main():
    current, is_published = read_version_line(VERSION_PATH)
    if not current:
        print("VERSION: файл не найден или пуст")
        return
    version = f"v{current}" if not current.startswith("v") else current
    post_text = parse_changelog_for_version(CHANGELOG_PATH, current)
    if not post_text:
        print("CHANGELOG.md: TELEGRAM_POST не найден для версии", version)
        return

    if is_published:
        print("Версия", version, "уже опубликована (есть признак + в VERSION)")
        return

    api_id = (os.getenv("TELEGRAM_API_ID") or "").strip().strip("'\"")
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip().strip("'\"")
    session_path = (os.getenv("PREMIUM_SESSION_PATH") or "").strip().strip("'\"")
    if not session_path or not api_id or not api_hash:
        print("Нужны TELEGRAM_API_ID, TELEGRAM_API_HASH, PREMIUM_SESSION_PATH в .env")
        return

    path_to_use = session_path if session_path.endswith(".session") else session_path + ".session"
    if not os.path.isabs(path_to_use):
        path_to_use = os.path.join(ROOT, path_to_use)
    if not os.path.isfile(path_to_use):
        path_to_use = os.path.join(ROOT, "premium_todo.session")
    if not os.path.isfile(path_to_use):
        print("Файл сессии не найден. Запустите scripts/create_premium_session.py")
        return

    base = path_to_use[:-8] if path_to_use.endswith(".session") else path_to_use
    try:
        from telethon import TelegramClient
    except ImportError:
        print("Установите: pip install telethon")
        return

    client = TelegramClient(base, int(api_id), api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("Сессия не авторизована. Пересоздайте сессию.")
            return
        await client.send_message(CHANNEL_USERNAME, post_text)
        mark_version_published(VERSION_PATH)
        print("Опубликовано в @shaolenai:", version)
    except Exception as e:
        print("Ошибка публикации:", e)
        raise
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
