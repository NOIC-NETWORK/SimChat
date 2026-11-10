/* ========================================================
   SimChat IDE · 桌面端六区布局逻辑
   从 ide-demo.html 迁移，数据层替换为真实 SimChatAPI 调用
   ======================================================== */
(function () {
  "use strict";
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const nowTime = () => {
    const d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
  };

  const ICON = {
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
    plan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h10M4 18h7"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5a3 3 0 0 0-3 3 3 3 0 0 0-1 5.8A3 3 0 0 0 8 19h1a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Z"/><path d="M15 5a3 3 0 0 1 3 3 3 3 0 0 1 1 5.8A3 3 0 0 1 16 19h-1a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/></svg>',
    terminal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12 5 5L20 6"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.5 20h19Z"/><path d="M12 9v5M12 17.2v.1"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.2 14.1 9.9 20.8 12 14.1 14.1 12 20.8 9.9 14.1 3.2 12 9.9 9.9Z"/></svg>',
  };

  /* ==================== 状态 ==================== */
  const STORE_KEY = "simchat_ide_state_v1";
  function readStore() { try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch { return {}; } }
  function writeStore(patch) { try { localStorage.setItem(STORE_KEY, JSON.stringify(Object.assign(readStore(), patch))); } catch {} }

  const state = {
    activity: "chat",
    sessionId: null,
    sessions: [],        // ← 从 API 拉
    sessionMessages: [], // ← 从 API 拉
    runId: null,
    runs: [],            // ← 从 API 拉
    mods: [],            // ← 从 API 拉
    tools: [],           // ← 从 API 拉
    theme: readStore().theme || "system",
    themeResolved: "light",
    model: readStore().model || "",
    models: [],          // ← 从 API 拉（provider discover）
    approval: readStore().approval || "on_demand",
    mode: readStore().mode || "chat",
    sessionQuery: "",
    panelTab: "events",
    events: [], sandbox: [], logs: [],
    pendingApproval: null, // { agent_id, run_id, tool, risk, args, scope }
    workspace: { configured: false, exists: false, path: "", name: "" },
    wpPath: "",
    paletteIndex: 0, paletteHits: [],
  };

  function persist() {
    writeStore({ theme: state.theme, model: state.model, approval: state.approval, mode: state.mode });
  }

  const API = window.SimChatAPI;

  /* ==================== Toast ==================== */
  function toast(message, isError) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " err" : "");
    el.textContent = message;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .25s"; }, 2400);
    setTimeout(() => el.remove(), 2800);
  }

  /* ==================== 事件流 / 日志 ==================== */
  function pushEvent(name, data, kind) {
    state.events.push({ t: nowTime(), name, data: data == null ? "" : (typeof data === "string" ? data : JSON.stringify(data)), kind: kind || "info" });
    if (state.events.length > 300) state.events.shift();
    if (state.panelTab === "events") renderPanel(false);
  }
  function pushLog(line, level) {
    state.logs.push({ t: nowTime(), line, level: level || "info" });
    if (state.logs.length > 200) state.logs.shift();
    if (state.panelTab === "logs") renderPanel(false);
  }

  /* ==================== 主题 ==================== */
  function applyTheme() {
    let resolved = state.theme;
    if (state.theme === "system") {
      resolved = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    state.themeResolved = resolved;
    document.body.dataset.theme = resolved;
  }
  function toggleTheme() {
    state.theme = state.themeResolved === "dark" ? "light" : "dark";
    persist();
    applyTheme();
    renderInspector();
    if (state.activity === "settings") renderSettings();
  }

  /* ==================== 通用渲染辅助 ==================== */
  function chipOk(text) { return '<span class="chip ok dot">' + esc(text) + "</span>"; }
  function chipWarn(text) { return '<span class="chip warn dot">' + esc(text) + "</span>"; }
  function chipDanger(text) { return '<span class="chip danger dot">' + esc(text) + "</span>"; }
  function riskBadge(risk) {
    const label = { read: "只读", write: "写入", dangerous: "高风险" }[risk] || risk;
    return '<span class="badge-risk" data-risk="' + esc(risk) + '">' + esc(label) + "</span>";
  }
  function approvalLabel() {
    return { on_demand: "按需", always_allow: "全部允许", always_deny: "全部拒绝" }[state.approval] || state.approval;
  }

  /* ==================== 侧栏 ==================== */
  const ACT_META = {
    chat: { title: "对话", action: "new-chat" },
    tasks: { title: "任务", action: "refresh" },
    ext: { title: "扩展", action: "refresh" },
    automation: { title: "自动化", action: "" },
    settings: { title: "设置", action: "" },
  };

  function sessionItem(s) {
    const mode = s.agent_capable ? "agent" : "chat";
    return '<button class="list-item" data-session="' + esc(s.id) + '" aria-current="' + (s.id === state.sessionId) + '">' +
      '<div class="li-top"><span class="li-title">' + esc((s.title || "").slice(0, 32) || "—") + '</span><span class="li-time">' + esc(s.updated_at || "") + "</span></div>" +
      '<div class="li-preview">' + esc((s.preview || s.title || "").slice(0, 60)) + "</div>" +
      '<div class="li-meta"><span class="chip">' + esc(mode) + '</span><span class="chip">' + (s.message_count || 0) + " 条</span></div></button>";
  }

  function renderSidebar() {
    const meta = ACT_META[state.activity];
    $("#side-title").textContent = meta.title;
    $("#side-action").style.display = meta.action ? "" : "none";
    $("#side-search").style.display = state.activity === "chat" || state.activity === "tasks" ? "" : "none";
    $("#side-search-input").placeholder = state.activity === "tasks" ? "搜索运行…" : "搜索会话…";
    const filter = $("#side-filter");
    filter.hidden = state.activity !== "tasks";
    let html = "";
    if (state.activity === "chat") {
      const q = state.sessionQuery.trim().toLowerCase();
      const list = state.sessions.filter((s) => !q || (s.title || "").toLowerCase().includes(q));
      html = list.length ? list.map(sessionItem).join("") : '<div class="panel-empty">暂无会话</div>';
      $("#side-sub").textContent = state.sessions.length + " 个会话";
    } else if (state.activity === "tasks") {
      html = state.runs.length
        ? state.runs.map((r) =>
            '<button class="list-item" data-run="' + esc(r.id) + '" aria-current="' + (r.id === state.runId) + '">' +
              '<div class="li-top"><span class="li-title">' + esc((r.title || r.id).slice(0, 40)) + '</span><span class="li-time">' + esc(r.updated_at || "") + "</span></div>" +
              '<div class="li-meta"><span class="chip">' + esc(r.status || "unknown") + '</span></div></button>'
          ).join("")
        : '<div class="panel-empty">暂无运行记录</div>';
      $("#side-sub").textContent = state.runs.length + " 次运行";
    } else if (state.activity === "ext") {
      html = '<div class="side-section">MOD</div>' +
        (state.mods.length
          ? state.mods.map((m) =>
              '<div class="list-item" style="cursor:default">' +
                '<div class="li-top"><span class="li-title">' + esc(m.name || m.id) + '</span>' +
                  '<button class="switch" data-mod="' + esc(m.id) + '" aria-checked="' + (m.enabled !== false) + '" role="switch"></button></div>' +
                '<div class="li-preview mono" style="font-size:10px">' + esc(m.id) + "</div></div>"
            ).join("")
          : '<div class="panel-empty">加载中…</div>') +
        '<div class="side-section" style="margin-top:8px">工具</div>' +
        (state.tools.length
          ? state.tools.map((t) =>
              '<div class="list-item" style="cursor:default"><div class="li-top"><span class="li-title mono">' + esc(t.name) + '</span>' +
                riskBadge(t.risk || "read") + '</div><div class="li-preview">' + esc(t.desc || "") + "</div></div>"
            ).join("")
          : '<div class="panel-empty">加载中…</div>');
      $("#side-sub").textContent = state.mods.length + " MOD · " + state.tools.length + " 工具";
    } else if (state.activity === "automation") {
      html = '<div class="panel-empty">automation API 未接入</div>';
      $("#side-sub").textContent = "未接入";
    } else {
      html = '<div class="side-section">设置导航</div>' +
        '<button class="list-item" data-settings-jump="provider"><div class="li-top"><span class="li-title">服务商与模型</span></div></button>' +
        '<button class="list-item" data-settings-jump="chat"><div class="li-top"><span class="li-title">对话参数</span></div></button>' +
        '<button class="list-item" data-settings-jump="workspace"><div class="li-top"><span class="li-title">工作目录</span></div></button>' +
        '<button class="list-item" data-settings-jump="appearance"><div class="li-top"><span class="li-title">外观</span></div></button>';
      $("#side-sub").textContent = "设置";
    }
    $("#side-scroll").innerHTML = html;
  }

  /* ==================== Activity 切换 ==================== */
  function setActivity(activity) {
    if (!activity) return;
    state.activity = activity;
    document.body.dataset.activity = activity;
    $$(".act-btn[data-activity]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.activity === activity)));
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + activity));
    renderSidebar();
    if (activity === "chat") renderChat();
    if (activity === "tasks") renderTasks();
    if (activity === "ext") renderExt();
    if (activity === "settings") renderSettings();
    renderInspector();
    pushEvent("activity_switch", { to: activity });
  }

  /* ==================== 对话 ==================== */
  function renderMessages() {
    const list = state.sessionMessages || [];
    const el = $("#msg-list");
    if (!el) return;
    if (!list.length) {
      el.innerHTML = '<div class="empty-card"><div class="empty-icon">' + ICON.spark + '</div>' +
        "<h3>尚未开始对话</h3><p>在下方输入框描述你的问题。</p>" +
        '<p class="mono" style="font-size:10.5px">' + esc(state.model || "") + " · " + esc(state.mode) + "</p></div>";
      return;
    }
    el.innerHTML = list.map((m) => {
      const isUser = m.role === "user";
      const text = m.content || m.text || "";
      return '<div class="msg ' + (isUser ? "user" : "assistant") + '">' +
        '<div class="avatar">' + (isUser ? "你" : "SC") + "</div>" +
        '<div class="msg-body">' +
        '<div class="msg-name">' + (isUser ? "你" : "SimChat") + '</div>' +
        (isUser
          ? '<div class="bubble-user">' + esc(text) + "</div>"
          : '<div class="md"><p>' + esc(text) + "</p></div>") +
        "</div></div>";
    }).join("");
    el.parentElement.scrollTop = el.parentElement.scrollHeight;
  }

  function renderChat() {
    const s = state.sessions.find((x) => x.id === state.sessionId);
    $("#chat-title").textContent = s ? (s.title || "对话") : "—";
    $("#chat-subtitle").textContent = state.mode + " · " + (state.model || "") + " · " + (s ? (s.message_count || 0) : 0) + " 条消息";
    renderMessages();
    updateWorkspaceUI();
    syncComposer();
  }

  function syncComposer() {
    const gate = !(state.workspace.configured && state.workspace.exists);
    const input = $("#composer-input");
    const send = $("#comp-send");
    $("#composer-box").classList.toggle("locked", gate);
    input.disabled = gate || !state.model;
    input.placeholder = gate ? "请先选择工作目录…" : !state.model ? "请先配置模型…" : "输入消息…";
    send.disabled = gate || !state.model || !input.value.trim();
  }

  function estimateTokens(text) {
    const chars = String(text || "").length;
    const ctx = 1240 + Math.round(chars * 1.4);
    const pct = Math.min(99, Math.round((ctx / 128000) * 100));
    const el = $("#comp-token-text");
    if (el) el.textContent = "≈ " + ctx.toLocaleString("en-US") + " / 128k  (" + pct + "%)";
  }

  async function sendMessage() {
    const input = $("#composer-input");
    const text = input.value.trim();
    if (!text) return;
    if (!(state.workspace.configured && state.workspace.exists)) { toast("请先配置工作目录", true); return; }
    if (!state.model) { toast("请先配置模型", true); return; }

    input.value = "";
    syncComposer();

    // 乐观地把用户消息推到本地状态
    state.sessionMessages.push({ role: "user", content: text });
    renderMessages();

    pushEvent(state.mode === "agent" ? "run_started" : "chat_started", { mode: state.mode, model: state.model });
    const assistantEl = $("#msg-list");
    let assistantBubble = null;

    try {
      await API.chatStream({
        message: text,
        session_id: state.sessionId,
        mode: state.mode,
        model: state.model,
      }, (eventName, data) => {
        if (data.session_id && data.session_id !== state.sessionId) {
          state.sessionId = data.session_id;
          renderSidebar();
        }
        if (eventName === "token" && data.text) {
          if (!assistantBubble) {
            assistantBubble = document.createElement("div");
            assistantBubble.className = "msg assistant";
            assistantBubble.innerHTML = '<div class="avatar">SC</div><div class="msg-body"><div class="msg-name">SimChat</div><div class="md"><p id="stream-text"></p></div></div>';
            assistantEl.appendChild(assistantBubble);
          }
          const p = assistantBubble.querySelector("#stream-text");
          if (p) p.textContent += data.text;
          assistantEl.parentElement.scrollTop = assistantEl.parentElement.scrollHeight;
        }
        if (eventName === "approval_required") {
          state.pendingApproval = data;
          toast("Agent 请求审批", false);
          pushEvent("approval_required", data, "approval");
          renderTasks();
          if (state.activity === "chat") setActivity("tasks");
        }
        if (eventName === "tool_call") pushEvent("tool_call", data, "info");
        if (eventName === "tool_result") pushEvent("tool_result", data, "info");
        if (eventName === "final" && data.text) {
          state.sessionMessages.push({ role: "assistant", content: data.text });
        }
        if (eventName === "error") pushEvent("error", data, "error");
      });
      pushEvent("final", {}, "final");
      // 刷新会话列表（消息数更新）
      API.listSessions().then((list) => {
        state.sessions = list;
        renderSidebar();
      }).catch(() => {});
    } catch (err) {
      pushLog("chat failed: " + err.message, "error");
      toast("发送失败: " + err.message, true);
    } finally {
      // 清理流式占位
      if (assistantBubble && !assistantBubble.querySelector("#stream-text")) {
        assistantBubble.remove();
      }
      syncComposer();
    }
  }

  /* ==================== 工作目录 ==================== */
  function updateWorkspaceUI() {
    const ws = state.workspace;
    const ok = ws.configured && ws.exists;
    const name = ws.configured ? ws.name : "选择工作目录";
    $("#side-ws-name").textContent = name;
    $("#status-ws-name").textContent = ws.configured ? ws.path : "未配置工作目录";
    $("#side-ws-chip").classList.toggle("missing", !ok);
    $("#lock-banner").classList.toggle("hidden", ok);
    syncComposer();
    renderInspector();
  }

  async function loadWorkspace() {
    try {
      const ws = await API.getWorkspace();
      state.workspace = ws || { configured: false, exists: false, path: "", name: "" };
      if (state.workspace.configured && state.workspace.path) {
        const parts = state.workspace.path.replace(/[\\/]+$/, "").split(/[\\/]/);
        state.workspace.name = parts[parts.length - 1];
      }
    } catch {
      state.workspace = { configured: false, exists: false, path: "", name: "" };
    }
    updateWorkspaceUI();
  }

  async function setWorkspace(path) {
    try {
      state.workspace = await API.setWorkspace(path);
      if (state.workspace.configured && state.workspace.path) {
        const parts = state.workspace.path.replace(/[\\/]+$/, "").split(/[\\/]/);
        state.workspace.name = parts[parts.length - 1];
      }
      persist();
    } catch (err) {
      toast(err.message || "设置工作目录失败", true);
      return false;
    }
    updateWorkspaceUI();
    toast("工作目录已设置");
    return true;
  }

  async function clearWorkspace() {
    try {
      state.workspace = await API.clearWorkspace();
    } catch {
      state.workspace = { configured: false, exists: false, path: "", name: "" };
    }
    updateWorkspaceUI();
    toast("工作目录已清除");
  }

  /* ==================== 工作目录选择器 ==================== */
  function openWorkspacePicker() {
    state.wpPath = state.workspace.configured ? state.workspace.path : "";
    $("#wp-backdrop").classList.add("open");
    renderWorkspacePicker();
  }
  function closeWorkspacePicker() { $("#wp-backdrop").classList.remove("open"); }

  async function renderWorkspacePicker() {
    const data = await API.browseWorkspace(state.wpPath || undefined);
    if (!data || !data.ok) { toast(data && data.error ? data.error : "无法浏览目录", true); return; }
    state.wpPath = data.path;
    $("#wp-path").textContent = data.path + (state.workspace.configured && data.path === state.workspace.path ? "   （当前工作目录）" : "");
    $("#wp-roots").innerHTML = [
      { path: "E:\\", name: "E:\\" },
      { path: "C:\\", name: "C:\\" },
    ].map((r) => '<button class="wp-root" data-wp-root="' + esc(r.path) + '" aria-pressed="' + (data.path === r.path) + '">' + esc(r.name) + "</button>").join("");
    $("#wp-up").disabled = !data.parent;
    $("#wp-list").innerHTML = data.entries.length ? data.entries.map((en) =>
      '<button class="wp-list wp-entry' + (en.is_dir ? "" : " is-file") + '"' + (en.is_dir ? ' data-wp-dir="' + esc(en.path) + '"' : " disabled") + ">" +
      (en.is_dir ? ICON.folder : ICON.file) + '<span class="grow">' + esc(en.name) + "</span>" +
      '<span class="chip" style="font-size:9.5px">' + (en.is_dir ? "目录" : "文件") + "</span></button>"
    ).join("") : '<div class="wp-empty">空目录</div>';
    $("#wp-trunc").classList.toggle("hidden", !data.truncated);
  }

  /* ==================== Inspector ==================== */
  function renderInspector() {
    const act = state.activity;
    let title = "会话信息";
    let html = "";
    if (act === "chat") {
      const s = state.sessions.find((x) => x.id === state.sessionId);
      const count = state.sessionMessages.length;
      title = "会话信息";
      html =
        '<div class="ins-section"><div class="ins-label">会话</div><div class="ins-card">' +
        '<div class="kv"><span class="k">标题</span><span class="v">' + esc(s ? (s.title || "—") : "—") + "</span></div>" +
        '<div class="kv"><span class="k">模式</span><span class="v">' + esc(state.mode) + "</span></div>" +
        '<div class="kv"><span class="k">模型</span><span class="v mono">' + esc(state.model || "—") + "</span></div>" +
        '<div class="kv"><span class="k">消息</span><span class="v">' + count + " 条</span></div>" +
        '<div class="kv"><span class="k">审批</span><span class="v">' + approvalLabel() + "</span></div>" +
        "</div></div>" +
        '<div class="ins-section"><div class="ins-label">工作目录</div><div class="ins-card">' +
        '<div class="kv"><span class="k">状态</span><span class="v">' + (state.workspace.configured ? (state.workspace.exists ? chipOk("已配置") : chipDanger("缺失")) : chipWarn("未配置")) + "</span></div>" +
        '<div class="kv"><span class="k">路径</span><span class="v mono" title="' + esc(state.workspace.path) + '">' + esc(state.workspace.path || "—") + "</span></div>" +
        "</div></div>";
    } else if (act === "tasks") {
      title = "运行";
      const run = state.runs.find((x) => x.id === state.runId);
      html =
        '<div class="ins-section"><div class="ins-label">当前运行</div><div class="ins-card">' +
        '<div class="kv"><span class="k">ID</span><span class="v mono">' + esc(run ? run.id : "—") + "</span></div>" +
        '<div class="kv"><span class="k">状态</span><span class="v">' + esc(run ? run.status || "—" : "—") + "</span></div>" +
        (state.pendingApproval ?
          '<div class="kv"><span class="k">待审批</span><span class="v">' + chipWarn(state.pendingApproval.tool) + "</span></div>" : "") +
        "</div></div>" +
        (state.pendingApproval ?
          '<div class="ins-section"><div class="ins-label">审批</div><div class="ins-card">' +
          '<div class="kv"><span class="k">工具</span><span class="v mono">' + esc(state.pendingApproval.tool) + "</span></div>" +
          '<div class="kv"><span class="k">风险</span><span class="v">' + riskBadge(state.pendingApproval.risk) + "</span></div>" +
          '<div class="kv"><span class="k">范围</span><span class="v mono" style="white-space:normal">' + esc(state.pendingApproval.scope || "") + "</span></div>" +
          "</div></div>" : "");
    } else if (act === "ext") {
      title = "扩展统计";
      const enabled = state.mods.filter((m) => m.enabled !== false).length;
      const toolsOn = state.tools.filter((t) => t.enabled !== false).length;
      html =
        '<div class="ins-section"><div class="ins-label">概览</div><div class="ins-card">' +
        '<div class="kv"><span class="k">MOD</span><span class="v">' + state.mods.length + " 个（启用 " + enabled + "）</span></div>" +
        '<div class="kv"><span class="k">工具</span><span class="v">' + state.tools.length + " 个（启用 " + toolsOn + "）</span></div>" +
        "</div></div>" +
        '<div class="ins-section"><div class="ins-label">风险分级</div><div class="ins-card">' +
        '<div class="kv"><span class="k">' + riskBadge("read") + '</span><span class="v">自动执行</span></div>' +
        '<div class="kv"><span class="k">' + riskBadge("write") + '</span><span class="v">需审批（按需模式）</span></div>' +
        '<div class="kv"><span class="k">' + riskBadge("dangerous") + '</span><span class="v">默认关闭</span></div></div></div>';
    } else if (act === "automation") {
      title = "自动化";
      html = '<div class="ins-section"><div class="ins-label">状态</div><div class="ins-card">' +
        '<div class="kv"><span class="k">available</span><span class="v mono">false</span></div>' +
        '<div class="kv"><span class="k">reason</span><span class="v mono">automation_api_pending</span></div></div></div>';
    } else {
      title = "设置";
      html =
        '<div class="ins-section"><div class="ins-label">当前模式</div><div class="ins-card">' +
        '<div class="kv"><span class="k">主题</span><span class="v">' + esc(state.theme) + " → " + esc(state.themeResolved) + "</span></div>" +
        '<div class="kv"><span class="k">模型</span><span class="v mono">' + esc(state.model || "—") + "</span></div>" +
        '<div class="kv"><span class="k">审批</span><span class="v">' + approvalLabel() + "</span></div></div></div>";
    }
    $("#ins-title").textContent = title;
    $("#ins-scroll").innerHTML = html;
  }

  /* ==================== 底部 Panel ==================== */
  function renderPanel(scrollToEnd) {
    const body = $("#panel-body");
    $$(".panel-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.panelTab === state.panelTab)));
    let rows = [];
    if (state.panelTab === "events") {
      rows = state.events.map((e) => {
        let kind = e.kind || "info";
        if (e.name === "error") kind = "error";
        else if (e.name === "aborted") kind = "aborted";
        else if (e.name === "final") kind = "final";
        else if (e.name === "approval_required") kind = "approval";
        return '<div class="ev" data-kind="' + kind + '"><span class="ev-time">' + e.t + '</span><span class="ev-name">' + esc(e.name) + '</span><span class="ev-data">' + esc(e.data) + "</span></div>";
      });
    } else if (state.panelTab === "sandbox") {
      rows = state.sandbox.map((e) => '<div class="ev"><span class="ev-time">' + e.t + '</span><span class="ev-data">' + esc(e.line) + "</span></div>");
    } else {
      rows = state.logs.map((e) => '<div class="ev" data-kind="' + (e.level === "error" ? "error" : e.level === "warn" ? "approval" : "info") + '"><span class="ev-time">' + e.t + '</span><span class="ev-data">' + esc(e.line) + "</span></div>");
    }
    body.innerHTML = rows.length ? rows.join("") : '<div class="panel-empty">暂无内容</div>';
    if (scrollToEnd !== false) body.scrollTop = body.scrollHeight;
  }

  /* ==================== 任务 / ReAct 时间线 ==================== */
  function nodeDot(type) {
    const map = { plan: ICON.plan, thought: ICON.brain, tool_call: ICON.terminal, tool_result: ICON.check, approval: ICON.warn, final: ICON.check, error: ICON.x, aborted: ICON.x };
    return map[type] || ICON.spark;
  }

  function renderTimeline(run, container) {
    const events = (run && run.events) || (run && run.timeline) || [];
    if (!events.length) {
      container.innerHTML = '<div class="panel-empty">运行事件流为空</div>';
      return;
    }
    container.innerHTML = '<div class="timeline">' + events.map((node) => {
      const type = node.type || node.name || "event";
      let extra = "";
      if (type === "tool_call") {
        extra = '<div class="call-card"><div class="cc-head"><span class="mono">' + esc(node.tool || node.name) + ".call</span></div>" +
          "<pre>" + esc(JSON.stringify(node.args || node.params || {}, null, 2)) + "</pre>" + "</div>";
      } else if (type === "approval_required" || type === "approval") {
        extra = '<div class="approval-card"><div class="approval-head">' + ICON.warn + "工具调用等待批准</div>" +
          '<div class="approval-body">' +
          '<div class="kv"><span class="k">工具</span><span class="v mono">' + esc(node.tool || "") + "</span></div>" +
          '<div class="kv"><span class="k">风险</span><span class="v">' + riskBadge(node.risk) + "</span></div>" +
          '<div class="kv"><span class="k">范围</span><span class="v mono">' + esc(node.scope || "") + "</span></div>" +
          "</div>" +
          '<div class="approval-actions">' +
          '<button class="btn sm primary" data-approval="approved">批准</button>' +
          '<button class="btn sm danger" data-approval="rejected">拒绝</button>' +
          '<button class="btn sm" data-approval="aborted">中止</button>' +
          '<div class="grow"></div></div></div>';
      }
      return '<div class="tnode" data-type="' + esc(type) + '"><div class="dot">' + nodeDot(type) + '</div>' +
        '<div class="tnode-head"><span class="tnode-label">' + esc(node.label || type) + "</span>" +
        (node.risk ? riskBadge(node.risk) : "") +
        (node.time ? '<span class="tnode-time">' + esc(node.time) + "</span>" : "") + "</div>" +
        '<div class="tnode-body">' + esc(node.text || node.message || "") + extra + "</div></div>";
    }).join("") + "</div>";
  }

  function renderTasks() {
    const run = state.runs.find((x) => x.id === state.runId) || state.runs[0] || {};
    $("#task-sub").textContent = run.id ? run.id + " · " + (run.title || "") : "无运行";
    $("#task-status-chip").textContent = run.status || "—";
    $("#task-body").innerHTML = '<div id="task-timeline-wrap"><div class="panel-empty">加载中…</div></div>';
    renderTimeline(run, $("#task-timeline-wrap"));
  }

  async function handleApproval(action) {
    if (!state.pendingApproval) { toast("没有待审批项", true); return; }
    const payload = {
      run_id: state.pendingApproval.run_id,
      approval_id: state.pendingApproval.approval_id || state.pendingApproval.id,
      action, // "approved" | "rejected" | "aborted"
    };
    try {
      await API.approveAgent(payload);
      pushEvent("approval_" + action, payload, "approval");
      toast(action === "approved" ? "已批准" : action === "rejected" ? "已拒绝" : "已中止");
      if (action === "aborted") state.pendingApproval = null;
    } catch (err) {
      toast(err.message || "审批失败", true);
    }
  }

  async function abortRun() {
    if (!state.pendingApproval) return;
    try {
      await API.abortAgent({ run_id: state.pendingApproval.run_id });
      pushEvent("aborted", {}, "aborted");
      state.pendingApproval = null;
      toast("已中止运行");
    } catch (err) { toast(err.message || "中止失败", true); }
  }

  /* ==================== 扩展 ==================== */
  function renderExt() {
    const body = $("#ext-body");
    const enabledMods = state.mods.filter((m) => m.enabled !== false);
    body.innerHTML =
      '<div class="section-title">已加载 MOD <span class="chip">' + state.mods.length + "</span></div>" +
      (state.mods.length
        ? '<div class="ext-grid">' + state.mods.map((m) =>
            '<div class="mod-card"><div class="mod-top"><div class="mod-ico">' + ICON.spark + '</div><div class="grow" style="min-width:0">' +
            '<div class="mod-title">' + esc(m.name || m.id) + '</div><div class="mod-id">' + esc(m.id) + "</div></div>" +
            '<button class="switch" data-mod="' + esc(m.id) + '" aria-checked="' + (m.enabled !== false) + '" role="switch"></button></div>' +
            '<div class="mod-desc">' + esc(m.desc || "") + "</div><div class=\"mod-foot\"><div class=\"grow\"></div><span class=\"chip " + (m.enabled !== false ? "ok" : "") + '">' + (m.enabled !== false ? "已启用" : "已停用") + "</span></div></div>"
          ).join("") + "</div>"
        : '<div class="panel-empty">加载中…</div>') +
      '<div class="section-title">工具与风险分级</div>' +
      (state.tools.length
        ? '<table class="tool-table"><thead><tr><th>工具</th><th>说明</th><th>风险</th><th>状态</th></tr></thead><tbody>' +
          state.tools.map((t) =>
            "<tr><td class='mono'>" + esc(t.name) + "</td><td>" + esc(t.desc || "") + "</td><td>" + riskBadge(t.risk || "read") + "</td>" +
            "<td><button class=\"switch\" data-tool=\"" + esc(t.name) + "\" aria-checked=\"" + (t.enabled !== false) + "\" role=\"switch\"></button></td></tr>"
          ).join("") + "</tbody></table>"
        : '<div class="panel-empty">加载中…</div>');
  }

  /* ==================== 设置 ==================== */
  const SETTINGS_LABEL = { provider: "服务商与模型", chat: "对话参数", workspace: "工作目录", appearance: "外观" };

  function renderSettings() {
    const nav = $("#set-nav");
    const current = SETTINGS_LABEL[state.settingsSection || "provider"] ? (state.settingsSection || "provider") : "provider";
    nav.innerHTML = '<button class="set-nav-item" data-settings-jump="provider" aria-current="' + (current === "provider") + '">服务商与模型</button>' +
      '<button class="set-nav-item" data-settings-jump="chat" aria-current="' + (current === "chat") + '">对话参数</button>' +
      '<button class="set-nav-item" data-settings-jump="workspace" aria-current="' + (current === "workspace") + '">工作目录</button>' +
      '<button class="set-nav-item" data-settings-jump="appearance" aria-current="' + (current === "appearance") + '">外观</button>';
    state.settingsSection = current;
    const panel = $("#settings-panel");
    if (current === "provider") {
      panel.innerHTML = '<div class="panel-inner"><h2 class="set-h2">服务商与模型</h2><p class="set-desc">在下方选择默认模型。完整的服务商配置请到 <code>/</code> 主界面。</p>' +
        '<div class="set-card"><h3 class="set-card-title">默认模型</h3>' +
        '<div class="field"><span class="field-label">模型</span>' +
        '<select class="field-select" id="set-model">' +
        (state.models.length
          ? state.models.map((m) => '<option value="' + esc(m.value || m) + '"' + (state.model === (m.value || m) ? " selected" : "") + ">" + esc(m.label || m) + "</option>").join("")
          : '<option value="">加载中…</option>') +
        "</select></div>" +
        '<div class="inline-actions"><button class="btn sm primary" data-settings-action="save-model">保存</button></div></div></div>';
      const sel = $("#set-model");
      sel.addEventListener("change", () => { state.model = sel.value; persist(); });
      $("#set-model").value = state.model;
    } else if (current === "chat") {
      panel.innerHTML = '<div class="panel-inner"><h2 class="set-h2">对话参数</h2><p class="set-desc">对话模式与 Agent 模式的切换。</p>' +
        '<div class="set-card"><h3 class="set-card-title">默认模式</h3>' +
        '<div class="inline-actions">' +
        '<button class="btn sm' + (state.mode === "chat" ? " primary" : "") + '" data-mode-pref="chat">对话</button>' +
        '<button class="btn sm' + (state.mode === "agent" ? " primary" : "") + '" data-mode-pref="agent">Agent</button>' +
        "</div></div></div>";
      $$("[data-mode-pref]").forEach((b) => b.addEventListener("click", () => {
        state.mode = b.dataset.modePref; persist(); applyChatModelPill(); updateStatusbar(); renderSettings(); toast("默认模式: " + state.mode);
      }));
    } else if (current === "workspace") {
      panel.innerHTML = '<div class="panel-inner"><h2 class="set-h2">工作目录</h2>' +
        '<div class="set-card"><h3 class="set-card-title">当前状态</h3>' +
        '<div class="kv"><span class="k">路径</span><span class="v mono" style="word-break:break-all">' + esc(state.workspace.path || "（未选择）") + "</span></div>" +
        '<div class="kv"><span class="k">状态</span><span class="v">' + (state.workspace.configured ? (state.workspace.exists ? chipOk("已配置") : chipDanger("缺失")) : chipWarn("未配置")) + "</span></div>" +
        '<div class="inline-actions" style="margin-top:10px"><button class="btn sm primary" data-settings-action="pick-workspace">选择目录</button>' +
        '<button class="btn sm ghost" data-settings-action="clear-workspace" style="color:var(--danger)">清除</button></div></div></div>';
    } else if (current === "appearance") {
      panel.innerHTML = '<div class="panel-inner"><h2 class="set-h2">外观</h2>' +
        '<div class="set-card"><h3 class="set-card-title">主题</h3>' +
        '<div class="theme-cards">' +
        [["system", "跟随系统"], ["light", "浅色"], ["dark", "深色"]].map((o) =>
          '<button class="theme-card" data-theme-pref="' + o[0] + '" aria-pressed="' + (state.theme === o[0]) + '">' + o[1] + "</button>"
        ).join("") +
        "</div></div></div>";
      $$("[data-theme-pref]").forEach((b) => b.addEventListener("click", () => {
        state.theme = b.dataset.themePref; persist(); applyTheme(); renderInspector(); renderSettings(); toast("主题已切换");
      }));
    }
    $$("[data-settings-action]", panel).forEach((b) => {
      b.addEventListener("click", () => handleSettingsAction(b.dataset.settingsAction));
    });
  }

  function openSettings(section) {
    state.settingsSection = section || "provider";
    if (state.activity !== "settings") setActivity("settings");
    else renderSettings();
  }

  function handleSettingsAction(action) {
    if (action === "pick-workspace") return openWorkspacePicker();
    if (action === "clear-workspace") { clearWorkspace(); renderSettings(); renderSidebar(); return; }
    if (action === "save-model") { toast("模型已保存"); return; }
  }

  /* ==================== 状态栏 ==================== */
  function updateStatusbar() {
    const waiting = !!state.pendingApproval;
    $("#status-dot").className = "status-dot" + (waiting ? " running" : "");
    $("#status-text").textContent = waiting ? "等待审批" : "空闲";
    $("#status-mode").textContent = state.mode === "agent" ? "Agent" : "对话";
    $("#status-model").value = state.model;
    $("#status-approval").value = state.approval;
  }

  function applyChatModelPill() {
    $$("#comp-mode button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
  }

  /* ==================== 命令面板 ==================== */
  function openPalette() { $("#pal-backdrop").classList.add("open"); setTimeout(() => $("#pal-input").focus(), 30); }
  function closePalette() { $("#pal-backdrop").classList.remove("open"); }

  /* ==================== 抽屉控制 ==================== */
  function toggleSidebar(force) {
    const next = typeof force === "boolean" ? force : document.body.dataset.sidebar !== "expanded";
    document.body.dataset.sidebar = next ? "expanded" : "collapsed";
    $("#drawer-backdrop").classList.toggle("open", next && window.innerWidth <= 1023);
  }
  function toggleInspector(force) {
    const next = typeof force === "boolean" ? force : document.body.dataset.inspector !== "expanded";
    document.body.dataset.inspector = next ? "expanded" : "collapsed";
  }
  function togglePanel(force) {
    const next = typeof force === "boolean" ? force : document.body.dataset.panel !== "expanded";
    document.body.dataset.panel = next ? "expanded" : "collapsed";
    if (next) renderPanel(true);
  }
  function closeDrawers() {
    if (window.innerWidth <= 1023) document.body.dataset.sidebar = "collapsed";
    if (window.innerWidth <= 1180) document.body.dataset.inspector = "collapsed";
    $("#drawer-backdrop").classList.remove("open");
  }

  /* ==================== 数据加载 ==================== */
  async function loadAll() {
    const tasks = [];
    tasks.push(API.listSessions().then((list) => {
      state.sessions = list || [];
      // 选一个默认会话
      const first = state.sessions.find((s) => s.message_count > 0);
      state.sessionId = state.sessionId || (first ? first.id : null) || (state.sessions[0] && state.sessions[0].id);
    }).catch(() => { state.sessions = []; }));

    tasks.push(API.listAgentTasks().then((list) => {
      state.runs = list || [];
      // 找是否有待审批
      const pending = state.runs.find((r) => r.status === "waiting_approval");
      if (pending) state.pendingApproval = pending;
      state.runId = state.runId || (pending && pending.id) || (state.runs[0] && state.runs[0].id);
    }).catch(() => { state.runs = []; }));

    tasks.push(API.listMods().then((list) => { state.mods = list || []; }).catch(() => { state.mods = []; }));
    tasks.push(API.agentTools().then((list) => { state.tools = list || []; }).catch(() => { state.tools = []; }));

    // 模型列表：先尝试从 providers 端点
    tasks.push(API.listProviders().then((data) => {
      const blocks = (data && data.blocks) || [];
      const availableModels = [];
      blocks.forEach((b) => {
        (b.models || []).forEach((m) => {
          availableModels.push({ value: m, label: m });
        });
      });
      if (!availableModels.length && state.model) {
        availableModels.push({ value: state.model, label: state.model });
      }
      state.models = availableModels;
      // 填充两个模型下拉框
      const modelOpts = availableModels.length
        ? availableModels.map((m) => '<option value="' + esc(m.value) + '">' + esc(m.label) + "</option>").join("")
        : '<option value="">—</option>';
      ["#comp-model", "#status-model"].forEach((sel) => {
        const el = $(sel); if (el) el.innerHTML = modelOpts;
      });
      // 确保 state.model 在列表里
      if (!availableModels.find((m) => m.value === state.model) && availableModels.length) {
        state.model = availableModels[0].value; persist();
      }
      $("#comp-model").value = state.model || "";
      $("#status-model").value = state.model || "";
      $("#status-provider").textContent = "服务商 " + ((data && data.provider) || "—");
    }).catch(() => { state.models = []; }));

    // 拉取当前会话的消息（如果有）
    await Promise.all(tasks);

    if (state.sessionId) {
      try {
        const s = await API.getSession(state.sessionId);
        state.sessionMessages = (s && s.messages) || [];
      } catch {
        state.sessionMessages = [];
      }
    }

    loadWorkspace();
  }

  /* ==================== 事件绑定 ==================== */
  function bindAll() {
    $$(".act-btn[data-activity]").forEach((b) => b.addEventListener("click", () => setActivity(b.dataset.activity)));

    $("#side-scroll").addEventListener("click", (e) => {
      const b = e.target.closest("[data-session]");
      if (b) { state.sessionId = b.dataset.session; state.sessionMessages = []; API.getSession(state.sessionId).then((s) => { state.sessionMessages = (s && s.messages) || []; renderChat(); }).catch(() => {}); renderSidebar(); renderChat(); renderInspector(); return; }
      const r = e.target.closest("[data-run]");
      if (r) { state.runId = r.dataset.run; state.pendingApproval = null; renderTasks(); renderSidebar(); renderInspector(); return; }
      const s = e.target.closest("[data-settings-jump]");
      if (s) { openSettings(s.dataset.settingsJump); return; }
      const m = e.target.closest("[data-mod]");
      if (m) API.toggleMod(m.dataset.mod, true).then(() => toast("MOD 状态已更新")).catch(() => toast("切换失败", true));
    });

    $("#side-action").addEventListener("click", () => {
      if (state.activity === "chat") {
        API.createSession().then((s) => {
          state.sessions.unshift(s);
          state.sessionId = s.id;
          state.sessionMessages = [];
          persist();
          renderSidebar(); renderChat(); renderInspector();
          toast("新对话已创建");
        }).catch((err) => toast(err.message || "创建失败", true));
      } else if (state.activity === "tasks") { loadAll().then(() => { renderSidebar(); renderTasks(); toast("已刷新"); }); }
      else if (state.activity === "ext") { loadAll().then(() => { renderSidebar(); renderExt(); toast("已重新扫描"); }); }
    });

    $("#side-search-input").addEventListener("input", (e) => { state.sessionQuery = e.target.value; renderSidebar(); });

    // 工作目录入口
    ["#side-ws-chip", "#status-ws", "#lock-select"].forEach((sel) => {
      const el = $(sel); if (el) el.addEventListener("click", openWorkspacePicker);
    });

    // 发送
    $("#composer-input").addEventListener("input", (e) => { estimateTokens(e.target.value); syncComposer(); });
    $("#composer-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    $("#comp-send").addEventListener("click", sendMessage);
    $("#comp-mode").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-mode]"); if (b) { state.mode = b.dataset.mode; persist(); applyChatModelPill(); renderChat(); updateStatusbar(); renderInspector(); }
    });
    $("#comp-model").addEventListener("change", (e) => { state.model = e.target.value; persist(); updateStatusbar(); renderChat(); renderInspector(); });

    // 状态栏
    $("#status-model").addEventListener("change", (e) => { state.model = e.target.value; persist(); $("#comp-model").value = state.model; updateStatusbar(); renderChat(); });
    $("#status-approval").addEventListener("change", (e) => { state.approval = e.target.value; persist(); renderInspector(); });

    // 面板/抽屉开关
    $("#panel-close").addEventListener("click", () => togglePanel(false));
    $("#status-panel").addEventListener("click", () => togglePanel());
    $("#act-toggle-inspector").addEventListener("click", () => toggleInspector());
    $("#status-inspector").addEventListener("click", () => toggleInspector());
    $("#ins-close").addEventListener("click", () => toggleInspector(false));
    $("#act-theme").addEventListener("click", toggleTheme);
    $("#act-exit").addEventListener("click", () => { location.href = "/"; });
    $("#chat-cmdk").addEventListener("click", openPalette);
    $("#drawer-backdrop").addEventListener("click", closeDrawers);

    $("#panel-clear").addEventListener("click", () => {
      if (state.panelTab === "events") state.events = [];
      else if (state.panelTab === "sandbox") state.sandbox = [];
      else state.logs = [];
      renderPanel(false);
    });
    $$(".panel-tab").forEach((b) => b.addEventListener("click", () => { state.panelTab = b.dataset.panelTab; renderPanel(true); }));

    $("#task-refresh").addEventListener("click", () => { loadAll().then(() => { renderTasks(); renderSidebar(); }); });
    $("#ext-refresh").addEventListener("click", () => { loadAll().then(() => { renderExt(); renderSidebar(); }); });

    $("#task-body").addEventListener("click", (e) => {
      const ap = e.target.closest("[data-approval]"); if (ap) { handleApproval(ap.dataset.approval); return; }
    });

    // 工作目录选择器
    $("#wp-close").addEventListener("click", closeWorkspacePicker);
    $("#wp-cancel").addEventListener("click", closeWorkspacePicker);
    $("#wp-backdrop").addEventListener("click", (e) => { if (e.target === $("#wp-backdrop")) closeWorkspacePicker(); });
    $("#wp-up").addEventListener("click", async () => {
      const data = await API.browseWorkspace(state.wpPath); if (data && data.ok && data.parent) { state.wpPath = data.parent; renderWorkspacePicker(); }
    });
    $("#wp-roots").addEventListener("click", (e) => {
      const b = e.target.closest("[data-wp-root]"); if (b) { state.wpPath = b.dataset.wpRoot; renderWorkspacePicker(); }
    });
    $("#wp-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-wp-dir]"); if (b) { state.wpPath = b.dataset.wpDir; renderWorkspacePicker(); }
    });
    $("#wp-go").addEventListener("click", () => {
      const raw = $("#wp-manual").value.trim(); if (!raw) return; state.wpPath = raw.replace(/\//g, "\\"); renderWorkspacePicker();
    });
    $("#wp-use").addEventListener("click", async () => {
      const ok = await setWorkspace(state.wpPath); if (ok) closeWorkspacePicker();
    });
    $("#wp-clear").addEventListener("click", async () => { await clearWorkspace(); closeWorkspacePicker(); });

    // 快捷键
    document.addEventListener("keydown", (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (e.key === "Escape") {
        if ($("#pal-backdrop").classList.contains("open")) { closePalette(); e.preventDefault(); return; }
        if ($("#wp-backdrop").classList.contains("open")) { closeWorkspacePicker(); e.preventDefault(); return; }
        closeDrawers(); return;
      }
      if (!mod) return;
      const key = e.key.toLowerCase();
      if (key === "k") { e.preventDefault(); openPalette(); return; }
      if (key === "b") { e.preventDefault(); toggleSidebar(); return; }
      if (key === "j") { e.preventDefault(); togglePanel(); return; }
      if (key === "i") { e.preventDefault(); toggleInspector(); return; }
      if (e.key === ",") { e.preventDefault(); openSettings(state.settingsSection); return; }
      const map = { "1": "chat", "2": "tasks", "3": "ext", "4": "automation" };
      if (map[key]) { e.preventDefault(); setActivity(map[key]); }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth <= 1023) { document.body.dataset.sidebar = "collapsed"; document.body.dataset.panel = "collapsed"; }
      $("#drawer-backdrop").classList.toggle("open", document.body.dataset.sidebar === "expanded" && window.innerWidth <= 1023);
      if (window.innerWidth <= 1180) document.body.dataset.inspector = "collapsed";
    });
  }

  /* ==================== 初始化 ==================== */
  async function init() {
    applyTheme();
    // 初始化窗口形态
    if (window.innerWidth <= 1023) {
      document.body.dataset.sidebar = "collapsed"; document.body.dataset.inspector = "collapsed"; document.body.dataset.panel = "collapsed";
    } else if (window.innerWidth <= 1180) {
      document.body.dataset.inspector = "collapsed"; document.body.dataset.panel = "collapsed";
    } else {
      document.body.dataset.panel = "collapsed";
    }

    // 先渲染骨架
    renderSidebar();
    renderChat();
    renderInspector();
    applyChatModelPill();
    updateStatusbar();
    estimateTokens("");
    syncComposer();

    // 拉真实数据
    bindAll();
    try {
      await loadAll();
    } catch (err) {
      pushLog("initial load failed: " + err.message, "error");
      toast("部分数据加载失败", true);
    }

    // 重渲染
    renderSidebar();
    renderChat();
    renderInspector();
    renderPanel(true);
    updateStatusbar();
  }

  init();
})();
