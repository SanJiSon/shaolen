const tg = window.Telegram?.WebApp;

// В браузере вне Telegram tg.showAlert/showConfirm кидают WebAppMethodUnsupported — подменяем на alert/confirm
if (tg) {
  if (typeof tg.showAlert === "function") {
    var _showAlert = tg.showAlert.bind(tg);
    tg.showAlert = function(msg) {
      try { _showAlert(msg); } catch (e) { alert(msg); }
    };
  }
  if (typeof tg.showConfirm === "function") {
    var _showConfirm = tg.showConfirm.bind(tg);
    tg.showConfirm = function(msg, cb) {
      try { _showConfirm(msg, cb); } catch (e) { if (typeof cb === "function") cb(confirm(msg)); }
    };
  }
}

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
  lastWaterResult: null,
  profileSubTab: "general", // "general" | "person" | "bmi" | "water" | "stats"
  sortableMissions: null,
  sortableGoals: null,
  sortableHabits: null,
  sortableSubgoals: [],
  reorderMode: false,
  reminderSettings: null,
  googleFitConnected: false,
  googleFitSteps: null,
  habitCalendarYear: new Date().getFullYear(),
  habitCalendarMonth: new Date().getMonth() + 1
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
  if (tg) {
    try { if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes(); } catch (_) {}
    try { if (typeof tg.disableHorizontalSwipes === "function") tg.disableHorizontalSwipes(); } catch (_) {}
  }
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
  if (tabName === "profile") {
    loadGoogleFitStatus().then(function() {
      if (state.googleFitConnected) return loadGoogleFitSteps();
    }).then(function() { renderProfile(); });
  }
}

async function fetchJSON(url, options = {}) {
  try {
    var headers = { 'Content-Type': 'application/json' };
    if (options.headers) Object.assign(headers, options.headers);
    if (url.indexOf("/api/") !== -1 && tg && tg.initData) {
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

function openDialog({ title, extraHtml = "", onSave, onDelete, initialValues }) {
  if (tg && tg.MainButton) tg.MainButton.hide();
  var titleEl = $("#dialog-title");
  var titleInput = $("#dialog-title-input");
  var descInput = $("#dialog-description-input");
  var extraEl = $("#dialog-extra");
  var backdrop = $("#dialog-backdrop");
  var form = $("#dialog-form");
  var deleteBtn = $("#dialog-delete");
  var iv = initialValues || {};
  if (titleEl) titleEl.textContent = title || "";
  if (titleInput) titleInput.value = (iv.title != null ? iv.title : "") || "";
  if (descInput) descInput.value = (iv.description != null ? iv.description : "") || "";
  if (extraEl) extraEl.innerHTML = extraHtml || "";
  if (backdrop) backdrop.classList.remove("hidden");
  if (deleteBtn) {
    if (onDelete) {
      deleteBtn.classList.remove("hidden");
      deleteBtn.onclick = function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var p = onDelete();
        var promise = (p && typeof p.then === "function" ? p : Promise.resolve());
        promise.then(function() {
          if (backdrop) backdrop.classList.add("hidden");
          if (form) form.onsubmit = null;
        }).catch(function(err) {
          if (tg) tg.showAlert("Не удалось удалить");
        });
      };
    } else {
      deleteBtn.classList.add("hidden");
      deleteBtn.onclick = null;
    }
  }
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
    <div class="swipe-row-drag-handle" aria-label="Перетащить"><span class="material-symbols-outlined">drag_indicator</span></div>
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
      if (e.target.closest(".habit-btn, .swipe-delete-btn, .swipe-row-drag-handle")) return;
      if (window._sortableDragging) return;
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
  if (state.sortableMissions) {
    state.sortableMissions.destroy();
    state.sortableMissions = null;
  }
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
    var completedSubs = subs.filter(function(s) { return s.is_completed; }).length;
    var totalSubs = subs.length;
    var subProgressPct = totalSubs > 0 ? Math.round((completedSubs / totalSubs) * 100) : 0;
    var subsHtml = subs.map(function(s) {
      var doneClass = s.is_completed ? " subgoal-done" : "";
      return "<div class=\"subgoal-row" + doneClass + "\" data-id=\"" + s.id + "\"><label class=\"subgoal-cb-wrap\"><input type=\"checkbox\" class=\"subgoal-done-cb\" data-id=\"" + s.id + "\" " + (s.is_completed ? "checked" : "") + " /><span>" + escapeHtml(s.title || "") + "</span></label><span class=\"subgoal-drag-handle\" aria-label=\"Удерживайте для перетаскивания\"><span class=\"material-symbols-outlined\">drag_indicator</span></span></div>";
    }).join("");
    var exampleBadge = (m.is_example ? "<span class=\"example-badge\">Пример</span>" : "");
    var progressBarHtml = totalSubs > 0 ? "<div class=\"mission-progress\"><div class=\"mission-progress-bar\"><div class=\"mission-progress-fill\" style=\"width:" + subProgressPct + "%\"></div></div><span class=\"mission-progress-label\">" + completedSubs + "/" + totalSubs + " подцелей</span></div>" : "";
    card.innerHTML =
      "<div class=\"card-header card-header-with-cb\">" +
      "<label class=\"mission-done-cb-wrap\"><input type=\"checkbox\" class=\"mission-done-cb\" data-id=\"" + m.id + "\" " + (m.is_completed ? "checked" : "") + " /></label>" +
      "<div class=\"card-title\">" + title + "</div>" +
      "<span class=\"badge\">" + done + "</span>" + exampleBadge +
      "</div>" +
      "<div class=\"card-description\">" + description + "</div>" +
      "<div class=\"card-meta\"><span>Создана: " + createdAt + "</span>" + (deadline ? "<span>Окончание: " + deadline + "</span>" : "") + "</div>" +
      (subs.length || true ? "<div class=\"card-subgoals\"><div class=\"subgoals-title\">Подцели</div><div class=\"subgoals-list\" data-mission-id=\"" + m.id + "\">" + subsHtml + "</div><button type=\"button\" class=\"link-btn add-subgoal-btn\" data-mission-id=\"" + m.id + "\">＋ Подцель</button></div>" : "") +
      progressBarHtml +
      "";
    card.dataset.editId = String(m.id);
    card.dataset.editType = "mission";
    root.appendChild(wrapSwipeDelete(card, "mission", m.id));
  });
  setupSwipeDelete(root);
  setupSortableSubgoals(root);
  setupSortableMissions(root);
}

function resetSwipeState(el) {
  if (!el) return;
  var content = el.querySelector(".swipe-row-content");
  if (content) content.style.transform = "";
  el.classList.remove("swiped");
}

function createSortableCommon(listEl, options) {
  if (typeof Sortable === "undefined") return null;
  var userOnEnd = options.onEnd;
  var userOnStart = options.onStart;
  options.onEnd = function(evt) {
    document.querySelectorAll(".swipe-row.subgoal-dragging").forEach(function(el) { el.classList.remove("subgoal-dragging"); });
    window._sortableDragging = false;
    document.body.classList.remove("drag-active");
    document.body.style.paddingRight = "";
    if (userOnEnd) userOnEnd.call(this, evt);
  };
  options.onStart = function(evt) {
    window._sortableDragging = true;
    resetSwipeState(evt.item);
    document.body.classList.add("drag-active");
    var scrollbarW = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarW > 0) document.body.style.paddingRight = scrollbarW + "px";
    if (userOnStart) userOnStart.call(this, evt);
  };
  return new Sortable(listEl, Object.assign({
    animation: 150,
    dataIdAttr: "data-id",
    draggable: ".swipe-row",
    forceFallback: true,
    fallbackOnBody: true,
    swapThreshold: 0.65,
    chosenClass: "sortable-chosen",
    ghostClass: "sortable-ghost",
    onClone: function(evt) {
      resetSwipeState(evt.clone);
    }
  }, options));
}

function setupSortableSubgoals(container) {
  if (!container || typeof Sortable === "undefined") return;
  state.sortableSubgoals.forEach(function(s) { if (s && s.destroy) s.destroy(); });
  state.sortableSubgoals = [];
  container.querySelectorAll(".subgoals-list[data-mission-id]").forEach(function(list) {
    var missionId = list.dataset.missionId;
    var sortable = createSortableCommon(list, {
      draggable: ".subgoal-row",
      handle: ".subgoal-drag-handle",
      onStart: function(evt) {
        var swipeRow = evt.item.closest(".swipe-row");
        if (swipeRow) swipeRow.classList.add("subgoal-dragging");
      },
      onEnd: function(evt) {
        var ids = this.toArray().map(function(id) { return parseInt(id, 10); }).filter(function(n) { return !isNaN(n); });
        if (ids.length && missionId) {
          fetchJSON(state.baseUrl + "/api/mission/" + missionId + "/subgoals/order", { method: "PUT", body: JSON.stringify({ subgoal_ids: ids }) }).then(function() { loadAll(); }).catch(function() { loadAll(); });
        }
      }
    });
    if (sortable) state.sortableSubgoals.push(sortable);
  });
}

function setupSortableMissions(container) {
  if (!container || !state.userId || typeof Sortable === "undefined") return;
  state.sortableMissions = createSortableCommon(container, {
    handle: ".swipe-row-drag-handle",
    onEnd: function(evt) {
      var ids = this.toArray().map(function(id) { return parseInt(id, 10); }).filter(function(n) { return !isNaN(n); });
      if (ids.length) {
        fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/missions/order", { method: "PUT", body: JSON.stringify({ mission_ids: ids }) }).then(function() { loadAll(); }).catch(function() { loadAll(); });
      }
    }
  });
}

function renderGoals(goals) {
  var root = $("#goals-list");
  if (state.sortableGoals) {
    state.sortableGoals.destroy();
    state.sortableGoals = null;
  }
  root.innerHTML = "";

  if (!goals || goals.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет целей.<br>Нажмите <strong>«+ Добавить»</strong></div>';
    return;
  }

  goals.forEach(function(g) {
    var done = g.is_completed ? "Завершена" : "В процессе";
    var priority = g.priority === 3 ? "🔥 Высокий" : g.priority === 2 ? "⭐ Средний" : "📌 Низкий";
    var card = document.createElement("div");
    card.className = "card card-goal" + (g.is_completed ? " goal-done" : "");
    var title = escapeHtml(g.title || "");
    var description = escapeHtml(g.description || "Без описания");
    var dl = g.deadline ? "Дедлайн: " + String(g.deadline).slice(0, 10) : "";
    var exampleBadge = (g.is_example ? "<span class=\"example-badge\">Пример</span>" : "");
    card.innerHTML =
      "<div class=\"card-header card-header-with-cb\">" +
      "<label class=\"goal-done-cb-wrap\"><input type=\"checkbox\" class=\"goal-done-cb\" data-id=\"" + g.id + "\" " + (g.is_completed ? "checked" : "") + " /></label>" +
      "<div class=\"card-title\">" + title + "</div>" +
      "<span class=\"badge\">" + priority + "</span>" + exampleBadge +
      "</div>" +
      "<div class=\"card-description\">" + description + "</div>" +
      "<div class=\"card-meta\"><span>" + done + "</span><span>" + dl + "</span></div>" +
      "";
    root.appendChild(wrapSwipeDelete(card, "goal", g.id));
  });
  setupSwipeDelete(root);
  setupSortableGoals(root);
}

function setupSortableGoals(container) {
  if (!container || !state.userId || typeof Sortable === "undefined") return;
  state.sortableGoals = createSortableCommon(container, {
    handle: ".swipe-row-drag-handle",
    onEnd: function(evt) {
      var ids = this.toArray().map(function(id) { return parseInt(id, 10); }).filter(function(n) { return !isNaN(n); });
      if (ids.length) {
        fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/goals/order", { method: "PUT", body: JSON.stringify({ goal_ids: ids }) }).then(function() { loadAll(); }).catch(function() { loadAll(); });
      }
    }
  });
}

function setupSortableHabits(container) {
  if (!container || !state.userId || typeof Sortable === "undefined") return;
  state.sortableHabits = createSortableCommon(container, {
    handle: ".swipe-row-drag-handle",
    onEnd: function(evt) {
      var ids = this.toArray().map(function(id) { return parseInt(id, 10); }).filter(function(n) { return !isNaN(n); });
      if (ids.length) {
        fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/habits/order", { method: "PUT", body: JSON.stringify({ habit_ids: ids }) }).then(function() { loadAll(); }).catch(function() { loadAll(); });
      }
    }
  });
}

function renderHabits(habits) {
  const root = $("#habits-list");
  if (state.sortableHabits) {
    state.sortableHabits.destroy();
    state.sortableHabits = null;
  }
  root.innerHTML = "";

  if (!habits || habits.length === 0) {
    root.innerHTML = '<div class="empty-state">У вас пока нет привычек.<br>Нажмите <strong>«+ Добавить»</strong></div>';
    return;
  }

  var HABIT_TARGET_DAYS = 21;
  habits.forEach((h) => {
    const count = h.today_count || 0;
    const habitId = parseInt(h.id) || 0;
    var totalCompletions = parseInt(h.total_completions || 0);
    const remindersOn = h.reminders_enabled !== 0;
    const card = document.createElement("div");
    card.className = "card habit-card habitica-row";
    const title = escapeHtml(h.title || '');
    var exampleBadge = (h.is_example ? "<span class=\"example-badge\">Пример</span>" : "");
    var waterCalcBadge = (h.is_water_calculated ? "<span class=\"water-calc-badge\">Рассчитана автоматически</span><button type=\"button\" class=\"habit-water-help icon-btn\" aria-label=\"Как рассчитано\" title=\"Как рассчитано\" data-desc=\"" + escapeHtml((h.description || "").replace(/"/g, "&quot;")) + "\">?</button>" : "");
    var pct = HABIT_TARGET_DAYS > 0 ? Math.round((totalCompletions / HABIT_TARGET_DAYS) * 100) : 0;
    var barPct = Math.min(100, pct);
    var barSegments = 10;
    var filledSegments = pct >= 100 ? 10 : Math.round((barPct / 100) * barSegments);
    var barHtml = "";
    for (var i = 0; i < barSegments; i++) barHtml += "<span class=\"habit-progress-seg " + (i < filledSegments ? "filled" : "") + "\"></span>";
    var progressHtml = "<div class=\"habit-progress\"><div class=\"habit-progress-bar\">" + barHtml + "</div><span class=\"habit-progress-text\">" + pct + "% (" + totalCompletions + "/" + HABIT_TARGET_DAYS + ")</span></div>";
    card.innerHTML = `
      <div class="habit-card-content">
        <button type="button" class="habit-btn habit-btn-plus" data-habit-id="${habitId}" data-action="increment">+</button>
        <div class="habit-name">${title}${exampleBadge}${waterCalcBadge}</div>
        <button type="button" class="habit-reminder-toggle icon-btn" data-habit-id="${habitId}" data-enabled="${remindersOn ? "1" : "0"}" aria-label="${remindersOn ? "Напоминания вкл" : "Напоминания выкл"}" title="${remindersOn ? "Напоминания вкл" : "Напоминания выкл"}"><span class="material-symbols-outlined">${remindersOn ? "notifications" : "notifications_off"}</span></button>
        <div class="habit-count-wrap ${count ? '' : 'hide'}">
          <span class="habit-count-number">${count}</span>
          <span class="habit-count-unit">раз</span>
        </div>
        <button type="button" class="habit-btn habit-btn-minus" data-habit-id="${habitId}" data-action="decrement">−</button>
      </div>
      ${progressHtml}
    `;
    card.dataset.editId = String(h.id);
    card.dataset.editType = "habit";
    root.appendChild(wrapSwipeDelete(card, "habit", h.id));
    var waterHelpBtn = card.querySelector(".habit-water-help");
    if (waterHelpBtn && h.description) {
      waterHelpBtn.addEventListener("click", function(e) {
        e.preventDefault();
        e.stopPropagation();
        var text = (h.description || "").trim() || "Норма рассчитана по формуле с учётом веса, активности и погоды (ВОЗ/Mayo).";
        if (tg && tg.showAlert) tg.showAlert(text); else alert(text);
      });
    }
  });
  setupSwipeDelete(root);
  setupSortableHabits(root);

  root.querySelectorAll('.habit-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const habitId = parseInt(btn.dataset.habitId);
      const action = btn.dataset.action;
      var h = (state.cache.habits || []).find(function(x) { return String(x.id) === String(habitId); });
      var prevToday = 0, prevTotal = 0;
      if (h) {
        prevToday = h.today_count || 0;
        prevTotal = h.total_completions || 0;
        if (action === 'increment') {
          h.today_count = prevToday + 1;
          h.total_completions = prevTotal + 1;
        } else {
          h.today_count = Math.max(0, prevToday - 1);
          h.total_completions = Math.max(0, prevTotal - 1);
        }
        renderHabits(state.cache.habits);
      }
      try {
        const endpoint = action === 'increment' 
          ? `${state.baseUrl}/api/habits/${habitId}/increment`
          : `${state.baseUrl}/api/habits/${habitId}/decrement`;
        const result = await fetchJSON(endpoint, { method: 'POST' });
        if (result && result.achievement_unlocked && result.habit_title) {
          showAchievementPopup(result.habit_title);
        }
        loadAll();
      } catch (err) {
        if (h) {
          h.today_count = prevToday;
          h.total_completions = prevTotal;
          renderHabits(state.cache.habits);
        }
        console.error('Ошибка счётчика:', err);
        if (tg) tg.showAlert('Ошибка при обновлении');
      }
    });
  });
  root.querySelectorAll('.habit-reminder-toggle').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const habitId = parseInt(btn.dataset.habitId);
      const enabled = btn.dataset.enabled !== "1";
      try {
        await fetchJSON(state.baseUrl + "/api/habits/" + habitId + "/reminder", {
          method: "PUT",
          body: JSON.stringify({ enabled: enabled })
        });
        btn.dataset.enabled = enabled ? "1" : "0";
        var icon = btn.querySelector(".material-symbols-outlined");
        if (icon) icon.textContent = enabled ? "notifications" : "notifications_off";
        btn.setAttribute("aria-label", enabled ? "Напоминания вкл" : "Напоминания выкл");
        btn.setAttribute("title", enabled ? "Напоминания вкл" : "Напоминания выкл");
      } catch (err) {
        console.error("Ошибка настройки напоминаний:", err);
        if (tg) tg.showAlert("Не удалось изменить настройку");
      }
    });
  });
}

var analyticsChartInstance = null;

function formatShortDate(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  var day = d.getDate();
  var month = d.toLocaleDateString("ru-RU", { month: "short" }).replace(".", "");
  return day + " " + month;
}

function renderAnalytics(data) {
  var root = $("#analytics-view");
  if (!root) return;

  if (analyticsChartInstance) {
    analyticsChartInstance.destroy();
    analyticsChartInstance = null;
  }

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

  var isDark = document.documentElement.getAttribute("data-theme") === "dark" || !document.documentElement.getAttribute("data-theme");
  var textColor = isDark ? "rgba(226, 232, 240, 0.9)" : "rgba(30, 41, 59, 0.9)";
  var gridColor = isDark ? "rgba(148, 163, 184, 0.2)" : "rgba(148, 163, 184, 0.3)";

  var periodTabsHtml = "<div class=\"analytics-period-tabs\">" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "week" ? " active" : "") + "\" data-period=\"week\">Неделя</button>" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "month" ? " active" : "") + "\" data-period=\"month\">Месяц</button>" +
    "<button type=\"button\" class=\"analytics-period-btn" + (period === "all" ? " active" : "") + "\" data-period=\"all\">Всё</button>" +
    "</div>";

  var summaryHtml = "<div class=\"analytics-summary-cards\">" +
    "<div class=\"analytics-card\">" +
    "<span class=\"analytics-card-icon\" aria-hidden=\"true\"><span class=\"material-symbols-outlined\">flag</span></span>" +
    "<div class=\"analytics-card-body\"><span class=\"analytics-card-value\">" + missionsCompleted + "/" + missionsTotal + "</span><span class=\"analytics-card-label\">Миссии</span><div class=\"analytics-card-progress\"><div class=\"analytics-card-progress-fill\" style=\"width:" + (missionsTotal > 0 ? Math.min(100, (missionsProgress || 0)) : 0) + "%\"></div></div></div>" +
    "</div>" +
    "<div class=\"analytics-card\">" +
    "<span class=\"analytics-card-icon\" aria-hidden=\"true\"><span class=\"material-symbols-outlined\">track_changes</span></span>" +
    "<div class=\"analytics-card-body\"><span class=\"analytics-card-value\">" + goalsCompleted + "/" + goalsTotal + "</span><span class=\"analytics-card-label\">Цели</span><div class=\"analytics-card-progress\"><div class=\"analytics-card-progress-fill\" style=\"width:" + (goalsRate || 0) + "%\"></div></div></div>" +
    "</div>" +
    "<div class=\"analytics-card\">" +
    "<span class=\"analytics-card-icon\" aria-hidden=\"true\"><span class=\"material-symbols-outlined\">repeat</span></span>" +
    "<div class=\"analytics-card-body\"><span class=\"analytics-card-value\">" + habitsCompletions + "</span><span class=\"analytics-card-label\">Привычки " + (streak > 0 ? "· серия " + streak + " дн." : "") + "</span><div class=\"analytics-card-progress\"><div class=\"analytics-card-progress-fill\" style=\"width:" + Math.min(100, (streak / 21) * 100) + "%\"></div></div></div>" +
    "</div>" +
    "</div>";

  var chartPlaceholder = labels.length === 0 ? "<div class=\"analytics-chart-empty\">Нет данных за выбранный период</div>" : "";
  var chartContainerHtml = "<div class=\"analytics-chart-section\">" +
    "<div class=\"analytics-chart-header\">" +
    "<span class=\"analytics-chart-title\">Выполнения привычек по дням</span>" +
    periodTabsHtml +
    "</div>" +
    "<div class=\"analytics-chart-canvas-wrap\">" +
    chartPlaceholder +
    "<canvas id=\"analytics-habit-chart\" role=\"img\" aria-label=\"График выполнений привычек по дням\" style=\"" + (labels.length === 0 ? "display:none" : "") + "\"></canvas>" +
    "</div>" +
    "</div>";

  root.innerHTML = summaryHtml + chartContainerHtml;

  if (typeof Chart !== "undefined" && labels.length > 0) {
    var ctx = document.getElementById("analytics-habit-chart");
    if (ctx) {
      var shortLabels = labels.map(function(l) { return formatShortDate(l); });
      analyticsChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
          labels: shortLabels,
          datasets: [{
            label: "Выполнений",
            data: values,
            backgroundColor: "rgba(124, 58, 237, 0.6)",
            borderColor: "rgba(124, 58, 237, 1)",
            borderWidth: 1,
            borderRadius: 6,
            borderSkipped: false,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { intersect: false, mode: "index" },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: isDark ? "rgba(30, 41, 59, 0.95)" : "rgba(255,255,255,0.95)",
              titleColor: textColor,
              bodyColor: textColor,
              padding: 12,
              cornerRadius: 8,
              callbacks: {
                title: function(items) { return items[0] && items[0].label ? items[0].label : ""; },
                label: function(ctx) { return "Выполнений: " + (ctx.raw || 0); }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                color: "rgba(148, 163, 184, 0.8)",
                maxRotation: 45,
                minRotation: 0,
                maxTicksLimit: 12,
                font: { size: 11 }
              }
            },
            y: {
              beginAtZero: true,
              grid: { color: gridColor },
              ticks: {
                color: "rgba(148, 163, 184, 0.8)",
                stepSize: 1,
                font: { size: 11 }
              }
            }
          }
        }
      });
    }
  }
}

function bmi(weightKg, heightM) {
  if (!weightKg || !heightM || heightM <= 0) return null;
  return Math.round((weightKg / (heightM * heightM)) * 10) / 10;
}
/** Категория ИМТ по ВОЗ: подпись, в норме ли, CSS-класс */
function bmiCategory(bmiVal) {
  if (bmiVal == null || isNaN(bmiVal)) return null;
  if (bmiVal < 18.5) return { label: "Недостаток веса", inNorm: false, className: "bmi-under" };
  if (bmiVal <= 24.9) return { label: "Норма", inNorm: true, className: "bmi-normal" };
  if (bmiVal <= 29.9) return { label: "Избыточный вес", inNorm: false, className: "bmi-over" };
  return { label: "Ожирение", inNorm: false, className: "bmi-obese" };
}
/** Идеальный диапазон веса по ВОЗ (ИМТ 18.5–24.9), кг */
function idealWeightRange(heightM) {
  if (!heightM || heightM <= 0) return null;
  var minKg = Math.round(18.5 * heightM * heightM * 10) / 10;
  var maxKg = Math.round(24.9 * heightM * heightM * 10) / 10;
  return { minKg: minKg, maxKg: maxKg };
}
function devineIdealKg(gender, heightCm) {
  if (!heightCm || heightCm <= 0) return null;
  var heightIn = heightCm / 2.54;
  if (heightIn < 60) heightIn = 60;
  return gender === "f" ? 45.5 + 2.3 * (heightIn - 60) : 50 + 2.3 * (heightIn - 60);
}

/** Современная шкала ИМТ: карточка с цифрой + горизонтальная шкала с маркером */
function bmiGaugeHtml(bmiVal, opts) {
  opts = opts || {};
  var bmiMin = 14;
  var bmiMax = 40;
  var cat = bmiVal != null && !isNaN(bmiVal) ? bmiCategory(bmiVal) : null;
  var val = bmiVal != null && !isNaN(bmiVal) ? Math.max(bmiMin, Math.min(bmiMax, bmiVal)) : 22;
  var t = (val - bmiMin) / (bmiMax - bmiMin);
  t = Math.max(0, Math.min(1, t));
  var markerLeft = t * 100;
  var catClass = cat && cat.className ? " bmi-" + cat.className : "";
  var catLabel = cat ? escapeHtml(cat.label) : "—";
  var valText = bmiVal != null && !isNaN(bmiVal) ? String(bmiVal) : "—";
  return "<div class=\"bmi-card-modern\">" +
    "<div class=\"bmi-card-value" + catClass + "\">" + valText + "</div>" +
    "<span class=\"bmi-card-label" + catClass + "\">" + catLabel + "</span>" +
    "<div class=\"bmi-scale-wrap\">" +
    "<div class=\"bmi-scale-bar\">" +
    "<span class=\"bmi-scale-seg bmi-under\"></span>" +
    "<span class=\"bmi-scale-seg bmi-normal\"></span>" +
    "<span class=\"bmi-scale-seg bmi-over\"></span>" +
    "<span class=\"bmi-scale-seg bmi-obese\"></span>" +
    "<span class=\"bmi-scale-marker\" style=\"left:" + markerLeft + "%\"></span>" +
    "</div>" +
    "<div class=\"bmi-scale-labels\">" +
    "<span>14</span><span>18.5</span><span>25</span><span>30</span><span>40</span>" +
    "</div>" +
    "</div>" +
    "</div>";
}

function drawWeightChart(container, data, targetWeight, opts) {
  opts = opts || {};
  if (!container || !Array.isArray(data)) return;
  var w = opts.width || 280;
  var h = opts.height || 120;
  var pad = { top: 8, right: 8, bottom: 20, left: 36 };
  var vals = data.map(function(d) { return Number(d.weight); });
  var minW = Math.min.apply(null, vals.concat(targetWeight ? [targetWeight] : [])) - 2;
  var maxW = Math.max.apply(null, vals.concat(targetWeight ? [targetWeight] : [])) + 2;
  if (minW >= maxW) { minW = minW - 5; maxW = maxW + 5; }
  var xs = data.map(function(_, i) { return pad.left + (i / Math.max(1, data.length - 1)) * (w - pad.left - pad.right); });
  var scaleY = function(v) { return pad.top + (1 - (v - minW) / (maxW - minW)) * (h - pad.top - pad.bottom); };
  var pathD = data.map(function(d, i) { return (i === 0 ? "M" : "L") + xs[i] + "," + scaleY(d.weight); }).join(" ");
  var targetY = targetWeight != null ? scaleY(targetWeight) : null;
  var svg = "<svg width=\"" + w + "\" height=\"" + h + "\" class=\"weight-chart-svg\">";
  if (targetY != null) {
    svg += "<line x1=\"" + pad.left + "\" y1=\"" + targetY + "\" x2=\"" + (w - pad.right) + "\" y2=\"" + targetY + "\" class=\"weight-chart-goal\" stroke-dasharray=\"4,2\"/>";
    svg += "<text x=\"" + (w - pad.right - 2) + "\" y=\"" + (targetY - 4) + "\" class=\"weight-chart-goal-label\" text-anchor=\"end\">Цель " + targetWeight + " кг</text>";
  }
  svg += "<path d=\"" + pathD + "\" class=\"weight-chart-line\" fill=\"none\"/>";
  data.forEach(function(d, i) {
    svg += "<circle cx=\"" + xs[i] + "\" cy=\"" + scaleY(d.weight) + "\" r=\"3\" class=\"weight-chart-dot\"/>";
  });
  svg += "</svg>";
  container.innerHTML = svg;
}

function renderProfile() {
  const root = $("#profile-view");
  if (!root) return;
  var p = state.cache.profile || {};
  var gender = (p.gender || "").trim() || "";
  var displayName = (p.display_name || "").trim();
  var firstName = (p.first_name || "").trim();
  var lastName = (p.last_name || "").trim();
  var name = displayName || [firstName, lastName].filter(Boolean).join(" ").trim() || "Пользователь";
  var initial = (name && name.charAt(0)) ? name.charAt(0).toUpperCase() : "?";
  var avatarBase = gender === "f" ? "ona" : (gender === "m" ? "on" : null);
  var avatarImg = avatarBase ? "images/" + avatarBase + ".png?t=" + Date.now() : null;
  var username = (p.username && String(p.username).trim()) ? "@" + escapeHtml(String(p.username).trim()) : "";
  var weight = p.weight != null ? Number(p.weight) : null;
  var height = p.height != null ? Number(p.height) : null;
  var age = p.age != null ? Number(p.age) : null;
  var targetWeight = p.target_weight != null ? Number(p.target_weight) : null;
  var weightHistory = state.cache.weightHistory || [];
  const missions = state.cache.missions || [];
  const goals = state.cache.goals || [];
  const habits = state.cache.habits || [];
  const a = state.cache.analytics || {};
  const missionsTotal = parseInt(a?.missions?.total || 0) || missions.length;
  const goalsTotal = parseInt(a?.goals?.total || 0) || goals.length;
  const habitsTotal = parseInt(a?.habits?.total || 0) || habits.length;

  var currentWeight = weightHistory.length ? weightHistory[weightHistory.length - 1].weight : weight;
  var weightForBmi = currentWeight != null ? currentWeight : weight;
  var heightM = height ? height / 100 : null;
  var bmiVal = bmi(weightForBmi, heightM);
  var bmiCat = bmiVal != null ? bmiCategory(bmiVal) : null;
  var idealRange = heightM ? idealWeightRange(heightM) : null;
  var idealKg = devineIdealKg(gender, height);
  var idealBmi = idealKg != null && heightM ? bmi(idealKg, heightM) : null;

  var lastWater = state.lastWaterResult || {};
  var selectedCity = (p.city || "").trim() ? escapeHtml((p.city || "").trim()) : "";
  var selectedCountry = (p.country || "").trim() ? escapeHtml((p.country || "").trim()) : "";

  if (state.profileSubTab === "bmi-water") state.profileSubTab = "bmi";
  if (!["general", "person", "bmi", "water", "stats", "achievements"].includes(state.profileSubTab)) state.profileSubTab = "general";
  var hasWeightData = (currentWeight != null || weight) && heightM;
  var bmiWidgetHtml = hasWeightData ? "<div class=\"profile-widget profile-widget-bmi\"><div class=\"profile-widget-title\">ИМТ</div><div class=\"profile-widget-bmi-value\">ИМТ: " + (bmiVal != null ? bmiVal : "—") + (bmiCat ? " — " + escapeHtml(bmiCat.label) : "") + (idealRange ? " · Диапазон нормы: " + idealRange.minKg + "–" + idealRange.maxKg + " кг" : "") + "</div></div>" : "";
  var weightWidgetHtml = (currentWeight != null || weightHistory.length || weight != null) ? "<div class=\"profile-widget profile-widget-weight\" id=\"profile-weight-widget-card\"><div class=\"weight-card-header\"><span class=\"weight-card-title\">Вес</span><span class=\"weight-card-date\">" + new Date().toLocaleDateString("ru-RU", { day: "numeric", month: "short", weekday: "short" }) + "</span></div><div class=\"weight-card-value\">" + (currentWeight != null ? currentWeight : weight).toFixed(1) + " кг</div>" + (weightHistory.length ? "<div class=\"weight-card-trend\"><span class=\"weight-trend-link\" id=\"weight-trend-link\">Тенденции &gt;</span><div id=\"profile-weight-chart-mini\" class=\"weight-chart-mini\"></div></div>" : "") + "</div>" : "";
  var stepsWidgetHtml = "";
  if (state.googleFitConnected) {
    var stepsVal = state.googleFitSteps != null ? state.googleFitSteps + " шагов сегодня" : "Загрузка…";
    stepsWidgetHtml = "<div class=\"profile-widget profile-widget-steps\"><div class=\"profile-widget-title\">Шаги (Google Fit)</div><div class=\"profile-widget-bmi-value\" id=\"profile-steps-value\">" + stepsVal + "</div>" + (state.googleFitSteps == null ? "<button type=\"button\" class=\"link-btn profile-steps-refresh\" id=\"profile-steps-refresh\">Обновить</button>" : "") + "</div>";
  }
  var ageText = age != null ? age + " лет" : "";
  var generalChecked = state.profileSubTab === "general" ? " checked" : "";
  var personChecked = state.profileSubTab === "person" ? " checked" : "";
  var bmiChecked = state.profileSubTab === "bmi" ? " checked" : "";
  var waterChecked = state.profileSubTab === "water" ? " checked" : "";
  var statsChecked = state.profileSubTab === "stats" ? " checked" : "";
  var achievementsChecked = state.profileSubTab === "achievements" ? " checked" : "";

  var contentPerson = `
    <div class="profile-form-section">
      <h3 class="profile-section-title">Информация о пользователе</h3>
      <div class="profile-edit-name">
        <label class="profile-edit-label">Как к вам обращаться?</label>
        <input type="text" id="profile-display-name-input" class="input" placeholder="${escapeHtml(name)}" value="${escapeHtml(displayName)}" maxlength="64" />
      </div>
      <label class="profile-field-label">Пол</label>
      <div class="profile-gender-cards">
        <button type="button" class="profile-gender-card ${gender === "m" ? "selected" : ""}" data-gender="m" aria-label="Мужской"><span class="material-symbols-outlined profile-gender-icon profile-gender-icon-m">face</span><span>Мужской</span></button>
        <button type="button" class="profile-gender-card ${gender === "f" ? "selected" : ""}" data-gender="f" aria-label="Женский"><span class="material-symbols-outlined profile-gender-icon profile-gender-icon-f">face_3</span><span>Женский</span></button>
      </div>
      <label class="profile-field-label">Рост (см)</label>
      <div class="profile-height-ruler-block">
        <div class="profile-height-display">
          <span id="profile-height-value" class="profile-height-value">${height != null ? height : "—"}</span><span class="profile-height-unit"> см</span>
        </div>
        <div class="profile-ruler-container">
          <div class="profile-ruler-track">
            <div class="profile-ruler-scale" id="profile-ruler-scale"></div>
          </div>
          <div class="profile-height-slider-wrap">
            <input type="range" id="profile-height-slider" class="profile-height-slider" min="100" max="220" value="${height != null && height >= 100 && height <= 220 ? height : 165}" step="1" aria-label="Рост в см" />
            <span class="profile-height-slider-hint">Перемещайте ползунок</span>
          </div>
        </div>
        <div class="profile-height-presets">
          <button type="button" class="profile-height-preset-btn" data-height="150">150</button>
          <button type="button" class="profile-height-preset-btn" data-height="160">160</button>
          <button type="button" class="profile-height-preset-btn" data-height="170">170</button>
          <button type="button" class="profile-height-preset-btn" data-height="180">180</button>
          <button type="button" class="profile-height-preset-btn" data-height="190">190</button>
        </div>
      </div>
      <input type="hidden" id="profile-height" value="${height != null ? height : ""}" />
      <div class="profile-row-two">
        <div class="profile-stepper-block">
          <label class="profile-field-label">Возраст</label>
          <div class="profile-stepper-card">
            <span class="profile-stepper-value" id="profile-age-value">${age != null ? age : "—"}</span>
            <div class="profile-stepper-btns">
              <button type="button" class="profile-stepper-btn profile-stepper-btn-icon" id="profile-age-minus" aria-label="Уменьшить"><span class="material-symbols-outlined profile-stepper-icon profile-stepper-icon-down">arrow_drop_down_circle</span></button>
              <button type="button" class="profile-stepper-btn profile-stepper-btn-icon" id="profile-age-plus" aria-label="Увеличить"><span class="material-symbols-outlined profile-stepper-icon profile-stepper-icon-up">arrow_drop_down_circle</span></button>
            </div>
          </div>
        </div>
        <div class="profile-stepper-block">
          <label class="profile-field-label">Вес (кг)</label>
          <div class="profile-stepper-card profile-stepper-card-weight">
            <span class="profile-stepper-value" id="profile-weight-value">${weight != null ? weight : "—"}</span>
            <div class="profile-stepper-btns profile-stepper-btns-weight">
              <button type="button" class="profile-stepper-btn profile-stepper-btn-icon" id="profile-weight-minus" aria-label="Уменьшить"><span class="material-symbols-outlined profile-stepper-icon profile-stepper-icon-down">arrow_drop_down_circle</span></button>
              <button type="button" class="profile-stepper-btn profile-stepper-btn-icon" id="profile-weight-plus" aria-label="Увеличить"><span class="material-symbols-outlined profile-stepper-icon profile-stepper-icon-up">arrow_drop_down_circle</span></button>
            </div>
            <button type="button" class="profile-add-weight-inline" id="profile-add-weight-btn">+ Добавить запись веса</button>
          </div>
        </div>
      </div>
      <input type="hidden" id="profile-age-input" value="${age != null ? age : ""}" />
      <input type="hidden" id="profile-weight-input" value="${weight != null ? weight : ""}" />
      <label class="profile-field-label">Целевой вес (кг)</label>
      <input type="number" id="profile-target-weight" class="input" step="0.1" min="0" placeholder="—" value="${targetWeight != null ? targetWeight : ""}" />
    </div>
    <div class="profile-save-block">
      <button type="button" class="primary-btn profile-save-fields-btn">Сохранить изменения</button>
    </div>
  `;

  var contentBmi = hasWeightData ? `
    <div class="profile-bmi-page">
      <div class="profile-bmi-page-header">
        <h3 class="profile-bmi-page-title">Калькулятор ИМТ</h3>
        <button type="button" class="icon-btn profile-help-btn profile-bmi-help" aria-label="Справка ИМТ" title="Как считается ИМТ">?</button>
      </div>
      <div class="profile-bmi-gauge-section">
        <p class="profile-bmi-section-label">Ваш индекс массы тела</p>
        <div id="profile-bmi-gauge" class="profile-bmi-gauge"></div>
      </div>
      <div class="profile-bmi-details-section">
        <p class="profile-bmi-section-label">Подробные результаты</p>
        <div class="profile-bmi-details-card">
          <p class="profile-bmi-details-text">${bmiVal != null && bmiCat ? "По введённым данным ваш индекс массы тела (ИМТ) составляет <strong class=\"bmi-detail-value\">" + bmiVal + "</strong>, что соответствует категории <strong class=\"bmi-detail-cat bmi-" + (bmiCat.className || "") + "\">" + escapeHtml(bmiCat.label) + "</strong> для вашего роста." : "Укажите вес и рост во вкладке «Человек»."}</p>
          <div class="profile-bmi-categories-table">
            <div class="profile-bmi-cat-row"><span class="profile-bmi-cat-bar bmi-under"></span><span>Недостаток веса</span><span>&lt; 18.5</span></div>
            <div class="profile-bmi-cat-row"><span class="profile-bmi-cat-bar bmi-normal"></span><span>Норма</span><span>18.5 – 24.9</span></div>
            <div class="profile-bmi-cat-row"><span class="profile-bmi-cat-bar bmi-over"></span><span>Избыточный вес</span><span>24.9 – 29.9</span></div>
            <div class="profile-bmi-cat-row"><span class="profile-bmi-cat-bar bmi-obese"></span><span>Ожирение</span><span>≥ 30</span></div>
          </div>
        </div>
      </div>
      <button type="button" class="primary-btn profile-edit-data-btn" id="profile-edit-data-btn">◀ Редактировать данные</button>
    </div>
  ` : "<p class=\"profile-hint\">Укажите вес и рост во вкладке «Человек» для расчёта ИМТ.</p>";

  var savedCityLabel = (selectedCity || selectedCountry) ? (selectedCity + (selectedCountry ? ", " + selectedCountry : "") + ((p.country_code || "").trim() ? " (" + escapeHtml((p.country_code || "").trim().toUpperCase()) + ")" : "")) : "";
  var contentWater = `
    <div class="profile-water-block profile-water-block-standalone">
      <div class="profile-water-block-header">
        <span>Норма воды в день</span>
        <button type="button" class="icon-btn profile-water-help-btn" id="profile-water-help-btn" aria-label="Справка" title="Как считается норма воды">?</button>
      </div>
      ${lastWater.liters != null ? `
      <div class="profile-water-result">
        <div class="profile-water-value">${lastWater.liters} л</div>
        <div class="profile-water-meta">По данным: ${lastWater.city ? escapeHtml(lastWater.city) : "—"}${lastWater.country ? ", " + escapeHtml(lastWater.country) : ""}${lastWater.temp != null ? "; темп. " + lastWater.temp + " °C" : ""}${lastWater.humidity != null ? "; влажность " + lastWater.humidity + "%" : ""}</div>
      </div>
      ` : savedCityLabel ? "<p class=\"profile-water-saved-city\">Город: " + savedCityLabel + "</p><p class=\"profile-water-empty\">Нажмите «Рассчитать» для нормы воды.</p>" : "<p class=\"profile-water-empty\">Нажмите «Рассчитать» для нормы воды.</p>"}
      <div class="profile-water-actions">
        <button type="button" class="secondary-btn profile-select-city-btn" id="profile-select-city-btn">${savedCityLabel ? "Изменить город" : "Выбрать город"}</button>
        <button type="button" class="primary-btn profile-water-calc-btn" id="profile-water-calc-btn">Рассчитать</button>
      </div>
    </div>
  `;

  var contentStats = `
    <div class="profile-stats">
      <div class="profile-stat-row"><span>Миссий</span><span>${missionsTotal}</span></div>
      <div class="profile-stat-row"><span>Целей</span><span>${goalsTotal}</span></div>
      <div class="profile-stat-row"><span>Привычек</span><span>${habitsTotal}</span></div>
    </div>
  `;

  var achievements = state.cache.achievements || [];
  var achievedCount = achievements.filter(function(a) { return a.achieved; }).length;
  var contentAchievements = `
    <div class="profile-achievements">
      <h3 class="profile-section-title">21 день подряд</h3>
      <p class="profile-achievements-hint">Достижение за 21 день выполнения привычки без пропусков.</p>
      <div class="achievements-grid">
        ${achievements.length ? achievements.map(function(a) {
          var cls = a.achieved ? "achievement-badge achieved" : "achievement-badge locked";
          var icon = a.achieved ? "military_tech" : "lock";
          return "<div class=\"" + cls + "\"><span class=\"material-symbols-outlined achievement-icon\">" + icon + "</span><span class=\"achievement-title\">" + escapeHtml(a.title || "Привычка") + "</span><span class=\"achievement-streak\">" + a.streak + " дн.</span></div>";
        }).join("") : "<p class=\"profile-hint\">Нет привычек. Добавьте привычки на вкладке «Привычки».</p>"}
      </div>
      ${achievedCount > 0 ? "<p class=\"achievements-summary\">Получено: " + achievedCount + " из " + achievements.length + "</p>" : ""}
    </div>
  `;

  var contentGeneral = (bmiWidgetHtml || weightWidgetHtml || stepsWidgetHtml) ? "<div class=\"profile-widgets-row\">" + bmiWidgetHtml + weightWidgetHtml + stepsWidgetHtml + "</div>" : "<p class=\"profile-hint\">Укажите вес и рост во вкладке «Человек», чтобы здесь отображались виджеты ИМТ и веса. Подключите Google Fit в настройках для отображения шагов.</p>";

  var subPageTitles = { person: "Человек", bmi: "ИМТ", water: "Вода", stats: "Статистика", achievements: "Достижения" };
  var subPageContent = { person: contentPerson, bmi: contentBmi, water: contentWater, stats: contentStats, achievements: contentAchievements };

  if (state.profileSubTab === "general") {
    root.innerHTML = `
    <div class="profile-main">
      <div class="profile-content-wrapper">
        <div class="profile-tabs-container">
          <div id="profile-identity" class="profile-identity">
            <div class="profile-identity-content">
              <div class="profile-avatar${avatarImg ? " has-avatar-img" : ""}">${avatarImg ? "<img src=\"" + avatarImg + "\" alt=\"\" class=\"profile-avatar-img\" data-jpg=\"images/" + avatarBase + ".jpg\" onerror=\"var i=this;if(i.dataset.jpg&&i.src.indexOf('.png')!==-1){i.src=i.dataset.jpg;i.onerror=function(){i.style.display='none';var s=i.nextElementSibling;if(s)s.style.display='flex';}}else{i.style.display='none';var s=i.nextElementSibling;if(s)s.style.display='flex';}\"><span class=\"profile-avatar-fallback\" style=\"display:none\">" + escapeHtml(initial) + "</span>" : "<span class=\"profile-avatar-fallback\">" + escapeHtml(initial) + "</span>"}</div>
              <h2 class="profile-name">${escapeHtml(name)}</h2>
              <p class="profile-age">${escapeHtml(ageText)}</p>
            </div>
          </div>
          <div class="vertical-tabs">
            <span class="profile-subtab profile-subtab-current"><span class="material-symbols-outlined profile-tab-icon">dashboard</span> Общие</span>
            <button type="button" class="profile-subtab profile-subtab-link" data-profile-tab="person"><span class="material-symbols-outlined profile-tab-icon">person</span> Человек</button>
            <button type="button" class="profile-subtab profile-subtab-link" data-profile-tab="bmi"><span class="material-symbols-outlined profile-tab-icon">monitor_weight</span> ИМТ</button>
            <button type="button" class="profile-subtab profile-subtab-link" data-profile-tab="water"><span class="material-symbols-outlined profile-tab-icon">water_drop</span> Вода</button>
            <button type="button" class="profile-subtab profile-subtab-link" data-profile-tab="stats"><span class="material-symbols-outlined profile-tab-icon">bar_chart</span> Статистика</button>
            <button type="button" class="profile-subtab profile-subtab-link" data-profile-tab="achievements"><span class="material-symbols-outlined profile-tab-icon">military_tech</span> Достижения</button>
          </div>
        </div>
        <div class="profile-content-area" id="profile-content-area">
          <section id="content-general" class="profile-tab-content">${contentGeneral}</section>
        </div>
      </div>
    </div>
  `;
    root.querySelectorAll(".profile-subtab-link").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var tab = btn.dataset.profileTab;
        if (tab) { state.profileSubTab = tab; renderProfile(); }
      });
    });
  } else {
    var currentTitle = subPageTitles[state.profileSubTab] || "";
    var currentContent = subPageContent[state.profileSubTab] || "";
    root.innerHTML = `
    <div class="profile-main profile-subpage">
      <header class="profile-subpage-header">
        <button type="button" class="profile-back-btn" id="profile-back-btn" aria-label="Назад"><span class="material-symbols-outlined">arrow_back</span></button>
        <h2 class="profile-subpage-title">${escapeHtml(currentTitle)}</h2>
      </header>
      <div class="profile-content-area profile-subpage-content" id="profile-content-area">
        ${currentContent}
      </div>
    </div>
  `;
    var backBtn = document.getElementById("profile-back-btn");
    if (backBtn) backBtn.addEventListener("click", function() { state.profileSubTab = "general"; renderProfile(); });
  }

  var gaugeEl = document.getElementById("profile-bmi-gauge");
  if (gaugeEl && hasWeightData) gaugeEl.innerHTML = bmiGaugeHtml(bmiVal, {});

  if (weightHistory.length) {
    var miniChart = root.querySelector("#profile-weight-chart-mini");
    if (miniChart) drawWeightChart(miniChart, weightHistory, targetWeight, { width: 260, height: 80 });
    var trendLink = root.querySelector("#weight-trend-link");
    if (trendLink) trendLink.addEventListener("click", function(e) { e.preventDefault(); openWeightTrendOverlay(); });
    var weightCard = root.querySelector("#profile-weight-widget-card");
    if (weightCard) weightCard.addEventListener("click", function(e) { if (!e.target.closest(".weight-trend-link")) openWeightTrendOverlay(); });
  }

  var addWeightBtn = root.querySelector("#profile-add-weight-btn");
  if (addWeightBtn) addWeightBtn.addEventListener("click", function() { openAddWeightDialog(); });
  var editDataBtn = document.getElementById("profile-edit-data-btn");
  if (editDataBtn) editDataBtn.addEventListener("click", function() { state.profileSubTab = "person"; renderProfile(); });
  $all(".profile-gender-card").forEach(function(btn) {
    btn.addEventListener("click", function() {
      $all(".profile-gender-card").forEach(function(b) { b.classList.remove("selected"); });
      btn.classList.add("selected");
    });
  });
  var ageInput = document.getElementById("profile-age-input");
  var ageValueEl = document.getElementById("profile-age-value");
  var ageMinus = document.getElementById("profile-age-minus");
  var agePlus = document.getElementById("profile-age-plus");
  if (ageInput && ageValueEl) {
    function updateAge(v) {
      var n = parseInt(v, 10);
      if (isNaN(n)) n = 0;
      n = Math.max(0, Math.min(150, n));
      ageInput.value = n;
      ageValueEl.textContent = n || "—";
    }
    if (ageMinus) ageMinus.addEventListener("click", function() { updateAge(parseInt(ageInput.value, 10) - 1); });
    if (agePlus) agePlus.addEventListener("click", function() { updateAge(parseInt(ageInput.value, 10) + 1); });
  }
  var weightInput = document.getElementById("profile-weight-input");
  var weightValueEl = document.getElementById("profile-weight-value");
  var weightMinus = document.getElementById("profile-weight-minus");
  var weightPlus = document.getElementById("profile-weight-plus");
  if (weightInput && weightValueEl) {
    function updateWeight(v) {
      var n = parseFloat(v);
      if (isNaN(n)) n = 0;
      n = Math.max(0, Math.min(300, Math.round(n * 10) / 10));
      weightInput.value = n;
      weightValueEl.textContent = n ? n : "—";
    }
    if (weightMinus) weightMinus.addEventListener("click", function() { updateWeight(parseFloat(weightInput.value || 0) - 0.5); });
    if (weightPlus) weightPlus.addEventListener("click", function() { updateWeight(parseFloat(weightInput.value || 0) + 0.5); });
  }
  var saveFieldsBtn = root.querySelector(".profile-save-fields-btn");
  var inputNameEl2 = root.querySelector("#profile-display-name-input");
  if (saveFieldsBtn) {
    saveFieldsBtn.addEventListener("click", async function() {
      var dn = (inputNameEl2 && inputNameEl2.value || "").trim();
      var gEl = root.querySelector(".profile-gender-card.selected");
      var g = gEl ? gEl.dataset.gender || null : null;
      var h = parseFloat(root.querySelector("#profile-height") && root.querySelector("#profile-height").value);
      var ag = parseInt(ageInput && ageInput.value, 10);
      var w = parseFloat(weightInput && weightInput.value);
      var tw = parseFloat(root.querySelector("#profile-target-weight") && root.querySelector("#profile-target-weight").value);
      try {
        await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/profile", {
          method: "PUT",
          body: JSON.stringify({
            display_name: dn || undefined,
            gender: g || undefined,
            weight: isNaN(w) || w <= 0 ? undefined : w,
            height: isNaN(h) || h <= 0 ? undefined : h,
            age: isNaN(ag) || ag <= 0 ? undefined : ag,
            target_weight: isNaN(tw) || tw <= 0 ? undefined : tw
          })
        });
        if (g) state.cache.profile = Object.assign({}, state.cache.profile || {}, { gender: g });
        state.profileSubTab = "general";
        await loadAll();
        if (tg) tg.showAlert("Профиль сохранён");
      } catch (err) {
        if (tg) tg.showAlert("Не удалось сохранить");
      }
    });
  }
  var waterHelpBtn = root.querySelector("#profile-water-help-btn");
  if (waterHelpBtn) waterHelpBtn.addEventListener("click", function() { showWaterHelp(); });
  var selectCityBtn = root.querySelector("#profile-select-city-btn");
  if (selectCityBtn) selectCityBtn.addEventListener("click", function() { openCityPicker(); });
  var waterCalcBtn = root.querySelector("#profile-water-calc-btn");
  if (waterCalcBtn) waterCalcBtn.addEventListener("click", function() { openWaterFlow(); });
  initHeightRuler(root);
}

function initHeightRuler(container) {
  var scaleEl = document.getElementById("profile-ruler-scale");
  var sliderEl = document.getElementById("profile-height-slider");
  var valueEl = document.getElementById("profile-height-value");
  var hiddenEl = document.getElementById("profile-height");
  var trackEl = container ? container.querySelector(".profile-ruler-track") : document.querySelector(".profile-ruler-track");
  if (!scaleEl || !sliderEl || !valueEl || !hiddenEl || !trackEl) return;
  var minH = 100;
  var maxH = 220;
  var pixelsPerCm = 10;
  function buildScale() {
    scaleEl.innerHTML = "";
    for (var i = minH; i <= maxH; i++) {
      var mark = document.createElement("div");
      mark.className = "profile-cm-mark";
      if (i % 10 === 0) mark.classList.add("tall");
      else if (i % 5 === 0) mark.classList.add("medium");
      else mark.classList.add("short");
      if (i % 10 === 0) {
        var num = document.createElement("div");
        num.className = "profile-cm-number";
        num.textContent = i;
        mark.appendChild(num);
      }
      scaleEl.appendChild(mark);
    }
  }
  function updateRulerPosition(val) {
    var v = parseInt(val, 10);
    if (isNaN(v)) v = 165;
    v = Math.max(minH, Math.min(maxH, v));
    var trackW = trackEl.offsetWidth || 280;
    var offset = (trackW / 2) - (v - minH) * pixelsPerCm;
    scaleEl.style.transform = "translateX(" + offset + "px)";
  }
  function syncFromSlider() {
    var v = parseInt(sliderEl.value, 10);
    valueEl.textContent = v;
    hiddenEl.value = v;
    updateRulerPosition(v);
  }
  buildScale();
  var initialVal = parseInt(sliderEl.value, 10);
  if (isNaN(initialVal)) initialVal = 165;
  valueEl.textContent = initialVal;
  hiddenEl.value = initialVal;
  updateRulerPosition(initialVal);
  sliderEl.addEventListener("input", syncFromSlider);
  $all(".profile-height-preset-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var h = parseInt(btn.dataset.height, 10);
      if (isNaN(h)) return;
      sliderEl.value = h;
      syncFromSlider();
    });
  });
}

async function openWeightTrendOverlay() {
  var overlay = $("#weight-trend-overlay");
  var periodSelect = $("#weight-trend-period");
  var chartEl = $("#weight-trend-chart");
  if (!overlay || !chartEl) return;
  overlay.classList.remove("hidden");
  var period = (periodSelect && periodSelect.value) || "week";
  try {
    var res = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/weight-history?period=" + period);
    var data = (res && res.data) ? res.data : [];
    var targetWeight = (state.cache.profile && state.cache.profile.target_weight != null) ? Number(state.cache.profile.target_weight) : null;
    drawWeightChart(chartEl, data, targetWeight, { width: 320, height: 220 });
  } catch (e) {
    chartEl.innerHTML = "<p class=\"weight-trend-error\">Не удалось загрузить данные</p>";
  }
}
function closeWeightTrendOverlay() {
  var overlay = $("#weight-trend-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function openAddWeightDialog() {
  var today = new Date().toISOString().slice(0, 10);
  var extra = "<label>Дата</label><input type=\"date\" id=\"dialog-weight-date\" class=\"input\" value=\"" + today + "\" /><label>Вес (кг)</label><input type=\"number\" id=\"dialog-weight-value\" class=\"input\" step=\"0.1\" min=\"0.1\" placeholder=\"кг\" />";
  openDialog({
    title: "Добавить вес",
    extraHtml: extra,
    initialValues: { title: "Добавить вес", description: "" },
    onSave: async function() {
      var dateEl = document.getElementById("dialog-weight-date");
      var valueEl = document.getElementById("dialog-weight-value");
      var date = dateEl ? dateEl.value : today;
      var value = valueEl ? parseFloat(valueEl.value) : NaN;
      if (isNaN(value) || value <= 0) {
        if (tg) tg.showAlert("Введите вес");
        throw { name: "validate" };
      }
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/weight", {
        method: "POST",
        body: JSON.stringify({ date: date, weight: value })
      });
      await loadAll();
      if (tg) tg.showAlert("Вес сохранён");
    }
  });
  setTimeout(function() {
    var titleInput = $("#dialog-title-input");
    var descInput = $("#dialog-description-input");
    var titleLabel = titleInput && titleInput.closest ? titleInput.closest("label") : null;
    if (titleInput) { titleInput.style.display = "none"; titleInput.value = "Добавить вес"; }
    if (titleLabel) titleLabel.style.display = "none";
    if (descInput) { descInput.style.display = "none"; descInput.closest("label") && (descInput.closest("label").style.display = "none"); }
    var dateEl = document.getElementById("dialog-weight-date");
    var valueEl = document.getElementById("dialog-weight-value");
    if (dateEl) dateEl.value = today;
    if (valueEl) valueEl.focus();
  }, 50);
}

function openWaterFlow() {
  var p = state.cache.profile || {};
  var hasCity = (p.city || "").trim();
  var hasCountry = (p.country || "").trim();
  if (hasCity || hasCountry) {
    runWaterCalculate(false, (p.city || "").trim(), (p.country || "").trim(), (p.country_code || "").trim());
    return;
  }
  var msg = "Даёте согласие на определение вашего города по IP для учёта погоды при расчёте нормы воды?";
  var useGeo = (typeof confirm !== "undefined") ? confirm(msg) : false;
  if (useGeo) {
    runWaterCalculate(true);
  } else {
    openCityPicker();
  }
}
async function runWaterCalculate(useGeo, city, country, countryCode) {
  try {
    var body = { use_geo: !!useGeo, activity_minutes: 0 };
    if (!useGeo && (city || country || countryCode)) {
      body.city = (city || "").trim();
      body.country = (country || "").trim();
      if ((countryCode || "").trim().length === 2) body.country_code = (countryCode || "").trim().toUpperCase();
    }
    var res = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/water-calculate", {
      method: "POST",
      body: JSON.stringify(body)
    });
    var liters = res && res.liters;
    var formula = res && res.formula;
    var city = res && res.city;
    var country = res && res.country;
    var temp = res && res.temp;
    var humidity = res && res.humidity;
    if (liters == null) {
      if (tg) tg.showAlert("Укажите вес в профиле");
      return;
    }
    state.lastWaterResult = { liters: liters, formula: formula, city: city, country: country, temp: temp, humidity: humidity };
    if (city != null || country != null) {
      if (!state.cache.profile) state.cache.profile = {};
      if (city != null) state.cache.profile.city = city;
      if (country != null) state.cache.profile.country = country;
    }
    renderProfile();
    var createHabit = (typeof confirm !== "undefined") ? confirm("Сформировать привычку «Пить воду» на основе расчёта?") : false;
    var formulaNote = [city && "город " + city, country && country, temp != null && "темп. " + temp + " °C", humidity != null && "влажность " + humidity + "%", formula].filter(Boolean).join("; ");
    if (createHabit) {
      await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/water-habit", {
        method: "POST",
        body: JSON.stringify({ liters_per_day: liters, formula_note: formulaNote })
      });
      await loadAll();
      if (tg) tg.showAlert("Привычка «Пить воду» добавлена. Рекомендуемая норма: " + liters + " л в день.");
    } else {
      if (tg) tg.showAlert("Рекомендуемая норма воды: " + liters + " л в день.");
    }
  } catch (e) {
    if (e && e.status === 400 && (e.body || "").indexOf("вес") >= 0) {
      if (tg) tg.showAlert("Укажите вес в профиле"); else alert("Укажите вес в профиле");
      return;
    }
    if (useGeo && (e && (e.status === 404 || e.status === 502))) {
      if (tg) tg.showAlert("Не удалось определить погоду по IP. Введите город вручную."); else alert("Не удалось определить погоду по IP. Введите город вручную.");
      var cityInput = prompt("Введите город (например: Москва):", "");
      var countryInput = prompt("Введите страну (например: Россия):", "");
      if (cityInput) runWaterCalculate(false, cityInput, countryInput);
      return;
    }
    if (!useGeo) {
      var cityInput = prompt("Введите город (например: Москва):", "");
      var countryInput = prompt("Введите страну (например: Россия):", "");
      if (cityInput) runWaterCalculate(false, cityInput, countryInput);
      return;
    }
    if (tg) tg.showAlert("Не удалось рассчитать. Попробуйте ввести город вручную."); else alert("Не удалось рассчитать.");
  }
}

function showInfoPopup(title, message) {
  var backdrop = $("#info-popup-backdrop");
  var titleEl = $("#info-popup-title");
  var messageEl = $("#info-popup-message");
  var okBtn = $("#info-popup-ok");
  if (!backdrop) return;
  if (titleEl) titleEl.textContent = title || "";
  if (messageEl) messageEl.textContent = message || "";
  backdrop.classList.remove("hidden");
  function close() {
    backdrop.classList.add("hidden");
  }
  if (okBtn) okBtn.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); close(); };
  backdrop.onclick = function(ev) {
    if (ev.target === backdrop) { ev.preventDefault(); close(); }
  };
  var dialog = backdrop.querySelector(".info-popup-dialog");
  if (dialog) dialog.onclick = function(ev) { ev.stopPropagation(); };
}

function showAchievementPopup(habitTitle) {
  var backdrop = $("#achievement-popup-backdrop");
  var habitEl = $("#achievement-popup-habit");
  var okBtn = $("#achievement-popup-ok");
  if (!backdrop) return;
  if (habitEl) habitEl.textContent = habitTitle || "Привычка";
  backdrop.classList.remove("hidden");
  function close() {
    backdrop.classList.add("hidden");
  }
  if (okBtn) okBtn.onclick = function(ev) { ev.preventDefault(); ev.stopPropagation(); close(); };
  backdrop.onclick = function(ev) {
    if (ev.target === backdrop) { ev.preventDefault(); close(); }
  };
  var dialog = backdrop.querySelector(".achievement-popup-dialog");
  if (dialog) dialog.onclick = function(ev) { ev.stopPropagation(); };
}

function showProfileHelpBmi() {
  var text = "ИМТ = вес (кг) / рост² (м). Оценка по ВОЗ: <18.5 — недостаток веса; 18.5–24.9 — норма; 25–29.9 — избыточный вес; ≥30 — ожирение. Идеальный диапазон веса — вес при ИМТ 18.5–24.9 для вашего роста. Идеальный ИМТ по формуле Девина (пол и рост) — золотой стандарт в клинической практике.";
  showInfoPopup("Справка ИМТ", text);
}
function showWaterHelp() {
  var text = "Вода (л) = (Вес_кг × 30 мл) + (Активность_мин × 15 мл) + климатическая поправка (ВОЗ/Mayo). 15 мл/мин — коэффициент потери жидкости при умеренной активности (MyFitnessPal, WaterMinder, Samsung Health).";
  if (tg && tg.showAlert) tg.showAlert(text); else alert(text);
}

var cityPickerSearchTimeout = null;
function openCityPicker() {
  var overlay = $("#city-picker-overlay");
  var searchEl = $("#city-picker-search");
  var listEl = $("#city-picker-list");
  if (!overlay || !listEl) return;
  overlay.classList.remove("hidden");
  if (searchEl) { searchEl.value = ""; searchEl.focus(); }
  listEl.innerHTML = "<p class=\"city-picker-hint\">Введите название города в поле выше</p>";
  if (searchEl) {
    searchEl.oninput = function() {
      var q = (searchEl.value || "").trim();
      if (cityPickerSearchTimeout) clearTimeout(cityPickerSearchTimeout);
      if (!q || q.length < 2) {
        listEl.innerHTML = "<p class=\"city-picker-hint\">Введите минимум 2 символа</p>";
        return;
      }
      cityPickerSearchTimeout = setTimeout(async function() {
        try {
          var res = await fetchJSON(state.baseUrl + "/api/geocode/search?q=" + encodeURIComponent(q));
          var results = (res && res.results) ? res.results : [];
          if (!results.length) {
            listEl.innerHTML = "<p class=\"city-picker-hint\">Ничего не найдено</p>";
            return;
          }
          listEl.innerHTML = results.map(function(r) {
            var code = (r.country_code || "").trim();
            var label = (r.name || "") + (r.country ? ", " + r.country : "") + (code ? " (" + code + ")" : "");
            return "<button type=\"button\" class=\"city-picker-item\" data-name=\"" + escapeHtml(r.name || "") + "\" data-country=\"" + escapeHtml(r.country || "") + "\" data-country-code=\"" + escapeHtml(code) + "\">" + escapeHtml(label) + "</button>";
          }).join("");
          listEl.querySelectorAll(".city-picker-item").forEach(function(btn) {
            btn.addEventListener("click", async function() {
              var name = btn.dataset.name || "";
              var country = btn.dataset.country || "";
              var countryCode = (btn.dataset.countryCode || "").trim();
              try {
                await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/profile", {
                  method: "PUT",
                  body: JSON.stringify({ city: name, country: country, country_code: countryCode || undefined })
                });
                closeCityPicker();
                await loadAll();
                if (tg) tg.showAlert("Город сохранён: " + name + (country ? ", " + country : ""));
              } catch (err) {
                if (tg) tg.showAlert("Не удалось сохранить город");
              }
            });
          });
        } catch (e) {
          listEl.innerHTML = "<p class=\"city-picker-hint\">Ошибка поиска</p>";
        }
      }, 300);
    };
  }
}
function closeCityPicker() {
  var overlay = $("#city-picker-overlay");
  if (overlay) overlay.classList.add("hidden");
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
    await fetchJSON(base + "/api/user/" + uid + "/ensure-examples", { method: "POST" }).catch(function() {});
    var profileFallback = {
      first_name: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.first_name) || "",
      last_name: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.last_name) || "",
      username: (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.username) || "",
      display_name: ""
    };
    const [achievementCheckRes, missions, goals, habits, analytics, profile, weightHistoryRes, achievementsRes] = await Promise.all([
      fetchJSON(base + "/api/user/" + uid + "/achievement-check").catch(function() { return {}; }),
      fetchJSON(base + "/api/user/" + uid + "/missions").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Миссии:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/goals").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Цели:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/habits").catch(e => { if (e && e.status === 401) throw e; console.error("❌ Привычки:", e.message); return []; }),
      fetchJSON(base + "/api/user/" + uid + "/analytics?period=" + (state.analyticsPeriod || "month")).catch(e => {
        if (e && e.status === 401) throw e;
        console.error("❌ Аналитика:", e.message);
        return { period: "month", missions: { total: 0, completed: 0, avg_progress: 0 }, goals: { total: 0, completed: 0, completion_rate: 0 }, habits: { total: 0, total_completions: 0, streak: 0 }, habit_chart: { labels: [], values: [] } };
      }),
      fetchJSON(base + "/api/user/" + uid + "/profile").catch(e => { if (e && e.status === 401) throw e; return profileFallback; }),
      fetchJSON(base + "/api/user/" + uid + "/weight-history?period=7").catch(function() { return { data: [] }; }),
      fetchJSON(base + "/api/user/" + uid + "/achievements").catch(function() { return { achievements: [] }; })
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
    state.cache.weightHistory = (weightHistoryRes && Array.isArray(weightHistoryRes.data)) ? weightHistoryRes.data : [];
    state.cache.achievements = (achievementsRes && achievementsRes.achievements) ? achievementsRes.achievements : [];

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

    if (achievementCheckRes && achievementCheckRes.achievement_unlocked && achievementCheckRes.habit_title) {
      showAchievementPopup(achievementCheckRes.habit_title);
    }

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
    state.cache.achievements = [];
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

async function loadReminderSettings() {
  if (!state.userId) return null;
  try {
    var r = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/reminder-settings");
    state.reminderSettings = r;
    return r;
  } catch (e) {
    state.reminderSettings = { notifications_enabled: true };
    return state.reminderSettings;
  }
}

async function loadGoogleFitStatus() {
  if (!state.userId) return;
  try {
    var r = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/google-fit/status");
    state.googleFitConnected = !!(r && r.connected);
  } catch (e) {
    state.googleFitConnected = false;
  }
}

async function loadGoogleFitSteps() {
  if (!state.userId || !state.googleFitConnected) return;
  try {
    var r = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/google-fit/steps");
    state.googleFitSteps = (r && r.steps != null) ? r.steps : null;
  } catch (e) {
    state.googleFitSteps = null;
  }
}

function renderSettings() {
  var container = $("#settings-view");
  if (!container) return;
  var s = state.reminderSettings || { notifications_enabled: true };
  var on = !!s.notifications_enabled;
  var gfConnected = !!state.googleFitConnected;
  container.innerHTML =
    "<div class=\"settings-row\">" +
      "<div><div class=\"settings-row-label\">Уведомления</div>" +
      "<div class=\"settings-row-hint\">Напоминания о привычках, целях и миссиях в Telegram. Отключите, чтобы не получать сообщения от бота.</div></div>" +
      "<button type=\"button\" class=\"settings-toggle " + (on ? "on" : "") + "\" id=\"settings-notifications-toggle\" aria-label=\"Уведомления " + (on ? "вкл" : "выкл") + "\"></button>" +
    "</div>" +
    "<div class=\"settings-row\">" +
      "<div><div class=\"settings-row-label\">Авторизация Google Fit</div>" +
      "<div class=\"settings-row-hint\">Подключите аккаунт Google, чтобы видеть шаги в профиле.</div></div>" +
      "<button type=\"button\" class=\"btn-sm " + (gfConnected ? "" : "primary-btn") + "\" id=\"settings-google-fit-btn\">" + (gfConnected ? "Отключить" : "Подключить") + "</button>" +
    "</div>";
  var toggle = $("#settings-notifications-toggle");
  if (toggle) {
    toggle.addEventListener("click", async function() {
      var newVal = !toggle.classList.contains("on");
      toggle.classList.toggle("on", newVal);
      try {
        await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/reminder-settings", {
          method: "PUT",
          body: JSON.stringify({ notifications_enabled: newVal })
        });
        state.reminderSettings = state.reminderSettings || {};
        state.reminderSettings.notifications_enabled = newVal;
      } catch (e) {
        if (tg) tg.showAlert("Не удалось сохранить настройку.");
      }
    });
  }
  var gfBtn = $("#settings-google-fit-btn");
  if (gfBtn) {
    gfBtn.addEventListener("click", async function() {
      if (state.googleFitConnected) {
        try {
          await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/google-fit", { method: "DELETE" });
          state.googleFitConnected = false;
          state.googleFitSteps = null;
          renderSettings();
          renderProfile();
        } catch (e) {
          if (tg) tg.showAlert("Не удалось отключить.");
        }
      } else {
        try {
          var r = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/google-fit/auth-url");
          var url = r && r.auth_url;
          if (url && tg && tg.openLink) tg.openLink(url);
          else if (url) window.open(url, "_blank");
          else if (tg) tg.showAlert("Google Fit не настроен на сервере.");
        } catch (e) {
          if (tg) tg.showAlert("Не удалось получить ссылку. Проверьте настройки сервера.");
        }
      }
    });
  }
}

function openSettingsOverlay() {
  var ov = $("#settings-overlay");
  if (!ov) return;
  loadReminderSettings().then(function() {
    loadGoogleFitStatus().then(function() {
      renderSettings();
      ov.classList.remove("hidden");
    }).catch(function() { renderSettings(); ov.classList.remove("hidden"); });
  });
}

function closeSettingsOverlay() {
  var ov = $("#settings-overlay");
  if (ov) ov.classList.add("hidden");
}

var MONTH_NAMES_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
var WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function openHabitCalendar() {
  var ov = $("#habit-calendar-overlay");
  if (!ov || !state.userId) return;
  renderHabitCalendar();
  ov.classList.remove("hidden");
}

function closeHabitCalendar() {
  var ov = $("#habit-calendar-overlay");
  if (ov) ov.classList.add("hidden");
}

function formatCalDate(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  return d.getDate() + " " + d.toLocaleDateString("ru-RU", { month: "short" }).replace(".", "");
}

async function renderHabitCalendar() {
  var view = $("#habit-calendar-view");
  var datesEl = $("#habit-calendar-dates");
  if (!view || !datesEl) return;
  view.innerHTML = "<p class=\"habit-calendar-loading\">Загрузка…</p>";
  datesEl.innerHTML = "";
  try {
    var data = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/habit-last-7-days");
    var dates = (data && data.dates) || [];
    var habits = (data && data.habits) || [];
  } catch (e) {
    view.innerHTML = "<p class=\"habit-calendar-error\">Ошибка загрузки</p>";
    return;
  }
  if (habits.length === 0) {
    view.innerHTML = "<p class=\"habit-calendar-empty\">Нет активных привычек. Добавьте привычку на вкладке «Привычки».</p>";
    return;
  }
  datesEl.innerHTML = "<span class=\"habit-cal-dates-label\">Привычка</span>" +
    dates.map(function(d) { return "<span class=\"habit-cal-date\">" + formatCalDate(d) + "</span>"; }).join("");
  var html = "";
  habits.forEach(function(h) {
    var title = escapeHtml(h.title || "Привычка");
    var daysStr = (h.days || []).map(function(d) { return d ? "<span class=\"habit-cal-dot habit-cal-dot-done\" title=\"Выполнено\">✓</span>" : "<span class=\"habit-cal-dot habit-cal-dot-skip\" title=\"Пропущено\">−</span>"; }).join("");
    html += "<div class=\"habit-cal-row\">" +
      "<span class=\"habit-cal-name\">" + title + "</span>" +
      "<span class=\"habit-cal-days\">" + daysStr + "</span>" +
      "</div>";
  });
  view.innerHTML = html;
}

function bindEvents() {
  var tabEls = $all(".tab");
  tabEls.forEach(function(btn) {
    btn.addEventListener("click", function() { switchTab(btn.dataset.tab); });
  });
  var settingsBtn = document.getElementById("settings-btn");
  if (settingsBtn) settingsBtn.addEventListener("click", openSettingsOverlay);
  var settingsOverlayClose = document.getElementById("settings-overlay-close");
  if (settingsOverlayClose) settingsOverlayClose.addEventListener("click", closeSettingsOverlay);
  var settingsBackdrop = $(".settings-overlay-backdrop");
  if (settingsBackdrop) settingsBackdrop.addEventListener("click", closeSettingsOverlay);
  var habitCalendarBtn = document.getElementById("habit-calendar-btn");
  if (habitCalendarBtn) habitCalendarBtn.addEventListener("click", openHabitCalendar);
  var habitCalendarClose = document.getElementById("habit-calendar-close");
  if (habitCalendarClose) habitCalendarClose.addEventListener("click", closeHabitCalendar);
  var habitCalendarBackdrop = $(".habit-calendar-backdrop");
  if (habitCalendarBackdrop) habitCalendarBackdrop.addEventListener("click", closeHabitCalendar);
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
      var mid = cb.dataset.id;
      var m = (state.cache.missions || []).find(function(x) { return String(x.id) === String(mid); });
      if (m) {
        m.is_completed = 1;
        renderMissions(state.cache.missions);
      }
      try {
        await fetchJSON(state.baseUrl + "/api/missions/" + mid + "/complete", { method: "POST" });
        loadAll();
      } catch (err) {
        if (m) { m.is_completed = 0; renderMissions(state.cache.missions); }
        if (tg) tg.showAlert("Ошибка");
      }
      return;
    }
    if (cb.classList && cb.classList.contains("goal-done-cb")) {
      e.preventDefault();
      var gid = cb.dataset.id;
      var g = (state.cache.goals || []).find(function(x) { return String(x.id) === String(gid); });
      if (g) {
        var prev = g.is_completed;
        g.is_completed = cb.checked ? 1 : 0;
        renderGoals(state.cache.goals);
        try {
          if (cb.checked) {
            await fetchJSON(state.baseUrl + "/api/goals/" + gid + "/complete", { method: "POST" });
          } else {
            await fetchJSON(state.baseUrl + "/api/goals/" + gid + "/uncomplete", { method: "POST" });
          }
          loadAll();
        } catch (err) {
          g.is_completed = prev;
          renderGoals(state.cache.goals);
          if (tg) tg.showAlert("Ошибка");
        }
      }
      return;
    }
    if (cb.classList && cb.classList.contains("subgoal-done-cb")) {
      e.preventDefault();
      var sid = cb.dataset.id;
      var subgoalsByMission = state.cache.subgoalsByMission || {};
      var found = null, prevVal;
      for (var mid in subgoalsByMission) {
        var list = subgoalsByMission[mid] || [];
        for (var i = 0; i < list.length; i++) {
          if (String(list[i].id) === String(sid)) {
            found = list[i];
            prevVal = found.is_completed;
            found.is_completed = cb.checked ? 1 : 0;
            break;
          }
        }
        if (found) break;
      }
      if (found) {
        renderMissions(state.cache.missions);
        try {
          if (cb.checked) {
            await fetchJSON(state.baseUrl + "/api/subgoals/" + sid + "/complete", { method: "POST" });
          } else {
            await fetchJSON(state.baseUrl + "/api/subgoals/" + sid + "/uncomplete", { method: "POST" });
          }
          loadAll();
        } catch (err) {
          found.is_completed = prevVal;
          renderMissions(state.cache.missions);
          if (tg) tg.showAlert("Ошибка");
        }
      }
      return;
    }
  });

  document.body.addEventListener("click", async function(e) {
    var stepsRefreshBtn = e.target.closest(".profile-steps-refresh");
    if (stepsRefreshBtn) {
      e.preventDefault();
      if (state.googleFitConnected) {
        await loadGoogleFitSteps();
        renderProfile();
      }
      return;
    }
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

    var subgoalRow = e.target.closest(".subgoal-row");
    /* Открывать редактирование при клике по подцели, кроме чекбокса и ручки перетаскивания */
    if (subgoalRow && !e.target.closest(".subgoal-drag-handle") && !e.target.closest("input.subgoal-done-cb")) {
      e.preventDefault();
      e.stopPropagation();
      var subgoalId = subgoalRow.dataset.id;
      if (!subgoalId) return;
      var subgoal = null;
      var subgoalsByMission = state.cache.subgoalsByMission || {};
      for (var mid in subgoalsByMission) {
        var list = subgoalsByMission[mid] || [];
        for (var i = 0; i < list.length; i++) {
          if (String(list[i].id) === String(subgoalId)) { subgoal = list[i]; break; }
        }
        if (subgoal) break;
      }
      if (subgoal) {
        if (tg && tg.MainButton) tg.MainButton.hide();
        openDialog({
          title: "Редактировать подцель",
          initialValues: { title: subgoal.title || "", description: subgoal.description || "" },
          onSave: async function(p) {
            var title = (p && p.title != null) ? String(p.title).trim() : "";
            var description = (p && p.description != null) ? String(p.description) : "";
            if (!title) { if (tg) tg.showAlert("Введите название"); throw new Error("validate"); }
            await fetchJSON(state.baseUrl + "/api/subgoals/" + subgoalId + "/update", {
              method: "POST",
              body: JSON.stringify({ title: title, description: description })
            });
            await loadAll();
          },
          onDelete: async function() {
            await fetchJSON(state.baseUrl + "/api/subgoals/" + subgoalId, { method: "DELETE" });
            await loadAll();
          }
        });
        return;
      }
    }

    var content = e.target.closest(".swipe-row-content");
    if (content && !e.target.closest(".habit-btn, .habit-reminder-toggle, .habit-water-help, .swipe-delete-btn, .mission-done-cb-wrap, .goal-done-cb-wrap, .subgoal-done-cb, .subgoal-cb-wrap, .subgoal-row, .add-subgoal-btn")) {
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

  function updateReorderModeUI() {
    document.body.classList.toggle("reorder-mode", state.reorderMode);
    $all(".panel-edit-btn").forEach(function(btn) {
      var icon = btn.querySelector(".panel-edit-btn-icon");
      if (icon) icon.textContent = state.reorderMode ? "check" : "edit";
      btn.setAttribute("aria-label", state.reorderMode ? "Готово" : "Режим перетаскивания");
      btn.setAttribute("title", state.reorderMode ? "Готово" : "Режим перетаскивания");
    });
  }

  $all(".panel-edit-btn").forEach(function(btn) {
    btn.addEventListener("click", function(e) {
      e.preventDefault();
      e.stopPropagation();
      state.reorderMode = !state.reorderMode;
      updateReorderModeUI();
    });
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

  var profileView = $("#profile-view");
  if (profileView) profileView.addEventListener("click", function(e) {
    if (e.target.closest(".profile-bmi-help")) { e.preventDefault(); showProfileHelpBmi(); }
  });

  var cityPickerClose = $("#city-picker-close");
  if (cityPickerClose) cityPickerClose.addEventListener("click", closeCityPicker);
  var cityPickerBackdrop = document.querySelector(".city-picker-backdrop");
  if (cityPickerBackdrop) cityPickerBackdrop.addEventListener("click", closeCityPicker);
  var weightTrendClose = $("#weight-trend-close");
  if (weightTrendClose) weightTrendClose.addEventListener("click", closeWeightTrendOverlay);
  var weightTrendBackdrop = document.querySelector(".weight-trend-backdrop");
  if (weightTrendBackdrop) weightTrendBackdrop.addEventListener("click", closeWeightTrendOverlay);
  var weightTrendPeriod = $("#weight-trend-period");
  if (weightTrendPeriod) weightTrendPeriod.addEventListener("change", async function() {
    var period = weightTrendPeriod.value;
    var chartEl = $("#weight-trend-chart");
    if (!chartEl || !state.userId) return;
    try {
      var res = await fetchJSON(state.baseUrl + "/api/user/" + state.userId + "/weight-history?period=" + period);
      var data = (res && res.data) ? res.data : [];
      var targetWeight = (state.cache.profile && state.cache.profile.target_weight != null) ? Number(state.cache.profile.target_weight) : null;
      drawWeightChart(chartEl, data, targetWeight, { width: 320, height: 220 });
    } catch (e) {
      chartEl.innerHTML = "<p class=\"weight-trend-error\">Не удалось загрузить данные</p>";
    }
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

