#!/usr/bin/env python3
"""
Отправка нативного Telegram Todo через MTProto (Telethon).
- Бот (bot_token): не может отправлять Todo (требуется Premium).
- Пользователь Premium (сессия из файла): отправляет Todo в личку тому, кто запросил /todo.
Подключение только на время отправки.
"""
import asyncio
import logging
import os
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Лимиты Telegram (консервативные значения; TODO_ITEMS_TOO_MUCH при превышении)
TODO_TITLE_MAX = 128
TODO_ITEM_TITLE_MAX = 128
TODO_ITEMS_MAX = 30


def _truncate(s: str, max_len: int) -> str:
    s = (s or "").strip() or "—"
    return s[:max_len] if len(s) > max_len else s


def _flatten_tasks(
    missions: list, goals: list, habits: list
) -> Tuple[str, List[Tuple[str, bool]]]:
    """
    Собирает плоский список (заголовок, [(title, is_completed), ...]) и заголовок списка.
    """
    items: List[Tuple[str, bool]] = []
    if missions:
        for m in missions:
            title = _truncate(m.get("title") or "Миссия", TODO_ITEM_TITLE_MAX)
            items.append((title, bool(m.get("is_completed"))))
            for sg in m.get("_subgoals") or []:
                sg_title = _truncate(sg.get("title") or "Подцель", TODO_ITEM_TITLE_MAX)
                items.append((sg_title, bool(sg.get("is_completed"))))
    if goals:
        for g in goals:
            title = _truncate(g.get("title") or "Цель", TODO_ITEM_TITLE_MAX)
            items.append((title, bool(g.get("is_completed"))))
    if habits:
        for h in habits:
            title = _truncate(h.get("title") or "Привычка", TODO_ITEM_TITLE_MAX)
            items.append((title, False))
    items = items[:TODO_ITEMS_MAX]

    if missions and not goals and not habits:
        head = "Миссии"
    elif goals and not missions and not habits:
        head = "Цели"
    elif habits and not missions and not goals:
        head = "Привычки"
    else:
        head = "Задачи"
    list_title = _truncate(head, TODO_TITLE_MAX)
    return list_title, items


async def send_native_todo_as_user(
    target_user_id: int,
    missions: list,
    goals: list,
    habits: list,
    *,
    session_path: str,
    api_id: int,
    api_hash: str,
    timeout: float = 15.0,
) -> Tuple[bool, str]:
    """
    Отправляет нативный Todo от имени пользователя (Premium-сессия из файла)
    в личку пользователю target_user_id. Сессия должна быть от аккаунта с Premium.
    """
    if not session_path or not api_id or not api_hash:
        return False, "Premium-сессия не настроена (PREMIUM_SESSION_PATH в .env)."
    session_path = session_path.strip().strip("'\"")
    if not os.path.isfile(session_path) and not os.path.isfile(session_path + ".session"):
        return False, "Файл сессии Premium не найден. Запустите скрипт создания сессии."
    path_to_use = session_path if session_path.endswith(".session") else session_path + ".session"
    if not os.path.isfile(path_to_use):
        return False, "Файл сессии Premium не найден. Запустите скрипт создания сессии."

    list_title, items = _flatten_tasks(missions, goals, habits)
    if not items:
        return False, "Нет задач для отправки."

    try:
        from telethon import TelegramClient
        from telethon.tl.functions.messages import SendMediaRequest
        from telethon.tl.types import (
            InputMediaTodo,
            TextWithEntities,
            TodoItem,
            TodoList,
        )
    except ImportError as e:
        logger.warning("Telethon not available: %s", e)
        return False, "Модуль Telethon не установлен."

    base = path_to_use[:-8] if path_to_use.endswith(".session") else path_to_use
    client = TelegramClient(base, int(api_id), api_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=10.0)
        if not await client.is_user_authorized():
            await client.disconnect()
            return False, "Сессия Premium не авторизована. Запустите скрипт создания сессии и войдите по коду."
        peer = await client.get_input_entity(target_user_id)
        title_twe = TextWithEntities(text=list_title, entities=[])
        todo_items = [
            TodoItem(id=i, title=TextWithEntities(text=title, entities=[]))
            for i, (title, _) in enumerate(items, start=1)
        ]
        todo_list = TodoList(
            title=title_twe,
            list=todo_items,
            others_can_append=True,
            others_can_complete=True,
        )
        media = InputMediaTodo(todo=todo_list)
        await asyncio.wait_for(
            client(SendMediaRequest(peer=peer, media=media, message="")),
            timeout=timeout,
        )
        return True, "Нативный список отправлен вам в личные сообщения."
    except asyncio.TimeoutError:
        logger.warning("send_native_todo_as_user: timeout target=%s", target_user_id)
        return False, "Таймаут. Попробуйте позже."
    except Exception as e:
        logger.exception("send_native_todo_as_user: %s", e)
        err = str(e).lower()
        if "api_id" in err or "api_hash" in err or "apiidinvalid" in err:
            return False, "Неверные TELEGRAM_API_ID или TELEGRAM_API_HASH."
        if "session" in err or "auth" in err or "phone" in err:
            return False, "Сессия Premium недействительна. Пересоздайте сессию скриптом."
        return False, f"Ошибка отправки: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def send_native_todo(
    chat_id: int,
    missions: list,
    goals: list,
    habits: list,
    *,
    api_id: int,
    api_hash: str,
    bot_token: str,
    timeout: float = 15.0,
) -> Tuple[bool, str]:
    """
    Подключается к Telegram через Telethon (только на время запроса), отправляет
    нативный Todo в чат и отключается. Возвращает (success, message).
    """
    if not bot_token or not api_id or not api_hash:
        return False, "Нативный Todo не настроен (TELEGRAM_API_ID, TELEGRAM_API_HASH в .env)."

    list_title, items = _flatten_tasks(missions, goals, habits)
    if not items:
        return False, "Нет задач для отправки. Добавьте миссии, цели или привычки в веб‑приложении."

    try:
        from telethon import TelegramClient
        from telethon.sessions import MemorySession
        from telethon.tl.functions.messages import SendMediaRequest
        from telethon.tl.types import (
            InputMediaTodo,
            TextWithEntities,
            TodoItem,
            TodoList,
        )
    except ImportError as e:
        logger.warning("Telethon not available: %s", e)
        return (
            False,
            "Модуль Telethon не найден в окружении бота. Установите: pip install telethon. "
            "Убедитесь, что бот запущен в том же venv, где выполняли pip install -r requirements.txt.",
        )

    client = TelegramClient(
        MemorySession(),
        int(api_id),
        api_hash,
    )
    try:
        await asyncio.wait_for(client.start(bot_token=bot_token), timeout=10.0)
        peer = await client.get_input_entity(chat_id)
        title_twe = TextWithEntities(text=list_title, entities=[])
        todo_items = [
            TodoItem(id=i, title=TextWithEntities(text=title, entities=[]))
            for i, (title, _) in enumerate(items, start=1)
        ]
        todo_list = TodoList(
            title=title_twe,
            list=todo_items,
            others_can_append=True,
            others_can_complete=True,
        )
        media = InputMediaTodo(todo=todo_list)
        await asyncio.wait_for(
            client(SendMediaRequest(peer=peer, media=media, message="")),
            timeout=timeout,
        )
        return True, "Нативный список задач отправлен."
    except asyncio.TimeoutError:
        logger.warning("send_native_todo: timeout chat_id=%s", chat_id)
        return False, "Таймаут. Попробуйте позже."
    except Exception as e:
        logger.exception("send_native_todo: %s", e)
        err = str(e).lower()
        if "api_id" in err or "api_hash" in err or "apiidinvalid" in err:
            return (
                False,
                "Неверные TELEGRAM_API_ID или TELEGRAM_API_HASH. "
                "Возьмите их на https://my.telegram.org → API development tools. "
                "Без кавычек и пробелов в .env, api_id — число, api_hash — строка из 32 символов.",
            )
        if "premium" in err:
            return (
                False,
                "PREMIUM_REQUIRED: Нативные Todo в Telegram доступны только аккаунтам с Premium; боты не могут их отправлять. Ниже — текстовый чеклист.",
            )
        if "todo" in err or "media" in err or "not supported" in err or "forbidden" in err:
            short = str(e).split("(")[0].strip() or str(e)[:80]
            return (
                False,
                f"Нативные списки Todo недоступны. Ответ API: {short}",
            )
        return False, f"Ошибка отправки: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
