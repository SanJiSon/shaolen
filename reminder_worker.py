#!/usr/bin/env python3
"""
Воркер умных напоминаний: анализирует историю привычек и отправляет контекстные
напоминания в Telegram. Работает по московскому времени.
Запуск: python reminder_worker.py (в цикле каждые 5 мин) или через systemd:
  systemctl start goals-reminder
"""
import asyncio
import os
import logging
from datetime import datetime, date, time, timedelta

import httpx

try:
    from zoneinfo import ZoneInfo
    TZ_MOSCOW = ZoneInfo("Europe/Moscow")
except ImportError:
    TZ_MOSCOW = None
from dotenv import load_dotenv

from database import Database

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "goals_bot.db")
INTERVAL_SEC = int(os.getenv("REMINDER_INTERVAL_SEC", "300"))  # 5 мин
DEFAULT_AVG_HOUR, DEFAULT_AVG_MIN = 10, 0  # если нет истории выполнения

_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "reminder.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

DISABLE_HINT = (
    "\n\nКак отключить напоминания: открой приложение → Настройки (иконка шестерёнки) → отключи «Уведомления»."
)


def _parse_avg_time(avg_str: str):
    """Возвращает (hour, minute) из строки HH:MM или None."""
    if not avg_str or ":" not in avg_str:
        return None
    try:
        parts = avg_str.strip().split(":")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None


def _time_to_minutes(h: int, m: int) -> int:
    return h * 60 + m


def _minutes_to_time(m: int):
    m = m % (24 * 60)
    return m // 60, m % 60


async def send_telegram_message(chat_id: int, text: str) -> bool:
    if not BOT_TOKEN or not text:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text})
            if r.status_code != 200:
                logger.warning("Telegram sendMessage %s: %s", r.status_code, r.text)
                return False
            return True
    except Exception as e:
        logger.exception("send_telegram_message: %s", e)
        return False


def _in_quiet_hours(now: time, start_str: str, end_str: str) -> bool:
    """Проверка: сейчас в тихих часах? start/end в формате HH:MM."""
    if not start_str or not end_str:
        return False
    try:
        sh, sm = int(start_str[:2]), int(start_str[3:5])
        eh, em = int(end_str[:2]), int(end_str[3:5])
        now_min = now.hour * 60 + now.minute
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if start_min <= end_min:
            return start_min <= now_min < end_min
        return now_min >= start_min or now_min < end_min
    except (ValueError, IndexError):
        return False


def _build_habit_first_message(title: str, add_disable_hint: bool) -> str:
    lower = (title or "").lower()
    if "вод" in lower or "воды" in lower or "пить" in lower:
        msg = f"Обычно в это время ты пьёшь воду. Не пора ли выпить стакан воды? 💧"
    elif "зарядк" in lower or "спорт" in lower or "упражнен" in lower:
        msg = f"Обычно в это время — «{title}». Давай сделаем хотя бы немного? 💪"
    elif "чита" in lower or "книг" in lower:
        msg = f"Время для «{title}». Несколько страниц в подарок себе 📚"
    else:
        msg = f"Обычно в это время ты делаешь «{title}». Не пора ли отметить? ✨"
    if add_disable_hint:
        msg += DISABLE_HINT
    return msg


def _build_habit_second_message(title: str) -> str:
    return f"Ты ещё не отметил «{title}» сегодня. Напомню позже, если не успеешь."


def _build_habit_third_message(title: str) -> str:
    return f"Напоминание: «{title}». Можешь перенести на вечер — открой приложение и отметь, когда сделаешь."


def _now_moscow():
    """Текущее время в Москве (для напоминаний по МСК)."""
    if TZ_MOSCOW:
        return datetime.now(TZ_MOSCOW)
    return datetime.now()


async def run_tick(db: Database) -> None:
    now_dt = _now_moscow()
    now_time = now_dt.time()
    today = now_dt.date().isoformat()

    user_ids = await db.get_users_with_reminders_enabled()
    if not user_ids:
        return

    for user_id in user_ids:
        try:
            settings = await db.get_user_reminder_settings(user_id)
            if not settings.get("notifications_enabled", True):
                continue
            if _in_quiet_hours(
                now_time,
                settings.get("quiet_hours_start") or "",
                settings.get("quiet_hours_end") or "",
            ):
                continue
            intensity = int(settings.get("reminder_intensity") or 2)
            first_sent = settings.get("first_reminder_sent", False)

            habits = await db.get_habits_not_done_today(user_id)
            no_history_habits = []  # привычки без истории выполнения (старые пользователи)
            now_min = now_time.hour * 60 + now_time.minute
            default_first_lo = _time_to_minutes(DEFAULT_AVG_HOUR, DEFAULT_AVG_MIN) - 15  # 09:45
            default_first_hi = _time_to_minutes(DEFAULT_AVG_HOUR, DEFAULT_AVG_MIN) + 5   # 10:05

            for habit in habits:
                habit_id = habit["id"]
                title = (habit.get("title") or "").strip() or "Привычка"
                avg_str = await db.get_habit_avg_completion_time(habit_id, days=30)
                parsed = _parse_avg_time(avg_str)
                if parsed is None:
                    no_history_habits.append(habit)
                    continue
                h_avg, m_avg = parsed

                avg_min = _time_to_minutes(h_avg, m_avg)
                first_start = _minutes_to_time(avg_min - 15)
                first_end = _minutes_to_time(avg_min + 5)
                second_start = _minutes_to_time(avg_min + 30)
                second_end = _minutes_to_time(avg_min + 45)
                third_start = _minutes_to_time(avg_min + 120)
                third_end = _minutes_to_time(avg_min + 135)

                first_lo = _time_to_minutes(*first_start)
                first_hi = _time_to_minutes(*first_end)
                second_lo = _time_to_minutes(*second_start)
                second_hi = _time_to_minutes(*second_end)
                third_lo = _time_to_minutes(*third_start)
                third_hi = _time_to_minutes(*third_end)

                def in_window(lo: int, hi: int) -> bool:
                    if lo <= hi:
                        return lo <= now_min < hi
                    return now_min >= lo or now_min < hi

                if intensity >= 1 and in_window(first_lo, first_hi):
                    if await db.was_reminder_sent_today(user_id, habit_id, "habit_first"):
                        continue
                    text = _build_habit_first_message(title, add_disable_hint=not first_sent)
                    if await send_telegram_message(user_id, text):
                        await db.log_reminder_sent(user_id, "habit_first", habit_id=habit_id)
                        if not first_sent:
                            await db.set_first_reminder_sent(user_id)
                    continue

                if intensity >= 2 and in_window(second_lo, second_hi):
                    if await db.was_reminder_sent_today(user_id, habit_id, "habit_second"):
                        continue
                    text = _build_habit_second_message(title)
                    if await send_telegram_message(user_id, text):
                        await db.log_reminder_sent(user_id, "habit_second", habit_id=habit_id)
                    continue

                if intensity >= 3 and in_window(third_lo, third_hi):
                    if await db.was_reminder_sent_today(user_id, habit_id, "habit_third"):
                        continue
                    text = _build_habit_third_message(title)
                    if await send_telegram_message(user_id, text):
                        await db.log_reminder_sent(user_id, "habit_third", habit_id=habit_id)

            # Привычки без истории выполнения (пользователи до внедрения напоминаний): одно общее напоминание в 09:45–10:05
            if no_history_habits and intensity >= 1:
                if default_first_lo <= now_min < default_first_hi:
                    if not await db.was_reminder_sent_today(user_id, None, "habit_first_no_history"):
                        n = len(no_history_habits)
                        text = f"У тебя есть привычки на сегодня ({n}). Не забудь отметить их в приложении! ✨"
                        if not first_sent:
                            text += DISABLE_HINT
                        if await send_telegram_message(user_id, text):
                            await db.log_reminder_sent(user_id, "habit_first_no_history", habit_id=None)
                            if not first_sent:
                                await db.set_first_reminder_sent(user_id)

            # Напоминание за неделю до дедлайна миссии
            missions = await db.get_missions(user_id, include_completed=False)
            week_later = (now_dt.date() + timedelta(days=7)).isoformat()
            for mission in missions:
                deadline = mission.get("deadline")
                if not deadline:
                    continue
                try:
                    dl = deadline[:10] if isinstance(deadline, str) and len(deadline) >= 10 else deadline
                except Exception:
                    continue
                if dl != week_later:
                    continue
                mid = mission.get("id")
                mtitle = (mission.get("title") or "").strip() or "Миссия"
                if mid and not await db.was_reminder_sent_today_mission(user_id, mid, "mission_deadline_7"):
                    text = f"За неделю до дедлайна миссии: осталось 7 дней для завершения «{mtitle}» 📅"
                    if await send_telegram_message(user_id, text):
                        await db.log_reminder_sent(user_id, "mission_deadline_7", mission_id=mid)

            # Ежедневное напоминание о целях (раз в день, в 10:00 по умолчанию)
            if now_time.hour == 10 and now_time.minute < 15:
                if not await db.was_reminder_sent_today(user_id, None, "goal_daily"):
                    goals = await db.get_goals(user_id, include_completed=False)
                    if goals:
                        n = len(goals)
                        text = f"У тебя {n} незавершённых целей на сегодня. Загляни в приложение! 🎯"
                        if await send_telegram_message(user_id, text):
                            await db.log_reminder_sent(user_id, "goal_daily")
        except Exception as e:
            logger.exception("reminder user %s: %s", user_id, e)


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан. Задайте в .env")
        return
    db = Database(DB_PATH)
    await db.init_db()
    logger.info("Reminder worker started (interval=%ss, timezone=Europe/Moscow)", INTERVAL_SEC)
    while True:
        try:
            await run_tick(db)
        except Exception as e:
            logger.exception("run_tick: %s", e)
        await asyncio.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
