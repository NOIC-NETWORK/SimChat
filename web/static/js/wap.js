/* ========================================================
   SimChat WAP · 移动端逻辑 v2
   Splash Screen · 无弹层（全部路由 / 内联展开） · 欢迎界面
   ======================================================== */
(function () {
  "use strict";
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const STORE_KEY = "simchat_wap_state_v2";
  function readStore() { try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch { return {}; } }
  function writeStore(patch) { try { localStorage.setItem(STORE_KEY, JSON.stringify(Object.assign(readStore(), patch))); } catch {} }

  const state = {
    route: "sessions",
    routeStack: [],        // 内存 history：ws-picker → me → sessions 这样的 back 链
    sessionId: null,
    sessions: [],
    sessionMessages: [],
    runs: [],
    workspace: { configured: false, exists: false, path: "", name: "" },
    model: readStore().model || "",
    models: [],
    mode: readStore().mode || "chat",
    theme: readStore().theme || "system",
    themeResolved: "light",
    wsPath: "",            // 工作目录选择器当前浏览路径
    expandedChoices: null, // "model" | "theme" | null
  };

  function persist() { writeStore({ model: state.model, mode: state.mode, theme: state.theme }); }
  const API = window.SimChatAPI;

  /* ==================== Toast ==================== */
  function toast(message, isError) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " err" : "");
    el.textContent = message;
    $("#mob-toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .25s"; }, 2200);
    setTimeout(() => el.remove(), 2600);
  }

  /* ==================== 主题 ==================== */
  function applyTheme() {
    let resolved = state.theme;
    if (state.theme === "system") resolved = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    state.themeResolved = resolved;
    document.body.dataset.theme = resolved;
  }

  /* ==================== Splash Screen ==================== */
  /**
   * 并行拉 SimChat 核心状态，进度反馈到 splash bar；
   * 所有请求完成（或超时）后淡出 splash，显示 shell。
   */
  async function runSplash() {
    const splash = $("#mob-splash");
    const fill = $("#splash-fill");
    const hint = $("#splash-hint");
    const skip = $("#splash-skip");
    const shell = $("#mob-shell");

    // 强制跳过（调试用）
    const skipRun = () => {
      splash.classList.add("fading");
      setTimeout(() => { splash.classList.add("hidden"); shell.hidden = false; }, 500);
    };
    skip.addEventListener("click", skipRun);
    setTimeout(() => { if (!skipRun._done) skip.hidden = false; }, 1200);

    let progress = 0;
    const totalStages = 4;
    function step(done, label) {
      progress = Math.min(100, Math.round((done / totalStages) * 100));
      fill.style.width = progress + "%";
      if (label) hint.textContent = label;
    }

    // 4 个阶段并行，但步进时逐个通知
    const stages = [
      API.listSessions().then((list) => { state.sessions = list || []; step(1, "加载会话…"); }),
      API.listProviders().then((data) => {
        const blocks = (data && data.blocks) || [];
        const avail = [];
        blocks.forEach((b) => (b.models || []).forEach((m) => avail.push({ value: m, label: m })));
        state.models = avail;
        if (!avail.find((m) => m.value === state.model) && avail.length) { state.model = avail[0].value; persist(); }
        step(2, "发现模型…");
      }).catch(() => { step(2, "发现模型…"); }),
      API.listAgentTasks().then((list) => { state.runs = list || []; step(3, "扫描任务…"); }),
      API.getWorkspace().then((ws) => {
        state.workspace = ws || { configured: false, exists: false, path: "", name: "" };
        if (state.workspace.configured && state.workspace.path) {
          const parts = state.workspace.path.replace(/[\\/]+$/, "").split(/[\\/]/);
          state.workspace.name = parts[parts.length - 1];
          state.wsPath = state.workspace.path;
        }
        step(4, "准备就绪");
      }).catch(() => { state.workspace = { configured: false, exists: false, path: "", name: "" }; step(4, "准备就绪"); }),
    ];

    // 超时保护：最多 4s 后不管进度多少都往下走
    const donePromise = Promise.allSettled(stages);
    const timeoutPromise = new Promise((r) => setTimeout(r, 4000));
    await Promise.race([donePromise, timeoutPromise]);
    step(totalStages, "准备就绪");
    // 等进度条动画补满
    await new Promise((r) => setTimeout(r, 350));

    skipRun._done = true;
    skipRun();
  }

  /* ==================== 路由 ==================== */
  const TAB_ROUTES = new Set(["sessions", "tasks", "me"]);
  const TITLES = { sessions: "对话", tasks: "任务", me: "我的", chat: "对话", "ws-picker": "工作目录" };

  function navigateRoute(route, opts) {
    opts = opts || {};
    // 记录 history（但只记录一次避免循环）
    if (opts.push !== false && route !== state.route) {
      // 不把 TabBar 路由推栈（只有全屏路由才 push：ws-picker）
      if (!TAB_ROUTES.has(route)) state.routeStack.push(state.route);
      // TabBar 切换（sessions/tasks/me）清栈：它们之间是平级
      if (TAB_ROUTES.has(route)) state.routeStack.length = 0;
    }
    state.route = route;
    document.body.dataset.route = route;

    // 渲染所有 screen
    $$(".mob-screen").forEach((s) => {
      s.classList.toggle("active", s.dataset.route === route);
      s.classList.remove("back");
    });
    // 滑入动画方向：ws-picker 从右进，从它出去时给一个 back 效果
    if (route === "ws-picker") {
      // 让它看起来像从另一个 stack 进
    }

    // TabBar
    const tabMap = { sessions: "sessions", tasks: "tasks", chat: "sessions", "ws-picker": null, me: "me" }[route];
    $$(".mob-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tabMap)));

    // 标题栏
    const back = $("#mob-back");
    const title = $("#mob-title");
    const right = $("#mob-head-right");

    if (route === "sessions") {
      back.hidden = true;
      title.textContent = "对话";
      right.innerHTML = '<button class="icon-btn" id="mob-new" title="新对话"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></button>';
    } else if (route === "chat") {
      back.hidden = false;
      const s = state.sessions.find((x) => x.id === state.sessionId);
      title.textContent = s ? (s.title || "对话") : "对话";
      right.innerHTML = "";
    } else if (route === "tasks") {
      back.hidden = true;
      title.textContent = "任务";
      right.innerHTML = "";
    } else if (route === "me") {
      back.hidden = true;
      title.textContent = "我的";
      right.innerHTML = "";
    } else if (route === "ws-picker") {
      back.hidden = false;
      title.textContent = "工作目录";
      right.innerHTML = "";
    }

    render();
  }

  function backToPrev() {
    if (state.routeStack.length) {
      const prev = state.routeStack.pop();
      navigateRoute(prev, { push: false });
    } else if (state.route === "chat") {
      navigateRoute("sessions", { push: false });
    } else if (state.route === "ws-picker") {
      navigateRoute("me", { push: false });
    } else {
      // 兜底
      navigateRoute("sessions", { push: false });
    }
  }

  /* ==================== 渲染 ==================== */
  function render() {
    if (state.route === "sessions") renderSessions();
    else if (state.route === "chat") renderChat();
    else if (state.route === "tasks") renderTasks();
    else if (state.route === "me") renderMe();
    else if (state.route === "ws-picker") renderWsPicker();
    renderWorkspaceLock();
  }

  function renderWorkspaceLock() {
    const gate = !(state.workspace.configured && state.workspace.exists);
    const banner = $("#mob-lock-banner");
    const box = $("#mob-composer-box");
    const input = $("#mob-composer-input");
    const send = $("#mob-send");
    banner.classList.toggle("hidden", !gate || state.route !== "chat");
    box.classList.toggle("locked", gate);
    input.disabled = gate || !state.model;
    input.placeholder = gate ? "请先配置工作目录（我的页）" : !state.model ? "请先配置模型" : "向 SimChat 提问…";
    send.disabled = gate || !state.model || !input.value.trim();

    $("#mob-me-model").textContent = state.model || "未配置";
    const ws = state.workspace;
    if (ws.configured) {
      $("#mob-me-ws-path").textContent = ws.path || "";
      $("#mob-me-ws-status").textContent = ws.exists ? "已配置" : "缺失";
      $("#mob-me-ws-status").style.color = ws.exists ? "var(--ok)" : "var(--danger)";
    } else {
      $("#mob-me-ws-path").textContent = "未配置";
      $("#mob-me-ws-status").textContent = "—";
    }
    $("#mob-me-mode").textContent = state.mode === "agent" ? "Agent" : "对话";
    const themeLabel = { system: "跟随系统", light: "浅色", dark: "深色" }[state.theme];
    $("#mob-me-theme-label").textContent = themeLabel;

    // 渲染内联选项组（只有当「我的」页在看时）
    renderChoices();
  }

  function renderChoices() {
    const modelBox = $("#mob-model-choices");
    const themeBox = $("#mob-theme-choices");
    if (!modelBox || !themeBox) return;

    const showModel = state.expandedChoices === "model";
    const showTheme = state.expandedChoices === "theme";
    modelBox.classList.toggle("hidden", !showModel);
    themeBox.classList.toggle("hidden", !showTheme);

    $("#mob-me-model-row").classList.toggle("open", showModel);
    $("#mob-me-theme-row").classList.toggle("open", showTheme);

    if (showModel && modelBox.innerHTML === "") {
      modelBox.innerHTML = state.models.length
        ? state.models.map((m) =>
            '<button class="mob-choice-item mono" data-model="' + esc(m.value || m) + '">' +
            '<div class="choice-grow">' + esc(m.value || m) + "</div>" +
            (state.model === (m.value || m) ? '<span class="check">✓</span>' : "") + "</button>"
          ).join("")
        : '<div style="padding:8px 18px;font-size:12px;color:var(--text-faint)">暂无可用模型，请先在桌面版配置服务商</div>';
    }
    if (showTheme && themeBox.innerHTML === "") {
      themeBox.innerHTML = [
        { v: "system", label: "跟随系统" },
        { v: "light", label: "浅色" },
        { v: "dark", label: "深色" },
      ].map((o) =>
        '<button class="mob-choice-item" data-theme="' + o.v + '">' +
        '<div class="choice-grow">' + o.label + "</div>" +
        (state.theme === o.v ? '<span class="check">✓</span>' : "") + "</button>"
      ).join("");
    }
  }

  function renderSessions() {
    const list = $("#mob-session-list");
    // 欢迎卡 + 空会话列表
    let itemsHTML = "";
    if (state.sessions.length) {
      itemsHTML = state.sessions.map((s) =>
        '<button class="mob-session-item" data-session="' + esc(s.id) + '">' +
        '<div class="mob-session-title">' + esc((s.title || "").slice(0, 32) || "—") + "</div>" +
        '<div class="mob-session-preview">' + esc((s.preview || s.title || "").slice(0, 60)) + "</div>" +
        '<div class="mob-session-meta">' +
        '<span>' + (s.agent_capable ? "Agent" : "Chat") + "</span>" +
        '<span>·</span>' +
        '<span>' + (s.message_count || 0) + " 条</span>" +
        (s.updated_at ? '<span>·</span><span>' + esc(s.updated_at) + "</span>" : "") +
        "</div></button>"
      ).join("");
    }
    const welcomeCard = state.sessions.length === 0
      ? '<div class="mob-welcome"><div class="mob-welcome-card">' +
          '<div class="mob-welcome-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 21l1.9-5.4A8 8 0 1 1 21 12Z"/></svg></div>' +
          '<h3>SimChat</h3>' +
          '<p>本地 AI 副驾驶 · 对话 / Agent / 工具调用<br>从新建一条对话开始吧</p>' +
          '<button id="welcome-new">' +
            '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>' +
            '开启第一条对话' +
          "</button>" +
        "</div></div>"
      : "";
    list.innerHTML = welcomeCard + itemsHTML;
  }

  function renderChat() {
    const box = $("#mob-chat-messages");
    if (!state.sessionMessages.length) {
      box.innerHTML = '<div class="mob-session-empty" style="padding:40px 20px">' +
        '<div class="empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3.2 14.1 9.9 20.8 12 14.1 14.1 12 20.8 9.9 14.1 3.2 12 9.9 9.9Z"/></svg></div>' +
        '<h3>开始对话</h3><p>在下方输入框描述你的问题</p></div>';
      box.scrollTop = 0;
      return;
    }
    box.innerHTML = state.sessionMessages.map((m) => {
      const isUser = m.role === "user";
      const text = m.content || m.text || "";
      return '<div class="msg ' + (isUser ? "user" : "assistant") + '">' +
        '<div class="avatar" style="width:24px;height:24px;font-size:10px">' + (isUser ? "你" : "SC") + "</div>" +
        '<div class="msg-body">' +
        (isUser
          ? '<div class="bubble-user" style="padding:8px 12px;font-size:14px">' + esc(text) + "</div>"
          : '<div class="md"><p>' + esc(text) + "</p></div>") +
        "</div></div>";
    }).join("");
    box.scrollTop = box.scrollHeight;
  }

  function renderTasks() {
    const list = $("#mob-task-list");
    if (!state.runs.length) return;
    list.innerHTML = state.runs.map((r) => {
      const events = (r.events || r.timeline || []).slice(-8);
      return '<div class="mob-task-card"><div class="mob-task-card-head">' +
        '<div class="mob-task-title">' + esc((r.title || r.id).slice(0, 40)) + "</div>" +
        '<span class="chip">' + esc(r.status || "unknown") + "</span>" +
        "</div>" +
        '<div class="mob-task-info">' + esc(r.id) + (r.updated_at ? " · " + esc(r.updated_at) : "") + "</div>" +
        (events.length
          ? '<div class="mob-task-events">' + events.map((e) => "[" + esc(e.type || e.name || "event") + "] " + esc((e.text || e.message || "").slice(0, 60))).join("\n") + "</div>"
          : "") + "</div>";
    }).join("");
  }

  function renderMe() { /* 我的页是静态 HTML，状态在 renderWorkspaceLock 同步 */ }

  async function renderWsPicker() {
    const data = await API.browseWorkspace(state.wsPath || undefined);
    if (!data || !data.ok) { toast(data && data.error ? data.error : "无法浏览目录", true); return; }
    state.wsPath = data.path;
    $("#mob-ws-current").textContent = data.path + (state.workspace.configured && data.path === state.workspace.path ? "   （当前工作目录）" : "");
    $("#mob-ws-up").disabled = !data.parent;
    $("#mob-ws-clear").disabled = !state.workspace.configured;
    $("#mob-ws-roots").innerHTML = [
      { path: "E:\\", name: "E:\\" },
      { path: "C:\\", name: "C:\\" },
    ].map((r) =>
      '<button class="mob-me-row selectable"' + (data.path === r.path ? ' style="background:var(--accent-soft)"' : "") + ' data-ws-root="' + esc(r.path) + '">' +
      '<div class="grow"><div class="label mono">' + esc(r.name) + "</div></div></button>"
    ).join("");
    $("#mob-ws-entries").innerHTML = data.entries.length ? data.entries.map((en) =>
      '<button class="mob-me-row' + (en.is_dir ? " selectable" : "") + '"' + (en.is_dir ? ' data-ws-dir="' + esc(en.path) + '"' : " disabled") + ">" +
      '<div class="grow"><div class="label">' + esc(en.name) + '</div><div class="sub">' + (en.is_dir ? "目录" : "文件") + "</div></div>" +
      (en.is_dir
        ? '<span style="color:var(--text-faint)"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 6 6 6-6 6"/></svg></span>'
        : '<span style="color:var(--text-faint);font-family:var(--font-mono);font-size:10px">FILE</span>') +
      "</button>"
    ).join("") : '<div style="padding:14px;text-align:center;color:var(--text-faint);font-size:12px">空目录</div>';
  }

  /* ==================== 发送消息 ==================== */
  async function sendMessage() {
    const input = $("#mob-composer-input");
    const text = input.value.trim();
    if (!text) return;
    const gate = !(state.workspace.configured && state.workspace.exists);
    if (gate) { toast("请先配置工作目录", true); return; }
    if (!state.model) { toast("请先配置模型", true); return; }

    input.value = "";
    const send = $("#mob-send"); send.disabled = true;

    state.sessionMessages.push({ role: "user", content: text });
    renderChat();

    let streamEl = null;
    try {
      await API.chatStream({
        message: text,
        session_id: state.sessionId,
        mode: state.mode,
        model: state.model,
      }, (eventName, data) => {
        if (data.session_id && data.session_id !== state.sessionId) {
          state.sessionId = data.session_id;
          navigateRoute("chat");
        }
        if (eventName === "token" && data.text) {
          if (!streamEl) {
            state.sessionMessages.push({ role: "assistant", content: "" });
            streamEl = state.sessionMessages[state.sessionMessages.length - 1];
          }
          streamEl.content += data.text;
          renderChat();
        }
        if (eventName === "final" && data.text) {
          state.sessionMessages.push({ role: "assistant", content: data.text });
          renderChat();
        }
        if (eventName === "error") toast(data.error || "对话失败", true);
      });
      API.listSessions().then((list) => { state.sessions = list || []; renderSessions(); }).catch(() => {});
    } catch (err) {
      toast(err.message || "发送失败", true);
    } finally {
      if (streamEl && !streamEl.content) {
        const idx = state.sessionMessages.indexOf(streamEl);
        if (idx !== -1) state.sessionMessages.splice(idx, 1);
        renderChat();
      }
      send.disabled = !(state.workspace.configured && state.workspace.exists && state.model);
    }
  }

  /* ==================== 数据加载 ==================== */
  async function loadRest() {
    if (state.sessionId) {
      try {
        const s = await API.getSession(state.sessionId);
        state.sessionMessages = (s && s.messages) || [];
      } catch { state.sessionMessages = []; }
    }
    // 首次进入选一个默认会话（有消息的优先）
    const firstWithMsgs = state.sessions.find((s) => s.message_count > 0);
    state.sessionId = state.sessionId || (firstWithMsgs ? firstWithMsgs.id : null) || (state.sessions[0] && state.sessions[0].id);
  }

  async function loadWorkspace() {
    try {
      state.workspace = await API.getWorkspace();
      if (state.workspace.configured && state.workspace.path) {
        const parts = state.workspace.path.replace(/[\\/]+$/, "").split(/[\\/]/);
        state.workspace.name = parts[parts.length - 1];
      }
    } catch {
      state.workspace = { configured: false, exists: false, path: "", name: "" };
    }
  }

  async function setWs(path) {
    try {
      state.workspace = await API.setWorkspace(path);
      if (state.workspace.configured && state.workspace.path) {
        const parts = state.workspace.path.replace(/[\\/]+$/, "").split(/[\\/]/);
        state.workspace.name = parts[parts.length - 1];
      }
      toast("工作目录已设置");
    } catch (err) {
      toast(err.message || "设置失败", true);
    }
    renderWorkspaceLock();
  }

  async function clearWs() {
    try { await API.clearWorkspace(); } catch {}
    await loadWorkspace();
    toast("工作目录已清除");
  }

  /* ==================== 事件绑定 ==================== */
  function bindAll() {
    // TabBar
    $$(".mob-tab").forEach((b) => b.addEventListener("click", () => navigateRoute(b.dataset.tab)));

    // 返回按钮
    $("#mob-back").addEventListener("click", backToPrev);

    // 新建 / 欢迎卡新建 / 会话项点击
    document.addEventListener("click", (e) => {
      const nb = e.target.closest("#mob-new") || e.target.closest("#welcome-new");
      if (nb) {
        API.createSession().then((s) => {
          state.sessions.unshift(s);
          state.sessionId = s.id;
          state.sessionMessages = [];
          navigateRoute("chat");
          toast("新对话已创建");
        }).catch((err) => toast(err.message || "创建失败", true));
        return;
      }
      const item = e.target.closest("[data-session]");
      if (item) {
        state.sessionId = item.dataset.session;
        API.getSession(state.sessionId).then((s) => {
          state.sessionMessages = (s && s.messages) || [];
          navigateRoute("chat");
        }).catch(() => { state.sessionMessages = []; navigateRoute("chat"); });
        return;
      }
    });

    // 发送
    const input = $("#mob-composer-input");
    const send = $("#mob-send");
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    input.addEventListener("input", () => {
      send.disabled = !(state.workspace.configured && state.workspace.exists && state.model) || !input.value.trim();
    });
    send.addEventListener("click", sendMessage);

    // 模式切换
    $("#mob-mode-switch").addEventListener("click", () => {
      state.mode = state.mode === "chat" ? "agent" : "chat";
      persist();
      $("#mob-mode-switch").textContent = state.mode === "agent" ? "Agent" : "对话";
      toast("模式: " + state.mode);
    });

    // 我的页：模型 / 主题 行点击 → 展开内联选项
    document.addEventListener("click", (e) => {
      const modelRow = e.target.closest("#mob-me-model-row");
      if (modelRow) {
        state.expandedChoices = state.expandedChoices === "model" ? null : "model";
        renderWorkspaceLock();
        return;
      }
      const themeRow = e.target.closest("#mob-me-theme-row");
      if (themeRow) {
        state.expandedChoices = state.expandedChoices === "theme" ? null : "theme";
        renderWorkspaceLock();
        return;
      }
      // 点击其他地方关闭
      if (!e.target.closest("#mob-me-card")) {
        if (state.expandedChoices !== null) {
          state.expandedChoices = null;
          renderWorkspaceLock();
        }
      }
      const exitRow = e.target.closest("#mob-me-exit");
      if (exitRow) { location.href = "/ide"; return; }
      const wsRow = e.target.closest("#mob-me-ws-row");
      if (wsRow) { state.wsPath = state.workspace.path || ""; navigateRoute("ws-picker"); return; }
    });

    // 内联选项点击（模型 / 主题）
    document.addEventListener("click", (e) => {
      const modelPick = e.target.closest("[data-model]");
      if (modelPick) {
        state.model = modelPick.dataset.model; persist();
        state.expandedChoices = null;
        renderWorkspaceLock(); toast("已选择模型");
        return;
      }
      const themePick = e.target.closest("[data-theme]");
      if (themePick) {
        state.theme = themePick.dataset.theme; persist();
        applyTheme();
        state.expandedChoices = null;
        renderWorkspaceLock(); toast("主题已切换");
        return;
      }
    });

    // ws-picker route 内部交互
    document.addEventListener("click", async (e) => {
      if (state.route !== "ws-picker") return;
      const root = e.target.closest("[data-ws-root]");
      if (root) { state.wsPath = root.dataset.wsRoot; await renderWsPicker(); return; }
      const dir = e.target.closest("[data-ws-dir]");
      if (dir) { state.wsPath = dir.dataset.wsDir; await renderWsPicker(); return; }
      const up = e.target.closest("#mob-ws-up");
      if (up) {
        const data = await API.browseWorkspace(state.wsPath);
        if (data && data.ok && data.parent) { state.wsPath = data.parent; await renderWsPicker(); }
        return;
      }
      const clear = e.target.closest("#mob-ws-clear");
      if (clear) { await clearWs(); await renderWsPicker(); await renderWorkspaceLock(); return; }
      const use = e.target.closest("#mob-ws-use");
      if (use) {
        await setWs(state.wsPath);
        backToPrev();
        return;
      }
    });
  }

  /* ==================== 初始化 ==================== */
  async function init() {
    applyTheme();
    bindAll();
    // 模式按钮初值
    $("#mob-mode-switch").textContent = state.mode === "agent" ? "Agent" : "对话";

    // Splash
    await runSplash();

    // Shell 内的骨架渲染
    navigateRoute("sessions");
    await loadRest();
    await loadWorkspace();

    render();
  }

  init();
})();
