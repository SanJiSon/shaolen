import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from database import Database

load_dotenv()

app = FastAPI(title="Goals WebApp API")

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
    await db.init_db()


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
    return await db.get_missions(user_id, include_completed=True)


@app.post("/api/missions")
async def api_add_mission(payload: MissionCreate):
    mission_id = await db.add_mission(payload.user_id, payload.title, payload.description or "")
    mission = await db.get_mission(mission_id)
    return mission


@app.get("/api/mission/{mission_id}/subgoals")
async def api_get_subgoals(mission_id: int):
    return await db.get_subgoals(mission_id)


@app.get("/api/user/{user_id}/goals")
async def api_get_goals(user_id: int):
    return await db.get_goals(user_id, include_completed=True)


@app.post("/api/goals")
async def api_add_goal(payload: GoalCreate):
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
    return await db.get_habits(user_id, active_only=False)


@app.post("/api/habits")
async def api_add_habit(payload: HabitCreate):
    habit_id = await db.add_habit(payload.user_id, payload.title, payload.description or "")
    habits = await db.get_habits(payload.user_id, active_only=False)
    for h in habits:
        if h["id"] == habit_id:
            return h
    raise HTTPException(status_code=404, detail="Habit not found after insert")


@app.get("/api/user/{user_id}/analytics")
async def api_get_analytics(user_id: int):
    return await db.get_user_analytics(user_id, days=30)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBAPP_PORT", "8000"))
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)

