import os
import warnings
import logging
from datetime import datetime, date

# Убираем предупреждение PTB про ConversationHandler (per_message / CallbackQueryHandler)
warnings.filterwarnings("ignore", message=".*per_message.*", category=UserWarning)
from typing import Dict, List, Optional
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from database import Database

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования (консоль + файл для круглосуточной работы и админки)
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "bot.log")
_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=_format, level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    _fh = logging.FileHandler(_log_file, encoding="utf-8")
    _fh.setFormatter(logging.Formatter(_format))
    logging.getLogger().addHandler(_fh)
except Exception:
    pass

# Состояния для ConversationHandler
(WAITING_TITLE, WAITING_DESCRIPTION, WAITING_DEADLINE, WAITING_PRIORITY,
 WAITING_MISSION_TITLE, WAITING_MISSION_DESCRIPTION, WAITING_SUBGOAL_TITLE,
 WAITING_HABIT_TITLE, WAITING_HABIT_DESCRIPTION) = range(9)

WEBAPP_URL = os.getenv("WEBAPP_URL")

# Инициализация базы данных
db = Database()


def _webapp_url() -> str:
    if not WEBAPP_URL:
        return ""
    return WEBAPP_URL.rstrip("/")


def get_webapp_inline_keyboard() -> Optional[InlineKeyboardMarkup]:
    """Inline-кнопка «Открыть приложение».

    Важно: при открытии Web App с inline-кнопки Telegram передаёт initData (user и т.д.).
    При открытии с reply-клавиатуры (кнопка над полем ввода) initData приходит пустым.
    """
    url = _webapp_url()
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Открыть приложение", web_app=WebAppInfo(url=url)),
    ]])


def remove_keyboard():
    """Убрать reply-клавиатуру (кнопки «Помощь» и «Открыть приложение» больше не показываются)."""
    return ReplyKeyboardRemove()


def get_mission_menu(mission_id: int) -> InlineKeyboardMarkup:
    """Меню для работы с миссией"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить подцель", callback_data=f"add_subgoal_{mission_id}")],
        [InlineKeyboardButton("📋 Подцели", callback_data=f"view_subgoals_{mission_id}")],
        [InlineKeyboardButton("✅ Завершить миссию", callback_data=f"complete_mission_{mission_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_mission_{mission_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="missions")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_goals_list_keyboard(goals: List[Dict], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура со списком целей"""
    keyboard = []
    start = page * per_page
    end = start + per_page
    page_goals = goals[start:end]
    
    for goal in page_goals:
        status = "✅" if goal.get('is_completed') else "⏳"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {goal['title'][:30]}",
                callback_data=f"goal_{goal['id']}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"goals_page_{page-1}"))
    if end < len(goals):
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"goals_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("➕ Добавить цель", callback_data="add_goal")])
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_missions_list_keyboard(missions: List[Dict], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура со списком миссий"""
    keyboard = []
    start = page * per_page
    end = start + per_page
    page_missions = missions[start:end]
    
    for mission in page_missions:
        status = "✅" if mission.get('is_completed') else "🎯"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {mission['title'][:30]}",
                callback_data=f"mission_{mission['id']}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"missions_page_{page-1}"))
    if end < len(missions):
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"missions_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("➕ Добавить миссию", callback_data="add_mission")])
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_habits_list_keyboard(habits: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком привычек"""
    keyboard = []
    
    for habit in habits:
        keyboard.append([
            InlineKeyboardButton(
                f"🔄 {habit['title'][:30]}",
                callback_data=f"habit_{habit['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить привычку", callback_data="add_habit")])
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_goal_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для работы с целью"""
    keyboard = [
        [InlineKeyboardButton("✅ Завершить", callback_data=f"complete_goal_{goal_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_goal_{goal_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="goals")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_habit_keyboard(habit_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для работы с привычкой"""
    keyboard = [
        [InlineKeyboardButton("✅ Выполнено сегодня", callback_data=f"toggle_habit_{habit_id}")],
        [InlineKeyboardButton("📊 Статистика", callback_data=f"habit_stats_{habit_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_habit_{habit_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="habits")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_subgoals_keyboard(mission_id: int, subgoals: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком подцелей"""
    keyboard = []
    
    for subgoal in subgoals:
        status = "✅" if subgoal.get('is_completed') else "⏳"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {subgoal['title'][:30]}",
                callback_data=f"subgoal_{subgoal['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить подцель", callback_data=f"add_subgoal_{mission_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад к миссии", callback_data=f"mission_{mission_id}")])
    
    return InlineKeyboardMarkup(keyboard)


def get_subgoal_keyboard(subgoal_id: int, mission_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для работы с подцелью"""
    keyboard = [
        [InlineKeyboardButton("✅ Завершить", callback_data=f"complete_subgoal_{subgoal_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_subgoal_{subgoal_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"view_subgoals_{mission_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await db.add_user(user.id, user.username)

    welcome_text = f"""
👋 Привет, {user.first_name}!

🎯 Добро пожаловать в бот для управления целями и привычками!

✨ Возможности:
• 🎯 Миссии — долгосрочные цели с подцелями
• ✅ Цели — краткосрочные и среднесрочные задачи
• 🔄 Привычки — ежедневные активности
• 📊 Аналитика — статистика и прогресс
"""
    await update.message.reply_text(welcome_text, reply_markup=remove_keyboard())

    # Inline-кнопка передаёт initData при открытии Web App; reply-кнопка «Открыть веб‑приложение» — часто нет.
    if _webapp_url():
        await update.message.reply_text(
            "👇 Чтобы войти под своим аккаунтом, откройте приложение по кнопке ниже:",
            reply_markup=get_webapp_inline_keyboard(),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 Помощь по использованию бота:

🎯 **Миссии** — долгосрочные цели с подцелями
   Пример: «Организация свадьбы» с подцелями:
   • Найти бюджет
   • Снять помещение
   • Выбрать меню

✅ **Цели** — задачи с дедлайнами и приоритетами

🔄 **Привычки** — ежедневные активности

📊 **Аналитика** — статистика прогресса

👇 Чтобы открыть веб‑приложение, нажмите кнопку ниже (так передаются данные для входа):
"""
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_webapp_inline_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "🎯 Миссии":
        await show_missions(update, context)
    elif text == "✅ Цели":
        await show_goals(update, context)
    elif text == "🔄 Привычки":
        await show_habits(update, context)
    elif text == "📊 Аналитика":
        await show_analytics(update, context)
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    else:
        kb = get_webapp_inline_keyboard()
        msg = "Откройте приложение по кнопке ниже:"
        await update.message.reply_text(msg, reply_markup=kb or remove_keyboard())


async def show_missions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список миссий"""
    user_id = update.effective_user.id
    missions = await db.get_missions(user_id)
    
    if not missions:
        text = "🎯 У вас пока нет миссий.\n\nНажмите кнопку ниже, чтобы добавить первую миссию!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить миссию", callback_data="add_mission"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"🎯 **Ваши миссии** ({len(missions)}):\n\n"
        for mission in missions[:5]:
            status = "✅" if mission.get('is_completed') else "⏳"
            text += f"{status} {mission['title']}\n"
        if len(missions) > 5:
            text += f"\n... и еще {len(missions) - 5}"
        keyboard = get_missions_list_keyboard(missions)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def show_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список целей"""
    user_id = update.effective_user.id
    goals = await db.get_goals(user_id)
    
    if not goals:
        text = "✅ У вас пока нет целей.\n\nНажмите кнопку ниже, чтобы добавить первую цель!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить цель", callback_data="add_goal"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"✅ **Ваши цели** ({len(goals)}):\n\n"
        for goal in goals[:5]:
            status = "✅" if goal.get('is_completed') else "⏳"
            priority_emoji = "🔥" if goal.get('priority', 1) == 3 else "⭐" if goal.get('priority', 1) == 2 else "📌"
            text += f"{status} {priority_emoji} {goal['title']}\n"
        if len(goals) > 5:
            text += f"\n... и еще {len(goals) - 5}"
        keyboard = get_goals_list_keyboard(goals)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def show_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список привычек"""
    user_id = update.effective_user.id
    habits = await db.get_habits(user_id)
    
    if not habits:
        text = "🔄 У вас пока нет привычек.\n\nНажмите кнопку ниже, чтобы добавить первую привычку!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить привычку", callback_data="add_habit"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"🔄 **Ваши привычки** ({len(habits)}):\n\n"
        for habit in habits:
            text += f"🔄 {habit['title']}\n"
        keyboard = get_habits_list_keyboard(habits)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def show_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать аналитику"""
    user_id = update.effective_user.id
    analytics = await db.get_user_analytics(user_id, days=30)
    
    text = f"""
📊 **Ваша аналитика за последние 30 дней:**

🎯 **Миссии:**
   Всего: {analytics['missions']['total']}
   Завершено: {analytics['missions']['completed']}
   Прогресс: {analytics['missions']['avg_progress']:.1f}%

✅ **Цели:**
   Всего: {analytics['goals']['total']}
   Завершено: {analytics['goals']['completed']}
   Выполнение: {analytics['goals']['completion_rate']:.1f}%

🔄 **Привычки:**
   Активных: {analytics['habits']['total']}
   Выполнений: {analytics['habits']['total_completions']}
    """
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
    ]])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # Главное меню
    if data == "main_menu":
        await query.edit_message_text(
            "🏠 Главное меню",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎯 Миссии", callback_data="missions"),
                InlineKeyboardButton("✅ Цели", callback_data="goals")
            ], [
                InlineKeyboardButton("🔄 Привычки", callback_data="habits"),
                InlineKeyboardButton("📊 Аналитика", callback_data="analytics")
            ]])
        )
    
    # Миссии
    elif data == "missions":
        await show_missions(update, context)
    elif data.startswith("mission_"):
        mission_id = int(data.split("_")[1])
        await show_mission_detail(update, context, mission_id)
    elif data.startswith("missions_page_"):
        page = int(data.split("_")[2])
        missions = await db.get_missions(user_id)
        text = f"🎯 **Ваши миссии** ({len(missions)}):\n\n"
        await query.edit_message_text(text, reply_markup=get_missions_list_keyboard(missions, page), parse_mode='Markdown')
    elif data == "add_mission":
        context.user_data['action'] = 'add_mission'
        await query.message.reply_text("📝 Введите название миссии:")
        return WAITING_MISSION_TITLE
    elif data.startswith("add_subgoal_"):
        mission_id = int(data.split("_")[2])
        context.user_data['mission_id'] = mission_id
        context.user_data['action'] = 'add_subgoal'
        await query.message.reply_text("📝 Введите название подцели:")
        return WAITING_SUBGOAL_TITLE
    elif data.startswith("view_subgoals_"):
        mission_id = int(data.split("_")[2])
        await show_subgoals(update, context, mission_id)
    elif data.startswith("complete_mission_"):
        mission_id = int(data.split("_")[2])
        await db.complete_mission(mission_id)
        await query.edit_message_text("✅ Миссия завершена!")
        await show_missions(update, context)
    elif data.startswith("delete_mission_"):
        mission_id = int(data.split("_")[2])
        await db.delete_mission(mission_id)
        await query.edit_message_text("🗑️ Миссия удалена!")
        await show_missions(update, context)
    
    # Подцели
    elif data.startswith("subgoal_"):
        subgoal_id = int(data.split("_")[1])
        await show_subgoal_detail(update, context, subgoal_id)
    elif data.startswith("complete_subgoal_"):
        subgoal_id = int(data.split("_")[2])
        subgoal = await db.get_subgoal(subgoal_id)
        if subgoal:
            mission_id = subgoal['mission_id']
            await db.complete_subgoal(subgoal_id)
            await query.edit_message_text("✅ Подцель завершена!")
            await show_subgoals(update, context, mission_id)
        else:
            await query.edit_message_text("❌ Подцель не найдена")
    elif data.startswith("delete_subgoal_"):
        subgoal_id = int(data.split("_")[2])
        subgoal = await db.get_subgoal(subgoal_id)
        if subgoal:
            mission_id = subgoal['mission_id']
            await db.delete_subgoal(subgoal_id)
            await query.edit_message_text("🗑️ Подцель удалена!")
            await show_subgoals(update, context, mission_id)
        else:
            await query.edit_message_text("❌ Подцель не найдена")
    
    # Цели
    elif data == "goals":
        await show_goals(update, context)
    elif data.startswith("goal_"):
        goal_id = int(data.split("_")[1])
        await show_goal_detail(update, context, goal_id)
    elif data.startswith("goals_page_"):
        page = int(data.split("_")[2])
        goals = await db.get_goals(user_id)
        text = f"✅ **Ваши цели** ({len(goals)}):\n\n"
        await query.edit_message_text(text, reply_markup=get_goals_list_keyboard(goals, page), parse_mode='Markdown')
    elif data == "add_goal":
        context.user_data['action'] = 'add_goal'
        await query.message.reply_text("📝 Введите название цели:")
        return WAITING_TITLE
    elif data.startswith("complete_goal_"):
        goal_id = int(data.split("_")[2])
        await db.complete_goal(goal_id)
        await query.edit_message_text("✅ Цель завершена!")
        await show_goals(update, context)
    elif data.startswith("delete_goal_"):
        goal_id = int(data.split("_")[2])
        await db.delete_goal(goal_id)
        await query.edit_message_text("🗑️ Цель удалена!")
        await show_goals(update, context)
    
    # Привычки
    elif data == "habits":
        await show_habits(update, context)
    elif data.startswith("habit_"):
        habit_id = int(data.split("_")[1])
        await show_habit_detail(update, context, habit_id)
    elif data == "add_habit":
        context.user_data['action'] = 'add_habit'
        await query.message.reply_text("📝 Введите название привычки:")
        return WAITING_HABIT_TITLE
    elif data.startswith("toggle_habit_"):
        habit_id = int(data.split("_")[2])
        today = date.today().isoformat()
        completed = await db.toggle_habit_record(habit_id, today)
        status = "✅ Выполнено!" if completed else "❌ Отменено"
        await query.edit_message_text(f"{status}\n\nПривычка отмечена на сегодня.")
        await show_habit_detail(update, context, habit_id)
    elif data.startswith("habit_stats_"):
        habit_id = int(data.split("_")[2])
        await show_habit_stats(update, context, habit_id)
    elif data.startswith("delete_habit_"):
        habit_id = int(data.split("_")[2])
        await db.delete_habit(habit_id)
        await query.edit_message_text("🗑️ Привычка удалена!")
        await show_habits(update, context)
    
    # Аналитика
    elif data == "analytics":
        await show_analytics(update, context)
    
    return ConversationHandler.END


async def show_mission_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, mission_id: int):
    """Показать детали миссии"""
    mission = await db.get_mission(mission_id)
    if not mission:
        await update.callback_query.edit_message_text("❌ Миссия не найдена")
        return
    
    subgoals = await db.get_subgoals(mission_id)
    completed_subgoals = sum(1 for sg in subgoals if sg.get('is_completed'))
    progress = (completed_subgoals / len(subgoals) * 100) if subgoals else 0
    
    status = "✅ Завершена" if mission.get('is_completed') else f"⏳ Прогресс: {progress:.0f}%"
    
    text = f"""
🎯 **{mission['title']}**

{mission.get('description', 'Без описания')}

📊 Статус: {status}
📋 Подцелей: {completed_subgoals}/{len(subgoals)}
📅 Создана: {mission['created_at'][:10]}
    """
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=get_mission_menu(mission_id),
        parse_mode='Markdown'
    )


async def show_subgoals(update: Update, context: ContextTypes.DEFAULT_TYPE, mission_id: int):
    """Показать подцели миссии"""
    subgoals = await db.get_subgoals(mission_id)
    mission = await db.get_mission(mission_id)
    
    if not mission:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Миссия не найдена")
        else:
            await update.message.reply_text("❌ Миссия не найдена")
        return
    
    if not subgoals:
        text = f"📋 У миссии '{mission['title']}' пока нет подцелей.\n\nДобавьте первую подцель!"
    else:
        completed = sum(1 for sg in subgoals if sg.get('is_completed'))
        text = f"📋 **Подцели миссии '{mission['title']}'** ({completed}/{len(subgoals)}):\n\n"
        for subgoal in subgoals:
            status = "✅" if subgoal.get('is_completed') else "⏳"
            text += f"{status} {subgoal['title']}\n"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=get_subgoals_keyboard(mission_id, subgoals),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=get_subgoals_keyboard(mission_id, subgoals),
            parse_mode='Markdown'
        )


async def show_subgoal_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, subgoal_id: int):
    """Показать детали подцели"""
    subgoal_data = await db.get_subgoal(subgoal_id)
    
    if not subgoal_data:
        await update.callback_query.edit_message_text("❌ Подцель не найдена")
        return
    
    mission_id = subgoal_data['mission_id']
    
    status = "✅ Завершена" if subgoal_data.get('is_completed') else "⏳ В процессе"
    
    text = f"""
📋 **{subgoal_data['title']}**

{subgoal_data.get('description', 'Без описания')}

📊 Статус: {status}
📅 Создана: {subgoal_data['created_at'][:10]}
    """
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=get_subgoal_keyboard(subgoal_id, mission_id),
        parse_mode='Markdown'
    )


async def show_goal_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, goal_id: int):
    """Показать детали цели"""
    goals = await db.get_goals(update.effective_user.id, include_completed=True)
    goal = next((g for g in goals if g['id'] == goal_id), None)
    
    if not goal:
        await update.callback_query.edit_message_text("❌ Цель не найдена")
        return
    
    status = "✅ Завершена" if goal.get('is_completed') else "⏳ В процессе"
    priority_emoji = "🔥 Высокий" if goal.get('priority', 1) == 3 else "⭐ Средний" if goal.get('priority', 1) == 2 else "📌 Низкий"
    deadline_text = f"\n⏰ Дедлайн: {goal['deadline']}" if goal.get('deadline') else ""
    
    text = f"""
✅ **{goal['title']}**

{goal.get('description', 'Без описания')}

📊 Статус: {status}
📌 Приоритет: {priority_emoji}{deadline_text}
📅 Создана: {goal['created_at'][:10]}
    """
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=get_goal_keyboard(goal_id),
        parse_mode='Markdown'
    )


async def show_habit_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    """Показать детали привычки"""
    habits = await db.get_habits(update.effective_user.id, active_only=False)
    habit = next((h for h in habits if h['id'] == habit_id), None)
    
    if not habit:
        await update.callback_query.edit_message_text("❌ Привычка не найдена")
        return
    
    today = date.today().isoformat()
    stats = await db.get_habit_stats(habit_id, days=7)
    
    text = f"""
🔄 **{habit['title']}**

{habit.get('description', 'Без описания')}

📊 За последние 7 дней:
   Выполнено: {stats['completed_days']}/{stats['total_days']}
   Процент: {stats['completion_rate']:.0f}%
    """
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=get_habit_keyboard(habit_id),
        parse_mode='Markdown'
    )


async def show_habit_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, habit_id: int):
    """Показать статистику привычки"""
    habits = await db.get_habits(update.effective_user.id, active_only=False)
    habit = next((h for h in habits if h['id'] == habit_id), None)
    
    if not habit:
        await update.callback_query.edit_message_text("❌ Привычка не найдена")
        return
    
    stats_7 = await db.get_habit_stats(habit_id, days=7)
    stats_30 = await db.get_habit_stats(habit_id, days=30)
    
    text = f"""
📊 **Статистика: {habit['title']}**

📅 За 7 дней:
   Выполнено: {stats_7['completed_days']}/{stats_7['total_days']}
   Процент: {stats_7['completion_rate']:.0f}%

📅 За 30 дней:
   Выполнено: {stats_30['completed_days']}/{stats_30['total_days']}
   Процент: {stats_30['completion_rate']:.0f}%
    """
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data=f"habit_{habit_id}")
    ]])
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# Обработчики для добавления элементов
async def handle_mission_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия миссии"""
    title = update.message.text
    context.user_data['mission_title'] = title
    await update.message.reply_text("📝 Введите описание миссии (или отправьте '-' чтобы пропустить):")
    return WAITING_MISSION_DESCRIPTION


async def handle_mission_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания миссии"""
    description = update.message.text
    if description == '-':
        description = ""
    
    user_id = update.effective_user.id
    title = context.user_data['mission_title']
    
    mission_id = await db.add_mission(user_id, title, description)
    await update.message.reply_text(f"✅ Миссия '{title}' добавлена!")
    
    # Показываем список миссий
    missions = await db.get_missions(user_id)
    if not missions:
        text = "🎯 У вас пока нет миссий.\n\nНажмите кнопку ниже, чтобы добавить первую миссию!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить миссию", callback_data="add_mission"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"🎯 **Ваши миссии** ({len(missions)}):\n\n"
        for mission in missions[:5]:
            status = "✅" if mission.get('is_completed') else "⏳"
            text += f"{status} {mission['title']}\n"
        if len(missions) > 5:
            text += f"\n... и еще {len(missions) - 5}"
        keyboard = get_missions_list_keyboard(missions)
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    return ConversationHandler.END


async def handle_subgoal_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия подцели"""
    title = update.message.text
    mission_id = context.user_data.get('mission_id')
    
    if mission_id:
        await db.add_subgoal(mission_id, title)
        await update.message.reply_text(f"✅ Подцель '{title}' добавлена!")
        # Создаем временный update для показа подцелей
        subgoals = await db.get_subgoals(mission_id)
        mission = await db.get_mission(mission_id)
        
        if not subgoals:
            text = f"📋 У миссии '{mission['title']}' пока нет подцелей.\n\nДобавьте первую подцель!"
        else:
            completed = sum(1 for sg in subgoals if sg.get('is_completed'))
            text = f"📋 **Подцели миссии '{mission['title']}'** ({completed}/{len(subgoals)}):\n\n"
            for subgoal in subgoals:
                status = "✅" if subgoal.get('is_completed') else "⏳"
                text += f"{status} {subgoal['title']}\n"
        
        await update.message.reply_text(
            text,
            reply_markup=get_subgoals_keyboard(mission_id, subgoals),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Ошибка: миссия не найдена")
    
    return ConversationHandler.END


async def handle_goal_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия цели"""
    title = update.message.text
    context.user_data['goal_title'] = title
    await update.message.reply_text("📝 Введите описание цели (или отправьте '-' чтобы пропустить):")
    return WAITING_DESCRIPTION


async def handle_goal_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания цели"""
    description = update.message.text
    if description == '-':
        description = ""
    
    context.user_data['goal_description'] = description
    await update.message.reply_text(
        "📅 Введите дедлайн в формате YYYY-MM-DD (или отправьте '-' чтобы пропустить):"
    )
    return WAITING_DEADLINE


async def handle_goal_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка дедлайна цели"""
    deadline = update.message.text
    if deadline == '-':
        deadline = None
    
    context.user_data['goal_deadline'] = deadline
    await update.message.reply_text("📌 Выберите приоритет:\n1 - Низкий\n2 - Средний\n3 - Высокий")
    return WAITING_PRIORITY


async def handle_goal_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка приоритета цели"""
    try:
        priority = int(update.message.text)
        if priority not in [1, 2, 3]:
            priority = 1
    except:
        priority = 1
    
    user_id = update.effective_user.id
    title = context.user_data['goal_title']
    description = context.user_data.get('goal_description', '')
    deadline = context.user_data.get('goal_deadline')
    
    await db.add_goal(user_id, title, description, deadline, priority)
    await update.message.reply_text(f"✅ Цель '{title}' добавлена!")
    
    # Показываем список целей
    goals = await db.get_goals(user_id)
    if not goals:
        text = "✅ У вас пока нет целей.\n\nНажмите кнопку ниже, чтобы добавить первую цель!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить цель", callback_data="add_goal"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"✅ **Ваши цели** ({len(goals)}):\n\n"
        for goal in goals[:5]:
            status = "✅" if goal.get('is_completed') else "⏳"
            priority_emoji = "🔥" if goal.get('priority', 1) == 3 else "⭐" if goal.get('priority', 1) == 2 else "📌"
            text += f"{status} {priority_emoji} {goal['title']}\n"
        if len(goals) > 5:
            text += f"\n... и еще {len(goals) - 5}"
        keyboard = get_goals_list_keyboard(goals)
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    return ConversationHandler.END


async def handle_habit_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия привычки"""
    title = update.message.text
    context.user_data['habit_title'] = title
    await update.message.reply_text("📝 Введите описание привычки (или отправьте '-' чтобы пропустить):")
    return WAITING_HABIT_DESCRIPTION


async def handle_habit_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания привычки"""
    description = update.message.text
    if description == '-':
        description = ""
    
    user_id = update.effective_user.id
    title = context.user_data['habit_title']
    
    await db.add_habit(user_id, title, description)
    await update.message.reply_text(f"✅ Привычка '{title}' добавлена!")
    
    # Показываем список привычек
    habits = await db.get_habits(user_id)
    if not habits:
        text = "🔄 У вас пока нет привычек.\n\nНажмите кнопку ниже, чтобы добавить первую привычку!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Добавить привычку", callback_data="add_habit"),
            InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")
        ]])
    else:
        text = f"🔄 **Ваши привычки** ({len(habits)}):\n\n"
        for habit in habits:
            text += f"🔄 {habit['title']}\n"
        keyboard = get_habits_list_keyboard(habits)
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("❌ Операция отменена.", reply_markup=remove_keyboard())
    return ConversationHandler.END


async def post_init(application: Application) -> None:
    """Инициализация базы данных при запуске приложения"""
    await db.init_db()
    logger.info("База данных инициализирована")


def main():
    """Главная функция запуска бота"""
    # Получение токена из переменных окружения
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN не найден в переменных окружения!")
        return
    
    # Создание приложения
    application = Application.builder().token(token).post_init(post_init).build()
    
    # ConversationHandler для добавления элементов (per_message=False по умолчанию — предупреждение подавлено выше)
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern="^add_mission$|^add_goal$|^add_habit$|^add_subgoal_"),
        ],
        states={
            WAITING_MISSION_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mission_title)],
            WAITING_MISSION_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mission_description)],
            WAITING_SUBGOAL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_subgoal_title)],
            WAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_title)],
            WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_description)],
            WAITING_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_deadline)],
            WAITING_PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_priority)],
            WAITING_HABIT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_habit_title)],
            WAITING_HABIT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_habit_description)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
