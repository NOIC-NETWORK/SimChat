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
    app.json.ensure_ascii = False
    if core is not None:
        app.extensions["simchat_core"] = core

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
        return render_template("index.html")

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
