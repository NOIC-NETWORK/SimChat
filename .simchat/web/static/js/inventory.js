/* SimChat Web — 原子能力物品栏（I 键开关）
   数据来源：/api/agent/tools（原子能力与装备状态）、/api/console/skills、/api/console/automation。
   装备状态按实例存在服务端（agents.json 的 equipped 字段），不使用 localStorage 作为权威。
   MCP / CoT / Orbiter 运行时未接入，仅如实展示空状态，不提供占位开关。 */
(() => {
  "use strict";

  const CATEGORIES = [
    {
      id: "blocks",
      label: "原子能力",
      icon: "🧱",
      desc: "ReAct 可直接调用的内建方块与已加载 MOD 工具；装备决定模型看得见、调得动什么。",
      endpoint: "/api/agent/tools",
    },
    {
      id: "skills",
      label: "技能",
      icon: "✦",
      desc: "loader 扫描到的 skill 包，经 skills 元工具调用。",
      endpoint: "/api/console/skills",
    },
    {
      id: "automation",
      label: "自动化",
      icon: "⏱",
      desc: "automation 引擎的 flow 清单，按触发器运行。",
      endpoint: "/api/console/automation",
    },
    {
      id: "mcp",
      label: "MCP",
      icon: "🔌",
      desc: "Model Context Protocol 服务",
      unavailable:
        "运行时尚未接入 MCP 客户端：没有服务清单、没有连接管理，也没有可调用的 MCP 工具。",
    },
    {
      id: "cot",
      label: "CoT",
      icon: "🧠",
      desc: "显式思维链策略",
      unavailable:
        "运行时尚未实现 CoT 策略层：无法配置、无法选择，对话里也不会出现思维链开关。",
    },
    {
      id: "orbiter",
      label: "Orbiter",
      icon: "🛰",
      desc: "调用其它 AI 的中继",
      unavailable:
        "运行时尚未实现 Orbiter 中继：输入框里的 Orbiter 开关只是预留 UI，不会发起任何跨 AI 调用。",
    },
  ];

  // 自有能力的分类展示顺序；MOD 声明的分类排在其后（按名称排序）
  const BUILTIN_CATEGORY_ORDER = ["CoT", "办公", "代码", "通讯", "创意", "检索", "自动化", "实验性", "其他"];
  const MOD_DEFAULT_CATEGORY = "其他";

  // 方块 logo：web/static/sprites/bricks 下的白色单色图，用 CSS mask 着色。
  const BRICK_BASE = "/static/sprites/bricks/";
  const BRICK_RULES = [
    [/readfile|read-file|read_file/i, "readFile.png"],
    [/screenshot|recognition/i, "screenshotRecognition.png"],
    [/websearch|web-search|web_search|search/i, "webSearch.png"],
    [/digest|automation|flow|cron/i, "plan.png"],
    [/netrunner|code|coding|codegen/i, "netrunner.png"],
  ];

  const state = {
    open: false,
    tab: "grid",
    cat: "blocks",
    query: "",
    selected: null,
    loading: false,
    loadedAt: 0,
    data: { blocks: null, skills: null, automation: null },
    loadPromise: null,
    lastFocus: null,
    deployBusy: null,
    deployNote: "",
  };

  const refs = {};

  function q(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function fetchJson(path) {
    const resp = await fetch(path, { headers: { Accept: "application/json" } });
    let data = null;
    try {
      data = await resp.json();
    } catch (_) {
      /* 非 JSON */
    }
    if (!resp.ok) {
      const message = (data && (data.error || data.reason || data.message)) || "请求失败（HTTP " + resp.status + "）";
      throw new Error(message);
    }
    return data;
  }

  function catById(id) {
    return CATEGORIES.find((c) => c.id === id) || CATEGORIES[0];
  }

  function brickFor(item) {
    const haystack = [item.id, item.name, item.type].join(" ");
    for (const [re, file] of BRICK_RULES) {
      if (re.test(haystack)) return BRICK_BASE + file;
    }
    // 自动化流程统一用 plan；技能没有对应方块时退回单色符号，不借用别人图标。
    return item.cat === "automation" ? BRICK_BASE + "plan.png" : "";
  }

  function brickHtml(item) {
    const src = brickFor(item);
    if (!src) return '<span class="inv-brick-fallback" aria-hidden="true">✦</span>';
    return '<i class="inv-brick" style="--brick:url(\'' + src + '\')" aria-hidden="true"></i>';
  }

  function normalize(raw, catId) {
    return {
      cat: catId,
      id: raw.id || "",
      name: raw.name || raw.id || "未命名",
      version: raw.version || "",
      desc: raw.description || "",
      // blocks 的开关语义是「已装备」，其余分类是「已启用」
      enabled: catId === "blocks" ? raw.equipped !== false : raw.enabled !== false,
      status: raw.status || "ok",
      hooks: Array.isArray(raw.hooks) ? raw.hooks : [],
      type: raw.type || "",
      risk: raw.risk || "",
      category: raw.category || MOD_DEFAULT_CATEGORY,
      // blocks 区分自有 / MOD；其余分类没有这层语义
      source: raw.source || (catId === "blocks" ? "builtin" : ""),
      modId: raw.mod_id || "",
      flow: raw.flow || raw.automation || null,
    };
  }

  function catItems(catId) {
    const bucket = state.data[catId];
    return bucket && bucket.items ? bucket.items : [];
  }

  /* ---------------- 数据加载 ---------------- */

  function activeAgentId() {
    try {
      return localStorage.getItem("simchat.active_agent_id") || "";
    } catch (_) {
      return "";
    }
  }

  function loadData(force) {
    if (state.loadPromise) return state.loadPromise;
    if (!force && state.data.blocks && state.data.skills && state.data.automation) {
      return Promise.resolve();
    }
    state.loading = true;
    renderChrome();
    renderPane();

    const agentId = activeAgentId();
    const toolsPath =
      "/api/agent/tools?all=1" + (agentId ? "&agent_id=" + encodeURIComponent(agentId) : "");
    const blocksJob = fetchJson(toolsPath)
      .then((payload) => {
        if (!payload || payload.success === false) {
          throw new Error((payload && payload.error) || "能力清单不可用");
        }
        const items = ((payload.tools) || [])
          .filter((item) => item && item.name)
          .map((item) =>
            normalize(Object.assign({}, item, { id: item.name, type: "block" }), "blocks")
          );
        state.data.blocks = {
          items,
          error: null,
          equipped: Array.isArray(payload.equipped) ? payload.equipped : null,
          agentId,
        };
      })
      .catch((error) => {
        state.data.blocks = {
          items: [],
          error: error.message,
          equipped: null,
          agentId,
        };
      });

    const skillsJob = fetchJson("/api/console/skills")
      .then((payload) => {
        if (!payload || payload.available === false) {
          throw new Error((payload && payload.reason) || "技能索引不可用");
        }
        const items = ((payload.data && payload.data.items) || [])
          .filter((item) => (item.type || "") !== "automation")
          .map((item) => normalize(item, "skills"));
        state.data.skills = { items, error: null };
      })
      .catch((error) => {
        state.data.skills = { items: [], error: error.message };
      });

    const automationJob = fetchJson("/api/console/automation")
      .then((payload) => {
        if (!payload || payload.available === false) {
          throw new Error((payload && payload.reason) || "自动化接口不可用");
        }
        const items = ((payload.data && payload.data.items) || []).map((item) => normalize(item, "automation"));
        state.data.automation = { items, error: null };
      })
      .catch((error) => {
        state.data.automation = { items: [], error: error.message };
      });

    state.loadPromise = Promise.all([blocksJob, skillsJob, automationJob]).then(() => {
      state.loading = false;
      state.loadPromise = null;
      state.loadedAt = Date.now();
      renderAll();
    });
    return state.loadPromise;
  }

  /* ---------------- 渲染：外框 ---------------- */

  function renderChrome() {
    renderRail();
    renderHeaderSummary();
    renderFooter();
  }

  function renderRail() {
    if (!refs.cats) return;
    refs.cats.innerHTML = CATEGORIES.map((cat) => {
      const active = cat.id === state.cat;
      const off = Boolean(cat.unavailable);
      let countHtml = "";
      if (off) {
        countHtml = '<span class="inv-cat-off">未接入</span>';
      } else if (state.loading && !state.data[cat.id]) {
        countHtml = '<span class="inv-cat-count">…</span>';
      } else {
        const total = catItems(cat.id).length;
        countHtml = '<span class="inv-cat-count">' + total + "</span>";
      }
      return (
        '<button type="button" class="inv-cat' +
        (active ? " is-active" : "") +
        (off ? " is-off" : "") +
        '" data-inv-cat="' + cat.id + '" role="tab" aria-selected="' + (active ? "true" : "false") +
        '" aria-label="' + escapeHtml(cat.label) + (off ? "（未接入）" : "") + '">' +
        '<span class="inv-cat-icon">' + cat.icon + "</span>" +
        '<span class="inv-cat-label">' + escapeHtml(cat.label) + "</span>" +
        countHtml +
        "</button>"
      );
    }).join("");
  }

  function renderHeaderSummary() {
    if (!refs.headSub) return;
    const parts = [];
    CATEGORIES.forEach((cat) => {
      if (cat.unavailable) return;
      if (state.data[cat.id]) parts.push(cat.label + " " + catItems(cat.id).length);
    });
    const offCount = CATEGORIES.filter((c) => c.unavailable).length;
    let text = state.loading && !parts.length ? "正在读取能力清单…" : parts.join(" · ");
    if (offCount) text += (text ? " · " : "") + offCount + " 类未接入";
    refs.headSub.textContent = text || "暂无能力数据";
  }

  function renderFooter() {
    if (!refs.footHint) return;
    if (state.selected) {
      const item = findItem(state.selected);
      if (item) {
        refs.footHint.textContent =
          "已选中：" + item.name + " · " + item.id +
          (item.version ? " · v" + item.version : "") +
          (item.hooks.length ? " · hooks: " + item.hooks.join(", ") : "");
        return;
      }
    }
    refs.footHint.textContent = "悬停查看详情 · I 开关面板 · Esc 关闭 · Tab 在分类与条目间移动 · Enter 选中";
  }

  function renderTabs() {
    if (!refs.tabs) return;
    refs.tabs.querySelectorAll("[data-inv-tab]").forEach((btn) => {
      const active = btn.dataset.invTab === state.tab;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function showPane(tab) {
    if (refs.panes) {
      refs.panes.forEach((pane) => {
        pane.classList.toggle("hidden", pane.dataset.pane !== tab);
      });
    }
  }

  function renderAll() {
    renderChrome();
    renderTabs();
    showPane(state.tab);
    renderPane();
  }

  function renderPane() {
    if (state.tab === "search") renderSearch();
    else if (state.tab === "deploy") renderDeploy();
    else renderGrid();
  }

  /* ---------------- 渲染：物品栏 ---------------- */

  function findItem(id) {
    for (const cat of CATEGORIES) {
      const hit = catItems(cat.id).find((item) => item.id === id);
      if (hit) return hit;
    }
    return null;
  }

  function englishName(item) {
    const match = String(item.name || "").trim().match(/^[A-Za-z][A-Za-z0-9._-]*/);
    return match ? match[0] : item.id || item.name || "Unnamed";
  }

  function slotHtml(item) {
    const name = englishName(item);
    return (
      '<button type="button" class="inv-slot' +
      (state.selected === item.id ? " is-selected" : "") +
      (item.enabled ? "" : " is-off") +
      '" data-inv-item="' + escapeHtml(item.id) + '" data-inv-cat="' + item.cat + '"' +
      ' role="listitem" aria-label="' + escapeHtml(name) + '">' +
      '<span class="inv-slot-icon">' + brickHtml(item) + "</span>" +
      '<span class="inv-slot-body">' +
      '<span class="inv-slot-name"><span class="inv-slot-name-text">' + escapeHtml(name) + "</span></span>" +
      '<span class="inv-slot-desc">' + escapeHtml(item.desc || "没有描述") + "</span>" +
      "</span></button>"
    );
  }

  /* ---------------- 悬停详情 ---------------- */

  function tooltipHtml(item) {
    const name = englishName(item);
    const dotClass = item.status === "err" ? "err" : item.enabled ? "on" : "off";
    const status = item.status === "err"
      ? "异常"
      : item.cat === "blocks"
        ? (item.enabled ? "已装备" : "未装备")
        : (item.enabled ? "已启用" : "已停用");
    return (
      '<div class="inv-tooltip-name">' + escapeHtml(name) + "</div>" +
      (item.name && item.name !== name
        ? '<div class="inv-tooltip-full-name">' + escapeHtml(item.name) + "</div>"
        : "") +
      '<div class="inv-tooltip-desc">' + escapeHtml(item.desc || "没有描述") + "</div>" +
      '<div class="inv-tooltip-meta">' +
      '<div class="inv-tooltip-row"><span>ID</span><code>' + escapeHtml(item.id) + "</code></div>" +
      '<div class="inv-tooltip-row"><span>版本</span><span>' +
      (item.version ? "v" + escapeHtml(item.version) : "—") + "</span></div>" +
      (item.risk
        ? '<div class="inv-tooltip-row"><span>风险</span><span>' + escapeHtml(item.risk) + "</span></div>"
        : "") +
      (item.cat === "blocks"
        ? '<div class="inv-tooltip-row"><span>分类</span><span>' +
          escapeHtml((item.source === "mod" ? "MOD · " : "自有 · ") + item.category) + "</span></div>"
        : "") +
      (item.modId
        ? '<div class="inv-tooltip-row"><span>来源</span><code>' + escapeHtml(item.modId) + "</code></div>"
        : "") +
      '<div class="inv-tooltip-row"><span>状态</span><span class="inv-tooltip-status">' +
      '<span class="inv-dot ' + dotClass + '"></span>' + status + "</span></div>" +
      (item.hooks.length
        ? '<div class="inv-tooltip-row"><span>Hooks</span><code>' + escapeHtml(item.hooks.join(", ")) + "</code></div>"
        : "") +
      "</div>"
    );
  }

  function showTooltip(slot) {
    if (!refs.tooltip || !slot) return;
    const item = findItem(slot.dataset.invItem);
    if (!item) return;
    hideTooltip();
    refs.tooltipSlot = slot;
    refs.tooltip.innerHTML = tooltipHtml(item);
    refs.tooltip.hidden = false;
    slot.setAttribute("aria-describedby", "inv-tooltip");
    positionTooltip(slot);
  }

  function positionTooltip(slot) {
    if (!refs.tooltip || refs.tooltip.hidden) return;
    const rect = slot.getBoundingClientRect();
    const width = refs.tooltip.offsetWidth;
    const height = refs.tooltip.offsetHeight;
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const margin = 12;
    const gap = 10;
    let left = rect.right + gap;
    let top = rect.top;

    if (left + width > viewportWidth - margin) left = rect.left - width - gap;
    if (left < margin) {
      left = Math.max(margin, Math.min(rect.left, viewportWidth - width - margin));
      top = rect.bottom + gap;
    }
    top = Math.max(margin, Math.min(top, viewportHeight - height - margin));
    refs.tooltip.style.left = Math.round(left) + "px";
    refs.tooltip.style.top = Math.round(top) + "px";
  }

  function hideTooltip() {
    if (refs.tooltipSlot) refs.tooltipSlot.removeAttribute("aria-describedby");
    refs.tooltipSlot = null;
    if (refs.tooltip) {
      refs.tooltip.hidden = true;
      refs.tooltip.innerHTML = "";
    }
  }

  function showState(icon, title, desc, extraHtml) {
    if (!refs.grid || !refs.state) return;
    refs.grid.hidden = true;
    refs.grid.innerHTML = "";
    refs.state.classList.remove("hidden");
    refs.state.innerHTML =
      '<div class="inv-state-icon">' + icon + "</div>" +
      '<div class="inv-state-title">' + escapeHtml(title) + "</div>" +
      (desc ? '<div class="inv-state-desc">' + escapeHtml(desc) + "</div>" : "") +
      (extraHtml || "");
  }

  function hideState() {
    if (!refs.state) return;
    refs.state.classList.add("hidden");
    refs.state.innerHTML = "";
    if (refs.grid) refs.grid.hidden = false;
  }

  function categoryRank(name) {
    const index = BUILTIN_CATEGORY_ORDER.indexOf(name);
    return index === -1 ? BUILTIN_CATEGORY_ORDER.length : index;
  }

  function groupByCategory(items) {
    const map = new Map();
    items.forEach((item) => {
      const key = item.category || MOD_DEFAULT_CATEGORY;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    });
    return Array.from(map.entries())
      .sort((a, b) => {
        const rank = categoryRank(a[0]) - categoryRank(b[0]);
        return rank !== 0 ? rank : a[0].localeCompare(b[0], "zh-Hans-CN");
      })
      .map(([label, list]) => ({ label, items: list }));
  }

  function subsectionHtml(label, items) {
    return (
      '<div class="inv-subsection">' +
      '<div class="inv-subsection-head"><span>' + escapeHtml(label) + "</span>" +
      '<span class="inv-subsection-count">' + items.length + "</span></div>" +
      '<div class="inv-subgrid">' + items.map(slotHtml).join("") + "</div>" +
      "</div>"
    );
  }

  function blockSectionHtml(title, items) {
    if (!items.length) return "";
    return (
      '<div class="inv-block-section">' +
      '<div class="inv-block-section-head">' +
      '<span class="inv-block-section-title">' + escapeHtml(title) + "</span>" +
      '<span class="inv-block-section-count">' + items.length + "</span>" +
      '<span class="inv-group-line"></span></div>' +
      groupByCategory(items).map((g) => subsectionHtml(g.label, g.items)).join("") +
      "</div>"
    );
  }

  /* 原子能力两级结构：自有能力（按功能分类） + MOD 能力（按 MOD 声明的分类） */
  function blockSectionsHtml(items) {
    const owned = items.filter((item) => item.source !== "mod");
    const modded = items.filter((item) => item.source === "mod");
    return blockSectionHtml("自有能力", owned) + blockSectionHtml("MOD 能力", modded);
  }

  function renderGrid() {
    hideTooltip();
    const cat = catById(state.cat);
    if (refs.toolbarTitle) refs.toolbarTitle.textContent = cat.label;
    if (refs.toolbarDesc) refs.toolbarDesc.textContent = cat.desc;

    if (cat.unavailable) {
      showState("🚧", cat.label + " 尚未接入",
        cat.unavailable,
        '<span class="inv-state-tag">未接入 · 不提供占位开关</span>');
      return;
    }

    const bucket = state.data[cat.id];
    if (!bucket) {
      showState("⏳", "正在读取…", state.loading ? "从 " + cat.endpoint + " 获取清单" : "");
      return;
    }
    if (bucket.error) {
      showState("⚠️", cat.label + " 加载失败", bucket.error,
        '<button type="button" class="inv-state-retry" data-inv-retry="1">重试</button>');
      return;
    }
    if (!bucket.items.length) {
      showState("🗃", "这一类暂时是空的",
        "接口 " + cat.endpoint + " 正常工作，只是本次扫描没有发现条目。");
      return;
    }

    hideState();
    if (cat.id === "blocks") {
      refs.grid.classList.add("is-grouped");
      refs.grid.innerHTML = blockSectionsHtml(bucket.items);
    } else {
      refs.grid.classList.remove("is-grouped");
      refs.grid.innerHTML = bucket.items.map(slotHtml).join("");
    }
  }

  /* ---------------- 渲染：搜索 ---------------- */

  function searchableText(item) {
    return [item.name, item.id, item.desc, item.version, item.hooks.join(" "), item.type,
      item.category, item.source, item.modId]
      .join(" ")
      .toLowerCase();
  }

  function renderSearch() {
    hideTooltip();
    if (!refs.searchInput) return;
    if (refs.searchInput.value !== state.query) refs.searchInput.value = state.query;
    const keyword = state.query.trim().toLowerCase();
    const available = CATEGORIES.filter((cat) => !cat.unavailable);

    if (!keyword) {
      refs.results.innerHTML =
        '<div class="inv-state">' +
        '<div class="inv-state-icon">🧭</div>' +
        '<div class="inv-state-title">跨分类搜索</div>' +
        '<div class="inv-state-desc">输入名称、ID、描述或 hook 关键词，会在原子能力、技能与自动化里一起查找。' +
        "MCP / CoT / Orbiter 尚未接入，不参与搜索。</div>" +
        "</div>";
      return;
    }

    let total = 0;
    const groups = available.map((cat) => {
      if (!state.data[cat.id]) return "";
      const hits = catItems(cat.id).filter((item) => searchableText(item).includes(keyword));
      if (!hits.length) return "";
      total += hits.length;
      const body = cat.id === "blocks"
        ? blockSectionsHtml(hits)
        : '<div class="inv-grid">' + hits.map(slotHtml).join("") + "</div>";
      return (
        '<div class="inv-group">' +
        '<div class="inv-group-head"><span>' + cat.icon + " " + escapeHtml(cat.label) +
        " · " + hits.length + '</span><span class="inv-group-line"></span></div>' +
        body +
        "</div>"
      );
    }).filter(Boolean).join("");

    if (!total) {
      refs.results.innerHTML =
        '<div class="inv-state">' +
        '<div class="inv-state-icon">🫥</div>' +
        '<div class="inv-state-title">没有匹配的能力</div>' +
        '<div class="inv-state-desc">换个关键词试试：可以搜名称、ID、描述或 hook（如 agent.block）。</div>' +
        "</div>";
      return;
    }

    refs.results.innerHTML =
      '<div class="inv-group-head" style="margin-bottom:8px"><span>共 ' + total +
      ' 项匹配</span><span class="inv-group-line"></span></div>' +
      groups +
      '<div class="inv-search-note">搜索范围：原子能力 ' + catItems("blocks").length +
      " 项 · 技能 " + catItems("skills").length +
      " 项 · 自动化 " + catItems("automation").length +
      " 项。MCP / CoT / Orbiter 未接入，未参与搜索。</div>";
  }

  /* ---------------- 渲染：部署（启用入口） ---------------- */

  function deployRow(item, busy) {
    const typeLabel =
      item.cat === "automation" ? "自动化"
        : item.cat === "blocks"
          ? "原子能力 · " + (item.category || MOD_DEFAULT_CATEGORY)
          : item.type === "binary" ? "Binary" : "Skill";
    const action = item.cat === "blocks"
      ? (item.enabled ? "卸下 " : "装备 ")
      : (item.enabled ? "停用 " : "启用 ");
    return (
      '<div class="inv-deploy-row' + (item.enabled ? "" : " is-off") + '">' +
      '<span class="inv-deploy-icon">' + brickHtml(item) + "</span>" +
      '<span class="inv-deploy-body">' +
      '<span class="inv-deploy-name">' + escapeHtml(item.name) +
      (item.version ? '<span class="inv-slot-ver">v' + escapeHtml(item.version) + "</span>" : "") +
      '<span class="inv-deploy-type">' + escapeHtml(typeLabel) + "</span>" +
      "</span>" +
      '<span class="inv-deploy-desc">' + escapeHtml(item.desc || "没有描述") + "</span>" +
      '<span class="inv-deploy-id">' + escapeHtml(item.id) + "</span>" +
      "</span>" +
      '<button type="button" class="mod-switch' + (item.enabled ? " on" : "") + '"' +
      ' data-inv-toggle="' + escapeHtml(item.id) + '" role="switch" aria-checked="' +
      (item.enabled ? "true" : "false") + '" aria-label="' +
      action + escapeHtml(item.name) + '"' +
      (busy ? " disabled" : "") + '><span class="mod-switch-knob"></span></button>' +
      "</div>"
    );
  }

  function renderDeploy() {
    if (!refs.deploy) return;
    const available = CATEGORIES.filter((cat) => !cat.unavailable);
    if (state.loading && !state.data.blocks && !state.data.skills && !state.data.automation) {
      refs.deploy.innerHTML =
        '<div class="inv-state"><div class="inv-state-icon">⏳</div>' +
        '<div class="inv-state-title">正在读取可部署能力…</div></div>';
      return;
    }

    const groups = available.map((cat) => {
      const bucket = state.data[cat.id];
      if (!bucket || !bucket.items.length) return "";
      return (
        '<div class="inv-group">' +
        '<div class="inv-group-head"><span>' + cat.icon + " " + escapeHtml(cat.label) +
        " · " + bucket.items.length + '</span><span class="inv-group-line"></span></div>' +
        bucket.items.map((item) => deployRow(item, state.deployBusy === item.id)).join("") +
        "</div>"
      );
    }).filter(Boolean).join("");

    const rows = available.reduce((sum, cat) => sum + catItems(cat.id).length, 0);
    const enabled = available.reduce(
      (sum, cat) => sum + catItems(cat.id).filter((item) => item.enabled).length, 0
    );
    const errors = available
      .map((cat) => (state.data[cat.id] && state.data[cat.id].error) || "")
      .filter(Boolean);

    if (!rows) {
      refs.deploy.innerHTML =
        '<div class="inv-state"><div class="inv-state-icon">📦</div>' +
        '<div class="inv-state-title">暂无可部署的能力</div>' +
        '<div class="inv-state-desc">原子能力、技能与自动化清单为空，或接口读取失败。</div>' +
        (errors.length ? '<span class="inv-state-tag">' + escapeHtml(errors[0]) + "</span>" : "") +
        "</div>";
      return;
    }

    refs.deploy.innerHTML =
      '<div class="inv-deploy-bar">' +
      '<span class="inv-deploy-stats">可部署 ' + rows + " 项 · 已开启 " + enabled + " 项</span>" +
      '<span class="inv-deploy-note" id="inv-deploy-note">' +
      escapeHtml(state.deployNote || "技能/自动化重启后生效；原子能力下一次运行生效") +
      "</span></div>" +
      groups +
      '<div class="inv-deploy-install">' +
      '<div class="inv-deploy-install-title">安装新的能力包</div>' +
      '<div class="inv-deploy-install-desc">运行时目前没有安装 / 上传 MOD 包的接口，这里只做启用开关。' +
      "安装入口需要后端补接口后再接入。</div>" +
      '<span class="inv-state-tag">缺少接口 · 暂不可安装</span>' +
      "</div>";
  }

  function equippedList() {
    const bucket = state.data.blocks;
    if (!bucket) return [];
    if (Array.isArray(bucket.equipped)) return bucket.equipped.slice();
    // 旧实例 equipped=null 表示「全部装备」，首次修改时物化为显式清单
    return bucket.items.map((item) => item.id);
  }

  async function toggleEquip(item) {
    const agentId = activeAgentId();
    if (!agentId) throw new Error("没有激活的 AI 实例，无法修改装备");
    const current = equippedList();
    const next = item.enabled
      ? current.filter((name) => name !== item.id)
      : current.concat(item.id);
    const resp = await fetch("/api/agents/" + encodeURIComponent(agentId), {
      method: "PUT",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ equipped: Array.from(new Set(next)) }),
    });
    const payload = await resp.json().catch(() => null);
    if (!resp.ok || (payload && payload.error)) {
      throw new Error((payload && payload.error) || "HTTP " + resp.status);
    }
    state.data.blocks.equipped = Array.from(new Set(next));
    item.enabled = !item.enabled;
    state.deployNote =
      "已" + (item.enabled ? "装备 " : "卸下 ") + item.name + "（下一次运行生效）";
  }

  async function toggleCapability(id) {
    if (state.deployBusy) return;
    const item = findItem(id);
    if (!item) return;
    state.deployBusy = id;
    renderDeploy();
    try {
      if (item.cat === "blocks") {
        await toggleEquip(item);
      } else {
        const endpoint = item.cat === "automation"
          ? "/api/console/automation/" + encodeURIComponent(id) + "/toggle"
          : "/api/console/skills/" + encodeURIComponent(id) + "/toggle";
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ enabled: !item.enabled }),
        });
        const payload = await resp.json().catch(() => null);
        if (!resp.ok || (payload && payload.ok === false)) {
          throw new Error((payload && (payload.error || payload.reason)) || "HTTP " + resp.status);
        }
        item.enabled = !item.enabled;
        state.deployNote = "已" + (item.enabled ? "启用 " : "停用 ") + item.name + "（重启后生效）";
      }
    } catch (error) {
      state.deployNote = "操作失败：" + error.message;
    } finally {
      state.deployBusy = null;
      renderDeploy();
      renderGrid();
      renderFooter();
    }
  }

  /* ---------------- 开关与焦点 ---------------- */

  function isEditable(target) {
    if (!target) return false;
    const tag = (target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable === true;
  }

  function focusables() {
    if (!refs.frame) return [];
    return Array.from(
      refs.frame.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((node) => node.offsetParent !== null);
  }

  function open() {
    if (state.open || !refs.overlay) return;
    state.open = true;
    state.lastFocus = document.activeElement;
    refs.overlay.classList.add("is-open");
    refs.overlay.setAttribute("aria-hidden", "false");
    renderTabs();
    showPane(state.tab);
    renderChrome();
    renderPane();
    loadData(false);
    if (refs.frame) {
      refs.frame.focus({ preventScroll: true });
    }
  }

  function close() {
    if (!state.open || !refs.overlay) return;
    hideTooltip();
    state.open = false;
    refs.overlay.classList.remove("is-open");
    refs.overlay.setAttribute("aria-hidden", "true");
    const back = state.lastFocus;
    state.lastFocus = null;
    if (back && typeof back.focus === "function" && document.contains(back)) {
      back.focus({ preventScroll: true });
    }
  }

  function toggle() {
    if (state.open) close();
    else open();
  }

  function selectItem(id) {
    state.selected = state.selected === id ? null : id;
    if (refs.grid) {
      refs.grid.querySelectorAll("[data-inv-item]").forEach((node) => {
        node.classList.toggle("is-selected", node.dataset.invItem === state.selected);
      });
    }
    if (refs.overlay) {
      refs.overlay.querySelectorAll(".inv-results [data-inv-item]").forEach((node) => {
        node.classList.toggle("is-selected", node.dataset.invItem === state.selected);
      });
    }
    renderFooter();
  }

  function switchTab(tab) {
    if (!tab || tab === state.tab) return;
    state.tab = tab;
    renderTabs();
    showPane(tab);
    renderPane();
    if (tab === "search") {
      const input = refs.searchInput;
      if (input) {
        input.value = state.query;
        input.focus({ preventScroll: true });
      }
    } else if (refs.frame) {
      refs.frame.focus({ preventScroll: true });
    }
  }

  function switchCat(catId) {
    const cat = catById(catId);
    state.cat = cat.id;
    state.selected = null;
    renderRail();
    renderFooter();
    if (cat.unavailable) {
      if (refs.toolbarTitle) refs.toolbarTitle.textContent = cat.label;
      if (refs.toolbarDesc) refs.toolbarDesc.textContent = cat.desc;
      renderGrid();
      return;
    }
    renderGrid();
  }

  /* ---------------- 事件 ---------------- */

  function bind() {
    refs.overlay = q("inv-panel");
    if (!refs.overlay) return;
    refs.frame = q("inv-frame");
    refs.cats = q("inv-cats");
    refs.tabs = q("inv-tabs");
    refs.grid = q("inv-grid");
    refs.state = q("inv-state");
    refs.results = q("inv-results");
    refs.searchInput = q("inv-search");
    refs.deploy = q("inv-deploy");
    refs.headSub = q("inv-head-sub");
    refs.footHint = q("inv-foot-hint");
    refs.toolbarTitle = q("inv-toolbar-title");
    refs.toolbarDesc = q("inv-toolbar-desc");
    refs.tooltip = q("inv-tooltip");
    refs.tooltipSlot = null;
    refs.panes = Array.from(refs.overlay.querySelectorAll("[data-pane]"));

    q("inv-close").addEventListener("click", close);
    q("inv-refresh").addEventListener("click", () => loadData(true));

    refs.overlay.addEventListener("click", (event) => {
      if (event.target === refs.overlay) {
        close();
        return;
      }
      const tabBtn = event.target.closest("[data-inv-tab]");
      if (tabBtn) {
        switchTab(tabBtn.dataset.invTab);
        return;
      }
      const catBtn = event.target.closest(".inv-cats [data-inv-cat]");
      if (catBtn) {
        switchCat(catBtn.dataset.invCat);
        return;
      }
      const itemBtn = event.target.closest("[data-inv-item]");
      if (itemBtn) {
        selectItem(itemBtn.dataset.invItem);
        return;
      }
      const toggleBtn = event.target.closest("[data-inv-toggle]");
      if (toggleBtn) {
        toggleCapability(toggleBtn.dataset.invToggle);
        return;
      }
      if (event.target.closest("[data-inv-retry]")) {
        loadData(true);
      }
    });

    refs.overlay.addEventListener("pointerover", (event) => {
      const slot = event.target.closest("[data-inv-item]");
      if (!slot || (event.relatedTarget && slot.contains(event.relatedTarget))) return;
      showTooltip(slot);
    });

    refs.overlay.addEventListener("pointerout", (event) => {
      const slot = event.target.closest("[data-inv-item]");
      if (!slot || (event.relatedTarget && slot.contains(event.relatedTarget))) return;
      hideTooltip();
    });

    refs.overlay.addEventListener("focusin", (event) => {
      const slot = event.target.closest("[data-inv-item]");
      if (slot) showTooltip(slot);
    });

    refs.overlay.addEventListener("focusout", (event) => {
      const slot = event.target.closest("[data-inv-item]");
      if (!slot || (event.relatedTarget && slot.contains(event.relatedTarget))) return;
      hideTooltip();
    });

    refs.overlay.addEventListener("scroll", hideTooltip, true);
    window.addEventListener("resize", hideTooltip);

    refs.searchInput.addEventListener("input", () => {
      state.query = refs.searchInput.value;
      renderSearch();
    });

    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key === "Escape" && state.open) {
          event.preventDefault();
          event.stopPropagation();
          close();
          return;
        }
        const key = event.key;
        if (
          (key === "i" || key === "I") &&
          !event.ctrlKey && !event.metaKey && !event.altKey &&
          !event.isComposing && !event.repeat &&
          !isEditable(event.target)
        ) {
          event.preventDefault();
          event.stopPropagation();
          toggle();
          return;
        }
        if (!state.open || key !== "Tab") return;
        const nodes = focusables();
        if (!nodes.length) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
      },
      true
    );
  }

  window.SimChatInventory = {
    open,
    close,
    toggle,
    isOpen: () => state.open,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
