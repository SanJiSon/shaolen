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
                    first_name TEXT,
                    last_name TEXT,
                    display_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col in ("first_name", "last_name", "display_name"):
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                except Exception:
                    pass
            for col, typ in [
                ("gender", "TEXT"), ("weight", "REAL"), ("height", "REAL"), ("age", "INTEGER"),
                ("target_weight", "REAL"), ("city", "TEXT"), ("country", "TEXT"), ("country_code", "TEXT"), ("geo_consent", "INTEGER"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
                except Exception:
                    pass

            # История веса (одна запись на пользователя на дату; только день, без времени суток)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS weight_history (
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    weight REAL NOT NULL,
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Таблица миссий
            await db.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    deadline TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    is_completed INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            try:
                await db.execute("ALTER TABLE missions ADD COLUMN deadline TEXT")
            except Exception:
                pass
            for col, default in [("is_example", "0")]:
                try:
                    await db.execute(f"ALTER TABLE missions ADD COLUMN {col} INTEGER DEFAULT {default}")
                except Exception:
                    pass

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
            try:
                await db.execute("ALTER TABLE goals ADD COLUMN is_example INTEGER DEFAULT 0")
            except Exception:
                pass

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
            try:
                await db.execute("ALTER TABLE habits ADD COLUMN is_example INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE habits ADD COLUMN is_water_calculated INTEGER DEFAULT 0")
            except Exception:
                pass
            for tbl, col in [("subgoals", "sort_order"), ("goals", "sort_order"), ("habits", "sort_order")]:
                try:
                    await db.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} INTEGER")
                except Exception:
                    pass

            # Таблица записей привычек (трекинг выполнения)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS habit_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    completed INTEGER DEFAULT 1,
                    count INTEGER DEFAULT 0,
                    FOREIGN KEY (habit_id) REFERENCES habits(id),
                    UNIQUE(habit_id, date)
                )
            """)
            
            # Добавляем колонку count если её нет (для существующих БД)
            try:
                await db.execute("ALTER TABLE habit_records ADD COLUMN count INTEGER DEFAULT 0")
            except:
                pass  # Колонка уже существует

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

            # Лимит запросов к «мастеру Шаолень» по пользователю и дню
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shaolen_daily_requests (
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    request_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Пользователи, которым уже выдавались примеры (если удалили — не добавлять снова)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_examples_seeded (
                    user_id INTEGER PRIMARY KEY,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # История запросов к Шаолень (для кнопки «История»)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shaolen_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_message TEXT NOT NULL,
                    assistant_reply TEXT NOT NULL,
                    has_image INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Капсула времени — одна на пользователя (активная)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS time_capsule (
                    user_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    expected_result TEXT NOT NULL,
                    open_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            # История капсул после открытия (для саморефлексии)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS time_capsule_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    expected_result TEXT NOT NULL,
                    open_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP,
                    viewed_at TIMESTAMP NOT NULL,
                    reflection TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            await db.commit()

    async def add_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ):
        """Добавление или обновление пользователя."""
        un = username or ""
        fn = first_name or ""
        ln = last_name or ""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO users (user_id, username, first_name, last_name)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     username = excluded.username,
                     first_name = CASE WHEN trim(excluded.first_name) != '' THEN excluded.first_name ELSE users.first_name END,
                     last_name = CASE WHEN trim(excluded.last_name) != '' THEN excluded.last_name ELSE users.last_name END
                """,
                (user_id, un, fn, ln),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение пользователя по ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    async def update_user_display_name(self, user_id: int, display_name: Optional[str]) -> None:
        """Обновить отображаемое имя пользователя."""
        dn = (display_name or "").strip() or None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET display_name = ? WHERE user_id = ?", (dn, user_id))
            await db.commit()

    async def update_user_profile_extended(
        self,
        user_id: int,
        gender: Optional[str] = None,
        weight: Optional[float] = None,
        height: Optional[float] = None,
        age: Optional[int] = None,
        target_weight: Optional[float] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        country_code: Optional[str] = None,
        geo_consent: Optional[int] = None,
    ) -> None:
        """Обновить расширенные поля профиля (пол, вес, рост, возраст, цель, город, страна, код страны, согласие на гео)."""
        async with aiosqlite.connect(self.db_path) as db:
            updates, vals = [], []
            if gender is not None:
                updates.append("gender = ?")
                vals.append((gender or "").strip() or None)
            if weight is not None:
                updates.append("weight = ?")
                vals.append(weight if weight > 0 else None)
            if height is not None:
                updates.append("height = ?")
                vals.append(height if height > 0 else None)
            if age is not None:
                updates.append("age = ?")
                vals.append(age if age > 0 else None)
            if target_weight is not None:
                updates.append("target_weight = ?")
                vals.append(target_weight if target_weight > 0 else None)
            if city is not None:
                updates.append("city = ?")
                vals.append((city or "").strip() or None)
            if country is not None:
                updates.append("country = ?")
                vals.append((country or "").strip() or None)
            if country_code is not None:
                code = (country_code or "").strip().upper()
                updates.append("country_code = ?")
                vals.append(code if len(code) == 2 else None)
            if geo_consent is not None:
                updates.append("geo_consent = ?")
                vals.append(1 if geo_consent else 0)
            if not updates:
                return
            vals.append(user_id)
            await db.execute(
                "UPDATE users SET " + ", ".join(updates) + " WHERE user_id = ?",
                vals,
            )
            await db.commit()

    async def add_weight_entry(self, user_id: int, date: str, weight: float) -> None:
        """Добавить/обновить запись веса на дату (date в формате YYYY-MM-DD)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO weight_history (user_id, date, weight) VALUES (?, ?, ?)",
                (user_id, date, weight),
            )
            await db.commit()

    async def get_weight_history(
        self, user_id: int, period: str = "7"
    ) -> List[Dict]:
        """История веса за период: 7 (последние 7 точек), week, month, 6months, year."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if period == "7":
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? ORDER BY date DESC LIMIT 7
                """
                async with db.execute(query, (user_id,)) as c:
                    rows = await c.fetchall()
                    return [dict(r) for r in reversed(rows)]
            elif period == "week":
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? AND date >= date('now', '-7 days')
                    ORDER BY date ASC
                """
            elif period == "month":
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? AND date >= date('now', '-1 month')
                    ORDER BY date ASC
                """
            elif period == "6months":
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? AND date >= date('now', '-6 months')
                    ORDER BY date ASC
                """
            elif period == "year":
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? AND date >= date('now', '-1 year')
                    ORDER BY date ASC
                """
            else:
                query = """
                    SELECT date, weight FROM weight_history
                    WHERE user_id = ? ORDER BY date DESC LIMIT 7
                """
            async with db.execute(query, (user_id,)) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    # === МИССИИ ===
    async def add_mission(self, user_id: int, title: str, description: str = "", deadline: Optional[str] = None, is_example: int = 0) -> int:
        """Добавление миссии. is_example=1 — предустановленный пример."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO missions (user_id, title, description, deadline, is_example) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, description or "", deadline, 1 if is_example else 0)
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

    async def update_mission(self, mission_id: int, title: str, description: str = "", deadline: Optional[str] = None) -> bool:
        """Обновление миссии. После сохранения пользователем снимается метка «пример»."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE missions SET title = ?, description = ?, deadline = ?, is_example = 0 WHERE id = ?",
                (title, description or "", deadline, mission_id)
            )
            await db.commit()
            return True

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
            async with db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM subgoals WHERE mission_id = ?",
                (mission_id,)
            ) as c:
                row = await c.fetchone()
                sort_order = row[0] if row and row[0] is not None else 0
            cursor = await db.execute(
                "INSERT INTO subgoals (mission_id, title, description, sort_order) VALUES (?, ?, ?, ?)",
                (mission_id, title, description, sort_order)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_subgoals(self, mission_id: int) -> List[Dict]:
        """Получение всех подцелей миссии (по sort_order, затем по id)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subgoals WHERE mission_id = ? ORDER BY COALESCE(sort_order, 999999), id ASC",
                (mission_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def set_subgoals_order(self, mission_id: int, subgoal_ids: List[int]) -> None:
        """Установить порядок подцелей (список id в нужном порядке)."""
        if not subgoal_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            for i, sg_id in enumerate(subgoal_ids):
                await db.execute(
                    "UPDATE subgoals SET sort_order = ? WHERE id = ? AND mission_id = ?",
                    (i, sg_id, mission_id)
                )
            await db.commit()

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

    async def uncomplete_subgoal(self, subgoal_id: int):
        """Снять отметку выполнения подцели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subgoals SET is_completed = 0, completed_at = NULL WHERE id = ?",
                (subgoal_id,)
            )
            await db.commit()

    async def delete_subgoal(self, subgoal_id: int):
        """Удаление подцели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM subgoals WHERE id = ?", (subgoal_id,))
            await db.commit()

    # === ЦЕЛИ ===
    async def add_goal(self, user_id: int, title: str, description: str = "",
                      deadline: Optional[str] = None, priority: int = 1, is_example: int = 0) -> int:
        """Добавление цели. is_example=1 — предустановленный пример."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM goals WHERE user_id = ?",
                (user_id,)
            ) as c:
                row = await c.fetchone()
                sort_order = row[0] if row and row[0] is not None else 0
            cursor = await db.execute(
                "INSERT INTO goals (user_id, title, description, deadline, priority, is_example, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, title, description, deadline, priority, 1 if is_example else 0, sort_order)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_goals(self, user_id: int, include_completed: bool = False) -> List[Dict]:
        """Получение всех целей пользователя (по sort_order, затем priority, created_at)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM goals WHERE user_id = ?"
            if not include_completed:
                query += " AND is_completed = 0"
            query += " ORDER BY COALESCE(sort_order, 999999), priority DESC, created_at DESC"
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def set_goals_order(self, user_id: int, goal_ids: List[int]) -> None:
        """Установить порядок целей (список id в нужном порядке)."""
        if not goal_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            for i, gid in enumerate(goal_ids):
                await db.execute(
                    "UPDATE goals SET sort_order = ? WHERE id = ? AND user_id = ?",
                    (i, gid, user_id)
                )
            await db.commit()

    async def get_goal(self, goal_id: int) -> Optional[Dict]:
        """Получение цели по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def complete_goal(self, goal_id: int):
        """Завершение цели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE goals SET is_completed = 1, completed_at = ? WHERE id = ?",
                (datetime.now(), goal_id)
            )
            await db.commit()

    async def update_goal(self, goal_id: int, title: str, description: str = "",
                         deadline: Optional[str] = None, priority: int = 1) -> bool:
        """Обновление цели. После сохранения пользователем снимается метка «пример»."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE goals SET title = ?, description = ?, deadline = ?, priority = ?, is_example = 0
                   WHERE id = ?""",
                (title, description or "", deadline, priority, goal_id)
            )
            await db.commit()
            return True

    async def delete_goal(self, goal_id: int):
        """Удаление цели"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            await db.commit()

    # === ПРИВЫЧКИ ===
    async def add_habit(self, user_id: int, title: str, description: str = "", is_example: int = 0, is_water_calculated: int = 0) -> int:
        """Добавление привычки. is_example=1 — пример; is_water_calculated=1 — рассчитана автоматически (вода)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM habits WHERE user_id = ?",
                (user_id,)
            ) as c:
                row = await c.fetchone()
                sort_order = row[0] if row and row[0] is not None else 0
            cursor = await db.execute(
                "INSERT INTO habits (user_id, title, description, is_example, is_water_calculated, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, title, description, 1 if is_example else 0, 1 if is_water_calculated else 0, sort_order)
            )
            await db.commit()
            return cursor.lastrowid

    async def update_habit(self, habit_id: int, title: str, description: str = "") -> bool:
        """Обновление привычки. После сохранения пользователем снимается метка «пример» и «рассчитана автоматически»."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE habits SET title = ?, description = ?, is_example = 0, is_water_calculated = 0 WHERE id = ?",
                (title, description or "", habit_id)
            )
            await db.commit()
            return True

    async def get_habit(self, habit_id: int) -> Optional[Dict]:
        """Получение привычки по ID (без today_count)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_habits(self, user_id: int, active_only: bool = True) -> List[Dict]:
        """Получение всех привычек пользователя с текущим счетчиком на сегодня"""
        from datetime import date
        today = date.today().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT h.*, 
                       COALESCE(hr.count, 0) as today_count
                FROM habits h
                LEFT JOIN habit_records hr ON h.id = hr.habit_id AND hr.date = ?
                WHERE h.user_id = ?
            """
            if active_only:
                query += " AND h.is_active = 1"
            query += " ORDER BY COALESCE(h.sort_order, 999999), h.created_at DESC"
            async with db.execute(query, (today, user_id)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def set_habits_order(self, user_id: int, habit_ids: List[int]) -> None:
        """Установить порядок привычек (список id в нужном порядке)."""
        if not habit_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            for i, hid in enumerate(habit_ids):
                await db.execute(
                    "UPDATE habits SET sort_order = ? WHERE id = ? AND user_id = ?",
                    (i, hid, user_id)
                )
            await db.commit()

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

    async def increment_habit_count(self, habit_id: int, date: str = None) -> int:
        """Увеличивает счетчик привычки на 1 для указанной даты (по умолчанию сегодня)"""
        from datetime import date as dt_date
        if date is None:
            date = dt_date.today().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существующую запись
            async with db.execute(
                "SELECT count FROM habit_records WHERE habit_id = ? AND date = ?",
                (habit_id, date)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    new_count = (row[0] or 0) + 1
                    await db.execute(
                        "UPDATE habit_records SET count = ? WHERE habit_id = ? AND date = ?",
                        (new_count, habit_id, date)
                    )
                else:
                    new_count = 1
                    await db.execute(
                        "INSERT INTO habit_records (habit_id, date, count, completed) VALUES (?, ?, 1, 1)",
                        (habit_id, date)
                    )
            await db.commit()
            return new_count

    async def decrement_habit_count(self, habit_id: int, date: str = None) -> int:
        """Уменьшает счетчик привычки на 1 для указанной даты (по умолчанию сегодня)"""
        from datetime import date as dt_date
        if date is None:
            date = dt_date.today().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существующую запись
            async with db.execute(
                "SELECT count FROM habit_records WHERE habit_id = ? AND date = ?",
                (habit_id, date)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] and row[0] > 0:
                    new_count = row[0] - 1
                    if new_count > 0:
                        await db.execute(
                            "UPDATE habit_records SET count = ? WHERE habit_id = ? AND date = ?",
                            (new_count, habit_id, date)
                        )
                    else:
                        # Удаляем запись если счетчик стал 0
                        await db.execute(
                            "DELETE FROM habit_records WHERE habit_id = ? AND date = ?",
                            (habit_id, date)
                        )
                        new_count = 0
                else:
                    new_count = 0
            await db.commit()
            return new_count

    async def delete_habit(self, habit_id: int):
        """Удаление привычки"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
            await db.execute("DELETE FROM habit_records WHERE habit_id = ?", (habit_id,))
            await db.commit()

    async def get_todays_habit_titles(self, user_id: int) -> List[str]:
        """Список названий привычек, отмеченных сегодня (хотя бы одно выполнение)."""
        from datetime import date
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT h.title FROM habits h
                JOIN habit_records hr ON h.id = hr.habit_id AND hr.date = ?
                WHERE h.user_id = ?
                ORDER BY h.title
                """,
                (today, user_id),
            ) as cursor:
                rows = await cursor.fetchall()
                return [str(row[0] or "").strip() for row in rows if row[0]]

    async def get_habit_completions_by_date(self, user_id: int, days: int = 30) -> List[Dict]:
        """По дням: дата и суммарное количество выполнений привычек за день (для графика)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT hr.date, SUM(COALESCE(hr.count, 0)) as total
                FROM habit_records hr
                JOIN habits h ON h.id = hr.habit_id AND h.user_id = ?
                WHERE hr.date >= date('now', '-' || ? || ' days')
                GROUP BY hr.date
                ORDER BY hr.date
                """,
                (user_id, days),
            ) as cursor:
                rows = await cursor.fetchall()
                return [{"date": row[0], "completions": int(row[1] or 0)} for row in rows]

    async def get_habit_streak(self, user_id: int) -> int:
        """Текущая серия дней подряд с хотя бы одним выполнением привычки (считая сегодня)."""
        by_date = await self.get_habit_completions_by_date(user_id, days=365)
        if not by_date:
            return 0
        by_date_dict = {r["date"]: r["completions"] for r in by_date}
        from datetime import date, timedelta
        today = date.today().isoformat()
        streak = 0
        d = date.today()
        for _ in range(365):
            key = d.isoformat()
            if by_date_dict.get(key, 0) > 0:
                streak += 1
                d -= timedelta(days=1)
            else:
                break
        return streak

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

            # Статистика привычек (total_completions = сумма count по всем записям, как на графике)
            async with db.execute(
                """SELECT COUNT(DISTINCT h.id) as total_habits,
                          COALESCE(SUM(hr.count), 0) as total_completions
                   FROM habits h
                   LEFT JOIN habit_records hr ON h.id = hr.habit_id AND hr.date >= date('now', '-' || ? || ' days')
                   WHERE h.user_id = ?""",
                (days, user_id)
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

    async def user_examples_were_seeded_once(self, user_id: int) -> bool:
        """Были ли этому пользователю уже когда-то выданы примеры (если удалил — не добавлять снова)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM user_examples_seeded WHERE user_id = ? LIMIT 1",
                (user_id,),
            ) as c:
                return (await c.fetchone()) is not None

    async def user_has_examples(self, user_id: int) -> bool:
        """Есть ли у пользователя сейчас предустановленные примеры (миссии/цели/привычки с is_example=1)."""
        async with aiosqlite.connect(self.db_path) as db:
            for table in ["missions", "goals", "habits"]:
                try:
                    async with db.execute(
                        f"SELECT 1 FROM {table} WHERE user_id = ? AND is_example = 1 LIMIT 1",
                        (user_id,),
                    ) as c:
                        if (await c.fetchone()) is not None:
                            return True
                except Exception:
                    pass  # колонка is_example может отсутствовать в старых БД
        return False

    async def _mark_examples_seeded(self, user_id: int) -> None:
        """Отметить, что этому пользователю уже выдавались примеры (чтобы при удалении не добавлять снова)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_examples_seeded (user_id) VALUES (?)",
                (user_id,),
            )
            await db.commit()

    async def ensure_user_examples(self, user_id: int) -> None:
        """Добавить предустановленные примеры только если пользователь новый (никогда не получал примеры).
        Если пользователь когда-то удалил примеры — повторно не добавляем."""
        if await self.user_examples_were_seeded_once(user_id):
            return
        if await self.user_has_examples(user_id):
            await self._mark_examples_seeded(user_id)
            return
        await self.add_user(user_id)
        await self.seed_user_examples(user_id)
        await self._mark_examples_seeded(user_id)

    async def seed_user_examples(self, user_id: int) -> None:
        """Добавляет предустановленные примеры миссий, целей и привычек (с меткой is_example=1)."""
        # Примеры привычек
        examples_habits = [
            ("Пить воду", "Стакан воды утром и в течение дня"),
            ("Зарядка", "10–15 минут утренней разминки"),
            ("Читать", "Хотя бы 10 минут чтения"),
            ("Прогулка", "Пройти 5000+ шагов"),
        ]
        for title, desc in examples_habits:
            await self.add_habit(user_id, title, desc, is_example=1)
        # Пример миссии с подцелями
        mid = await self.add_mission(
            user_id,
            "Здоровый образ жизни",
            "Регулярные привычки и цели на месяц",
            None,
            is_example=1,
        )
        for title, _ in [("Настроить режим сна", ""), ("Добавить привычки в приложение", ""), ("Первый отчёт через неделю", "")]:
            await self.add_subgoal(mid, title, "")
        # Примеры целей
        from datetime import date, timedelta
        d1 = (date.today() + timedelta(days=7)).isoformat()
        d2 = (date.today() + timedelta(days=30)).isoformat()
        await self.add_goal(user_id, "Пройти 5 км без остановки", "Постепенно увеличивать дистанцию", d1, 2, is_example=1)
        await self.add_goal(user_id, "Прочитать одну книгу", "Выбрать книгу и читать по 15 минут в день", d2, 1, is_example=1)

    # === Мастер Шаолень (лимит запросов в день) ===
    async def get_shaolen_requests_today(self, user_id: int) -> int:
        """Количество запросов к Шаолень за сегодня."""
        from datetime import date
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT request_count FROM shaolen_daily_requests WHERE user_id = ? AND date = ?",
                (user_id, today),
            ) as c:
                row = await c.fetchone()
                return int(row[0]) if row else 0

    async def increment_shaolen_requests(self, user_id: int) -> None:
        """Увеличить счётчик запросов к Шаолень на сегодня на 1."""
        from datetime import date
        today = date.today().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO shaolen_daily_requests (user_id, date, request_count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(user_id, date) DO UPDATE SET request_count = request_count + 1""",
                (user_id, today),
            )
            await db.commit()

    async def add_shaolen_history(
        self, user_id: int, user_message: str, assistant_reply: str, has_image: bool = False
    ) -> None:
        """Добавить запись в историю запросов Шаолень."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO shaolen_history (user_id, user_message, assistant_reply, has_image)
                   VALUES (?, ?, ?, ?)""",
                (user_id, (user_message or "")[:4000], (assistant_reply or "")[:16000], 1 if has_image else 0),
            )
            await db.commit()

    async def get_shaolen_history(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Последние записи истории Шаолень по пользователю."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, user_id, created_at, user_message, assistant_reply, has_image
                   FROM shaolen_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            ) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    async def get_all_users_with_stats(self) -> List[Dict]:
        """Для админки: все пользователи и агрегаты (число миссий, целей, привычек, запросов к Шаолень)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT u.user_id, u.username, u.first_name, u.last_name, u.display_name, u.created_at,
                          (SELECT COUNT(*) FROM missions m WHERE m.user_id = u.user_id) AS missions_count,
                          (SELECT COUNT(*) FROM goals g WHERE g.user_id = u.user_id) AS goals_count,
                          (SELECT COUNT(*) FROM habits h WHERE h.user_id = u.user_id) AS habits_count,
                          (SELECT COUNT(*) FROM shaolen_history sh WHERE sh.user_id = u.user_id) AS shaolen_requests
                   FROM users u ORDER BY u.user_id"""
            ) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    async def get_shaolen_history_for_admin(self, limit: int = 200, offset: int = 0) -> List[Dict]:
        """Для админки: последние запросы к Шаолень с данными пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT sh.id, sh.user_id, sh.created_at, sh.user_message, sh.assistant_reply, sh.has_image,
                          u.username, u.first_name, u.last_name, u.display_name
                   FROM shaolen_history sh
                   LEFT JOIN users u ON u.user_id = sh.user_id
                   ORDER BY sh.created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    # === КАПСУЛА ВРЕМЕНИ (одна на пользователя) ===
    async def get_time_capsule(self, user_id: int) -> Optional[Dict]:
        """Получить капсулу пользователя, если есть."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM time_capsule WHERE user_id = ?", (user_id,)
            ) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    async def create_time_capsule(
        self,
        user_id: int,
        title: str,
        expected_result: str,
        open_at: datetime,
    ) -> None:
        """Создать капсулу (одна на пользователя, заменяет существующую при повторе)."""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO time_capsule
                   (user_id, title, expected_result, open_at, created_at, last_edited_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, title.strip(), expected_result.strip(), open_at, now, now),
            )
            await db.commit()

    async def update_time_capsule(
        self,
        user_id: int,
        title: str,
        expected_result: str,
        open_at: datetime,
    ) -> bool:
        """Обновить капсулу; возвращает False, если капсулы нет или она уже «запечатана» (час после последнего редактирования прошёл)."""
        now = datetime.now()
        cap = await self.get_time_capsule(user_id)
        if not cap:
            return False
        last = cap.get("last_edited_at") or cap.get("created_at")
        if isinstance(last, str):
            try:
                last = datetime.fromisoformat(last.replace("Z", "").strip())
            except Exception:
                last = now
        if last is None:
            last = now
        if (now - last).total_seconds() >= 3600:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE time_capsule
                   SET title = ?, expected_result = ?, open_at = ?, last_edited_at = ?
                   WHERE user_id = ?""",
                (title.strip(), expected_result.strip(), open_at, now, user_id),
            )
            await db.commit()
        return True

    async def delete_time_capsule(self, user_id: int) -> bool:
        """Удалить капсулу пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM time_capsule WHERE user_id = ?", (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def archive_time_capsule(self, user_id: int) -> bool:
        """Перенести открытую капсулу в историю и удалить из активных. Возвращает True, если была капсула."""
        cap = await self.get_time_capsule(user_id)
        if not cap:
            return False
        now = datetime.now()
        open_at = cap.get("open_at")
        created_at = cap.get("created_at") or now
        if hasattr(open_at, "isoformat"):
            open_at = open_at.isoformat() if open_at else None
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat() if created_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO time_capsule_history
                   (user_id, title, expected_result, open_at, created_at, viewed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    cap.get("title") or "",
                    cap.get("expected_result") or "",
                    str(open_at or ""),
                    str(created_at or ""),
                    now,
                ),
            )
            await db.execute("DELETE FROM time_capsule WHERE user_id = ?", (user_id,))
            await db.commit()
        return True

    async def get_time_capsule_history(self, user_id: int) -> List[Dict]:
        """Список капсул в истории (от новых к старым)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, user_id, title, expected_result, open_at, created_at, viewed_at, reflection
                   FROM time_capsule_history WHERE user_id = ? ORDER BY viewed_at DESC""",
                (user_id,),
            ) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    async def add_capsule_reflection(self, history_id: int, user_id: int, reflection: str) -> bool:
        """Добавить впечатления к капсуле в истории (только раз, если ещё пусто)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, reflection FROM time_capsule_history WHERE id = ? AND user_id = ?",
                (history_id, user_id),
            ) as c:
                row = await c.fetchone()
            if not row or (row[1] and str(row[1]).strip()):
                return False
            await db.execute(
                "UPDATE time_capsule_history SET reflection = ? WHERE id = ? AND user_id = ?",
                ((reflection or "").strip(), history_id, user_id),
            )
            await db.commit()
        return True
