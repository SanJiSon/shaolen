import os
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles  # Не нужен, если используешь Nginx
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

from database import Database

load_dotenv()

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


# Инициализация БД теперь в lifespan выше


# Middleware для автоматического создания пользователя
@app.middleware("http")
async def ensure_user_exists(request: Request, call_next):
    """Создает пользователя автоматически при первом обращении к API"""
    # Проверяем, является ли запрос API запросом с user_id
    path = request.url.path
    
    if path.startswith("/api/user/") and request.method == "GET":
        try:
            # Извлекаем user_id из пути
            parts = path.split("/")
            if len(parts) >= 4:
                user_id = int(parts[3])
                # Создаем пользователя если его нет
                await db.add_user(user_id, None)
                logger.info(f"Пользователь {user_id} создан/проверен")
        except (ValueError, IndexError):
            pass  # Не API запрос с user_id
    
    response = await call_next(request)
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


@app.get("/api/user/{user_id}/missions", response_model=None)
async def api_get_missions(user_id: int):
    """Получение миссий пользователя"""
    try:
        logger.info(f"Запрос миссий для пользователя {user_id}")
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
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


@app.post("/api/missions")
async def api_add_mission(payload: MissionCreate):
    """Добавление миссии"""
    # Убеждаемся, что пользователь существует
    await db.add_user(payload.user_id, None)
    mission_id = await db.add_mission(payload.user_id, payload.title, payload.description or "")
    mission = await db.get_mission(mission_id)
    return mission


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
    """Получение целей пользователя"""
    try:
        logger.info(f"Запрос целей для пользователя {user_id}")
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
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
    # Убеждаемся, что пользователь существует
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
            return g
    raise HTTPException(status_code=404, detail="Goal not found after insert")


@app.get("/api/user/{user_id}/habits", response_model=None)
async def api_get_habits(user_id: int):
    """Получение привычек пользователя с текущими счетчиками"""
    try:
        logger.info(f"Запрос привычек для пользователя {user_id}")
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
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
    # Убеждаемся, что пользователь существует
    await db.add_user(payload.user_id, None)
    habit_id = await db.add_habit(payload.user_id, payload.title, payload.description or "")
    habits = await db.get_habits(payload.user_id, active_only=False)
    for h in habits:
        if h["id"] == habit_id:
            return h
    raise HTTPException(status_code=404, detail="Habit not found after insert")


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


@app.get("/api/user/{user_id}/analytics", response_model=None)
async def api_get_analytics(user_id: int):
    """Получение аналитики пользователя"""
    try:
        logger.info(f"Запрос аналитики для пользователя {user_id}")
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
        analytics = await db.get_user_analytics(user_id, days=30)
        
        # Преобразуем все числа в float для JSON
        result = {
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
                "total_completions": int(analytics.get("habits", {}).get("total_completions", 0))
            }
        }
        
        logger.info(f"Аналитика получена: {result}")
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Ошибка получения аналитики для пользователя {user_id}: {e}", exc_info=True)
        error_result = {
            "missions": {"total": 0, "completed": 0, "avg_progress": 0.0},
            "goals": {"total": 0, "completed": 0, "completion_rate": 0.0},
            "habits": {"total": 0, "total_completions": 0}
        }
        return JSONResponse(content=error_result)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBAPP_PORT", "8000"))
    logger.info(f"Запуск API сервера на порту {port}")
    logger.info("Примечание: Статика должна отдаваться через Nginx")
    logger.info("API endpoints доступны по адресу: http://0.0.0.0:{}/api/".format(port))
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)

