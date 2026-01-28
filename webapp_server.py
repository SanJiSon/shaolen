import base64
import io
import os
import re
import json
import hmac
import hashlib
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
SHAOLEN_MODEL = "llama-3.3-70b-versatile"
SHAOLEN_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


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


class MissionUpdate(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None


class GoalUpdate(BaseModel):
    title: str
    description: Optional[str] = ""
    deadline: Optional[str] = None
    priority: int = 1


class HabitUpdate(BaseModel):
    title: str
    description: Optional[str] = ""


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
    d = dict(obj) if hasattr(obj, "keys") else obj
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


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


@app.delete("/api/subgoals/{subgoal_id}")
async def api_delete_subgoal(subgoal_id: int):
    """Удалить подцель"""
    await db.delete_subgoal(subgoal_id)
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
                elif isinstance(value, (int, float, bool, str)):
                    clean_subgoal[key] = value
                else:
                    clean_subgoal[key] = str(value)
            result.append(clean_subgoal)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения подцелей для миссии {mission_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


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
    await db.update_goal(goal_id, payload.title, payload.description or "", payload.deadline, payload.priority)
    goal = await db.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return JSONResponse(content=_row_to_json(goal))


@app.get("/api/user/{user_id}/habits", response_model=None)
async def api_get_habits(user_id: int):
    """Получение привычек пользователя (user_id проверен через initData в middleware)."""
    try:
        logger.info(f"Запрос привычек для пользователя {user_id}")
        habits = await db.get_habits(user_id, active_only=False)
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
            result.append(clean_habit)
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения привычек для пользователя {user_id}: {e}", exc_info=True)
        return JSONResponse(content=[])


@app.post("/api/habits")
async def api_add_habit(payload: HabitCreate):
    """Добавление привычки"""
    await db.add_user(payload.user_id, None)
    habit_id = await db.add_habit(payload.user_id, payload.title, payload.description or "")
    habits = await db.get_habits(payload.user_id, active_only=False)
    for h in habits:
        if h["id"] == habit_id:
            return JSONResponse(content=_row_to_json(h))
    raise HTTPException(status_code=404, detail="Habit not found after insert")


@app.put("/api/habits/{habit_id}")
async def api_update_habit(habit_id: int, payload: HabitUpdate):
    """Редактирование привычки"""
    await db.update_habit(habit_id, payload.title, payload.description or "")
    habit = await db.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return JSONResponse(content=_row_to_json(habit))


@app.post("/api/habits/{habit_id}/increment")
async def api_increment_habit(habit_id: int):
    """Увеличить счетчик привычки на 1"""
    try:
        count = await db.increment_habit_count(habit_id)
        return {"count": count}
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
        await db.delete_mission(mission_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления миссии {mission_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/goals/{goal_id}")
async def api_delete_goal(goal_id: int):
    """Удаление цели"""
    try:
        await db.delete_goal(goal_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления цели {goal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/habits/{habit_id}")
async def api_delete_habit(habit_id: int):
    """Удаление привычки"""
    try:
        await db.delete_habit(habit_id)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Ошибка удаления привычки {habit_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None


class ShaolenAsk(BaseModel):
    message: Optional[str] = ""  # текст или пусто, если отправлено голосовое (тогда используется транскрипция)
    image_base64: Optional[str] = None  # data:image/jpeg;base64,... или только base64
    audio_base64: Optional[str] = None  # голосовое сообщение: base64 ogg/m4a/wav/webm (транскрибируется через Groq Whisper)
    history: Optional[List[Dict[str, Any]]] = None  # [{"role":"user"|"assistant","content":"..."}] — контекст диалога


@app.get("/api/user/{user_id}/profile", response_model=None)
async def api_get_profile(user_id: int):
    """Профиль пользователя: имя, отображаемое имя, статистика."""
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    out = {
        "user_id": user.get("user_id"),
        "username": user.get("username") or "",
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "display_name": user.get("display_name") or "",
    }
    return JSONResponse(content=out)


@app.put("/api/user/{user_id}/profile")
async def api_update_profile(user_id: int, payload: ProfileUpdate):
    """Сохранить отображаемое имя."""
    await db.update_user_display_name(user_id, payload.display_name)
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    out = {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "display_name": (user.get("display_name") or "").strip() or "",
    }
    return JSONResponse(content=out)


@app.post("/api/user/{user_id}/seed")
async def api_seed_user(user_id: int):
    """Добавить примеры миссий, целей и привычек, если у пользователя ещё пусто"""
    await db.seed_user_examples(user_id)
    return JSONResponse(content={"ok": True, "message": "Примеры добавлены или уже были"})


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
    """Транскрибировать голосовое через Groq Whisper. audio_b64 — base64 без префикса data:."""
    if not audio_b64 or not str(audio_b64).strip():
        return None
    s = str(audio_b64).strip()
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
        # Groq принимает (filename, bytes) или file-like; форматы: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
        out = client.audio.transcriptions.create(
            file=("audio.ogg", raw),
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
        model = SHAOLEN_VISION_MODEL
    else:
        user_content = text[:2000]
        model = SHAOLEN_MODEL

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
        chat = client.chat.completions.create(
            model=model,
            messages=messages_for_groq,
            max_tokens=800,
            temperature=0.7,
        )
        reply = (chat.choices[0].message.content or "").strip() if chat.choices else ""
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
    for item in from_groq:
        typ, title, subgoals = item[0], item[1], (item[2] if len(item) > 2 else [])
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
    return JSONResponse(content={
        "bot": "active" if bot_active else ("inactive" if bot_active is False else "unknown"),
        "webapp": "active" if webapp_active else ("inactive" if webapp_active is False else "unknown"),
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


@app.get("/api/admin/logs")
async def api_admin_logs(request: Request, source: str = "bot", n: int = 500):
    if not _admin_token(request):
        return JSONResponse(status_code=403, content=_admin_403_body())
    base = os.path.dirname(os.path.abspath(__file__))
    name = "bot.log" if source == "bot" else "webapp.log"
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

