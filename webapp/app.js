const tg = window.Telegram?.WebApp;

const state = {
  userId: null,
  baseUrl: "",
  cache: { missions: [], goals: [], habits: [], analytics: null },
  seeded: false,
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

  if (tg && tg.MainButton) { try { tg.MainButton.hide(); } catch (_) {} }
  if (tg && tg.BackButton) { try { tg.BackButton.hide(); } catch (_) {} }
  // Определяем базовый URL API
  const loc = window.location;
  // Используем текущий origin (протокол + хост) для API
  state.baseUrl = `${loc.protocol}//${loc.host}`;
  
  // Если есть порт, включаем его
  if (loc.port && loc.port !== '80' && loc.port !== '443') {
    state.baseUrl = `${loc.protocol}//${loc.hostname}:${loc.port}`;
  }
  
  console.log('📍 Текущий URL:', loc.href);
  console.log('📍 Protocol:', loc.protocol);
  console.log('📍 Host:', loc.host);
  console.log('📍 Hostname:', loc.hostname);
  console.log('📍 Port:', loc.port);
  console.log('📍 Base URL для API:', state.baseUrl);
  console.log('✅ Инициализация завершена');
}

function $(selector) {
  return document.querySelector(selector);
}

function $all(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function switchTab(_tabName) {
  // Один список — вкладок нет, оставляем пустой вызов для совместимости
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
    const contentType = res.headers.get('content-type') || '';
    console.log(`📥 Content-Type: ${contentType}`);
    
    // Читаем текст только ОДИН раз
    const text = await res.text();
    console.log(`📄 Сырой ответ (первые 200 символов):`, text.substring(0, 200));
    
    if (!res.ok) {
      console.error('❌ API Error:', res.status, res.statusText, text.substring(0, 200));
      throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    
    // Проверяем, что ответ действительно JSON
    if (!contentType.includes('application/json')) {
      console.error('❌ Ответ не является JSON. Content-Type:', contentType);
      console.error('❌ Тело ответа:', text.substring(0, 200));
      throw new Error(`Server returned non-JSON response. Content-Type: ${contentType}`);
    }
    
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
      console.error('❌ Проблемный текст (полный):', text);
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
  if (tg && tg.MainButton) tg.MainButton.hide();
  var titleEl = $("#dialog-title");
  var titleInput = $("#dialog-title-input");
  var descInput = $("#dialog-description-input");
  var extraEl = $("#dialog-extra");
  var backdrop = $("#dialog-backdrop");
  if (titleEl) titleEl.textContent = title || "";
  if (titleInput) titleInput.value = "";
  if (descInput) descInput.value = "";
  if (extraEl) extraEl.innerHTML = extraHtml || "";
  if (backdrop) backdrop.classList.remove("hidden");

  function cancel(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (backdrop) backdrop.classList.add("hidden");
  }

  var cb = $("#dialog-cancel");
  var sb = $("#dialog-save");
  function doSave(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    var t = (titleInput && titleInput.value ? titleInput.value : "").trim();
    var d = (descInput && descInput.value ? descInput.value : "").trim();
    if (!t) {
      if (tg) tg.showAlert("Введите название");
      return;
    }
    if (sb) { sb.disabled = true; sb.textContent = "Сохранение…"; }
    var done = function() {
      if (backdrop) backdrop.classList.add("hidden");
      if (sb) { sb.disabled = false; sb.textContent = "Сохранить"; }
    };
    var fail = function(err) {
      console.error("Ошибка сохранения:", err);
      if (tg) tg.showAlert("Не удалось сохранить. Проверьте подключение.");
      if (sb) { sb.disabled = false; sb.textContent = "Сохранить"; }
    };
    try {
      var p = onSave({ title: t, description: d });
      (p && typeof p.then === "function" ? p : Promise.resolve()).then(done).catch(fail);
    } catch (e) {
      fail(e);
    }
  }
  if (cb) cb.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); cancel(ev); };
  if (sb) sb.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); doSave(ev); };
  if (backdrop) {
    backdrop.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); if (ev.target === backdrop) cancel(ev); };
  }
  var dialogEl = backdrop && backdrop.querySelector(".dialog");
  if (dialogEl) dialogEl.onclick = function(ev) { ev.stopPropagation(); };
}

// --- render ---

function wrapSwipeDelete(node, type, id) {
  const wrap = document.createElement("div");
  wrap.className = "swipe-row";
  wrap.dataset.type = type;
  wrap.dataset.id = String(id);
  wrap.innerHTML = `
    <div class="swipe-row-content">${node.outerHTML}</div>
    <div class="swipe-row-actions"><button type="button" class="swipe-delete-btn">Удалить</button></div>
  `;
  return wrap;
}

function setupSwipeDelete(container) {
  if (!container) return;
  const rows = container.querySelectorAll(".swipe-row");
  rows.forEach((row) => {
    const type = row.dataset.type;
    const id = row.dataset.id;
    const content = row.querySelector(".swipe-row-content");
    const btn = row.querySelector(".swipe-delete-btn");
    let startX = 0, startLeft = 0;
    const apply = (x) => {
      const w = 72;
      const v = Math.max(-w, Math.min(0, x));
      if (content) content.style.transform = `translateX(${v}px)`;
      row.classList.toggle("swiped", v <= -w / 2);
    };
    const onStart = (e) => {
      if (e.target.closest(".habit-btn, .swipe-delete-btn")) return;
      startX = e.touches ? e.touches[0].clientX : e.clientX;
      startLeft = content && content.style.transform ? parseFloat(content.style.transform) || 0 : 0;
    };
    const onMove = (e) => {
      const x = (e.touches ? e.touches[0].clientX : e.clientX) - startX;
      apply(startLeft + x);
    };
    const onEnd = () => {
      const tx = content ? parseFloat(content.style.transform) || 0 : 0;
      row.classList.toggle("swiped", tx <= -36);
      if (tx > -36) apply(0);
      else apply(-72);
    };
    row.addEventListener("touchstart", onStart, { passive: true });
    row.addEventListener("touchmove", onMove, { passive: true });
    row.addEventListener("touchend", onEnd);
    row.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      onStart(e);
      const mm = (ev) => { if (ev.buttons !== 1) return; onMove(ev); };
      const mu = () => { onEnd(); document.removeEventListener("mousemove", mm); document.removeEventListener("mouseup", mu); };
      document.addEventListener("mousemove", mm);
      document.addEventListener("mouseup", mu);
    });
    if (btn) {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        try {
          const url = `${state.baseUrl}/api/${type === "mission" ? "missions" : type === "goal" ? "goals" : "habits"}/${id}`;
          await fetch(url, { method: "DELETE" });
          await loadAll();
        } catch (err) {
          console.error(err);
          if (tg) tg.showAlert("Не удалось удалить");
        }
      });
    }
  });
}

function renderMissions(missions) {
  const root = $("#missions-list");
  root.innerHTML = "";
  
  if (!missions || missions.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет миссий.<br>Используйте кнопку <strong>«➕ Добавить миссию»</strong> выше или загрузите примеры: <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
    return;
  }
  
  missions.forEach((m) => {
    const done = m.is_completed ? "Завершена" : "В процессе";
    const card = document.createElement("div");
    card.className = "card";
    const title = escapeHtml(m.title || '');
    const description = escapeHtml(m.description || "Без описания");
    const createdAt = m.created_at ? String(m.created_at).slice(0, 10) : '';
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">${title}</div>
        <span class="badge">${done}</span>
      </div>
      <div class="card-description">${description}</div>
      <div class="card-meta"><span>Создана: ${createdAt}</span></div>
    `;
    root.appendChild(wrapSwipeDelete(card, "mission", m.id));
  });
  setupSwipeDelete(root);
}

function renderGoals(goals) {
  const root = $("#goals-list");
  root.innerHTML = "";
  
  if (!goals || goals.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет целей.<br>Кнопка <strong>«➕ Добавить цель»</strong> выше или <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
    return;
  }
  
  goals.forEach((g) => {
    const done = g.is_completed ? "Завершена" : "В процессе";
    const priority =
      g.priority === 3 ? "🔥 Высокий" : g.priority === 2 ? "⭐ Средний" : "📌 Низкий";
    const card = document.createElement("div");
    card.className = "card";
    const title = escapeHtml(g.title || '');
    const description = escapeHtml(g.description || "Без описания");
    const deadline = g.deadline ? "Дедлайн: " + String(g.deadline).slice(0, 10) : "";
    card.innerHTML = `
      <div class="card-header">
        <div class="card-title">${title}</div>
        <span class="badge">${priority}</span>
      </div>
      <div class="card-description">${description}</div>
      <div class="card-meta"><span>${done}</span><span>${deadline}</span></div>
    `;
    root.appendChild(wrapSwipeDelete(card, "goal", g.id));
  });
  setupSwipeDelete(root);
}

function renderHabits(habits) {
  const root = $("#habits-list");
  root.innerHTML = "";
  
  if (!habits || habits.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет привычек (Пить воду, Зарядка и др.).<br>Кнопка <strong>«➕ Добавить привычку»</strong> выше или <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
    return;
  }
  
  habits.forEach((h) => {
    const count = h.today_count || 0;
    const habitId = parseInt(h.id) || 0;
    const card = document.createElement("div");
    card.className = "card habit-card habitica-row";
    const title = escapeHtml(h.title || '');
    card.innerHTML = `
      <div class="habit-card-content">
        <button type="button" class="habit-btn habit-btn-plus" data-habit-id="${habitId}" data-action="increment">+</button>
        <div class="habit-name">${title}</div>
        <div class="habit-count-wrap ${count ? '' : 'hide'}">
          <span class="habit-count-number">${count}</span>
          <span class="habit-count-unit">раз</span>
        </div>
        <button type="button" class="habit-btn habit-btn-minus" data-habit-id="${habitId}" data-action="decrement">−</button>
      </div>
    `;
    root.appendChild(wrapSwipeDelete(card, "habit", h.id));
  });
  setupSwipeDelete(root);
  
  root.querySelectorAll('.habit-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const habitId = parseInt(btn.dataset.habitId);
      const action = btn.dataset.action;
      try {
        const endpoint = action === 'increment' 
          ? `${state.baseUrl}/api/habits/${habitId}/increment`
          : `${state.baseUrl}/api/habits/${habitId}/decrement`;
        const result = await fetchJSON(endpoint, { method: 'POST' });
        const row = btn.closest('.habit-card');
        const numEl = row && row.querySelector('.habit-count-number');
        const wrapEl = row && row.querySelector('.habit-count-wrap');
        const newCount = result.count || 0;
        if (numEl) numEl.textContent = newCount;
        if (wrapEl) {
          wrapEl.classList.toggle('hide', !newCount);
        }
        await loadAll();
      } catch (err) {
        console.error('Ошибка счётчика:', err);
        if (tg) tg.showAlert('Ошибка при обновлении');
      }
    });
  });
}

function renderAnalytics(data) {
  const root = $("#analytics-view");
  if (!root) return;
  
  const missionsTotal = parseInt(data?.missions?.total || 0);
  const missionsCompleted = parseInt(data?.missions?.completed || 0);
  const missionsProgress = parseFloat(data?.missions?.avg_progress || 0);
  const goalsTotal = parseInt(data?.goals?.total || 0);
  const goalsCompleted = parseInt(data?.goals?.completed || 0);
  const goalsRate = parseFloat(data?.goals?.completion_rate || 0);
  const habitsTotal = parseInt(data?.habits?.total || 0);
  const habitsCompletions = parseInt(data?.habits?.total_completions || 0);
  const streak = parseInt(data?.habits?.streak || 0);
  const chart = data?.habit_chart || { labels: [], values: [] };
  const labels = Array.isArray(chart.labels) ? chart.labels : [];
  const values = Array.isArray(chart.values) ? chart.values : [];
  const maxVal = values.length ? Math.max(1, ...values) : 1;
  
  let chartHtml = "";
  if (labels.length) {
    chartHtml = `
      <div class="analytics-chart-wrap">
        <div class="analytics-chart-title">Выполнения привычек по дням</div>
        <div class="analytics-chart">
          ${labels.map((l, i) => {
            const v = values[i] || 0;
            const h = Math.round((v / maxVal) * 100);
            const short = (l + "").slice(-5);
            return `<div class="analytics-chart-bar-wrap"><div class="analytics-chart-bar" style="height:${h}%"></div><span class="analytics-chart-label">${escapeHtml(short)}</span></div>`;
          }).join("")}
        </div>
      </div>
    `;
  }
  
  root.innerHTML = `
    ${streak > 0 ? `<div class="streak-badge">🔥 Серия: ${streak} дн.</div>` : ""}
    ${chartHtml}
    <div class="metric-group">
      <h4>Миссии</h4>
      <div class="metric-row"><span>Всего</span><span>${missionsTotal}</span></div>
      <div class="metric-row"><span>Завершено</span><span>${missionsCompleted}</span></div>
      <div class="metric-row"><span>Средний прогресс</span><span>${missionsProgress.toFixed(1)}%</span></div>
    </div>
    <div class="metric-group">
      <h4>Цели</h4>
      <div class="metric-row"><span>Всего</span><span>${goalsTotal}</span></div>
      <div class="metric-row"><span>Завершено</span><span>${goalsCompleted}</span></div>
      <div class="metric-row"><span>Выполнение</span><span>${goalsRate.toFixed(1)}%</span></div>
    </div>
    <div class="metric-group">
      <h4>Привычки</h4>
      <div class="metric-row"><span>Активных</span><span>${habitsTotal}</span></div>
      <div class="metric-row"><span>Выполнений (30 дн.)</span><span>${habitsCompletions}</span></div>
      <div class="metric-row"><span>Серия</span><span>${streak} дн.</span></div>
    </div>
  `;
}

function renderProfile() {
  const root = $("#profile-view");
  if (!root) return;
  const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  const firstName = u ? escapeHtml(u.first_name || "") : "";
  const lastName = u ? escapeHtml(u.last_name || "") : "";
  const username = u && u.username ? "@" + escapeHtml(u.username) : "";
  const name = [firstName, lastName].filter(Boolean).join(" ") || "Пользователь";
  const missions = state.cache.missions || [];
  const goals = state.cache.goals || [];
  const habits = state.cache.habits || [];
  const a = state.cache.analytics || {};
  const missionsTotal = parseInt(a?.missions?.total || 0) || missions.length;
  const goalsTotal = parseInt(a?.goals?.total || 0) || goals.length;
  const habitsTotal = parseInt(a?.habits?.total || 0) || habits.length;
  root.innerHTML = `
    <div class="profile-avatar">${firstName ? firstName.charAt(0).toUpperCase() : "?"}</div>
    <div class="profile-name">${name}</div>
    ${username ? `<div class="profile-username">${username}</div>` : ""}
    <div class="profile-stats">
      <div class="profile-stat-row"><span>Миссий</span><span>${missionsTotal}</span></div>
      <div class="profile-stat-row"><span>Целей</span><span>${goalsTotal}</span></div>
      <div class="profile-stat-row"><span>Привычек</span><span>${habitsTotal}</span></div>
    </div>
    <button type="button" class="primary-btn seed-btn js-seed-examples">Загрузить примеры миссий, целей и привычек</button>
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
  console.log('URL проверки API:', base + '/api/health');
  console.log('URL миссий:', base + '/api/user/' + uid + '/missions');
  
  // Проверка API: при недоступности всё равно рисуем интерфейс, потом покажем предупреждение
  try {
    const healthRes = await fetch(base + '/api/health', { method: 'GET' });
    const healthOk = healthRes.ok && (healthRes.headers.get('content-type') || '').includes('application/json');
    console.log('🔍 /api/health:', healthRes.status, healthOk ? 'OK' : 'FAIL');
    if (!healthOk) {
      const text = await healthRes.text();
      console.error('🔍 Ответ /api/health не JSON:', text.substring(0, 150));
      renderMissions([]);
      renderGoals([]);
      renderHabits([]);
      renderAnalytics({ missions: { total: 0, completed: 0, avg_progress: 0 }, goals: { total: 0, completed: 0, completion_rate: 0 }, habits: { total: 0, total_completions: 0, streak: 0 }, habit_chart: { labels: [], values: [] } });
      if (tg) tg.showAlert('Сервер API недоступен. Проверьте Nginx (прокси /api/ на порт 8000).');
      return;
    }
  } catch (healthErr) {
    console.error('🔍 /api/health недоступен:', healthErr);
    renderMissions([]);
    renderGoals([]);
    renderHabits([]);
    renderAnalytics({ missions: { total: 0, completed: 0, avg_progress: 0 }, goals: { total: 0, completed: 0, completion_rate: 0 }, habits: { total: 0, total_completions: 0, streak: 0 }, habit_chart: { labels: [], values: [] } });
    if (tg) tg.showAlert('Не удалось подключиться к API. Проверьте Nginx и доступность ' + base + '/api/');
    return;
  }
  
  try {
    if (!state.seeded) {
      state.seeded = true;
      try {
        await fetch(base + "/api/user/" + uid + "/seed", { method: "POST" });
      } catch (_) {}
    }
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
          habits: { total: 0, total_completions: 0, streak: 0 },
          habit_chart: { labels: [], values: [] }
        };
      }),
    ]);
    
    console.log('✅ Данные получены:');
    console.log('  Миссии:', missions?.length || 0);
    console.log('  Цели:', goals?.length || 0);
    console.log('  Привычки:', habits?.length || 0);
    console.log('  Аналитика:', analytics);
    
    const missionsList = Array.isArray(missions) ? missions : [];
    const goalsList = Array.isArray(goals) ? goals : [];
    const habitsList = Array.isArray(habits) ? habits : [];
    const analyticsData = analytics || {
      missions: { total: 0, completed: 0, avg_progress: 0 },
      goals: { total: 0, completed: 0, completion_rate: 0 },
      habits: { total: 0, total_completions: 0, streak: 0 },
      habit_chart: { labels: [], values: [] }
    };
    
    state.cache.missions = missionsList;
    state.cache.goals = goalsList;
    state.cache.habits = habitsList;
    state.cache.analytics = analyticsData;
    
    // Сразу показываем интерфейс (пустой или с данными)
    renderMissions(missionsList);
    renderGoals(goalsList);
    renderHabits(habitsList);
    renderAnalytics(analyticsData);
    renderProfile();
    
    console.log('✅ Данные успешно отображены');
  } catch (e) {
    console.error('❌ Критическая ошибка загрузки данных:', e);
    console.error('Stack:', e.stack);
    
    // Показываем пустые списки вместо ошибки
    state.cache.missions = [];
    state.cache.goals = [];
    state.cache.habits = [];
    state.cache.analytics = {
      missions: { total: 0, completed: 0, avg_progress: 0 },
      goals: { total: 0, completed: 0, completion_rate: 0 },
      habits: { total: 0, total_completions: 0, streak: 0 },
      habit_chart: { labels: [], values: [] }
    };
    renderMissions([]);
    renderGoals([]);
    renderHabits([]);
    renderAnalytics(state.cache.analytics);
    renderProfile();
    
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
  var tabEls = $all(".tab");
  if (tabEls.length) {
    tabEls.forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
  }

  document.body.addEventListener("click", async (e) => {
    if (!e.target.closest(".js-seed-examples")) return;
    e.preventDefault();
    try {
      await fetchJSON(`${state.baseUrl}/api/user/${state.userId}/seed`, { method: "POST" });
      await loadAll();
      if (tg) tg.showAlert("Примеры загружены");
    } catch (err) {
      if (tg) tg.showAlert("Ошибка загрузки примеров");
    }
  });

  const addMissionBtn = $("#add-mission-btn");
  if (addMissionBtn) addMissionBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
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

  const addGoalBtn = $("#add-goal-btn");
  if (addGoalBtn) addGoalBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
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

  const addHabitBtn = $("#add-habit-btn");
  if (addHabitBtn) addHabitBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
    openDialog({
      title: "Новая привычка",
      onSave: async function( data ) {
        await fetchJSON(state.baseUrl + "/api/habits", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: state.userId, title: data.title, description: data.description || "" }),
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

