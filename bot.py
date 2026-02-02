#!/usr/bin/env python3
"""Telegram-бот Шаолень: /start + inline (@shaolen_bot — список задач)."""
import asyncio
import logging
import os

from dotenv import load_dotenv  # type: ignore[import-untyped]
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent  # type: ignore[import-untyped]
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes  # type: ignore[import-untyped]

from database import Database
from native_todo import send_native_todo

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_BASE_URL", "") or os.getenv("WEBAPP_URL", "").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "goals_bot.db")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database(DB_PATH)
MAX_MESSAGE_LENGTH = 4096


def _escape_html(s: str) -> str:
    """Экранирует < и > для безопасного вывода в HTML."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_task_list(
    missions: list, goals: list, habits: list, is_premium: bool
) -> str:
    """Текст в формате чеклиста: заголовок «Миссии» / «Цели» / «Привычки» + строки ☐/☑."""
    lines = []

    if missions:
        for m in missions or []:
            title = _escape_html((m.get("title") or "").strip() or "Миссия")
            done = m.get("is_completed")
            lines.append(("☑ " if done else "☐ ") + ("<s>" + title + "</s>" if done else title))
            for sg in m.get("_subgoals") or []:
                sg_title = _escape_html((sg.get("title") or "").strip() or "Подцель")
                sg_done = sg.get("is_completed")
                lines.append("  " + ("☑ " if sg_done else "☐ ") + ("<s>" + sg_title + "</s>" if sg_done else sg_title))

    if goals:
        for g in goals or []:
            title = _escape_html((g.get("title") or "").strip() or "Цель")
            done = g.get("is_completed")
            lines.append(("☑ " if done else "☐ ") + ("<s>" + title + "</s>" if done else title))

    if habits:
        for h in habits or []:
            title = _escape_html((h.get("title") or "").strip() or "Привычка")
            lines.append("☐ " + title)

    if not lines:
        return "Задачи (пусто)\n\nДобавьте в @shaolen_bot"

    # Один заголовок: Миссии / Цели / Привычки
    if missions and not goals and not habits:
        head = "Миссии"
    elif goals and not missions and not habits:
        head = "Цели"
    elif habits and not missions and not goals:
        head = "Привычки"
    else:
        head = "Задачи"

    text = "<b>" + head + "</b>\n\n" + "\n".join(lines)
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
    query_text = (query.query or "").strip().lower()

    missions, goals, habits = [], [], []
    try:
        await db.add_user(user_id, user.username, user.first_name, user.last_name)
        missions, goals, habits = await _fetch_user_tasks(user_id)
    except Exception as e:
        logger.exception("inline_query: %s", e)
        await query.answer(
            [
                InlineQueryResultArticle(
                    id="error",
                    title="⚠️ Ошибка",
                    description="Не удалось загрузить задачи",
                    input_message_content=InputTextMessageContent("Ошибка загрузки задач. Попробуйте позже."),
                )
            ],
            cache_time=10,
        )
        return

    results = []
    
    # Фильтруем по запросу: "миссии", "цели", "привычки" или показываем все
    show_missions = not query_text or "мисс" in query_text or "mission" in query_text
    show_goals = not query_text or "цел" in query_text or "goal" in query_text or "задач" in query_text
    show_habits = not query_text or "привыч" in query_text or "habit" in query_text
    
    # Без thumbnail_url — иначе слева от названий в списке inline отображаются пустые квадраты.
    # Нативный Todo/checklist в inline недоступен: API отдаёт только текст (InputTextMessageContent).

    # 1. Миссии
    if show_missions and missions:
        missions_text = _build_task_list(missions, [], [], is_premium)
        results.append(
            InlineQueryResultArticle(
                id="missions",
                title=f"Миссии ({len(missions)})",
                description="Долгосрочные цели с подцелями",
                input_message_content=InputTextMessageContent(missions_text, parse_mode="HTML"),
            )
        )
    
    # 2. Цели
    if show_goals and goals:
        goals_text = _build_task_list([], goals, [], is_premium)
        results.append(
            InlineQueryResultArticle(
                id="goals",
                title=f"Цели ({len(goals)})",
                description="Задачи с дедлайнами",
                input_message_content=InputTextMessageContent(goals_text, parse_mode="HTML"),
            )
        )
    
    # 3. Привычки
    if show_habits and habits:
        habits_text = _build_task_list([], [], habits, is_premium)
        results.append(
            InlineQueryResultArticle(
                id="habits",
                title=f"Привычки ({len(habits)})",
                description="Ежедневные активности",
                input_message_content=InputTextMessageContent(habits_text, parse_mode="HTML"),
            )
        )
    
    # Если ничего не найдено
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="empty",
                title="Задачи не найдены",
                description="Добавьте миссии, цели или привычки в приложении",
                input_message_content=InputTextMessageContent(
                    "Задачи (пусто)\n\nДобавьте в @shaolen_bot"
                ),
            )
        )
    
    await query.answer(results, cache_time=60)


async def todo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /todo — отправить нативный Telegram Todo в этот чат (подключение только на время отправки)."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    await db.add_user(user.id, user.username, user.first_name, user.last_name)
    try:
        missions, goals, habits = await _fetch_user_tasks(user.id)
    except Exception as e:
        logger.exception("todo_handler fetch: %s", e)
        await update.message.reply_text("Не удалось загрузить задачи. Попробуйте позже.")
        return
    api_id = TELEGRAM_API_ID.strip()
    api_hash = (TELEGRAM_API_HASH or "").strip()
    ok, msg = await send_native_todo(
        chat.id,
        missions,
        goals,
        habits,
        api_id=int(api_id) if api_id.isdigit() else 0,
        api_hash=api_hash,
        bot_token=BOT_TOKEN,
    )
    await update.message.reply_text(msg)


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан. Добавьте в .env")
        return

    try:
        await db.init_db()
    except Exception as e:
        logger.warning("init_db: %s", e)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("todo", todo_handler))  # type: ignore[name-defined]
    app.add_handler(InlineQueryHandler(inline_query_handler))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот запущен")

    # Держим бота запущенным
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
