/* ========================================================
   SimChat IDE · VSCode 风格六区布局
   Activity Bar: Explorer / Search / Agent / Extensions / Debug / Settings
   中央: 标签页 + 代码编辑器
   底部: Panel (Chat / 事件流 / 沙箱 / 日志)
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
    folderOpen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v2H3z"/><path d="M3 11h18l-1.6 7.2A2 2 0 0 1 17.5 20H5.5a2 2 0 0 1-1.9-1.3z"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
    plan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h10M4 18h7"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5a3 3 0 0 0-3 3 3 3 0 0 0-1 5.8A3 3 0 0 0 8 19h1a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Z"/><path d="M15 5a3 3 0 0 1 3 3 3 3 0 0 1 1 5.8A3 3 0 0 1 16 19h-1a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/></svg>',
    terminal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12 5 5L20 6"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.5 20h19Z"/><path d="M12 9v5M12 17.2v.1"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.2 14.1 9.9 20.8 12 14.1 14.1 12 20.8 9.9 14.1 3.2 12 9.9 9.9Z"/></svg>',
    chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
  };

  /* ==================== 状态 ==================== */
  const STORE_KEY = "simchat_ide_state_v1";
  function readStore() { try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch { return {}; } }
  function writeStore(patch) { try { localStorage.setItem(STORE_KEY, JSON.stringify(Object.assign(readStore(), patch))); } catch {} }

  const state = {
    activity: "explorer",
    sessionId: null,
    sessions: [],
    sessionMessages: [],
    runId: null,
    runs: [],
    mods: [],
    tools: [],
    theme: readStore().theme || "system",
    themeResolved: "light",
    model: readStore().model || "",
    models: [],
    approval: readStore().approval || "on_demand",
    mode: readStore().mode || "chat",
    sessionQuery: "",
    panelTab: "chat",
    events: [], sandbox: [], logs: [],
    pendingApproval: null,
    workspace: { configured: false, exists: false, path: "", name: "" },
    wpPath: "",
    paletteIndex: 0, paletteHits: [],
    editorFiles: [],
    editorActive: null,
    editorCache: {},
    fileTree: null,
    fileTreeExpanded: {}, // { [path]: true } 手动管理展开的目录集合
    settingsSection: "provider",
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
    if (state.panelTab === "events") renderPanel();
  }
  function pushLog(line, level) {
    state.logs.push({ t: nowTime(), line, level: level || "info" });
    if (state.logs.length > 200) state.logs.shift();
    if (state.panelTab === "logs") renderPanel();
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
  function fileIconClass(filename) {
    const ext = (filename.split(".").pop() || "").toLowerCase();
    return ["py", "js", "html", "css", "md", "json"].includes(ext) ? ext : "";
  }
  function fileSvgIcon(filename) {
    const ext = fileIconClass(filename);
    if (!ext) return '<span class="ft-icon">' + ICON.file + "</span>";
    return '<span class="et-icon ' + ext + '">' + ICON.file + "</span>";
  }

  /* ==================== Activity 元数据 ==================== */
  const ACT_META = {
    explorer:   { title: "资源管理器", action: "refresh",  search: false },
    search:     { title: "搜索",       action: "",         search: false },
    agent:      { title: "Agent 与会话", action: "new-chat", search: true },
    extensions: { title: "扩展",       action: "refresh",  search: false },
    debug:      { title: "调试",       action: "",         search: false },
    settings:   { title: "设置",       action: "",         search: false },
  };

  /* ==================== 侧栏：文件树 ==================== */
  function renderFileTree() {
    if (!state.fileTree || !state.fileTree.entries) {
      return '<div class="panel-empty">' +
        (state.workspace.configured
          ? '文件树加载失败'
          : '请先在底部状态栏选择工作目录') +
        '</div>';
    }
    return '<div class="file-tree" id="file-tree-root">' + renderFileGroup(state.fileTree.entries, 1, state.fileTree.path) + "</div>";
  }

  function renderFileGroup(entries, level, parentPath) {
    // 排序：目录在前，文件在后；各自按名称排序
    const sorted = [...entries].sort((a, b) => {
      if (!!b.is_dir !== !!a.is_dir) return a.is_dir ? -1 : 1;
      return (a.name || "").localeCompare(b.name || "");
    });
    const html = sorted.map((en) => {
      const isOpen = !!state.fileTreeExpanded[en.path];
      const hasChildren = en.is_dir;
      let childrenHtml = "";
      if (hasChildren && isOpen) {
        // 展开的目录：递归加载子条目
        const children = state.fileTreeCache && state.fileTreeCache[en.path];
        if (children && children.entries) {
          childrenHtml = '<div class="ft-group" data-level="' + level + '">' + renderFileGroup(children.entries, level + 1, en.path) + "</div>";
        } else {
          childrenHtml = '<div class="ft-group" data-level="' + level + '"><div class="ft-item" style="color:var(--text-faint)">加载中…</div></div>';
        }
      }
      const icon = en.is_dir
        ? (isOpen ? ICON.folderOpen : ICON.folder)
        : (fileIconClass(en.name) ? '<span class="et-icon ' + fileIconClass(en.name) + '">' + ICON.file + '</span>' : ICON.file);
      return '<div>' +
        '<div class="ft-item' + (state.editorActive === en.path ? '" data-active="true"' : '"') +
        ' data-ft-path="' + esc(en.path) + '" data-ft-isdir="' + (en.is_dir ? "true" : "false") + '">' +
          (hasChildren ? '<span class="ft-arrow' + (isOpen ? " open" : "") + '">' + ICON.chevron + "</span>" : '<span style="width:14px"></span>') +
          '<span class="ft-icon">' + icon + "</span>" +
          '<span class="ft-name">' + esc(en.name) + "</span>" +
        "</div>" +
        childrenHtml +
      "</div>";
    }).join("");
    return html;
  }

  async function toggleDir(path) {
    const willOpen = !state.fileTreeExpanded[path];
    if (willOpen) {
      state.fileTreeExpanded[path] = true;
      // 如果缓存里没有子条目，就去 fetch
      if (!state.fileTreeCache) state.fileTreeCache = {};
      if (!state.fileTreeCache[path]) {
        try {
          const data = await API.browseWorkspace(path);
          if (data && data.ok) state.fileTreeCache[path] = data;
        } catch {}
      }
    } else {
      delete state.fileTreeExpanded[path];
    }
    renderSidebar();
  }

  async function refreshFileTree() {
    if (!state.workspace.configured || !state.workspace.path) { toast("请先选择工作目录", true); return; }
    try {
      const data = await API.browseWorkspace(state.workspace.path);
      if (data && data.ok) {
        state.fileTree = data;
        state.fileTreeExpanded = {};
        state.fileTreeCache = {};
        // 默认展开根目录
        state.fileTreeExpanded[state.workspace.path] = true;
        renderSidebar();
        toast("文件树已刷新");
      }
    } catch (err) {
      toast("刷新失败: " + err.message, true);
    }
  }

  /* ==================== 侧栏：Agent activity ==================== */
  function sessionItem(s) {
    const mode = s.agent_capable ? "agent" : "chat";
    return '<button class="list-item" data-session="' + esc(s.id) + '" aria-current="' + (s.id === state.sessionId) + '">' +
      '<div class="li-top"><span class="li-title">' + esc((s.title || "").slice(0, 32) || "—") + '</span><span class="li-time">' + esc(s.updated_at || "") + "</span></div>" +
      '<div class="li-preview">' + esc((s.preview || s.title || "").slice(0, 60)) + "</div>" +
      '<div class="li-meta"><span class="chip">' + esc(mode) + '</span><span class="chip">' + (s.message_count || 0) + " 条</span></div></button>";
  }

  function agentActivityHtml() {
    const q = state.sessionQuery.trim().toLowerCase();
    const filtered = state.sessions.filter((s) => !q || (s.title || "").toLowerCase().includes(q));
    let html = '<div class="side-section">会话</div>';
    html += filtered.length ? filtered.map(sessionItem).join("") : '<div class="panel-empty">暂无会话</div>';
    // Agent 运行列表
    if (state.runs.length) {
      html += '<div class="side-section" style="margin-top:8px">运行记录</div>';
      html += state.runs.map((r) =>
        '<button class="list-item" data-run="' + esc(r.id) + '" aria-current="' + (r.id === state.runId) + '">' +
          '<div class="li-top"><span class="li-title">' + esc((r.title || r.id).slice(0, 40)) + '</span><span class="li-time">' + esc(r.updated_at || "") + "</span></div>" +
          '<div class="li-meta"><span class="chip dot">' + esc(r.status || "unknown") + '</span></div></button>'
      ).join("");
    }
    return html;
  }

  /* ==================== 侧栏：Extensions activity ==================== */
  function extensionsActivityHtml() {
    let html = '<div class="side-section">MOD</div>' +
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
    return html;
  }

  /* ==================== 侧栏：Settings activity ==================== */
  function settingsActivityHtml() {
    const jump = (key, label) => '<button class="list-item" data-settings-jump="' + key + '"><div class="li-top"><span class="li-title">' + label + '</span></div></button>';
    return '<div class="side-section">设置导航</div>' +
      jump("provider", "服务商与模型") +
      jump("chat", "对话参数") +
      jump("workspace", "工作目录") +
      jump("appearance", "外观");
  }

  /* ==================== 侧栏主渲染 ==================== */
  function renderSidebar() {
    const meta = ACT_META[state.activity];
    $("#side-title").textContent = meta.title;
    $("#side-action").style.display = meta.action ? "" : "none";
    $("#side-search").style.display = meta.search ? "" : "none";
    $("#side-search-input").placeholder = state.activity === "agent" ? "搜索会话…" : "搜索…";

    let html = "";
    let sub = "";
    if (state.activity === "explorer") {
      html = renderFileTree();
      sub = state.workspace.configured ? state.workspace.path : "未选择工作目录";
    } else if (state.activity === "search") {
      html = '<div class="panel-empty">全局搜索 API 未接入<br><span style="font-size:11px;color:var(--text-faint)">search_api_pending</span></div>';
      sub = "未接入";
    } else if (state.activity === "agent") {
      html = agentActivityHtml();
      sub = state.sessions.length + " 个会话" + (state.runs.length ? " · " + state.runs.length + " 次运行" : "");
    } else if (state.activity === "extensions") {
      html = extensionsActivityHtml();
      sub = state.mods.length + " MOD · " + state.tools.length + " 工具";
    } else if (state.activity === "debug") {
      html = '<div class="panel-empty">调试面板占位<br><span style="font-size:11px;color:var(--text-faint)">debug_api_pending</span></div>';
      sub = "未接入";
    } else if (state.activity === "settings") {
      html = settingsActivityHtml();
      sub = "设置";
    }
    $("#side-sub").textContent = sub;
    $("#side-scroll").innerHTML = html;
  }

  /* ==================== Activity 切换 ==================== */
  function setActivity(activity) {
    if (!activity || activity === state.activity) return;
    state.activity = activity;
    document.body.dataset.activity = activity;
    $$(".act-btn[data-activity]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.activity === activity)));
    renderSidebar();
    renderInspector();
    pushEvent("activity_switch", { to: activity });
  }

  /* ==================== 编辑器 ==================== */
  function renderEditorSurface() {
    const surface = $("#editor-surface");
    if (state.editorActive) {
      const file = state.editorFiles.find((f) => f.path === state.editorActive);
      if (!file) { renderEditorEmpty(); return; }
      const cache = state.editorCache[file.path];
      const content = cache ? cache.content : "// 加载中…";
      const lines = content.split("\n");
      const gutter = lines.map((_, i) => "<div>" + (i + 1) + "</div>").join("");
      surface.innerHTML =
        '<div class="editor-gutter">' + gutter + '</div>' +
        '<div class="editor-code">' + esc(content) + "</div>";
    } else {
      renderEditorEmpty();
    }
  }

  function renderEditorEmpty() {
    const surface = $("#editor-surface");
    surface.innerHTML =
      '<div class="editor-empty">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 9h8M8 13h5"/></svg>' +
        "<h3>欢迎使用 SimChat IDE</h3>" +
        "<p>选择左侧资源管理器中的文件开始编辑</p>" +
        '<p style="font-size:11px;color:var(--text-faint)">Ctrl+E 切换资源管理器 · Ctrl+J 打开底部 Chat Panel</p>' +
      "</div>";
  }

  function renderEditorTabs() {
    const tabs = $("#editor-tabs");
    if (!state.editorFiles.length) { tabs.innerHTML = ""; return; }
    tabs.innerHTML = state.editorFiles.map((f) =>
      '<button class="editor-tab' + (state.editorActive === f.path ? " active" : "") + '" data-editor-tab="' + esc(f.path) + '">' +
        '<span class="et-icon ' + f.icon + '">' + ICON.file + "</span>" +
        '<span class="et-name">' + esc(f.name) + "</span>" +
        '<span class="et-close" data-editor-close="' + esc(f.path) + '" title="关闭">×</span>' +
      "</button>"
    ).join("");
  }

  async function openFile(path) {
    // 如果已经打开，直接激活
    const existing = state.editorFiles.find((f) => f.path === path);
    if (existing) {
      state.editorActive = path;
      renderEditorTabs();
      renderEditorSurface();
      renderSidebar();
      return;
    }
    // 从路径推导文件名
    const name = path.split(/[\\/]/).pop();
    const icon = fileIconClass(name);
    state.editorFiles.push({ path, name, icon });
    state.editorActive = path;
    // 先显示 loading 态
    state.editorCache[path] = { content: "// 加载中…", loaded: false };
    renderEditorTabs();
    renderEditorSurface();
    renderSidebar();
    pushEvent("file_opened", { path });
    // 真正读文件
    try {
      const data = await API.readWorkspaceFile(path);
      if (data && data.ok) {
        state.editorCache[path] = { content: data.content, loaded: true };
        // 如果当前激活的还是这个文件，刷新显示
        if (state.editorActive === path) renderEditorSurface();
      }
    } catch (err) {
      state.editorCache[path] = {
        content: "// 文件读取失败\n// " + esc(err.message || "未知错误") + "\n\n// 后端返回：" + (err.body && err.body.error ? esc(err.body.error) : ""),
        loaded: false,
      };
      if (state.editorActive === path) renderEditorSurface();
      pushLog("open file failed: " + path + " → " + (err.message || ""), "error");
    }
  }

  function closeFile(path) {
    const idx = state.editorFiles.findIndex((f) => f.path === path);
    if (idx < 0) return;
    state.editorFiles.splice(idx, 1);
    delete state.editorCache[path];
    if (state.editorActive === path) {
      // 激活相邻 tab
      const next = state.editorFiles[Math.min(idx, state.editorFiles.length - 1)];
      state.editorActive = next ? next.path : null;
    }
    renderEditorTabs();
    renderEditorSurface();
    renderSidebar();
  }

  /* ==================== 底部 Panel：Chat Tab ==================== */
  function renderPanelMessages() {
    const msgEl = $("#panel-chat-messages");
    if (!msgEl) return;
    const list = state.sessionMessages || [];
    if (!list.length) {
      msgEl.innerHTML = '<div class="panel-empty" style="text-align:center;padding:30px 20px">' +
        '<div style="margin-bottom:10px">' + ICON.spark + "</div>" +
        (state.sessionId
          ? '<div>当前会话暂无消息</div><div style="font-size:11px;color:var(--text-faint);margin-top:4px">在下方输入框开始对话</div>'
          : '<div>选择或创建会话后开始对话</div><div style="font-size:11px;color:var(--text-faint);margin-top:4px">在左侧 Agent 面板新建会话</div>') +
      "</div>";
    } else {
      msgEl.innerHTML = list.map((m) => {
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
    }
    msgEl.scrollTop = msgEl.scrollHeight;
    syncComposer();
  }

  function syncComposer() {
    const gate = !(state.workspace.configured && state.workspace.exists);
    const input = $("#panel-composer");
    const send = $("#panel-send");
    const hint = $("#panel-session-hint");
    const lockBanner = $("#panel-lock-banner");
    // 锁定状态
    lockBanner.classList.toggle("hidden", !gate);
    input.disabled = gate || !state.model;
    input.placeholder = gate ? "请先选择工作目录…" : !state.model ? "请先配置模型…" : "在底部对话… (Ctrl+Enter 发送)";
    send.disabled = gate || !state.model || !input.value.trim();
    // 会话提示
    const s = state.sessions.find((x) => x.id === state.sessionId);
    hint.textContent = s
      ? "会话: " + esc((s.title || "未命名").slice(0, 24)) + " · " + state.mode
      : "当前无会话";
    // 模型选择器
    const modelSel = $("#panel-model");
    if (modelSel && modelSel.value !== state.model) modelSel.value = state.model || "";
    // mode pill
    $$("#panel-mode button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
  }

  async function sendMessage() {
    const input = $("#panel-composer");
    const text = input.value.trim();
    if (!text) return;
    if (!(state.workspace.configured && state.workspace.exists)) { toast("请先配置工作目录", true); return; }
    if (!state.model) { toast("请先配置模型", true); return; }

    input.value = "";
    syncComposer();

    state.sessionMessages.push({ role: "user", content: text });
    renderPanelMessages();

    pushEvent(state.mode === "agent" ? "run_started" : "chat_started", { mode: state.mode, model: state.model });

    const msgEl = $("#panel-chat-messages");
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
            msgEl.appendChild(assistantBubble);
          }
          const p = assistantBubble.querySelector("#stream-text");
          if (p) p.textContent += data.text;
          msgEl.scrollTop = msgEl.scrollHeight;
        }
        if (eventName === "approval_required") {
          state.pendingApproval = data;
          toast("Agent 请求审批", false);
          pushEvent("approval_required", data, "approval");
          renderInspector();
        }
        if (eventName === "tool_call") pushEvent("tool_call", data, "info");
        if (eventName === "tool_result") pushEvent("tool_result", data, "info");
        if (eventName === "final" && data.text) {
          state.sessionMessages.push({ role: "assistant", content: data.text });
        }
        if (eventName === "error") pushEvent("error", data, "error");
      });
      pushEvent("final", {}, "final");
      API.listSessions().then((list) => {
        state.sessions = list;
        renderSidebar();
      }).catch(() => {});
    } catch (err) {
      pushLog("chat failed: " + err.message, "error");
      toast("发送失败: " + err.message, true);
    } finally {
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
    // Panel Chat Tab 里的锁定横幅
    const lockBanner = $("#panel-lock-banner");
    if (lockBanner) lockBanner.classList.toggle("hidden", ok);
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
    // 如果工作目录已配置，加载文件树
    if (state.workspace.configured && state.workspace.path) {
      try {
        const data = await API.browseWorkspace(state.workspace.path);
        if (data && data.ok) {
          state.fileTree = data;
          state.fileTreeExpanded = {};
          state.fileTreeCache = {};
          state.fileTreeExpanded[state.workspace.path] = true;
        }
      } catch (err) {
        pushLog("browse workspace failed: " + err.message, "error");
      }
    }
    renderSidebar();
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
    // 清空编辑器 & 重新加载文件树
    state.editorFiles = [];
    state.editorActive = null;
    state.editorCache = {};
    state.fileTree = null;
    state.fileTreeExpanded = {};
    state.fileTreeCache = {};
    updateWorkspaceUI();
    await loadWorkspace();
    renderEditorTabs();
    renderEditorSurface();
    toast("工作目录已设置");
    return true;
  }

  async function clearWorkspace() {
    try {
      state.workspace = await API.clearWorkspace();
    } catch {
      state.workspace = { configured: false, exists: false, path: "", name: "" };
    }
    state.editorFiles = [];
    state.editorActive = null;
    state.editorCache = {};
    state.fileTree = null;
    state.fileTreeExpanded = {};
    state.fileTreeCache = {};
    updateWorkspaceUI();
    renderEditorTabs();
    renderEditorSurface();
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
      '<button class="wp-entry' + (en.is_dir ? "" : " is-file") + '"' + (en.is_dir ? ' data-wp-dir="' + esc(en.path) + '"' : " disabled") + ">" +
      (en.is_dir ? ICON.folder : ICON.file) + '<span class="grow">' + esc(en.name) + "</span>" +
      '<span class="chip" style="font-size:9.5px">' + (en.is_dir ? "目录" : "文件") + "</span></button>"
    ).join("") : '<div class="wp-empty">空目录</div>';
    $("#wp-trunc").classList.toggle("hidden", !data.truncated);
  }

  /* ==================== Inspector ==================== */
  function nodeDot(type) {
    const map = { plan: ICON.plan, thought: ICON.brain, tool_call: ICON.terminal, tool_result: ICON.check, approval: ICON.warn, final: ICON.check, error: ICON.x, aborted: ICON.x };
    return map[type] || ICON.spark;
  }

  function renderTimeline(run) {
    const events = (run && run.events) || (run && run.timeline) || [];
    if (!events.length) return '<div class="panel-empty">运行事件流为空</div>';
    return '<div class="timeline">' + events.map((node) => {
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

  function renderInspector() {
    const act = state.activity;
    let title = "信息";
    let html = "";

    if (act === "explorer") {
      title = "资源管理器";
      html =
        '<div class="ins-section"><div class="ins-label">工作目录</div><div class="ins-card">' +
        '<div class="kv"><span class="k">状态</span><span class="v">' + (state.workspace.configured ? (state.workspace.exists ? chipOk("已配置") : chipDanger("缺失")) : chipWarn("未配置")) + "</span></div>" +
        '<div class="kv"><span class="k">路径</span><span class="v mono" title="' + esc(state.workspace.path) + '">' + esc(state.workspace.path || "—") + "</span></div>" +
        (state.fileTree && state.fileTree.entries ? '<div class="kv"><span class="k">条目</span><span class="v">' + state.fileTree.entries.length + " 项</span></div>" : "") +
        "</div></div>" +
        '<div class="ins-section"><div class="ins-label">编辑器</div><div class="ins-card">' +
        '<div class="kv"><span class="k">打开文件</span><span class="v">' + state.editorFiles.length + "</span></div>" +
        '<div class="kv"><span class="k">活动文件</span><span class="v mono" title="' + esc(state.editorActive || "") + '">' + esc((state.editorActive || "—").split(/[\\/]/).pop()) + "</span></div>" +
        "</div></div>";
    } else if (act === "agent") {
      const s = state.sessions.find((x) => x.id === state.sessionId);
      const run = state.runs.find((x) => x.id === state.runId);
      title = "Agent 与会话";
      html =
        '<div class="ins-section"><div class="ins-label">当前会话</div><div class="ins-card">' +
        '<div class="kv"><span class="k">标题</span><span class="v">' + esc(s ? (s.title || "—") : "—") + "</span></div>" +
        '<div class="kv"><span class="k">模式</span><span class="v">' + esc(state.mode) + "</span></div>" +
        '<div class="kv"><span class="k">模型</span><span class="v mono">' + esc(state.model || "—") + "</span></div>" +
        '<div class="kv"><span class="k">消息</span><span class="v">' + state.sessionMessages.length + " 条</span></div>" +
        "</div></div>";
      if (run) {
        html += '<div class="ins-section"><div class="ins-label">当前运行</div><div class="ins-card">' +
          '<div class="kv"><span class="k">ID</span><span class="v mono">' + esc(run.id) + "</span></div>" +
          '<div class="kv"><span class="k">状态</span><span class="v">' + esc(run.status || "—") + "</span></div>" +
          (state.pendingApproval ?
            '<div class="kv"><span class="k">待审批</span><span class="v">' + chipWarn(state.pendingApproval.tool) + "</span></div>" : "") +
          "</div></div>";
        if (run.events || run.timeline) {
          html += '<div class="ins-section"><div class="ins-label">ReAct 时间线</div>' + renderTimeline(run) + "</div>";
        }
        if (state.pendingApproval) {
          html +=
            '<div class="ins-section"><div class="ins-label">审批</div><div class="ins-card">' +
            '<div class="kv"><span class="k">工具</span><span class="v mono">' + esc(state.pendingApproval.tool) + "</span></div>" +
            '<div class="kv"><span class="k">风险</span><span class="v">' + riskBadge(state.pendingApproval.risk) + "</span></div>" +
            '<div class="kv"><span class="k">范围</span><span class="v mono" style="white-space:normal">' + esc(state.pendingApproval.scope || "") + "</span></div>" +
            "</div></div>";
        }
      }
    } else if (act === "extensions") {
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
    } else if (act === "search") {
      title = "搜索";
      html = '<div class="panel-empty">全局搜索 API 未接入</div>';
    } else if (act === "debug") {
      title = "调试";
      html = '<div class="panel-empty">调试面板占位</div>';
    } else if (act === "settings") {
      title = "设置";
      html =
        '<div class="ins-section"><div class="ins-label">当前模式</div><div class="ins-card">' +
        '<div class="kv"><span class="k">主题</span><span class="v">' + esc(state.theme) + " → " + esc(state.themeResolved) + "</span></div>" +
        '<div class="kv"><span class="k">模型</span><span class="v mono">' + esc(state.model || "—") + "</span></div>" +
        '<div class="kv"><span class="k">审批</span><span class="v">' + approvalLabel() + "</span></div>" +
        '<div class="kv"><span class="k">模式</span><span class="v">' + esc(state.mode) + "</span></div></div></div>";
      // 显示当前 settingsSection 详情
      const section = state.settingsSection || "provider";
      if (section === "provider") {
        html += '<div class="ins-section"><div class="ins-label">服务商与模型</div><div class="ins-card">' +
          '<div class="kv"><span class="k">模型数</span><span class="v">' + state.models.length + "</span></div>" +
          '<div class="kv"><span class="k">当前</span><span class="v mono">' + esc(state.model || "—") + "</span></div>" +
          "</div></div>";
      } else if (section === "workspace") {
        html += '<div class="ins-section"><div class="ins-label">工作目录</div><div class="ins-card">' +
          '<div class="kv"><span class="k">路径</span><span class="v mono" style="word-break:break-all">' + esc(state.workspace.path || "—") + "</span></div>" +
          '<div class="kv"><span class="k">状态</span><span class="v">' + (state.workspace.configured ? chipOk("已配置") : chipWarn("未配置")) + "</span></div>" +
          "</div></div>";
      } else if (section === "appearance") {
        html += '<div class="ins-section"><div class="ins-label">外观</div><div class="ins-card">' +
          '<div class="kv"><span class="k">主题模式</span><span class="v">' + esc(state.theme) + "</span></div>" +
          "</div></div>";
      } else if (section === "chat") {
        html += '<div class="ins-section"><div class="ins-label">对话参数</div><div class="ins-card">' +
          '<div class="kv"><span class="k">默认模式</span><span class="v">' + esc(state.mode) + "</span></div>" +
          '<div class="kv"><span class="k">审批策略</span><span class="v">' + approvalLabel() + "</span></div>" +
          "</div></div>";
      }
    }
    $("#ins-title").textContent = title;
    $("#ins-scroll").innerHTML = html;
  }

  /* ==================== 底部 Panel ==================== */
  function renderPanel() {
    const chatPanel = $("#panel-chat");
    const body = $("#panel-body");
    // 同步 tab 选中态
    $$(".panel-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.panelTab === state.panelTab)));

    if (state.panelTab === "chat") {
      chatPanel.hidden = false;
      body.hidden = true;
      renderPanelMessages();
      return;
    }
    // 非 Chat Tab：隐藏 Chat Panel，显示 events/sandbox/logs
    chatPanel.hidden = true;
    body.hidden = false;

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
    body.scrollTop = body.scrollHeight;
  }

  /* ==================== 审批 / 中止 ==================== */
  async function handleApproval(action) {
    if (!state.pendingApproval) { toast("没有待审批项", true); return; }
    const payload = {
      run_id: state.pendingApproval.run_id,
      approval_id: state.pendingApproval.approval_id || state.pendingApproval.id,
      action,
    };
    try {
      await API.approveAgent(payload);
      pushEvent("approval_" + action, payload, "approval");
      toast(action === "approved" ? "已批准" : action === "rejected" ? "已拒绝" : "已中止");
      if (action === "aborted") state.pendingApproval = null;
      renderInspector();
      renderSidebar();
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
      renderInspector();
      renderSidebar();
    } catch (err) { toast(err.message || "中止失败", true); }
  }

  /* ==================== 状态栏 ==================== */
  function updateStatusbar() {
    const waiting = !!state.pendingApproval;
    $("#status-dot").className = "status-dot" + (waiting ? " running" : "");
    $("#status-text").textContent = waiting ? "等待审批" : "空闲";
    $("#status-mode").textContent = state.mode === "agent" ? "Agent" : "对话";
    const statusModel = $("#status-model");
    if (statusModel && statusModel.value !== state.model) statusModel.value = state.model || "";
    const statusApproval = $("#status-approval");
    if (statusApproval && statusApproval.value !== state.approval) statusApproval.value = state.approval;
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
    if (next) renderPanel();
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
      const first = state.sessions.find((s) => s.message_count > 0);
      state.sessionId = state.sessionId || (first ? first.id : null) || (state.sessions[0] && state.sessions[0].id);
    }).catch(() => { state.sessions = []; }));

    tasks.push(API.listAgentTasks().then((list) => {
      state.runs = list || [];
      const pending = state.runs.find((r) => r.status === "waiting_approval");
      if (pending) state.pendingApproval = pending;
      state.runId = state.runId || (pending && pending.id) || (state.runs[0] && state.runs[0].id);
    }).catch(() => { state.runs = []; }));

    tasks.push(API.listMods().then((list) => { state.mods = list || []; }).catch(() => { state.mods = []; }));
    tasks.push(API.agentTools().then((list) => { state.tools = list || []; }).catch(() => { state.tools = []; }));

    // 模型列表
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
      const modelOpts = availableModels.length
        ? availableModels.map((m) => '<option value="' + esc(m.value) + '">' + esc(m.label) + "</option>").join("")
        : '<option value="">—</option>';
      // 填充 Panel Chat 和状态栏的模型下拉框
      ["#panel-model", "#status-model"].forEach((sel) => {
        const el = $(sel); if (el) { el.innerHTML = modelOpts; el.value = state.model || ""; }
      });
      if (!availableModels.find((m) => m.value === state.model) && availableModels.length) {
        state.model = availableModels[0].value; persist();
      }
      $("#panel-model").value = state.model || "";
      $("#status-model").value = state.model || "";
      $("#status-provider").textContent = "服务商 " + ((data && data.provider) || "—");
    }).catch(() => { state.models = []; }));

    await Promise.all(tasks);

    if (state.sessionId) {
      try {
        const s = await API.getSession(state.sessionId);
        state.sessionMessages = (s && s.messages) || [];
      } catch {
        state.sessionMessages = [];
      }
    }

    await loadWorkspace();
  }

  /* ==================== 事件绑定 ==================== */
  function bindAll() {
    // Activity Bar
    $$(".act-btn[data-activity]").forEach((b) => b.addEventListener("click", () => setActivity(b.dataset.activity)));

    // Side Bar 点击事件
    $("#side-scroll").addEventListener("click", (e) => {
      // 文件树
      const ft = e.target.closest("[data-ft-path]");
      if (ft) {
        const isDir = ft.dataset.ftIsdir === "true";
        if (isDir) toggleDir(ft.dataset.ftPath);
        else openFile(ft.dataset.ftPath);
        return;
      }
      // 会话
      const b = e.target.closest("[data-session]");
      if (b) {
        state.sessionId = b.dataset.session;
        state.sessionMessages = [];
        API.getSession(state.sessionId).then((s) => { state.sessionMessages = (s && s.messages) || []; renderPanelMessages(); }).catch(() => {});
        renderSidebar(); renderPanelMessages(); renderInspector();
        // 自动展开 Panel
        document.body.dataset.panel = "expanded";
        pushEvent("activity_switch", { to: "agent" });
        return;
      }
      // 运行
      const r = e.target.closest("[data-run]");
      if (r) {
        state.runId = r.dataset.run;
        state.pendingApproval = null;
        renderSidebar(); renderInspector();
        return;
      }
      // 设置跳转
      const s = e.target.closest("[data-settings-jump]");
      if (s) {
        state.settingsSection = s.dataset.settingsJump;
        renderSidebar(); renderInspector();
        return;
      }
      // MOD 开关
      const m = e.target.closest("[data-mod]");
      if (m) API.toggleMod(m.dataset.mod, true).then(() => toast("MOD 状态已更新")).catch(() => toast("切换失败", true));
    });

    // Side Bar action 按钮（新会话 / 刷新文件树 / 刷新扩展）
    $("#side-action").addEventListener("click", () => {
      if (state.activity === "agent") {
        API.createSession().then((s) => {
          state.sessions.unshift(s);
          state.sessionId = s.id;
          state.sessionMessages = [];
          persist();
          document.body.dataset.panel = "expanded";
          renderSidebar(); renderPanelMessages(); renderInspector();
          toast("新会话已创建");
        }).catch((err) => toast(err.message || "创建失败", true));
      } else if (state.activity === "explorer") {
        refreshFileTree();
      } else if (state.activity === "extensions") {
        loadAll().then(() => { renderSidebar(); renderInspector(); toast("已重新扫描"); });
      }
    });

    // Side Bar 搜索
    $("#side-search-input").addEventListener("input", (e) => { state.sessionQuery = e.target.value; renderSidebar(); });

    // 文件树的 × 关闭图标（通过 Side Bar 事件委托处理 ft-item 点击）
    // 编辑器 tabs（通过 #editor-tabs 事件委托）
    $("#editor-tabs").addEventListener("click", (e) => {
      const closeBtn = e.target.closest("[data-editor-close]");
      if (closeBtn) {
        e.stopPropagation();
        closeFile(closeBtn.dataset.editorClose);
        return;
      }
      const tab = e.target.closest("[data-editor-tab]");
      if (tab) openFile(tab.dataset.editorTab);
    });

    // 工作目录入口
    ["#side-ws-chip", "#status-ws"].forEach((sel) => {
      const el = $(sel); if (el) el.addEventListener("click", openWorkspacePicker);
    });

    // Panel Chat Tab composer
    const panelComposer = $("#panel-composer");
    if (panelComposer) {
      panelComposer.addEventListener("input", () => syncComposer());
      panelComposer.addEventListener("keydown", (e) => {
        // Ctrl+Enter 发送，Enter 换行
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          sendMessage();
        }
      });
    }
    const panelSend = $("#panel-send");
    if (panelSend) panelSend.addEventListener("click", sendMessage);
    const panelMode = $("#panel-mode");
    if (panelMode) panelMode.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-mode]"); if (b) { state.mode = b.dataset.mode; persist(); syncComposer(); updateStatusbar(); renderInspector(); }
    });
    const panelModel = $("#panel-model");
    if (panelModel) panelModel.addEventListener("change", (e) => { state.model = e.target.value; persist(); updateStatusbar(); renderPanelMessages(); renderInspector(); });

    // 状态栏
    $("#status-model").addEventListener("change", (e) => {
      state.model = e.target.value; persist();
      const pm = $("#panel-model"); if (pm) pm.value = state.model;
      updateStatusbar(); renderPanelMessages();
    });
    $("#status-approval").addEventListener("change", (e) => { state.approval = e.target.value; persist(); renderInspector(); });

    // 面板 / 抽屉开关
    $("#panel-close").addEventListener("click", () => togglePanel(false));
    $("#status-panel").addEventListener("click", () => togglePanel());
    $("#act-toggle-inspector").addEventListener("click", () => toggleInspector());
    $("#status-inspector").addEventListener("click", () => toggleInspector());
    $("#ins-close").addEventListener("click", () => toggleInspector(false));
    $("#act-theme").addEventListener("click", toggleTheme);
    $("#act-exit").addEventListener("click", () => { location.href = "/"; });
    $("#drawer-backdrop").addEventListener("click", closeDrawers);

    // Panel Tab 切换
    $$(".panel-tab").forEach((b) => b.addEventListener("click", () => { state.panelTab = b.dataset.panelTab; renderPanel(); }));
    $("#panel-clear").addEventListener("click", () => {
      if (state.panelTab === "chat") state.sessionMessages = [];
      else if (state.panelTab === "events") state.events = [];
      else if (state.panelTab === "sandbox") state.sandbox = [];
      else state.logs = [];
      renderPanel();
    });

    // Inspector 里的审批按钮（事件委托）
    $("#ins-scroll").addEventListener("click", (e) => {
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
      if (key === ",") { e.preventDefault(); state.settingsSection = "provider"; setActivity("settings"); return; }
      // Activity Bar 快捷键
      const map = { "1": "explorer", "2": "search", "3": "agent", "4": "extensions", "5": "debug", "6": "settings" };
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

    // 根据窗口大小设置初始形态
    if (window.innerWidth <= 1023) {
      document.body.dataset.sidebar = "collapsed"; document.body.dataset.inspector = "collapsed"; document.body.dataset.panel = "collapsed";
    } else if (window.innerWidth <= 1180) {
      document.body.dataset.inspector = "collapsed";
      // Panel 在中等屏幕默认展开
    }
    // 大屏：Panel 默认展开（ide.html body 已设 data-panel="expanded"）

    // 骨架渲染
    renderEditorEmpty();
    renderEditorTabs();
    renderSidebar();
    renderPanel();  // 这会正确显示 Chat Tab
    renderInspector();
    updateStatusbar();
    syncComposer();

    // 绑定事件
    bindAll();

    // 加载真实数据
    try {
      await loadAll();
    } catch (err) {
      pushLog("initial load failed: " + err.message, "error");
      toast("部分数据加载失败", true);
    }

    // 加载后重渲染
    renderSidebar();
    renderPanel();
    renderInspector();
    updateStatusbar();
    renderEditorEmpty(); // 如果没有打开的文件，保持空态
  }

  init();
})();
