#!/usr/bin/env python3
"""
Отправка нативного Telegram Todo через MTProto (Telethon).
Подключение только на время отправки, без постоянной второй сессии — для стабильности.
"""
import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Лимиты Telegram (консервативные значения)
TODO_TITLE_MAX = 128
TODO_ITEM_TITLE_MAX = 128
TODO_ITEMS_MAX = 100


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
        if "todo" in err or "media" in err or "not supported" in err or "premium" in err or "forbidden" in err:
            short = str(e).split("(")[0].strip() or str(e)[:80]
            return (
                False,
                "Нативные списки Todo недоступны: Telegram может ограничивать их для ботов или чатов. "
                f"Ответ API: {short}"
            )
        return False, f"Ошибка отправки: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
