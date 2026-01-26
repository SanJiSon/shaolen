import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

from database import Database

load_dotenv()

app = FastAPI(title="Goals WebApp API")
logger = logging.getLogger(__name__)

db = Database()


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


@app.on_event("startup")
async def on_startup():
    try:
        await db.init_db()
        logger.info(f"База данных инициализирована: {db.db_path}")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise


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


# Статика — сама веб‑страница Telegram WebApp
static_dir = os.path.join(os.path.dirname(__file__), "webapp")
os.makedirs(static_dir, exist_ok=True)

from fastapi.responses import FileResponse, HTMLResponse

# Корневой роут для index.html (Telegram WebApp должен открывать полный URL)
@app.get("/", response_class=HTMLResponse)
async def root():
    """Корневой роут - отдаем index.html"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebApp not found</h1>", status_code=404)

@app.get("/index.html", response_class=HTMLResponse)
async def index_html():
    """Прямой доступ к index.html"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>WebApp not found</h1>", status_code=404)

# Монтируем статику для CSS, JS и других файлов
# Используем отдельный роут для статики, чтобы не конфликтовать с корневым
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Также монтируем на /webapp для обратной совместимости
app.mount("/webapp", StaticFiles(directory=static_dir, html=True), name="webapp")


@app.get("/api/user/{user_id}/missions")
async def api_get_missions(user_id: int):
    """Получение миссий пользователя"""
    try:
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
        missions = await db.get_missions(user_id, include_completed=True)
        return missions if missions else []
    except Exception as e:
        logger.error(f"Ошибка получения миссий для пользователя {user_id}: {e}")
        return []


@app.post("/api/missions")
async def api_add_mission(payload: MissionCreate):
    """Добавление миссии"""
    # Убеждаемся, что пользователь существует
    await db.add_user(payload.user_id, None)
    mission_id = await db.add_mission(payload.user_id, payload.title, payload.description or "")
    mission = await db.get_mission(mission_id)
    return mission


@app.get("/api/mission/{mission_id}/subgoals")
async def api_get_subgoals(mission_id: int):
    return await db.get_subgoals(mission_id)


@app.get("/api/user/{user_id}/goals")
async def api_get_goals(user_id: int):
    """Получение целей пользователя"""
    # Убеждаемся, что пользователь существует
    await db.add_user(user_id, None)
    goals = await db.get_goals(user_id, include_completed=True)
    return goals if goals else []


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


@app.get("/api/user/{user_id}/habits")
async def api_get_habits(user_id: int):
    """Получение привычек пользователя с текущими счетчиками"""
    try:
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
        habits = await db.get_habits(user_id, active_only=False)
        # Преобразуем today_count в обычное число
        for habit in habits:
            if 'today_count' in habit:
                habit['today_count'] = habit['today_count'] or 0
        return habits if habits else []
    except Exception as e:
        logger.error(f"Ошибка получения привычек для пользователя {user_id}: {e}")
        return []


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


@app.get("/api/user/{user_id}/analytics")
async def api_get_analytics(user_id: int):
    """Получение аналитики пользователя"""
    try:
        # Убеждаемся, что пользователь существует
        await db.add_user(user_id, None)
        analytics = await db.get_user_analytics(user_id, days=30)
        return analytics
    except Exception as e:
        logger.error(f"Ошибка получения аналитики для пользователя {user_id}: {e}")
        return {
            "missions": {"total": 0, "completed": 0, "avg_progress": 0},
            "goals": {"total": 0, "completed": 0, "completion_rate": 0},
            "habits": {"total": 0, "total_completions": 0}
        }


if __name__ == "__main__":
    import uvicorn
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    port = int(os.getenv("WEBAPP_PORT", "8000"))
    logger.info(f"Запуск веб-сервера на порту {port}")
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)

