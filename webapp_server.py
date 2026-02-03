import base64
import io
import os
import re
import json
import hmac
import hashlib
from urllib.parse import quote, urlencode
import subprocess
from contextlib import asynccontextmanager
from urllib.parse import unquote
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import logging

import asyncio

import aiosqlite
import httpx

from database import Database

try:
    from groq import Groq
except ImportError:
    Groq = None

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
LIMIT_SHAOLEN_PER_DAY = 50
GOOGLE_FIT_CLIENT_ID = os.getenv("GOOGLE_FIT_CLIENT_ID", "")
GOOGLE_FIT_CLIENT_SECRET = os.getenv("GOOGLE_FIT_CLIENT_SECRET", "")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "").rstrip("/")  # https://your-domain.com

# Списки моделей по приоритету: при 429 (лимит Groq) пробуем следующую. Для пользователя без изменений.
# Чтобы добавить новую модель — допишите строку в нужный список.
SHAOLEN_TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
SHAOLEN_VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
]


def validate_telegram_init_data(init_data: str) -> Optional[dict]:
    """Проверяет подпись Telegram WebApp initData и возвращает данные (в т.ч. user) или None."""
    if not init_data or not BOT_TOKEN:
        return None
    data = {}
    hash_val = ""
    for part in init_data.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k == "hash":
            hash_val = v
            continue
        data[k] = unquote(v)
    if not hash_val or "user" not in data:
        return None
    check_str = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, hash_val):
        return None
    try:
        data["_user"] = json.loads(data["user"])
    except Exception:
        return None
    return data

# Настройка логирования (консоль + файл для админки и просмотра логов)
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "webapp.log")
_fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=_fmt)
logger = logging.getLogger(__name__)
try:
    _fh = logging.FileHandler(_log_file, encoding="utf-8")
    _fh.setFormatter(logging.Formatter(_fmt))
    logging.getLogger().addHandler(_fh)
except Exception:
    pass

db = Database()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await db.init_db()
        logger.info(f"База данных инициализирована: {db.db_path}")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise
    yield
    # Shutdown (если нужно)

app = FastAPI(title="Goals WebApp API", lifespan=lifespan)


class MissionCreate(BaseModel):
    user_id: int
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None


class SubgoalCreate(BaseModel):
    title: str
    description: Optional[str] = ""


class SubgoalsOrderBody(BaseModel):
    subgoal_ids: List[int]


class MissionsOrderBody(BaseModel):
    mission_ids: List[int]


class GoalsOrderBody(BaseModel):
    goal_ids: List[int]


class HabitsOrderBody(BaseModel):
    habit_ids: List[int]


class GoalCreate(BaseModel):
    user_id: int
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None
    priority: int = 1


class HabitCreate(BaseModel):
    user_id: int
    title: str
    description: Optional[str] = ""
    reminder_time: Optional[str] = None
    category_id: Optional[int] = None


class MissionUpdate(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None


class GoalUpdate(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None
    priority: int = 1
    is_pinned: Optional[bool] = None


class HabitUpdate(BaseModel):
    title: str
    description: Optional[str] = ""
    reminder_time: Optional[str] = None
    category_id: Optional[int] = None


class TimeCapsuleCreate(BaseModel):
    title: str
    expected_result: str
    open_in_days: int = 0
    open_in_hours: float = 24.0


class TimeCapsuleUpdate(BaseModel):
    title: str
    expected_result: str
    open_in_days: int = 0
    open_in_hours: float = 24.0


class CapsuleReflectionBody(BaseModel):
    reflection: str = ""


# Инициализация БД теперь в lifespan выше


# Middleware: проверка Telegram initData для /api/user/... и привязка к реальному user_id
@app.middleware("http")
async def check_telegram_user(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/user/"):
        raw = request.headers.get("X-Telegram-Init-Data", "").strip()
        parsed = validate_telegram_init_data(raw)
        if not parsed:
            logger.warning(f"⛔ Нет или неверный X-Telegram-Init-Data для {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Откройте приложение из Telegram. Данные пользователя не прошли проверку."},
            )
        u = parsed.get("_user") or {}
        tg_user_id = u.get("id")
        if tg_user_id is None:
            return JSONResponse(status_code=401, content={"detail": "В initData нет пользователя."})
        try:
            path_user_id = int(path.split("/")[3])
        except (IndexError, ValueError):
            path_user_id = None
        if path_user_id is not None and int(tg_user_id) != path_user_id:
            logger.warning(f"⛔ user_id в пути ({path_user_id}) не совпадает с Telegram ({tg_user_id})")
            return JSONResponse(status_code=403, content={"detail": "Доступ запрещён для этого пользователя."})
        await db.add_user(
            int(tg_user_id),
            username=u.get("username"),
            first_name=u.get("first_name"),
            last_name=u.get("last_name"),
        )
        request.state.telegram_user_id = int(tg_user_id)
    response = await call_next(request)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    path = request.url.path
    method = request.method
    logger.info(f"📥 {method} {path} - IP: {request.client.host if request.client else 'unknown'}")
    response = await call_next(request)
    logger.info(f"📤 {method} {path} - Status: {response.status_code}")
    return response


# CORS (для локальной разработки удобно открыть для всех источников)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Примечание: Если используешь Nginx для статики, эта часть не нужна
# Nginx отдает HTML/CSS/JS, а FastAPI только обрабатывает API запросы
# 
# Если статика отдается через Nginx, можно закомментировать блок ниже
# и оставить только API endpoints

# Статика — опционально, если не используешь Nginx
# Раскомментируй, если нужна отдача статики через FastAPI
"""
static_dir = os.path.join(os.path.dirname(__file__), "webapp")
os.makedirs(static_dir, exist_ok=True)

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebApp not found</h1>", status_code=404)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
"""


@app.get("/api/health", response_model=None)
async def api_health():
    """Проверка доступности API. Вызови: curl http://localhost:8000/api/health"""
    logger.info("📥 GET /api/health - проверка здоровья API")
    return JSONResponse(content={"status": "ok", "service": "goals-api"})


@app.get("/api/me", response_model=None)
async def api_me(request: Request):
    """
    Определение пользователя по X-Telegram-Init-Data.
    Используется, когда в WebApp приходит пустой initDataUnsafe.user (например на части клиентов).
    """
    raw = request.headers.get("X-Telegram-Init-Data", "").strip()
    parsed = validate_telegram_init_data(raw)
    if not parsed:
        logger.warning("⛔ GET /api/me — нет или неверный X-Telegram-Init-Data")
        return JSONResponse(
            status_code=401,
            content={"detail": "Откройте приложение из Telegram. Данные пользователя не прошли проверку."},
        )
    u = parsed.get("_user") or {}
    tg_user_id = u.get("id")
    if tg_user_id is None:
        return JSONResponse(status_code=401, content={"detail": "В initData нет пользователя."})
    await db.add_user(
        int(tg_user_id),
        username=u.get("username"),
        first_name=u.get("first_name"),
        last_name=u.get("last_name"),
    )
    return JSONResponse(content={
        "user_id": int(tg_user_id),
        "first_name": u.get("first_name"),
        "last_name": u.get("last_name"),
        "username": u.get("username"),
    })


@app.put("/api/user/{user_id}/missions/order")
async def api_set_missions_order(user_id: int, payload: MissionsOrderBody):
    """Изменить порядок миссий (перетаскивание)."""
    if payload.mission_ids:
        await db.set_missions_order(user_id, payload.mission_ids)
    return JSONResponse(content={"ok": True})


@app.get("/api/user/{user_id}/missions", response_model=None)
async def api_get_missions(user_id: int):
    """Получение миссий пользователя (user_id проверен через initData в middleware)."""
    try:
        logger.info(f"Запрос миссий для пользователя {user_id}")
        missions = await db.get_missions(user_id, include_completed=True)
        logger.info(f"Найдено миссий: {len(missions) if missions else 0}")
        
        # Преобразуем данные для JSON (убираем None, конвертируем типы)
        result = []
        for mission in (missions or []):
            clean_mission = {}
            for key, value in mission.items():
                if value is None:
                    clean_mission[key] = None
                elif isinstance(value, (int, float, bool, str)):
                    clean_mission[key] = value
                else:
                    clean_mission[key] = str(value)
            result.append(clean_mission)
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения миссий для пользователя {user_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


def _row_to_json(obj):
    """Приводит строку БД/словарь к JSON-сериализуемому виду."""
    if obj is None:
        return None
    try:
        d = dict(obj) if hasattr(obj, "keys") else obj
        if not isinstance(d, dict):
            return None
        out = {}
        for k, v in d.items():
            key = str(k) if k is not None else ""
            if v is None:
                out[key] = None
            elif hasattr(v, "isoformat"):
                out[key] = v.isoformat()
            elif isinstance(v, (int, float, bool, str)):
                out[key] = v
            else:
                out[key] = str(v)
        return out
    except Exception:
        return None


@app.post("/api/missions")
async def api_add_mission(payload: MissionCreate):
    """Добавление миссии"""
    await db.add_user(payload.user_id, None)
    mission_id = await db.add_mission(
        payload.user_id, payload.title, payload.description or "", payload.deadline
    )
    mission = await db.get_mission(mission_id)
    return JSONResponse(content=_row_to_json(mission) or {})


@app.put("/api/missions/{mission_id}")
async def api_update_mission(mission_id: int, payload: MissionUpdate):
    """Редактирование миссии"""
    await db.update_mission(
        mission_id, payload.title, payload.description or "", payload.deadline
    )
    mission = await db.get_mission(mission_id)
    return JSONResponse(content=_row_to_json(mission) or {})


@app.post("/api/missions/{mission_id}/complete")
async def api_complete_mission(mission_id: int):
    """Отметить миссию как выполненную"""
    await db.complete_mission(mission_id)
    mission = await db.get_mission(mission_id)
    return JSONResponse(content=_row_to_json(mission) or {})


@app.post("/api/goals/{goal_id}/complete")
async def api_complete_goal(goal_id: int):
    """Отметить цель как выполненную"""
    await db.complete_goal(goal_id)
    goal = await db.get_goal(goal_id)
    return JSONResponse(content=_row_to_json(goal) or {})


@app.post("/api/goals/{goal_id}/uncomplete")
async def api_uncomplete_goal(goal_id: int):
    """Снять отметку выполнения цели"""
    await db.uncomplete_goal(goal_id)
    goal = await db.get_goal(goal_id)
    return JSONResponse(content=_row_to_json(goal) or {})


@app.post("/api/missions/{mission_id}/subgoals")
async def api_add_subgoal(mission_id: int, payload: SubgoalCreate):
    """Добавить подцель к миссии"""
    subgoal_id = await db.add_subgoal(
        mission_id, payload.title, payload.description or ""
    )
    subgoal = await db.get_subgoal(subgoal_id)
    return JSONResponse(content=_row_to_json(subgoal) or {})


@app.post("/api/subgoals/{subgoal_id}/complete")
async def api_complete_subgoal(subgoal_id: int):
    """Отметить подцель как выполненную"""
    await db.complete_subgoal(subgoal_id)
    subgoal = await db.get_subgoal(subgoal_id)
    return JSONResponse(content=_row_to_json(subgoal) or {})


@app.post("/api/subgoals/{subgoal_id}/uncomplete")
async def api_uncomplete_subgoal(subgoal_id: int):
    """Снять отметку выполнения подцели"""
    await db.uncomplete_subgoal(subgoal_id)
    subgoal = await db.get_subgoal(subgoal_id)
    return JSONResponse(content=_row_to_json(subgoal) or {})


@app.put("/api/subgoals/{subgoal_id}")
@app.post("/api/subgoals/{subgoal_id}/update")
async def api_update_subgoal(subgoal_id: int, payload: SubgoalCreate):
    """Редактировать подцель (название и описание). PUT или POST .../update."""
    try:
        title = payload.title if payload.title is not None else ""
        description = payload.description if payload.description is not None else ""
        ok = await db.update_subgoal(subgoal_id, title, description)
        if not ok:
            return JSONResponse(content={"error": "not_found"}, status_code=404)
        subgoal = await db.get_subgoal(subgoal_id)
        if not subgoal:
            return JSONResponse(content={"error": "not_found"}, status_code=404)
        return JSONResponse(content=_row_to_json(subgoal) or {})
    except Exception as e:
        logger.exception("Ошибка обновления подцели %s: %s", subgoal_id, e)
        return JSONResponse(
            content={"error": "server_error", "detail": str(e)},
            status_code=500,
        )


@app.delete("/api/subgoals/{subgoal_id}")
async def api_delete_subgoal(subgoal_id: int):
    """Удалить подцель"""
    sg = await db.get_subgoal(subgoal_id)
    if sg:
        mission_id = sg.get("mission_id")
        if mission_id is not None:
            mission = await db.get_mission(mission_id)
            if mission:
                user_id = mission.get("user_id")
                if user_id is not None:
                    await _delete_calendar_event_for_entity(user_id, "subgoal", subgoal_id)
    await db.delete_subgoal(subgoal_id)
    return JSONResponse(content={"ok": True})


@app.put("/api/mission/{mission_id}/subgoals/order")
async def api_set_subgoals_order(mission_id: int, payload: SubgoalsOrderBody):
    """Изменить порядок подцелей миссии (перетаскивание)."""
    if payload.subgoal_ids:
        await db.set_subgoals_order(mission_id, payload.subgoal_ids)
    return JSONResponse(content={"ok": True})


@app.get("/api/mission/{mission_id}/subgoals", response_model=None)
async def api_get_subgoals(mission_id: int):
    try:
        subgoals = await db.get_subgoals(mission_id)
        result = []
        for subgoal in (subgoals or []):
            clean_subgoal = {}
            for key, value in subgoal.items():
                if value is None:
                    clean_subgoal[key] = None
                elif key == "is_completed":
                    clean_subgoal[key] = 1 if (value and value != 0 and value != "0") else 0
                elif isinstance(value, (int, float, bool, str)):
                    clean_subgoal[key] = value
                else:
                    clean_subgoal[key] = str(value)
            result.append(clean_subgoal)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения подцелей для миссии {mission_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


@app.put("/api/user/{user_id}/goals/order")
async def api_set_goals_order(user_id: int, payload: GoalsOrderBody):
    """Изменить порядок целей (перетаскивание)."""
    if payload.goal_ids:
        await db.set_goals_order(user_id, payload.goal_ids)
    return JSONResponse(content={"ok": True})


@app.get("/api/user/{user_id}/goals", response_model=None)
async def api_get_goals(user_id: int):
    """Получение целей пользователя (user_id проверен через initData в middleware)."""
    try:
        logger.info(f"Запрос целей для пользователя {user_id}")
        goals = await db.get_goals(user_id, include_completed=True)
        logger.info(f"Найдено целей: {len(goals) if goals else 0}")
        
        # Преобразуем данные для JSON
        result = []
        for goal in (goals or []):
            clean_goal = {}
            for key, value in goal.items():
                if value is None:
                    clean_goal[key] = None
                elif isinstance(value, (int, float, bool, str)):
                    clean_goal[key] = value
                else:
                    clean_goal[key] = str(value)
            result.append(clean_goal)
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения целей для пользователя {user_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


@app.post("/api/goals")
async def api_add_goal(payload: GoalCreate):
    """Добавление цели"""
    await db.add_user(payload.user_id, None)
    goal_id = await db.add_goal(
        payload.user_id,
        payload.title,
        payload.description or "",
        payload.deadline,
        payload.priority,
    )
    goals = await db.get_goals(payload.user_id, include_completed=True)
    for g in goals:
        if g["id"] == goal_id:
            return JSONResponse(content=_row_to_json(g))
    raise HTTPException(status_code=404, detail="Goal not found after insert")


@app.put("/api/goals/{goal_id}")
async def api_update_goal(goal_id: int, payload: GoalUpdate):
    """Редактирование цели"""
    await db.update_goal(
        goal_id, payload.title, payload.description or "", payload.deadline, payload.priority,
        is_pinned=payload.is_pinned
    )
    goal = await db.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return JSONResponse(content=_row_to_json(goal))


@app.put("/api/user/{user_id}/habits/order")
async def api_set_habits_order(user_id: int, payload: HabitsOrderBody):
    """Изменить порядок привычек (перетаскивание)."""
    if payload.habit_ids:
        await db.set_habits_order(user_id, payload.habit_ids)
    return JSONResponse(content={"ok": True})


@app.get("/api/user/{user_id}/habits", response_model=None)
async def api_get_habits(user_id: int, category_id: Optional[int] = None):
    """Получение привычек пользователя. category_id — фильтр по категории (опционально)."""
    try:
        logger.info(f"Запрос привычек для пользователя {user_id}")
        habits = await db.get_habits(user_id, active_only=False, category_id=category_id)
        logger.info(f"Найдено привычек: {len(habits) if habits else 0}")
        
        # Преобразуем данные для JSON
        result = []
        for habit in (habits or []):
            clean_habit = {}
            for key, value in habit.items():
                if key == 'today_count':
                    # Убеждаемся, что счетчик - это число
                    clean_habit[key] = int(value) if value is not None else 0
                elif value is None:
                    clean_habit[key] = None
                elif isinstance(value, (int, float, bool, str)):
                    clean_habit[key] = value
                else:
                    clean_habit[key] = str(value)
            hid = habit.get("id")
            streak = await db.get_habit_streak_for_habit(hid, days=365) if hid else 0
            total_completions = await db.get_habit_total_completions(hid) if hid else 0
            clean_habit["streak"] = streak
            clean_habit["total_completions"] = total_completions
            result.append(clean_habit)

        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения привычек для пользователя {user_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


@app.get("/api/user/{user_id}/habit-categories", response_model=None)
async def api_get_habit_categories(user_id: int):
    """Список категорий привычек (для фильтра и выбора цвета в календаре)."""
    categories = await db.get_habit_categories()
    return JSONResponse(content=categories)


class HabitCategoryColorBody(BaseModel):
    category_id: int
    color_id: Optional[str] = None


class HabitCategoriesColorsBody(BaseModel):
    categories: List[dict]  # [{ category_id, color_id }, ...]


@app.put("/api/user/{user_id}/habit-categories/colors", response_model=None)
async def api_set_habit_categories_colors(user_id: int, payload: HabitCategoriesColorsBody):
    """Обновить цвета категорий для календаря (color_id "1"—"11" или null)."""
    for item in (payload.categories or []):
        cid = item.get("category_id")
        color_id = item.get("color_id")
        if cid is not None:
            await db.set_habit_category_color(int(cid), (color_id or "").strip() or None)
    return JSONResponse(content={"ok": True})


@app.post("/api/habits")
async def api_add_habit(payload: HabitCreate):
    """Добавление привычки"""
    await db.add_user(payload.user_id, None)
    habit_id = await db.add_habit(
        payload.user_id,
        payload.title,
        payload.description or "",
        reminder_time=payload.reminder_time,
        category_id=payload.category_id,
    )
    habits = await db.get_habits(payload.user_id, active_only=False)
    for h in habits:
        if h["id"] == habit_id:
            return JSONResponse(content=_row_to_json(h))
    raise HTTPException(status_code=404, detail="Habit not found after insert")


@app.put("/api/habits/{habit_id}")
async def api_update_habit(habit_id: int, payload: HabitUpdate):
    """Редактирование привычки"""
    await db.update_habit(habit_id, payload.title, payload.description or "", reminder_time=payload.reminder_time, category_id=payload.category_id)
    habit = await db.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return JSONResponse(content=_row_to_json(habit))


class HabitReminderUpdate(BaseModel):
    enabled: bool


@app.put("/api/habits/{habit_id}/reminder")
async def api_set_habit_reminder(habit_id: int, payload: HabitReminderUpdate):
    """Включить/выключить напоминания для привычки."""
    habit = await db.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    await db.set_habit_reminder_enabled(habit_id, payload.enabled)
    return JSONResponse(content={"ok": True, "reminders_enabled": payload.enabled})


def _send_achievement_telegram(user_id: int, habit_title: str) -> None:
    """Отправляет уведомление о достижении 21 в Telegram."""
    if not BOT_TOKEN or not user_id:
        return
    msg = (
        f"🏆 *Достижение разблокировано!*\n\n"
        f"*{habit_title}*\n\n"
        f"Ты молодец! 21 повторение — это отличный результат! Продолжай в том же духе! 💪✨"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        import asyncio
        async def _send():
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"chat_id": user_id, "text": msg, "parse_mode": "Markdown"})
        asyncio.create_task(_send())
    except Exception as e:
        logger.warning("Не удалось отправить уведомление о достижении: %s", e)


@app.post("/api/habits/{habit_id}/increment")
async def api_increment_habit(habit_id: int):
    """Увеличить счетчик привычки на 1. Возвращает achievement_unlocked, habit_title при достижении 21."""
    try:
        count = await db.increment_habit_count(habit_id)
        result = {"count": count}
        try:
            habit = await db.get_habit(habit_id)
            if habit:
                total = await db.get_habit_total_completions(habit_id)
                notified = habit.get("achievement_21_notified") or 0
                if total >= 21 and not notified:
                    await db.set_habit_achievement_notified(habit_id)
                    title = (habit.get("title") or "").strip() or "Привычка"
                    result["achievement_unlocked"] = True
                    result["habit_title"] = title
        except Exception as ae:
            logger.warning("achievement-check при increment: %s", ae)
        return result
    except Exception as e:
        logger.error(f"Ошибка увеличения счетчика привычки {habit_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/habits/{habit_id}/decrement")
async def api_decrement_habit(habit_id: int):
    """Уменьшить счетчик привычки на 1"""
    try:
        count = await db.decrement_habit_count(habit_id)
        return {"count": count}
    except Exception as e:
        logger.error(f"Ошибка уменьшения счетчика привычки {habit_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/missions/{mission_id}")
async def api_delete_mission(mission_id: int):
    """Удаление миссии и её подцелей"""
    try:
        mission = await db.get_mission(mission_id)
        if mission:
            user_id = mission.get("user_id")
            if user_id is not None:
                subgoals = await db.get_subgoals(mission_id)
                for sg in subgoals:
                    sgid = sg.get("id")
                    if sgid is not None:
                        await _delete_calendar_event_for_entity(user_id, "subgoal", sgid)
        await db.delete_mission(mission_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления миссии {mission_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/goals/{goal_id}")
async def api_delete_goal(goal_id: int):
    """Удаление цели"""
    try:
        goal = await db.get_goal(goal_id)
        if goal:
            user_id = goal.get("user_id")
            if user_id is not None:
                await _delete_calendar_event_for_entity(user_id, "goal", goal_id)
        await db.delete_goal(goal_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления цели {goal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/habits/{habit_id}")
async def api_delete_habit(habit_id: int):
    """Удаление привычки"""
    try:
        habit = await db.get_habit(habit_id)
        if habit:
            user_id = habit.get("user_id")
            if user_id is not None:
                await _delete_calendar_event_for_entity(user_id, "habit", habit_id)
        await db.delete_habit(habit_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления привычки {habit_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    gender: Optional[str] = None  # "m" / "f" / ""
    weight: Optional[float] = None
    height: Optional[float] = None
    age: Optional[int] = None
    target_weight: Optional[float] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None  # ISO 2 буквы для геокодинга (Москва → RU)
    geo_consent: Optional[bool] = None


class ReminderSettingsUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None  # "HH:MM" или null
    quiet_hours_end: Optional[str] = None
    reminder_intensity: Optional[int] = None  # 1–3


class ShaolenAsk(BaseModel):
    message: Optional[str] = ""  # текст или пусто, если отправлено голосовое (тогда используется транскрипция)
    image_base64: Optional[str] = None  # data:image/jpeg;base64,... или только base64
    audio_base64: Optional[str] = None  # голосовое сообщение: base64 ogg/m4a/wav/webm (транскрибируется через Groq Whisper)
    history: Optional[List[Dict[str, Any]]] = None  # [{"role":"user"|"assistant","content":"..."}] — контекст диалога


def _profile_out(user: dict) -> dict:
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username") or "",
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "display_name": (user.get("display_name") or "").strip() or "",
        "gender": (user.get("gender") or "").strip() or "",
        "weight": user.get("weight"),
        "height": user.get("height"),
        "age": user.get("age"),
        "target_weight": user.get("target_weight"),
        "city": (user.get("city") or "").strip() or None,
        "country": (user.get("country") or "").strip() or None,
        "country_code": (user.get("country_code") or "").strip().upper() or None,
        "geo_consent": bool(user.get("geo_consent")),
    }


@app.get("/api/user/{user_id}/reminder-settings", response_model=None)
async def api_get_reminder_settings(user_id: int):
    """Настройки умных напоминаний: уведомления вкл/выкл, тихие часы, интенсивность."""
    settings = await db.get_user_reminder_settings(user_id)
    return JSONResponse(content=settings)


@app.put("/api/user/{user_id}/reminder-settings")
async def api_update_reminder_settings(user_id: int, payload: ReminderSettingsUpdate):
    """Сохранить настройки напоминаний."""
    await db.set_user_reminder_settings(
        user_id,
        notifications_enabled=payload.notifications_enabled,
        quiet_hours_start=payload.quiet_hours_start,
        quiet_hours_end=payload.quiet_hours_end,
        reminder_intensity=payload.reminder_intensity,
    )
    settings = await db.get_user_reminder_settings(user_id)
    return JSONResponse(content=settings)


# --- Google Fit (шаги) и Calendar (выгрузка событий) ---
# calendar — полный доступ к календарю (создание событий). calendar.events иногда даёт 403.
GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/fitness.activity.read "
    "https://www.googleapis.com/auth/calendar"
)


def _google_fit_state_encode(user_id: int) -> str:
    """Кодируем state для OAuth: user_id + подпись."""
    sig = hmac.new(
        (BOT_TOKEN or "fit").encode(),
        str(user_id).encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    raw = f"{user_id}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _google_fit_state_decode(state: str) -> Optional[int]:
    """Декодируем и проверяем state, возвращаем user_id или None."""
    try:
        padded = state + "=" * (4 - len(state) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        uid_s, sig = raw.split(":", 1)
        uid = int(uid_s)
        expected = hmac.new(
            (BOT_TOKEN or "fit").encode(),
            str(uid).encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return uid
    except Exception:
        return None


@app.get("/api/user/{user_id}/google-fit/auth-url", response_model=None)
async def api_google_fit_auth_url(user_id: int):
    """URL для авторизации Google Fit (открыть в браузере)."""
    if not GOOGLE_FIT_CLIENT_ID or not WEBAPP_BASE_URL:
        return JSONResponse(
            status_code=503,
            content={"detail": "Google Fit не настроен на сервере."},
        )
    redirect_uri = f"{WEBAPP_BASE_URL}/api/google-fit/callback"
    state = _google_fit_state_encode(user_id)
    params = {
        "client_id": GOOGLE_FIT_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return JSONResponse(content={"auth_url": url})


@app.get("/api/google-fit/callback")
async def api_google_fit_callback(request: Request, code: str = "", state: str = ""):
    """OAuth callback от Google. Сохраняет токены и редирект на страницу успеха."""
    if not code or not state:
        return JSONResponse(
            status_code=400,
            content={"detail": "Отсутствуют code или state."},
        )
    user_id = _google_fit_state_decode(state)
    if user_id is None:
        return JSONResponse(status_code=400, content={"detail": "Неверный state."})
    if not GOOGLE_FIT_CLIENT_ID or not GOOGLE_FIT_CLIENT_SECRET or not WEBAPP_BASE_URL:
        return JSONResponse(status_code=503, content={"detail": "Google Fit не настроен."})
    redirect_uri = f"{WEBAPP_BASE_URL}/api/google-fit/callback"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_FIT_CLIENT_ID,
                "client_secret": GOOGLE_FIT_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        logger.warning("Google token exchange failed: %s %s", r.status_code, r.text)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content="<html><body><h1>Ошибка авторизации</h1><p>Не удалось получить доступ к Google Fit. Попробуйте снова.</p></body></html>",
            status_code=400,
        )
    data = r.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)
    if not access:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content="<html><body><h1>Ошибка</h1><p>Нет access_token в ответе Google.</p></body></html>",
            status_code=500,
        )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    await db.save_google_fit_tokens(user_id, access, refresh, expires_at)
    logger.info("Google Fit tokens saved for user %s", user_id)
    from fastapi.responses import RedirectResponse
    success_url = f"{WEBAPP_BASE_URL}/google-fit-success.html"
    return RedirectResponse(url=success_url, status_code=302)


@app.get("/api/user/{user_id}/google-fit/status", response_model=None)
async def api_google_fit_status(user_id: int):
    """Подключён ли Google Fit."""
    tokens = await db.get_google_fit_tokens(user_id)
    return JSONResponse(content={"connected": tokens is not None})


@app.get("/api/user/{user_id}/google-fit/steps", response_model=None)
async def api_google_fit_steps(user_id: int):
    """Количество шагов за сегодня (по Google Fit)."""
    tokens = await db.get_google_fit_tokens(user_id)
    if not tokens:
        return JSONResponse(content={"steps": None, "error": "not_connected"})
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")
    now = datetime.now(timezone.utc)
    if expires_at and isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_at = None
    if expires_at and (now - timedelta(minutes=5)) >= expires_at and refresh:
        async with httpx.AsyncClient() as client:
            rr = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_FIT_CLIENT_ID,
                    "client_secret": GOOGLE_FIT_CLIENT_SECRET,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if rr.status_code == 200:
            rdata = rr.json()
            access = rdata.get("access_token")
            exp = rdata.get("expires_in", 3600)
            new_expires = now + timedelta(seconds=exp)
            await db.save_google_fit_tokens(user_id, access, refresh, new_expires)
    if not access:
        return JSONResponse(content={"steps": None, "error": "token_expired"})
    tz = timezone.utc
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(today_start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.step_count.delta"}],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": str(start_ms),
        "endTimeMillis": str(end_ms),
    }
    try:
        async with httpx.AsyncClient() as client:
            fr = await client.post(
                "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate",
                json=body,
                headers={"Authorization": f"Bearer {access}"},
            )
    except Exception as e:
        logger.exception("Google Fitness API error: %s", e)
        return JSONResponse(content={"steps": None, "error": "api_error"})
    if fr.status_code != 200:
        logger.warning("Fitness API %s: %s", fr.status_code, fr.text)
        return JSONResponse(content={"steps": None, "error": "api_error"})
    data = fr.json()
    total = 0
    for bucket in data.get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                for v in pt.get("value", []):
                    total += int(v.get("intVal", 0))
    return JSONResponse(content={"steps": total})


@app.delete("/api/user/{user_id}/google-fit")
async def api_google_fit_disconnect(user_id: int):
    """Отключить Google Fit."""
    await db.delete_google_fit_tokens(user_id)
    return JSONResponse(content={"ok": True})


# --- Синхронизация с Google Календарь ---
def _habit_suggested_time(title: str, index: int, total: int) -> tuple:
    """
    Определяет рекомендуемое время для привычки по названию.
    Возвращает (hour, minute). Распределяет равномерно в течение дня (6–22 ч).
    """
    t = (title or "").lower()
    # Вода: равномерно в течение дня — 8, 11, 14, 17, 20
    if any(x in t for x in ["вод", "воды", "пить", "воду"]):
        slots = [(8, 0), (11, 0), (14, 0), (17, 0), (20, 0)]
        h, m = slots[index % len(slots)]
        return h, m
    # Утренние: зарядка, спорт, витамины — 6:30–8:30
    if any(x in t for x in ["зарядк", "спорт", "упражнен", "витамин", "утр", "таблет", "разминк"]):
        return 7 + (index % 2), 0 if index % 2 == 0 else 30
    # Вечерние: чтение, медитация, дневник, сон — 20–22
    if any(x in t for x in ["чита", "книг", "медитац", "дневник", "сон", "спат", "отдых", "расслаб"]):
        return 20 + (index % 3), 0
    # Дневные: прогулка, ходьба, растяжка — 12, 18
    if any(x in t for x in ["прогулк", "ходьб", "растяжк"]):
        return 12 if index % 2 == 0 else 18, 0
    # По умолчанию: равномерно 8–20
    if total <= 0:
        total = 1
    step = max(1, (20 - 8) // total)
    h = 8 + (index * step) % 12
    return min(h, 20), 0


@app.get("/api/user/{user_id}/calendar-sync-settings", response_model=None)
async def api_calendar_sync_settings(user_id: int):
    """Настройки выгрузки в Google Календарь."""
    settings = await db.get_calendar_sync_settings(user_id)
    return JSONResponse(content=settings)


class CalendarSyncSettingsBody(BaseModel):
    sync_subgoals: Optional[bool] = None
    sync_habits: Optional[bool] = None
    sync_goals: Optional[bool] = None
    event_color_id: Optional[str] = None
    use_dedicated_calendar_for_color: Optional[bool] = None


@app.put("/api/user/{user_id}/calendar-sync-settings", response_model=None)
async def api_update_calendar_sync_settings(user_id: int, payload: CalendarSyncSettingsBody):
    """Сохранить настройки выгрузки в календарь."""
    cur = await db.get_calendar_sync_settings(user_id)
    sync_subgoals = payload.sync_subgoals if payload.sync_subgoals is not None else cur["sync_subgoals"]
    sync_habits = payload.sync_habits if payload.sync_habits is not None else cur["sync_habits"]
    sync_goals = payload.sync_goals if payload.sync_goals is not None else cur["sync_goals"]
    event_color_id = payload.event_color_id if payload.event_color_id is not None else cur.get("event_color_id")
    use_dedicated = payload.use_dedicated_calendar_for_color if payload.use_dedicated_calendar_for_color is not None else cur.get("use_dedicated_calendar_for_color", False)
    await db.set_calendar_sync_settings(user_id, sync_subgoals, sync_habits, sync_goals, event_color_id, use_dedicated)
    return JSONResponse(content={"ok": True})


def _calendar_base_url(calendar_id: str) -> str:
    """URL-путь календаря: primary без кодирования, иначе id кодируем (например @ -> %40)."""
    if calendar_id == "primary":
        return "https://www.googleapis.com/calendar/v3/calendars/primary"
    return "https://www.googleapis.com/calendar/v3/calendars/" + quote(calendar_id, safe="")


async def _delete_calendar_event_for_entity(user_id: int, entity_type: str, entity_id: int) -> None:
    """Удалить событие календаря для сущности (привычка/цель/подцель): из БД и в Google."""
    ce = await db.delete_calendar_event(user_id, entity_type, entity_id)
    if not ce or not ce.get("event_id"):
        return
    tokens = await db.get_google_fit_tokens(user_id)
    if not tokens:
        return
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")
    now = datetime.now(timezone.utc)
    if expires_at and isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_at = None
    if expires_at and (now - timedelta(minutes=5)) >= expires_at and refresh:
        async with httpx.AsyncClient(timeout=30.0) as client:
            rr = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_FIT_CLIENT_ID,
                    "client_secret": GOOGLE_FIT_CLIENT_SECRET,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if rr.status_code == 200:
                rdata = rr.json()
                access = rdata.get("access_token")
                exp = rdata.get("expires_in", 3600)
                await db.save_google_fit_tokens(user_id, access, refresh, now + timedelta(seconds=exp))
    if not access:
        return
    base = _calendar_base_url(ce.get("calendar_id") or "primary")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.delete(
                f"{base}/events/{ce['event_id']}",
                headers={"Authorization": f"Bearer {access}"},
            )
    except Exception as e:
        logger.warning("calendar delete event %s %s: %s", entity_type, entity_id, e)


async def _ensure_shaolen_calendar(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    user_id: int,
    event_color_id: Optional[str],
    settings: Dict[str, Any],
) -> str:
    """
    Если выбран цвет — вернуть id календаря «Шаолень Привычки» (создать при необходимости)
    и задать цвет на уровне календаря (CalendarList), чтобы на iOS отображался правильный цвет.
    Иначе — primary.
    """
    if not event_color_id:
        return "primary"
    existing_id = (settings.get("shaolen_calendar_id") or "").strip() or None
    if existing_id:
        r = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{quote(existing_id, safe='')}",
            headers=headers,
        )
        if r.status_code == 200:
            # Обновить цвет календаря в списке (на случай смены цвета в настройках)
            await client.patch(
                f"https://www.googleapis.com/calendar/v3/users/me/calendarList/{quote(existing_id, safe='')}",
                json={"colorId": event_color_id},
                headers=headers,
            )
            return existing_id
        # Календарь удалён — создаём заново
        await db.set_shaolen_calendar_id(user_id, None)
    # Создать вторичный календарь
    cr = await client.post(
        "https://www.googleapis.com/calendar/v3/calendars",
        json={
            "summary": "Шаолень Привычки",
            "description": "Привычки, цели и подцели из @shaolen_bot",
        },
        headers=headers,
    )
    if cr.status_code != 200 or not cr.content:
        logger.warning("calendar-sync: не удалось создать календарь: %s", cr.status_code)
        return "primary"
    cdata = cr.json()
    new_id = (cdata.get("id") or "").strip()
    if not new_id:
        return "primary"
    # Задать цвет календаря в списке (для iOS важнее цвет календаря, чем событий)
    await client.patch(
        f"https://www.googleapis.com/calendar/v3/users/me/calendarList/{quote(new_id, safe='')}",
        json={"colorId": event_color_id},
        headers=headers,
    )
    await db.set_shaolen_calendar_id(user_id, new_id)
    logger.info("calendar-sync: календарь «Шаолень Привычки» создан/используется, colorId=%s", event_color_id)
    return new_id


@app.post("/api/user/{user_id}/calendar-sync", response_model=None)
async def api_calendar_sync(user_id: int):
    """Выгрузить подцели, привычки и цели в Google Календарь."""
    tokens = await db.get_google_fit_tokens(user_id)
    if not tokens:
        return JSONResponse(status_code=400, content={"detail": "Подключите Google в настройках (Авторизация Google Fit / Синхронизация с Google)."})
    settings = await db.get_calendar_sync_settings(user_id)
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")
    now = datetime.now(timezone.utc)
    if expires_at and isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_at = None
    if expires_at and (now - timedelta(minutes=5)) >= expires_at and refresh:
        async with httpx.AsyncClient(timeout=30.0) as client:
            rr = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_FIT_CLIENT_ID,
                    "client_secret": GOOGLE_FIT_CLIENT_SECRET,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if rr.status_code == 200:
            rdata = rr.json()
            access = rdata.get("access_token")
            exp = rdata.get("expires_in", 3600)
            new_expires = now + timedelta(seconds=exp)
            await db.save_google_fit_tokens(user_id, access, refresh, new_expires)
    if not access:
        return JSONResponse(status_code=400, content={"detail": "Токен истёк. Отключите и подключите Google заново."})

    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    created = 0
    errors = []
    today = now.strftime("%Y-%m-%d")
    tz = "Europe/Moscow"
    tz_offset = "+03:00"
    # Google Calendar API: colorId "1"—"11". Для Android — основной календарь + цвет на событиях. Для iOS — отдельный календарь «Шаолень Привычки» с цветом на уровне календаря (настройка use_dedicated_calendar_for_color).
    event_color_id = (settings.get("event_color_id") or "").strip() or None
    if event_color_id and event_color_id not in (str(i) for i in range(1, 12)):
        event_color_id = None
    use_dedicated = bool(settings.get("use_dedicated_calendar_for_color"))
    if event_color_id:
        logger.info("calendar-sync: цвет colorId=%s; отдельный календарь (iOS)=%s", event_color_id, use_dedicated)

    # Таймаут для Google Calendar API (по умолчанию 5 с бывает мало — ReadTimeout)
    calendar_timeout = 60.0
    try:
        async with httpx.AsyncClient(timeout=calendar_timeout) as client:
            if use_dedicated and event_color_id:
                try:
                    calendar_id = await _ensure_shaolen_calendar(client, headers, user_id, event_color_id, settings)
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
                    logger.warning("calendar-sync: таймаут/ошибка при получении календаря «Шаолень Привычки»: %s — используем основной календарь", e)
                    calendar_id = "primary"
            else:
                calendar_id = "primary"
            calendar_base = _calendar_base_url(calendar_id)

        if settings.get("sync_habits", True):
            habits = await db.get_habits(user_id, active_only=True)
            for i, h in enumerate(habits):
                hid = h.get("id")
                title = (h.get("title") or "").strip() or "Привычка"
                habit_color = (h.get("category_color_id") or "").strip()
                if habit_color not in (str(x) for x in range(1, 12)):
                    habit_color = event_color_id
                rt = (h.get("reminder_time") or "").strip()
                if rt and ":" in rt:
                    try:
                        parts = rt.split(":")
                        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                        hour = max(0, min(23, hour))
                        minute = max(0, min(59, minute))
                    except (ValueError, IndexError):
                        hour, minute = _habit_suggested_time(title, i, len(habits))
                else:
                    hour, minute = _habit_suggested_time(title, i, len(habits))
                start_dt = f"{today}T{hour:02d}:{minute:02d}:00{tz_offset}"
                total_min = hour * 60 + minute + 30
                if total_min >= 24 * 60:
                    end_h, end_m = 23, 59
                else:
                    end_h, end_m = total_min // 60, total_min % 60
                end_dt = f"{today}T{end_h:02d}:{end_m:02d}:00{tz_offset}"
                event = {
                    "summary": f"Привычка: {title}",
                    "description": "Из приложения @shaolen_bot",
                    "start": {"dateTime": start_dt, "timeZone": tz},
                    "end": {"dateTime": end_dt, "timeZone": tz},
                    "recurrence": ["RRULE:FREQ=DAILY"],
                }
                if habit_color:
                    event["colorId"] = str(habit_color)
                try:
                    existing = await db.get_calendar_event(user_id, "habit", hid) if hid else None
                    r = None
                    async with httpx.AsyncClient(timeout=calendar_timeout) as client:
                        if existing and (existing.get("event_id") or "").strip():
                            base = _calendar_base_url((existing.get("calendar_id") or calendar_id) or "primary")
                            r = await client.put(
                                f"{base}/events/{existing['event_id']}",
                                json=event,
                                headers=headers,
                            )
                            if r.status_code == 404:
                                existing = None
                        if not existing or not (existing.get("event_id") or "").strip():
                            r = await client.post(
                                f"{calendar_base}/events",
                                json=event,
                                headers=headers,
                            )
                            if r.status_code in (200, 201):
                                resp_data = r.json() if r.content else {}
                                eid = (resp_data.get("id") or "").strip()
                                if eid and hid is not None:
                                    await db.set_calendar_event(user_id, "habit", hid, calendar_id, eid)
                        if r is not None and r.status_code in (200, 201):
                            created += 1
                        elif r is not None:
                            err_body = (r.text or "")[:200]
                            logger.warning("Calendar API habit %s: %s %s", title, r.status_code, err_body)
                            errors.append(f"habit {title}: {r.status_code}")
                except Exception as e:
                    errors.append(f"habit {title}: {str(e)}")

        if settings.get("sync_goals", True):
            goals = await db.get_goals(user_id, include_completed=False)
            for g in goals:
                gid = g.get("id")
                title = (g.get("title") or "").strip() or "Цель"
                dl = g.get("deadline")
                if not dl:
                    continue
                try:
                    dl_str = str(dl)[:10] if dl else today
                except Exception:
                    dl_str = today
                start_dt = f"{dl_str}T09:00:00{tz_offset}"
                end_dt = f"{dl_str}T10:00:00{tz_offset}"
                event = {
                    "summary": f"Цель: {title}",
                    "description": (g.get("description") or "")[:500] or "Из приложения @shaolen_bot",
                    "start": {"dateTime": start_dt, "timeZone": tz},
                    "end": {"dateTime": end_dt, "timeZone": tz},
                }
                if event_color_id:
                    event["colorId"] = str(event_color_id)
                try:
                    existing = await db.get_calendar_event(user_id, "goal", gid) if gid else None
                    r = None
                    async with httpx.AsyncClient(timeout=calendar_timeout) as client:
                        if existing and (existing.get("event_id") or "").strip():
                            base = _calendar_base_url((existing.get("calendar_id") or calendar_id) or "primary")
                            r = await client.put(
                                f"{base}/events/{existing['event_id']}",
                                json=event,
                                headers=headers,
                            )
                            if r.status_code == 404:
                                existing = None
                        if not existing or not (existing.get("event_id") or "").strip():
                            r = await client.post(
                                f"{calendar_base}/events",
                                json=event,
                                headers=headers,
                            )
                            if r.status_code in (200, 201):
                                resp_data = r.json() if r.content else {}
                                eid = (resp_data.get("id") or "").strip()
                                if eid and gid is not None:
                                    await db.set_calendar_event(user_id, "goal", gid, calendar_id, eid)
                        if r is not None and r.status_code in (200, 201):
                            created += 1
                        elif r is not None:
                            err_body = (r.text or "")[:200]
                            logger.warning("Calendar API goal %s: %s %s", title, r.status_code, err_body)
                            errors.append(f"goal {title}: {r.status_code}")
                except Exception as e:
                    errors.append(f"goal {title}: {str(e)}")

        if settings.get("sync_subgoals", True):
            missions = await db.get_missions(user_id, include_completed=False)
            for m in missions:
                dl = m.get("deadline")
                if not dl:
                    continue
                try:
                    dl_str = str(dl)[:10] if dl else today
                except Exception:
                    dl_str = today
                mtitle = (m.get("title") or "").strip() or "Миссия"
                subgoals = await db.get_subgoals(m.get("id") or 0)
                for j, sg in enumerate(subgoals):
                    sgid = sg.get("id")
                    sgtitle = (sg.get("title") or "").strip() or "Подцель"
                    hour = 9 + (j % 8)
                    event = {
                        "summary": f"{mtitle}: {sgtitle}",
                        "description": "Из приложения @shaolen_bot",
                        "start": {"dateTime": f"{dl_str}T{hour:02d}:00:00{tz_offset}", "timeZone": tz},
                        "end": {"dateTime": f"{dl_str}T{hour:02d}:30:00{tz_offset}", "timeZone": tz},
                    }
                    if event_color_id:
                        event["colorId"] = str(event_color_id)
                    try:
                        existing = await db.get_calendar_event(user_id, "subgoal", sgid) if sgid else None
                        r = None
                        async with httpx.AsyncClient(timeout=calendar_timeout) as client:
                            if existing and (existing.get("event_id") or "").strip():
                                base = _calendar_base_url((existing.get("calendar_id") or calendar_id) or "primary")
                                r = await client.put(
                                    f"{base}/events/{existing['event_id']}",
                                    json=event,
                                    headers=headers,
                                )
                                if r.status_code == 404:
                                    existing = None
                            if not existing or not (existing.get("event_id") or "").strip():
                                r = await client.post(
                                    f"{calendar_base}/events",
                                    json=event,
                                    headers=headers,
                                )
                                if r.status_code in (200, 201):
                                    resp_data = r.json() if r.content else {}
                                    eid = (resp_data.get("id") or "").strip()
                                    if eid and sgid is not None:
                                        await db.set_calendar_event(user_id, "subgoal", sgid, calendar_id, eid)
                            if r is not None and r.status_code in (200, 201):
                                created += 1
                            elif r is not None:
                                err_body = (r.text or "")[:200]
                                logger.warning("Calendar API subgoal %s: %s %s", sgtitle, r.status_code, err_body)
                                errors.append(f"subgoal {sgtitle}: {r.status_code}")
                    except Exception as e:
                        errors.append(f"subgoal {sgtitle}: {str(e)}")

        resp = {"ok": True, "created": created, "errors": errors[:10]}
        # Если все запросы завершились ошибкой — подсказка по 403
        if created == 0 and errors and any("403" in e for e in errors):
            resp["hint"] = (
                "403 Forbidden: Включите Google Calendar API в Google Cloud Console и "
                "отключите/подключите Google в настройках (чтобы получить доступ к календарю)."
            )
        return JSONResponse(content=resp)
    except httpx.ReadTimeout:
        logger.warning("calendar sync: ReadTimeout from Google API")
        return JSONResponse(status_code=503, content={"detail": "Google Calendar ответил слишком долго. Попробуйте позже."})
    except httpx.ConnectTimeout:
        logger.warning("calendar sync: ConnectTimeout to Google API")
        return JSONResponse(status_code=503, content={"detail": "Не удалось подключиться к Google. Попробуйте позже."})
    except Exception as e:
        logger.exception("calendar sync: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/user/{user_id}/profile", response_model=None)
async def api_get_profile(user_id: int):
    """Профиль пользователя: имя, пол, вес, рост, возраст, цель, город, статистика."""
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return JSONResponse(content=_profile_out(user))


@app.put("/api/user/{user_id}/profile")
async def api_update_profile(user_id: int, payload: ProfileUpdate):
    """Сохранить профиль (имя, пол, вес, рост, возраст, цель, город, согласие на гео). При сохранении веса добавляется точка в историю на сегодня."""
    if payload.display_name is not None:
        await db.update_user_display_name(user_id, payload.display_name)
    await db.update_user_profile_extended(
        user_id,
        gender=payload.gender,
        weight=payload.weight,
        height=payload.height,
        age=payload.age,
        target_weight=payload.target_weight,
        city=payload.city,
        country=payload.country,
        country_code=payload.country_code,
        geo_consent=payload.geo_consent,
    )
    if payload.weight is not None and payload.weight > 0:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.add_weight_entry(user_id, today, payload.weight)
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return JSONResponse(content=_profile_out(user))


@app.get("/api/user/{user_id}/weight-history", response_model=None)
async def api_weight_history(user_id: int, period: str = "7"):
    """История веса: period = 7 | week | month | 6months | year."""
    if period not in ("7", "week", "month", "6months", "year"):
        period = "7"
    rows = await db.get_weight_history(user_id, period=period)
    return JSONResponse(content={"period": period, "data": rows})


class WeightEntryBody(BaseModel):
    date: str  # YYYY-MM-DD
    weight: float


@app.post("/api/user/{user_id}/weight", response_model=None)
async def api_add_weight(user_id: int, payload: WeightEntryBody):
    """Добавить/обновить вес на дату."""
    if payload.weight <= 0:
        raise HTTPException(status_code=400, detail="Вес должен быть больше 0")
    import re as re_mod
    if not re_mod.match(r"^\d{4}-\d{2}-\d{2}$", payload.date):
        raise HTTPException(status_code=400, detail="Дата в формате YYYY-MM-DD")
    await db.add_user(user_id)
    await db.add_weight_entry(user_id, payload.date, payload.weight)
    user = await db.get_user(user_id)
    if user:
        await db.update_user_profile_extended(user_id, weight=payload.weight)
    return JSONResponse(content={"ok": True, "date": payload.date, "weight": payload.weight})


# --- Погода и геолокация (для расчёта воды) ---
def _client_ip(request: Request) -> Optional[str]:
    """IP клиента (учёт X-Forwarded-For за Nginx)."""
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _geo_by_ip(ip: str) -> Optional[Dict[str, Any]]:
    """Геолокация по IP через ip-api.com (city, country, lat, lon)."""
    if not ip or ip == "127.0.0.1":
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "city,country,lat,lon"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") != "success":
                return None
            return {
                "city": data.get("city") or "",
                "country": data.get("country") or "",
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            }
    except Exception as e:
        logger.warning("Гео по IP %s: %s", ip, e)
        return None


async def _weather_by_coords(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Погода по координатам (Open-Meteo): temp °C, humidity %."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m",
                },
            )
            if r.status_code != 200:
                return None
            data = r.json()
            cur = data.get("current") or {}
            return {
                "temp": cur.get("temperature_2m"),
                "humidity": cur.get("relative_humidity_2m"),
            }
    except Exception as e:
        logger.warning("Погода по координатам: %s", e)
        return None


async def _geocode_city(city: str, country: str = "", country_code: str = "") -> Optional[Dict[str, Any]]:
    """Геокодинг города (Open-Meteo): lat, lon, name. country_code — ISO 2 буквы для однозначного выбора (напр. Москва, RU)."""
    try:
        params = {"name": city.strip(), "count": 10, "language": "ru"}
        code = (country_code or "").strip().upper()
        if len(code) == 2:
            params["countryCode"] = code  # Open-Meteo API: camelCase
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params=params,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            results = data.get("results") or []
            if not results:
                return None
            # Берём первый результат (при фильтре по стране — нужный город)
            r0 = results[0]
            return {"lat": r0.get("latitude"), "lon": r0.get("longitude"), "name": r0.get("name"), "country": r0.get("country") or r0.get("country_code")}
    except Exception as e:
        logger.warning("Геокодинг %s: %s", city, e)
        return None


async def _geocode_search(query: str, count: int = 10) -> List[Dict[str, Any]]:
    """Поиск городов по запросу (Open-Meteo): список {name, country, country_code, lat, lon}, сортировка по населению, полное название страны."""
    if not (query or "").strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": query.strip(), "count": 20, "language": "ru"},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            raw = data.get("results") or []
            # Сортировка по населению (сначала крупные города — реальные столицы/мегаполисы)
            raw.sort(key=lambda x: -(x.get("population") or 0))
            seen = set()
            out = []
            for r in raw:
                name = (r.get("name") or "").strip()
                # Полное название страны (API возвращает локализованное имя страны)
                country_full = (r.get("country") or "").strip()
                country_code = (r.get("country_code") or "").strip().upper()
                if not name:
                    continue
                key = (name, country_code)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "name": name,
                    "country": country_full or country_code,
                    "country_code": country_code,
                    "lat": r.get("latitude"),
                    "lon": r.get("longitude"),
                })
                if len(out) >= min(count, 15):
                    break
            return out
    except Exception as e:
        logger.warning("Поиск городов %s: %s", query, e)
        return []


def _water_climate_factor(temp: Optional[float], humidity: Optional[float]) -> float:
    """Климатическая поправка к норме воды (доля от базовой, 0 = без добавки). По ВОЗ/Mayo Clinic."""
    h = humidity or 0
    if h > 70:
        return 0.15  # высокая влажность +10–20%
    if temp is None:
        return 0.0
    if temp < 20:
        return 0.0
    if temp <= 26:
        return 0.10 if h < 60 else 0.15  # +10–15%
    if temp <= 32:
        return 0.25 if h < 70 else 0.20  # +20–30% / при влажности +10–20%
    return 0.40  # >32 °C +30–50%


def _water_liters(weight_kg: float, activity_min: float, climate_factor: float) -> float:
    """Вода (л) = (Вес_кг × 30 мл) + (Активность_минуты × 15 мл) + климатическая поправка к базе."""
    base_ml = weight_kg * 30 + activity_min * 15
    base_l = base_ml / 1000.0
    add = base_l * climate_factor
    return round(base_l + add, 2)


@app.get("/api/weather/by-ip", response_model=None)
async def api_weather_by_ip(request: Request):
    """Погода по IP клиента (город, страна, temp, humidity). Для расчёта воды."""
    ip = _client_ip(request)
    if not ip:
        return JSONResponse(content={"error": "IP не определён"}, status_code=400)
    geo = await _geo_by_ip(ip)
    if not geo or geo.get("lat") is None:
        return JSONResponse(content={"error": "Город по IP не определён"}, status_code=404)
    weather = await _weather_by_coords(geo["lat"], geo["lon"])
    if not weather:
        return JSONResponse(content={"error": "Погода недоступна"}, status_code=502)
    return JSONResponse(content={"city": geo.get("city"), "country": geo.get("country"), **weather})


@app.get("/api/geocode/search", response_model=None)
async def api_geocode_search(q: str = ""):
    """Поиск городов по названию (для выбора из списка). Возвращает список {name, country, lat, lon}."""
    results = await _geocode_search(q)
    return JSONResponse(content={"results": results})


@app.get("/api/weather/by-city", response_model=None)
async def api_weather_by_city(city: str, country: str = "", country_code: str = ""):
    """Погода по названию города. country_code — ISO 2 буквы (предпочтительно для однозначного выбора)."""
    if not (city or "").strip():
        raise HTTPException(status_code=400, detail="Укажите город")
    loc = await _geocode_city(city.strip(), country.strip(), country_code.strip())
    if not loc:
        return JSONResponse(content={"error": "Город не найден"}, status_code=404)
    weather = await _weather_by_coords(loc["lat"], loc["lon"])
    if not weather:
        return JSONResponse(content={"error": "Погода недоступна"}, status_code=502)
    return JSONResponse(content={"city": loc.get("name") or city, "country": country, **weather})


class WaterCalculateBody(BaseModel):
    activity_minutes: Optional[float] = 0
    use_geo: Optional[bool] = True  # получить город по IP и погоду
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None  # ISO 2 буквы для однозначного геокодинга
    temp: Optional[float] = None  # если уже есть погода
    humidity: Optional[float] = None


@app.post("/api/user/{user_id}/water-calculate", response_model=None)
async def api_water_calculate(user_id: int, request: Request, payload: WaterCalculateBody):
    """Рассчитать рекомендуемый объём воды в день (л). Учитывает вес, активность, погоду (по IP или город)."""
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    weight = user.get("weight")
    if not weight or weight <= 0:
        return JSONResponse(
            status_code=400,
            content={"detail": "Укажите вес в профиле"},
        )
    activity = float(payload.activity_minutes or 0)
    temp, humidity = payload.temp, payload.humidity
    city_out = (payload.city or "").strip() or None
    country_out = (payload.country or "").strip() or None
    if payload.use_geo:
        ip = _client_ip(request)
        geo = await _geo_by_ip(ip) if ip else None
        if geo:
            if not (city_out or country_out):
                city_out = geo.get("city") or city_out
                country_out = geo.get("country") or country_out
            if geo.get("lat") is not None:
                w = await _weather_by_coords(geo["lat"], geo["lon"])
                if w:
                    temp = w.get("temp")
                    humidity = w.get("humidity")
    if temp is None and (payload.city or "").strip():
        code = (payload.country_code or user.get("country_code") or "").strip().upper()
        if len(code) != 2:
            code = ""
        loc = await _geocode_city((payload.city or "").strip(), (payload.country or "").strip(), code)
        if loc:
            w = await _weather_by_coords(loc["lat"], loc["lon"])
            if w:
                temp = w.get("temp")
                humidity = w.get("humidity")
    climate = _water_climate_factor(temp, humidity)
    liters = _water_liters(weight, activity, climate)
    # Сохраняем город/страну в профиль, чтобы при следующем заходе не вводить заново
    if city_out is not None or country_out is not None:
        code = (payload.country_code or user.get("country_code") or "").strip().upper()
        await db.update_user_profile_extended(
            user_id,
            city=city_out,
            country=country_out,
            country_code=code if len(code) == 2 else None,
        )
    return JSONResponse(content={
        "liters": liters,
        "weight_kg": weight,
        "activity_minutes": activity,
        "climate_factor": round(climate * 100, 0),
        "temp": temp,
        "humidity": humidity,
        "city": city_out,
        "country": country_out,
        "formula": "Вода (л) = (Вес_кг × 30 мл) + (Активность_мин × 15 мл) + климатическая поправка ВОЗ/Mayo",
    })


class WaterHabitBody(BaseModel):
    liters_per_day: float
    title: Optional[str] = None
    formula_note: Optional[str] = None  # текст для справки «как рассчитано» (город, темп., влажность, формула)


@app.post("/api/user/{user_id}/water-habit", response_model=None)
async def api_water_habit(user_id: int, payload: WaterHabitBody):
    """Создать привычку «Пить воду Xл» с плашкой «Рассчитана автоматически»."""
    if payload.liters_per_day <= 0:
        raise HTTPException(status_code=400, detail="Укажите объём воды в день")
    liters = payload.liters_per_day
    title = f"Пить воду {liters:.0f}л" if liters == int(liters) else f"Пить воду {liters:.1f}л"
    desc = f"Рекомендуемая норма: {liters:.1f} л в день. "
    if payload.formula_note:
        desc += payload.formula_note
    else:
        desc += "По формуле с учётом веса, активности и погоды (ВОЗ/Mayo)."
    hid = await db.add_habit(user_id, title, desc, is_example=0, is_water_calculated=1)
    return JSONResponse(content={"ok": True, "habit_id": hid, "title": title, "liters_per_day": liters})


@app.post("/api/user/{user_id}/seed")
async def api_seed_user(user_id: int):
    """Добавить примеры миссий, целей и привычек, если у пользователя ещё пусто"""
    await db.seed_user_examples(user_id)
    return JSONResponse(content={"ok": True, "message": "Примеры добавлены или уже были"})


@app.post("/api/user/{user_id}/ensure-examples")
async def api_ensure_user_examples(user_id: int):
    """Убедиться, что у пользователя есть предустановленные примеры (для новых и без примеров)."""
    await db.ensure_user_examples(user_id)
    return JSONResponse(content={"ok": True})


@app.get("/api/user/{user_id}/analytics", response_model=None)
async def api_get_analytics(user_id: int, period: str = "month"):
    """Получение аналитики пользователя. period: week (7 дн.), month (30 дн.), all (365 дн.)"""
    from datetime import date, timedelta
    if period == "week":
        days = 7
    elif period == "all":
        days = 365
    else:
        days = 30  # month
    try:
        logger.info(f"Запрос аналитики для пользователя {user_id}, период={period}, days={days}")
        analytics = await db.get_user_analytics(user_id, days=days)
        chart_data = await db.get_habit_completions_by_date(user_id, days=days)
        habit_streak = await db.get_habit_streak(user_id)

        today = date.today()
        labels_chart = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        by_date = {r["date"]: r["completions"] for r in chart_data}
        values_chart = [by_date.get(d, 0) for d in labels_chart]
        
        # Преобразуем все числа в float для JSON
        result = {
            "period": period,
            "missions": {
                "total": int(analytics.get("missions", {}).get("total", 0)),
                "completed": int(analytics.get("missions", {}).get("completed", 0)),
                "avg_progress": float(analytics.get("missions", {}).get("avg_progress", 0))
            },
            "goals": {
                "total": int(analytics.get("goals", {}).get("total", 0)),
                "completed": int(analytics.get("goals", {}).get("completed", 0)),
                "completion_rate": float(analytics.get("goals", {}).get("completion_rate", 0))
            },
            "habits": {
                "total": int(analytics.get("habits", {}).get("total", 0)),
                "total_completions": int(analytics.get("habits", {}).get("total_completions", 0)),
                "streak": int(habit_streak)
            },
            "habit_chart": {
                "labels": labels_chart,
                "values": values_chart
            }
        }
        
        logger.info(f"Аналитика получена: {result}")
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения аналитики для пользователя {user_id}: {e}", exc_info=True)
        error_result = {
            "missions": {"total": 0, "completed": 0, "avg_progress": 0.0},
            "goals": {"total": 0, "completed": 0, "completion_rate": 0.0},
            "habits": {"total": 0, "total_completions": 0, "streak": 0},
            "habit_chart": {"labels": [], "values": []}
        }
        return JSONResponse(content=error_result)


@app.get("/api/user/{user_id}/achievements", response_model=None)
async def api_achievements(user_id: int):
    """Достижения: текущие привычки + сохранённые (привычки с 21+ повторениями, удалённые)."""
    try:
        out = []
        habits = await db.get_habits(user_id, active_only=False)
        for h in (habits or []):
            hid = h.get("id")
            total_completions = await db.get_habit_total_completions(hid) if hid else 0
            title = (h.get("title") or "").strip() or "Привычка"
            out.append({
                "habit_id": hid,
                "title": title,
                "streak": total_completions,
                "achieved": total_completions >= 21,
            })
        saved = await db.get_user_achievements(user_id)
        out.extend(saved)
        return JSONResponse(content={"achievements": out})
    except Exception as e:
        logger.exception("achievements: %s", e)
        return JSONResponse(content={"achievements": []})


@app.get("/api/user/{user_id}/achievement-check", response_model=None)
async def api_achievement_check(user_id: int):
    """Проверка: если есть привычки с 21+ повторениями без уведомления — пометить и вернуть для показа в приложении."""
    try:
        habits = await db.get_habits(user_id, active_only=False)
        for h in (habits or []):
            hid = h.get("id")
            if not hid:
                continue
            total = await db.get_habit_total_completions(hid)
            notified = h.get("achievement_21_notified") or 0
            if total >= 21 and not notified:
                await db.set_habit_achievement_notified(hid)
                title = (h.get("title") or "").strip() or "Привычка"
                return JSONResponse(content={"ok": True, "achievement_unlocked": True, "habit_title": title})
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.warning("achievement-check: %s", e)
        return JSONResponse(content={"ok": False})


@app.get("/api/user/{user_id}/habit-last-7-days", response_model=None)
async def api_habit_last_7_days(user_id: int):
    """Последние 7 дней (включая сегодня) для каждой привычки: + выполнено, - пропущено."""
    try:
        data = await db.get_habit_last_7_days(user_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.exception("habit-last-7-days: %s", e)
        return JSONResponse(
            status_code=500,
            content={"dates": [], "habits": [], "error": str(e)},
        )


@app.get("/api/user/{user_id}/habit-calendar", response_model=None)
async def api_habit_calendar(user_id: int, year: int, month: int):
    """Данные календаря привычек за месяц (для страницы «Календарь привычек»)."""
    from datetime import date
    today = date.today()
    if year < 2020 or year > 2100 or month < 1 or month > 12:
        year, month = today.year, today.month
    try:
        data = await db.get_habit_calendar_month(user_id, year, month)
        return JSONResponse(content=data)
    except Exception as e:
        logger.exception("habit-calendar: %s", e)
        return JSONResponse(
            status_code=500,
            content={"days": {}, "total_habits": 0, "error": str(e)},
        )


@app.get("/api/user/{user_id}/shaolen/usage", response_model=None)
async def api_shaolen_usage(user_id: int):
    """Лимит запросов к мастеру Шаолень: использовано сегодня и лимит в день."""
    used = await db.get_shaolen_requests_today(user_id)
    return JSONResponse(content={"used": used, "limit": LIMIT_SHAOLEN_PER_DAY})


@app.get("/api/user/{user_id}/shaolen/history", response_model=None)
async def api_shaolen_history(user_id: int, limit: int = 50):
    """История запросов к Шаолень: последние пары вопрос–ответ."""
    if limit < 1 or limit > 100:
        limit = 50
    rows = await db.get_shaolen_history(user_id, limit=limit)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "created_at": r.get("created_at").isoformat() if hasattr(r.get("created_at"), "isoformat") else str(r.get("created_at") or ""),
            "user_message": r.get("user_message") or "",
            "assistant_reply": r.get("assistant_reply") or "",
            "has_image": bool(r.get("has_image")),
        })
    return JSONResponse(content=out)


def _parse_iso(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if hasattr(s, "isoformat"):
        return s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "").strip())
    except Exception:
        return None


@app.get("/api/user/{user_id}/time-capsule", response_model=None)
async def api_get_time_capsule(user_id: int):
    """Капсула времени: одна на пользователя. can_edit — можно ли редактировать (в течение часа после последнего редактирования)."""
    cap = await db.get_time_capsule(user_id)
    if not cap:
        return JSONResponse(content={"capsule": None, "can_edit": False})
    now = datetime.now()
    last = _parse_iso(cap.get("last_edited_at") or cap.get("created_at")) or now
    can_edit = (now - last).total_seconds() < 3600
    open_at = cap.get("open_at")
    if hasattr(open_at, "isoformat"):
        open_at = open_at.isoformat()
    open_at_s = str(open_at or "")
    if open_at_s and "Z" not in open_at_s and "+" not in open_at_s[-6:]:
        open_at_s = open_at_s + "Z"
    return JSONResponse(content={
        "capsule": {
            "title": cap.get("title") or "",
            "expected_result": cap.get("expected_result") or "",
            "open_at": open_at_s,
            "created_at": (cap.get("created_at").isoformat() if hasattr(cap.get("created_at"), "isoformat") else str(cap.get("created_at") or "")),
        },
        "can_edit": can_edit,
    })


_DEFAULT_CAPSULE_TITLE = "Через 30 дней привычек я надеюсь…"


@app.post("/api/user/{user_id}/time-capsule", response_model=None)
async def api_create_time_capsule(user_id: int, payload: TimeCapsuleCreate):
    """Создать капсулу времени. open_in_days и open_in_hours (целые) задают момент открытия от «сейчас»."""
    title = (payload.title or "").strip()
    if not title or title == _DEFAULT_CAPSULE_TITLE:
        return JSONResponse(
            status_code=400,
            content={"detail": "Необходимо добавить свой заголовок для капсулы времени"},
        )
    total_hours = max(0, int(round(float(payload.open_in_hours or 0)))) + 24 * max(0, int(payload.open_in_days or 0))
    if total_hours < 1:
        return JSONResponse(
            status_code=400,
            content={"detail": "Укажите время открытия: хотя бы 1 день или 1 час"},
        )
    open_at = (datetime.now(timezone.utc) + timedelta(hours=total_hours)).replace(tzinfo=None)
    await db.create_time_capsule(
        user_id,
        title=title,
        expected_result=payload.expected_result or "",
        open_at=open_at,
    )
    cap = await db.get_time_capsule(user_id)
    open_at_s = cap.get("open_at")
    if hasattr(open_at_s, "isoformat"):
        open_at_s = open_at_s.isoformat()
    open_at_s = str(open_at_s or "")
    if open_at_s and "Z" not in open_at_s and "+" not in open_at_s[-6:]:
        open_at_s = open_at_s + "Z"
    return JSONResponse(content={
        "capsule": {
            "title": cap.get("title") or "",
            "expected_result": cap.get("expected_result") or "",
            "open_at": open_at_s,
        },
        "can_edit": True,
    })


@app.patch("/api/user/{user_id}/time-capsule", response_model=None)
async def api_update_time_capsule(user_id: int, payload: TimeCapsuleUpdate):
    """Обновить капсулу (только в течение часа после последнего редактирования)."""
    total_hours = max(0, int(round(float(payload.open_in_hours or 0)))) + 24 * max(0, int(payload.open_in_days or 0))
    if total_hours < 1:
        total_hours = 1
    open_at = (datetime.now(timezone.utc) + timedelta(hours=total_hours)).replace(tzinfo=None)
    ok = await db.update_time_capsule(user_id, payload.title or "Капсула", payload.expected_result or "", open_at)
    if not ok:
        return JSONResponse(status_code=403, content={"detail": "Капсула запечатана или отсутствует. Редактировать можно только в течение часа после создания/последнего изменения."})
    cap = await db.get_time_capsule(user_id)
    open_at_s = cap.get("open_at")
    if hasattr(open_at_s, "isoformat"):
        open_at_s = open_at_s.isoformat()
    open_at_s = str(open_at_s or "")
    if open_at_s and "Z" not in open_at_s and "+" not in open_at_s[-6:]:
        open_at_s = open_at_s + "Z"
    return JSONResponse(content={
        "capsule": {"title": cap.get("title"), "expected_result": cap.get("expected_result"), "open_at": open_at_s},
        "can_edit": True,
    })


@app.delete("/api/user/{user_id}/time-capsule", response_model=None)
async def api_delete_time_capsule(user_id: int):
    """Удалить капсулу времени."""
    await db.delete_time_capsule(user_id)
    return JSONResponse(content={"ok": True})


@app.post("/api/user/{user_id}/time-capsule/archive", response_model=None)
async def api_archive_time_capsule(user_id: int):
    """Перенести открытую капсулу в историю и разрешить создание новой."""
    ok = await db.archive_time_capsule(user_id)
    return JSONResponse(content={"ok": ok, "capsule": None})


@app.get("/api/user/{user_id}/time-capsule/history", response_model=None)
async def api_get_capsule_history(user_id: int):
    """История открытых капсул (для саморефлексии)."""
    rows = await db.get_time_capsule_history(user_id)
    out = []
    for r in rows:
        viewed = r.get("viewed_at")
        if hasattr(viewed, "isoformat"):
            viewed = viewed.isoformat()
        out.append({
            "id": r.get("id"),
            "title": r.get("title") or "",
            "expected_result": r.get("expected_result") or "",
            "open_at": str(r.get("open_at") or ""),
            "viewed_at": str(viewed or ""),
            "reflection": (r.get("reflection") or "").strip() or None,
        })
    return JSONResponse(content=out)


@app.patch("/api/user/{user_id}/time-capsule/history/{history_id}/reflection", response_model=None)
async def api_add_capsule_reflection(user_id: int, history_id: int, payload: CapsuleReflectionBody):
    """Один раз добавить впечатления к капсуле в истории."""
    ok = await db.add_capsule_reflection(history_id, user_id, payload.reflection or "")
    if not ok:
        return JSONResponse(status_code=400, content={"detail": "Запись не найдена или впечатления уже добавлены."})
    return JSONResponse(content={"ok": True})


def _build_shaolen_system_prompt(missions: list, goals: list, habits: list) -> str:
    parts = [
        "Ты — мастер Шаолень, мудрый и доброжелательный помощник в приложении для целей, миссий и привычек.",
        "Отвечай кратко и по-русски. Опирайся на миссии, цели и привычки пользователя: предлагай советы в духе «Вижу, вы хотите… — вот как это делать правильно» или «Учитывая вашу цель …, советую …».",
        "Не придумывай то, чего нет в списке ниже. Если списков нет — просто поддержи и дай общий совет по постановке целей.",
        "",
        "ВАЖНО: когда пользователь просит подобрать или добавить привычки/цели/миссии (например «хочу похудеть, добавь привычки» или «подбери цели») — в ответе ты предлагаешь конкретные названия. Чтобы бот их реально создал, в самом конце ответа добавь ровно одну строку:",
        "__ДОБАВИТЬ__ привычки: то, что ты перечислил в тексте, через запятую",
        "Пример: если написал «предлагаю привычки: контроль питания, пить воду, сон 8 часов» — в конец добавь строку: __ДОБАВИТЬ__ привычки: контроль питания, пить воду, сон 8 часов",
        "Для целей: __ДОБАВИТЬ__ цели: цель1, цель2. Для миссий: __ДОБАВИТЬ__ миссии: Миссия (подцели: а, б). Можно несколько блоков через |: привычки: а, б | цели: в. Эту строку пользователь не увидит.",
        "",
        "Миссии пользователя (долгосрочные цели с подцелями):",
    ]
    if missions:
        for m in missions:
            title = (m.get("title") or "").strip()
            if title:
                parts.append(f"  • {title}")
    else:
        parts.append("  (пока нет)")
    parts.append("")
    parts.append("Цели пользователя:")
    if goals:
        for g in goals:
            title = (g.get("title") or "").strip()
            if title:
                parts.append(f"  • {title}")
    else:
        parts.append("  (пока нет)")
    parts.append("")
    parts.append("Привычки пользователя:")
    if habits:
        for h in habits:
            title = (h.get("title") or "").strip()
            if title:
                parts.append(f"  • {title}")
    else:
        parts.append("  (пока нет)")
    return "\n".join(parts)


def _is_stats_or_today_request(text: str) -> bool:
    """Проверяет, спрашивает ли пользователь про статистику или выполнение за сегодня/неделю."""
    if not text or len(text) < 5:
        return False
    low = (text or "").lower()
    triggers = (
        "статистик", "выполнил сегодня", "что сделал сегодня", "какие привычки", "что отмечено",
        "покажи за неделю", "прогресс за неделю", "статистика за неделю", "за неделю",
        "сколько выполнил", "какой прогресс", "моя статистика", "сводка за",
    )
    return any(t in low for t in triggers)


async def _build_stats_context_for_shaolen(db: Database, user_id: int, text: str) -> str:
    """
    Если запрос про статистику/сегодня/неделю — возвращает блок для system-промпта
    с актуальными данными (сегодня отмеченные привычки, аналитика за 7 дней).
    Иначе пустая строка.
    """
    if not _is_stats_or_today_request(text):
        return ""
    try:
        today_habits = await db.get_todays_habit_titles(user_id)
        analytics_7 = await db.get_user_analytics(user_id, days=7)
        streak = await db.get_habit_streak(user_id)
        parts = [
            "Данные по запросу пользователя (ответь на его вопрос, опираясь на эти цифры):",
            "— Сегодня отмечены привычки: " + (", ".join(today_habits) if today_habits else "пока ни одной") + ".",
            "— За последние 7 дней: миссий завершено {m_done} из {m_all}, целей {g_done} из {g_all}, "
            "привычек отмечено {h_count} раз, серия дней подряд (стрик): {streak}.".format(
                m_done=int(analytics_7.get("missions", {}).get("completed", 0)),
                m_all=int(analytics_7.get("missions", {}).get("total", 0)),
                g_done=int(analytics_7.get("goals", {}).get("completed", 0)),
                g_all=int(analytics_7.get("goals", {}).get("total", 0)),
                h_count=int(analytics_7.get("habits", {}).get("total_completions", 0)),
                streak=streak,
            ),
        ]
        return "\n".join(parts)
    except Exception as e:
        logger.warning("Ошибка формирования контекста статистики для Шаолень: %s", e)
        return ""


def _extract_title(s: str) -> str:
    """Извлечь название: убрать обрамляющие кавычки и лишние пробелы."""
    if not s:
        return ""
    s = s.strip()
    if (len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"") or (s.startswith("«") and "»" in s):
        if s.startswith("«"):
            return s[1:s.index("»")].strip()[:200]
        return s[1:-1].strip()[:200]
    return s.strip("'\"«»").strip()[:200]


def _parse_add_intent(text: str):
    """
    Если пользователь просит добавить привычку/цель/миссию/задачу — возвращаем
    ("habit"|"goal"|"mission", title, description, subgoals_list или []).
    Поддержка кавычек: «добавь привычку 'пить воду'», текстом и голосом.
    Иначе None.
    """
    t = (text or "").strip()
    if len(t) < 4:
        return None
    low = t.lower()
    # Ключевые слова для «добавить»
    add_triggers = r"(?:добавь|добавить|создай|создать|хочу|заведи|завести|запиши|внести|новая?)\s+"

    # Привычка (в т.ч. "добавь привычку 'пить воду'")
    m = re.search(add_triggers + r"привычк\w*\s*[:-]?\s*(.+)", low, re.IGNORECASE)
    if m:
        title = _extract_title(m.group(1).strip())
        if title:
            return ("habit", title, "", [])

    # Цель или задача (задача = цель в контексте приложения)
    m = re.search(
        add_triggers + r"(?:цел\w*|задач\w*)\s*[:-]?\s*(.+)",
        low,
        re.IGNORECASE,
    )
    if m:
        title = _extract_title(m.group(1).strip())
        if title:
            return ("goal", title, "", [])

    # Миссия (возможно с подцелями)
    m = re.search(add_triggers + r"мисси\w*\s*[:-]?\s*(.+)", low, re.IGNORECASE)
    if m:
        rest = m.group(1).strip()
        subgoals = []
        title = rest
        sub_match = re.search(
            r"\s+(?:с\s+)?подцелями?\s*[:-]?\s*(.+)$",
            rest,
            re.IGNORECASE,
        )
        if sub_match:
            title = rest[: sub_match.start()].strip()
            sub_str = sub_match.group(1).strip()
            for part in re.split(r"[,;]|\s+и\s+", sub_str):
                s = part.strip().strip("'\"").strip()[:150]
                if s:
                    subgoals.append(s)
        title = _extract_title(title)
        if title:
            return ("mission", title[:200], "", subgoals)
    return None


def _is_rate_limit_error(e: Exception) -> bool:
    """Распознать ошибку превышения лимита Groq (429)."""
    code = getattr(e, "status_code", None)
    if code == 429:
        return True
    msg = str(e).lower()
    return "429" in str(e) or "rate" in msg or "rate limit" in msg


def _chat_completion_with_fallback(
    client: "Groq",
    messages: list,
    model_list: List[str],
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    """Вызов chat.completions с переключением на следующую модель при 429. Для пользователя без изменений."""
    last_error: Optional[Exception] = None
    for model in model_list:
        try:
            chat = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (chat.choices[0].message.content or "").strip() if chat.choices else ""
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                logger.warning("Лимит модели %s, переключаемся на следующую: %s", model, e)
                continue
            raise
    if last_error:
        raise last_error
    return ""


def _parse_groq_add_block(reply: str):
    """
    Ищет в ответе Groq строку __ДОБАВИТЬ__ ... и извлекает привычки/цели/миссии.
    Возвращает (reply_без_этой_строки, [(typ, title, subgoals), ...]),
    где typ in ("habit","goal","mission").
    """
    if not reply or "__ДОБАВИТЬ__" not in reply:
        return reply.strip(), []
    lines = reply.split("\n")
    cleaned = []
    add_line = None
    for line in lines:
        if "__ДОБАВИТЬ__" in line:
            add_line = line
            continue
        cleaned.append(line)
    reply_clean = "\n".join(cleaned).strip()
    if not add_line:
        return reply_clean, []

    to_add = []
    rest = add_line.split("__ДОБАВИТЬ__", 1)[-1].strip()
    for part in re.split(r"\s*\|\s*", rest):
        part = part.strip()
        m = re.match(r"привычки?\s*[:-]\s*(.+)", part, re.IGNORECASE)
        if m:
            for s in re.split(r"[,;]", m.group(1)):
                t = s.strip().strip("'\"").strip()[:200]
                if t:
                    to_add.append(("habit", t, []))
            continue
        m = re.match(r"цели?\s*[:-]\s*(.+)", part, re.IGNORECASE)
        if m:
            for s in re.split(r"[,;]", m.group(1)):
                t = s.strip().strip("'\"").strip()[:200]
                if t:
                    to_add.append(("goal", t, []))
            continue
        m = re.match(r"мисси\w*\s*[:-]\s*(.+)", part, re.IGNORECASE)
        if m:
            block = m.group(1).strip()
            for chunk in re.split(r"(?<=\))\s*,\s*|,\s*(?=[^()]*(?:\(|$))", block):
                chunk = chunk.strip().strip("'\"").strip()
                subgoals = []
                subm = re.search(r"\s*\(подцели?\s*[:-]\s*([^)]+)\)", chunk, re.IGNORECASE)
                if subm:
                    for s in re.split(r"[,;]|\s+и\s+", subm.group(1)):
                        t = s.strip().strip("'\"").strip()[:150]
                        if t:
                            subgoals.append(t)
                    chunk = chunk[: subm.start()].strip().strip("'\"").strip()
                if chunk:
                    to_add.append(("mission", chunk[:200], subgoals[:10]))
            continue
    return reply_clean, to_add


def _normalize_image_url(img_b64: Optional[str]) -> Optional[str]:
    """Вернуть data:image/...;base64,... не длиннее ~4MB для Groq."""
    if not img_b64 or not str(img_b64).strip():
        return None
    s = str(img_b64).strip()
    if s.startswith("data:"):
        if len(s) > 5_500_000:
            return None
        return s
    if len(s) > 5_400_000:
        return None
    return "data:image/jpeg;base64," + s


def _transcribe_audio_groq(client: "Groq", audio_b64: str, language: str = "ru") -> Optional[str]:
    """Транскрибировать голосовое через Groq Whisper. audio_b64 — base64 или data:audio/...;base64,..."""
    if not audio_b64 or not str(audio_b64).strip():
        return None
    s = str(audio_b64).strip()
    ext = "ogg"
    if "webm" in s.lower():
        ext = "webm"
    elif "m4a" in s.lower() or "mp4" in s.lower():
        ext = "m4a"
    elif "mp3" in s.lower() or "mpeg" in s.lower():
        ext = "mp3"
    if s.startswith("data:audio/") and ";base64," in s:
        s = s.split(";base64,", 1)[-1]
    if len(s) > 25 * 1024 * 1024 * 4 // 3:  # ~25 MB base64
        return None
    try:
        raw = base64.b64decode(s, validate=True)
    except Exception:
        return None
    if not raw or len(raw) > 25_000_000:
        return None
    try:
        # Groq принимает (filename, bytes); форматы: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
        out = client.audio.transcriptions.create(
            file=("audio." + ext, raw),
            model="whisper-large-v3-turbo",
            language=language,
            response_format="text",
            temperature=0.0,
        )
        if hasattr(out, "text"):
            return (out.text or "").strip()
        return (str(out) or "").strip()
    except Exception as e:
        logger.warning("Ошибка транскрипции голоса Groq: %s", e)
        return None


@app.post("/api/user/{user_id}/shaolen/ask", response_model=None)
async def api_shaolen_ask(user_id: int, payload: ShaolenAsk):
    """Запрос к мастеру Шаолень. Лимит 50 запросов в день. Поддержка картинки и голосовых сообщений."""
    used = await db.get_shaolen_requests_today(user_id)
    if used >= LIMIT_SHAOLEN_PER_DAY:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Сегодня достигнут лимит запросов (50 в день). Заходите завтра.",
                "usage": {"used": used, "limit": LIMIT_SHAOLEN_PER_DAY},
            },
        )
    text = str(payload.message or "").strip()
    has_audio = bool(payload.audio_base64 and str(payload.audio_base64).strip())
    if has_audio and Groq and GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        transcribed = _transcribe_audio_groq(client, payload.audio_base64)
        if transcribed:
            text = (text + " " + transcribed).strip() if text else transcribed
        elif not text:
            return JSONResponse(
                status_code=400,
                content={"detail": "Не удалось распознать голос. Попробуйте ещё раз или напишите текстом."},
            )
    if not text:
        return JSONResponse(
            status_code=400,
            content={"detail": "Напишите текст или отправьте голосовое сообщение."},
        )

    if not Groq or not GROQ_API_KEY:
        logger.warning("Groq не настроен: нет GROQ_API_KEY или пакета groq")
        return JSONResponse(
            status_code=503,
            content={"detail": "Советник временно недоступен. Добавьте GROQ_API_KEY в настройки сервера."},
        )

    image_url = _normalize_image_url(payload.image_base64)
    has_image = bool(image_url)
    logger.info("shaolen/ask user_id=%s has_image=%s has_audio=%s msg_len=%s", user_id, has_image, has_audio, len(text))

    created_what = None
    intent = _parse_add_intent(text)
    if intent:
        action, title, desc, subgoals = intent
        try:
            if action == "habit":
                await db.add_habit(user_id, title, desc or "")
                created_what = f"привычку «{title}»"
            elif action == "goal":
                await db.add_goal(user_id, title, desc or "", None, 1)
                created_what = f"цель «{title}»"
            elif action == "mission":
                mid = await db.add_mission(user_id, title, desc or "", None)
                for sg in (subgoals or [])[:10]:
                    await db.add_subgoal(mid, sg, "")
                sub_s = f" (подцели: {', '.join(subgoals[:5])})" if subgoals else ""
                created_what = f"миссию «{title}»{sub_s}"
        except Exception as e:
            logger.exception("Ошибка авто-добавления по фразе user_id=%s: %s", user_id, e)
            created_what = None

    missions = await db.get_missions(user_id, include_completed=True)
    goals = await db.get_goals(user_id, include_completed=True)
    habits = await db.get_habits(user_id, active_only=False)
    system_text = _build_shaolen_system_prompt(
        [dict(m) for m in missions],
        [dict(g) for g in goals],
        [dict(h) for h in habits],
    )
    stats_ctx = await _build_stats_context_for_shaolen(db, user_id, text)
    if stats_ctx:
        system_text += "\n\n" + stats_ctx
    if has_image:
        system_text += "\n\nПользователь может присылать фото еды — помогай оценивать калории и давать советы по питанию в рамках его целей."
    if created_what:
        system_text += f"\n\nТы только что по просьбе пользователя добавил {created_what}. Ответь коротко, подтверди добавление и подбодри."

    user_content: object
    if has_image and image_url:
        user_content = [
            {"type": "text", "text": text[:2000]},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        model_list = list(SHAOLEN_VISION_MODELS)
    else:
        user_content = text[:2000]
        model_list = list(SHAOLEN_TEXT_MODELS)

    # Собираем контекст диалога (последние 20 сообщений), чтобы ответы учитывали уточняющие вопросы
    messages_for_groq = [{"role": "system", "content": system_text}]
    raw_history = payload.history or []
    for h in raw_history[-20:]:
        role = (h.get("role") or "").strip().lower()
        content = (h.get("content") or "").strip()[:1200]
        if not content or role not in ("user", "assistant"):
            continue
        messages_for_groq.append({"role": role, "content": content})
    messages_for_groq.append({"role": "user", "content": user_content})

    try:
        client = Groq(api_key=GROQ_API_KEY)
        reply = _chat_completion_with_fallback(
            client, messages_for_groq, model_list, max_tokens=800, temperature=0.7
        )
    except Exception as e:
        logger.exception("Ошибка вызова Groq для user_id=%s: %s", user_id, e)
        await db.add_shaolen_history(
            user_id, text, "[Ошибка: не удалось получить ответ от советника]", has_image=has_image
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "Не удалось получить ответ от советника. Попробуйте позже."},
        )

    reply_clean, from_groq = _parse_groq_add_block(reply)
    reply = reply_clean
    # Не дублировать: если уже создали по интенту из фразы («добавь задачу X»), не создавать то же из ответа Groq
    intent_key = None
    if intent and created_what:
        intent_action, intent_title = intent[0], (intent[1] or "").strip().lower()
        intent_key = (intent_action, intent_title)
    for item in from_groq:
        typ, title, subgoals = item[0], item[1], (item[2] if len(item) > 2 else [])
        if intent_key and typ == intent_key[0] and (title or "").strip().lower() == intent_key[1]:
            continue
        try:
            if typ == "habit":
                await db.add_habit(user_id, title, "")
            elif typ == "goal":
                await db.add_goal(user_id, title, "", None, 1)
            elif typ == "mission":
                mid = await db.add_mission(user_id, title, "", None)
                for sg in subgoals:
                    await db.add_subgoal(mid, sg, "")
        except Exception as e:
            logger.warning("Не удалось создать из ответа Groq typ=%s title=%s: %s", typ, title, e)

    await db.increment_shaolen_requests(user_id)
    await db.add_shaolen_history(user_id, text, reply, has_image=has_image)
    new_used = used + 1
    out = {"reply": reply, "usage": {"used": new_used, "limit": LIMIT_SHAOLEN_PER_DAY}}
    if from_groq or (intent and created_what):
        out["created"] = from_groq[0][0] if from_groq else intent[0]
    return JSONResponse(content=out)


def _admin_token(request: Request) -> bool:
    token = request.headers.get("X-Admin-Token") or request.query_params.get("token") or ""
    return bool(ADMIN_TOKEN and token.strip() == ADMIN_TOKEN.strip())


def _admin_required(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())


def _admin_403_body() -> dict:
    """Подсказка при 403: видит ли сервер ADMIN_TOKEN (без раскрытия значения)."""
    body = {"detail": "Неверный или отсутствующий ADMIN_TOKEN"}
    t = (ADMIN_TOKEN or "").strip()
    if not t:
        body["hint"] = "ADMIN_TOKEN на сервере пустой или не задан — проверьте .env и EnvironmentFile в systemd"
    else:
        body["hint"] = f"На сервере токен задан (длина {len(t)}). Сверьте токен в ссылке/заголовке с .env"
    return body


# === Отладка 403: без авторизации, только смотреть, видит ли процесс ADMIN_TOKEN ===
@app.get("/api/admin/check-env")
async def api_admin_check_env():
    """Проверка: задан ли ADMIN_TOKEN на сервере (длина без раскрытия значения)."""
    t = (ADMIN_TOKEN or "").strip()
    return JSONResponse(content={
        "token_loaded": bool(t),
        "token_length": len(t),
    })


# === Админ-API (требует ADMIN_TOKEN в заголовке X-Admin-Token или ?token=...) ===
@app.get("/api/admin/status")
async def api_admin_status(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    base = os.path.dirname(os.path.abspath(__file__))
    log_bot = os.path.join(base, "logs", "bot.log")
    log_webapp = os.path.join(base, "logs", "webapp.log")
    bot_ok = os.path.isfile(log_bot)
    webapp_ok = os.path.isfile(log_webapp)
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "goals-bot"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=base,
        )
        bot_active = r.returncode == 0 and (r.stdout or "").strip() == "active"
    except Exception:
        bot_active = None
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "goals-webapp"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=base,
        )
        webapp_active = r.returncode == 0 and (r.stdout or "").strip() == "active"
    except Exception:
        webapp_active = None
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "goals-reminder"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=base,
        )
        reminder_active = r.returncode == 0 and (r.stdout or "").strip() == "active"
    except Exception:
        reminder_active = None
    return JSONResponse(content={
        "bot": "active" if bot_active else ("inactive" if bot_active is False else "unknown"),
        "webapp": "active" if webapp_active else ("inactive" if webapp_active is False else "unknown"),
        "reminder": "active" if reminder_active else ("inactive" if reminder_active is False else "unknown"),
    })


@app.post("/api/admin/bot/start")
async def api_admin_bot_start(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "start", "goals-bot"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда start отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/bot/stop")
async def api_admin_bot_stop(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "stop", "goals-bot"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда stop отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/webapp/start")
async def api_admin_webapp_start(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "start", "goals-webapp"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда start отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/webapp/stop")
async def api_admin_webapp_stop(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "stop", "goals-webapp"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда stop отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/reminder/start")
async def api_admin_reminder_start(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "start", "goals-reminder"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда start отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/reminder/stop")
async def api_admin_reminder_stop(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        subprocess.run(["systemctl", "stop", "goals-reminder"], capture_output=True, text=True, timeout=5)
        return JSONResponse(content={"ok": True, "message": "Команда stop отправлена"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/admin/logs")
async def api_admin_logs(request: Request, source: str = "bot", n: int = 500):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    base = os.path.dirname(os.path.abspath(__file__))
    name = "bot.log" if source == "bot" else ("reminder.log" if source == "reminder" else "webapp.log")
    path = os.path.join(base, "logs", name)
    if not os.path.isfile(path):
        return JSONResponse(content={"lines": [], "path": path})
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-n:] if n else lines
        return JSONResponse(content={"lines": tail, "path": path})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/admin/users")
async def api_admin_users(request: Request):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        rows = await db.get_all_users_with_stats()
        out = []
        for r in rows:
            created = r.get("created_at")
            out.append({
                "user_id": r.get("user_id"),
                "username": r.get("username") or "",
                "first_name": r.get("first_name") or "",
                "last_name": r.get("last_name") or "",
                "display_name": r.get("display_name") or "",
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "missions_count": r.get("missions_count") or 0,
                "goals_count": r.get("goals_count") or 0,
                "habits_count": r.get("habits_count") or 0,
                "shaolen_requests": r.get("shaolen_requests") or 0,
                "reminders_count": r.get("reminders_count") or 0,
            })
        total = len(out)
        with_requests = sum(1 for x in out if (x.get("shaolen_requests") or 0) > 0)
        return JSONResponse(content={
            "users": out,
            "total_users": total,
            "users_with_shaolen_requests": with_requests,
        })
    except Exception as e:
        logger.exception("admin users: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


def _bmi_category(bmi_val: float) -> str:
    """Категория ИМТ по ВОЗ (как в app.js)."""
    if bmi_val is None or (isinstance(bmi_val, float) and (bmi_val != bmi_val)):
        return None
    if bmi_val < 18.5:
        return "Недостаток веса"
    if bmi_val <= 24.9:
        return "Норма"
    if bmi_val <= 29.9:
        return "Избыточный вес"
    return "Ожирение"


@app.get("/api/admin/users/{user_id}/data")
async def api_admin_user_data(request: Request, user_id: int):
    """Миссии, цели, привычки и профиль (рост, вес, возраст, ИМТ) пользователя (только для админа)."""
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        user = await db.get_user(user_id)
        profile_out = None
        if user:
            weight = user.get("weight")
            height = user.get("height")
            age = user.get("age")
            bmi_val = None
            if weight and height and height > 0:
                try:
                    bmi_val = round(float(weight) / ((float(height) / 100) ** 2), 1)
                except (TypeError, ValueError):
                    pass
            profile_out = {
                "height": float(height) if height is not None else None,
                "weight": float(weight) if weight is not None else None,
                "age": int(age) if age is not None else None,
                "bmi": bmi_val,
                "bmi_category": _bmi_category(bmi_val) if bmi_val is not None else None,
            }
        missions = await db.get_missions(user_id, include_completed=True)
        goals = await db.get_goals(user_id, include_completed=True)
        habits = await db.get_habits(user_id, active_only=False)
        def to_json_list(rows):
            return [_row_to_json(r) or {} for r in (rows or [])]
        return JSONResponse(content={
            "profile": profile_out,
            "missions": to_json_list(missions),
            "goals": to_json_list(goals),
            "habits": to_json_list(habits),
        })
    except Exception as e:
        logger.exception("admin user data: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/users/sync-telegram-names")
async def api_admin_sync_telegram_names(request: Request):
    """Синхронизация имён и username всех пользователей из Telegram API (getChat)."""
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    if not BOT_TOKEN:
        return JSONResponse(status_code=500, content={"detail": "BOT_TOKEN не задан"})
    try:
        user_ids = await db.get_all_user_ids()
        updated = 0
        failed_ids = []
        for uid in user_ids:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/getChat",
                        params={"chat_id": uid},
                    )
                data = r.json()
                if not data.get("ok"):
                    failed_ids.append(uid)
                    continue
                chat = data.get("result") or {}
                first_name = (chat.get("first_name") or "").strip() or None
                last_name = (chat.get("last_name") or "").strip() or None
                username = (chat.get("username") or "").strip() or None
                async with aiosqlite.connect(db.db_path) as conn:
                    await conn.execute(
                        """UPDATE users SET first_name = ?, last_name = ?, username = ?
                           WHERE user_id = ?""",
                        (first_name, last_name, username, uid),
                    )
                    await conn.commit()
                updated += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning("sync telegram names for %s: %s", uid, e)
                failed_ids.append(uid)
        return JSONResponse(content={
            "ok": True,
            "updated": updated,
            "failed": len(failed_ids),
            "failed_ids": failed_ids[:50],
        })
    except Exception as e:
        logger.exception("admin sync telegram names: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/broadcast")
async def api_admin_broadcast(request: Request):
    """Отправить сообщение всем пользователям через Telegram."""
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    if not BOT_TOKEN:
        return JSONResponse(status_code=500, content={"detail": "BOT_TOKEN не задан"})
    try:
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"detail": "Текст сообщения не может быть пустым"})
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Неверный JSON"})
    try:
        user_ids = await db.get_all_user_ids()
        sent = 0
        failed_ids = []
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        for uid in user_ids:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(url, json={"chat_id": uid, "text": text})
                if r.status_code == 200 and (r.json() or {}).get("ok"):
                    sent += 1
                else:
                    failed_ids.append(uid)
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning("broadcast to %s: %s", uid, e)
                failed_ids.append(uid)
        return JSONResponse(content={
            "ok": True,
            "sent": sent,
            "total": len(user_ids),
            "failed": len(failed_ids),
            "failed_ids": failed_ids[:50],
        })
    except Exception as e:
        logger.exception("admin broadcast: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/admin/users/{user_id}/reset-data")
async def api_admin_reset_user_data(request: Request, user_id: int):
    """Сброс миссий, целей, привычек и аналитики. Профиль не трогаем. Примеры восстанавливаются."""
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        await db.reset_user_data(user_id)
        return JSONResponse(content={"ok": True, "message": "Данные сброшены, примеры восстановлены"})
    except Exception as e:
        logger.exception("admin reset user data: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/admin/shaolen-requests")
async def api_admin_shaolen_requests(request: Request, limit: int = 200, offset: int = 0):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    try:
        rows = await db.get_shaolen_history_for_admin(limit=min(limit, 500), offset=offset)
        out = []
        for r in rows:
            created = r.get("created_at")
            out.append({
                "id": r.get("id"),
                "user_id": r.get("user_id"),
                "username": r.get("username") or "",
                "first_name": r.get("first_name") or "",
                "last_name": r.get("last_name") or "",
                "display_name": r.get("display_name") or "",
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "user_message": r.get("user_message") or "",
                "assistant_reply": r.get("assistant_reply") or "",
                "has_image": bool(r.get("has_image")),
            })
        return JSONResponse(content={"requests": out})
    except Exception as e:
        logger.exception("admin shaolen-requests: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBAPP_PORT", "8000"))
    logger.info(f"Запуск API сервера на порту {port}")
    logger.info("Примечание: Статика должна отдаваться через Nginx")
    logger.info("API endpoints доступны по адресу: http://0.0.0.0:{}/api/".format(port))
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)

