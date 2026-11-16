/* SimChat Web — header 导航入口快捷键
   物品栏 I / AI 实例 E / 网关 G / MOD 菜单 M / 设置 C
   仅在无修饰键、非输入态时生效；面板打开时同一按键可关闭。
   面板的开关复用 chat.js 暴露的 SimChatPanels，避免与既有 click 绑定重复触发。 */
(() => {
  "use strict";

  const ENTRIES = [
    { key: "i", nav: "mc-inventory", kind: "inventory", label: "物品栏" },
    { key: "e", nav: "mc-singleplayer", panel: "agent-list", label: "AI 实例" },
    { key: "g", nav: "mc-multiplayer", panel: "gateway-console", label: "网关" },
    { key: "m", nav: "mc-mods", panel: "mod-console", label: "MOD 菜单" },
    { key: "c", nav: "nav-settings", kind: "setup", label: "设置" },
  ];

  const returnFocus = new Map();

  function isEditable(target) {
    if (!target) return false;
    const tag = (target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable === true;
  }

  function panels() {
    return window.SimChatPanels || null;
  }

  function isOpen(entry) {
    if (entry.kind === "inventory") {
      return Boolean(window.SimChatInventory && window.SimChatInventory.isOpen());
    }
    if (entry.kind === "setup") {
      return Boolean(document.getElementById("setup")?.classList.contains("is-open"));
    }
    const api = panels();
    return Boolean(api && api.isOpen(entry.panel));
  }

  function openEntry(entry) {
    if (entry.kind === "inventory") {
      window.SimChatInventory?.open();
      return;
    }
    if (entry.kind === "setup") {
      document.getElementById("open-setup")?.click();
      return;
    }
    panels()?.open(entry.panel);
  }

  function closeEntry(entry) {
    if (entry.kind === "inventory") {
      window.SimChatInventory?.close();
      return;
    }
    if (entry.kind === "setup") {
      document.getElementById("setup-back")?.click();
      return;
    }
    panels()?.close(entry.panel);
  }

  function restoreFocus(entry) {
    const back = returnFocus.get(entry.key);
    returnFocus.delete(entry.key);
    if (back && document.contains(back) && back !== document.body) {
      back.focus({ preventScroll: true });
      return;
    }
    document.getElementById(entry.nav)?.focus({ preventScroll: true });
  }

  function closeOthers(exceptKey) {
    ENTRIES.forEach((entry) => {
      if (entry.key === exceptKey || !isOpen(entry)) return;
      closeEntry(entry);
    });
  }

  function toggleEntry(entry, fromShortcut) {
    if (isOpen(entry)) {
      closeEntry(entry);
      restoreFocus(entry);
      return;
    }
    closeOthers(entry.key);
    if (fromShortcut) returnFocus.set(entry.key, document.activeElement);
    openEntry(entry);
  }

  function bindClicks() {
    // 只接管本次新增的两个入口；AI 实例 / 网关 / MOD 的点击仍由 chat.js 既有监听处理
    ["mc-inventory", "nav-settings"].forEach((id) => {
      const entry = ENTRIES.find((item) => item.nav === id);
      const btn = document.getElementById(id);
      if (!entry || !btn) return;
      btn.addEventListener("click", () => toggleEntry(entry, false));
    });
  }

  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape") {
        // 物品栏、setup、settings-console 的 Esc 由各自的既有实现处理
        if (window.SimChatInventory && window.SimChatInventory.isOpen()) return;
        if (isOpen(ENTRIES.find((item) => item.kind === "setup"))) return;
        if (document.getElementById("settings-console")?.classList.contains("is-open")) return;
        const open = ENTRIES.find((entry) => entry.panel && isOpen(entry));
        if (open) {
          event.preventDefault();
          event.stopPropagation();
          closeEntry(open);
          restoreFocus(open);
        }
        return;
      }

      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (event.isComposing || event.repeat) return;
      if (isEditable(event.target)) return;

      const entry = ENTRIES.find((item) => item.key === event.key.toLowerCase());
      if (!entry || entry.kind === "inventory") return; // I 由 inventory.js 处理
      event.preventDefault();
      event.stopPropagation();
      toggleEntry(entry, true);
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindClicks);
  } else {
    bindClicks();
  }
})();
