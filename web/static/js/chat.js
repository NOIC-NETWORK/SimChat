/* SimChat Web — 会话侧边栏 + 服务商配置 + 流式对话 */
(() => {
  "use strict";

  const el = {
    sidebar: document.getElementById("sidebar"),
    backdrop: document.getElementById("sidebar-backdrop"),
    sessionList: document.getElementById("session-list"),
    newChat: document.getElementById("new-chat"),
    toggleSidebar: document.getElementById("toggle-sidebar"),
    openSetup: document.getElementById("open-setup"),
    title: document.getElementById("chat-title"),
    statusDot: document.getElementById("status-dot"),
    conversation: document.getElementById("conversation"),
    setup: document.getElementById("setup"),
    setupBack: document.getElementById("setup-back"),
    setupMessage: document.getElementById("setup-message"),
    providerTabs: document.getElementById("provider-tabs"),
    providerDetail: document.getElementById("provider-detail"),
    providerForm: document.getElementById("provider-form"),
    providerFields: document.getElementById("provider-fields"),
    providerPresets: document.getElementById("provider-presets"),
    testProvider: document.getElementById("test-provider"),
    saveProvider: document.getElementById("save-provider"),
    welcome: document.getElementById("welcome"),
    messages: document.getElementById("messages"),
    composer: document.getElementById("composer"),
    lockBanner: document.getElementById("lock-banner"),
    lockConfig: document.getElementById("lock-config"),
    input: document.getElementById("input"),
    send: document.getElementById("send"),
    agentToggle: document.getElementById("agent-toggle"),
    agentToggleLabel: document.getElementById("agent-toggle-label"),
    openIde: document.getElementById("open-ide"),
    tokenBar: document.getElementById("token-bar"),
    tokenInput: document.getElementById("token-input"),
    tokenTotal: document.getElementById("token-total"),

    // 基础设置元素
    setMaxHistory: document.getElementById("set-max-history"),
    setMaxHistoryVal: document.getElementById("set-max-history-val"),
    setTemperature: document.getElementById("set-temperature"),
    setTemperatureVal: document.getElementById("set-temperature-val"),
    setMaxTokens: document.getElementById("set-max-tokens"),
    setSystemPrompt: document.getElementById("set-system-prompt"),
    setSendWithEnter: document.getElementById("set-send-with-enter"),
    setShowTokenBar: document.getElementById("set-show-token-bar"),
    setTheme: document.getElementById("set-theme"),
    setFontScale: document.getElementById("set-font-scale"),
    setFontScaleVal: document.getElementById("set-font-scale-val"),
    settingsStatus: document.getElementById("settings-status"),
    saveSettingsBtn: document.getElementById("save-settings-btn"),
    resetSettingsBtn: document.getElementById("reset-settings-btn"),
    openConsole: document.getElementById("open-console"),

    // 控制台元素
    settingsConsole: document.getElementById("settings-console"),
    consoleBack: document.getElementById("console-back"),
    consoleStatus: document.getElementById("console-status"),
    navItems: document.querySelectorAll(".console-nav-item"),
    sections: document.querySelectorAll(".setting-section[data-section]"),

    // 概览卡片
    ovProvider: document.getElementById("ov-provider"),
    ovProviderDetail: document.getElementById("ov-provider-detail"),
    ovUptime: document.getElementById("ov-uptime"),
    ovListen: document.getElementById("ov-listen"),
    ovVersion: document.getElementById("ov-version"),
    ovSessions: document.getElementById("ov-sessions"),
  };

  const state = {
    sessionId: null,
    streaming: false,
    stickToBottom: true,
    locked: true,
    mode: "chat",  // "chat" | "setup" | "console" —— 唯一事实源
    providers: [],
    presets: [],
    blocks: {},
    activeProvider: null,
    configured: null,
    resolved: null,
    drafts: {},

    // 设置页状态
    settings: null,
    settingsDirty: false,
    activeSection: "overview",
  };

  const TRASH_ICON =
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>';

  const COPY_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>' +
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

  const CHECK_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
    '<polyline points="20 6 9 17 4 12"/></svg>';

  const RETRY_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<polyline points="23 4 23 10 17 10"/>' +
    '<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';

  const CODE_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<polyline points="16 18 22 12 16 6"/>' +
    '<polyline points="8 6 2 12 8 18"/></svg>';

  const RENDER_ICON =
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
    '<circle cx="12" cy="12" r="3"/></svg>';

  const LOGO_URL =
    document.body.dataset.logo || "/static/sprites/logos/simChat-1.png";

  const LAST_SESSION_KEY = "simchat:last_session";

  function saveSessionId(sid) {
    try {
      if (sid) localStorage.setItem(LAST_SESSION_KEY, sid);
      else localStorage.removeItem(LAST_SESSION_KEY);
    } catch (_) {
      /* 无痕模式等情况下 localStorage 可能不可用，静默忽略 */
    }
  }

  function loadSessionId() {
    try {
      return localStorage.getItem(LAST_SESSION_KEY);
    } catch (_) {
      return null;
    }
  }

  function setSessionId(sid) {
    state.sessionId = sid;
    saveSessionId(sid);
  }

  // ---------------- Token 估算 ----------------

  /* 无 tokenizer 可用时的字符级估算：CJK 约 1 字 1 token，其余约 4 字符 1 token。 */
  const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/;

  function estimateTokens(text) {
    const src = String(text || "");
    if (!src) return 0;
    let cjk = 0;
    let other = 0;
    for (const ch of src) {
      if (CJK_RE.test(ch)) cjk += 1;
      else other += 1;
    }
    return cjk + Math.ceil(other / 4);
  }

  function formatTokens(count) {
    return Number(count || 0).toLocaleString("en-US");
  }

  function updateInputTokens() {
    if (!el.tokenInput) return;
    el.tokenInput.textContent = "输入 " + formatTokens(estimateTokens(el.input.value)) + " tokens";
  }

  function recalcSessionTokens() {
    let total = 0;
    el.messages.querySelectorAll(".message").forEach((row) => {
      const count = estimateTokens(row._raw ? row._raw.text : "");
      total += count;
      if (row._tokensEl) {
        row._tokensEl.textContent = formatTokens(count) + " tokens";
        row._tokensEl.classList.toggle("hidden", count === 0);
      }
    });
    if (el.tokenTotal) el.tokenTotal.textContent = "会话 " + formatTokens(total) + " tokens";
  }

  // ---------------- 工具函数 ----------------

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[ch]);
  }

  /* 极简 Markdown 渲染：代码块 / 行内代码 / 粗体 / 无序与有序列表。
     所有文本先转义，避免模型输出注入 HTML。 */
  function renderMarkdown(text) {
    const codeBlocks = [];
    let src = escapeHtml(text || "");

    src = src.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code) => {
      const index = codeBlocks.length;
      codeBlocks.push(
        '<pre class="code-block"><code>' + code.replace(/\n$/, "") + "</code></pre>"
      );
      return "\u0000BLOCK" + index + "\u0000";
    });

    src = src.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
    src = src.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");

    const html = src
      .split(/\n{2,}/)
      .map((block) => {
        const lines = block.split("\n").filter((line) => line.trim() !== "");
        if (!lines.length) return "";
        if (/^\u0000BLOCK\d+\u0000$/.test(lines[0])) return lines.join("");
        if (lines.every((line) => /^[-*]\s+/.test(line))) {
          return (
            "<ul>" +
            lines.map((line) => "<li>" + line.replace(/^[-*]\s+/, "") + "</li>").join("") +
            "</ul>"
          );
        }
        if (lines.every((line) => /^\d+\.\s+/.test(line))) {
          return (
            "<ol>" +
            lines.map((line) => "<li>" + line.replace(/^\d+\.\s+/, "") + "</li>").join("") +
            "</ol>"
          );
        }
        return "<p>" + lines.join("<br>") + "</p>";
      })
      .join("");

    return html.replace(/\u0000BLOCK(\d+)\u0000/g, (_, index) => codeBlocks[Number(index)]);
  }

  async function api(path, options) {
    const resp = await fetch(path, options);
    if (!resp.ok) {
      let message = "请求失败（HTTP " + resp.status + "）";
      try {
        const data = await resp.json();
        if (data && (data.error || data.message)) message = data.error || data.message;
      } catch (_) {
        /* 非 JSON 响应 */
      }
      throw new Error(message);
    }
    return resp.json();
  }

  // ---------------- 侧边栏 ----------------

  function openSidebar() {
    el.sidebar.classList.add("open");
    el.backdrop.classList.add("show");
  }

  function closeSidebar() {
    el.sidebar.classList.remove("open");
    el.backdrop.classList.remove("show");
  }

  async function loadSessions() {
    try {
      const data = await api("/api/sessions");
      renderSessions(data.sessions || []);
    } catch (err) {
      console.error("[SimChat] 会话列表加载失败:", err);
    }
  }

  function renderSessions(sessions) {
    el.sessionList.innerHTML = "";
    if (!sessions.length) {
      const empty = document.createElement("div");
      empty.className = "session-empty";
      empty.textContent = "暂无会话";
      el.sessionList.appendChild(empty);
      return;
    }

    for (const session of sessions) {
      const item = document.createElement("div");
      item.className = "session-item" + (session.id === state.sessionId ? " active" : "");
      item.dataset.id = session.id;
      item.title = session.title || "新对话";

      const title = document.createElement("span");
      title.className = "session-title";
      title.textContent = session.title || "新对话";
      item.appendChild(title);

      const remove = document.createElement("button");
      remove.className = "session-delete";
      remove.type = "button";
      remove.title = "删除会话";
      remove.setAttribute("aria-label", "删除会话");
      remove.innerHTML = TRASH_ICON;
      remove.addEventListener("click", (event) => {
        event.stopPropagation();
        removeSession(session.id);
      });
      item.appendChild(remove);

      item.addEventListener("click", () => openSession(session.id));
      el.sessionList.appendChild(item);

      if (session.id === state.sessionId && !state.locked) {
        el.title.textContent = session.title || "新对话";
      }
    }
  }

  async function removeSession(sid) {
    if (!window.confirm("删除这个会话？此操作不可撤销。")) return;
    try {
      await api("/api/sessions/" + encodeURIComponent(sid), { method: "DELETE" });
      if (sid === state.sessionId) startNewChat();
      await loadSessions();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function openSession(sid) {
    if (state.streaming) return;
    try {
      const data = await api("/api/sessions/" + encodeURIComponent(sid));
      const session = data.session;
      setSessionId(session.id);
      state.stickToBottom = true;
      el.title.textContent = session.title || "新对话";
      el.messages.innerHTML = "";

      const history = session.messages || [];
      for (const message of history) addMessage(message.role, message.content, true);

      // 只有解锁（配好服务商）才进 chat 模式；否则保持 setup 不被覆盖
      if (!state.locked) enterMode("chat");

      closeSidebar();
      scrollToBottom(true);
      await loadSessions();
      if (!state.locked) el.input.focus();
    } catch (err) {
      addMessage("assistant", "加载会话失败：" + err.message);
    }
  }

  function startNewChat() {
    if (state.streaming) return;
    setSessionId(null);
    state.stickToBottom = true;
    el.messages.innerHTML = "";
    recalcSessionTokens();
    document
      .querySelectorAll(".session-item.active")
      .forEach((node) => node.classList.remove("active"));
    closeSidebar();

    if (state.locked) {
      el.title.textContent = "连接服务商";
      showSetup();
      return;
    }

    el.title.textContent = "新对话";
    enterMode("chat");
    el.input.focus();
  }

  // ---------------- 服务商检测与配置 ----------------

  function currentProvider() {
    return (
      state.providers.find((item) => item.id === state.activeProvider) ||
      state.providers[0] ||
      null
    );
  }

  function providerById(id) {
    return state.providers.find((item) => item.id === id) || null;
  }

  /* 状态点提示：Auto Model 时显示自动选中的服务商，便于确认"记住了" */
  function connectionLabel() {
    if (state.locked) return "未配置可用服务商";
    if (state.streaming) return "生成中";
    const target = providerById(state.resolved);
    if (state.configured === "auto") {
      return "Auto Model · " + (target ? target.label : "自动选择");
    }
    return "已连接" + (target ? " · " + target.label : "");
  }

  function applyBlocks(blocks) {
    state.blocks = {};
    (blocks || []).forEach((block) => {
      state.blocks[block.id] = block;
    });

    document.querySelectorAll("[data-block]").forEach((node) => {
      const block = state.blocks[node.dataset.block];
      if (!block) return;
      const text = block.description || block.label;
      if (text) node.textContent = text;
      if (block.hint) node.title = block.hint;
    });
  }

  function setSetupMessage(text, kind) {
    el.setupMessage.textContent = text || "";
    el.setupMessage.className = "setup-message" + (kind ? " " + kind : "");
  }

  function setSetupBusy(busy) {
    el.testProvider.disabled = busy;
    el.saveProvider.disabled = busy;
  }

  function setLocked(locked, keepSetup) {
    state.locked = locked;
    el.lockBanner.classList.toggle("hidden", !locked);
    el.composer.classList.toggle("hidden", locked);
    el.tokenBar?.classList.toggle("hidden", locked);
    el.statusDot.classList.toggle("locked", locked);
    el.statusDot.classList.toggle("streaming", !locked && state.streaming);
    el.setupBack.classList.toggle("hidden", locked);

    if (locked) {
      if (!state.sessionId) el.title.textContent = "连接服务商";
      if (state.mode !== "setup") showSetup();
    } else {
      if (state.mode === "setup" && !keepSetup) hideSetup();
    }
    el.statusDot.title = connectionLabel();
    updateSendState();
  }

  function setProviderData(data, keepSetup) {
    state.providers = data.providers || [];
    state.presets = data.presets || [];
    state.configured = data.configured || null;
    state.resolved = data.resolved || null;
    applyBlocks(data.blocks || []);
    state.drafts = {};

    const preferred = data.preferred;
    if (!state.activeProvider || !state.providers.some((item) => item.id === state.activeProvider)) {
      state.activeProvider = preferred || (state.providers[0] ? state.providers[0].id : null);
    }

    setLocked(!data.available, keepSetup);

    if (state.mode === "setup") {
      renderProviderTabs();
      renderProviderDetail();
      renderProviderForm();
      renderPresets();
    }
  }

  function renderProviderTabs() {
    el.providerTabs.innerHTML = "";
    for (const provider of state.providers) {
      const block = state.blocks["provider." + provider.id] || {};
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "provider-tab" + (provider.id === state.activeProvider ? " active" : "");
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", provider.id === state.activeProvider ? "true" : "false");

      const dot = document.createElement("span");
      dot.className = "dot" + (provider.available ? " available" : "");
      tab.appendChild(dot);

      const label = document.createElement("span");
      label.textContent = block.label || provider.label;
      tab.appendChild(label);

      tab.title = block.hint || provider.detail || "";
      tab.addEventListener("click", () => {
        if (state.activeProvider === provider.id) return;
        state.activeProvider = provider.id;
        renderProviderTabs();
        renderProviderDetail();
        renderProviderForm();
      });
      el.providerTabs.appendChild(tab);
    }
  }

  function renderProviderDetail() {
    const provider = currentProvider();
    el.providerDetail.textContent = provider ? provider.detail || "" : "没有可配置的服务商";
  }

  function renderProviderForm() {
    el.providerFields.innerHTML = "";
    const provider = currentProvider();
    if (!provider) return;

    const draft = state.drafts[provider.id] || (state.drafts[provider.id] = {});

    const fields = provider.fields || [];
    if (!fields.length) {
      // Auto Model 没有可填字段：说明它会挑谁，并提示无需手动选
      const hint = document.createElement("span");
      hint.className = "field-hint";
      hint.textContent = "无需填写字段。保存后 SimChat 会自动使用当前最优的可用服务商。";
      el.providerFields.appendChild(hint);
      return;
    }

    for (const field of fields) {
      if (!(field.name in draft)) draft[field.name] = field.value || "";

      const wrap = document.createElement("label");
      wrap.className = "field";

      const caption = document.createElement("span");
      caption.className = "field-label";
      caption.textContent = field.label + (field.required ? "" : "（可选）");
      wrap.appendChild(caption);

      let control;
      if (Array.isArray(field.options) && field.options.length) {
        control = document.createElement("select");
        const options = field.options.slice();
        const current = draft[field.name] || "";
        if (current && options.indexOf(current) === -1) options.unshift(current);
        if (!current) options.unshift("");
        for (const value of options) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = value || "请选择模型";
          control.appendChild(option);
        }
        control.value = current;
      } else {
        control = document.createElement("input");
        control.type = field.type === "password" ? "password" : "text";
        control.value = draft[field.name] || "";
        control.placeholder = field.placeholder || "";
        control.autocomplete = "off";
      }

      control.className = "field-input";
      control.name = field.name;
      control.addEventListener("input", () => {
        draft[field.name] = control.value;
      });
      control.addEventListener("change", () => {
        draft[field.name] = control.value;
      });
      wrap.appendChild(control);

      if (field.hint) {
        const hint = document.createElement("span");
        hint.className = "field-hint";
        hint.textContent = field.hint;
        wrap.appendChild(hint);
      }

      el.providerFields.appendChild(wrap);
    }
  }

  function renderPresets() {
    el.providerPresets.innerHTML = "";
    const presets = state.presets || [];
    el.providerPresets.classList.toggle("hidden", !presets.length);

    for (const preset of presets) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "preset-chip";
      chip.textContent = preset.label;
      chip.title = preset.description || "";
      chip.addEventListener("click", () => {
        state.activeProvider = preset.provider;
        const draft = state.drafts[preset.provider] || (state.drafts[preset.provider] = {});
        Object.assign(draft, preset.values || {});
        renderProviderTabs();
        renderProviderDetail();
        renderProviderForm();
        setSetupMessage("已填入预设：" + preset.label, "");
      });
      el.providerPresets.appendChild(chip);
    }
  }

  function collectConfig() {
    const provider = currentProvider();
    if (!provider) return {};
    const draft = state.drafts[provider.id] || {};
    const config = {};
    for (const field of provider.fields || []) {
      config[field.name] = String(draft[field.name] || "").trim();
    }
    return config;
  }

  // ---------------- 模式切换（单一事实源，烧毛球的核心） ----------------
  // mode ∈ { "chat" | "setup" | "console" }
  // 所有 visibility 只由这一处控制，杜绝 showSetup/openConsole 互相踩脚。

  function enterMode(next) {
    if (state.mode === next) return;
    const prev = state.mode;
    console.log("[MODE]", prev, "→", next, new Error().stack.split("\n").slice(2, 4).join(" ← "));
    state.mode = next;

    // 蒙版层：只用 .is-open 类控制显隐（CSS 里 display:none 默认，display:flex 需 .is-open）
    // 绝不碰 [hidden] 属性或 .hidden 类——之前就是被 CSS 的 display:flex 覆盖导致永远显示。
    el.setup.classList.remove("is-open");
    el.settingsConsole.classList.remove("is-open");

    if (next === "chat") {
      // 主界面全开
      el.conversation.style.display = "";
      el.messages.style.display = "";
      showWelcome(el.messages.children.length === 0);
      document.body.style.overflow = "";
    } else if (next === "setup") {
      // 右侧抽屉面板：底下主界面保持可见（有半透明遮罩）
      // 不再硬藏 messages/welcome——PC 风格，边看聊天边改设置
      el.setup.classList.add("is-open");
      el.setupBack.style.display = state.locked ? "none" : "";
      document.body.style.overflow = "";
      if (prev !== "setup") {
        renderProviderTabs();
        renderProviderDetail();
        renderProviderForm();
        renderPresets();
        loadSettings();
      }
    } else if (next === "console") {
      // 控制台全屏盖下来
      el.conversation.style.display = "none";
      el.settingsConsole.classList.add("is-open");
      document.body.style.overflow = "hidden";
    }
  }

  // 四个薄 wrapper——内部一律走 enterMode，外部调用不动
  function showSetup() { enterMode("setup"); }
  function hideSetup() {
    if (state.locked) return;
    enterMode("chat");
  }
  function openConsole() {
    enterMode("console");
    const saved = (localStorage.getItem(SECTION_KEY) || "overview").trim();
    switchSection(saved);
    renderOverview();
  }
  function closeConsole() {
    // 关掉控制台后回到 chat 还是 setup，看 locked 状态
    try { localStorage.removeItem(ADVANCED_KEY); } catch (_) {}
    enterMode(state.locked ? "setup" : "chat");
  }

  async function loadProviders() {
    try {
      const data = await api("/api/providers");
      setProviderData(data);
    } catch (err) {
      state.locked = true;
      state.providers = [];
      setLocked(true);
      showSetup();
      setSetupMessage("无法检测服务商：" + err.message, "error");
    }
  }

  async function saveProvider() {
    const provider = currentProvider();
    if (!provider) return;
    setSetupBusy(true);
    setSetupMessage("正在保存并检测…", "");

    try {
      const data = await api("/api/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider.id,
          config: collectConfig(),
          activate: true,
        }),
      });

      const saved = (data.providers || []).find((item) => item.id === provider.id);
      const savedAvailable = !!(saved && saved.available);
      setProviderData(data, !savedAvailable);

      if (savedAvailable) {
        await loadSessions();
        if (!state.locked) el.input.focus();
      } else {
        setSetupMessage(
          (saved && saved.detail) || "配置已保存，但该服务商仍不可用。",
          "error"
        );
      }
    } catch (err) {
      setSetupMessage(err.message, "error");
    } finally {
      setSetupBusy(false);
    }
  }

  async function testProvider() {
    const provider = currentProvider();
    if (!provider) return;
    setSetupBusy(true);
    setSetupMessage("正在测试连接…", "");

    try {
      const result = await api("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: provider.id, config: collectConfig() }),
      });
      if (!result.ok) {
        setSetupMessage(result.message || "连接失败", "error");
        return;
      }

      /* 测试通过就立刻落盘：避免"测过 / 配过，但刷新后没记住"。
         Auto Model 模式下只保存字段，不挤掉用户选的自动模式。 */
      const data = await api("/api/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider.id,
          config: collectConfig(),
          activate: provider.id === "auto" || state.configured !== "auto",
        }),
      });

      const saved = (data.providers || []).find((item) => item.id === provider.id);
      const savedAvailable = !!(saved && saved.available);
      setProviderData(data, !savedAvailable);

      if (savedAvailable) {
        await loadSessions();
        if (!state.locked) el.input.focus();
      } else {
        setSetupMessage(
          (saved && saved.detail) || "配置已保存，但该服务商仍不可用。",
          "error"
        );
      }
    } catch (err) {
      setSetupMessage(err.message, "error");
    } finally {
      setSetupBusy(false);
    }
  }

  // ---------------- 消息操作栏 ----------------

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // 回退方案
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  function createAssistantActions(content, getRaw) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    actions.innerHTML =
      '<button class="action-btn" data-action="toggle" title="查看源码" aria-label="查看源码">' +
      CODE_ICON + '<span>查看源码</span></button>' +
      '<button class="action-btn" data-action="copy-md" title="复制 Markdown" aria-label="复制 Markdown">' +
      COPY_ICON + '<span>复制 Markdown</span></button>' +
      '<button class="action-btn" data-action="copy-text" title="复制纯文本" aria-label="复制纯文本">' +
      COPY_ICON + '<span>复制纯文本</span></button>' +
      '<button class="action-btn" data-action="regenerate" title="重答" aria-label="重答">' +
      RETRY_ICON + '<span>重答</span></button>';

    let showingRaw = false;
    const body = content;
    const rawBackup = document.createElement("pre");
    rawBackup.className = "raw-markdown hidden";

    actions.addEventListener("click", async (event) => {
      const btn = event.target.closest(".action-btn");
      if (!btn) return;
      const action = btn.dataset.action;

      if (action === "toggle") {
        showingRaw = !showingRaw;
        if (showingRaw) {
          rawBackup.textContent = getRaw();
          body.classList.add("hidden");
          rawBackup.classList.remove("hidden");
          btn.innerHTML = RENDER_ICON + '<span>查看渲染</span>';
        } else {
          body.classList.remove("hidden");
          rawBackup.classList.add("hidden");
          btn.innerHTML = CODE_ICON + '<span>查看源码</span>';
        }
      } else if (action === "copy-md") {
        const ok = await copyText(getRaw());
        flashButton(btn, ok);
      } else if (action === "copy-text") {
        const ok = await copyText(body.innerText || "");
        flashButton(btn, ok);
      } else if (action === "regenerate") {
        regenerateLast();
      }
    });

    return { actions, rawBackup };
  }

  function flashButton(btn, ok) {
    const orig = btn.innerHTML;
    btn.classList.add("flash-" + (ok ? "ok" : "err"));
    btn.innerHTML = (ok ? CHECK_ICON : '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>') +
      '<span>' + (ok ? "已复制" : "复制失败") + '</span>';
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.classList.remove("flash-ok", "flash-err");
    }, 1400);
  }

  async function regenerateLast() {
    if (state.streaming) return;
    // 找到最后一条 user 消息的原始内容
    const rows = el.messages.querySelectorAll(".message.user");
    if (!rows.length) return;
    const lastUser = rows[rows.length - 1];
    const text = ((lastUser._raw && lastUser._raw.text) || "").trim();
    if (!text) return;

    // 找到最后一条 assistant 行——删掉它和它的操作栏
    const aRows = el.messages.querySelectorAll(".message.assistant");
    if (aRows.length) aRows[aRows.length - 1].remove();

    await sendMessage(text, { regenerate: true });
  }

  // ---------------- 消息渲染 ----------------

  function showWelcome(show) {
    el.welcome.classList.toggle("hidden", !show);
  }

  function addMessage(role, content, showActions) {
    const row = document.createElement("div");
    row.className = "message " + (role === "user" ? "user" : "assistant");

    if (role === "user") {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      const bubbleText = document.createElement("span");
      bubbleText.className = "bubble-text";
      bubbleText.textContent = content || "";
      bubble.appendChild(bubbleText);
      const tokens = document.createElement("span");
      tokens.className = "bubble-tokens";
      bubble.appendChild(tokens);
      row.appendChild(bubble);
      row._raw = { text: content || "" };
      row._tokensEl = tokens;
      el.messages.appendChild(row);
      scrollToBottom();
      recalcSessionTokens();
      return bubble;
    }

    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    const avatarImg = document.createElement("img");
    avatarImg.src = LOGO_URL;
    avatarImg.alt = "";
    avatar.appendChild(avatarImg);
    row.appendChild(avatar);

    // assistant-main：content（消息体）+ actions（按钮栏）纵向堆叠
    const main = document.createElement("div");
    main.className = "assistant-main";

    const body = document.createElement("div");
    body.className = "content";
    const raw = { text: content || "" }; // 用对象以便闭包内可更新
    const getRaw = () => raw.text;
    if (content) body.innerHTML = renderMarkdown(content);
    main.appendChild(body);

    const tokens = document.createElement("div");
    tokens.className = "message-tokens hidden";
    main.appendChild(tokens);

    // 创建操作栏（流式中隐藏、错误时隐藏、正常结束/加载历史显示）
    const { actions, rawBackup } = createAssistantActions(body, getRaw);
    actions.classList.toggle("hidden", !showActions);
    main.appendChild(actions);
    main.appendChild(rawBackup);

    row.appendChild(main);

    el.messages.appendChild(row);
    scrollToBottom();

    // 暴露给外部更新（流式 token 追加、final 落盘后更新 raw）
    row._body = body;
    row._raw = raw;
    row._actions = actions;
    row._tokensEl = tokens;
    recalcSessionTokens();
    return row;
  }

  function scrollToBottom(force) {
    if (force || state.stickToBottom) {
      el.conversation.scrollTop = el.conversation.scrollHeight;
    }
  }

  // ---------------- 输入框 ----------------

  function autoResize() {
    el.input.style.height = "auto";
    el.input.style.height = Math.min(el.input.scrollHeight, 200) + "px";
  }

  function updateSendState() {
    el.send.disabled = state.streaming || state.locked || !el.input.value.trim();
  }

  function setStreaming(streaming) {
    state.streaming = streaming;
    el.statusDot.classList.toggle("streaming", streaming && !state.locked);
    el.statusDot.title = connectionLabel();
    updateSendState();
  }

  // ---------------- 流式对话 ----------------

  async function sendMessage(text, options) {
    options = options || {};
    if (state.streaming) return;
    if (state.locked) {
      showSetup();
      return;
    }

    setStreaming(true);
    state.stickToBottom = true;
    showWelcome(false);

    addMessage("user", text);
    const row = addMessage("assistant", "");
    const contentEl = row._body;
    const raw = row._raw;
    const actions = row._actions;
    contentEl.classList.add("streaming");
    actions.classList.add("hidden");

    let full = "";
    let errorMessage = "";
    let errorCode = "";
    let reader = null;
    let lastTokenTick = 0;

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: state.sessionId,
          regenerate: !!options.regenerate,
        }),
      });

      if (!resp.ok || !resp.body) {
        let message = "对话请求失败（HTTP " + resp.status + "）";
        let code = "";
        try {
          const data = await resp.json();
          if (data && data.error) message = data.error;
          if (data && data.code) code = data.code;
        } catch (_) {
          /* 忽略解析失败 */
        }
        errorCode = code;
        throw new Error(message);
      }

      reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      readStream:
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);

          for (const line of frame.split("\n")) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            if (!raw) continue;

            let event;
            try {
              event = JSON.parse(raw);
            } catch (_) {
              continue;
            }

            if (event.event === "chat_started") {
              setSessionId(event.session_id || state.sessionId);
            } else if (event.event === "token") {
              full += event.content || "";
              contentEl.textContent = full;
              raw.text = full;
              scrollToBottom();
              const now = Date.now();
              if (now - lastTokenTick > 150) {
                lastTokenTick = now;
                recalcSessionTokens();
              }
            } else if (event.event === "final") {
              full = event.content || full;
              raw.text = full;
              setSessionId(event.session_id || state.sessionId);
            } else if (event.event === "error") {
              errorMessage = event.message || "对话失败";
              errorCode = event.code || "";
              break readStream;
            }
          }
        }
      }

      if (errorMessage && reader) {
        try {
          await reader.cancel();
        } catch (_) {
          /* 忽略 */
        }
      }
    } catch (err) {
      errorMessage = err.message || String(err);
      if (reader) {
        try {
          await reader.cancel();
        } catch (_) {
          /* 忽略 */
        }
      }
    }

    contentEl.classList.remove("streaming");
    if (full) {
      contentEl.innerHTML = renderMarkdown(full);
      raw.text = full;
    } else if (!errorMessage) {
      contentEl.innerHTML = renderMarkdown("（无回复）");
      raw.text = "（无回复）";
    }

    if (errorMessage) {
      const error = document.createElement("p");
      error.className = "error-text";
      error.textContent = errorMessage;
      contentEl.appendChild(error);
    } else {
      // 正常结束，显示操作栏
      actions.classList.remove("hidden");
    }

    setStreaming(false);
    recalcSessionTokens();
    scrollToBottom();
    await loadSessions();

    if (errorCode === "provider_unavailable") {
      await loadProviders();
      return;
    }

    el.input.focus();
  }

  // ---------------- 预留接口：Agent 切换 / IDE 跳转 ----------------

  function toggleAgentMode() {
    const track = el.agentToggle;
    const isAgent = track.dataset.mode === "agent";
    const next = isAgent ? "chat" : "agent";
    track.dataset.mode = next;
    track.setAttribute("aria-pressed", String(next === "agent"));
    if (el.agentToggleLabel) {
      el.agentToggleLabel.textContent = next === "agent" ? "Agent" : "对话";
    }
    if (next === "agent") {
      // TODO: 接入 Agent 模式（MOD 加载 + 工具调用）
      console.warn("[SimChat] Agent 模式尚未实现，当前停留在对话模式。");
      // 切回（避免用户进入不可用态）
      setTimeout(() => toggleAgentMode(), 100);
    }
  }

  function openIde() {
    // TODO: 接入 IDE 跳转（Trae / VS Code / WebDAV 之一）
    console.warn("[SimChat] IDE 跳转尚未配置。");
  }

  // ---------------- 主题应用 ----------------

  function applyTheme(theme) {
    theme = theme || "system";
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
  }

  // ---------------- 基础设置 ----------------

  function setSettingsStatus(text, kind) {
    if (!el.settingsStatus) return;
    el.settingsStatus.textContent = text || "";
    el.settingsStatus.className = "settings-status" + (kind ? " " + kind : "");
  }

  function setConsoleStatus(text, kind) {
    if (!el.consoleStatus) return;
    el.consoleStatus.textContent = text || "已同步";
    el.consoleStatus.className = "settings-status-pill" + (kind ? " " + kind : "");
  }

  function setDirty(dirty) {
    state.settingsDirty = !!dirty;
    if (dirty) setSettingsStatus("未保存", "error");
    else setSettingsStatus("已保存", "ok");
  }

  function readSettingsForm() {
    return {
      max_history: parseInt(el.setMaxHistory?.value, 10) || 40,
      temperature: parseFloat(el.setTemperature?.value) || 0.7,
      max_tokens: parseInt(el.setMaxTokens?.value, 10) || 4096,
      system_prompt: (el.setSystemPrompt?.value || "").trim(),
      send_with_enter: el.setSendWithEnter?.classList.contains("on") ?? true,
      show_token_bar: el.setShowTokenBar?.classList.contains("on") ?? true,
      theme: document.querySelector("#set-theme .theme-card.active")?.dataset.theme || "system",
      font_scale: parseFloat(el.setFontScale?.value) || 1.0,
    };
  }

  function populateSettingsForm(s) {
    if (!s) return;
    if (el.setMaxHistory) {
      el.setMaxHistory.value = s.max_history ?? 40;
      el.setMaxHistoryVal.textContent = s.max_history ?? 40;
    }
    if (el.setTemperature) {
      el.setTemperature.value = s.temperature ?? 0.7;
      el.setTemperatureVal.textContent = (s.temperature ?? 0.7).toFixed(1);
    }
    if (el.setMaxTokens) el.setMaxTokens.value = s.max_tokens ?? 4096;
    if (el.setSystemPrompt) el.setSystemPrompt.value = s.system_prompt ?? "";
    if (el.setSendWithEnter) el.setSendWithEnter.classList.toggle("on", !!s.send_with_enter);
    if (el.setShowTokenBar) el.setShowTokenBar.classList.toggle("on", !!s.show_token_bar);
    if (el.setTheme) {
      el.setTheme.querySelectorAll(".theme-card").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.theme === (s.theme || "system"));
      });
    }
    if (el.setFontScale) {
      el.setFontScale.value = s.font_scale ?? 1.0;
      el.setFontScaleVal.textContent = (s.font_scale ?? 1.0).toFixed(2);
    }
  }

  async function loadSettings() {
    try {
      const data = await api("/api/settings");
      state.settings = data.settings;
      populateSettingsForm(data.settings);
      // 重新合并方块（基础设置方块在 /api/settings 里也返回）
      if (data.blocks && data.blocks.length) applyBlocks(data.blocks);
      applyTheme(data.settings?.theme);
      setDirty(false);
    } catch (err) {
      console.warn("[SimChat] 设置加载失败:", err);
    }
  }

  async function saveSettings() {
    const form = readSettingsForm();
    try {
      const data = await api("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      state.settings = data.settings;
      applyTheme(data.settings.theme);
      // 发送键行为
      el.input.removeEventListener("keydown", _chatKeyHandler);
      el.input.addEventListener("keydown", _chatKeyHandler);
      setDirty(false);
      setConsoleStatus("已同步", "ok");
    } catch (err) {
      setSettingsStatus("保存失败：" + err.message, "error");
    }
  }

  async function resetSettings() {
    if (!window.confirm("确定恢复基础设置为默认值？此操作不可撤销。")) return;
    try {
      const data = await api("/api/settings/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "settings" }),
      });
      state.settings = data.settings;
      populateSettingsForm(data.settings);
      applyTheme(data.settings.theme);
      setDirty(false);
    } catch (err) {
      setSettingsStatus("恢复失败：" + err.message, "error");
    }
  }

  // ---------------- 控制台 ----------------

  const ADVANCED_KEY = "simchat.advanced";
  const SECTION_KEY = "simchat.section";

  function switchSection(name) {
    state.activeSection = name;
    try { localStorage.setItem(SECTION_KEY, name); } catch (_) {}

    el.navItems?.forEach((nav) => {
      nav.classList.toggle("is-active", nav.dataset.section === name);
    });
    el.sections?.forEach((sec) => {
      sec.hidden = sec.dataset.section !== name;
    });
  }

  // ---------------- 概览渲染 ----------------

  function formatUptime(seconds) {
    if (!seconds || seconds < 0) return "—";
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return d + "d " + h + "h";
    if (h > 0) return h + "h " + m + "m";
    return m + "m";
  }

  // 进程启动时间
  const _processStart = Date.now();

  async function renderOverview() {
    try {
      const data = await api("/api/providers");
      const resolved = data.resolved;
      const prov = (data.providers || []).find((p) => p.id === resolved) || null;

      if (el.ovProvider) {
        el.ovProvider.textContent = prov ? prov.label : "未配置";
        el.ovProviderDetail.textContent = prov ? prov.detail : "无可用服务商";
      }

      if (el.ovUptime) {
        const secs = (Date.now() - _processStart) / 1000;
        el.ovUptime.textContent = formatUptime(secs);
      }

      if (el.ovListen) {
        el.ovListen.textContent = location.hostname + ":" + location.port;
      }
      if (el.ovVersion) {
        el.ovVersion.textContent = "SimChat 1.0";
      }

      // 会话数
      const sessions = await api("/api/sessions");
      if (el.ovSessions) {
        el.ovSessions.textContent = (sessions.sessions || []).length;
      }
    } catch (err) {
      console.warn("[SimChat] 概览渲染失败:", err);
    }
  }

  // ---------------- 事件绑定 ----------------

  el.newChat.addEventListener("click", startNewChat);
  el.toggleSidebar.addEventListener("click", openSidebar);
  el.backdrop.addEventListener("click", closeSidebar);
  el.openSetup.addEventListener("click", showSetup);
  el.lockConfig.addEventListener("click", showSetup);
  el.agentToggle?.addEventListener("click", toggleAgentMode);
  el.agentToggle?.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleAgentMode(); }
  });
  el.openIde?.addEventListener("click", openIde);
  el.setupBack.addEventListener("click", hideSetup);
  el.providerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveProvider();
  });
  el.testProvider.addEventListener("click", testProvider);

  el.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = el.input.value.trim();
    if (!text || state.streaming || state.locked) return;
    el.input.value = "";
    autoResize();
    updateInputTokens();
    updateSendState();
    sendMessage(text);
  });

  el.input.addEventListener("input", () => {
    autoResize();
    updateInputTokens();
    updateSendState();
  });

  // 发送键：行为由 settings.send_with_enter 决定
  el.input.addEventListener("keydown", (event) => {
    const sendOnEnter = state.settings?.send_with_enter !== false;
    if (sendOnEnter && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      el.composer.requestSubmit();
    }
  });

  el.conversation.addEventListener("scroll", () => {
    const c = el.conversation;
    state.stickToBottom = c.scrollHeight - c.scrollTop - c.clientHeight < 80;
  });

  document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      el.input.value = button.dataset.prompt || button.textContent.trim();
      autoResize();
      updateInputTokens();
      updateSendState();
      el.input.focus();
    });
  });

  // ---------------- 基础设置事件绑定 ----------------

  // 滑块实时显示值 + dirty 标记
  function bindRange(rangeEl, valEl) {
    if (!rangeEl) return;
    const handler = () => {
      if (valEl) valEl.textContent = rangeEl.value;
      setDirty(true);
    };
    rangeEl.addEventListener("input", handler);
    rangeEl.addEventListener("change", handler);
  }

  bindRange(el.setMaxHistory, el.setMaxHistoryVal);
  bindRange(el.setTemperature, el.setTemperatureVal);
  bindRange(el.setFontScale, el.setFontScaleVal);

  [el.setMaxTokens, el.setSystemPrompt].forEach((elRef) => {
    elRef?.addEventListener("input", () => setDirty(true));
    elRef?.addEventListener("change", () => setDirty(true));
  });

  // 开关
  [el.setSendWithEnter, el.setShowTokenBar].forEach((track) => {
    track?.addEventListener("click", () => {
      track.classList.toggle("on");
      setDirty(true);
    });
  });

  // 主题选择
  el.setTheme?.querySelectorAll(".theme-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      el.setTheme.querySelectorAll(".theme-card").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      setDirty(true);
    });
  });

  el.saveSettingsBtn?.addEventListener("click", saveSettings);
  el.resetSettingsBtn?.addEventListener("click", resetSettings);
  el.openConsole?.addEventListener("click", openConsole);

  // ---------------- 控制台事件绑定 ----------------

  el.navItems?.forEach((nav) => {
    nav.addEventListener("click", () => switchSection(nav.dataset.section));
  });
  el.consoleBack?.addEventListener("click", closeConsole);

  // 键盘：Esc 优先关 console，其次关 setup（locked 时不关 setup）
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (el.settingsConsole?.classList.contains("is-open")) {
      closeConsole();
    } else if (el.setup?.classList.contains("is-open") && !state.locked) {
      hideSetup();
    }
  });

  // 点击 setup 遮罩（::before）关闭——locked 时不关（还没配服务商）
  el.setup?.addEventListener("click", (e) => {
    if (state.locked) return;
    // 只有点到蒙版本身（不是 setup-card 或里面的内容）才关
    if (e.target === el.setup) hideSetup();
  });

  // 自动展开控制台（记住用户偏好）——等基础设置的门禁逻辑跑完后再执行
  // 已废弃：默认永远不自动进 console，用户手动点齿轮 → 高级 才会进。
  // 保留 SECTION_KEY 只用于记住上次看的是 console 里哪个分区。
  try {
    // 空——留个 try 占位防止 lint 警告
  } catch (_) {}

  // ---------------- 初始化 ----------------

  autoResize();
  updateInputTokens();
  updateSendState();

  (async function init() {
    await Promise.all([loadSessions(), loadProviders(), loadSettings()]);
    // 永远不自动进 console——用户点齿轮 → 进 setup，点"高级" → 进 console，返回 → 退出。
    // localStorage["simchat.advanced"] 历史残留，清掉避免每次刷新卡壳。
    try { localStorage.removeItem("simchat.advanced"); } catch (_) {}

    const lastSid = loadSessionId();
    if (lastSid) {
      // 恢复上次会话；若后端已删则静默回退到新对话
      await openSession(lastSid).catch(() => saveSessionId(null));
    }
    // Minecraft 风格随机 splash（subtitle.txt 已随静态资源发布）
    try {
      const resp = await fetch("/static/subtitle.txt", { cache: "no-cache" });
      if (resp.ok) {
        const text = await resp.text();
        const lines = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
        if (lines.length) {
          const splash = document.getElementById("welcome-splash");
          if (splash) {
            const pick = lines[Math.floor(Math.random() * lines.length)];
            splash.textContent = pick;
            if (Math.random() < 0.15) {
              // 偶尔给 splash 里每个字符随机上色
              splash.innerHTML = Array.from(pick)
                .map((ch) => {
                  const hue = Math.floor(Math.random() * 360);
                  return '<span style="color:hsl(' + hue + ',85%,55%)">' + escapeHtml(ch) + "</span>";
                })
                .join("");
            }
          }
        }
      }
    } catch (_) {
      /* splash 加载失败不影响主流程 */
    }
  })();
})();
