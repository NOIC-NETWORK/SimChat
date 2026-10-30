# -*- coding: utf-8 -*-
"""Agent 模式 Web 蓝图：把 runtime/agent 的 ReAct 循环接到 SimChat 本体。

端点（与 spec/events.md §1 对齐）：
  GET    /agent/tools
  POST   /agent/run
  POST   /agent/approve
  POST   /agent/abort
  GET    /agent/tasks
  DELETE /agent/tasks/<sid>

蓝图同时注册在 `/api/agent` 与 `/api/simchat/agent` 两个前缀下：
前者与现有 `/api/chat`、`/api/sessions` 一致，后者兼容冻结的 Agent SSE fixture。

传输层（run_started / keepalive / 断连中止）在本模块；其余事件由 AgentLoop 发。
"""

import json
import queue
import threading

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    stream_with_context,
)

from simchat.runtime.agent import (
    AgentLoop,
    SimChatAgentBackend,
    agent_runs,
    configure_shell,
    discard_pending_state,
    list_agent_tools,
    load_pending_state,
    resolve_workdir,
    save_pending_state,
    ToolError,
)


def _get_core():
    from simchat.web import _get_core as get_core

    return get_core(current_app)


def _system_prompt(core, data, fallback=None):
    text = (data.get("system") or "").strip()
    if not text:
        try:
            text = (core.load_settings().get("system_prompt") or "").strip()
        except Exception:
            text = ""
    if not text:
        text = (fallback or "").strip()
    return text or None


def _make_backend(core, data, fallback=None):
    meta = fallback or {}
    return SimChatAgentBackend(
        core,
        provider=data.get("provider") or meta.get("provider"),
        model=data.get("model") or meta.get("model"),
        temperature=float(meta.get("temperature") or 0.7),
        max_tokens=int(meta.get("max_tokens") or 1024),
    )


def _sse_response(run_id, run_callable, ttl):
    """共享 SSE 运行器：worker 线程执行 run_callable(emit)，捕获挂起态并落盘。

    run_callable(emit) -> Optional[pending_state]：返回挂起态表示待审批，None 表示终结。
    """
    event_queue = queue.Queue()
    pending_holder = {"state": None}

    def emit(evt):
        event_queue.put(evt)

    def worker():
        try:
            pending_holder["state"] = run_callable(emit)
        except Exception as e:
            print(f"[Agent] 运行错误: {e}")
            emit({"event": "error", "message": f"Agent 运行异常: {e}"})
            pending_holder["state"] = None
        finally:
            state = pending_holder["state"]
            if state is None:
                discard_pending_state(run_id)
            else:
                save_pending_state(state, ttl=ttl)
            agent_runs.finish(run_id)
            event_queue.put(None)

    def generate():
        yield "data: " + json.dumps(
            {"event": "run_started", "run_id": run_id, "schema": 1}, ensure_ascii=False
        ) + "\n\n"
        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                try:
                    evt = event_queue.get(timeout=60)
                except queue.Empty:
                    # 长推理期间发送心跳注释行，防止连接被代理/浏览器掐断
                    yield ": keepalive\n\n"
                    continue
                if evt is None:
                    break
                yield "data: " + json.dumps(evt, ensure_ascii=False) + "\n\n"
        except GeneratorExit:
            # 客户端断开：中止任务（fail-closed）
            agent_runs.abort(run_id)
            raise
        finally:
            agent_runs.abort(run_id)  # 兜底：无论何种退出都让循环尽快停止
            agent_runs.remove(run_id)

    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


def create_agent_blueprint(name="agent"):
    bp = Blueprint(name, __name__)

    @bp.get("/tools")
    def agent_tools():
        """工具清单与风险分级（shell 的 enabled 反映当前配置）。"""
        core = _get_core()
        options = core.agent_options()
        configure_shell(options["shell_enabled"], options["shell_timeout"])
        return jsonify({"success": True, "tools": list_agent_tools()})

    @bp.post("/run")
    def agent_run():
        core = _get_core()
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "消息内容为空"}), 400
        if not core.has_available_provider():
            return jsonify({
                "error": "尚未配置可用的服务商，请先完成服务商配置。",
                "code": "provider_unavailable",
            }), 409

        # 模式："chat"（懒调用）| "agent"（完整 ReAct + 审批流）
        mode = (data.get("mode") or "agent").strip().lower()
        if mode not in ("chat", "agent"):
            mode = "agent"

        options = core.agent_options()
        try:
            workdir = resolve_workdir(data.get("workdir") or options["workdir"] or None)
        except ToolError as e:
            return jsonify({"error": str(e)}), 400

        run_id = agent_runs.create()
        history = data.get("history") or []
        session_id = (data.get("session_id") or "").strip() or ("agent_" + run_id[:12])
        system_prompt = _system_prompt(core, data)
        backend = _make_backend(core, data)
        max_turns = options["max_turns"]
        shell_enabled = options["shell_enabled"] if mode == "agent" else False
        shell_timeout = options["shell_timeout"]

        def run_callable(emit):
            configure_shell(shell_enabled, shell_timeout)
            run = agent_runs.get(run_id)
            loop = AgentLoop(
                backend,
                workdir=workdir,
                max_turns=max_turns,
                abort_event=run["abort"] if run else None,
                shell_enabled=shell_enabled,
                shell_timeout=shell_timeout,
                mode=mode,
            )
            return loop.run(
                message=message,
                history=history,
                session_id=session_id,
                run_id=run_id,
                system_prompt=system_prompt,
                emit=emit,
            )

        return _sse_response(run_id, run_callable, options["approval_ttl"])

    @bp.post("/approve")
    def agent_approve():
        """审批挂起的写操作并恢复 SSE 流。"""
        core = _get_core()
        data = request.get_json(silent=True) or {}
        run_id = (data.get("run_id") or "").strip()
        decision = (data.get("decision") or "").strip().lower()
        edits = data.get("edits")
        if not run_id:
            return jsonify({"error": "run_id 为空"}), 400
        if decision not in ("approve", "reject"):
            return jsonify({"error": "decision 必须为 'approve' 或 'reject'"}), 400
        if edits is not None and not isinstance(edits, dict):
            return jsonify({"error": "edits 必须为对象"}), 400

        options = core.agent_options()
        state = load_pending_state(run_id, ttl=options["approval_ttl"])
        if state is None:
            return jsonify({"error": "挂起态不存在或已过期（fail-closed），请重新发起任务"}), 410

        try:
            workdir = resolve_workdir(state.get("workdir") or options["workdir"] or None)
        except ToolError as e:
            return jsonify({"error": str(e)}), 400
        try:
            max_turns = int(state.get("max_turns") or options["max_turns"])
        except (TypeError, ValueError):
            max_turns = options["max_turns"]
        system_prompt = _system_prompt(core, data, fallback=state.get("system_prompt"))
        backend = _make_backend(core, data, fallback=state.get("backend"))
        shell_enabled = options["shell_enabled"]
        shell_timeout = options["shell_timeout"]

        # 复用 run_id 重新登记（新建 abort 事件，旧的已被原流程清理）
        agent_runs.register(run_id)

        # 模式：从 pending state 继承，或从请求/默认取
        mode = (data.get("mode") or state.get("mode") or "agent").strip().lower()
        if mode not in ("chat", "agent"):
            mode = "agent"

        def run_callable(emit):
            configure_shell(shell_enabled, shell_timeout)
            run = agent_runs.get(run_id)
            loop = AgentLoop(
                backend,
                workdir=workdir,
                max_turns=max_turns,
                abort_event=run["abort"] if run else None,
                shell_enabled=shell_enabled,
                shell_timeout=shell_timeout,
                mode=mode,
            )
            return loop.resume(state, decision, edits, system_prompt, emit=emit)

        return _sse_response(run_id, run_callable, options["approval_ttl"])

    @bp.post("/abort")
    def agent_abort():
        """中止运行（幂等）；挂起态同时清理，审批无法恢复。"""
        data = request.get_json(silent=True) or {}
        run_id = (data.get("run_id") or "").strip()
        if not run_id:
            return jsonify({"error": "run_id 为空"}), 400
        run = agent_runs.get(run_id)
        agent_runs.abort(run_id)
        discard_pending_state(run_id)
        return jsonify({"success": True, "run_id": run_id, "was_active": bool(run)})

    @bp.get("/tasks")
    def agent_tasks():
        """列出 agent_ 前缀的任务会话（按更新时间倒序）。"""
        core = _get_core()
        tasks = []
        for item in core.list_sessions():
            sid = item.get("id") or ""
            if not sid.startswith("agent_"):
                continue
            session = core.get_session(sid) or {}
            messages = session.get("messages") or []
            first_user = next(
                (m.get("content") or "" for m in messages if m.get("role") == "user"),
                "",
            )
            tasks.append({
                "session_id": sid,
                "message": (first_user or "")[:80],
                "message_count": len(messages),
                "title": session.get("title") or "",
                "mtime": int(session.get("updated_at") or 0),
            })
        tasks.sort(key=lambda t: t.get("mtime", 0), reverse=True)
        return jsonify({"success": True, "tasks": tasks})

    @bp.delete("/tasks/<path:sid>")
    def agent_task_delete(sid):
        """删除任务会话；仅允许 agent_ 前缀（防误删 Chat 会话）。"""
        if not sid.startswith("agent_"):
            return jsonify({"error": "非法 session_id（仅允许 agent_ 前缀）"}), 400
        core = _get_core()
        if not core.delete_session(sid):
            return jsonify({"error": "任务不存在"}), 404
        return jsonify({"success": True, "session_id": sid})

    return bp
