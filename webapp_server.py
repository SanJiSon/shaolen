import os
import json
import hmac
import hashlib
from contextlib import asynccontextmanager
from urllib.parse import unquote
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

from database import Database

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBAPP_PORT", "8000"))
    logger.info(f"Запуск API сервера на порту {port}")
    logger.info("Примечание: Статика должна отдаваться через Nginx")
    logger.info("API endpoints доступны по адресу: http://0.0.0.0:{}/api/".format(port))
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)

