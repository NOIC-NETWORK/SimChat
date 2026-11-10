/* ========================================================
   SimChat IDE · API 封装层
   为 ide.js / wap.js 提供统一的 fetch + SSE 工具
   所有请求都显式带 Content-Type: application/json
   ======================================================== */
(function () {
  "use strict";

  const API = {
    /** 通用 fetch JSON */
    async json(method, path, body) {
      const opts = {
        method,
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
      };
      if (body !== undefined) opts.body = JSON.stringify(body);
      const resp = await fetch(path, opts);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const err = new Error(data.error || `HTTP ${resp.status}`);
        err.status = resp.status;
        err.code = data.code;
        err.body = data;
        throw err;
      }
      return data;
    },

    /** GET 快捷 */
    get(path) { return API.json("GET", path); },
    post(path, body) { return API.json("POST", path, body); },
    put(path, body) { return API.json("PUT", path, body); },
    del(path) { return API.json("DELETE", path); },

    /** ===== 会话 ===== */
    listSessions() { return API.get("/api/sessions").then((r) => r.sessions || []); },
    createSession() { return API.post("/api/sessions").then((r) => r.session); },
    getSession(sid) { return API.get(`/api/sessions/${sid}`).then((r) => r.session); },
    deleteSession(sid) { return API.del(`/api/sessions/${sid}`); },

    /** ===== 工作目录 ===== */
    getWorkspace() { return API.get("/api/workspace").then((r) => r.workspace); },
    setWorkspace(path) { return API.post("/api/workspace", { path }).then((r) => r.workspace); },
    clearWorkspace() { return API.del("/api/workspace").then((r) => r.workspace); },
    browseWorkspace(path) {
      const qs = path ? "?path=" + encodeURIComponent(path) : "";
      return API.get("/api/workspace/browse" + qs);
    },

    /** ===== 设置 ===== */
    getSettings() { return API.get("/api/settings"); },
    saveSettings(patch) { return API.post("/api/settings", patch); },

    /** ===== 服务商 ===== */
    listProviders() { return API.get("/api/providers"); },
    saveProvider(provider, config, activate) {
      return API.post("/api/providers", { provider, config, activate: activate !== false });
    },
    testProvider(provider, config) { return API.post("/api/providers/test", { provider, config }); },
    discoverProvider(provider, config) { return API.post("/api/providers/discover", { provider, config }); },

    /** ===== Agent ===== */
    listAgentTasks() { return API.get("/api/agent/tasks").then((r) => r.tasks || r.runs || []); },
    agentTools() { return API.get("/api/agent/tools").then((r) => r.tools || []); },
    approveAgent(payload) { return API.post("/api/agent/approve", payload); },
    abortAgent(payload) { return API.post("/api/agent/abort", payload); },

    /** ===== MOD / 技能 ===== */
    listMods() { return API.get("/api/console/mods").then((r) => r.mods || []); },
    toggleMod(modId, enabled) { return API.post(`/api/console/mods/${modId}/toggle`, { enabled }); },
    listSkills() { return API.get("/api/console/skills").then((r) => r.skills || []); },

    /** ===== 用量 ===== */
    getUsage() { return API.get("/api/console/usage"); },

    /** ===== 对话 SSE ===== */
    /**
     * 发起流式对话（POST /api/chat），逐事件回调
     * @param {Object} payload { message, session_id, mode, model, ... }
     * @param {Function} onEvent 每收到一个 SSE 事件行时回调 (eventName, data) => void
     *   其中 data 是已解析的 JSON 对象（SSE 格式：data: {...}\n\n）
     * @returns {Promise<{session_id, final_text}>} 流结束后 resolve
     */
    async chatStream(payload, onEvent) {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const err = new Error(data.error || `HTTP ${resp.status}`);
        err.status = resp.status;
        err.code = data.code;
        throw err;
      }
      if (!resp.body) throw new Error("浏览器不支持 ReadableStream");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sessionId = payload.session_id;
      let finalText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 按 SSE 分隔符 \n\n 切事件
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          // 取 data: 行
          const lines = chunk.split("\n");
          let dataLine = "";
          let eventName = "message";
          for (const line of lines) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
          }
          if (!dataLine) continue;
          let parsed;
          try { parsed = JSON.parse(dataLine); } catch { parsed = { text: dataLine }; }

          if (parsed.session_id) sessionId = parsed.session_id;
          if (parsed.text) finalText += parsed.text;
          if (onEvent) onEvent(eventName, parsed);
        }
      }
      return { session_id: sessionId, final_text: finalText };
    },

    /** Agent SSE — POST /api/agent/run，事件回调同 chatStream */
    async agentRun(payload, onEvent) {
      const resp = await fetch("/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const err = new Error(data.error || `HTTP ${resp.status}`);
        err.status = resp.status;
        err.code = data.code;
        throw err;
      }
      if (!resp.body) throw new Error("浏览器不支持 ReadableStream");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const lines = chunk.split("\n");
          let dataLine = "";
          let eventName = "agent.event";
          for (const line of lines) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
          }
          if (!dataLine) continue;
          let parsed;
          try { parsed = JSON.parse(dataLine); } catch { parsed = { text: dataLine }; }
          if (onEvent) onEvent(eventName, parsed);
        }
      }
      return;
    },
  };

  window.SimChatAPI = API;
})();
