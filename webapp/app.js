const tg = window.Telegram?.WebApp;

const state = {
  userId: null,
  baseUrl: "",
};

function initUser() {
  console.log('=== Инициализация пользователя ===');
  console.log('Telegram WebApp доступен:', !!tg);
  
  // Получаем userId из Telegram WebApp
  if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
    state.userId = tg.initDataUnsafe.user.id;
    console.log('✅ User ID из Telegram:', state.userId);
    console.log('Данные пользователя:', tg.initDataUnsafe.user);
  } else {
    // Fallback для тестирования (в продакшене это не должно происходить)
    console.warn("⚠️ Telegram WebApp не инициализирован, используем тестовый userId");
    if (tg) {
      console.warn('initDataUnsafe:', tg.initDataUnsafe);
    }
    state.userId = 1;
  }

  // Определяем базовый URL API
  const loc = window.location;
  state.baseUrl = `${loc.protocol}//${loc.host}`;
  
  console.log('📍 Текущий URL:', loc.href);
  console.log('📍 Base URL для API:', state.baseUrl);
  console.log('✅ Инициализация завершена');
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
    console.log(`📡 Запрос: ${options.method || 'GET'} ${url}`);
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
    
    console.log(`📥 Ответ: ${res.status} ${res.statusText}`);
    console.log(`📥 Content-Type: ${res.headers.get('content-type')}`);
    
    if (!res.ok) {
      const errorText = await res.text();
      console.error('❌ API Error:', res.status, res.statusText, errorText);
      throw new Error(`Request failed: ${res.status} ${res.statusText} - ${errorText}`);
    }
    
    // Проверяем, что ответ действительно JSON
    const contentType = res.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      const text = await res.text();
      console.error('❌ Ответ не является JSON. Content-Type:', contentType);
      console.error('❌ Тело ответа:', text.substring(0, 200));
      throw new Error(`Server returned non-JSON response. Content-Type: ${contentType}`);
    }
    
    // Пытаемся получить текст сначала для отладки
    const text = await res.text();
    console.log(`📄 Сырой ответ (первые 200 символов):`, text.substring(0, 200));
    
    if (!text || text.trim() === '') {
      console.warn('⚠️ Пустой ответ от сервера');
      return null;
    }
    
    // Парсим JSON
    let data;
    try {
      data = JSON.parse(text);
    } catch (parseError) {
      console.error('❌ Ошибка парсинга JSON:', parseError);
      console.error('❌ Проблемный текст:', text);
      throw new Error(`Invalid JSON response: ${parseError.message}`);
    }
    
    console.log(`✅ Успешно получены данные:`, data);
    return data;
  } catch (e) {
    if (e.name === 'TypeError' && e.message.includes('fetch')) {
      console.error('❌ Сетевая ошибка - сервер недоступен:', e.message);
      throw new Error('Failed to fetch - сервер недоступен. Проверьте, что веб-сервер запущен.');
    }
    if (e.name === 'SyntaxError') {
      console.error('❌ Ошибка синтаксиса JSON:', e.message);
      throw new Error(`JSON parse error: ${e.message}`);
    }
    console.error('❌ Fetch error:', e);
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
  
  if (!missions || missions.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет миссий. Добавьте первую миссию!</div>';
    return;
  }
  
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
  
  if (!goals || goals.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет целей. Добавьте первую цель!</div>';
    return;
  }
  
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
  
  if (!habits || habits.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет привычек. Добавьте первую привычку!</div>';
    return;
  }
  
  habits.forEach((h) => {
    const count = h.today_count || 0;
    const card = document.createElement("div");
    card.className = "card habit-card";
    card.innerHTML = `
      <div class="habit-card-content">
        <div class="habit-controls">
          <button class="habit-btn habit-btn-minus" data-habit-id="${h.id}" data-action="decrement">−</button>
          <div class="habit-counter">
            <span class="habit-count-number">${count}</span>
            <span class="habit-count-label">раз</span>
          </div>
          <button class="habit-btn habit-btn-plus" data-habit-id="${h.id}" data-action="increment">+</button>
        </div>
        <div class="habit-info">
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
        </div>
      </div>
    `;
    root.appendChild(card);
  });
  
  // Добавляем обработчики для кнопок + и -
  root.querySelectorAll('.habit-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const habitId = parseInt(btn.dataset.habitId);
      const action = btn.dataset.action;
      
      try {
        const endpoint = action === 'increment' 
          ? `${state.baseUrl}/api/habits/${habitId}/increment`
          : `${state.baseUrl}/api/habits/${habitId}/decrement`;
        
        const result = await fetchJSON(endpoint, { method: 'POST' });
        
        // Обновляем счетчик в UI
        const counter = btn.closest('.habit-card').querySelector('.habit-count-number');
        if (counter) {
          counter.textContent = result.count || 0;
        }
        
        // Обновляем все данные для синхронизации
        await loadAll();
      } catch (error) {
        console.error('Ошибка обновления счетчика:', error);
        if (tg) {
          tg.showAlert('Ошибка при обновлении счетчика');
        }
      }
    });
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
    const errorMsg = "Ошибка: не удалось определить пользователя. Убедитесь, что вы открыли приложение через Telegram.";
    console.error(errorMsg);
    if (tg) {
      tg.showAlert(errorMsg);
    }
    return;
  }
  
  console.log('=== Начало загрузки данных ===');
  console.log('User ID:', uid);
  console.log('Base URL:', base);
  
  try {
    // Проверяем доступность API
    const testUrl = `${base}/api/user/${uid}/missions`;
    console.log('Тестируем URL:', testUrl);
    
    const [missions, goals, habits, analytics] = await Promise.all([
      fetchJSON(`${base}/api/user/${uid}/missions`).catch(e => {
        console.error('❌ Ошибка загрузки миссий:', e.message, e);
        return [];
      }),
      fetchJSON(`${base}/api/user/${uid}/goals`).catch(e => {
        console.error('❌ Ошибка загрузки целей:', e.message, e);
        return [];
      }),
      fetchJSON(`${base}/api/user/${uid}/habits`).catch(e => {
        console.error('❌ Ошибка загрузки привычек:', e.message, e);
        return [];
      }),
      fetchJSON(`${base}/api/user/${uid}/analytics`).catch(e => {
        console.error('❌ Ошибка загрузки аналитики:', e.message, e);
        return {
          missions: { total: 0, completed: 0, avg_progress: 0 },
          goals: { total: 0, completed: 0, completion_rate: 0 },
          habits: { total: 0, total_completions: 0 }
        };
      }),
    ]);
    
    console.log('✅ Данные получены:');
    console.log('  Миссии:', missions?.length || 0);
    console.log('  Цели:', goals?.length || 0);
    console.log('  Привычки:', habits?.length || 0);
    console.log('  Аналитика:', analytics);
    
    // Обрабатываем пустые данные
    renderMissions(Array.isArray(missions) ? missions : []);
    renderGoals(Array.isArray(goals) ? goals : []);
    renderHabits(Array.isArray(habits) ? habits : []);
    renderAnalytics(analytics || {
      missions: { total: 0, completed: 0, avg_progress: 0 },
      goals: { total: 0, completed: 0, completion_rate: 0 },
      habits: { total: 0, total_completions: 0 }
    });
    
    console.log('✅ Данные успешно отображены');
  } catch (e) {
    console.error('❌ Критическая ошибка загрузки данных:', e);
    console.error('Stack:', e.stack);
    
    // Показываем пустые списки вместо ошибки
    renderMissions([]);
    renderGoals([]);
    renderHabits([]);
    renderAnalytics({
      missions: { total: 0, completed: 0, avg_progress: 0 },
      goals: { total: 0, completed: 0, completion_rate: 0 },
      habits: { total: 0, total_completions: 0 }
    });
    
    // Определяем тип ошибки
    let errorMsg = "Ошибка при загрузке данных.";
    if (e.message) {
      if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
        errorMsg = "Не удалось подключиться к серверу. Убедитесь, что веб-сервер запущен и доступен.";
      } else if (e.message.includes('404')) {
        errorMsg = "API endpoint не найден. Проверьте настройки сервера.";
      } else if (e.message.includes('500')) {
        errorMsg = "Ошибка на сервере. Проверьте логи веб-сервера.";
      } else {
        errorMsg = `Ошибка: ${e.message}`;
      }
    }
    
    console.error('Показываем ошибку пользователю:', errorMsg);
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

