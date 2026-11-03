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
    providerAccordion: document.getElementById("provider-accordion"),
    providerForm: document.getElementById("provider-form"),
    providerFields: document.getElementById("provider-fields"),
    providerPresets: document.getElementById("provider-presets"),
    testProvider: document.getElementById("test-provider"),
    saveProvider: document.getElementById("save-provider"),
    welcome: document.getElementById("welcome"),
    messages: document.getElementById("messages"),
    composer: document.getElementById("composer"),
    lockBanner: document.getElementById("lock-banner"),
    lockText: document.getElementById("lock-text"),
    lockConfig: document.getElementById("lock-config"),

    // 工作目录选择器
    workspaceChip: document.getElementById("workspace-chip"),
    workspaceChipName: document.getElementById("workspace-chip-name"),
    workspaceModal: document.getElementById("workspace-modal"),
    workspaceClose: document.getElementById("workspace-close"),
    workspaceUp: document.getElementById("workspace-up"),
    workspaceCurrentPath: document.getElementById("workspace-current-path"),
    workspaceManualPath: document.getElementById("workspace-manual-path"),
    workspaceManualOpen: document.getElementById("workspace-manual-open"),
    workspaceRoots: document.getElementById("workspace-roots"),
    workspaceList: document.getElementById("workspace-list"),
    workspaceMessage: document.getElementById("workspace-message"),
    workspaceClear: document.getElementById("workspace-clear"),
    workspaceCancel: document.getElementById("workspace-cancel"),
    workspaceConfirm: document.getElementById("workspace-confirm"),
    input: document.getElementById("input"),
    send: document.getElementById("send"),
    attachBtn: document.getElementById("attach-btn"),
    attachInput: document.getElementById("attach-input"),
    attachChips: document.getElementById("attach-chips"),
    modelSelect: document.getElementById("model-select"),
    modelRefresh: document.getElementById("model-refresh"),
    approvalMode: document.getElementById("approval-mode"),
    orbiterMode: document.getElementById("orbiter-mode"),
    voiceInputMode: document.getElementById("voice-input-mode"),
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

    // 网关概览
    gwHealthBadge: document.getElementById("gw-health-badge"),
    gwSocketUrl: document.getElementById("gw-socket-url"),
    gwAccessToken: document.getElementById("gw-access-token"),
    gwPassword: document.getElementById("gw-password"),
    gwSessionKey: document.getElementById("gw-session-key"),
    gwLanguage: document.getElementById("gw-language"),
    gwConnect: document.getElementById("gw-connect"),
    gwRefresh: document.getElementById("gw-refresh"),
    gwCopyUrl: document.getElementById("gw-copy-url"),
    gwCopyToken: document.getElementById("gw-copy-token"),
    gwAccessMsg: document.getElementById("gw-access-msg"),
    gwHandshakeTime: document.getElementById("gw-handshake-time"),
    gwHealth: document.getElementById("gw-health"),
    gwUptime: document.getElementById("gw-uptime"),
    gwTickInterval: document.getElementById("gw-tick-interval"),
    gwChannelRefresh: document.getElementById("gw-channel-refresh"),
    gwChannelHint: document.getElementById("gw-channel-hint"),

    // 通讯通道
    commChannelTabs: document.getElementById("comm-channel-tabs"),
    commForm: document.getElementById("comm-form"),
    commFormActions: document.getElementById("comm-form-actions"),
    commSave: document.getElementById("comm-save"),
    commClear: document.getElementById("comm-clear"),
    commFormMsg: document.getElementById("comm-form-msg"),

    // 实验功能 · Hippo
    hippoToggle: document.getElementById("hippo-toggle"),
    hippoToggleLabel: document.getElementById("hippo-toggle-label"),
    hippoStatusBadge: document.getElementById("hippo-status-badge"),

    // 启动与守护
    lifecycleAutostartTrack: document.getElementById("lifecycle-autostart-track"),
    lifecycleAutostartBadge: document.getElementById("lifecycle-autostart-badge"),
    lifecycleAutostartMeta: document.getElementById("lifecycle-autostart-meta"),
    lifecycleWatchdogTrack: document.getElementById("lifecycle-watchdog-track"),
    lifecycleWatchdogBadge: document.getElementById("lifecycle-watchdog-badge"),
    lifecycleWdRunning: document.getElementById("lifecycle-wd-running"),
    lifecycleWdPid: document.getElementById("lifecycle-wd-pid"),
    lifecycleWdRestarts: document.getElementById("lifecycle-wd-restarts"),
    lifecycleWdLast: document.getElementById("lifecycle-wd-last"),
    lifecycleServer: document.getElementById("lifecycle-server"),
    lifecycleWdPaused: document.getElementById("lifecycle-wd-paused"),
    lifecycleRefresh: document.getElementById("lifecycle-refresh"),
    lifecycleStopWatchdog: document.getElementById("lifecycle-stop-watchdog"),
    lifecycleStopService: document.getElementById("lifecycle-stop-service"),
    lifecycleMsg: document.getElementById("lifecycle-msg"),
    lifecycleConfirm: document.getElementById("lifecycle-confirm"),
    lifecycleConfirmCheck: document.getElementById("lifecycle-confirm-check"),
    lifecycleConfirmInput: document.getElementById("lifecycle-confirm-input"),
    lifecycleConfirmEnable: document.getElementById("lifecycle-confirm-enable"),
    lifecycleConfirmCancel: document.getElementById("lifecycle-confirm-cancel"),

    // 用户个人中心
    userBadge: document.getElementById("user-badge"),
    userAvatar: document.getElementById("user-avatar"),
    userName: document.getElementById("user-name"),
    profileAvatarPreview: document.getElementById("profile-avatar-preview"),
    profileAvatarInput: document.getElementById("profile-avatar-input"),
    profileAvatarClear: document.getElementById("profile-avatar-clear"),
    profileUsername: document.getElementById("profile-username"),
    profileBirthday: document.getElementById("profile-birthday"),
    profileEmergency: document.getElementById("profile-emergency"),
    profileMeta: document.getElementById("profile-meta"),
    profileMsg: document.getElementById("profile-msg"),
    profileSave: document.getElementById("profile-save"),

    // 实例监控
    instList: document.getElementById("instances-list"),
    instOnline: document.getElementById("inst-online"),
    instTotal: document.getElementById("inst-total"),
    instGenerated: document.getElementById("inst-generated"),
    instRefresh: document.getElementById("inst-refresh"),

    // 会话管理（控制台）
    sesTable: document.getElementById("sessions-table"),
    sesTbody: document.getElementById("sessions-tbody"),
    sesEmpty: document.getElementById("sessions-empty"),
    sesLoading: document.getElementById("sessions-loading"),
    sesFooterInfo: document.getElementById("sessions-footer-info"),
    sesRefresh: document.getElementById("ses-refresh"),
    sesActiveWithin: document.getElementById("ses-active-within"),
    sesLimit: document.getElementById("ses-limit"),
  };

  const state = {
    sessionId: null,
    streaming: false,
    stickToBottom: true,
    locked: true,
    mode: "chat",  // "chat" | "setup" | "console" —— 唯一事实源
    agents: "chat", // "chat" | "agent" —— Agent 开关的当前模式
    providers: [],
    presets: [],
    blocks: {},
    activeProvider: null,
    configured: null,
    resolved: null,
    drafts: {},
    model: null,          // composer 模型选择；null = 跟随服务商默认
    modelProvider: null,   // 选中模型所属的 provider id（新：聚合多 provider 模型时需要）
    approvalMode: "manual", // "manual" | "auto" | "off" | "custom"
    attachments: [],      // 待发送的文本附件 {name, content}

    // Agent 运行态
    agentRunId: null,       // 当前运行的 run_id
    agentPendingRunId: null, // 待审批的 run_id

    // 自动模型发现
    discoverTimer: null,   // 防抖计时器
    discovering: false,    // 是否正在 discover
    lastDiscoveredAt: {},  // 每个 provider 上次 discover 成功的时间戳

    // 设置页状态
    settings: null,
    settingsDirty: false,
    activeSection: "overview",

    // 用户档案
    profile: null,          // 后端返回的 profile.json 内容
    profileAvatar: "",      // 编辑中的头像 data URL（保存后写回 profile）

    // 通讯通道缓存
    comms: null,              // { active, channels: [...] }
    commsActiveChannel: null,  // 当前选中渲染的 channel id（与后端 .active 无关）

    // 启动与守护
    lifecycle: null,          // 后端 /api/lifecycle 快照
    lifecycleTimer: null,     // 守护状态轮询
    lifecycleBusy: false,
    commsPollTimer: null,     // 群机器人运行时状态轮询
    commsRuntimeMsg: null,    // { channelId, text, kind } 运行面板临时提示

    // 工作目录（workspace）
    workspace: null,         // { configured, exists, path, name }
    workspaceBrowse: null,   // 最近一次目录浏览结果

    // 实验功能
    hippoEnabled: false,

    // 实例监控
    deviceId: null,          // 持久化设备 ID（localStorage）
    tabId: null,             // 标签页 ID（sessionStorage，每 tab 唯一）
    heartbeatTimer: null,    // 心跳定时器
    instances: null,         // /api/instances 返回的缓存
    instancesPollTimer: null,// 实例列表轮询（当用户在 instances 分区时）

    // 会话管理（控制台）
    sessions: null,          // /api/sessions 返回的完整缓存
  };

  // ---------------- 模型提供商存档（固化 + 全局可调用） ----------------
  // 把后端返回的 providers（含已 discover 的 models）缓存到 localStorage，
  // 下次刷新页面先读缓存渲染 UI，再异步从后端刷新——避免每次打开都等 discover。
  // 同时暴露 window.SimChatProviderStore，使任何需要"选择模型"的地方都能调用。
  const PROVIDER_CACHE_KEY = "simchat.providers.cache";
  const PROVIDER_CACHE_MAX_AGE = 10 * 60 * 1000; // 10 分钟内视为新鲜

  const providerStore = {
    _data: null,

    /** 从 localStorage 读取缓存；过期或无数据返回 null */
    loadFromCache() {
      try {
        const raw = localStorage.getItem(PROVIDER_CACHE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !parsed.providers) return null;
        const age = Date.now() - (parsed.savedAt || 0);
        if (age > PROVIDER_CACHE_MAX_AGE) return null;
        this._data = parsed;
        return parsed;
      } catch (_) {
        return null;
      }
    },

    /** 把 providers 数据写入 localStorage 缓存 */
    saveToCache(data) {
      try {
        const payload = {
          providers: data.providers || [],
          presets: data.presets || [],
          configured: data.configured || null,
          resolved: data.resolved || null,
          preferred: data.preferred || null,
          blocks: data.blocks || [],
          savedAt: Date.now(),
        };
        localStorage.setItem(PROVIDER_CACHE_KEY, JSON.stringify(payload));
        this._data = payload;
      } catch (_) {
        /* localStorage 不可用时静默忽略 */
      }
    },

    /** 清除缓存 */
    clearCache() {
      try { localStorage.removeItem(PROVIDER_CACHE_KEY); } catch (_) {}
      this._data = null;
    },

    // —— 以下为全局可调用的便捷 API ——

    /** 获取所有 provider */
    getAll() {
      return (this._data && this._data.providers) || state.providers || [];
    },

    /** 按 ID 获取单个 provider */
    getProvider(id) {
      return this.getAll().find((p) => p.id === id) || null;
    },

    /** 获取当前 resolved（实际生效）的 provider */
    getResolved() {
      const id = (this._data && this._data.resolved) || state.resolved;
      if (id) {
        const p = this.getProvider(id);
        if (p) return p;
      }
      // 兜底：第一个 available 的
      return this.getAll().find((p) => p.available) || null;
    },

    /** 获取指定 provider 的模型列表 */
    getModels(providerId) {
      const p = this.getProvider(providerId);
      if (p && p.models && p.models.length) return p.models;
      // 从 fields.options 兜底
      if (p && p.fields) {
        for (const f of p.fields) {
          if ((f.name === "model" || f.name === "model_name") && Array.isArray(f.options) && f.options.length) {
            return f.options;
          }
        }
      }
      return [];
    },

    /** 获取默认 provider 的模型列表（composer 下拉用） */
    getDefaultModels() {
      const resolved = this.getResolved();
      if (resolved) {
        const models = this.getModels(resolved.id);
        if (models.length) return { provider: resolved, models };
      }
      // 兜底：遍历所有 provider 找有 models 的
      for (const p of this.getAll()) {
        const models = this.getModels(p.id);
        if (models.length) return { provider: p, models };
      }
      return { provider: null, models: [] };
    },

    /** 获取指定 provider 的默认模型名 */
    getDefaultModelName(providerId) {
      const p = this.getProvider(providerId);
      if (!p) return "";
      const v = p.values || {};
      return v.model || v.model_name || (this.getModels(providerId)[0] || "");
    },
  };

  // 暴露到全局——任何地方都可以调用 window.SimChatProviderStore
  window.SimChatProviderStore = providerStore;

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

  // Token 预算常量（与后端 runtime/agent/loop.py 保持一致）
  const TOKEN_BUDGET = 16384;
  const TOKEN_COMPACTION_THRESHOLD = 12288;

  // 根据 token 比例返回等级：'ok' / 'warn' / 'critical'
  function tokenLevel(current, budget) {
    const ratio = budget > 0 ? current / budget : 0;
    if (ratio >= 0.95) return "critical";
    if (ratio >= 0.8) return "warn";
    return "ok";
  }

  // Agent 当前运行的 token 用量追踪
  let currentAgentTaskTokens = { prompt: 0, completion: 0, last_prompt: 0, last_completion: 0 };

  // ---------------- 每日使用统计（localStorage） ----------------
  // 从 kirara 迁移过来的每日 token 用量持久化模块
  const UT_STORAGE_KEY = "simchat_usage_daily";
  const UT_LIMIT_KEY = "simchat_usage_limit_config";
  const UT_LIMIT_DEFAULT = { enabled: false, limit: 50000, locked: false };

  function utReadAll() {
    try {
      const raw = localStorage.getItem(UT_STORAGE_KEY);
      if (!raw) return {};
      const obj = JSON.parse(raw);
      return (obj && typeof obj === "object") ? obj : {};
    } catch (_) { return {}; }
  }

  function utWriteAll(data) {
    try {
      localStorage.setItem(UT_STORAGE_KEY, JSON.stringify(data));
    } catch (_) { /* localStorage 不可用时静默忽略 */ }
  }

  function utTodayKey() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  // 累加一条用量到当日记录（Agent / Chat 都在结束时调用）
  function recordDailyUsage(entry) {
    const inputTokens = Number.isFinite(entry.inputTokens) ? entry.inputTokens : 0;
    const outputTokens = Number.isFinite(entry.outputTokens) ? entry.outputTokens : 0;
    const durationMs = Number.isFinite(entry.durationMs) ? entry.durationMs : 0;
    const all = utReadAll();
    const key = utTodayKey();
    if (!all[key]) all[key] = { input_tokens: 0, output_tokens: 0, time_ms: 0, exchanges: 0 };
    all[key].input_tokens += inputTokens;
    all[key].output_tokens += outputTokens;
    all[key].time_ms += durationMs;
    all[key].exchanges += 1;
    utWriteAll(all);
  }

  function utReadLimitConfig() {
    try {
      const raw = localStorage.getItem(UT_LIMIT_KEY);
      if (!raw) return Object.assign({}, UT_LIMIT_DEFAULT);
      const obj = JSON.parse(raw);
      return {
        enabled: obj.enabled === true,
        limit: Number.isFinite(obj.limit) && obj.limit > 0 ? obj.limit : UT_LIMIT_DEFAULT.limit,
        locked: obj.locked === true,
      };
    } catch (_) { return Object.assign({}, UT_LIMIT_DEFAULT); }
  }

  function utWriteLimitConfig(cfg) {
    try { localStorage.setItem(UT_LIMIT_KEY, JSON.stringify(cfg)); } catch (_) {}
  }

  // 今日是否已达上限（供 sendMessage 在发送前检查）
  function utIsLimitExceeded() {
    const cfg = utReadLimitConfig();
    if (!cfg.enabled) return false;
    const all = utReadAll();
    const rec = all[utTodayKey()] || { input_tokens: 0, output_tokens: 0 };
    return (rec.input_tokens + rec.output_tokens) >= cfg.limit;
  }

  // 获取今日用量（用于 UI 显示）
  function utGetTodayUsage() {
    const all = utReadAll();
    const rec = all[utTodayKey()] || { input_tokens: 0, output_tokens: 0 };
    return { used: (rec.input_tokens || 0) + (rec.output_tokens || 0), input: rec.input_tokens || 0, output: rec.output_tokens || 0 };
  }

  // 今日已用量占上限的百分比（0-100，上限未启用时返回 0）
  function utGetUsagePercent() {
    const cfg = utReadLimitConfig();
    if (!cfg.enabled || !cfg.limit) return 0;
    const usage = utGetTodayUsage();
    return Math.min(100, (usage.used / cfg.limit) * 100);
  }

  // ---------------- 每日用量 UI（DOM 已硬编码在 index.html） ----------------
  const _quotaBannerEl = document.getElementById("quota-limit-banner");
  const _quotaUsedLabel = document.getElementById("quota-used-label");
  const _quotaLimitLabel = document.getElementById("quota-limit-label");
  const _quotaBarFill = document.getElementById("quota-bar-fill");
  const _quotaBarWrap = document.getElementById("daily-usage-bar");

  function updateQuotaUI() {
    const cfg = utReadLimitConfig();
    const usage = utGetTodayUsage();

    // 超限横幅
    if (_quotaBannerEl) {
      const exceeded = cfg.enabled && usage.used >= cfg.limit;
      _quotaBannerEl.classList.toggle("hidden", !exceeded);
    }

    // 进度条
    if (_quotaBarWrap) {
      if (cfg.enabled) {
        const pct = Math.min(100, (usage.used / cfg.limit) * 100);
        if (_quotaBarFill) {
          _quotaBarFill.style.width = pct + "%";
          _quotaBarFill.className = "usage-bar-fill level-" + tokenLevel(usage.used, cfg.limit);
        }
        if (_quotaUsedLabel) _quotaUsedLabel.textContent = "今日 " + formatTokens(usage.used);
        if (_quotaLimitLabel) _quotaLimitLabel.textContent = "/ " + formatTokens(cfg.limit);
        _quotaBarWrap.style.display = "flex";
      } else {
        if (_quotaUsedLabel) _quotaUsedLabel.textContent = "今日 " + formatTokens(usage.used);
        if (_quotaLimitLabel) _quotaLimitLabel.textContent = "（未启用限制）";
        if (_quotaBarFill) _quotaBarFill.style.width = "0%";
        _quotaBarWrap.style.display = "flex";
      }
    }
  }

  // 暴露到 window，方便设置页调用
  window.utReadLimitConfig = utReadLimitConfig;
  window.utWriteLimitConfig = utWriteLimitConfig;
  window.utIsLimitExceeded = utIsLimitExceeded;
  window.utGetTodayUsage = utGetTodayUsage;
  window.utGetUsagePercent = utGetUsagePercent;
  window.updateQuotaUI = updateQuotaUI;

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

  /* Markdown 渲染：优先使用 marked.js + DOMPurify（CDN 加载），降级到极简实现。 */
  function renderMarkdown(text) {
    const src = String(text || "");

    // 优先路径：marked + DOMPurify
    if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
      try {
        marked.setOptions({
          breaks: true,        // 单个换行也渲染为 <br>
          gfm: true,           // GitHub Flavored Markdown
          headerIds: false,
          mangle: false,
        });
        const rawHtml = marked.parse(src);
        const clean = DOMPurify.sanitize(rawHtml, {
          ADD_ATTR: ["target"],
          FORBID_TAGS: ["iframe", "script", "style"],
        });
        return clean;
      } catch (e) {
        console.warn("[SimChat] marked 渲染失败，降级:", e);
      }
    }

    // 降级：极简实现（兼容无网络环境）
    const codeBlocks = [];
    let escaped = escapeHtml(src);
    escaped = escaped.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code) => {
      const index = codeBlocks.length;
      codeBlocks.push(
        '<pre class="code-block"><code>' + code.replace(/\n$/, "") + "</code></pre>"
      );
      return "\u0000BLOCK" + index + "\u0000";
    });
    escaped = escaped.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
    escaped = escaped.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    const html = escaped
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
    // 过滤掉空会话（只有"+"按钮才能开新对话）
    const valid = (sessions || []).filter((s) => (s.message_count || 0) > 0);
    if (!valid.length) {
      const empty = document.createElement("div");
      empty.className = "session-empty";
      empty.textContent = "暂无会话";
      el.sessionList.appendChild(empty);
      return;
    }

    for (const session of valid) {
      const item = document.createElement("div");
      item.className = "session-item" + (session.id === state.sessionId ? " active" : "");
      item.dataset.id = session.id;
      item.title = session.title || "新对话";

      const title = document.createElement("span");
      title.className = "session-title";
      title.textContent = session.title || "新对话";
      item.appendChild(title);

      // 模式标识符：区分 Agent 会话与对话会话
      const mode = session.mode === "agent" ? "agent" : "chat";
      const modeChip = document.createElement("span");
      modeChip.className = "session-mode session-mode--" + mode;
      modeChip.textContent = mode === "agent" ? "Agent" : "对话";
      item.appendChild(modeChip);

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

  async function openSession(sid, options) {
    options = options || {};
    if (state.streaming) return;
    try {
      const data = await api("/api/sessions/" + encodeURIComponent(sid));
      const session = data.session;
      setSessionId(session.id);
      state.stickToBottom = true;
      el.title.textContent = session.title || "新对话";
      el.messages.innerHTML = "";

      // 按会话来源恢复对应模式，避免 Agent 会话以对话模式继续
      setAgentMode(session.mode === "agent" ? "agent" : "chat");

      const history = session.messages || [];
      for (const message of history) addMessage(message.role, message.content, true);

      // enterMode 有早退守卫（mode 相同时直接 return），welcome 显隐必须在这里同步
      showWelcome(history.length === 0);

      // 只有解锁（配好服务商）才进 chat 模式；否则保持 setup 不被覆盖
      if (!state.locked) enterMode("chat");

      closeSidebar();
      scrollToBottom(true);
      await loadSessions();
      if (!state.locked) el.input.focus();
    } catch (err) {
      if (options.silent) {
        // 启动时恢复的会话可能已被删除（或旧版本未落盘）：静默清理并回到新对话
        saveSessionId(null);
        startNewChat();
        return;
      }
      addMessage("assistant", "加载会话失败：" + err.message);
    }
  }

  function startNewChat() {
    if (state.streaming) return;
    setSessionId(null);
    state.stickToBottom = true;
    el.messages.innerHTML = "";
    recalcSessionTokens();
    // 同上：enterMode 可能早退，welcome 显隐在此同步
    showWelcome(true);
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
    if (!workspaceReady()) return "未选择工作目录";
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

  function workspaceReady() {
    const ws = state.workspace;
    return !!(ws && ws.configured && ws.exists);
  }

  /* 服务商或工作目录任一缺失，输入区都保持锁定。 */
  function interactionBlocked() {
    return state.locked || !workspaceReady();
  }

  function renderLockBanner() {
    if (state.locked) {
      el.lockText.textContent = "尚未配置可用的服务商，无法对话。";
      el.lockConfig.textContent = "配置服务商";
      el.lockConfig.dataset.action = "provider";
      return;
    }
    const ws = state.workspace;
    if (!ws || !ws.configured) {
      el.lockText.textContent = "尚未选择工作目录，选择后即可开始对话。";
      el.lockConfig.textContent = "选择工作目录";
      el.lockConfig.dataset.action = "workspace";
      return;
    }
    el.lockText.textContent = "工作目录不存在：" + ws.path;
    el.lockConfig.textContent = "重新选择";
    el.lockConfig.dataset.action = "workspace";
  }

  function applyInteractionGate() {
    const blocked = interactionBlocked();
    el.lockBanner.classList.toggle("hidden", !blocked);
    el.composer.classList.toggle("hidden", blocked);
    el.tokenBar?.classList.toggle("hidden", blocked);
    // 每日用量进度条跟随 token-bar 一起显隐
    const dub = document.getElementById("daily-usage-bar");
    if (dub) dub.classList.toggle("hidden", blocked);
    const qb = document.getElementById("quota-limit-banner");
    if (qb) qb.classList.toggle("hidden", blocked || !utIsLimitExceeded());
    el.statusDot.classList.toggle("locked", blocked);
    el.statusDot.classList.toggle("streaming", !blocked && state.streaming);
    el.statusDot.title = connectionLabel();
    renderLockBanner();
    updateSendState();
  }

  function setLocked(locked, keepSetup) {
    state.locked = locked;
    el.setupBack.classList.toggle("hidden", locked);

    if (locked) {
      if (!state.sessionId) el.title.textContent = "连接服务商";
      if (state.mode !== "setup") showSetup();
    } else {
      if (state.mode === "setup" && !keepSetup) hideSetup();
    }
    applyInteractionGate();
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
    updateModelSelect();

    if (state.mode === "setup") {
      renderProviderAccordion();
      renderProviderForm();
      renderPresets();
    }

    // 固化到 localStorage——下次刷新先读缓存，不等后端 discover
    providerStore.saveToCache(data);
  }

  // ---------------- Composer 工具条：模型选择 / 附件 / 预留控件 ----------------

  /* 模型下拉：聚合所有 provider 的所有模型，用 optgroup 按 provider 分组。
     这样无论用户配了 ollama + openai_compat 还是只配了一个，下拉里都能看到所有选项。
     option.value 格式为 "providerId::modelName"（双冒号分隔），避免不同 provider 有同名模型时冲突。 */
  function updateModelSelect() {
    const select = el.modelSelect;
    if (!select) return;
    const providers = state.providers || [];

    select.innerHTML = "";

    // ------- Auto Model（第一个选项，默认选中） -------
    const autoProvider = providers.find((p) => p.id === "auto");
    const autoOpt = document.createElement("option");
    autoOpt.value = "__auto__";
    autoOpt.textContent = "⚡ Auto Model (自动选择最优)";
    autoOpt.dataset.providerId = "auto";
    if (autoProvider && autoProvider.resolved) {
      autoOpt.textContent += `  [${autoProvider.resolved}]`;
    }
    select.appendChild(autoOpt);

    // 收集所有有模型的 provider（跳过 auto——它是虚拟 provider，没有自己的模型）
    const providersWithModels = [];
    for (const p of providers) {
      if (p.id === "auto") continue;
      let models = [];
      if (p.models && p.models.length) {
        models = p.models.slice();
      } else if (p.values) {
        // 兜底：从 values 里拿单个模型名
        const single = p.values.model || p.values.model_name;
        if (single) models = [single];
      }
      if (!models.length) continue;
      providersWithModels.push({ provider: p, models });
    }

    if (!providersWithModels.length) {
      select.disabled = false; // Auto 始终可选
      select.title = "选择模型";
      // 默认 Auto
      select.value = "__auto__";
      state.model = null;
      state.modelProvider = "auto";
      return;
    }

    select.disabled = false;

    // 当前已选：从 state.model + state.modelProvider 拼 key；或从 target provider 的默认模型取
    let currentKey = null; // 格式 "providerId::modelName"

    for (const group of providersWithModels) {
      const { provider, models } = group;

      const optgroup = document.createElement("optgroup");
      optgroup.label = provider.label || provider.id;

      // 确定这个 provider 的默认选中项
      const values = provider.values || {};
      const defaultModel = values.model || values.model_name || models[0] || "";

      for (const name of models) {
        const opt = document.createElement("option");
        const key = provider.id + "::" + name;
        opt.value = key;
        opt.textContent = name;

        // 选中逻辑优先顺序：
        // 1. state 里已有的 modelProvider+model 匹配
        // 2. 当前 resolved provider 的默认模型
        // 3. 第一个 provider 的第一个模型兜底
        if (state.modelProvider && state.model &&
            state.modelProvider === provider.id && state.model === name) {
          opt.selected = true;
          currentKey = key;
        } else if (!currentKey && state.resolved === provider.id && name === defaultModel) {
          // resolved provider 的默认模型自动选中
          opt.selected = true;
          currentKey = key;
        }

        optgroup.appendChild(opt);
      }

      // 兜底：如果还没选中过任何，resolved provider 没找到，选第一个 provider 的第一个
      if (!currentKey && providersWithModels[0].provider.id === provider.id) {
        // 先不设，等外层循环完再兜底
      }

      select.appendChild(optgroup);
    }

    // 最终兜底：还没选中
    if (!currentKey) {
      // 如果 state 指向 auto 或压根没设，优先 Auto Model
      const preferAuto = !state.modelProvider || state.modelProvider === "auto";
      const targetOpt = preferAuto
        ? select.querySelector('option[value="__auto__"]')
        : select.querySelector("option");
      if (targetOpt) {
        targetOpt.selected = true;
        currentKey = targetOpt.value;
      }
    }

    // 同步到 state
    if (currentKey === "__auto__") {
      state.model = null;
      state.modelProvider = "auto";
    } else if (currentKey && currentKey.includes("::")) {
      const idx = currentKey.indexOf("::");
      state.modelProvider = currentKey.substring(0, idx);
      state.model = currentKey.substring(idx + 2);
    } else {
      state.model = null;
      state.modelProvider = null;
    }

    const target = providers.find((p) => p.id === state.modelProvider);
    select.title = "选择模型" + (target ? "（" + target.label + "）" : "");
  }

  function setAgentOnlyVisible(visible) {
    document.querySelectorAll(".agent-only").forEach((node) => {
      node.classList.toggle("hidden", !visible);
    });
  }

  /* 预留开关控件：Orbiter / 语音输入。只做 UI 状态，不接后端。 */
  function bindReservedToggle(btn) {
    btn?.addEventListener("click", () => btn.classList.toggle("on"));
  }

  const ATTACH_MAX_BYTES = 256 * 1024;

  function renderAttachChips() {
    if (!el.attachChips) return;
    el.attachChips.innerHTML = "";
    el.attachChips.classList.toggle("hidden", state.attachments.length === 0);
    state.attachments.forEach((att, index) => {
      const chip = document.createElement("span");
      chip.className = "attach-chip";
      chip.title = att.name + "（" + att.content.length + " 字符）";

      const name = document.createElement("span");
      name.className = "attach-chip-name";
      name.textContent = att.name;
      chip.appendChild(name);

      const remove = document.createElement("button");
      remove.className = "attach-chip-x";
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", "移除附件 " + att.name);
      remove.addEventListener("click", () => {
        state.attachments.splice(index, 1);
        renderAttachChips();
        updateSendState();
      });
      chip.appendChild(remove);

      el.attachChips.appendChild(chip);
    });
  }

  const ATTACH_TEXT_EXT =
    /\.(txt|md|markdown|json|jsonl|js|ts|jsx|tsx|py|java|c|h|cpp|hpp|cs|go|rs|rb|php|html?|css|scss|less|xml|ya?ml|toml|ini|cfg|conf|log|csv|sql|sh|bat|ps1|vue|svelte)$/i;

  function attachFile(file) {
    if (!file) return;
    if (file.size > ATTACH_MAX_BYTES) {
      window.alert("文件过大（" + Math.ceil(file.size / 1024) + " KB），目前仅支持 256 KB 以内的文本文件。");
      return;
    }
    if (!ATTACH_TEXT_EXT.test(file.name) && !(file.type || "").startsWith("text/")) {
      window.alert("目前仅支持文本类文件（代码 / 文档 / 数据），二进制文件暂不支持。");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      state.attachments.push({ name: file.name, content: String(reader.result || "") });
      renderAttachChips();
      updateSendState();
      el.input.focus();
    };
    reader.onerror = () => window.alert("读取文件失败：" + file.name);
    reader.readAsText(file);
  }

  /* 发送前把附件内容拼进消息正文，发送后清空 */
  function composeMessageWithAttachments(text) {
    if (!state.attachments.length) return text;
    const parts = state.attachments.map(
      (att) => "【附件 " + att.name + "】\n" + att.content
    );
    parts.push(text);
    return parts.join("\n\n");
  }

  function clearAttachments() {
    state.attachments = [];
    renderAttachChips();
  }

  // ---------------- 预留接口：Agent 切换 / IDE 跳转 ----------------

  function getCurrentMode() {
    return (el.agentToggle?.dataset.mode === "agent") ? "agent" : "chat";
  }

  function setAgentMode(next) {
    const track = el.agentToggle;
    if (!track) return;
    next = next === "agent" ? "agent" : "chat";
    track.dataset.mode = next;
    track.setAttribute("aria-pressed", String(next === "agent"));
    state.agents = next;
    if (el.agentToggleLabel) {
      el.agentToggleLabel.textContent = next === "agent" ? "Agent" : "对话";
    }
    // 审批 / Orbiter 等控件仅在 Agent 模式显示（功能本身仍为预留）
    setAgentOnlyVisible(next === "agent");
    // 切换底下 welcome-sub 文案（不动 splash）
    const subEl = document.getElementById("welcome-sub");
    if (subEl) {
      if (next === "agent") {
        subEl.textContent = "Agent 模式 · 读写本地项目 + Shell · 会话自动保存在本地";
      } else {
        subEl.textContent = "SimChat 本体独立对话 · 会话自动保存在本地";
      }
    }
  }

  function toggleAgentMode() {
    setAgentMode(getCurrentMode() === "agent" ? "chat" : "agent");
  }

  function renderProviderAccordion() {
    if (!el.providerAccordion) return; // 防御性检查
    el.providerAccordion.innerHTML = "";
    for (const provider of state.providers) {
      if (provider.id === "auto") continue; // Auto Model 不在这里配置

      const block = state.blocks["provider." + provider.id] || {};
      const item = document.createElement("div");
      item.className = "provider-accordion-item" + (provider.id === state.activeProvider ? " open" : "");
      item.dataset.providerId = provider.id;

      // ------- Header -------
      const header = document.createElement("div");
      header.className = "provider-accordion-header";
      header.setAttribute("role", "button");
      header.tabIndex = 0;
      header.setAttribute("aria-expanded", provider.id === state.activeProvider ? "true" : "false");

      const title = document.createElement("span");
      title.className = "provider-accordion-title";
      title.textContent = block.label || provider.label;
      header.appendChild(title);

      // 状态徽章
      const badge = document.createElement("span");
      let badgeClass = "empty";
      let badgeText = "未配置";
      if (provider.available) {
        badgeClass = "ok";
        badgeText = "可用";
      } else if (provider.last_test_error) {
        badgeClass = "warn";
        badgeText = "异常";
      }
      badge.className = "provider-accordion-badge " + badgeClass;
      badge.innerHTML = '<span class="dot"></span>' + badgeText;
      header.appendChild(badge);

      const arrow = document.createElement("span");
      arrow.className = "provider-accordion-arrow";
      arrow.textContent = "▶";
      header.appendChild(arrow);

      // 切换展开/收起
      const toggleExpand = () => {
        const willOpen = !item.classList.contains("open");
        // 关闭所有其他面板（accordion 行为）
        document.querySelectorAll(".provider-accordion-item").forEach((el) => {
          el.classList.remove("open");
          el.querySelector(".provider-accordion-header")?.setAttribute("aria-expanded", "false");
        });
        if (willOpen) {
          item.classList.add("open");
          header.setAttribute("aria-expanded", "true");
          state.activeProvider = provider.id;
          renderProviderForm();
          updateModelSelect();
          // 异步 discover 拿最新 models
          const draft = state.drafts[provider.id] || {};
          const cfg = {};
          for (const f of provider.fields || []) cfg[f.name] = String(draft[f.name] || "").trim();
          scheduleDiscoverProvider(provider.id, cfg);
        } else {
          state.activeProvider = null;
          updateModelSelect();
        }
      };

      header.addEventListener("click", toggleExpand);
      header.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleExpand(); }
      });

      item.appendChild(header);

      // ------- Body -------
      const body = document.createElement("div");
      body.className = "provider-accordion-body";
      const inner = document.createElement("div");
      inner.className = "provider-accordion-body-inner";

      if (provider.id === state.activeProvider) {
        const detail = document.createElement("div");
        detail.className = "provider-accordion-detail";
        detail.textContent = provider.detail || "";
        inner.appendChild(detail);
      }

      body.appendChild(inner);
      item.appendChild(body);

      el.providerAccordion.appendChild(item);
    }
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
      let datalist = null;
      if (Array.isArray(field.options) && field.options.length) {
        // 有 options 时：用 <input> + <datalist>（既有补全又能自由输入，比纯 <select> 灵活）
        const datalistId = "dl-" + provider.id + "-" + field.name;
        datalist = document.createElement("datalist");
        datalist.id = datalistId;
        const seen = new Set();
        for (const val of field.options) {
          if (seen.has(val)) continue;
          seen.add(val);
          const opt = document.createElement("option");
          opt.value = val;
          datalist.appendChild(opt);
        }
        control = document.createElement("input");
        control.type = "text";
        control.setAttribute("list", datalistId);
        control.value = draft[field.name] || "";
        control.placeholder = field.placeholder || "从下拉选择或手动输入";
        control.autocomplete = "off";
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
        // api_base / api_key / base_url 变化时自动触发 discover（防抖 1 秒）
        const discoverTriggers = {
          openai_compat: ["api_base", "api_key"],
          ollama: ["base_url"],
        };
        const triggerFields = discoverTriggers[provider.id] || [];
        if (triggerFields.includes(field.name)) {
          scheduleDiscoverProvider(provider.id, collectConfig());
        }
      });
      control.addEventListener("change", () => {
        draft[field.name] = control.value;
      });
      wrap.appendChild(control);
      if (datalist) wrap.appendChild(datalist);

      // api_base / base_url 旁边放个「🔍 探测模型」手动按钮
      if ((field.name === "api_base" || field.name === "base_url") && provider.id !== "auto") {
        const probeBtn = document.createElement("button");
        probeBtn.type = "button";
        probeBtn.className = "field-probe-btn";
        probeBtn.textContent = "🔍 探测模型";
        probeBtn.title = "用当前 API Base + Key 自动发现可用模型";
        probeBtn.addEventListener("click", (e) => {
          e.preventDefault();
          const cfg = collectConfig();
          discoverProvider(provider.id, cfg, false);
        });
        wrap.appendChild(probeBtn);
      }

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
      renderProviderAccordion();
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

  // 关闭动画：先挂 .is-closing 播退场动画（CSS 里 .is-closing 保持显示），
  // 播完才摘类真正隐藏；setTimeout 兜底，防止 animationend 丢失导致面板卡住。
  function closeWithAnim(layer) {
    if (!layer.classList.contains("is-open")) return;
    layer.classList.remove("is-open");
    layer.classList.add("is-closing");
    const card = layer.querySelector(".setup-card") || layer;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      layer.classList.remove("is-closing");
      card.removeEventListener("animationend", finish);
    };
    card.addEventListener("animationend", finish);
    setTimeout(finish, 320);
  }

  function enterMode(next) {
    if (state.mode === next) return;
    const prev = state.mode;
    console.log("[MODE]", prev, "→", next, new Error().stack.split("\n").slice(2, 4).join(" ← "));
    state.mode = next;

    // 蒙版层：只用 .is-open 类控制显隐（CSS 里 display:none 默认，display:flex 需 .is-open）
    // 绝不碰 [hidden] 属性或 .hidden 类——之前就是被 CSS 的 display:flex 覆盖导致永远显示。
    closeWithAnim(el.setup);
    closeWithAnim(el.settingsConsole);

    if (next === "chat") {
      // 主界面全开
      el.conversation.style.display = "";
      el.messages.style.display = "";
      showWelcome(el.messages.children.length === 0);
      document.body.style.overflow = "";
      // setup → chat 切换后重新按 resolved provider 刷新下拉
      updateModelSelect();
    } else if (next === "setup") {
      // 右侧抽屉面板：底下主界面保持可见（有半透明遮罩）
      // 不再硬藏 messages/welcome——PC 风格，边看聊天边改设置
      el.setup.classList.add("is-open");
      el.setupBack.style.display = state.locked ? "none" : "";
      document.body.style.overflow = "";
      if (prev !== "setup") {
      renderProviderAccordion();
        renderProviderForm();
        renderPresets();
        loadSettings();
        // 进 setup 也立刻同步一次（按 activeProvider 优先）
        updateModelSelect();
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
  function openConsole(section) {
    enterMode("console");
    // 支持直接打开指定分区（如点侧边栏用户徽章进个人中心）
    const target = typeof section === "string" && section
      ? section
      : (localStorage.getItem(SECTION_KEY) || "overview").trim();
    switchSection(target);
    renderOverview();
  }
  function closeConsole() {
    // 关掉控制台后回到 chat 还是 setup，看 locked 状态
    stopLifecyclePolling();
    closeLifecycleConfirm();
    try { localStorage.removeItem(ADVANCED_KEY); } catch (_) {}
    enterMode(state.locked ? "setup" : "chat");
  }

  async function loadProviders() {
    // 第一步：先尝试从 localStorage 缓存读，立刻渲染 UI
    // 这样刷新页面后模型下拉立即有数据，不用等后端 discover
    const cached = providerStore.loadFromCache();
    if (cached && cached.providers && cached.providers.length) {
      setProviderData({ ...cached, available: cached.providers.some((p) => p.available) });
    }

    // 第二步：异步从后端拉最新数据（会覆盖缓存渲染的结果）
    try {
      const data = await api("/api/providers");
      setProviderData(data);
    } catch (err) {
      // 后端不可用：如果有缓存就继续用缓存；否则进入 locked 状态
      if (!cached || !cached.providers || !cached.providers.some((p) => p.available)) {
        state.locked = true;
        state.providers = [];
        setLocked(true);
        showSetup();
        setSetupMessage("无法检测服务商：" + err.message, "error");
      }
      // 有缓存就静默继续用缓存，只在 console 里警告
      console.warn("[SimChat] 后端不可用，使用本地缓存的 providers");
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

  // ---------------- 自动模型发现 ----------------

  async function discoverProvider(providerId, draftValues, silent) {
    /** 调 /api/providers/discover 拉模型列表，更新 state.providers 后重渲染表单。
        silent=true 时不弹 toast（输入过程中自动 discover 用）。 */
    if (state.discovering) return;
    state.discovering = true;
    const provider = (state.providers || []).find((p) => p.id === providerId);
    if (!provider) { state.discovering = false; return; }

    try {
      const result = await api("/api/providers/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerId, config: draftValues || {} }),
      });

      if (result.ok && result.models && result.models.length) {
        // 找到当前 provider，更新 models + fields.options
        const providers = state.providers || [];
        for (const p of providers) {
          if (p.id === providerId) {
            p.models = result.models;
            for (const f of p.fields || []) {
              if (f.name === "model_name" || f.name === "model") {
                f.options = result.models.slice();
                f.hint = "已探测到 " + result.models.length + " 个模型";
                // 保留用户当前输入的模型名在 options 里
                const curModel = (draftValues && (draftValues.model_name || draftValues.model)) || f.value;
                if (curModel && !f.options.includes(curModel)) {
                  f.options.unshift(curModel);
                }
              }
            }
            break;
          }
        }
        state.lastDiscoveredAt[providerId] = Date.now();
        renderProviderForm();
        updateModelSelect();
        if (!silent) {
          setSetupMessage("✓ " + (result.message || ("发现 " + result.models.length + " 个模型")), "");
        }
      } else if (!silent && result.message) {
        setSetupMessage(result.message, "error");
      }
    } catch (err) {
      if (!silent) setSetupMessage("模型发现失败: " + err.message, "error");
    } finally {
      state.discovering = false;
    }
  }

  function scheduleDiscoverProvider(providerId, draftValues) {
    /** 防抖触发自动 discover：1 秒内无新输入才真正发起请求。 */
    if (state.discoverTimer) clearTimeout(state.discoverTimer);
    state.discoverTimer = setTimeout(() => {
      clearTimeout(state.discoverTimer);
      state.discoverTimer = null;
      discoverProvider(providerId, draftValues, true);
    }, 1000);
  }

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
    el.send.disabled =
      state.streaming ||
      state.locked ||
      !workspaceReady() ||
      (!el.input.value.trim() && state.attachments.length === 0);
  }

  function setStreaming(streaming) {
    state.streaming = streaming;
    el.statusDot.classList.toggle("streaming", streaming && !interactionBlocked());
    el.statusDot.title = connectionLabel();
    updateSendState();
  }

  // ---------------- Agent SSE 辅助函数 ----------------

  function riskLabel(risk) {
    const map = { read: "只读", write: "写操作", dangerous: "危险" };
    return map[risk] || risk;
  }

  function createPlanCard(steps, raw) {
    const card = document.createElement("div");
    card.className = "agent-card agent-plan-card";
    const header = document.createElement("div");
    header.className = "agent-card-header";
    header.innerHTML = '<svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>执行计划';
    card.appendChild(header);
    const ul = document.createElement("ul");
    ul.className = "plan-steps";
    (steps || []).forEach((text, i) => {
      const li = document.createElement("li");
      li.className = "plan-step";
      li.dataset.idx = i;
      li.innerHTML = '<span class="plan-step-check">✓</span><span class="plan-step-text"></span>';
      li.querySelector(".plan-step-text").textContent = text;
      ul.appendChild(li);
    });
    card.appendChild(ul);
    return card;
  }

  function updatePlanDone(cardsContainer, doneCount) {
    const planCard = cardsContainer.querySelector(".agent-plan-card");
    if (!planCard) return;
    const steps = planCard.querySelectorAll(".plan-step");
    steps.forEach((li) => {
      const idx = parseInt(li.dataset.idx, 10);
      li.classList.toggle("done", idx < doneCount);
    });
  }

  function createThoughtCard(content) {
    const card = document.createElement("div");
    card.className = "agent-card agent-thought-card";
    const header = document.createElement("div");
    header.className = "agent-card-header";
    header.innerHTML = '<svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>思考';
    card.appendChild(header);
    const body = document.createElement("div");
    body.className = "thought-content";
    body.textContent = content || "…";
    card.appendChild(body);
    return card;
  }

  function createToolCallCard(toolName, input, risk) {
    const card = document.createElement("div");
    card.className = "agent-card agent-tool-call-card";
    const header = document.createElement("div");
    header.className = "agent-card-header";
    header.innerHTML = '<svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>工具调用';
    card.appendChild(header);
    const info = document.createElement("div");
    info.className = "tool-call-info";
    info.innerHTML =
      '<span class="tool-badge">' + escapeHtml(toolName || "?") + '</span>' +
      '<span class="tool-risk tool-risk-' + (risk || "read") + '">' + riskLabel(risk || "read") + '</span>';
    card.appendChild(info);
    if (input && Object.keys(input).length) {
      const paramsEl = document.createElement("div");
      paramsEl.className = "tool-params";
      try {
        paramsEl.textContent = JSON.stringify(input, null, 2);
      } catch (_) {
        paramsEl.textContent = String(input);
      }
      card.appendChild(paramsEl);
    }
    const resultSlot = document.createElement("div");
    resultSlot.className = "tool-result hidden";
    card.appendChild(resultSlot);
    return card;
  }

  function createApprovalCard(toolName, input, risk, reason, onApprove, onReject) {
    const card = document.createElement("div");
    card.className = "agent-card agent-approval-card";
    const header = document.createElement("div");
    header.className = "agent-card-header";
    header.innerHTML = '<svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>需要审批';
    card.appendChild(header);
    const reasonEl = document.createElement("div");
    reasonEl.className = "approval-reason";
    const riskBadge = '<span class="approval-risk-badge ' + (risk || "write") + '">' + riskLabel(risk || "write") + '</span>';
    reasonEl.innerHTML = escapeHtml(reason || "") + riskBadge;
    card.appendChild(reasonEl);

    const info = document.createElement("div");
    info.className = "tool-call-info";
    info.innerHTML = '<span class="tool-badge">' + escapeHtml(toolName || "?") + '</span>';
    card.appendChild(info);

    if (input && Object.keys(input).length) {
      const paramsEl = document.createElement("div");
      paramsEl.className = "tool-params";
      try { paramsEl.textContent = JSON.stringify(input, null, 2); } catch (_) { paramsEl.textContent = String(input); }
      card.appendChild(paramsEl);
    }

    const actions = document.createElement("div");
    actions.className = "approval-actions";
    const approveBtn = document.createElement("button");
    approveBtn.className = "approval-btn approve";
    approveBtn.type = "button";
    approveBtn.textContent = "批准执行";
    const rejectBtn = document.createElement("button");
    rejectBtn.className = "approval-btn reject";
    rejectBtn.type = "button";
    rejectBtn.textContent = "拒绝";
    approveBtn.addEventListener("click", () => { approveBtn.disabled = true; rejectBtn.disabled = true; onApprove(); });
    rejectBtn.addEventListener("click", () => { approveBtn.disabled = true; rejectBtn.disabled = true; onReject(); });
    actions.appendChild(approveBtn);
    actions.appendChild(rejectBtn);
    card.appendChild(actions);
    return card;
  }

  function createErrorCard(message) {
    const card = document.createElement("div");
    card.className = "agent-card agent-error-card";
    card.textContent = "⚠ " + (message || "未知错误");
    return card;
  }

  function createTokenBadge(prompt, completion, budget, threshold) {
    const badge = document.createElement("span");
    badge.className = "agent-token-badge";
    const b = budget || TOKEN_BUDGET;
    const t = threshold || TOKEN_COMPACTION_THRESHOLD;
    const lvl = tokenLevel(prompt, b);
    badge.classList.add("level-" + lvl);
    badge.textContent = "📊 " + formatTokens(prompt) + " / " + formatTokens(b);
    badge.title = "本轮 prompt " + formatTokens(prompt) + " tokens" +
      "；累计 completion " + formatTokens(completion) +
      "；阈值 " + formatTokens(t);
    return badge;
  }

  function createCompactionCard(beforeEntries, afterEntries, beforeTokens, afterTokens, threshold, budget) {
    const card = document.createElement("div");
    card.className = "agent-card agent-compaction-card";
    const header = document.createElement("div");
    header.className = "agent-card-header";
    header.innerHTML = '<svg class="agent-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>上下文压缩';
    card.appendChild(header);
    const body = document.createElement("div");
    body.className = "compaction-summary";
    body.innerHTML =
      '<span>上下文超限（约 ' + formatTokens(beforeTokens) + ' tokens）</span>' +
      '<span>早期 ' + beforeEntries + ' → ' + afterEntries + ' 条</span>' +
      '<span>压缩后约 ' + formatTokens(afterTokens) + ' tokens</span>';
    card.appendChild(body);
    return card;
  }

  // 找到 assistant 消息行里的 .agent-cards 容器，没有就创建
  function ensureAgentCards(row) {
    let cards = row._agentCards;
    if (cards) return cards;
    cards = document.createElement("div");
    cards.className = "agent-cards";
    row._agentCards = cards;
    // 插到 body（content）和 actions 之间
    row._body.parentNode.insertBefore(cards, row._actions);
    return cards;
  }

  function updateLastToolResult(cardsContainer, callId, ok, output, error) {
    const toolCards = cardsContainer.querySelectorAll(".agent-tool-call-card");
    // 结果卡片在 tool_result 里用 call_id 做标记；我们直接找最后一个没显示结果的 tool card
    // 简单实现：找最后一个 tool-card，填入结果
    for (let i = toolCards.length - 1; i >= 0; i--) {
      const c = toolCards[i];
      const slot = c.querySelector(".tool-result");
      if (slot && slot.classList.contains("hidden")) {
        slot.classList.remove("hidden");
        if (ok) {
          slot.textContent = output || "（执行成功）";
        } else {
          slot.classList.add("error");
          slot.textContent = "✗ " + (error || "执行失败");
        }
        // 标记这个 call_id 已经处理过
        c.dataset.callId = callId;
        return;
      }
      if (c.dataset.callId) return; // 已处理过就停下
    }
  }

  // ---------------- SSE 解析辅助 ----------------

  async function* parseSSE(reader) {
    const decoder = new TextDecoder();
    let buffer = "";
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
          try { yield JSON.parse(raw); } catch (_) { /* keepalive 等注释行 */ }
        }
      }
    }
  }

  // ---------------- Agent 模式运行（统一走 /api/agent/run） ----------------

  async function runAgent(text, options, mode, existingRow) {
    options = options || {};
    mode = mode || "agent";

    // 重置 token 追踪状态
    currentAgentTaskTokens = { prompt: 0, completion: 0, last_prompt: 0, last_completion: 0 };

    setStreaming(true);
    state.stickToBottom = true;
    showWelcome(false);

    let row = existingRow;
    if (!row) {
      addMessage("user", text);
      row = addMessage("assistant", "");
    }
    row._body.classList.add("streaming");
    row._actions.classList.add("hidden");
    const contentEl = row._body;
    const raw = row._raw;
    const actions = row._actions;

    // Agent 模式下先显示 thought
    const cardsContainer = ensureAgentCards(row);

    let finalText = "";
    let errorMessage = "";
    let errorCode = "";
    let reader = null;
    let runId = null;

    // 如果有之前待审批的 run_id，先把它清除
    if (options.resumeRunId) {
      runId = options.resumeRunId;
    }

    const payload = {
      message: text,
      session_id: state.sessionId,
      provider: state.modelProvider || undefined,
      model: state.model || undefined,
      mode: mode,
      history: options.history || undefined,
    };

    let endpoint = "/api/agent/run";
    if (options.resumeRunId) {
      endpoint = "/api/agent/approve";
    }

    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options.resumeRunId
          ? { run_id: options.resumeRunId, decision: options.decision, edits: options.edits || {}, mode: mode }
          : payload),
      });

      if (!resp.ok || !resp.body) {
        let message = "Agent 请求失败（HTTP " + resp.status + "）";
        let code = "";
        try {
          const data = await resp.json();
          if (data && data.error) message = data.error;
          if (data && data.code) code = data.code;
        } catch (_) {}
        errorCode = code;
        throw new Error(message);
      }

      reader = resp.body.getReader();

      for await (const event of parseSSE(reader)) {
        if (!event || !event.event) continue;

        if (event.event === "run_started") {
          runId = event.run_id;
          state.agentRunId = runId;
        } else if (event.event === "plan") {
          const card = createPlanCard(event.steps, event.raw);
          cardsContainer.appendChild(card);
          scrollToBottom();
        } else if (event.event === "plan_progress") {
          updatePlanDone(cardsContainer, event.done_count || 0);
        } else if (event.event === "thought") {
          // Agent 模式显示 thought 卡片；Chat 模式懒调用也显示（简化）
          const card = createThoughtCard(event.content);
          cardsContainer.appendChild(card);
          scrollToBottom();
        } else if (event.event === "tool_call") {
          const card = createToolCallCard(event.tool, event.input, event.risk);
          card.dataset.callId = event.call_id;
          cardsContainer.appendChild(card);
          scrollToBottom();
        } else if (event.event === "tool_result") {
          const card = cardsContainer.querySelector('.agent-tool-call-card[data-call-id="' + event.call_id + '"]') ||
            (() => {
              // 如果没找到对应 card，新建一个
              const c = createToolCallCard(event.tool, null, event.risk);
              c.dataset.callId = event.call_id;
              cardsContainer.appendChild(c);
              return c;
            })();
          const slot = card.querySelector(".tool-result");
          if (slot) {
            slot.classList.remove("hidden");
            if (event.ok) {
              slot.textContent = event.output || "（执行成功）";
            } else {
              slot.classList.add("error");
              slot.textContent = "✗ " + (event.error || "执行失败");
            }
          }
          scrollToBottom();
        } else if (event.event === "approval_required") {
          // 暂停等待用户审批
          const pendingRunId = runId;
          state.agentPendingRunId = pendingRunId;
          const card = createApprovalCard(
            event.tool, event.input, event.risk, event.reason,
            () => handleApproval(pendingRunId, "approve", mode, row, cardsContainer),
            () => handleApproval(pendingRunId, "reject", mode, row, cardsContainer)
          );
          card.dataset.callId = event.call_id;
          cardsContainer.appendChild(card);
          // 中止流：这里需要中断当前 SSE 等待
          if (reader) { try { await reader.cancel(); } catch (_) {} }
          reader = null;
          scrollToBottom();
          // 提前 return，等用户审批后 handleApproval 会重新调用 runAgent(resume)
          return;
        } else if (event.event === "final") {
          finalText = event.content || "";
          raw.text = finalText;
          contentEl.innerHTML = renderMarkdown(finalText);
          setSessionId(event.session_id || state.sessionId);
        } else if (event.event === "aborted") {
          const abortedCard = document.createElement("div");
          abortedCard.className = "agent-card agent-aborted-card";
          abortedCard.textContent = "⏹ " + (event.message || "任务已中止");
          cardsContainer.appendChild(abortedCard);
          scrollToBottom();
        } else if (event.event === "max_turns") {
          const mtCard = document.createElement("div");
          mtCard.className = "agent-card agent-max-turns-card";
          mtCard.textContent = "⟳ " + (event.message || "已达最大轮数");
          cardsContainer.appendChild(mtCard);
          scrollToBottom();
        } else if (event.event === "compaction") {
          // transcript 压缩事件：显示压缩提示卡片
          const compCard = createCompactionCard(
            event.before_entries, event.after_entries,
            event.before_tokens, event.after_tokens,
            event.threshold, event.budget
          );
          cardsContainer.appendChild(compCard);
          scrollToBottom();
        } else if (event.event === "token_usage") {
          // token 用量事件：累加并更新 token 徽章
          const pt = event.prompt_tokens || 0;
          const ct = event.completion_tokens || 0;
          currentAgentTaskTokens.last_prompt = pt;
          currentAgentTaskTokens.last_completion = ct;
          currentAgentTaskTokens.prompt = pt;
          currentAgentTaskTokens.completion = (currentAgentTaskTokens.completion || 0) + ct;
          // 在 Agent 卡片容器中找最后一个 agent-plan-card 或最后一个卡片，在其 header 右侧插入 token 徽章
          // 更简洁的做法：在第一张卡片的 header 里更新/追加徽章
          const firstCard = cardsContainer.querySelector(".agent-card");
          if (firstCard) {
            let badge = firstCard.querySelector(".agent-token-badge");
            if (!badge) {
              const header = firstCard.querySelector(".agent-card-header");
              if (header) {
                badge = createTokenBadge(pt, currentAgentTaskTokens.completion, event.budget, event.threshold);
                header.appendChild(badge);
              }
            } else {
              const lvl = tokenLevel(pt, event.budget || TOKEN_BUDGET);
              badge.className = "agent-token-badge level-" + lvl;
              badge.textContent = "📊 " + formatTokens(pt) + " / " + formatTokens(event.budget || TOKEN_BUDGET);
              badge.title = "本轮 prompt " + formatTokens(pt) + " tokens" +
                "；累计 completion " + formatTokens(currentAgentTaskTokens.completion) +
                "；阈值 " + formatTokens(event.threshold || TOKEN_COMPACTION_THRESHOLD);
            }
          }
        } else if (event.event === "error") {
          errorMessage = event.message || "Agent 运行错误";
          cardsContainer.appendChild(createErrorCard(errorMessage));
        }
      }
    } catch (err) {
      errorMessage = err.message || String(err);
      cardsContainer.appendChild(createErrorCard(errorMessage));
      if (reader) { try { await reader.cancel(); } catch (_) {} }
    }

    // 收尾
    contentEl.classList.remove("streaming");
    state.agentRunId = null;
    setStreaming(false);
    recalcSessionTokens();

    // Agent 模式 token 结算：记录每日用量
    try {
      recordDailyUsage({
        inputTokens: currentAgentTaskTokens.prompt || 0,
        outputTokens: currentAgentTaskTokens.completion || 0,
      });
      updateQuotaUI();
    } catch (_) { /* 静默失败 */ }

    scrollToBottom();
    await loadSessions();

    if (errorCode === "provider_unavailable") {
      await loadProviders();
      return;
    }
    if (errorCode === "workspace_required" || errorCode === "workspace_missing") {
      await loadWorkspace();
      openWorkspacePicker();
      return;
    }

    el.input.focus();
  }

  // ---------------- 审批处理 ----------------

  async function handleApproval(pendingRunId, decision, mode, row, cardsContainer) {
    // 找到审批卡片并禁用按钮
    const approvalCard = cardsContainer.querySelector(".agent-approval-card");
    if (approvalCard) {
      approvalCard.classList.add("hidden");
    }
    state.agentPendingRunId = null;
    await runAgent(null, {
      resumeRunId: pendingRunId,
      decision: decision,
    }, mode, row);
  }

  async function abortAgent() {
    if (!state.agentRunId && !state.agentPendingRunId) return;
    const runId = state.agentRunId || state.agentPendingRunId;
    try {
      await fetch("/api/agent/abort", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId }),
      });
    } catch (err) {
      console.warn("[Agent] abort 请求失败:", err);
    }
    state.agentRunId = null;
    state.agentPendingRunId = null;
    setStreaming(false);
  }

  // ---------------- 流式对话（Chat 模式） ----------------

  async function sendChat(text, options) {
    options = options || {};
    setStreaming(true);
    state.stickToBottom = true;
    showWelcome(false);

    addMessage("user", text);
    const row = addMessage("assistant", "");
    row._body.classList.add("streaming");
    row._actions.classList.add("hidden");
    const contentEl = row._body;
    const raw = row._raw;

    let accumulated = "";
    let errorMessage = "";

    const payload = {
      message: text,
      session_id: state.sessionId || undefined,
      provider: state.modelProvider || undefined,
      model: state.model || undefined,
      regenerate: !!options.regenerate,
    };

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok || !resp.body) {
        let message = "对话请求失败（HTTP " + resp.status + "）";
        let code = "";
        try {
          const data = await resp.json();
          if (data && data.error) message = data.error;
          if (data && data.code) code = data.code;
        } catch (_) {}
        if (code === "provider_unavailable") {
          errorMessage = message;
          await loadProviders();
        } else if (code === "workspace_required" || code === "workspace_missing") {
          errorMessage = message;
          await loadWorkspace();
          openWorkspacePicker();
        } else {
          errorMessage = message;
        }
        throw new Error(message);
      }

      const reader = resp.body.getReader();

      for await (const event of parseSSE(reader)) {
        if (!event || !event.event) continue;

        if (event.event === "chat_started") {
          // 后端创建/返回了 session_id，存下来
          if (event.session_id) setSessionId(event.session_id);
        } else if (event.event === "token") {
          accumulated += event.content || "";
          raw.text = accumulated;
          contentEl.innerHTML = renderMarkdown(accumulated);
          scrollToBottom();
        } else if (event.event === "final") {
          const finalText = event.content || accumulated;
          raw.text = finalText;
          contentEl.innerHTML = renderMarkdown(finalText);
          if (event.session_id) setSessionId(event.session_id);
        } else if (event.event === "error") {
          errorMessage = event.message || "未知错误";
          // 把错误也显示在气泡里（红色）
          contentEl.innerHTML = '<p class="error-text">' + escapeHtml(errorMessage) + '</p>';
          break;
        }
      }
    } catch (err) {
      if (!errorMessage) errorMessage = err.message || String(err);
      if (!accumulated) {
        contentEl.innerHTML = '<p class="error-text">' + escapeHtml(errorMessage) + '</p>';
      }
    }

    // 收尾
    row._body.classList.remove("streaming");
    row._actions.classList.remove("hidden");
    setStreaming(false);
    recalcSessionTokens();

    // Chat 模式 token 结算：从对话历史估算输入、从最终答复估算输出
    try {
      const inputTok = estimateTokens(text || "");
      const outputTok = estimateTokens(finalText || accumulated || "");
      recordDailyUsage({ inputTokens: inputTok, outputTokens: outputTok });
      updateQuotaUI();
    } catch (_) { /* 静默失败 */ }

    scrollToBottom();
    await loadSessions();
    el.input.focus();
  }

  // ---------------- 流式对话 ----------------

  async function sendMessage(text, options) {
    options = options || {};
    if (state.streaming) return;
    if (state.locked) {
      showSetup();
      return;
    }
    if (!workspaceReady()) {
      openWorkspacePicker();
      return;
    }

    // 本地每日 token 限制检查（前端硬闸，静默拦截）
    if (utIsLimitExceeded()) {
      updateQuotaUI();
      return;
    }

    updateQuotaUI();

    // 根据当前模式选择执行路径
    const mode = getCurrentMode();

    // 附件：气泡里只显示文件名，完整内容随请求发给后端
    const attachNames = state.attachments.map((att) => att.name);
    const payloadText = composeMessageWithAttachments(text);
    const displayText = attachNames.length
      ? "📎 " + attachNames.join("、") + (text ? "\n\n" + text : "")
      : text;
    clearAttachments();

    if (mode === "agent") {
      // Agent 模式：完整 ReAct 循环 + 审批流
      await runAgent(displayText, { regenerate: !!options.regenerate }, "agent");
    } else {
      // Chat 模式：简单流式对话（真正的 token-by-token 流式 + 自动 session 保存）
      await sendChat(payloadText, options);
    }
  }

  // ---------------- 工作目录（workspace） ----------------

  const WS_FOLDER_ICON =
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
  const WS_FILE_ICON =
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';

  function applyWorkspace(ws) {
    state.workspace = ws || null;
    const configured = !!(ws && ws.configured);
    el.workspaceChip?.classList.toggle("is-set", configured);
    if (el.workspaceChipName) {
      el.workspaceChipName.textContent = configured ? (ws.name || ws.path) : "选择工作目录";
    }
    if (el.workspaceChip) {
      el.workspaceChip.title = configured ? "工作目录：" + ws.path : "选择工作目录";
    }
    applyInteractionGate();
  }

  async function loadWorkspace() {
    try {
      const data = await api("/api/workspace");
      applyWorkspace(data.workspace || null);
    } catch (err) {
      console.warn("[SimChat] 工作目录状态加载失败:", err);
      applyWorkspace(null);
    }
  }

  function _setWorkspaceMessage(text, kind) {
    if (!el.workspaceMessage) return;
    el.workspaceMessage.textContent = text || "";
    el.workspaceMessage.className = "workspace-message" + (kind ? " " + kind : "");
  }

  function openWorkspacePicker() {
    if (!el.workspaceModal) return;
    el.workspaceModal.classList.add("is-open");
    el.workspaceModal.setAttribute("aria-hidden", "false");
    _setWorkspaceMessage("");
    const start = state.workspace?.configured ? state.workspace.path : "";
    browseWorkspace(start);
  }

  function closeWorkspacePicker() {
    if (!el.workspaceModal) return;
    el.workspaceModal.classList.remove("is-open");
    el.workspaceModal.setAttribute("aria-hidden", "true");
  }

  async function browseWorkspace(path) {
    el.workspaceConfirm.disabled = true;
    _setWorkspaceMessage("加载目录…");
    try {
      const query = path ? "?path=" + encodeURIComponent(path) : "";
      const data = await api("/api/workspace/browse" + query);
      renderWorkspaceBrowse(data);
      _setWorkspaceMessage("");
    } catch (err) {
      _setWorkspaceMessage(err.message || "目录读取失败", "error");
    }
  }

  function renderWorkspaceBrowse(data) {
    state.workspaceBrowse = data;
    const current = data.path || "";
    if (el.workspaceCurrentPath) el.workspaceCurrentPath.textContent = current || "请选择磁盘 / 根目录";
    if (el.workspaceManualPath) el.workspaceManualPath.value = current;
    if (el.workspaceUp) el.workspaceUp.disabled = !data.parent;
    if (el.workspaceConfirm) el.workspaceConfirm.disabled = !current;

    el.workspaceRoots.innerHTML = "";
    (data.roots || []).forEach((root) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "workspace-root-chip";
      chip.textContent = root;
      chip.title = "浏览 " + root;
      chip.addEventListener("click", () => browseWorkspace(root));
      el.workspaceRoots.appendChild(chip);
    });

    el.workspaceList.innerHTML = "";
    const entries = data.entries || [];
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "workspace-list-empty";
      empty.textContent = current ? "此目录为空" : "点击上方磁盘 / 根目录开始浏览";
      el.workspaceList.appendChild(empty);
      return;
    }

    entries.forEach((entry) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "workspace-entry " + (entry.is_dir ? "is-dir" : "is-file");
      row.title = entry.path;

      const icon = document.createElement("span");
      icon.className = "workspace-entry-icon";
      icon.innerHTML = entry.is_dir ? WS_FOLDER_ICON : WS_FILE_ICON;

      const name = document.createElement("span");
      name.className = "workspace-entry-name";
      name.textContent = entry.name;

      row.appendChild(icon);
      row.appendChild(name);
      if (entry.is_dir) {
        row.addEventListener("click", () => browseWorkspace(entry.path));
      }
      el.workspaceList.appendChild(row);
    });

    if (data.truncated) {
      _setWorkspaceMessage("目录条目过多，仅显示前 500 项", "");
    }
  }

  async function confirmWorkspace() {
    const path = state.workspaceBrowse?.path || "";
    if (!path) return;
    el.workspaceConfirm.disabled = true;
    _setWorkspaceMessage("保存中…");
    try {
      const data = await api("/api/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: path }),
      });
      applyWorkspace(data.workspace || null);
      closeWorkspacePicker();
      if (!state.locked) {
        enterMode("chat");
        el.input.focus();
      }
    } catch (err) {
      _setWorkspaceMessage(err.message || "保存失败", "error");
    } finally {
      el.workspaceConfirm.disabled = !(state.workspaceBrowse && state.workspaceBrowse.path);
    }
  }

  async function clearWorkspace() {
    if (!state.workspace?.configured) {
      closeWorkspacePicker();
      return;
    }
    if (!window.confirm("确定清除工作目录吗？清除后将无法发起对话。")) return;
    try {
      const data = await api("/api/workspace", { method: "DELETE" });
      applyWorkspace(data.workspace || null);
      closeWorkspacePicker();
    } catch (err) {
      _setWorkspaceMessage(err.message || "清除失败", "error");
    }
  }

  function workspaceGoUp() {
    const parent = state.workspaceBrowse?.parent;
    if (parent) browseWorkspace(parent);
  }

  function openManualWorkspacePath() {
    const value = (el.workspaceManualPath?.value || "").trim();
    if (!value) {
      _setWorkspaceMessage("请输入目录绝对路径", "error");
      return;
    }
    browseWorkspace(value);
  }

  // ---------------- IDE 界面跳转 ----------------

  function openIde() {
    // IDE 界面由后端 /ide 路由提供（单文件演示页）
    window.location.href = "/ide";
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
    const form = {
      max_history: parseInt(el.setMaxHistory?.value, 10) || 40,
      temperature: parseFloat(el.setTemperature?.value) || 0.7,
      max_tokens: parseInt(el.setMaxTokens?.value, 10) || 4096,
      system_prompt: (el.setSystemPrompt?.value || "").trim(),
      send_with_enter: el.setSendWithEnter?.classList.contains("on") ?? true,
      show_token_bar: el.setShowTokenBar?.classList.contains("on") ?? true,
      theme: document.querySelector("#set-theme .theme-card.active")?.dataset.theme || "system",
      font_scale: parseFloat(el.setFontScale?.value) || 1.0,
    };
    return form;
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

  // ---------------- 用户个人中心 ----------------

  function profileInitials(name) {
    const text = String(name || "").trim();
    if (!text) return "U";
    // Array.from 按码点切分，兼容中文与 emoji
    return Array.from(text)[0].toUpperCase();
  }

  // 把头像渲染到指定圆形容器：有图显示图片，无图显示用户名首字母
  function applyAvatar(target, avatar, name) {
    if (!target) return;
    if (avatar) {
      target.innerHTML = '<img src="' + escapeHtml(avatar) + '" alt="用户头像">';
    } else {
      target.textContent = profileInitials(name);
    }
  }

  function renderUserBadge() {
    const p = state.profile || {};
    const name = (p.username || "").trim() || "本地用户";
    if (el.userName) el.userName.textContent = name;
    applyAvatar(el.userAvatar, p.avatar, name);
  }

  function renderProfileForm() {
    const p = state.profile || {};
    state.profileAvatar = p.avatar || "";
    if (el.profileUsername) el.profileUsername.value = p.username || "";
    if (el.profileBirthday) el.profileBirthday.value = p.birthday || "";
    if (el.profileEmergency) el.profileEmergency.value = p.emergency_contact || "";
    applyAvatar(el.profileAvatarPreview, state.profileAvatar, p.username);

    if (el.profileMeta) {
      const parts = [];
      if (p.created_at) parts.push("创建于 " + String(p.created_at).replace("T", " ").slice(0, 16));
      if (p.updated_at) parts.push("最近更新 " + String(p.updated_at).replace("T", " ").slice(0, 16));
      el.profileMeta.textContent = parts.join(" · ");
    }
    setProfileMsg("");
  }

  function setProfileMsg(text, kind) {
    if (!el.profileMsg) return;
    el.profileMsg.textContent = text || "";
    el.profileMsg.className = "comm-form-msg" + (kind ? " " + kind : "");
  }

  async function loadProfile() {
    try {
      const data = await api("/api/profile");
      state.profile = data.profile || {};
      renderUserBadge();
      renderProfileForm();
    } catch (err) {
      console.warn("[SimChat] 用户档案加载失败:", err);
    }
  }

  // 本地图片 → 256px 正方形内等比缩放 → data URL
  function readAvatarFile(file) {
    return new Promise((resolve, reject) => {
      if (!file) return reject(new Error("未选择图片"));
      if (!/^image\/(png|jpeg|webp|gif)$/i.test(file.type)) {
        return reject(new Error("只支持 PNG / JPEG / WEBP / GIF 图片"));
      }
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error("图片解析失败"));
        img.onload = () => {
          const size = 256;
          const scale = Math.min(1, size / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d");
          if (!ctx) return reject(new Error("浏览器不支持图片处理"));
          ctx.drawImage(img, 0, 0, w, h);
          // PNG 保留透明通道，其余统一转 JPEG 控制体积
          const isPng = file.type === "image/png";
          resolve(canvas.toDataURL(isPng ? "image/png" : "image/jpeg", 0.85));
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  async function pickProfileAvatar() {
    const file = el.profileAvatarInput?.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await readAvatarFile(file);
      state.profileAvatar = dataUrl;
      applyAvatar(el.profileAvatarPreview, dataUrl, el.profileUsername?.value || "");
      setProfileMsg("头像已选择，点击「保存」后生效", "ok");
    } catch (err) {
      setProfileMsg(err.message, "error");
    }
    el.profileAvatarInput.value = "";
  }

  function clearProfileAvatar() {
    state.profileAvatar = "";
    applyAvatar(el.profileAvatarPreview, "", el.profileUsername?.value || "");
    setProfileMsg("头像已移除，点击「保存」后生效", "");
  }

  async function saveProfile() {
    const username = (el.profileUsername?.value || "").trim();
    if (!username) {
      setProfileMsg("用户名不能为空", "error");
      el.profileUsername?.focus();
      return;
    }
    if (el.profileSave) el.profileSave.disabled = true;
    setProfileMsg("保存中…");
    try {
      const data = await api("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          birthday: (el.profileBirthday?.value || "").trim(),
          emergency_contact: (el.profileEmergency?.value || "").trim(),
          avatar: state.profileAvatar || "",
        }),
      });
      state.profile = data.profile || {};
      renderUserBadge();
      renderProfileForm();
      setProfileMsg("已保存", "ok");
    } catch (err) {
      setProfileMsg(err.message, "error");
    } finally {
      if (el.profileSave) el.profileSave.disabled = false;
    }
  }

  // ---------------- 控制台 ----------------

  const ADVANCED_KEY = "simchat.advanced";
  const SECTION_KEY = "simchat.section";

  // -------- Usage Section 状态 --------
  let _usageCache = null;
  let _usageQuotaBindings = false;

  async function renderUsageSection() {
    // 绑定一次表单事件（idempotent）
    bindQuotaForm();

    let data;
    try {
      const resp = await fetch("/api/console/usage", { cache: "no-store" });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error || "加载失败");
      data = json;
    } catch (err) {
      // 后端不可用时退化到纯前端本地数据
      data = {
        success: true,
        quota: { enabled: false, limit: 0, period: "day", lock: false },
        today: { input_tokens: 0, output_tokens: 0, total_tokens: 0, exchanges: 0 },
        recent: buildFallbackRecent(),
      };
    }
    _usageCache = data;

    // ---- 统计卡片 ----
    document.getElementById("usage-today-total").textContent = formatTokens(data.today.total_tokens);
    const detailParts = [];
    if (data.today.input_tokens) detailParts.push("in " + formatTokens(data.today.input_tokens));
    if (data.today.output_tokens) detailParts.push("out " + formatTokens(data.today.output_tokens));
    document.getElementById("usage-today-detail").textContent = detailParts.length ? detailParts.join(" · ") : "—";
    document.getElementById("usage-today-input").textContent = formatTokens(data.today.input_tokens);
    document.getElementById("usage-today-output").textContent = formatTokens(data.today.output_tokens);
    document.getElementById("usage-today-exchanges").textContent = formatTokens(data.today.exchanges);

    // ---- 近 7 天条形图 ----
    const chart = document.getElementById("usage-chart");
    if (chart) {
      chart.innerHTML = "";
      const maxTok = Math.max(1, ...data.recent.map(d => d.total_tokens || 0));
      const todayStr = new Date().toISOString().slice(0, 10);
      data.recent.forEach(day => {
        const height = Math.max(3, (day.total_tokens / maxTok) * 110);
        const dayEl = document.createElement("div");
        dayEl.className = "usage-chart-day";
        const bar = document.createElement("div");
        bar.className = "usage-chart-bar";
        if (day.date === todayStr) bar.classList.add("is-today");
        bar.style.height = height + "px";
        bar.setAttribute("data-tokens", formatTokens(day.total_tokens));
        dayEl.appendChild(bar);
        const label = document.createElement("div");
        label.className = "usage-chart-label";
        label.textContent = day.date.slice(5).replace("-", "/"); // MM/DD
        dayEl.appendChild(label);
        chart.appendChild(dayEl);
      });
    }

    // ---- 额度配置表单 ----
    const quota = data.quota || {};
    const toggle = document.getElementById("quota-enabled-toggle");
    const limitInput = document.getElementById("quota-limit-input");
    const periodSelect = document.getElementById("quota-period-select");
    const lockToggle = document.getElementById("quota-lock-toggle");
    const lockHint = document.getElementById("quota-lock-hint");

    if (toggle) toggle.checked = !!quota.enabled;
    if (limitInput) limitInput.value = quota.limit || 0;
    if (periodSelect) periodSelect.value = quota.period || "day";
    if (lockToggle) lockToggle.checked = !!quota.lock;

    // 锁定时禁用 limit/period/enabled 编辑
    const blocked = !!quota.lock;
    [limitInput, periodSelect].forEach(el => { if (el) el.disabled = blocked; });
    if (toggle) toggle.disabled = blocked;
    if (lockHint) lockHint.classList.toggle("hidden", !blocked);
  }

  function buildFallbackRecent() {
    // 后端不可用时，从 localStorage 拼装最近 7 天
    const all = utReadAll();
    const today = new Date();
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const rec = all[key] || {};
      const inp = rec.input_tokens || 0;
      const out = rec.output_tokens || 0;
      result.push({
        date: key,
        input_tokens: inp,
        output_tokens: out,
        total_tokens: inp + out,
        exchanges: rec.exchanges || 0,
      });
    }
    return result;
  }

  function bindQuotaForm() {
    if (_usageQuotaBindings) return;
    _usageQuotaBindings = true;

    const toggle = document.getElementById("quota-enabled-toggle");
    const limitInput = document.getElementById("quota-limit-input");
    const periodSelect = document.getElementById("quota-period-select");
    const lockToggle = document.getElementById("quota-lock-toggle");
    const saveBtn = document.getElementById("quota-save-btn");
    const resetBtn = document.getElementById("quota-reset-btn");
    const feedback = document.getElementById("quota-save-feedback");

    if (saveBtn) saveBtn.addEventListener("click", async () => {
      const limitVal = limitInput ? parseInt(limitInput.value, 10) || 0 : 0;
      const enabled = toggle ? toggle.checked : false;
      const period = periodSelect ? periodSelect.value : "day";
      const lock = lockToggle ? lockToggle.checked : false;

      // enabled=false 时 limit 自动设为 0（关闭限制）
      const effectiveLimit = enabled ? Math.max(0, limitVal) : 0;

      // 同时写 localStorage（前端硬闸）和后端 settings.json（后端硬闸）
      const cfg = utReadLimitConfig();
      cfg.enabled = enabled;
      cfg.limit = effectiveLimit;
      cfg.locked = lock;
      utWriteLimitConfig(cfg);
      updateQuotaUI();

      // 后端保存（lock 状态下可能返回 403）
      if (_usageCache && _usageCache.quota && _usageCache.quota.lock && !lock) {
        // 从锁定变为解锁：先更新本地缓存，再提交
        _usageCache.quota.lock = false;
      }
      try {
        const resp = await fetch("/api/console/usage/quota", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: effectiveLimit, period, lock }),
        });
        const json = await resp.json();
        if (!json.success) throw new Error(json.error || "保存失败");
        if (feedback) {
          feedback.textContent = "✓ 已保存";
          feedback.classList.remove("is-error");
          setTimeout(() => { if (feedback) feedback.textContent = ""; }, 2000);
        }
      } catch (err) {
        // 后端 API 不存在时（旧版 simchat）静默降级——前端 localStorage 已是硬闸
        if (feedback) {
          feedback.textContent = "已保存到本地（后端未连通）";
          feedback.classList.remove("is-error");
          setTimeout(() => { if (feedback) feedback.textContent = ""; }, 2000);
        }
      }
      // 立即刷新显示
      renderUsageSection();
      updateQuotaUI();
    });

    if (resetBtn) resetBtn.addEventListener("click", async () => {
      if (!confirm("确定要重置今日 token 用量记录吗？")) return;
      try {
        await fetch("/api/console/usage/reset-today", { method: "POST" });
      } catch (_) {}
      // 本地 localStorage 也清理今天
      const all = utReadAll();
      const todayKey = utTodayKey();
      delete all[todayKey];
      utWriteAll(all);
      renderUsageSection();
      updateQuotaUI();
    });
  }

  function switchSection(name) {
    state.activeSection = name;
    try { localStorage.setItem(SECTION_KEY, name); } catch (_) {}

    el.navItems?.forEach((nav) => {
      nav.classList.toggle("is-active", nav.dataset.section === name);
    });
    el.sections?.forEach((sec) => {
      sec.hidden = sec.dataset.section !== name;
    });

    // 惰性加载：只在第一次切到某个分区时拉数据
    if (name === "profile") {
      renderProfileForm();
    } else if (name === "usage") {
      renderUsageSection();
    } else if (name === "comms" && !state.comms) {
      loadComms();
    } else if (name === "comms") {
      renderComms();
    } else if (name === "instances") {
      loadInstances();
      startInstancesPolling();
    } else {
      stopInstancesPolling();
    }

    if (name === "sessions") {
      loadConsoleSessions();
    }

    if (name === "lifecycle") {
      loadLifecycle();
      startLifecyclePolling();
    } else {
      stopLifecyclePolling();
    }

    updateCommRuntimePolling();
  }

  // ---------------- 启动与守护 ----------------

  function lifecycleMsg(text, kind) {
    if (!el.lifecycleMsg) return;
    el.lifecycleMsg.textContent = text || "";
    el.lifecycleMsg.className = "lifecycle-msg" + (kind ? " " + kind : "");
  }

  function _lcSetBadge(node, text, kind) {
    if (!node) return;
    node.textContent = text;
    node.className = "lifecycle-badge" + (kind ? " " + kind : "");
  }

  function _lcSetStat(node, text, kind) {
    if (!node) return;
    node.textContent = text;
    node.className = "lifecycle-stat-value" + (kind ? " " + kind : "");
  }

  function formatLifecycleStamp(value) {
    if (!value) return "—";
    return String(value).replace("T", " ");
  }

  function renderLifecycle(data) {
    if (!data) return;
    state.lifecycle = data;
    const auto = data.autostart || {};
    const wd = data.watchdog || {};
    const server = data.server || {};

    if (el.lifecycleAutostartTrack) {
      el.lifecycleAutostartTrack.classList.toggle("on", !!auto.enabled);
      el.lifecycleAutostartTrack.setAttribute("aria-checked", auto.enabled ? "true" : "false");
    }
    _lcSetBadge(
      el.lifecycleAutostartBadge,
      auto.enabled ? "已安装" : "未安装",
      auto.enabled ? "on" : ""
    );
    if (el.lifecycleAutostartMeta) {
      if (!auto.supported) {
        el.lifecycleAutostartMeta.textContent = auto.method_label || "当前系统不支持";
      } else {
        el.lifecycleAutostartMeta.textContent =
          (auto.method_label || "") + (auto.location ? "\n" + auto.location : "");
      }
    }

    if (el.lifecycleWatchdogTrack) {
      el.lifecycleWatchdogTrack.classList.toggle("on", !!wd.enabled);
      el.lifecycleWatchdogTrack.setAttribute("aria-checked", wd.enabled ? "true" : "false");
    }
    const paused = !!wd.paused;
    _lcSetBadge(
      el.lifecycleWatchdogBadge,
      paused ? "熔断中" : wd.enabled ? "已启用" : "未启用",
      paused ? "warn" : wd.enabled ? "on" : ""
    );
    _lcSetStat(el.lifecycleWdRunning, wd.running ? "运行中" : "未运行", wd.running ? "ok" : "");
    _lcSetStat(el.lifecycleWdPid, wd.guardian_pid ? String(wd.guardian_pid) : "—");
    _lcSetStat(el.lifecycleWdRestarts, (wd.restarts || 0) + " 次");
    _lcSetStat(el.lifecycleWdLast, formatLifecycleStamp(wd.last_restart_at));
    _lcSetStat(
      el.lifecycleServer,
      server.running ? (server.url || "运行中") : "未运行",
      server.running ? "ok" : ""
    );
    _lcSetStat(
      el.lifecycleWdPaused,
      paused ? (wd.paused_reason || "已熔断") : "正常",
      paused ? "warn" : "ok"
    );
    if (el.lifecycleStopWatchdog) el.lifecycleStopWatchdog.disabled = !wd.running;
  }

  async function loadLifecycle() {
    try {
      const data = await api("/api/lifecycle");
      renderLifecycle(data);
    } catch (err) {
      lifecycleMsg("状态读取失败：" + err.message, "error");
    }
  }

  function startLifecyclePolling() {
    stopLifecyclePolling();
    state.lifecycleTimer = setInterval(() => {
      if (state.activeSection === "lifecycle") loadLifecycle();
    }, 6000);
  }

  function stopLifecyclePolling() {
    if (state.lifecycleTimer) {
      clearInterval(state.lifecycleTimer);
      state.lifecycleTimer = null;
    }
  }

  async function toggleAutostart() {
    if (state.lifecycleBusy) return;
    if (!state.lifecycle) {
      await loadLifecycle();
      return;
    }
    const current = !!state.lifecycle.autostart?.enabled;
    if (!current && !window.confirm("将在当前用户登录时自动启动 SimChat。是否继续？")) {
      await loadLifecycle();
      return;
    }
    state.lifecycleBusy = true;
    lifecycleMsg(current ? "正在移除自启动项…" : "正在安装自启动项…");
    try {
      const data = await api("/api/lifecycle/autostart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !current }),
      });
      renderLifecycle(data);
      lifecycleMsg(
        !current ? (data.detail || "已安装开机自启") : "已移除开机自启",
        "ok"
      );
    } catch (err) {
      lifecycleMsg(err.message || "设置失败", "error");
      await loadLifecycle();
    } finally {
      state.lifecycleBusy = false;
    }
  }

  function openLifecycleConfirm() {
    if (!el.lifecycleConfirm) return;
    if (el.lifecycleConfirmCheck) el.lifecycleConfirmCheck.checked = false;
    if (el.lifecycleConfirmInput) el.lifecycleConfirmInput.value = "";
    updateLifecycleConfirmState();
    el.lifecycleConfirm.classList.add("is-open");
    el.lifecycleConfirm.setAttribute("aria-hidden", "false");
    el.lifecycleConfirmInput?.focus();
  }

  function closeLifecycleConfirm() {
    if (!el.lifecycleConfirm) return;
    el.lifecycleConfirm.classList.remove("is-open");
    el.lifecycleConfirm.setAttribute("aria-hidden", "true");
  }

  function updateLifecycleConfirmState() {
    const phrase = state.lifecycle?.confirmation_phrase || "启用自动拉起";
    const checked = !!el.lifecycleConfirmCheck?.checked;
    const typed = (el.lifecycleConfirmInput?.value || "").trim();
    if (el.lifecycleConfirmEnable) {
      el.lifecycleConfirmEnable.disabled = !(checked && typed === phrase);
    }
  }

  async function enableWatchdog() {
    const phrase = state.lifecycle?.confirmation_phrase || "启用自动拉起";
    if (!el.lifecycleConfirmCheck?.checked) return;
    if ((el.lifecycleConfirmInput?.value || "").trim() !== phrase) return;
    if (state.lifecycleBusy) return;
    state.lifecycleBusy = true;
    lifecycleMsg("正在启动守护进程…");
    try {
      const data = await api("/api/lifecycle/watchdog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: true, confirm: phrase }),
      });
      renderLifecycle(data);
      closeLifecycleConfirm();
      lifecycleMsg("自动拉起已启用", "ok");
    } catch (err) {
      lifecycleMsg(err.message || "启用失败", "error");
    } finally {
      state.lifecycleBusy = false;
    }
  }

  async function disableWatchdog() {
    if (state.lifecycleBusy) return;
    if (!window.confirm("停止自动拉起？守护进程会退出，当前 Web 服务继续运行。")) {
      await loadLifecycle();
      return;
    }
    state.lifecycleBusy = true;
    lifecycleMsg("正在停止守护进程…");
    try {
      const data = await api("/api/lifecycle/watchdog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: false }),
      });
      renderLifecycle(data);
      lifecycleMsg("自动拉起已停止", "ok");
    } catch (err) {
      lifecycleMsg(err.message || "停止失败", "error");
      await loadLifecycle();
    } finally {
      state.lifecycleBusy = false;
    }
  }

  async function stopWatchdogOnly() {
    if (state.lifecycleBusy) return;
    if (!window.confirm("停止守护进程？当前 Web 服务会继续运行，但不会再被自动拉起。")) return;
    state.lifecycleBusy = true;
    lifecycleMsg("正在停止守护进程…");
    try {
      await api("/api/lifecycle/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "watchdog" }),
      });
      await loadLifecycle();
      lifecycleMsg("守护已停止，Web 服务继续运行", "ok");
    } catch (err) {
      lifecycleMsg(err.message || "停止失败", "error");
    } finally {
      state.lifecycleBusy = false;
    }
  }

  async function stopService() {
    if (state.lifecycleBusy) return;
    const ok = window.confirm(
      "立即停止 SimChat 服务？\n\n" +
      "本次停止会同时解除自动拉起，守护进程不会复活它；开机自启设置保持不变。"
    );
    if (!ok) return;
    state.lifecycleBusy = true;
    stopLifecyclePolling();
    lifecycleMsg("正在停止服务…");
    try {
      const data = await api("/api/lifecycle/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "service" }),
      });
      if (el.lifecycleStopService) el.lifecycleStopService.disabled = true;
      lifecycleMsg(data.message || "服务已停止，可关闭此页面", "ok");
    } catch (err) {
      lifecycleMsg(err.message || "停止失败", "error");
      state.lifecycleBusy = false;
    }
  }

  // ---------------- 会话管理（控制台） ----------------

  const _SESS_OVERRIDE_OPTIONS = {
    thinking: [
      { value: "inherit", label: "继承（全局）" },
      { value: "low",     label: "low" },
      { value: "medium",  label: "medium" },
      { value: "high",    label: "high" },
    ],
    verbose: [
      { value: "inherit", label: "继承（全局）" },
      { value: "low",     label: "low" },
      { value: "medium",  label: "medium" },
      { value: "high",    label: "high" },
    ],
    reasoning: [
      { value: "inherit", label: "继承（全局）" },
      { value: "off",     label: "off" },
      { value: "low",     label: "low" },
      { value: "medium",  label: "medium" },
      { value: "high",    label: "high" },
    ],
  };

  /** 相对时间格式化：返回 "just now" / "5 min ago" / "2h ago" / "昨天" 等 */
  function _formatRelativeTime(timestamp) {
    if (!timestamp) return "—";
    const diff = (Date.now() / 1000) - timestamp;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + " min ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + "d ago";
    // 超过一周显示日期
    const d = new Date(timestamp * 1000);
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${mm}-${dd}`;
  }

  /** 获取当前筛选参数 */
  function _getSessionFilters() {
    const withinRaw = (el.sesActiveWithin?.value || "").trim();
    const limitRaw = (el.sesLimit?.value || "").trim();
    return {
      withinMinutes: withinRaw ? Math.max(1, parseInt(withinRaw, 10)) : null,
      limit: limitRaw ? Math.max(1, parseInt(limitRaw, 10)) : null,
    };
  }

  /** 根据筛选参数过滤会话列表（返回新数组） */
  function _applySessionFilters(sessions) {
    const { withinMinutes, limit } = _getSessionFilters();
    let list = sessions.slice();

    if (withinMinutes) {
      const cutoff = (Date.now() / 1000) - withinMinutes * 60;
      list = list.filter((s) => (s.updated_at || 0) >= cutoff);
    }

    if (limit) {
      list = list.slice(0, limit);
    }

    return list;
  }

  /** 渲染控制台会话表格（纯 DOM 操作，不发请求） */
  function renderSessionsConsole(sessions) {
    if (!el.sesTbody) return;

    const filtered = _applySessionFilters(sessions || []);

    // 空态
    if (!filtered.length) {
      el.sesTable.style.display = "none";
      if (el.sesEmpty) el.sesEmpty.hidden = false;
      if (el.sesLoading) el.sesLoading.hidden = true;
      if (el.sesFooterInfo) {
        const total = sessions?.length || 0;
        const { withinMinutes, limit } = _getSessionFilters();
        el.sesFooterInfo.textContent =
          total === 0
            ? "本地暂无会话"
            : `共 ${total} 条，筛选后 0 条${withinMinutes ? "（活跃 ≤ " + withinMinutes + " min）" : ""}${limit ? "（limit " + limit + "）" : ""}`;
      }
      return;
    }

    el.sesTable.style.display = "";
    if (el.sesEmpty) el.sesEmpty.hidden = true;
    if (el.sesLoading) el.sesLoading.hidden = true;

    // 构建下拉框选项 HTML（复用给每行）
    const buildOptions = (options, current) =>
      options.map((o) =>
        `<option value="${o.value}" ${o.value === current ? "selected" : ""}>${o.label}</option>`
      ).join("");

    const rowsHtml = filtered.map((s) => {
      const overrides = s.overrides || {};
      const key = s.id || "—";
      const title = (s.title || "").trim();
      const label = title && title !== "新对话" ? title : key;
      const labelClass = title && title !== "新对话" ? "sess-label" : "sess-label is-fallback";
      const modeClass = s.mode === "agent" ? "sess-kind agent" : "sess-kind chat";
      const modeLabel = s.mode === "agent" ? "agent" : "direct";
      const updated = _formatRelativeTime(s.updated_at);
      const tokens = typeof s.tokens_estimated === "number"
        ? s.tokens_estimated.toLocaleString()
        : "—";
      const thinkingVal = overrides.thinking || "inherit";
      const verboseVal = overrides.verbose || "inherit";
      const reasoningVal = overrides.reasoning || "inherit";

      const rowId = `ses-row-${key}`;
      return `
        <tr data-sid="${key}" id="${rowId}">
          <td class="col-key"><span class="sess-key" title="点击复制会话 ID">${key}</span></td>
          <td class="col-label"><span class="${labelClass}" title="${label}">${label}</span></td>
          <td class="col-kind"><span class="${modeClass}">${modeLabel}</span></td>
          <td class="col-updated">${updated}</td>
          <td class="col-tokens">${tokens}</td>
          <td class="col-thinking">
            <select class="sess-override" data-override="thinking">
              ${buildOptions(_SESS_OVERRIDE_OPTIONS.thinking, thinkingVal)}
            </select>
          </td>
          <td class="col-verbose">
            <select class="sess-override" data-override="verbose">
              ${buildOptions(_SESS_OVERRIDE_OPTIONS.verbose, verboseVal)}
            </select>
          </td>
          <td class="col-reasoning">
            <select class="sess-override" data-override="reasoning">
              ${buildOptions(_SESS_OVERRIDE_OPTIONS.reasoning, reasoningVal)}
            </select>
          </td>
          <td class="col-actions">
            <div class="sess-actions">
              <button class="sess-action-btn" data-act="refresh" title="刷新本行">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                刷新
              </button>
              <button class="sess-action-btn danger" data-act="delete" title="删除此会话">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>
                删除
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    el.sesTbody.innerHTML = rowsHtml;

    // 绑定行内事件：下拉框 change、按钮点击
    el.sesTbody.querySelectorAll("tr").forEach((row) => {
      const sid = row.dataset.sid;
      if (!sid) return;

      // 下拉框 → 批量保存 overrides
      row.querySelectorAll(".sess-override").forEach((select) => {
        select.addEventListener("change", () => {
          _saveSessionOverrides(sid, row).catch((err) => {
            console.error("保存 overrides 失败:", err);
          });
        });
      });

      // Key 点击 → 复制
      const keyEl = row.querySelector(".sess-key");
      if (keyEl) {
        keyEl.addEventListener("click", () => {
          navigator.clipboard?.writeText(sid).then(
            () => { keyEl.style.color = "var(--accent)"; setTimeout(() => { keyEl.style.color = ""; }, 800); },
            () => {}
          );
        });
      }

      // Actions 按钮
      row.querySelectorAll(".sess-action-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const act = btn.dataset.act;
          if (act === "delete") _deleteSession(sid);
          else if (act === "refresh") {
            loadConsoleSessions();
          }
        });
      });
    });

    // 底部统计
    if (el.sesFooterInfo) {
      const total = sessions.length;
      const shown = filtered.length;
      const { withinMinutes, limit } = _getSessionFilters();
      const parts = [`共 ${total} 条`];
      if (shown !== total) parts.push(`当前显示 ${shown} 条`);
      if (withinMinutes) parts.push(`活跃 ≤ ${withinMinutes} min`);
      if (limit) parts.push(`limit ${limit}`);
      el.sesFooterInfo.textContent = parts.join(" · ");
    }
  }

  /** 从行 DOM 提取当前 overrides 并 PATCH 到后端 */
  async function _saveSessionOverrides(sid, row) {
    if (!row) return;
    const overrides = {};
    row.querySelectorAll(".sess-override").forEach((select) => {
      const key = select.dataset.override;
      if (key) overrides[key] = select.value;
    });

    try {
      const resp = await api("/api/sessions/" + encodeURIComponent(sid), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overrides }),
      });

      // 更新本地缓存
      if (state.sessions) {
        const cached = state.sessions.find((s) => s.id === sid);
        if (cached) cached.overrides = resp.overrides || {};
      }
    } catch (err) {
      alert("保存失败: " + (err.message || err));
      // 回滚：重新拉一次覆盖值
      await loadConsoleSessions();
    }
  }

  /** 删除会话（带确认） */
  async function _deleteSession(sid) {
    if (!window.confirm(`确认删除会话 ${sid}？此操作不可恢复。`)) return;
    try {
      await api("/api/sessions/" + encodeURIComponent(sid), { method: "DELETE" });
      // 从本地缓存移除
      if (state.sessions) {
        state.sessions = state.sessions.filter((s) => s.id !== sid);
      }
      renderSessionsConsole(state.sessions || []);
      // 同时刷新侧边栏会话列表（chat.js 已有的 loadSessions → renderSessions）
      try { await loadSessions(); } catch (_) {}
      // 刷新概览的会话计数
      if (el.ovSessions && state.sessions) {
        el.ovSessions.textContent = state.sessions.length;
      }
    } catch (err) {
      alert("删除失败: " + (err.message || err));
    }
  }

  /** 拉取会话列表并渲染控制台表格 */
  async function loadConsoleSessions() {
    // 显示 loading（如果表格还没数据）
    if (el.sesTable) el.sesTable.style.display = "none";
    if (el.sesLoading) el.sesLoading.hidden = false;
    if (el.sesEmpty) el.sesEmpty.hidden = true;

    try {
      const data = await api("/api/sessions");
      state.sessions = data.sessions || [];
    } catch (err) {
      console.error("加载会话列表失败:", err);
      state.sessions = [];
    } finally {
      renderSessionsConsole(state.sessions || []);
    }
  }

  /** 绑定筛选栏的实时过滤（debounce 50ms）和刷新按钮 */
  function _bindSessionFilters() {
    if (el.sesRefresh) {
      el.sesRefresh.addEventListener("click", () => loadConsoleSessions());
    }

    let debounceTimer = null;
    const onFilterChange = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        renderSessionsConsole(state.sessions || []);
      }, 80);
    };

    [el.sesActiveWithin, el.sesLimit].forEach((input) => {
      input?.addEventListener("input", onFilterChange);
    });
  }

  // 在 DOMContentLoaded 时绑定筛选事件（如果存在）
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _bindSessionFilters);
  } else {
    _bindSessionFilters();
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

      // 网关概览
      await renderGateway();
    } catch (err) {
      console.warn("[SimChat] 概览渲染失败:", err);
    }
  }

  // ---------------- 网关概览渲染 ----------------

  function _formatHealth(h) {
    return { online: "在线", degraded: "降级", offline: "离线" }[h] || h || "—";
  }

  function _formatTimestamp(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch (_) { return iso; }
  }

  function _setGatewayMsg(msg, type) {
    if (!el.gwAccessMsg) return;
    el.gwAccessMsg.textContent = msg || "";
    el.gwAccessMsg.classList.remove("ok", "error");
    if (type) el.gwAccessMsg.classList.add(type);
  }

  async function renderGateway() {
    try {
      const data = await api("/api/gateway");
      const access = data.access || {};
      const snap = data.snapshot || {};

      // 访问字段
      if (el.gwSocketUrl) el.gwSocketUrl.value = access.socket_url || "";
      if (el.gwAccessToken) el.gwAccessToken.value = access.access_token || "";
      if (el.gwSessionKey) el.gwSessionKey.value = access.session_key || "";
      if (el.gwLanguage) el.gwLanguage.value = access.language || "";

      // 顶部健康徽章
      const h = snap.health || "offline";
      if (el.gwHealthBadge) {
        el.gwHealthBadge.textContent = _formatHealth(h);
        el.gwHealthBadge.classList.remove("ok", "degraded", "offline");
        if (h === "online") el.gwHealthBadge.classList.add("ok");
        else if (h === "degraded") el.gwHealthBadge.classList.add("degraded");
        else el.gwHealthBadge.classList.add("offline");
      }

      // 快照时间
      if (el.gwHandshakeTime) {
        el.gwHandshakeTime.textContent = "握手 " + _formatTimestamp(snap.handshake_at);
      }

      // 快照网格
      if (el.gwHealth) {
        el.gwHealth.textContent = _formatHealth(h);
        el.gwHealth.classList.remove("health-online", "health-degraded", "health-offline");
        el.gwHealth.classList.add("health-" + h);
      }
      if (el.gwUptime) {
        el.gwUptime.textContent = formatUptime(snap.uptime_seconds || 0);
      }
      if (el.gwTickInterval) {
        if (snap.tick_interval_ms != null) {
          el.gwTickInterval.textContent = snap.tick_interval_ms + " ms";
          el.gwTickInterval.classList.remove("na");
        } else {
          el.gwTickInterval.textContent = "Not available";
          el.gwTickInterval.classList.add("na");
        }
      }
      if (el.gwChannelRefresh) {
        if (snap.channel_last_refresh) {
          el.gwChannelRefresh.textContent = _formatTimestamp(snap.channel_last_refresh);
          el.gwChannelRefresh.classList.remove("na");
        } else {
          el.gwChannelRefresh.textContent = "—";
        }
      }

      // 频道提示
      if (el.gwChannelHint) {
        el.gwChannelHint.style.display = snap.channel_available ? "none" : "flex";
      }
    } catch (err) {
      console.warn("[SimChat] 网关渲染失败:", err);
      _setGatewayMsg("网关快照加载失败", "error");
    }
  }

  async function connectGateway() {
    _setGatewayMsg("连接中…");
    try {
      const data = await api("/api/gateway/connect", {
        method: "POST",
        body: JSON.stringify({ password: el.gwPassword?.value || null }),
      });
      if (data.ok) {
        _setGatewayMsg(data.message || "握手成功", "ok");
        await renderGateway();
      } else {
        _setGatewayMsg(data.error || "连接失败", "error");
      }
    } catch (err) {
      _setGatewayMsg("连接请求失败", "error");
    }
  }

  async function _copyToClipboard(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
    } catch (_) { /* 静默失败 */ }
  }

  // ---------------- 通讯通道 ----------------

  function _setCommMsg(msg, kind) {
    if (!el.commFormMsg) return;
    el.commFormMsg.textContent = msg || "";
    el.commFormMsg.classList.remove("ok", "error");
    if (kind) el.commFormMsg.classList.add(kind);
  }

  async function loadComms() {
    try {
      const resp = await api("/api/console/comms");
      state.comms = resp.data || null;
      renderComms();
    } catch (err) {
      console.warn("[SimChat] 通讯通道加载失败:", err);
      state.comms = { active: null, channels: [] };
      if (el.commForm) el.commForm.innerHTML =
        '<div class="state-card" style="border-style:solid"><div class="state-card-icon">⚠️</div>' +
        '<h4 class="state-card-title">通讯通道加载失败</h4>' +
        '<p class="state-card-reason">' + escapeHtml(err.message) + '</p></div>';
      if (el.commFormActions) el.commFormActions.style.display = "none";
    }
  }

  function _commRuntimeOf(channel) {
    return (channel && (channel.runtime || null)) || null;
  }

  function _commTabIndicatorClass(ch) {
    const runtime = _commRuntimeOf(ch);
    if (runtime && runtime.running) return " running";
    if ((ch.fields || []).some((f) => f.configured)) return " configured";
    return "";
  }

  function _commTabIndicatorTitle(ch) {
    const runtime = _commRuntimeOf(ch);
    if (runtime && runtime.running) {
      return runtime.connected ? "运行中且已连接" : "运行中，等待事件";
    }
    if ((ch.fields || []).some((f) => f.configured)) return "已配置";
    return "未配置";
  }

  function _makeCommTab(ch, currentId) {
    const isSelected = ch.id === currentId;
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "comm-channel-tab" + (isSelected ? " is-active" : "");
    tab.dataset.channelId = ch.id;
    tab.title = ch.description || ch.label;

    const indicator = document.createElement("span");
    const indicatorClass = _commTabIndicatorClass(ch);
    indicator.className = "comm-channel-tab-indicator" + indicatorClass;
    indicator.title = _commTabIndicatorTitle(ch);

    const label = document.createElement("span");
    label.className = "comm-channel-tab-label";
    label.textContent = ch.label;

    tab.appendChild(indicator);
    tab.appendChild(label);
    tab.addEventListener("click", () => {
      state.commsActiveChannel = ch.id;
      state.commsRuntimeMsg = null;
      renderComms();
    });
    return tab;
  }

  function renderComms() {
    const data = state.comms;
    if (!data || !data.channels || !data.channels.length) return;

    // 决定当前选中的 tab
    let currentId = state.commsActiveChannel;
    if (!currentId || !data.channels.find((c) => c.id === currentId)) {
      currentId = data.active || data.channels[0].id;
    }
    state.commsActiveChannel = currentId;

    // 按 group 分组渲染（群机器人是一个分组，两种接入方式是组内两个独立按钮）
    if (el.commChannelTabs) {
      el.commChannelTabs.innerHTML = "";
      const groups = [];
      const byKey = {};
      for (const ch of data.channels) {
        const key = ch.group || "__single__";
        if (!byKey[key]) {
          byKey[key] = { label: ch.group_label || "", channels: [] };
          groups.push(byKey[key]);
        }
        byKey[key].channels.push(ch);
      }
      for (const group of groups) {
        const groupEl = document.createElement("div");
        groupEl.className = "comm-channel-group";
        if (group.label) {
          const head = document.createElement("div");
          head.className = "comm-channel-group-head";
          head.textContent = group.label;
          groupEl.appendChild(head);
        }
        const row = document.createElement("div");
        row.className = "comm-channel-group-tabs";
        for (const ch of group.channels) {
          row.appendChild(_makeCommTab(ch, currentId));
        }
        groupEl.appendChild(row);
        el.commChannelTabs.appendChild(groupEl);
      }
    }

    // 渲染当前选中通道的表单
    const channel = data.channels.find((c) => c.id === currentId) || data.channels[0];
    if (!channel) return;
    renderCommForm(channel, currentId === data.active);
  }

  function renderCommForm(channel, isActive) {
    if (!el.commForm) return;

    // 顶部描述
    let html = '<div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">' +
      escapeHtml(channel.description || "") + '</div>';

    // 群机器人运行面板（启动 / 停止 / 测试 / Webhook 地址）
    if (channel.runtime_supported) {
      html += renderCommRuntimeHtml(channel);
    }

    // 加密提示条（仅当有敏感字段时显示）
    const hasSensitive = (channel.fields || []).some((f) => f.sensitive);
    if (hasSensitive) {
      html += '<div class="comm-form-secret-hint">🔒 敏感字段（AK / 授权码等）在本机加密存储，永不明文回显。' +
        '留空敏感字段表示"保持不变"。</div>';
    }

    // 字段网格
    html += '<div class="comm-form-grid">';
    for (const field of (channel.fields || [])) {
      const isBool = typeof field.default === "boolean";
      const isSelect = field.type === "select";
      const isTextarea = field.type === "textarea";
      const cls = "comm-field" + (field.sensitive ? " sensitive" : "") + (isBool ? "" : " full");

      html += '<label class="' + cls + '" data-key="' + escapeHtml(field.key) + '">';
      html += '<span class="comm-field-label">' + escapeHtml(field.label) + '</span>';

      if (isBool) {
        // 未保存过时按默认值显示，避免默认开启的开关显示成关闭
        const rawValue = String(field.value ?? "").trim().toLowerCase();
        const checked = field.value === true || rawValue === "true" || rawValue === "1" ||
          (rawValue === "" && field.default === true);
        html += '<div class="field-switch" style="margin-top:2px">';
        html += '<div class="switch-track' + (checked ? " on" : "") + '" data-key="' + escapeHtml(field.key) + '">';
        html += '<div class="switch-thumb"></div></div>';
        html += '<span class="switch-label">' + (checked ? "启用" : "关闭") + '</span>';
        html += '</div>';
      } else if (isSelect) {
        const current = String(field.value || field.default || "");
        html += '<select class="comm-field-input" data-key="' + escapeHtml(field.key) + '">';
        for (const choice of (field.choices || [])) {
          const value = String(choice[0]);
          const selected = value === current ? " selected" : "";
          html += '<option value="' + escapeHtml(value) + '"' + selected + '>' +
            escapeHtml(String(choice[1] || value)) + '</option>';
        }
        html += '</select>';
      } else if (field.sensitive) {
        // 敏感字段：type=password，值为 "********" 或 ""
        html += '<input type="password" class="comm-field-input" data-key="' + escapeHtml(field.key) + '"' +
          ' placeholder="' + (field.configured ? "已保存，留空保持不变" : escapeHtml(field.placeholder || "在此输入")) + '"' +
          ' autocomplete="off" value="">';
        if (field.configured) {
          html += '<span class="comm-field-hint">当前已加密保存</span>';
        } else if (field.placeholder) {
          html += '<span class="comm-field-hint">' + escapeHtml(field.placeholder) + '</span>';
        }
      } else if (isTextarea) {
        html += '<textarea class="comm-field-input" rows="3" data-key="' + escapeHtml(field.key) + '"' +
          ' placeholder="' + escapeHtml(field.placeholder || "") + '">' +
          escapeHtml(String(field.value || "")) + '</textarea>';
      } else {
        html += '<input type="text" class="comm-field-input" data-key="' + escapeHtml(field.key) + '"' +
          ' placeholder="' + escapeHtml(field.placeholder || "") + '"' +
          ' value="' + escapeHtml(String(field.value || "")) + '">';
      }
      html += '</label>';
    }
    html += '</div>';

    el.commForm.innerHTML = html;
    if (el.commFormActions) el.commFormActions.style.display = "";

    // 布尔开关：点击切换并在保存时随表单一起提交
    el.commForm.querySelectorAll(".field-switch").forEach((row) => {
      row.addEventListener("click", () => {
        const track = row.querySelector(".switch-track");
        if (!track) return;
        track.classList.toggle("on");
        const label = row.querySelector(".switch-label");
        if (label) label.textContent = track.classList.contains("on") ? "启用" : "关闭";
      });
    });

    if (channel.runtime_supported) bindCommRuntime(channel);
    _setCommMsg("");
  }

  // ---------------- 群机器人运行面板 ----------------

  function _commRuntimeStatus(channel) {
    const runtime = _commRuntimeOf(channel) || {};
    const transport = runtime.transport || "";
    if (!runtime.running) return { text: "未运行", cls: "idle" };
    if (runtime.connected) return { text: "运行中 · 已连接", cls: "on" };
    if (transport === "http" || transport === "webhook") {
      return { text: "运行中 · 等待回调", cls: "warn" };
    }
    return { text: "运行中 · 连接中", cls: "warn" };
  }

  function _commTransportLabel(channel, transport) {
    for (const field of (channel.fields || [])) {
      if (field.key !== "transport") continue;
      for (const choice of (field.choices || [])) {
        if (String(choice[0]) === transport) return String(choice[1] || transport);
      }
    }
    return transport || "—";
  }

  function _commWebhookUrl(channel) {
    if (!channel.webhook_path) return "";
    return location.origin + channel.webhook_path;
  }

  function renderCommRuntimeHtml(channel) {
    const runtime = _commRuntimeOf(channel) || {};
    const status = _commRuntimeStatus(channel);
    const counts = "收 " + (runtime.messages_in || 0) + " / 发 " + (runtime.replies_out || 0);
    const transport = runtime.transport || _commTransportValue(channel);
    const isOneBot = channel.id === "qq_group_onebot";
    const webhookVisible = isOneBot ? transport === "http" : transport === "webhook";
    const groupPlaceholder = isOneBot ? "群号，例如 123456789" : "群 OpenID（group_openid）";
    const msg = state.commsRuntimeMsg && state.commsRuntimeMsg.channelId === channel.id
      ? state.commsRuntimeMsg : null;

    let html = '<div class="comm-runtime" data-runtime-channel="' + escapeHtml(channel.id) + '">';
    html += '<div class="comm-runtime-head">';
    html += '<span class="comm-runtime-dot ' + status.cls + '" data-role="dot"></span>';
    html += '<strong class="comm-runtime-title">群机器人运行时</strong>';
    html += '<span class="comm-runtime-state" data-role="state">' + escapeHtml(status.text) + '</span>';
    html += '<span class="comm-runtime-counters" data-role="counters">' + counts + '</span>';
    html += '</div>';
    html += '<div class="comm-runtime-meta" data-role="meta">' + escapeHtml(_commRuntimeMeta(channel, runtime)) + '</div>';
    html += '<div class="comm-runtime-error" data-role="error"' +
      (runtime.last_error ? "" : ' style="display:none"') + '>' +
      escapeHtml(runtime.last_error || "") + '</div>';
    html += '<div class="comm-runtime-actions">';
    html += '<button type="button" class="primary-button" data-role="start"' +
      (runtime.running ? " disabled" : "") + '>启动</button>';
    html += '<button type="button" class="ghost-button" data-role="stop"' +
      (runtime.running ? "" : " disabled") + '>停止</button>';
    html += '<button type="button" class="ghost-button" data-role="testconn">测试连接</button>';
    html += '</div>';
    html += '<div class="comm-runtime-groups" data-role="groups"></div>';
    html += '<div class="comm-runtime-webhook" data-role="webhook"' +
      (webhookVisible ? "" : ' style="display:none"') + '>';
    html += '<span class="comm-runtime-webhook-label">回调地址</span>';
    html += '<code data-role="webhook-url">' + escapeHtml(_commWebhookUrl(channel)) + '</code>';
    html += '<button type="button" class="ghost-button" data-role="copy-webhook">复制</button>';
    html += '</div>';
    html += '<div class="comm-test-send">';
    html += '<input type="text" class="comm-field-input" data-role="test-group" placeholder="' +
      escapeHtml(groupPlaceholder) + '">';
    html += '<input type="text" class="comm-field-input" data-role="test-msg" placeholder="测试消息内容">';
    html += '<button type="button" class="ghost-button" data-role="testsend">发送测试</button>';
    html += '</div>';
    if (!isOneBot) {
      html += '<div class="comm-runtime-tip">官方 API 默认只能被动回复：先在群里 @ 机器人一次，' +
        '再点「发送测试」，会自动使用该群最近一条消息的 ID。</div>';
    }
    html += '<div class="comm-runtime-msg" data-role="msg"></div>';
    html += '</div>';
    return html;
  }

  function _commRuntimeMeta(channel, runtime) {
    const transport = runtime.transport || _commTransportValue(channel);
    const parts = [];
    parts.push("连接方式：" + _commTransportLabel(channel, transport));
    if (runtime.started_at) parts.push("启动于 " + runtime.started_at);
    if (runtime.last_message_at) parts.push("最近收消息 " + runtime.last_message_at);
    if (runtime.last_reply_at) parts.push("最近回复 " + runtime.last_reply_at);
    const groupCount = (runtime.groups || []).length;
    if (groupCount) parts.push("已发现 " + groupCount + " 个群");
    return parts.join(" · ");
  }

  function _renderCommGroups(panel, channel, runtime) {
    const node = panel.querySelector('[data-role="groups"]');
    if (!node) return;
    const groups = runtime.groups || [];
    if (!groups.length) {
      node.innerHTML = '<span class="comm-runtime-groups-empty">还没有发现群：' +
        '把机器人拉进群，或在群里 @ 它一次，这里会出现可点选的群标识。</span>';
      return;
    }
    node.innerHTML = '<span class="comm-runtime-groups-label">最近活跃群（点击填入）</span>';
    for (const group of groups) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "comm-runtime-group-chip";
      chip.dataset.group = group.id;
      chip.textContent = group.id;
      chip.title = "点击填入测试发送的群标识";
      node.appendChild(chip);
    }
  }

  function _commTransportValue(channel) {
    const field = (channel.fields || []).find((f) => f.key === "transport");
    if (!field) return "";
    return String(field.value || field.default || "");
  }

  function _setRuntimeMsg(channelId, text, kind) {
    state.commsRuntimeMsg = text ? { channelId, text, kind: kind || "" } : null;
    const panel = el.commForm?.querySelector('[data-runtime-channel="' + channelId + '"]');
    if (!panel) return;
    const node = panel.querySelector('[data-role="msg"]');
    if (!node) return;
    node.textContent = text || "";
    node.classList.remove("ok", "error");
    if (kind) node.classList.add(kind);
  }

  function applyCommRuntime(channel) {
    const panel = el.commForm?.querySelector('[data-runtime-channel="' + channel.id + '"]');
    if (!panel) return;
    const runtime = _commRuntimeOf(channel) || {};
    const status = _commRuntimeStatus(channel);
    const dot = panel.querySelector('[data-role="dot"]');
    if (dot) dot.className = "comm-runtime-dot " + status.cls;
    const stateNode = panel.querySelector('[data-role="state"]');
    if (stateNode) stateNode.textContent = status.text;
    const counters = panel.querySelector('[data-role="counters"]');
    if (counters) counters.textContent =
      "收 " + (runtime.messages_in || 0) + " / 发 " + (runtime.replies_out || 0);
    const meta = panel.querySelector('[data-role="meta"]');
    if (meta) meta.textContent = _commRuntimeMeta(channel, runtime);
    const error = panel.querySelector('[data-role="error"]');
    if (error) {
      error.textContent = runtime.last_error || "";
      error.style.display = runtime.last_error ? "" : "none";
    }
    const startBtn = panel.querySelector('[data-role="start"]');
    if (startBtn) startBtn.disabled = !!runtime.running;
    const stopBtn = panel.querySelector('[data-role="stop"]');
    if (stopBtn) stopBtn.disabled = !runtime.running;
    _renderCommGroups(panel, channel, runtime);
    _updateCommWebhookVisibility(channel);
  }

  function _updateCommWebhookVisibility(channel) {
    const panel = el.commForm?.querySelector('[data-runtime-channel="' + channel.id + '"]');
    if (!panel) return;
    const select = el.commForm?.querySelector('[data-key="transport"]');
    const transport = select ? String(select.value || "") : _commTransportValue(channel);
    const isOneBot = channel.id === "qq_group_onebot";
    const row = panel.querySelector('[data-role="webhook"]');
    if (!row) return;
    const visible = isOneBot ? transport === "http" : transport === "webhook";
    row.style.display = visible ? "" : "none";
    const urlNode = row.querySelector('[data-role="webhook-url"]');
    if (urlNode) urlNode.textContent = _commWebhookUrl(channel);
  }

  function _commChannelNow(channelId) {
    return (state.comms?.channels || []).find((c) => c.id === channelId) || null;
  }

  function bindCommRuntime(channel) {
    const panel = el.commForm?.querySelector('[data-runtime-channel="' + channel.id + '"]');
    if (!panel) return;
    _renderCommGroups(panel, channel, _commRuntimeOf(channel) || {});
    _updateCommWebhookVisibility(channel);

    // 群标识 chip 用事件委托，轮询刷新后依然有效
    panel.querySelector('[data-role="groups"]')?.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-group]");
      if (!chip) return;
      const target = panel.querySelector('[data-role="test-group"]');
      if (target) target.value = chip.dataset.group;
      _setRuntimeMsg(channel.id, "已填入群标识，点「发送测试」即可");
    });

    const select = el.commForm?.querySelector('[data-key="transport"]');
    if (select) {
      select.addEventListener("change", () => _updateCommWebhookVisibility(channel));
    }

    const startBtn = panel.querySelector('[data-role="start"]');
    startBtn?.addEventListener("click", () => startCommBot(channel.id));
    const stopBtn = panel.querySelector('[data-role="stop"]');
    stopBtn?.addEventListener("click", () => stopCommBot(channel.id));
    const testConn = panel.querySelector('[data-role="testconn"]');
    testConn?.addEventListener("click", () => testCommConnection(channel.id));
    const copyBtn = panel.querySelector('[data-role="copy-webhook"]');
    copyBtn?.addEventListener("click", () => {
      _copyToClipboard(panel.querySelector('[data-role="webhook-url"]')?.textContent || "");
      _setRuntimeMsg(channel.id, "回调地址已复制");
      setTimeout(() => _setRuntimeMsg(channel.id, ""), 1500);
    });
    const testSend = panel.querySelector('[data-role="testsend"]');
    testSend?.addEventListener("click", () => {
      const group = panel.querySelector('[data-role="test-group"]')?.value || "";
      const message = panel.querySelector('[data-role="test-msg"]')?.value || "";
      testCommSend(channel.id, group, message);
    });
  }

  async function _saveCommSilent(channelId) {
    const payload = collectCommForm();
    const resp = await api("/api/console/comms/" + channelId, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.data) state.comms = resp.data;
    return resp;
  }

  async function _refreshCommsFromServer() {
    const resp = await api("/api/console/comms");
    state.comms = resp.data || null;
  }

  async function startCommBot(channelId) {
    _setRuntimeMsg(channelId, "正在保存配置并启动…");
    try {
      await _saveCommSilent(channelId);
      const resp = await api("/api/console/comms/" + channelId + "/start", { method: "POST" });
      if (resp.data) state.comms = resp.data;
      state.commsRuntimeMsg = { channelId, text: "群机器人已启动", kind: "ok" };
      renderComms();
    } catch (err) {
      _setRuntimeMsg(channelId, err.message || "启动失败", "error");
    }
  }

  async function stopCommBot(channelId) {
    _setRuntimeMsg(channelId, "正在停止…");
    try {
      const resp = await api("/api/console/comms/" + channelId + "/stop", { method: "POST" });
      if (resp.data) state.comms = resp.data;
      state.commsRuntimeMsg = { channelId, text: "群机器人已停止", kind: "ok" };
      renderComms();
    } catch (err) {
      _setRuntimeMsg(channelId, err.message || "停止失败", "error");
    }
  }

  async function testCommConnection(channelId) {
    _setRuntimeMsg(channelId, "正在测试连接…");
    try {
      await _saveCommSilent(channelId);
      const resp = await api("/api/console/comms/" + channelId + "/test-connection", { method: "POST" });
      const channel = _commChannelNow(channelId);
      if (channel && resp.runtime) channel.runtime = resp.runtime;
      if (channel) applyCommRuntime(channel);
      _setRuntimeMsg(channelId, resp.detail || "连接成功", "ok");
    } catch (err) {
      _setRuntimeMsg(channelId, err.message || "连接失败", "error");
    }
  }

  async function testCommSend(channelId, group, message) {
    if (!group.trim()) {
      _setRuntimeMsg(channelId, "请先填写群号 / 群 OpenID", "error");
      return;
    }
    if (!message.trim()) {
      _setRuntimeMsg(channelId, "请先填写测试消息", "error");
      return;
    }
    _setRuntimeMsg(channelId, "正在发送测试消息…");
    try {
      await _saveCommSilent(channelId);
      const resp = await api("/api/console/comms/" + channelId + "/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: group.trim(), message: message.trim() }),
      });
      const channel = _commChannelNow(channelId);
      if (channel && resp.runtime) channel.runtime = resp.runtime;
      if (channel) applyCommRuntime(channel);
      _setRuntimeMsg(channelId, "测试消息已发送", "ok");
    } catch (err) {
      _setRuntimeMsg(channelId, err.message || "发送失败", "error");
    }
  }

  function updateCommRuntimePolling() {
    if (state.activeSection === "comms") {
      if (!state.commsPollTimer) {
        state.commsPollTimer = setInterval(refreshCommRuntime, 8000);
      }
    } else if (state.commsPollTimer) {
      clearInterval(state.commsPollTimer);
      state.commsPollTimer = null;
    }
  }

  async function refreshCommRuntime() {
    if (state.activeSection !== "comms" || !state.comms?.channels) return;
    try {
      const resp = await api("/api/console/comms/runtime");
      const runtimeMap = resp.data || {};
      for (const channel of state.comms.channels) {
        if (runtimeMap[channel.id]) channel.runtime = runtimeMap[channel.id];
      }
      // 更新当前面板 + 所有 tab 指示点
      const current = _commChannelNow(state.commsActiveChannel);
      if (current?.runtime_supported) applyCommRuntime(current);
      if (el.commChannelTabs) {
        for (const tab of el.commChannelTabs.querySelectorAll(".comm-channel-tab")) {
          const channel = _commChannelNow(tab.dataset.channelId);
          const dot = tab.querySelector(".comm-channel-tab-indicator");
          if (!channel || !dot) continue;
          dot.className = "comm-channel-tab-indicator" + _commTabIndicatorClass(channel);
          dot.title = _commTabIndicatorTitle(channel);
        }
      }
    } catch (_) {
      /* 轮询失败静默 */
    }
  }

  function collectCommForm() {
    if (!el.commForm) return {};
    const payload = {};
    el.commForm.querySelectorAll("[data-key]").forEach((el) => {
      const key = el.dataset.key;
      if (el.classList.contains("switch-track")) {
        payload[key] = el.classList.contains("on");
      } else if (el.type === "checkbox") {
        payload[key] = el.checked;
      } else {
        payload[key] = el.value;
      }
    });
    return payload;
  }

  async function saveCommChannel() {
    const channelId = state.commsActiveChannel;
    if (!channelId) return;
    const payload = collectCommForm();
    _setCommMsg("保存中…");
    try {
      const resp = await api("/api/console/comms/" + channelId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.comms = resp.data || null;
      renderComms();
      _setCommMsg("已保存（敏感字段已加密）", "ok");
      setTimeout(() => {
        const sec = (state.comms?.channels || []).find((c) => c.id === channelId);
        renderCommForm(sec, state.comms?.active === channelId);
      }, 600);
    } catch (err) {
      _setCommMsg(err.message || "保存失败", "error");
    }
  }

  async function clearCommChannel() {
    const channelId = state.commsActiveChannel;
    if (!channelId) return;
    if (!confirm("确定要清除 " + channelId + " 的全部配置吗？此操作不可撤销。")) return;
    _setCommMsg("清除中…");
    try {
      const resp = await api("/api/console/comms/" + channelId + "/clear", {
        method: "POST",
      });
      state.comms = resp.data || null;
      renderComms();
      _setCommMsg("已清除", "ok");
    } catch (err) {
      _setCommMsg(err.message || "清除失败", "error");
    }
  }

  // ---------------- 事件绑定 ----------------

  el.newChat.addEventListener("click", startNewChat);
  el.toggleSidebar.addEventListener("click", openSidebar);
  el.backdrop.addEventListener("click", closeSidebar);
  el.openSetup.addEventListener("click", showSetup);
  el.lockConfig.addEventListener("click", () => {
    if (!workspaceReady()) openWorkspacePicker();
    else showSetup();
  });

  // 工作目录选择器
  el.workspaceChip?.addEventListener("click", openWorkspacePicker);
  el.workspaceClose?.addEventListener("click", closeWorkspacePicker);
  el.workspaceCancel?.addEventListener("click", closeWorkspacePicker);
  el.workspaceConfirm?.addEventListener("click", confirmWorkspace);
  el.workspaceUp?.addEventListener("click", workspaceGoUp);
  el.workspaceManualOpen?.addEventListener("click", openManualWorkspacePath);
  el.workspaceManualPath?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      openManualWorkspacePath();
    }
  });
  el.workspaceClear?.addEventListener("click", clearWorkspace);
  el.workspaceModal?.addEventListener("click", (event) => {
    if (event.target === el.workspaceModal) closeWorkspacePicker();
  });

  el.agentToggle?.addEventListener("click", toggleAgentMode);
  el.agentToggle?.addEventListener("keydown", (e) => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleAgentMode(); }
  });

  // Composer 工具条：附件上传 / 模型选择 / 预留开关
  el.attachBtn?.addEventListener("click", () => el.attachInput?.click());
  el.attachInput?.addEventListener("change", () => {
    attachFile(el.attachInput.files && el.attachInput.files[0]);
    el.attachInput.value = "";
  });
  el.modelSelect?.addEventListener("change", () => {
    const val = el.modelSelect.value || "";
    if (val === "__auto__") {
      state.model = null;
      state.modelProvider = "auto";
    } else if (val.includes("::")) {
      const idx = val.indexOf("::");
      state.modelProvider = val.substring(0, idx);
      state.model = val.substring(idx + 2);
    } else {
      state.model = val || null;
      state.modelProvider = null;
    }
  });
  el.modelRefresh?.addEventListener("click", async () => {
    const btn = el.modelRefresh;
    btn.classList.add("refreshing");
    // 先刷新 /api/providers 拿最新配置（后端会自动探测 models）
    try {
      await loadProviders();
    } finally {
      btn.classList.remove("refreshing");
    }
  });
  el.approvalMode?.addEventListener("change", () => {
    state.approvalMode = el.approvalMode.value;
  });
  bindReservedToggle(el.orbiterMode);
  bindReservedToggle(el.voiceInputMode);
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
    if (!workspaceReady()) {
      openWorkspacePicker();
      return;
    }
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

  // 角色切换 UI 已移除（架构先行）：后端 /api/settings 的 character 段保留，
  // 前端在架构完成后以新页面形态重新接入。

  el.saveSettingsBtn?.addEventListener("click", saveSettings);
  el.resetSettingsBtn?.addEventListener("click", resetSettings);
  el.openConsole?.addEventListener("click", openConsole);

  // ---------------- 个人中心事件绑定 ----------------

  el.userBadge?.addEventListener("click", () => {
    closeSidebar();
    openConsole("profile");
  });
  el.profileAvatarInput?.addEventListener("change", pickProfileAvatar);
  el.profileAvatarClear?.addEventListener("click", clearProfileAvatar);
  el.profileSave?.addEventListener("click", saveProfile);

  // ---------------- 控制台事件绑定 ----------------

  el.navItems?.forEach((nav) => {
    nav.addEventListener("click", () => switchSection(nav.dataset.section));
  });
  el.consoleBack?.addEventListener("click", closeConsole);

  // 网关概览事件绑定
  el.gwConnect?.addEventListener("click", connectGateway);
  el.gwRefresh?.addEventListener("click", async () => {
    _setGatewayMsg("刷新中…");
    try {
      await renderGateway();
      _setGatewayMsg("已刷新", "ok");
    } catch (_) {
      _setGatewayMsg("刷新失败", "error");
    }
  });
  el.gwCopyUrl?.addEventListener("click", () => {
    _copyToClipboard(el.gwSocketUrl?.value || "");
    _setGatewayMsg("URL 已复制");
    setTimeout(() => { if (el.gwAccessMsg?.textContent === "URL 已复制") _setGatewayMsg(""); }, 1500);
  });
  el.gwCopyToken?.addEventListener("click", () => {
    _copyToClipboard(el.gwAccessToken?.value || "");
    _setGatewayMsg("令牌已复制");
    setTimeout(() => { if (el.gwAccessMsg?.textContent === "令牌已复制") _setGatewayMsg(""); }, 1500);
  });

  // 通讯通道事件绑定（tab 的 click 已在 renderComms 里动态绑定）
  el.commSave?.addEventListener("click", saveCommChannel);
  el.commClear?.addEventListener("click", clearCommChannel);

  // 实验功能 · Hippo 开关（localStorage 级预留）
  const HIPPO_TOGGLE_KEY = "simchat.experiment.hippo";
  function initHippoToggle() {
    let enabled = false;
    try { enabled = localStorage.getItem(HIPPO_TOGGLE_KEY) === "1"; } catch (_) {}
    state.hippoEnabled = enabled;
    if (el.hippoToggle) el.hippoToggle.classList.toggle("on", enabled);
    if (el.hippoToggleLabel) el.hippoToggleLabel.textContent = enabled ? "已启用（后端未接入）" : "关闭";
  }
  function toggleHippo() {
    if (!el.hippoToggle) return;
    state.hippoEnabled = !state.hippoEnabled;
    el.hippoToggle.classList.toggle("on", state.hippoEnabled);
    if (el.hippoToggleLabel) {
      el.hippoToggleLabel.textContent = state.hippoEnabled ? "已启用（后端未接入）" : "关闭";
    }
    try { localStorage.setItem(HIPPO_TOGGLE_KEY, state.hippoEnabled ? "1" : "0"); } catch (_) {}
  }
  initHippoToggle();
  el.hippoToggle?.addEventListener("click", toggleHippo);

  // 启动与守护 · 事件绑定
  el.lifecycleAutostartTrack?.addEventListener("click", toggleAutostart);
  el.lifecycleAutostartTrack?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleAutostart();
    }
  });
  el.lifecycleWatchdogTrack?.addEventListener("click", () => {
    if (!state.lifecycle) {
      loadLifecycle();
      return;
    }
    if (state.lifecycle.watchdog?.enabled) {
      disableWatchdog();
    } else {
      openLifecycleConfirm();
    }
  });
  el.lifecycleWatchdogTrack?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    el.lifecycleWatchdogTrack.click();
  });
  el.lifecycleRefresh?.addEventListener("click", async () => {
    await loadLifecycle();
    lifecycleMsg("状态已刷新", "ok");
  });
  el.lifecycleStopWatchdog?.addEventListener("click", stopWatchdogOnly);
  el.lifecycleStopService?.addEventListener("click", stopService);
  el.lifecycleConfirmCheck?.addEventListener("change", updateLifecycleConfirmState);
  el.lifecycleConfirmInput?.addEventListener("input", updateLifecycleConfirmState);
  el.lifecycleConfirmEnable?.addEventListener("click", enableWatchdog);
  el.lifecycleConfirmCancel?.addEventListener("click", closeLifecycleConfirm);
  el.lifecycleConfirm?.addEventListener("click", (event) => {
    if (event.target === el.lifecycleConfirm) closeLifecycleConfirm();
  });

  // 键盘：Esc 优先关 console，其次关 setup（locked 时不关 setup）
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (el.lifecycleConfirm?.classList.contains("is-open")) {
      closeLifecycleConfirm();
    } else if (el.workspaceModal?.classList.contains("is-open")) {
      closeWorkspacePicker();
    } else if (el.settingsConsole?.classList.contains("is-open")) {
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
  updateQuotaUI(); // 每日用量进度条 + 超限横幅初始化

  (async function init() {
    await Promise.all([loadSessions(), loadProviders(), loadSettings(), loadProfile(), loadWorkspace()]);
    // 永远不自动进 console——用户点齿轮 → 进 setup，点"高级" → 进 console，返回 → 退出。
    // localStorage["simchat.advanced"] 历史残留，清掉避免每次刷新卡壳。
    try { localStorage.removeItem("simchat.advanced"); } catch (_) {}

    const lastSid = loadSessionId();
    if (lastSid) {
      // 恢复上次会话；若后端已删则静默回退到新对话（不弹出错误气泡）
      await openSession(lastSid, { silent: true });
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

    // ---------- 实例监控初始化 ----------
    initInstanceHeartbeat();
  })();

  // ============================================================
  // 实例 / 设备监控模块
  // ============================================================

  const INSTANCE_HEARTBEAT_KEY = "simchat.device_id";
  const INSTANCE_TAB_KEY = "simchat.tab_id";
  const INSTANCE_HEARTBEAT_INTERVAL = 15000;  // 15 秒一次
  const INSTANCE_POLL_INTERVAL = 5000;        // 在 instances 分区中每 5 秒刷列表

  function _generateShortId(len) {
    len = len || 12;
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let s = "";
    for (let i = 0; i < len; i++) s += chars.charAt(Math.floor(Math.random() * chars.length));
    return s;
  }

  /** 从 User-Agent 解析 OS、浏览器、版本等信息。纯前端，无需后端。 */
  function _parseUA() {
    const ua = navigator.userAgent || "";
    const platform = navigator.platform || "";
    let os = "Unknown", osVersion = "", browser = "Unknown", browserVersion = "", arch = "";

    // OS 检测
    if (/Windows NT 10\.0/.test(ua)) { os = "Windows"; osVersion = "10/11"; }
    else if (/Windows NT 6\.3/.test(ua)) { os = "Windows"; osVersion = "8.1"; }
    else if (/Windows NT 6\.2/.test(ua)) { os = "Windows"; osVersion = "8"; }
    else if (/Windows NT 6\.1/.test(ua)) { os = "Windows"; osVersion = "7"; }
    else if (/Windows NT 5\.1/.test(ua)) { os = "Windows"; osVersion = "XP"; }
    else if (/Mac OS X ([\d_.]+)/.test(ua)) { os = "macOS"; osVersion = (ua.match(/Mac OS X ([\d_.]+)/) || [, ""])[1].replace(/_/g, "."); }
    else if (/Android ([\d.]+)/.test(ua)) { os = "Android"; osVersion = (ua.match(/Android ([\d.]+)/) || [, ""])[1]; }
    else if (/iPhone|iPad|iPod/.test(ua)) { os = "iOS"; osVersion = (ua.match(/OS ([\d_]+)/) || [, ""])[1].replace(/_/g, "."); }
    else if (/Linux/.test(ua)) { os = "Linux"; osVersion = (platform || "").trim(); }
    else if (/HarmonyOS/.test(ua)) { os = "HarmonyOS"; osVersion = (ua.match(/HarmonyOS ([\d.]+)/) || [, ""])[1]; }

    // 浏览器检测（顺序敏感：Edge 包含 Chrome，Chrome 包含 Safari）
    if (/Edg\//.test(ua)) { browser = "Edge"; browserVersion = (ua.match(/Edg\/([\d.]+)/) || [, ""])[1]; }
    else if (/OPR\//.test(ua) || /Opera\//.test(ua)) { browser = "Opera"; browserVersion = (ua.match(/(?:OPR|Opera)\/([\d.]+)/) || [, ""])[1]; }
    else if (/Chrome\//.test(ua) && !/Chromium/.test(ua)) { browser = "Chrome"; browserVersion = (ua.match(/Chrome\/([\d.]+)/) || [, ""])[1]; }
    else if (/Safari\//.test(ua)) { browser = "Safari"; browserVersion = (ua.match(/Version\/([\d.]+)/) || [, ""])[1]; }
    else if (/Firefox\//.test(ua)) { browser = "Firefox"; browserVersion = (ua.match(/Firefox\/([\d.]+)/) || [, ""])[1]; }
    else if (/HarmonyOS/.test(ua)) { browser = "Harmony WebView"; browserVersion = (ua.match(/HarmonyOSBrowser\/([\d.]+)/) || [, ""])[1] || "—"; }

    // 架构
    if (/WOW64|Win64|x64|x86_64/.test(ua)) arch = "64-bit";
    else if (/ARM|aarch64/.test(ua)) arch = "ARM";
    else if (/Windows/.test(ua)) arch = "32-bit";

    // 优先用现代 UA Client Hints API（更精确）
    const uach = navigator.userAgentData;
    if (uach && uach.brands && uach.brands.length) {
      const brand = uach.brands
        .filter((b) => !b.brand.includes("Not") && !b.brand.includes("Chromium"))
        .sort((a, b) => (b.version || 0) - (a.version || 0))[0];
      if (brand) { browser = brand.brand; browserVersion = brand.version; }
      if (uach.platform) { os = uach.platform; }
      if (uach.platformVersion) osVersion = uach.platformVersion;
      if (uach.architecture) arch = uach.architecture;
    }

    return { os, os_version: osVersion, browser, browser_version: browserVersion, arch, ua };
  }

  /** 采集当前设备的完整信息 payload。 */
  function collectDeviceInfo() {
    const ua = _parseUA();
    const scr = screen || {};
    const today = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const isoDate = today.getFullYear() + "-" + pad(today.getMonth() + 1) + "-" + pad(today.getDate()) +
      " " + pad(today.getHours()) + ":" + pad(today.getMinutes()) + ":" + pad(today.getSeconds());

    return {
      // 系统
      os: ua.os,
      os_version: ua.os_version,
      arch: ua.arch,
      platform: navigator.platform || "",
      vendor: navigator.vendor || "",

      // 浏览器
      browser: ua.browser,
      browser_version: ua.browser_version,
      ua: ua.ua,

      // 屏幕
      screen: (scr.width || 0) + "×" + (scr.height || 0),
      viewport: (window.innerWidth || 0) + "×" + (window.innerHeight || 0),
      device_pixel_ratio: window.devicePixelRatio || 1,
      color_depth: scr.colorDepth || 0,

      // 环境
      language: navigator.language || (navigator.languages && navigator.languages[0]) || "",
      languages: (navigator.languages || []).slice(0, 3).join(", "),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      timezone_offset: new Date().getTimezoneOffset(),
      date: isoDate,

      // 硬件
      hardware_concurrency: navigator.hardwareConcurrency || 0,
      device_memory: navigator.deviceMemory || "",
      max_touch_points: navigator.maxTouchPoints || 0,

      // 网络
      online: navigator.onLine,
      connection_type: (navigator.connection && navigator.connection.effectiveType) || "",

      // SimChat
      simchat_build: "2026-11-03",
    };
  }

  /** 初始化 deviceId / tabId 并启动心跳。 */
  function initInstanceHeartbeat() {
    // deviceId：localStorage 持久化，同一浏览器同一用户始终相同
    try {
      let id = localStorage.getItem(INSTANCE_HEARTBEAT_KEY);
      if (!id) {
        id = "dev-" + _generateShortId(8) + "-" + Date.now().toString(36);
        localStorage.setItem(INSTANCE_HEARTBEAT_KEY, id);
      }
      state.deviceId = id;
    } catch (_) {
      state.deviceId = "anon-" + _generateShortId(12);
    }

    // tabId：sessionStorage，每个标签页唯一
    try {
      let tid = sessionStorage.getItem(INSTANCE_TAB_KEY);
      if (!tid) {
        tid = "tab-" + _generateShortId(6);
        sessionStorage.setItem(INSTANCE_TAB_KEY, tid);
      }
      state.tabId = tid;
    } catch (_) {
      state.tabId = "tab-" + _generateShortId(6);
    }

    // 首次立即发一次
    sendHeartbeat();
    // 然后定时
    state.heartbeatTimer = setInterval(sendHeartbeat, INSTANCE_HEARTBEAT_INTERVAL);

    // 页面隐藏时降低频率（可选），切回来立即发一次
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) sendHeartbeat();
    });
    // 关闭页面前最后发一次（sendBeacon 不丢失）
    window.addEventListener("beforeunload", () => {
      const payload = JSON.stringify({
        device_id: state.deviceId,
        tab_id: state.tabId,
        info: collectDeviceInfo(),
      });
      try { navigator.sendBeacon("/api/instances/heartbeat", payload); } catch (_) {}
    });
  }

  async function sendHeartbeat() {
    if (!state.deviceId) return;
    try {
      await fetch("/api/instances/heartbeat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: state.deviceId,
          tab_id: state.tabId,
          info: collectDeviceInfo(),
        }),
      });
    } catch (_) {
      /* 网络断开等情况静默跳过——下一轮会重试 */
    }
  }

  // ---------- 实例列表加载 / 渲染 ----------

  function startInstancesPolling() {
    stopInstancesPolling();
    // 切进来先立刻拉一次
    loadInstances();
    state.instancesPollTimer = setInterval(() => {
      if (state.activeSection === "instances") loadInstances();
    }, INSTANCE_POLL_INTERVAL);
  }

  function stopInstancesPolling() {
    if (state.instancesPollTimer) {
      clearInterval(state.instancesPollTimer);
      state.instancesPollTimer = null;
    }
  }

  async function loadInstances() {
    if (el.instRefresh) el.instRefresh.classList.add("loading");
    try {
      const data = await api("/api/instances");
      state.instances = data;
      renderInstances(data);
    } catch (_) {
      // 静默——下次轮询会重试
    } finally {
      if (el.instRefresh) el.instRefresh.classList.remove("loading");
    }
  }

  function _fmtAgo(seconds) {
    if (seconds < 5) return "刚刚";
    if (seconds < 60) return seconds + " 秒前";
    if (seconds < 3600) return Math.floor(seconds / 60) + " 分钟前";
    if (seconds < 86400) return Math.floor(seconds / 3600) + " 小时前";
    return Math.floor(seconds / 86400) + " 天前";
  }

  function _deviceIcon(os) {
    const name = String(os || "").toLowerCase();
    if (/android/.test(name) || /ios/.test(name) || /harmony/.test(name)) return "📱";
    if (/mac/.test(name)) return "💻";
    if (/linux/.test(name)) return "🐧";
    if (/windows/.test(name)) return "🪟";
    return "🖥️";
  }

  function renderInstances(data) {
    if (!data) return;

    // 顶部统计
    if (el.instOnline) el.instOnline.textContent = String(data.online || 0);
    if (el.instTotal) el.instTotal.textContent = String(data.total || 0);
    if (el.instGenerated) {
      const g = data.generated_at || "";
      el.instGenerated.textContent = g ? g.replace("T", " ").replace("Z", "") : "—";
    }

    if (!el.instList) return;
    el.instList.innerHTML = "";

    const items = data.instances || [];
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "instance-empty";
      empty.innerHTML = '<span class="instance-empty-icon">📡</span>还没有任何设备连接到这个 SimChat 实例。当前浏览器应该正在第一次上报，稍等几秒刷新。';
      el.instList.appendChild(empty);
      return;
    }

    for (const inst of items) {
      el.instList.appendChild(_buildInstanceCard(inst));
    }
  }

  function _buildInstanceCard(inst) {
    const card = document.createElement("div");
    card.className = "instance-card" + (inst.online ? "" : " is-offline");
    const isSelf = inst.device_id === state.deviceId;
    if (isSelf) card.classList.add("is-self");

    const info = inst.info || {};

    // ---- 头部 ----
    const head = document.createElement("div");
    head.className = "instance-head";

    const dot = document.createElement("div");
    dot.className = "instance-status-dot " + (inst.online ? "online" : "offline");
    head.appendChild(dot);

    const icon = document.createElement("div");
    icon.className = "instance-icon";
    icon.textContent = _deviceIcon(info.os);
    head.appendChild(icon);

    const title = document.createElement("div");
    title.className = "instance-title";
    const osLine = document.createElement("div");
    osLine.className = "instance-os";
    osLine.textContent = [info.os, info.os_version].filter(Boolean).join(" ") || "Unknown Device";
    title.appendChild(osLine);

    const sub = document.createElement("div");
    sub.className = "instance-sub";
    const parts = [];
    parts.push((info.browser || "—") + " " + (info.browser_version || ""));
    if (info.arch) parts.push(info.arch);
    if (inst.remote_ip) parts.push(inst.remote_ip);
    parts.push("首次接入 " + new Date(inst.first_seen * 1000).toLocaleString());
    sub.textContent = parts.join(" · ");
    title.appendChild(sub);
    head.appendChild(title);

    if (isSelf) {
      const selfBadge = document.createElement("span");
      selfBadge.className = "instance-self-badge";
      selfBadge.textContent = "本机";
      head.appendChild(selfBadge);
    }

    const pill = document.createElement("span");
    pill.className = "instance-status-pill " + (inst.online ? "online" : "offline");
    pill.textContent = inst.online ? "在线" : (_fmtAgo(inst.last_seen_ago_seconds) + " 离线");
    head.appendChild(pill);

    card.appendChild(head);

    // ---- 详情网格 ----
    const details = document.createElement("div");
    details.className = "instance-details";

    const row = (label, value, klass) => {
      const wrap = document.createElement("div");
      wrap.className = "instance-detail";
      const l = document.createElement("div");
      l.className = "instance-detail-label";
      l.textContent = label;
      const v = document.createElement("div");
      v.className = "instance-detail-value" + (klass ? " " + klass : "");
      v.textContent = (value === undefined || value === null || value === "") ? "—" : String(value);
      v.title = v.textContent;
      wrap.appendChild(l);
      wrap.appendChild(v);
      return wrap;
    };

    details.appendChild(row("屏幕", info.screen || "—"));
    details.appendChild(row("视口", info.viewport || "—"));
    details.appendChild(row("语言", info.language || "—", "normal"));
    details.appendChild(row("时区", info.timezone || "—", "normal"));
    details.appendChild(row("当前日期", info.date || "—"));
    details.appendChild(row("设备像素比", info.device_pixel_ratio || "—"));
    details.appendChild(row("CPU 核心", info.hardware_concurrency || "—"));
    details.appendChild(row("内存 (GB)", info.device_memory || "—"));
    details.appendChild(row("触摸点", info.max_touch_points || 0));
    details.appendChild(row("网络", info.connection_type || (info.online ? "online" : "offline"), "normal"));
    if (info.simchat_build) details.appendChild(row("SimChat 版本", info.simchat_build));
    if (inst.tabs > 1) details.appendChild(row("标签页数", inst.tabs));

    // 最后心跳 / 首次接入（时间戳，友好显示）
    const lastHb = new Date(inst.last_heartbeat * 1000).toLocaleString();
    details.appendChild(row("最后心跳", lastHb));

    card.appendChild(details);

    return card;
  }

  // 刷新按钮绑定
  el.instRefresh?.addEventListener("click", loadInstances);
})();

