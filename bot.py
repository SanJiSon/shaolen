#!/usr/bin/env python3
"""Telegram-бот Шаолень: /start + inline (@shaolen_bot — список задач)."""
import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes

from database import Database

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_BASE_URL", "") or os.getenv("WEBAPP_URL", "").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "goals_bot.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database(DB_PATH)
MAX_MESSAGE_LENGTH = 4096


def _build_task_list(
    missions: list, goals: list, habits: list, is_premium: bool
) -> str:
    """Собирает текст списка задач. Premium — checklist (☐), иначе — список (•)."""
    lines = []
    prefix = "☐ " if is_premium else "• "

    for m in missions or []:
        title = (m.get("title") or "").strip() or "Миссия"
        lines.append(prefix + title)
        for sg in m.get("_subgoals") or []:
            sg_title = (sg.get("title") or "").strip() or "Подцель"
            sub_pref = "  ☐ " if is_premium else "  – "
            lines.append(sub_pref + sg_title)

    for g in goals or []:
        lines.append(prefix + ((g.get("title") or "").strip() or "Цель"))

    for h in habits or []:
        lines.append(prefix + ((h.get("title") or "").strip() or "Привычка"))

    if not lines:
        return "📋 Мои задачи (пусто)\n\nДобавьте миссии, цели и привычки в @shaolen_bot"

    text = "📋 Мои задачи\n\n" + "\n".join(lines)
    return text[: MAX_MESSAGE_LENGTH - 20] + "\n\n…" if len(text) > MAX_MESSAGE_LENGTH else text


async def _fetch_user_tasks(user_id: int) -> tuple:
    missions = await db.get_missions(user_id, include_completed=False)
    for m in missions:
        m["_subgoals"] = await db.get_subgoals(m.get("id") or 0)
    goals = await db.get_goals(user_id, include_completed=False)
    habits = await db.get_habits(user_id, active_only=True)
    return missions, goals, habits


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        await db.add_user(user.id, user.username, user.first_name, user.last_name)

    if not WEBAPP_URL:
        await update.message.reply_text(
            "Привет! Веб-приложение не настроено (WEBAPP_BASE_URL в .env)."
        )
        return

    await update.message.reply_text(
        "Откройте веб-приложение:",
        reply_markup={
            "inline_keyboard": [
                [{"text": "🚀 Открыть веб‑приложение", "web_app": {"url": WEBAPP_URL}}]
            ]
        },
    )


async def inline_query_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик inline @shaolen_bot — список задач в чат."""
    query = update.inline_query
    if not query or not query.from_user:
        return

    user = query.from_user
    user_id = user.id
    is_premium = getattr(user, "is_premium", False) or False

    missions, goals, habits = [], [], []
    try:
        await db.add_user(user_id, user.username, user.first_name, user.last_name)
        missions, goals, habits = await _fetch_user_tasks(user_id)
        text = _build_task_list(missions, goals, habits, is_premium)
    except Exception as e:
        logger.exception("inline_query: %s", e)
        text = "Ошибка загрузки задач. Попробуйте позже."

    has_tasks = bool(missions or goals or habits)
    await query.answer(
        [
            InlineQueryResultArticle(
                id="tasks",
                title="Мои задачи" if has_tasks else "Мои задачи (пусто)",
                description="Отправить список миссий, целей и привычек в чат",
                input_message_content=InputTextMessageContent(text),
            )
        ],
        cache_time=60,
    )


def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан. Добавьте в .env")
        return

    try:
        asyncio.run(db.init_db())
    except Exception as e:
        logger.warning("init_db: %s", e)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
