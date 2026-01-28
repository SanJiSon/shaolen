const tg = window.Telegram?.WebApp;

const state = {
  userId: null,
  baseUrl: "",
  cache: { missions: [], goals: [], habits: [], analytics: null, profile: null, subgoalsByMission: {} },
  analyticsPeriod: "month",
  shaolenMessages: [],
  shaolenUsage: { used: 0, limit: 50 },
  shaolenHistory: [],
  shaolenFullscreen: false,
  shaolenImageData: null,
  shaolenVoiceData: null,
  shaolenRecording: false,
  shaolenRecordingChunks: [],
  capsule: null,
  capsuleCanEdit: false,
  capsuleView: "main",
  capsuleHistory: [],
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
      if (sb) { sb.disabled = false; sb.textContent = "Сохранить"; }
      if (err && (err.message === "validate" || err.name === "validate")) {
        /* сообщение уже показано в onSave */
      } else {
        if (tg) tg.showAlert("Не удалось сохранить. Проверьте подключение.");
      }
    };
    var restoreBtn = function() {
      if (sb) { sb.disabled = false; sb.textContent = "Сохранить"; }
    };
    try {
      var p = onSave({ title: t, description: d });
      var promise = (p && typeof p.then === "function" ? p : Promise.resolve());
      promise.then(done, fail).finally(restoreBtn);
    } catch (e) {
      fail(e);
      restoreBtn();
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
  var root = $("#missions-list");
  root.innerHTML = "";

  if (!missions || missions.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет миссий.<br>Нажмите <strong>«+ Добавить»</strong></div>';
    return;
  }

  var subgoalsByMission = state.cache.subgoalsByMission || {};
  missions.forEach(function(m) {
    var done = m.is_completed ? "Завершена" : "В процессе";
    var card = document.createElement("div");
    card.className = "card card-mission";
    var title = escapeHtml(m.title || "");
    var description = escapeHtml(m.description || "Без описания");
    var createdAt = m.created_at ? String(m.created_at).slice(0, 10) : "";
    var deadline = m.deadline ? String(m.deadline).slice(0, 10) : "";
    var subs = subgoalsByMission[m.id] || [];
    var subsHtml = subs.map(function(s) {
      var doneClass = s.is_completed ? " subgoal-done" : "";
      return "<div class=\"subgoal-row" + doneClass + "\"><label class=\"subgoal-cb-wrap\"><input type=\"checkbox\" class=\"subgoal-done-cb\" data-id=\"" + s.id + "\" " + (s.is_completed ? "checked" : "") + " /><span>" + escapeHtml(s.title || "") + "</span></label></div>";
    }).join("");
    card.innerHTML =
      "<div class=\"card-header card-header-with-cb\">" +
      "<label class=\"mission-done-cb-wrap\"><input type=\"checkbox\" class=\"mission-done-cb\" data-id=\"" + m.id + "\" " + (m.is_completed ? "checked" : "") + " /></label>" +
      "<div class=\"card-title\">" + title + "</div>" +
      "<span class=\"badge\">" + done + "</span>" +
      "</div>" +
      "<div class=\"card-description\">" + description + "</div>" +
      "<div class=\"card-meta\"><span>Создана: " + createdAt + "</span>" + (deadline ? "<span>Окончание: " + deadline + "</span>" : "") + "</div>" +
      (subs.length || true ? "<div class=\"card-subgoals\"><div class=\"subgoals-title\">Подцели</div><div class=\"subgoals-list\">" + subsHtml + "</div><button type=\"button\" class=\"link-btn add-subgoal-btn\" data-mission-id=\"" + m.id + "\">＋ Подцель</button></div>" : "") +
      "";
    card.dataset.editId = String(m.id);
    card.dataset.editType = "mission";
    root.appendChild(wrapSwipeDelete(card, "mission", m.id));
  });
  setupSwipeDelete(root);
}

function renderGoals(goals) {
  var root = $("#goals-list");
  root.innerHTML = "";

  if (!goals || goals.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет целей.<br>Нажмите <strong>«+ Добавить»</strong></div>';
    return;
  }

  goals.forEach(function(g) {
    var done = g.is_completed ? "Завершена" : "В процессе";
    var priority = g.priority === 3 ? "🔥 Высокий" : g.priority === 2 ? "⭐ Средний" : "📌 Низкий";
    var card = document.createElement("div");
    card.className = "card card-goal";
    var title = escapeHtml(g.title || "");
    var description = escapeHtml(g.description || "Без описания");
    var dl = g.deadline ? "Дедлайн: " + String(g.deadline).slice(0, 10) : "";
    card.innerHTML =
      "<div class=\"card-header card-header-with-cb\">" +
      "<label class=\"goal-done-cb-wrap\"><input type=\"checkbox\" class=\"goal-done-cb\" data-id=\"" + g.id + "\" " + (g.is_completed ? "checked" : "") + " /></label>" +
      "<div class=\"card-title\">" + title + "</div>" +
      "<span class=\"badge\">" + priority + "</span>" +
      "</div>" +
      "<div class=\"card-description\">" + description + "</div>" +
      "<div class=\"card-meta\"><span>" + done + "</span><span>" + dl + "</span></div>" +
      "";
    root.appendChild(wrapSwipeDelete(card, "goal", g.id));
  });
  setupSwipeDelete(root);
}

function renderHabits(habits) {
  const root = $("#habits-list");
  root.innerHTML = "";
  
  if (!habits || habits.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет привычек.<br>Нажмите <strong>«+ Добавить»</strong></div>';
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
  var root = $("#analytics-view");
  if (!root) return;

  var period = data && data.period ? data.period : (state.analyticsPeriod || "month");
  state.analyticsPeriod = period;
  var missionsTotal = parseInt(data?.missions?.total || 0);
  var missionsCompleted = parseInt(data?.missions?.completed || 0);
  var missionsProgress = parseFloat(data?.missions?.avg_progress || 0);
  var goalsTotal = parseInt(data?.goals?.total || 0);
  var goalsCompleted = parseInt(data?.goals?.completed || 0);
  var goalsRate = parseFloat(data?.goals?.completion_rate || 0);
  var habitsTotal = parseInt(data?.habits?.total || 0);
  var habitsCompletions = parseInt(data?.habits?.total_completions || 0);
  var streak = parseInt(data?.habits?.streak || 0);
  var chart = data?.habit_chart || { labels: [], values: [] };
  var labels = Array.isArray(chart.labels) ? chart.labels : [];
  var values = Array.isArray(chart.values) ? chart.values : [];
  var maxVal = values.length ? Math.max(1, Math.max.apply(null, values)) : 1;

  var periodTabsHtml = "<div class=\"analytics-period-tabs\">" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "week" ? " active" : "") + "\" data-period=\"week\">Неделя</button>" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "month" ? " active" : "") + "\" data-period=\"month\">Месяц</button>" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "all" ? " active" : "") + "\" data-period=\"all\">Всё</button>" +
    "</div>";
  var chartHtml = "<div class=\"analytics-chart-wrap\"><div class=\"analytics-chart-title\">Выполнения привычек по дням</div>" + periodTabsHtml;
  if (labels.length) {
    chartHtml += "<div class=\"analytics-chart\">" +
      labels.map(function(l, i) {
        var v = values[i] || 0;
        var h = Math.round((v / maxVal) * 100);
        var short = (l + "").slice(-5);
        return "<div class=\"analytics-chart-bar-wrap\"><div class=\"analytics-chart-bar\" style=\"height:" + h + "%\"></div><span class=\"analytics-chart-label\">" + escapeHtml(short) + "</span></div>";
      }).join("") +
      "</div>";
  }
  chartHtml += "</div>";

  root.innerHTML =
    (streak > 0 ? "<div class=\"streak-badge\">🔥 Серия: " + streak + " дн.</div>" : "") +
    chartHtml +
    "<div class=\"metric-group\"><h4>Миссии</h4>" +
    "<div class=\"metric-row\"><span>Всего</span><span>" + missionsTotal + "</span></div>" +
    "<div class=\"metric-row\"><span>Завершено</span><span>" + missionsCompleted + "</span></div>" +
    "<div class=\"metric-row\"><span>Средний прогресс</span><span>" + missionsProgress.toFixed(1) + "%</span></div></div>" +
    "<div class=\"metric-group\"><h4>Цели</h4>" +
    "<div class=\"metric-row\"><span>Всего</span><span>" + goalsTotal + "</span></div>" +
    "<div class=\"metric-row\"><span>Завершено</span><span>" + goalsCompleted + "</span></div>" +
    "<div class=\"metric-row\"><span>Выполнение</span><span>" + goalsRate.toFixed(1) + "%</span></div></div>" +
    "<div class=\"metric-group\"><h4>Привычки</h4>" +
    "<div class=\"metric-row\"><span>Активных</span><span>" + habitsTotal + "</span></div>" +
    "<div class=\"metric-row\"><span>Выполнений</span><span>" + habitsCompletions + "</span></div>" +
    "<div class=\"metric-row\"><span>Серия</span><span>" + streak + " дн.</span></div></div>";
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

function parseOpenAt(s) {
  if (!s) return null;
  try {
    var str = String(s).trim();
    if (!str) return null;
    // Бэкенд отдаёт время в UTC с суффиксом "Z". Если суффикса нет — считаем UTC, иначе парсер может принять как local.
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(str) && str.indexOf("Z") === -1 && !/[-+]\d{2}:?\d{2}$/.test(str)) {
      str = str.replace(/(\.\d+)?$/, "$1Z");
    }
    var d = new Date(str);
    return isNaN(d.getTime()) ? null : d;
  } catch (e) { return null; }
}

function capsuleCountdown(openAt) {
  var end = parseOpenAt(openAt);
  if (!end) return { days: 0, hours: 0, minutes: 0, totalMs: 0, opened: true };
  var now = new Date();
  var totalMs = end.getTime() - now.getTime();
  if (totalMs <= 0) return { days: 0, hours: 0, minutes: 0, totalMs: 0, opened: true };
  var days = Math.floor(totalMs / (24 * 60 * 60 * 1000));
  var restMs = totalMs % (24 * 60 * 60 * 1000);
  var hours = Math.floor(restMs / (60 * 60 * 1000));
  var minutes = Math.floor((restMs % (60 * 60 * 1000)) / (60 * 1000));
  return { days: days, hours: hours, minutes: minutes, totalMs: totalMs, opened: false };
}

function formatCapsuleCountdown(cd) {
  if (cd.opened) return "";
  var totalMs = cd.totalMs;
  var h = 60 * 60 * 1000;
  var d = 24 * h;
  if (totalMs >= d) return cd.days + " дн. " + cd.hours + " ч.";
  if (totalMs >= h) return cd.hours + " ч. " + cd.minutes + " мин.";
  return cd.minutes + " мин.";
}

function runCapsuleConfetti() {
  var canvas = document.getElementById("capsule-confetti-canvas");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var w = canvas.width = window.innerWidth;
  var h = canvas.height = window.innerHeight;
  var particles = [];
  var colors = ["#7c3aed", "#22c55e", "#f43f5e", "#fbbf24", "#38bdf8"];
  for (var i = 0; i < 80; i++) {
    particles.push({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 8, vy: -4 - Math.random() * 6,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: 4 + Math.random() * 6
    });
  }
  function tick() {
    ctx.fillStyle = "rgba(12,14,20,0.15)";
    ctx.fillRect(0, 0, w, h);
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      p.x += p.vx; p.y += p.vy; p.vy += 0.2;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  var count = 0;
  var id = setInterval(function() {
    tick();
    if (++count > 120) clearInterval(id);
  }, 33);
}

function renderCapsuleHistoryList() {
  var list = state.capsuleHistory || [];
  var html = "<div class=\"capsule-history-header\"><button type=\"button\" class=\"link-btn capsule-back-btn\">← К капсуле</button></div>";
  if (list.length === 0) {
    html += "<div class=\"capsule-intro\">Пока нет открытых капсул. Откройте капсулу — она появится здесь, и вы сможете добавить впечатления.</div>";
  } else {
    list.forEach(function(h) {
      var viewed = (h.viewed_at || "").slice(0, 16).replace("T", " ");
      var ref = h.reflection;
      var refBlock = ref
        ? "<div class=\"capsule-history-reflection\">" + escapeHtml(ref) + "</div>"
        : "<button type=\"button\" class=\"link-btn capsule-add-reflection-btn\" data-id=\"" + h.id + "\">+ Добавить впечатления</button><div class=\"capsule-reflection-form hidden\" id=\"ref-form-" + h.id + "\"><textarea class=\"input capsule-reflection-input\" id=\"ref-text-" + h.id + "\" placeholder=\"Что получилось на самом деле? Чем довольны?\" rows=\"3\"></textarea><button type=\"button\" class=\"primary-btn capsule-save-reflection-btn\" data-id=\"" + h.id + "\">Сохранить</button></div>";
      html += "<div class=\"capsule-history-card\" data-id=\"" + h.id + "\">" +
        "<div class=\"capsule-history-title\">" + escapeHtml(h.title || "") + "</div>" +
        "<div class=\"capsule-history-meta\">Открыта: " + escapeHtml(viewed) + "</div>" +
        "<div class=\"capsule-history-expected\"><strong>Ожидали:</strong> " + escapeHtml(h.expected_result || "") + "</div>" +
        "<div class=\"capsule-history-ref-block\">" + refBlock + "</div></div>";
    });
  }
  return html;
}

function renderCapsule() {
  var root = $("#capsule-view");
  if (!root) return;

  if (state.capsuleView === "history") {
    root.innerHTML = "<div class=\"capsule-history-root\">" + renderCapsuleHistoryList() + "</div>";
    root.querySelectorAll(".capsule-back-btn").forEach(function(b) {
      b.addEventListener("click", function() { state.capsuleView = "main"; renderCapsule(); });
    });
    root.querySelectorAll(".capsule-add-reflection-btn").forEach(function(b) {
      b.addEventListener("click", function() {
        var id = b.dataset.id;
        var form = document.getElementById("ref-form-" + id);
        if (form) form.classList.remove("hidden");
      });
    });
    root.querySelectorAll(".capsule-save-reflection-btn").forEach(function(b) {
      b.addEventListener("click", async function() {
        var id = parseInt(b.dataset.id, 10);
        var textEl = document.getElementById("ref-text-" + id);
        var text = textEl ? textEl.value : "";
        try {
          await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule/history/" + id + "/reflection", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reflection: text })
          });
          var idx = (state.capsuleHistory || []).findIndex(function(h) { return h.id === id; });
          if (idx >= 0 && state.capsuleHistory) state.capsuleHistory[idx].reflection = text;
          if (tg) tg.showAlert("Впечатления сохранены");
          renderCapsule();
        } catch (e) {
          if (tg) tg.showAlert("Не удалось сохранить");
        }
      });
    });
    return;
  }

  var cap = state.capsule;
  var canEdit = state.capsuleCanEdit;
  var topBar = "<div class=\"capsule-top-bar\"><button type=\"button\" class=\"link-btn capsule-history-link\">📜 История капсул</button></div>";

  if (!cap) {
    root.innerHTML = topBar +
      "<div class=\"capsule-intro\">" +
      "<p><strong>Капсула времени</strong> — это послание себе в будущее.</p>" +
      "<p>Опишите, чего вы ждёте от себя через несколько дней или недель привычек и целей. Когда капсула откроется, вы сможете сравнить ожидания и реальность — и увидеть, как далеко продвинулись.</p>" +
      "<p>Пример: заголовок «Через 30 дней привычек я надеюсь выглядеть стройнее», описание — конкретный образ результата.</p>" +
      "<p>Создать можно только одну капсулу. После открытия её можно перенести в историю и создать новую. В течение часа после создания активную капсулу можно редактировать или удалить.</p>" +
      "</div>" +
      "<button type=\"button\" id=\"capsule-create-btn\" class=\"primary-btn\">Создать капсулу</button>";
    root.querySelectorAll(".capsule-history-link").forEach(function(b) {
      b.addEventListener("click", showCapsuleHistory);
    });
    var btn = document.getElementById("capsule-create-btn");
    if (btn) btn.addEventListener("click", openCapsuleCreateDialog);
    return;
  }

  var openAt = cap.open_at;
  var cd = capsuleCountdown(openAt);

  if (cd.opened) {
    root.innerHTML = topBar +
      "<div class=\"capsule-countdown capsule-opened\">Капсула открыта!</div>" +
      "<button type=\"button\" id=\"capsule-reveal-btn\" class=\"primary-btn\">Открыть</button>";
    root.querySelectorAll(".capsule-history-link").forEach(function(b) {
      b.addEventListener("click", showCapsuleHistory);
    });
    var revBtn = document.getElementById("capsule-reveal-btn");
    if (revBtn) revBtn.addEventListener("click", function() {
      var overlay = $("#capsule-open-overlay");
      var body = $("#capsule-open-body");
      if (body) body.innerHTML = "<div class=\"capsule-reveal-title\">" + escapeHtml(cap.title || "") + "</div><div class=\"capsule-reveal-result\">" + escapeHtml(cap.expected_result || "") + "</div>";
      if (overlay) overlay.classList.remove("hidden");
      runCapsuleConfetti();
    });
    return;
  }

  var countdownText = "До открытия: " + formatCapsuleCountdown(cd);
  var actionsHtml = "";
  if (canEdit) actionsHtml = "<div class=\"capsule-actions\"><button type=\"button\" class=\"secondary-btn capsule-edit-btn\">Редактировать</button> <button type=\"button\" class=\"secondary-btn capsule-delete-btn\">Удалить</button></div>";

  root.innerHTML = topBar +
    "<div class=\"capsule-countdown\">" + escapeHtml(countdownText) + "</div>" +
    "<div class=\"capsule-title-preview\">" + escapeHtml(cap.title || "") + "</div>" +
    actionsHtml;

  root.querySelectorAll(".capsule-history-link").forEach(function(b) {
    b.addEventListener("click", showCapsuleHistory);
  });
  root.querySelectorAll(".capsule-edit-btn").forEach(function(b) {
    b.addEventListener("click", function() { openCapsuleEditDialog(cap); });
  });
  root.querySelectorAll(".capsule-delete-btn").forEach(function(b) {
    b.addEventListener("click", confirmCapsuleDelete);
  });
}

function openCapsuleCreateDialog() {
  closeCapsuleOverlay();
  var extra = "<label>Открыть через (дней)</label><input type=\"number\" id=\"cap-days\" class=\"input\" min=\"0\" value=\"30\" />" +
    "<label>Открыть через (часов, только целые)</label><input type=\"number\" id=\"cap-hours\" class=\"input\" min=\"0\" step=\"1\" value=\"0\" placeholder=\"Только часы — укажите целое число\" />";
  openDialog({
    title: "Создать капсулу времени",
    extraHtml: extra,
    initialValues: { title: "Через 30 дней привычек я надеюсь…", description: "Опишите ожидаемый результат: как вы хотите себя чувствовать или выглядеть." },
    onSave: async function(p) {
      var t = (p.title || "").trim();
      var defaultTitle = "Через 30 дней привычек я надеюсь…";
      if (!t || t === defaultTitle) {
        if (tg) tg.showAlert("Необходимо добавить свой заголовок для капсулы времени"); else alert("Необходимо добавить свой заголовок для капсулы времени");
        throw new Error("validate");
      }
      var days = parseInt(document.getElementById("cap-days").value, 10) || 0;
      var hours = parseInt(document.getElementById("cap-hours").value, 10) || 0;
      if (days === 0 && hours === 0) {
        if (tg) tg.showAlert("Укажите время открытия: хотя бы 1 день или 1 час"); else alert("Укажите время открытия: хотя бы 1 день или 1 час");
        throw new Error("validate");
      }
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: p.title, expected_result: p.description, open_in_days: days, open_in_hours: hours })
      });
      await loadAll();
      if (tg) tg.showAlert("Капсула обновлена");
    }
  });
}

function openCapsuleEditDialog(cap) {
  var extra = "<label>Открыть через (дней)</label><input type=\"number\" id=\"cap-days\" class=\"input\" min=\"0\" value=\"0\" />" +
    "<label>Открыть через (часов, только целые)</label><input type=\"number\" id=\"cap-hours\" class=\"input\" min=\"0\" step=\"1\" value=\"24\" />";
  openDialog({
    title: "Редактировать капсулу",
    extraHtml: extra,
    initialValues: { title: cap.title || "", description: cap.expected_result || "" },
    onSave: async function(p) {
      var days = parseInt(document.getElementById("cap-days").value, 10) || 0;
      var hours = parseInt(document.getElementById("cap-hours").value, 10) || 0;
      if (days === 0 && hours === 0) {
        if (tg) tg.showAlert("Укажите хотя бы 1 час или 1 день"); else alert("Укажите хотя бы 1 час или 1 день");
        throw new Error("validate");
      }
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: p.title, expected_result: p.description, open_in_days: days, open_in_hours: hours })
      });
      await loadAll();
      if (tg) tg.showAlert("Капсула обновлена");
    }
  });
}

function confirmCapsuleDelete() {
  var msg = "Удалить капсулу времени?";
  if (tg && typeof tg.showConfirm === "function") {
    tg.showConfirm(msg, function(ok) { if (ok) doCapsuleDelete(); });
  } else if (window.confirm(msg)) {
    doCapsuleDelete();
  }
}

async function doCapsuleDelete() {
  try {
    await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule", { method: "DELETE" });
    await loadAll();
    if (tg) tg.showAlert("Капсула удалена");
  } catch (e) {
    if (tg) tg.showAlert("Не удалось удалить");
  }
}

async function showCapsuleHistory() {
  if (!state.userId) return;
  try {
    var list = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule/history");
    state.capsuleHistory = Array.isArray(list) ? list : [];
  } catch (e) {
    state.capsuleHistory = [];
  }
  state.capsuleView = "history";
  renderCapsule();
}

async function closeCapsuleOverlayAndArchive() {
  var overlay = $("#capsule-open-overlay");
  if (state.capsule && state.userId) {
    try {
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/time-capsule/archive", { method: "POST" });
    } catch (e) { /* ignore */ }
  }
  if (overlay) overlay.classList.add("hidden");
  await loadAll();
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
      "Не удалось определить пользователя. Откройте приложение по кнопке «🚀 Открыть приложение» в сообщении бота (в чате), а не по кнопке над клавиатурой. Нажмите /start и выберите кнопку в последнем сообщении.";
    console.error(errorMsg);
    if (tg) tg.showAlert("Откройте приложение по кнопке в сообщении бота (/start → кнопка внизу), не по кнопке над клавиатурой.");
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
      fetchJSON(base + "/api/user/" + uid + "/analytics?period=" + (state.analyticsPeriod || "month")).catch(e => {
        if (e && e.status === 401) throw e;
        console.error("❌ Аналитика:", e.message);
        return { period: "month", missions: { total: 0, completed: 0, avg_progress: 0 }, goals: { total: 0, completed: 0, completion_rate: 0 }, habits: { total: 0, total_completions: 0, streak: 0 }, habit_chart: { labels: [], values: [] } };
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

    state.cache.subgoalsByMission = {};
    if (missionsList.length) {
      var subs = await Promise.all(missionsList.map(function(m) {
        return fetchJSON(base + "/api/mission/" + m.id + "/subgoals").then(function(r) { return Array.isArray(r) ? r : []; }).catch(function() { return []; });
      }));
      missionsList.forEach(function(m, i) { state.cache.subgoalsByMission[m.id] = subs[i] || []; });
    }

    var capsuleRes = await fetchJSON(base + "/api/user/" + uid + "/time-capsule").catch(function() { return { capsule: null, can_edit: false }; });
    state.capsule = (capsuleRes && capsuleRes.capsule) || null;
    state.capsuleCanEdit = !!(capsuleRes && capsuleRes.can_edit);

    renderMissions(missionsList);
    renderGoals(goalsList);
    renderHabits(habitsList);
    renderAnalytics(analyticsData);
    renderProfile();
    renderCapsule();

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

function openShaolenChat() {
  var overlay = $("#shaolen-overlay");
  var chatEl = $("#shaolen-chat");
  var fab = $("#shaolen-fab");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  if (fab) fab.classList.add("shaolen-fab--hidden");
  if (chatEl) chatEl.classList.remove("shaolen-chat--fullscreen");
  state.shaolenFullscreen = false;
  var restoreBtn = $(".shaolen-restore-btn");
  var fullscreenBtn = $(".shaolen-fullscreen-btn");
  if (restoreBtn) restoreBtn.classList.add("hidden");
  if (fullscreenBtn) fullscreenBtn.classList.remove("hidden");
  var hp = $("#shaolen-history-panel");
  if (hp) hp.classList.add("hidden");
  fetchShaolenUsage().then(function() { renderShaolenChat(); });
}

function closeShaolenChat() {
  if (state.shaolenRecording) stopShaolenVoiceRecording();
  var overlay = $("#shaolen-overlay");
  var fab = $("#shaolen-fab");
  if (overlay) overlay.classList.add("hidden");
  if (fab) fab.classList.remove("shaolen-fab--hidden");
}

function fetchShaolenUsage() {
  var uid = state.userId;
  if (!uid) return Promise.resolve();
  return fetchJSON(state.baseUrl + "/api/user/" + uid + "/shaolen/usage")
    .then(function(r) { state.shaolenUsage = r || { used: 0, limit: 50 }; })
    .catch(function() { state.shaolenUsage = { used: 0, limit: 50 }; });
}

function renderShaolenChat() {
  var usageEl = $(".shaolen-usage");
  var messagesEl = $(".shaolen-messages");
  if (!messagesEl) return;
  var u = state.shaolenUsage || { used: 0, limit: 50 };
  if (usageEl) usageEl.textContent = "Запросов сегодня: " + u.used + " / " + u.limit;
  var msgs = state.shaolenMessages || [];
  var avatarSrc = "images/shaolen-avatar.png";
  var html = "";
  for (var i = 0; i < msgs.length; i++) {
    var m = msgs[i];
    var cls = m.role === "user" ? "shaolen-msg-user" : "shaolen-msg-assistant";
    var body = escapeHtml(m.content || "");
    if (m.imagePreview) body = "<img class=\"shaolen-msg-img\" src=\"" + escapeHtml(m.imagePreview) + "\" alt=\"\" />" + body;
    if (m.role === "assistant") {
      html += "<div class=\"shaolen-msg-row shaolen-msg-row-assistant\"><img src=\"" + escapeHtml(avatarSrc) + "\" alt=\"\" class=\"shaolen-msg-avatar\" /><div class=\"shaolen-msg " + cls + "\">" + body + "</div></div>";
    } else {
      html += "<div class=\"shaolen-msg-row shaolen-msg-row-user\"><div class=\"shaolen-msg " + cls + "\">" + body + "</div></div>";
    }
  }
  messagesEl.innerHTML = html;
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setShaolenFullscreen(on) {
  state.shaolenFullscreen = !!on;
  var chatEl = $("#shaolen-chat");
  var overlay = $("#shaolen-overlay");
  var restoreBtn = $(".shaolen-restore-btn");
  var fullscreenBtn = $(".shaolen-fullscreen-btn");
  if (chatEl) chatEl.classList.toggle("shaolen-chat--fullscreen", state.shaolenFullscreen);
  if (overlay) overlay.classList.toggle("shaolen-overlay--fullscreen", state.shaolenFullscreen);
  if (restoreBtn) restoreBtn.classList.toggle("hidden", !state.shaolenFullscreen);
  if (fullscreenBtn) fullscreenBtn.classList.toggle("hidden", state.shaolenFullscreen);
}

function openShaolenHistory() {
  var panel = $("#shaolen-history-panel");
  if (!panel || !state.userId) return;
  panel.classList.remove("hidden");
  var listEl = panel.querySelector(".shaolen-history-list");
  if (!listEl) return;
  listEl.innerHTML = "<div class=\"shaolen-history-loading\">Загрузка…</div>";
  fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/shaolen/history?limit=50")
    .then(function(rows) {
      state.shaolenHistory = rows || [];
      if (!state.shaolenHistory.length) {
        listEl.innerHTML = "<div class=\"shaolen-history-empty\">История пуста</div>";
        return;
      }
      var html = "";
      for (var i = 0; i < state.shaolenHistory.length; i++) {
        var r = state.shaolenHistory[i];
        var dateStr = (r.created_at || "").slice(0, 16).replace("T", " ");
        var userShort = (r.user_message || "").slice(0, 80);
        if ((r.user_message || "").length > 80) userShort += "…";
        var replyShort = (r.assistant_reply || "").slice(0, 120);
        if ((r.assistant_reply || "").length > 120) replyShort += "…";
        var userFull = escapeHtml(r.user_message || "");
        var replyFull = escapeHtml(r.assistant_reply || "");
        html += "<div class=\"shaolen-history-item\" data-idx=\"" + i + "\">";
        html += "<div class=\"shaolen-history-date\">" + escapeHtml(dateStr) + (r.has_image ? " 📷" : "") + " <span class=\"shaolen-history-toggle\">▼</span></div>";
        html += "<div class=\"shaolen-history-user\">" + escapeHtml(userShort) + "</div>";
        html += "<div class=\"shaolen-history-reply\">" + escapeHtml(replyShort) + "</div>";
        html += "<div class=\"shaolen-history-full\" style=\"display:none\"><div class=\"shaolen-history-full-req\">" + userFull + "</div><div class=\"shaolen-history-full-ans\">" + replyFull + "</div><button type=\"button\" class=\"shaolen-history-copy link-btn\">Скопировать запрос в буфер</button></div>";
        html += "</div>";
      }
      listEl.innerHTML = html;
      listEl.querySelectorAll(".shaolen-history-item").forEach(function(el) {
        var idx = parseInt(el.dataset.idx, 10);
        var r = state.shaolenHistory[idx];
        if (!r) return;
        var toggle = el.querySelector(".shaolen-history-toggle");
        var full = el.querySelector(".shaolen-history-full");
        var copyBtn = el.querySelector(".shaolen-history-copy");
        function openFull() {
          if (full.style.display === "none") {
            full.style.display = "block";
            if (toggle) toggle.textContent = "▲";
          } else {
            full.style.display = "none";
            if (toggle) toggle.textContent = "▼";
          }
        }
        el.addEventListener("click", function(ev) {
          if (ev.target.closest(".shaolen-history-copy")) return;
          openFull();
        });
        if (copyBtn) copyBtn.addEventListener("click", function(ev) {
          ev.stopPropagation();
          var t = (r.user_message || "") + "\n\n--- Ответ ---\n" + (r.assistant_reply || "");
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t).then(function() { if (tg) tg.showAlert("Скопировано"); });
          }
        });
      });
    })
    .catch(function() { listEl.innerHTML = "<div class=\"shaolen-history-empty\">Не удалось загрузить</div>"; });
}

function closeShaolenHistory() {
  var panel = $("#shaolen-history-panel");
  if (panel) panel.classList.add("hidden");
}

function clearShaolenImage() {
  state.shaolenImageData = null;
  var preview = $(".shaolen-image-preview");
  var input = $("#shaolen-image-input");
  if (preview) preview.innerHTML = "";
  if (input) input.value = "";
}

function clearShaolenVoice() {
  state.shaolenVoiceData = null;
  var preview = $(".shaolen-voice-preview");
  var input = $("#shaolen-voice-input");
  if (preview) preview.innerHTML = "";
  if (input) input.value = "";
}

function startShaolenVoiceRecording() {
  if (state.shaolenRecording) return;
  var MR = window.MediaRecorder || window.webkitMediaRecorder;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !MR) {
    if (tg) tg.showAlert("Запись с микрофона недоступна. Используйте кнопку 📎 для выбора аудиофайла.");
    return;
  }
  state.shaolenRecordingChunks = [];
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(function(stream) {
      state.shaolenRecording = true;
      state.shaolenRecordingStream = stream;
      var mime = "audio/webm";
      if (MR.isTypeSupported && MR.isTypeSupported("audio/webm;codecs=opus")) mime = "audio/webm;codecs=opus";
      else if (MR.isTypeSupported && MR.isTypeSupported("audio/webm")) mime = "audio/webm";
      var rec;
      try {
        rec = new MR(stream, { mimeType: mime, audioBitsPerSecond: 64000 });
      } catch (_) {
        rec = new MR(stream);
      }
      state.shaolenMediaRecorder = rec;
      rec.ondataavailable = function(e) { if (e.data && e.data.size > 0) state.shaolenRecordingChunks.push(e.data); };
      rec.onstop = function() {
        var micBtn = $(".shaolen-voice-btn");
        if (micBtn) micBtn.classList.remove("shaolen-recording-active");
        if (state.shaolenRecordingStream) {
          state.shaolenRecordingStream.getTracks().forEach(function(t) { t.stop(); });
          state.shaolenRecordingStream = null;
        }
        state.shaolenMediaRecorder = null;
        state.shaolenRecording = false;
        var preview = $(".shaolen-voice-preview");
        if (state.shaolenRecordingChunks.length === 0) {
          if (preview) preview.innerHTML = "";
          if (tg) tg.showAlert("Запись пуста. Попробуйте ещё раз.");
          return;
        }
        var blob = new Blob(state.shaolenRecordingChunks, { type: "audio/webm" });
        state.shaolenRecordingChunks = [];
        var fr = new FileReader();
        fr.onload = function() {
          var data = fr.result;
          if (typeof data === "string" && data) {
            state.shaolenVoiceData = data;
            if (preview) {
              preview.innerHTML = "<span class=\"shaolen-preview-thumb\">🎤 голосовое</span> <button type=\"button\" class=\"shaolen-voice-remove link-btn\">удалить</button>";
              var removeBtn = preview.querySelector(".shaolen-voice-remove");
              if (removeBtn) removeBtn.addEventListener("click", function() { clearShaolenVoice(); });
            }
            renderShaolenChat();
          }
        };
        fr.readAsDataURL(blob);
      };
      rec.start(200);
      var preview = $(".shaolen-voice-preview");
      var micBtn = $(".shaolen-voice-btn");
      if (micBtn) micBtn.classList.add("shaolen-recording-active");
      if (preview) {
        preview.innerHTML = "<span class=\"shaolen-preview-thumb shaolen-recording\">🔴 Запись…</span> <button type=\"button\" class=\"shaolen-record-stop link-btn\">Остановить</button>";
        var stopBtn = preview.querySelector(".shaolen-record-stop");
        if (stopBtn) stopBtn.addEventListener("click", stopShaolenVoiceRecording);
      }
      renderShaolenChat();
    })
    .catch(function(err) {
      state.shaolenRecording = false;
      if (tg) tg.showAlert("Нет доступа к микрофону. Разрешите микрофон в настройках или прикрепите файл (📎).");
      console.warn("getUserMedia error:", err);
    });
}

function stopShaolenVoiceRecording() {
  if (!state.shaolenRecording || !state.shaolenMediaRecorder) return;
  try {
    if (state.shaolenMediaRecorder.state === "recording") state.shaolenMediaRecorder.stop();
  } catch (e) { state.shaolenRecording = false; state.shaolenMediaRecorder = null; }
}

function compressImageForShaolen(file, maxBytes) {
  maxBytes = maxBytes || 700000;
  return new Promise(function(resolve, reject) {
    var img = new Image();
    var url = (typeof URL !== "undefined" && URL.createObjectURL) ? URL.createObjectURL(file) : null;
    if (!url) { reject(new Error("No URL.createObjectURL")); return; }
    img.onload = function() {
      if (typeof URL !== "undefined" && URL.revokeObjectURL) URL.revokeObjectURL(url);
      var w = img.naturalWidth || img.width;
      var h = img.naturalHeight || img.height;
      var maxSide = 1024;
      if (w > maxSide || h > maxSide) {
        if (w > h) { h = Math.round(h * maxSide / w); w = maxSide; } else { w = Math.round(w * maxSide / h); h = maxSide; }
      }
      var canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      var ctx = canvas.getContext("2d");
      if (!ctx) { resolve(null); return; }
      ctx.drawImage(img, 0, 0, w, h);
      var quality = 0.82;
      function tryExport() {
        canvas.toBlob(function(blob) {
          if (!blob) { resolve(null); return; }
          if (blob.size <= maxBytes) {
            var fr = new FileReader();
            fr.onload = function() { resolve(fr.result); };
            fr.onerror = function() { resolve(null); };
            fr.readAsDataURL(blob);
            return;
          }
          quality -= 0.12;
          if (quality > 0.2) tryExport(); else {
            var fr2 = new FileReader();
            fr2.onload = function() { resolve(fr2.result); };
            fr2.onerror = function() { resolve(null); };
            fr2.readAsDataURL(blob);
          }
        }, "image/jpeg", quality);
      }
      tryExport();
    };
    img.onerror = function() {
      if (typeof URL !== "undefined" && URL.revokeObjectURL) URL.revokeObjectURL(url);
      reject(new Error("Failed to load image"));
    };
    img.src = url;
  });
}

function sendShaolenMessage() {
  var input = $("#shaolen-input");
  var sendBtn = $("#shaolen-send");
  if (!input || !state.userId) return;
  var text = (input.value || "").trim();
  var hasImage = !!state.shaolenImageData;
  var hasVoice = !!state.shaolenVoiceData;
  if (!text && !hasImage && !hasVoice) return;
  var u = state.shaolenUsage || { used: 0, limit: 50 };
  if (u.used >= u.limit) {
    if (tg) tg.showAlert("Достигнут лимит запросов на сегодня (50). Заходите завтра.");
    return;
  }
  var displayContent = text || (hasImage ? "[Фото]" : (hasVoice ? "[Голосовое]" : ""));
  state.shaolenMessages.push({
    role: "user",
    content: displayContent,
    imagePreview: hasImage ? (state.shaolenImageData.indexOf("data:") === 0 ? state.shaolenImageData : "data:image/jpeg;base64," + state.shaolenImageData) : null,
  });
  input.value = "";
  var bodyToSend = {
    message: text || (hasImage ? "Что на фото? Оцени калории и дай краткий совет." : (hasVoice ? "" : "")),
  };
  if (state.shaolenImageData) bodyToSend.image_base64 = state.shaolenImageData;
  if (state.shaolenVoiceData) bodyToSend.audio_base64 = state.shaolenVoiceData;
  var prev = state.shaolenMessages.slice(0, -1).slice(-20);
  bodyToSend.history = prev.map(function(m) { return { role: m.role, content: (m.content || "").slice(0, 1200) }; });
  clearShaolenImage();
  clearShaolenVoice();
  renderShaolenChat();
  if (sendBtn) sendBtn.disabled = true;
  fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/shaolen/ask", {
    method: "POST",
    body: JSON.stringify(bodyToSend),
  })
    .then(function(res) {
      var reply = (res && res.reply != null) ? String(res.reply).trim() : "";
      if (!reply) {
        reply = "Ответ не получен. Попробуйте переформулировать или записать голосовое кнопкой 🎤.";
      }
      state.shaolenMessages.push({ role: "assistant", content: reply });
      state.shaolenUsage = (res && res.usage) ? res.usage : state.shaolenUsage;
      renderShaolenChat();
      if (res && res.created) loadAll();
    })
    .catch(function(err) {
      var msg = "Не удалось получить ответ.";
      if (err && err.status === 429) msg = "Лимит запросов на сегодня исчерпан. Заходите завтра.";
      else if (err && err.status === 413) msg = "Фото слишком большое. Выберите другое или меньшее изображение.";
      else if (err && err.body) { try { var j = JSON.parse(err.body); if (j.detail) msg = j.detail; } catch (_) {} }
      state.shaolenMessages.push({ role: "assistant", content: "⚠️ " + msg });
      renderShaolenChat();
      if (err && err.status === 429 && err.body) {
        try { var j = JSON.parse(err.body); if (j.usage) state.shaolenUsage = j.usage; } catch (_) {}
      }
    })
    .finally(function() { if (sendBtn) sendBtn.disabled = false; });
}

function openCapsuleOverlay() {
  var ov = $("#capsule-overlay");
  if (ov) { ov.classList.remove("hidden"); renderCapsule(); }
}

function closeCapsuleOverlay() {
  var ov = $("#capsule-overlay");
  if (ov) ov.classList.add("hidden");
}

function bindEvents() {
  var tabEls = $all(".tab");
  tabEls.forEach(function(btn) {
    btn.addEventListener("click", function() { switchTab(btn.dataset.tab); });
  });
  var capsuleMenuBtn = document.getElementById("capsule-menu-btn");
  if (capsuleMenuBtn) capsuleMenuBtn.addEventListener("click", openCapsuleOverlay);
  var capsuleOverlayClose = document.getElementById("capsule-overlay-close");
  if (capsuleOverlayClose) capsuleOverlayClose.addEventListener("click", closeCapsuleOverlay);
  var capsuleBackdrop = $(".capsule-overlay-backdrop");
  if (capsuleBackdrop) capsuleBackdrop.addEventListener("click", closeCapsuleOverlay);
  var capsuleCloseBtn = document.getElementById("capsule-open-close");
  if (capsuleCloseBtn) capsuleCloseBtn.addEventListener("click", function() {
    closeCapsuleOverlayAndArchive().catch(function() {});
  });

  var shaolenFab = $("#shaolen-fab");
  if (shaolenFab) shaolenFab.addEventListener("click", function() {
    if (!state.userId) { if (tg) tg.showAlert("Откройте приложение из Telegram."); return; }
    openShaolenChat();
  });
  var shaolenClose = $(".shaolen-close");
  if (shaolenClose) shaolenClose.addEventListener("click", closeShaolenChat);
  var shaolenHistoryBtn = $(".shaolen-history-btn");
  if (shaolenHistoryBtn) shaolenHistoryBtn.addEventListener("click", openShaolenHistory);
  var shaolenHistoryClose = $(".shaolen-history-close");
  if (shaolenHistoryClose) shaolenHistoryClose.addEventListener("click", closeShaolenHistory);
  var shaolenFullscreenBtn = $(".shaolen-fullscreen-btn");
  if (shaolenFullscreenBtn) shaolenFullscreenBtn.addEventListener("click", function() { setShaolenFullscreen(true); });
  var shaolenRestoreBtn = $(".shaolen-restore-btn");
  if (shaolenRestoreBtn) shaolenRestoreBtn.addEventListener("click", function() { setShaolenFullscreen(false); });
  var shaolenSwipeArea = $(".shaolen-swipe-area");
  if (shaolenSwipeArea) {
    var startY = 0;
    shaolenSwipeArea.addEventListener("touchstart", function(e) { startY = e.touches[0].clientY; }, { passive: true });
    shaolenSwipeArea.addEventListener("touchend", function(e) {
      var endY = e.changedTouches && e.changedTouches[0] ? e.changedTouches[0].clientY : startY;
      if (startY - endY > 50) setShaolenFullscreen(true);
    }, { passive: true });
  }
  var shaolenSend = $("#shaolen-send");
  if (shaolenSend) shaolenSend.addEventListener("click", sendShaolenMessage);
  var shaolenInput = $("#shaolen-input");
  if (shaolenInput) shaolenInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendShaolenMessage(); }
  });
  var shaolenAttachBtn = $(".shaolen-attach-btn");
  var shaolenImageInput = $("#shaolen-image-input");
  if (shaolenAttachBtn && shaolenImageInput) {
    shaolenAttachBtn.addEventListener("click", function() { shaolenImageInput.click(); });
    shaolenImageInput.addEventListener("change", function() {
      var f = shaolenImageInput.files && shaolenImageInput.files[0];
      if (!f || !f.type.match(/^image\//)) return;
      var preview = $(".shaolen-image-preview");
      if (preview) preview.innerHTML = "<span class=\"shaolen-preview-thumb\">Сжатие…</span>";
      compressImageForShaolen(f, 600000).then(function(data) {
        if (!data || typeof data !== "string") {
          if (preview) preview.innerHTML = "";
          if (tg) tg.showAlert("Не удалось обработать фото.");
          return;
        }
        state.shaolenImageData = data;
        if (preview) {
          preview.innerHTML = "<span class=\"shaolen-preview-thumb\">📷</span> <button type=\"button\" class=\"shaolen-preview-remove link-btn\">удалить</button>";
          var removeBtn = preview.querySelector(".shaolen-preview-remove");
          if (removeBtn) removeBtn.addEventListener("click", function() { clearShaolenImage(); });
        }
      }).catch(function() {
        if (preview) preview.innerHTML = "";
        if (tg) tg.showAlert("Не удалось загрузить фото.");
      });
    });
  }
  var shaolenVoiceBtn = $(".shaolen-voice-btn");
  var shaolenVoiceInput = $("#shaolen-voice-input");
  var shaolenVoiceAttachBtn = $(".shaolen-voice-attach-btn");
  if (shaolenVoiceBtn) {
    shaolenVoiceBtn.addEventListener("click", function() {
      if (state.shaolenRecording) {
        stopShaolenVoiceRecording();
      } else {
        startShaolenVoiceRecording();
      }
    });
  }
  if (shaolenVoiceAttachBtn && shaolenVoiceInput) {
    shaolenVoiceAttachBtn.addEventListener("click", function() { shaolenVoiceInput.click(); });
  }
  if (shaolenVoiceInput) {
    shaolenVoiceInput.addEventListener("change", function() {
      var f = shaolenVoiceInput.files && shaolenVoiceInput.files[0];
      if (!f || !f.type.match(/^audio\//)) {
        shaolenVoiceInput.value = "";
        return;
      }
      var maxBytes = 20 * 1024 * 1024;
      if (f.size > maxBytes) {
        if (tg) tg.showAlert("Файл больше 20 МБ. Выберите более короткое голосовое.");
        shaolenVoiceInput.value = "";
        return;
      }
      var preview = $(".shaolen-voice-preview");
      if (preview) preview.innerHTML = "<span class=\"shaolen-preview-thumb\">Загрузка…</span>";
      var fr = new FileReader();
      fr.onload = function() {
        var data = fr.result;
        if (typeof data !== "string" || !data) {
          if (preview) preview.innerHTML = "";
          return;
        }
        state.shaolenVoiceData = data;
        if (preview) {
          preview.innerHTML = "<span class=\"shaolen-preview-thumb\">🎤 голосовое</span> <button type=\"button\" class=\"shaolen-voice-remove link-btn\">удалить</button>";
          var removeBtn = preview.querySelector(".shaolen-voice-remove");
          if (removeBtn) removeBtn.addEventListener("click", function() { clearShaolenVoice(); });
        }
        renderShaolenChat();
      };
      fr.onerror = function() {
        if (preview) preview.innerHTML = "";
        if (tg) tg.showAlert("Не удалось загрузить голосовое.");
        shaolenVoiceInput.value = "";
      };
      fr.readAsDataURL(f);
    });
  }
  var shaolenOverlay = $("#shaolen-overlay");
  if (shaolenOverlay) shaolenOverlay.addEventListener("click", function(e) {
    if (e.target === shaolenOverlay) closeShaolenChat();
  });

  document.body.addEventListener("change", async function(e) {
    var cb = e.target;
    if (cb.classList && cb.classList.contains("mission-done-cb") && cb.checked) {
      e.preventDefault();
      try {
        await fetchJSON(state.baseUrl + "/api/missions/" + cb.dataset.id + "/complete", { method: "POST" });
        await loadAll();
      } catch (err) { if (tg) tg.showAlert("Ошибка"); }
      return;
    }
    if (cb.classList && cb.classList.contains("goal-done-cb") && cb.checked) {
      e.preventDefault();
      try {
        await fetchJSON(state.baseUrl + "/api/goals/" + cb.dataset.id + "/complete", { method: "POST" });
        await loadAll();
      } catch (err) { if (tg) tg.showAlert("Ошибка"); }
      return;
    }
    if (cb.classList && cb.classList.contains("subgoal-done-cb") && cb.checked) {
      e.preventDefault();
      try {
        await fetchJSON(state.baseUrl + "/api/subgoals/" + cb.dataset.id + "/complete", { method: "POST" });
        await loadAll();
      } catch (err) { if (tg) tg.showAlert("Ошибка"); }
      return;
    }
  });

  document.body.addEventListener("click", async function(e) {
    var periodBtn = e.target.closest(".analytics-period-btn");
    if (periodBtn) {
      e.preventDefault();
      state.analyticsPeriod = periodBtn.dataset.period || "month";
      var base = state.baseUrl, uid = state.userId;
      if (!uid) return;
      try {
        var ax = await fetchJSON(base + "/api/user/" + uid + "/analytics?period=" + state.analyticsPeriod);
        state.cache.analytics = ax;
        renderAnalytics(ax);
        $all(".analytics-period-btn").forEach(function(b) { b.classList.toggle("active", b.dataset.period === state.analyticsPeriod); });
      } catch (err) { if (tg) tg.showAlert("Ошибка загрузки аналитики"); }
      return;
    }
    var addBtn = e.target.closest(".add-subgoal-btn");
    if (addBtn) {
      e.preventDefault();
      var mid = addBtn.dataset.missionId;
      if (!mid) return;
      openDialog({
        title: "Подцель",
        initialValues: { title: "", description: "" },
        onSave: async function(p) {
          await fetchJSON(state.baseUrl + "/api/missions/" + mid + "/subgoals", { method: "POST", body: JSON.stringify({ title: p.title, description: p.description || "" }) });
          await loadAll();
        }
      });
      return;
    }

    var content = e.target.closest(".swipe-row-content");
    if (content && !e.target.closest(".habit-btn, .swipe-delete-btn, .mission-done-cb-wrap, .goal-done-cb-wrap, .subgoal-done-cb, .subgoal-cb-wrap, .add-subgoal-btn")) {
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
              var missionExtra = "<label>Дата окончания</label><input id=\"deadline-input\" class=\"input\" type=\"date\" />";
              openDialog({
                title: "Редактировать миссию",
                extraHtml: missionExtra,
                initialValues: { title: item.title || "", description: item.description || "", deadline: item.deadline ? String(item.deadline).slice(0, 10) : "" },
                onSave: async function(p) {
                  var dlEl = document.getElementById("deadline-input");
                  var dlVal = (dlEl && dlEl.value) ? dlEl.value : null;
                  await fetchJSON(state.baseUrl + "/api/missions/" + id, { method: "PUT", body: JSON.stringify({ title: p.title, description: p.description, deadline: dlVal || null }) });
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
    var missionAddExtra = "<label>Дата окончания</label><input id=\"deadline-input\" class=\"input\" type=\"date\" />";
    openDialog({
      title: "Новая миссия",
      extraHtml: missionAddExtra,
      initialValues: { title: "", description: "", deadline: "" },
      onSave: async function(p) {
        var dlEl = document.getElementById("deadline-input");
        var dlVal = (dlEl && dlEl.value) ? dlEl.value : null;
        await fetchJSON(state.baseUrl + "/api/missions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: state.userId, title: p.title, description: p.description || "", deadline: dlVal }),
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
  console.log("WebApp v5 — капсула времени");
  initUser();
  bindEvents();
  await loadAll();
  var hash = window.location.hash || "";
  if (hash === "#capsule") openCapsuleOverlay();
  if (hash === "#capsule-history") { openCapsuleOverlay(); showCapsuleHistory(); }
});

