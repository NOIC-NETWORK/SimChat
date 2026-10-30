"""SimChat Web — 本体独立对话的 Flask 外壳。

路由只做两件事：把 SessionStore 的会话 CRUD 暴露成 JSON，
把 SimChatCore.chat_stream() 的 SSE 事件原样转发给浏览器。
对话逻辑全部在 simchat/runtime/，本模块不持有任何模型状态。

启动：python -m simchat.web
"""

import json
import threading

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

__all__ = ["create_app"]

_core_lock = threading.Lock()


def _get_core(app):
    """首次使用时实例化 SimChatCore（失败时由调用方返回 500）。"""
    core = app.extensions.get("simchat_core")
    if core is None:
        with _core_lock:
            core = app.extensions.get("simchat_core")
            if core is None:
                from simchat.runtime import SimChatCore

                core = SimChatCore()
                app.extensions["simchat_core"] = core
    return core


def create_app(core=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.jinja_env.auto_reload = True  # 改了模板立即生效，避免旧进程缓存旧 HTML
    if core is not None:
        app.extensions["simchat_core"] = core

    # Agent 模式（ReAct 循环）：/api/agent 与冻结 fixture 使用的 /api/simchat/agent
    from .agent import create_agent_blueprint

    app.register_blueprint(create_agent_blueprint("agent"), url_prefix="/api/agent")
    app.register_blueprint(
        create_agent_blueprint("simchat_agent"), url_prefix="/api/simchat/agent"
    )

    # 开发期 anti-cache：避免浏览器缓存旧版 JS/CSS 导致"改了啥也不生效"
    @app.after_request
    def _no_cache_static(resp):
        path = request.path
        if path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    def provider_status(core):
        """服务商总览 + UI 方块材质 + MOD 预设。"""
        from simchat.runtime import ui_blocks

        status = core.provider_status()
        status["blocks"] = ui_blocks.list_blocks()
        status["presets"] = ui_blocks.list_presets()
        return status

    # ---------------- 页面 ----------------

    @app.get("/")
    def index():
        # 首次启动（无 profile）跳注册页，否则进主界面
        core = _get_core(app)
        if not core.has_profile():
            return render_template("register.html")
        return render_template("index.html")

    @app.get("/register")
    def register_page():
        core = _get_core(app)
        if core.has_profile():
            # 已有 profile 不让再注册
            return jsonify({"redirect": "/"}), 302
        return render_template("register.html")

    # ---------------- 服务商配置 ----------------

    @app.get("/api/providers")
    def list_providers():
        return jsonify(provider_status(_get_core(app)))

    @app.post("/api/providers")
    def save_provider():
        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip()
        try:
            core = _get_core(app)
            core.save_provider(
                provider,
                data.get("config") or {},
                activate=bool(data.get("activate", True)),
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(provider_status(core))

    @app.post("/api/providers/test")
    def test_provider():
        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip()
        try:
            return jsonify(_get_core(app).test_provider(provider, data.get("config") or {}))
        except ValueError as error:
            return jsonify({"ok": False, "message": str(error)}), 400

    @app.post("/api/providers/discover")
    def discover_provider():
        """手动触发模型列表发现。payload 为表单字段。返回 {ok, models, message}。"""
        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip()
        if provider not in ("ollama", "openai_compat"):
            return jsonify({"ok": False, "models": [], "message": "未知服务商: " + provider}), 400
        try:
            return jsonify(_get_core(app).discover_provider(provider, data.get("config") or {}))
        except ValueError as error:
            return jsonify({"ok": False, "models": [], "message": str(error)}), 400

    # ---------------- 用户档案 ----------------

    @app.get("/api/profile")
    def get_profile():
        core = _get_core(app)
        profile_data = core.load_profile()
        return jsonify({
            "has_profile": core.has_profile(),
            "profile": profile_data,
        })

    @app.post("/api/profile")
    def save_profile():
        data = request.get_json(silent=True) or {}
        try:
            saved = _get_core(app).save_profile({
                "username": data.get("username", ""),
                "birthday": data.get("birthday", ""),
                "emergency_contact": data.get("emergency_contact", ""),
            })
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "profile": saved})

    # ---------------- 基础设置 ----------------

    @app.get("/api/settings")
    def get_settings():
        core = _get_core(app)
        s = core.load_settings()
        from simchat.runtime import ui_blocks
        return jsonify({
            "settings": s,
            "defaults": {
                "max_history": 40, "temperature": 0.7, "max_tokens": 4096,
                "send_with_enter": True, "show_token_bar": True,
                "theme": "system", "font_scale": 1.0,
            },
            "blocks": ui_blocks.list_blocks(),
        })

    @app.post("/api/settings")
    def post_settings():
        data = request.get_json(silent=True) or {}
        core = _get_core(app)
        try:
            saved = core.save_settings(data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"settings": saved})

    @app.post("/api/settings/reset")
    def reset_settings():
        data = request.get_json(silent=True) or {}
        scope = (data.get("scope") or "settings").strip()
        core = _get_core(app)
        try:
            saved = core.reset_settings(scope=scope)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"settings": saved})

    # ---------------- 网关概览 ----------------

    import time as _time
    _gateway_start = _time.time()

    @app.get("/api/gateway")
    def gateway_snapshot():
        """返回网关握手快照 + 访问信息。

        由于本体尚未实现真正的网关模块，此端点返回占位数据：
        - socket_url / access_token 等访问信息根据当前请求动态生成
        - 健康状况 / 运行时间 / 刻度间隔 / 频道刷新时间 返回运行态真实值
        """
        host = request.host or "127.0.0.1:5000"
        scheme = "wss" if request.is_secure else "ws"
        socket_url = "%s://%s/gateway" % (scheme, host)

        uptime_s = _time.time() - _gateway_start

        # 访问令牌（占位：用 host + 进程启动时间简单 hash）
        import hashlib
        token_seed = "%s-%.0f" % (host, _gateway_start)
        access_token = hashlib.sha256(token_seed.encode()).hexdigest()[:24]

        # 频道刷新时间 —— 网关还没跑，所以是 None
        channel_last_refresh = None

        return jsonify({
            "access": {
                "socket_url": socket_url,
                "access_token": access_token,
                "password": None,           # 不持久化；若需要连接时前端临时输入
                "session_key": "simchat.default",
                "language": "zh-CN",
            },
            "snapshot": {
                "health": "online",          # online / degraded / offline
                "uptime_seconds": uptime_s,
                "tick_interval_ms": None,    # Not available
                "channel_last_refresh": channel_last_refresh,
                "channel_available": False,  # IM 频道未接入
                "handshake_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            },
        })

    @app.post("/api/gateway/connect")
    def gateway_connect():
        """手动刷新 / 尝试连接网关（占位）。"""
        data = request.get_json(silent=True) or {}
        # 真实实现会在此发起握手、建立频道、返回 channel 信息
        return jsonify({
            "ok": True,
            "message": "网关握手已触发（占位实现）",
            "snapshot": {
                "health": "online",
                "uptime_seconds": _time.time() - _gateway_start,
                "tick_interval_ms": None,
                "channel_last_refresh": None,
                "channel_available": False,
                "handshake_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            },
        })

    # ---------------- 通讯通道 ----------------

    @app.get("/api/console/comms")
    def list_comms():
        from simchat.runtime import comms as comms_mod
        core = _get_core(app)
        return jsonify({
            "available": True,
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "reason": "",
            "data": comms_mod.list_channels(core.data_root),
        })

    @app.post("/api/console/comms/<channel_id>")
    def save_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        data = request.get_json(silent=True) or {}
        core = _get_core(app)
        try:
            result = comms_mod.save_channel(core.data_root, channel_id, data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": result})

    @app.post("/api/console/comms/<channel_id>/activate")
    def activate_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        core = _get_core(app)
        try:
            result = comms_mod.set_active(core.data_root, channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": result})

    @app.post("/api/console/comms/<channel_id>/clear")
    def clear_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        core = _get_core(app)
        try:
            result = comms_mod.clear_channel(core.data_root, channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": result})

    # ---------------- 会话 CRUD ----------------

    @app.get("/api/sessions")
    def list_sessions():
        return jsonify({"sessions": _get_core(app).list_sessions()})

    @app.post("/api/sessions")
    def create_session():
        return jsonify({"session": _get_core(app).create_session()})

    @app.get("/api/sessions/<sid>")
    def get_session(sid):
        session = _get_core(app).get_session(sid)
        if not session:
            return jsonify({"error": "会话不存在"}), 404
        return jsonify({"session": session})

    @app.delete("/api/sessions/<sid>")
    def delete_session(sid):
        return jsonify({"deleted": _get_core(app).delete_session(sid)})

    # ---------------- 对话（SSE） ----------------

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "消息不能为空"}), 400

        core = _get_core(app)
        if not core.has_available_provider():
            return jsonify({
                "error": "尚未配置可用的服务商，请先完成服务商配置。",
                "code": "provider_unavailable",
            }), 409

        def generate():
            for event in core.chat_stream(
                message,
                session_id=data.get("session_id"),
                provider=data.get("provider"),
                model=data.get("model"),
                system=data.get("system"),
                regenerate=bool(data.get("regenerate")),
            ):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    return app
