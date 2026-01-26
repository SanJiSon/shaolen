const tg = window.Telegram?.WebApp;

const state = {
  userId: null,
  baseUrl: "",
};

function initUser() {
  // Получаем userId из Telegram WebApp
  if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
    state.userId = tg.initDataUnsafe.user.id;
  } else {
    // Fallback для тестирования (в продакшене это не должно происходить)
    console.warn("Telegram WebApp не инициализирован, используем тестовый userId");
    state.userId = 1;
  }

  // Определяем базовый URL API
  const loc = window.location;
  // Убираем /webapp или /index.html из пути, оставляем только домен
  const pathParts = loc.pathname.split('/').filter(p => p && p !== 'webapp' && p !== 'index.html');
  state.baseUrl = `${loc.protocol}//${loc.host}`;
  
  console.log('Initialized with userId:', state.userId, 'baseUrl:', state.baseUrl);
}

function $(selector) {
  return document.querySelector(selector);
}

function $all(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function switchTab(tabName) {
  $all(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  $all(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
}

async function fetchJSON(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const errorText = await res.text();
      console.error('API Error:', res.status, errorText);
      throw new Error(`Request failed: ${res.status} ${errorText}`);
    }
    return res.json();
  } catch (e) {
    console.error('Fetch error:', e);
    throw e;
  }
}

function openDialog({ title, extraHtml = "", onSave }) {
  $("#dialog-title").textContent = title;
  $("#dialog-title-input").value = "";
  $("#dialog-description-input").value = "";
  $("#dialog-extra").innerHTML = extraHtml;

  const backdrop = $("#dialog-backdrop");
  backdrop.classList.remove("hidden");

  const cancel = () => {
    backdrop.classList.add("hidden");
  };

  const save = async () => {
    const t = $("#dialog-title-input").value.trim();
    const d = $("#dialog-description-input").value.trim();
    if (!t) return;
    await onSave({ title: t, description: d });
    backdrop.classList.add("hidden");
  };

  $("#dialog-cancel").onclick = cancel;
  $("#dialog-save").onclick = save;
}

// --- render ---

function renderMissions(missions) {
  const root = $("#missions-list");
  root.innerHTML = "";
  missions.forEach((m) => {
    const done = m.is_completed ? "Завершена" : "В процессе";
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">${m.title}</div>
        <span class="badge">${done}</span>
      </div>
      <div class="card-description">
        ${m.description || "Без описания"}
      </div>
      <div class="card-meta">
        <span>Создана: ${String(m.created_at).slice(0, 10)}</span>
      </div>
    `;
    root.appendChild(card);
  });
}

function renderGoals(goals) {
  const root = $("#goals-list");
  root.innerHTML = "";
  goals.forEach((g) => {
    const done = g.is_completed ? "Завершена" : "В процессе";
    const priority =
      g.priority === 3 ? "🔥 Высокий" : g.priority === 2 ? "⭐ Средний" : "📌 Низкий";
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">${g.title}</div>
        <span class="badge">${priority}</span>
      </div>
      <div class="card-description">
        ${g.description || "Без описания"}
      </div>
      <div class="card-meta">
        <span>${done}</span>
        <span>${g.deadline ? "Дедлайн: " + g.deadline.slice(0, 10) : ""}</span>
      </div>
    `;
    root.appendChild(card);
  });
}

function renderHabits(habits) {
  const root = $("#habits-list");
  root.innerHTML = "";
  habits.forEach((h) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">${h.title}</div>
        <span class="badge">${h.is_active ? "Активна" : "Отключена"}</span>
      </div>
      <div class="card-description">
        ${h.description || "Без описания"}
      </div>
      <div class="card-meta">
        <span>Создана: ${String(h.created_at).slice(0, 10)}</span>
      </div>
    `;
    root.appendChild(card);
  });
}

function renderAnalytics(data) {
  const root = $("#analytics-view");
  root.innerHTML = `
    <div class="metric-group">
      <h4>Миссии</h4>
      <div class="metric-row"><span>Всего</span><span>${data.missions.total}</span></div>
      <div class="metric-row"><span>Завершено</span><span>${data.missions.completed}</span></div>
      <div class="metric-row"><span>Средний прогресс</span><span>${data.missions.avg_progress.toFixed(
        1
      )}%</span></div>
    </div>
    <div class="metric-group">
      <h4>Цели</h4>
      <div class="metric-row"><span>Всего</span><span>${data.goals.total}</span></div>
      <div class="metric-row"><span>Завершено</span><span>${data.goals.completed}</span></div>
      <div class="metric-row"><span>Выполнение</span><span>${data.goals.completion_rate.toFixed(
        1
      )}%</span></div>
    </div>
    <div class="metric-group">
      <h4>Привычки</h4>
      <div class="metric-row"><span>Активных</span><span>${data.habits.total}</span></div>
      <div class="metric-row"><span>Выполнений</span><span>${
        data.habits.total_completions
      }</span></div>
    </div>
  `;
}

async function loadAll() {
  const uid = state.userId;
  const base = state.baseUrl;
  
  if (!uid) {
    console.error('userId не установлен');
    if (tg) tg.showAlert("Ошибка: не удалось определить пользователя");
    return;
  }
  
  try {
    // Показываем индикатор загрузки
    const loadingMsg = tg ? tg.showAlert("Загрузка данных...") : null;
    
    const [missions, goals, habits, analytics] = await Promise.all([
      fetchJSON(`${base}/api/user/${uid}/missions`),
      fetchJSON(`${base}/api/user/${uid}/goals`),
      fetchJSON(`${base}/api/user/${uid}/habits`),
      fetchJSON(`${base}/api/user/${uid}/analytics`),
    ]);
    
    renderMissions(missions);
    renderGoals(goals);
    renderHabits(habits);
    renderAnalytics(analytics);
    
    if (tg && loadingMsg) {
      tg.close(); // Закрываем alert если он был показан
    }
  } catch (e) {
    console.error('Ошибка загрузки данных:', e);
    const errorMsg = e.message || "Ошибка при загрузке данных";
    if (tg) {
      tg.showAlert(errorMsg);
    } else {
      alert(errorMsg);
    }
  }
}

function bindEvents() {
  $all(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  $("#add-mission-btn").addEventListener("click", () => {
    openDialog({
      title: "Новая миссия",
      onSave: async ({ title, description }) => {
        await fetchJSON(`${state.baseUrl}/api/missions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: state.userId, title, description }),
        });
        await loadAll();
      },
    });
  });

  $("#add-goal-btn").addEventListener("click", () => {
    const extra =
      '<input id="deadline-input" class="input" type="date" /><select id="priority-input" class="input"><option value="1">📌 Низкий приоритет</option><option value="2">⭐ Средний приоритет</option><option value="3">🔥 Высокий приоритет</option></select>';
    openDialog({
      title: "Новая цель",
      extraHtml: extra,
      onSave: async ({ title, description }) => {
        const deadline = document.getElementById("deadline-input").value || null;
        const priority = parseInt(document.getElementById("priority-input").value, 10);
        await fetchJSON(`${state.baseUrl}/api/goals`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: state.userId,
            title,
            description,
            deadline,
            priority,
          }),
        });
        await loadAll();
      },
    });
  });

  $("#add-habit-btn").addEventListener("click", () => {
    openDialog({
      title: "Новая привычка",
      onSave: async ({ title, description }) => {
        await fetchJSON(`${state.baseUrl}/api/habits`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: state.userId, title, description }),
        });
        await loadAll();
      },
    });
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initUser();
  bindEvents();
  await loadAll();
});

