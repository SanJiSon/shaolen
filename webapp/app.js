const tg = window.Telegram?.WebApp;

const state = {
  userId: null,
  baseUrl: "",
  cache: { missions: [], goals: [], habits: [], analytics: null, profile: null },
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
    console.warn("⚠️ Telegram WebApp не инициализирован или пользователь не определён");
    if (tg) console.warn("initDataUnsafe:", tg.initDataUnsafe);
    state.userId = null;
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

function switchTab(tabName) {
  var panels = $all(".tab-panel");
  var tabs = $all(".tab");
  panels.forEach(function(p) {
    p.classList.toggle("active", p.id === "panel-" + tabName);
  });
  tabs.forEach(function(t) {
    t.classList.toggle("active", t.dataset.tab === tabName);
    t.setAttribute("aria-selected", t.dataset.tab === tabName ? "true" : "false");
  });
}

async function fetchJSON(url, options = {}) {
  try {
    var headers = { 'Content-Type': 'application/json' };
    if (options.headers) Object.assign(headers, options.headers);
    if ((url.indexOf("/api/user/") !== -1 || url.indexOf("/api/me") !== -1) && tg && tg.initData) {
      headers["X-Telegram-Init-Data"] = tg.initData;
    }
    console.log(`📡 Запрос: ${options.method || 'GET'} ${url}`);
    const res = await fetch(url, {
      ...options,
      headers: headers
    });
    
    console.log(`📥 Ответ: ${res.status} ${res.statusText}`);
    const contentType = res.headers.get('content-type') || '';
    console.log(`📥 Content-Type: ${contentType}`);
    
    // Читаем текст только ОДИН раз
    const text = await res.text();
    console.log(`📄 Сырой ответ (первые 200 символов):`, text.substring(0, 200));
    
    if (!res.ok) {
      var err = new Error("Request failed: " + res.status + " " + res.statusText);
      err.status = res.status;
      err.body = text;
      throw err;
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

function openDialog({ title, extraHtml = "", onSave, initialValues }) {
  if (tg && tg.MainButton) tg.MainButton.hide();
  var titleEl = $("#dialog-title");
  var titleInput = $("#dialog-title-input");
  var descInput = $("#dialog-description-input");
  var extraEl = $("#dialog-extra");
  var backdrop = $("#dialog-backdrop");
  var form = $("#dialog-form");
  var iv = initialValues || {};
  if (titleEl) titleEl.textContent = title || "";
  if (titleInput) titleInput.value = (iv.title != null ? iv.title : "") || "";
  if (descInput) descInput.value = (iv.description != null ? iv.description : "") || "";
  if (extraEl) extraEl.innerHTML = extraHtml || "";
  if (backdrop) backdrop.classList.remove("hidden");
  if (extraEl && iv.deadline != null) {
    setTimeout(function() {
      var de = document.getElementById("deadline-input");
      if (de) de.value = iv.deadline ? String(iv.deadline).slice(0, 10) : "";
    }, 0);
  }
  if (extraEl && iv.priority != null) {
    setTimeout(function() {
      var pe = document.getElementById("priority-input");
      if (pe) pe.value = String(iv.priority);
    }, 0);
  }

  function cancel(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (backdrop) backdrop.classList.add("hidden");
    if (form) form.onsubmit = null;
  }

  var cb = $("#dialog-cancel");
  var sb = $("#dialog-save");
  function doSave(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (!onSave) {
      console.error("openDialog: onSave не передан");
      if (tg) tg.showAlert("Ошибка: действие сохранения не задано.");
      return;
    }
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
      if (form) form.onsubmit = null;
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
  if (form) {
    form.onsubmit = function(ev) { ev.preventDefault(); ev.stopPropagation(); doSave(ev); return false; };
  }
  if (sb) sb.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); doSave(ev); };
  if (backdrop) {
    backdrop.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); if (ev.target === backdrop) cancel(ev); };
  }
  var dialogEl = backdrop && backdrop.querySelector(".dialog");
  if (dialogEl) dialogEl.onclick = function(ev) { ev.stopPropagation(); };
  setTimeout(function() { if (titleInput) titleInput.focus(); }, 50);
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
  const w = 72;
  rows.forEach((row) => {
    const type = row.dataset.type;
    const id = row.dataset.id;
    const content = row.querySelector(".swipe-row-content");
    const btn = row.querySelector(".swipe-delete-btn");
    let startX = 0, startY = 0, startLeft = 0, tracking = false;
    const apply = (x) => {
      const v = Math.max(-w, Math.min(0, x));
      if (content) content.style.transform = "translateX(" + v + "px)";
      row.classList.toggle("swiped", v <= -w / 2);
    };
    const onStart = (e) => {
      if (e.target.closest(".habit-btn, .swipe-delete-btn")) return;
      startX = e.touches ? e.touches[0].clientX : e.clientX;
      startY = e.touches ? e.touches[0].clientY : e.clientY;
      startLeft = content && content.style.transform ? parseFloat(String(content.style.transform).replace(/[^-\d.]/g, "")) || 0 : 0;
      tracking = true;
    };
    const onMove = (e) => {
      if (!tracking) return;
      var x = (e.touches ? e.touches[0].clientX : e.clientX) - startX;
      var y = (e.touches ? e.touches[0].clientY : e.clientY) - startY;
      if (e.cancelable && (Math.abs(x) > 8 || Math.abs(y) > 8)) {
        if (Math.abs(x) > Math.abs(y) * 1.2) e.preventDefault();
      }
      apply(startLeft + x);
    };
    const onEnd = () => {
      tracking = false;
      var tx = content ? (parseFloat(String(content.style.transform).replace(/[^-\d.]/g, "")) || 0) : 0;
      row.classList.toggle("swiped", tx <= -36);
      if (tx > -36) apply(0);
      else apply(-72);
    };
    row.addEventListener("touchstart", onStart, { passive: true });
    row.addEventListener("touchmove", onMove, { passive: false });
    row.addEventListener("touchend", onEnd, { passive: true });
    row.addEventListener("touchcancel", onEnd, { passive: true });
    row.addEventListener("mousedown", function(e) {
      if (e.button !== 0) return;
      onStart(e);
      var mm = function(ev) { if (ev.buttons !== 1) return; onMove(ev); };
      var mu = function() { onEnd(); document.removeEventListener("mousemove", mm); document.removeEventListener("mouseup", mu); };
      document.addEventListener("mousemove", mm);
      document.addEventListener("mouseup", mu);
    });
    if (btn) {
      btn.addEventListener("click", async function(e) {
        e.preventDefault();
        e.stopPropagation();
        try {
          var url = state.baseUrl + "/api/" + (type === "mission" ? "missions" : type === "goal" ? "goals" : "habits") + "/" + id;
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
    root.innerHTML = '<div class="empty-state">У вас пока нет миссий.<br>Нажмите <strong>«+ Добавить»</strong> или <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
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
    card.dataset.editId = String(m.id);
  card.dataset.editType = "mission";
  root.appendChild(wrapSwipeDelete(card, "mission", m.id));
  });
  setupSwipeDelete(root);
}

function renderGoals(goals) {
  const root = $("#goals-list");
  root.innerHTML = "";
  
  if (!goals || goals.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет целей.<br>Нажмите <strong>«+ Добавить»</strong> или <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
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
    root.innerHTML = '<div class="empty-state">У вас пока нет привычек.<br>Нажмите <strong>«+ Добавить»</strong> или <button type="button" class="primary-btn js-seed-examples">Загрузить примеры</button></div>';
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
    card.dataset.editId = String(h.id);
    card.dataset.editType = "habit";
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
  var p = state.cache.profile || {};
  var displayName = (p.display_name || "").trim();
  var firstName = (p.first_name || "").trim();
  var lastName = (p.last_name || "").trim();
  var name = displayName || [firstName, lastName].filter(Boolean).join(" ").trim() || "Пользователь";
  var initial = (name && name.charAt(0)) ? name.charAt(0).toUpperCase() : "?";
  var username = (p.username && String(p.username).trim()) ? "@" + escapeHtml(String(p.username).trim()) : "";
  const missions = state.cache.missions || [];
  const goals = state.cache.goals || [];
  const habits = state.cache.habits || [];
  const a = state.cache.analytics || {};
  const missionsTotal = parseInt(a?.missions?.total || 0) || missions.length;
  const goalsTotal = parseInt(a?.goals?.total || 0) || goals.length;
  const habitsTotal = parseInt(a?.habits?.total || 0) || habits.length;
  root.innerHTML = `
    <div class="profile-avatar">${escapeHtml(initial)}</div>
    <div class="profile-name">${escapeHtml(name)}</div>
    ${username ? `<div class="profile-username">${username}</div>` : ""}
    <div class="profile-edit-name">
      <label class="profile-edit-label">Как к вам обращаться?</label>
      <input type="text" id="profile-display-name-input" class="input" placeholder="${escapeHtml(name)}" value="${escapeHtml(displayName)}" maxlength="64" />
      <button type="button" class="primary-btn profile-save-name-btn">Сохранить имя</button>
    </div>
    <div class="profile-stats">
      <div class="profile-stat-row"><span>Миссий</span><span>${missionsTotal}</span></div>
      <div class="profile-stat-row"><span>Целей</span><span>${goalsTotal}</span></div>
      <div class="profile-stat-row"><span>Привычек</span><span>${habitsTotal}</span></div>
    </div>
    <button type="button" class="primary-btn seed-btn js-seed-examples">Загрузить примеры миссий, целей и привычек</button>
  `;
  var saveBtn = root.querySelector(".profile-save-name-btn");
  var inputEl = root.querySelector("#profile-display-name-input");
  if (saveBtn && inputEl) {
    saveBtn.addEventListener("click", async function() {
      var val = (inputEl.value || "").trim();
      try {
        await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/profile", {
          method: "PUT",
          body: JSON.stringify({ display_name: val })
        });
        state.cache.profile = (state.cache.profile || {});
        state.cache.profile.display_name = val;
        renderProfile();
        if (tg) tg.showAlert("Имя сохранено");
      } catch (err) {
        if (tg) tg.showAlert("Не удалось сохранить");
      }
    });
  }
}

function getInitData() {
  if (!tg) return "";
  if (tg.initData && typeof tg.initData === "string" && tg.initData.length > 10) return tg.initData;
  return "";
}

async function ensureUserId() {
  // 1) уже задан из initDataUnsafe
  if (state.userId != null) return true;
  if (!tg) return false;
  var initData = getInitData();
  if (!initData) {
    // На части телефонов initData появляется с задержкой — даём 2 попытки с паузой
    await new Promise(function(r) { setTimeout(r, 350); });
    initData = getInitData();
  }
  if (!initData) {
    await new Promise(function(r) { setTimeout(r, 500); });
    initData = getInitData();
  }
  if (!initData) return false;
  try {
    var me = await fetchJSON(state.baseUrl + "/api/me", {
      headers: { "X-Telegram-Init-Data": initData },
    });
    if (me && (me.user_id != null || me.user_id !== undefined)) {
      state.userId = me.user_id;
      console.log("✅ User ID получен через /api/me:", state.userId);
      return true;
    }
  } catch (e) {
    console.warn("Не удалось получить пользователя через /api/me:", e);
  }
  return false;
}

async function loadAll() {
  var base = state.baseUrl;

  // На части устройств initDataUnsafe.user пустой, но приложение открыто из Telegram — получаем userId через /api/me
  await ensureUserId();

  var uid = state.userId;
  if (!uid) {
    console.error("userId не установлен. initData есть:", !!getInitData(), "tg:", !!tg);
    var errorMsg =
      "Ошибка: не удалось определить пользователя. Убедитесь, что вы открыли приложение через Telegram.";
    console.error(errorMsg);
    if (tg) tg.showAlert(errorMsg);
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
      try {
        await fetchJSON(base + "/api/user/" + uid + "/seed", { method: "POST" });
        console.log("Seed выполнен успешно");
      } catch (e) {
        console.warn("Seed запрос не удался:", e);
      }
      state.seeded = true;
    }
    var profileFallback = {
      first_name: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.first_name) || "",
      last_name: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.last_name) || "",
      username: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.username) || "",
      display_name: ""
    };
    const [missions, goals, habits, analytics, profile] = await Promise.all([
      fetchJSON(base + "/api/user/" + uid + "/missions").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Миссии:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/goals").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Цели:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/habits").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Привычки:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/analytics").catch(e => {
        if (e && e.status === 401) throw e;
        console.error("❌ Аналитика:", e.message);
        return { missions: { total: 0, completed: 0, avg_progress: 0 }, goals: { total: 0, completed: 0, completion_rate: 0 }, habits: { total: 0, total_completions: 0, streak: 0 }, habit_chart: { labels: [], values: [] } };
      }),
      fetchJSON(base + "/api/user/" + uid + "/profile").catch(e => { if (e && e.status === 401) throw e; return profileFallback; })
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
    state.cache.profile = (profile && typeof profile === "object") ? profile : profileFallback;

    renderMissions(missionsList);
    renderGoals(goalsList);
    renderHabits(habitsList);
    renderAnalytics(analyticsData);
    renderProfile();
    
    console.log('✅ Данные успешно отображены');
  } catch (e) {
    if (e && e.status === 401) {
      var msg = "Откройте приложение из Telegram. Данные пользователя не прошли проверку.";
      if (tg) tg.showAlert(msg); else alert(msg);
      return;
    }
    if (e && e.status === 403) {
      var msg2 = "Доступ запрещён для этого пользователя.";
      if (tg) tg.showAlert(msg2); else alert(msg2);
      return;
    }
    console.error("❌ Критическая ошибка загрузки данных:", e);

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
  tabEls.forEach(function(btn) {
    btn.addEventListener("click", function() { switchTab(btn.dataset.tab); });
  });

  document.body.addEventListener("click", async function(e) {
    if (e.target.closest(".js-seed-examples")) {
    e.preventDefault();
    try {
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/seed", { method: "POST" });
      await loadAll();
      if (tg) tg.showAlert("Примеры загружены");
    } catch (err) {
      if (tg) tg.showAlert("Ошибка загрузки примеров");
    }
    return;
    }
    var content = e.target.closest(".swipe-row-content");
    if (content && !e.target.closest(".habit-btn, .swipe-delete-btn")) {
      var row = e.target.closest(".swipe-row");
      if (row) {
        var type = row.dataset.type, id = row.dataset.id;
        if (type && id) {
          var item = null;
          if (type === "mission") item = (state.cache.missions || []).find(function(m) { return String(m.id) === String(id); });
          else if (type === "goal") item = (state.cache.goals || []).find(function(g) { return String(g.id) === String(id); });
          else if (type === "habit") item = (state.cache.habits || []).find(function(h) { return String(h.id) === String(id); });
          if (item) {
            e.preventDefault();
            e.stopPropagation();
            if (tg && tg.MainButton) tg.MainButton.hide();
            if (type === "mission") {
              openDialog({
                title: "Редактировать миссию",
                initialValues: { title: item.title || "", description: item.description || "" },
                onSave: async function(p) {
                  await fetchJSON(state.baseUrl + "/api/missions/" + id, { method: "PUT", body: JSON.stringify({ title: p.title, description: p.description }) });
                  await loadAll();
                }
              });
            } else if (type === "goal") {
              var goalExtra = '<input id="deadline-input" class="input" type="date" /><select id="priority-input" class="input"><option value="1">Низкий</option><option value="2">Средний</option><option value="3">Высокий</option></select>';
              openDialog({
                title: "Редактировать цель",
                extraHtml: goalExtra,
                initialValues: { title: item.title || "", description: item.description || "", deadline: item.deadline || "", priority: item.priority != null ? item.priority : 1 },
                onSave: async function(p) {
                  var dl = document.getElementById("deadline-input");
                  var pr = document.getElementById("priority-input");
                  await fetchJSON(state.baseUrl + "/api/goals/" + id, {
                    method: "PUT",
                    body: JSON.stringify({ title: p.title, description: p.description, deadline: (dl && dl.value) || null, priority: pr ? parseInt(pr.value, 10) : 1 })
                  });
                  await loadAll();
                }
              });
            } else if (type === "habit") {
              openDialog({
                title: "Редактировать привычку",
                initialValues: { title: item.title || "", description: item.description || "" },
                onSave: async function(p) {
                  await fetchJSON(state.baseUrl + "/api/habits/" + id, { method: "PUT", body: JSON.stringify({ title: p.title, description: p.description }) });
                  await loadAll();
                }
              });
            }
          }
        }
      }
    }
  });

  var addMissionBtn = $("#add-mission-btn");
  if (addMissionBtn) addMissionBtn.addEventListener("click", async function(e) {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
    if (!state.userId) await ensureUserId();
    if (!state.userId && tg) { tg.showAlert("Не удалось определить пользователя. Откройте приложение из Telegram."); return; }
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
  if (addGoalBtn) addGoalBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
    if (!state.userId) await ensureUserId();
    if (!state.userId && tg) { tg.showAlert("Не удалось определить пользователя. Откройте приложение из Telegram."); return; }
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
  if (addHabitBtn) addHabitBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (tg && tg.MainButton) tg.MainButton.hide();
    if (!state.userId) await ensureUserId();
    if (!state.userId && tg) { tg.showAlert("Не удалось определить пользователя. Откройте приложение из Telegram."); return; }
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

document.addEventListener("DOMContentLoaded", async function() {
  console.log("WebApp v4 — вкладки, свайп без сдвига, редактирование, новая палитра");
  initUser();
  bindEvents();
  await loadAll();
});

