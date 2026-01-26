import aiosqlite
from datetime import datetime
from typing import List, Optional, Dict
import json


class Database:
    def __init__(self, db_path: str = "goals_bot.db"):
        self.db_path = db_path

    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица миссий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    is_completed INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица подцелей (подцели миссий)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS subgoals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    is_completed INTEGER DEFAULT 0,
                    FOREIGN KEY (mission_id) REFERENCES missions(id)
                )
            """)

            # Таблица целей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    deadline TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    is_completed INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица привычек
            await db.execute("""
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица записей привычек (трекинг выполнения)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS habit_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    completed INTEGER DEFAULT 1,
                    FOREIGN KEY (habit_id) REFERENCES habits(id),
                    UNIQUE(habit_id, date)
                )
            """)

            # Таблица аналитики
            await db.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    goals_completed INTEGER DEFAULT 0,
                    habits_completed INTEGER DEFAULT 0,
                    missions_progress REAL DEFAULT 0.0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE(user_id, date)
                )
            """)

            await db.commit()

    async def add_user(self, user_id: int, username: Optional[str] = None):
        """Добавление пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            await db.commit()

    # === МИССИИ ===
    async def add_mission(self, user_id: int, title: str, description: str = "") -> int:
        """Добавление миссии"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO missions (user_id, title, description) VALUES (?, ?, ?)",
                (user_id, title, description)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_missions(self, user_id: int, include_completed: bool = False) -> List[Dict]:
        """Получение всех миссий пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM missions WHERE user_id = ?"
            if not include_completed:
                query += " AND is_completed = 0"
            query += " ORDER BY created_at DESC"
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_mission(self, mission_id: int) -> Optional[Dict]:
        """Получение миссии по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def complete_mission(self, mission_id: int):
        """Завершение миссии"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE missions SET is_completed = 1, completed_at = ? WHERE id = ?",
                (datetime.now(), mission_id)
            )
            await db.commit()

    async def delete_mission(self, mission_id: int):
        """Удаление миссии"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
            await db.execute("DELETE FROM subgoals WHERE mission_id = ?", (mission_id,))
            await db.commit()

    # === ПОДЦЕЛИ ===
    async def add_subgoal(self, mission_id: int, title: str, description: str = "") -> int:
        """Добавление подцели к миссии"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO subgoals (mission_id, title, description) VALUES (?, ?, ?)",
                (mission_id, title, description)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_subgoals(self, mission_id: int) -> List[Dict]:
        """Получение всех подцелей миссии"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subgoals WHERE mission_id = ? ORDER BY created_at ASC",
                (mission_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_subgoal(self, subgoal_id: int) -> Optional[Dict]:
        """Получение подцели по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM subgoals WHERE id = ?", (subgoal_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def complete_subgoal(self, subgoal_id: int):
        """Завершение подцели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subgoals SET is_completed = 1, completed_at = ? WHERE id = ?",
                (datetime.now(), subgoal_id)
            )
            await db.commit()

    async def delete_subgoal(self, subgoal_id: int):
        """Удаление подцели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM subgoals WHERE id = ?", (subgoal_id,))
            await db.commit()

    # === ЦЕЛИ ===
    async def add_goal(self, user_id: int, title: str, description: str = "", 
                      deadline: Optional[str] = None, priority: int = 1) -> int:
        """Добавление цели"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO goals (user_id, title, description, deadline, priority) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, description, deadline, priority)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_goals(self, user_id: int, include_completed: bool = False) -> List[Dict]:
        """Получение всех целей пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM goals WHERE user_id = ?"
            if not include_completed:
                query += " AND is_completed = 0"
            query += " ORDER BY priority DESC, created_at DESC"
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def complete_goal(self, goal_id: int):
        """Завершение цели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE goals SET is_completed = 1, completed_at = ? WHERE id = ?",
                (datetime.now(), goal_id)
            )
            await db.commit()

    async def delete_goal(self, goal_id: int):
        """Удаление цели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            await db.commit()

    # === ПРИВЫЧКИ ===
    async def add_habit(self, user_id: int, title: str, description: str = "") -> int:
        """Добавление привычки"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO habits (user_id, title, description) VALUES (?, ?, ?)",
                (user_id, title, description)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_habits(self, user_id: int, active_only: bool = True) -> List[Dict]:
        """Получение всех привычек пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM habits WHERE user_id = ?"
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY created_at DESC"
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def toggle_habit_record(self, habit_id: int, date: str) -> bool:
        """Переключение выполнения привычки на дату (возвращает True если выполнена)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существующую запись
            async with db.execute(
                "SELECT completed FROM habit_records WHERE habit_id = ? AND date = ?",
                (habit_id, date)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    new_status = 0 if row[0] else 1
                    await db.execute(
                        "UPDATE habit_records SET completed = ? WHERE habit_id = ? AND date = ?",
                        (new_status, habit_id, date)
                    )
                else:
                    await db.execute(
                        "INSERT INTO habit_records (habit_id, date, completed) VALUES (?, ?, 1)",
                        (habit_id, date)
                    )
                    new_status = 1
            await db.commit()
            return new_status == 1

    async def get_habit_stats(self, habit_id: int, days: int = 30) -> Dict:
        """Получение статистики привычки за последние N дней"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT COUNT(*) as total, SUM(completed) as completed 
                   FROM habit_records 
                   WHERE habit_id = ? AND date >= date('now', '-' || ? || ' days')""",
                (habit_id, days)
            ) as cursor:
                row = await cursor.fetchone()
                total = row[0] or 0
                completed = row[1] or 0
                return {
                    "total_days": total,
                    "completed_days": completed,
                    "completion_rate": (completed / total * 100) if total > 0 else 0
                }

    async def delete_habit(self, habit_id: int):
        """Удаление привычки"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
            await db.execute("DELETE FROM habit_records WHERE habit_id = ?", (habit_id,))
            await db.commit()

    # === АНАЛИТИКА ===
    async def get_user_analytics(self, user_id: int, days: int = 30) -> Dict:
        """Получение аналитики пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            # Статистика целей
            async with db.execute(
                """SELECT COUNT(*) as total, SUM(is_completed) as completed 
                   FROM goals WHERE user_id = ? AND created_at >= date('now', '-' || ? || ' days')""",
                (user_id, days)
            ) as cursor:
                goals_row = await cursor.fetchone()
                goals_total = goals_row[0] or 0
                goals_completed = goals_row[1] or 0

            # Статистика привычек
            async with db.execute(
                """SELECT COUNT(DISTINCT h.id) as total_habits,
                          SUM(CASE WHEN hr.completed = 1 THEN 1 ELSE 0 END) as total_completions
                   FROM habits h
                   LEFT JOIN habit_records hr ON h.id = hr.habit_id 
                   WHERE h.user_id = ? AND hr.date >= date('now', '-' || ? || ' days')""",
                (user_id, days)
            ) as cursor:
                habits_row = await cursor.fetchone()
                habits_total = habits_row[0] or 0
                habits_completions = habits_row[1] or 0

            # Статистика миссий
            async with db.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) as completed,
                          AVG(CASE 
                              WHEN is_completed = 1 THEN 1.0 
                              ELSE (SELECT CAST(COUNT(CASE WHEN is_completed = 1 THEN 1 END) AS REAL) / 
                                           NULLIF(COUNT(*), 0) FROM subgoals WHERE mission_id = missions.id)
                          END) as avg_progress
                   FROM missions WHERE user_id = ? AND created_at >= date('now', '-' || ? || ' days')""",
                (user_id, days)
            ) as cursor:
                missions_row = await cursor.fetchone()
                missions_total = missions_row[0] or 0
                missions_completed = missions_row[1] or 0
                missions_progress = missions_row[2] or 0.0

            return {
                "goals": {
                    "total": goals_total,
                    "completed": goals_completed,
                    "completion_rate": (goals_completed / goals_total * 100) if goals_total > 0 else 0
                },
                "habits": {
                    "total": habits_total,
                    "total_completions": habits_completions
                },
                "missions": {
                    "total": missions_total,
                    "completed": missions_completed,
                    "avg_progress": missions_progress * 100
                }
            }
