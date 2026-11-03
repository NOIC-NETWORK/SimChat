"""SimChat Web — 本体独立对话的 Flask 外壳。

路由只做两件事：把 SessionStore 的会话 CRUD 暴露成 JSON，
把 SimChatCore.chat_stream() 的 SSE 事件原样转发给浏览器。
对话逻辑全部在 simchat/runtime/，本模块不持有任何模型状态。

启动：python -m simchat.web
"""

import json
import os
import threading
import time

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

# IDE 界面演示页：项目根目录下的单文件 HTML（templates 之外，读文件原文返回）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ide_page_path():
    return os.path.join(_PROJECT_ROOT, "ide-demo.html")


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


def _get_bot_manager(app):
    """群机器人运行时管理器（进程级单例）。"""
    manager = app.extensions.get("simchat_bots")
    if manager is None:
        from simchat.runtime import im_bots

        manager = im_bots.BotManager(_get_core(app))
        app.extensions["simchat_bots"] = manager
    return manager


def _comms_payload(app, core):
    """通讯通道视图 + 群机器人运行状态。"""
    from simchat.runtime import comms as comms_mod

    data = comms_mod.list_channels(core.data_root)
    try:
        summary = _get_bot_manager(app).summary()
    except Exception:
        summary = {}
    for channel in data["channels"]:
        channel["runtime"] = summary.get(channel["id"])
        if channel.get("runtime_supported"):
            channel["webhook_path"] = "/api/console/comms/%s/webhook" % channel["id"]
    return data


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

    @app.get("/ide")
    def ide_page():
        """IDE 界面（单文件演示页），与 / 的对话界面共用同一后端。"""
        path = _ide_page_path()
        if not os.path.isfile(path):
            return "IDE 界面文件缺失：ide-demo.html", 404
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        resp = Response(html, mimetype="text/html")
        # 开发期避免浏览器缓存旧版页面
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

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
            payload = {
                "username": data.get("username", ""),
                "birthday": data.get("birthday", ""),
                "emergency_contact": data.get("emergency_contact", ""),
            }
            # 只有显式传 avatar 时才更新头像，避免旧客户端保存其他字段时把头像清空
            if "avatar" in data:
                payload["avatar"] = data.get("avatar", "")
            saved = _get_core(app).save_profile(payload)
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

    # ---------------- 工作目录（workspace） ----------------

    @app.get("/api/workspace")
    def get_workspace():
        return jsonify({"workspace": _get_core(app).workspace_status()})

    @app.post("/api/workspace")
    def set_workspace():
        data = request.get_json(silent=True) or {}
        try:
            status = _get_core(app).save_workspace(data.get("path") or "")
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "workspace": status})

    @app.delete("/api/workspace")
    def clear_workspace():
        return jsonify({"ok": True, "workspace": _get_core(app).clear_workspace()})

    @app.get("/api/workspace/browse")
    def browse_workspace():
        try:
            listing = _get_core(app).browse_workspace(request.args.get("path"))
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        return jsonify({"ok": True, **listing})

    # ---------------- 健康检查 / 生命周期 ----------------

    def _lifecycle():
        from simchat.runtime import lifecycle

        return lifecycle

    @app.get("/api/health")
    def health():
        """守护进程用它判断 Web 是否存活；不读写任何用户数据。"""
        return jsonify({"ok": True, "app": "simchat", "pid": os.getpid()})

    @app.get("/api/lifecycle")
    def lifecycle_status():
        lifecycle = _lifecycle()
        return jsonify(lifecycle.status(server_pid=os.getpid()))

    @app.post("/api/lifecycle/autostart")
    def lifecycle_autostart():
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400
        lifecycle = _lifecycle()
        try:
            return jsonify(lifecycle.set_autostart(enabled))
        except lifecycle.LifecycleError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        except Exception as error:  # pragma: no cover - 平台相关
            return jsonify({"ok": False, "error": "设置开机自启失败：%s" % error}), 500

    @app.post("/api/lifecycle/watchdog")
    def lifecycle_watchdog():
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400
        lifecycle = _lifecycle()
        try:
            return jsonify(
                lifecycle.set_watchdog(
                    enabled,
                    confirm=data.get("confirm") or "",
                    port=data.get("port") or None,
                )
            )
        except lifecycle.LifecycleError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        except Exception as error:  # pragma: no cover - 平台相关
            return jsonify({"ok": False, "error": "设置自动拉起失败：%s" % error}), 500

    @app.post("/api/lifecycle/stop")
    def lifecycle_stop():
        """mode=watchdog 只停守护；mode=service 停守护并退出当前 Web 进程。"""
        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "service").strip()
        lifecycle = _lifecycle()
        try:
            lifecycle.stop_watchdog()
        except Exception as error:  # pragma: no cover - 平台相关
            return jsonify({"ok": False, "error": "停止守护失败：%s" % error}), 500
        if mode == "watchdog":
            return jsonify({"ok": True, "stopped": False, "message": "守护已停止，Web 服务继续运行"})

        # 先让响应返回，再退出进程；stop 标记已写入，守护不会复活
        def _exit_process():
            time.sleep(0.9)
            os._exit(0)

        threading.Thread(target=_exit_process, daemon=True).start()
        return jsonify({
            "ok": True,
            "stopped": True,
            "message": "SimChat 服务已停止；开机自启设置保持不变",
        })

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
        core = _get_core(app)
        return jsonify({
            "available": True,
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "reason": "",
            "data": _comms_payload(app, core),
        })

    @app.get("/api/console/comms/runtime")
    def comms_runtime():
        return jsonify({
            "available": True,
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "data": _get_bot_manager(app).summary(),
        })

    @app.post("/api/console/comms/<channel_id>")
    def save_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        data = request.get_json(silent=True) or {}
        core = _get_core(app)
        try:
            comms_mod.save_channel(core.data_root, channel_id, data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": _comms_payload(app, core)})

    @app.post("/api/console/comms/<channel_id>/activate")
    def activate_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        core = _get_core(app)
        try:
            comms_mod.set_active(core.data_root, channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": _comms_payload(app, core)})

    @app.post("/api/console/comms/<channel_id>/clear")
    def clear_comm_channel(channel_id):
        from simchat.runtime import comms as comms_mod
        core = _get_core(app)
        try:
            if channel_id in ("qq_group_onebot", "qq_group_official"):
                _get_bot_manager(app).stop(channel_id)
            comms_mod.clear_channel(core.data_root, channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "data": _comms_payload(app, core)})

    # ---------------- 群机器人运行时 ----------------

    @app.post("/api/console/comms/<channel_id>/start")
    def start_comm_bot(channel_id):
        from simchat.runtime.im_bots import ImBotError
        try:
            runtime = _get_bot_manager(app).start(channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except ImBotError as error:
            return jsonify({"error": str(error)}), error.status
        core = _get_core(app)
        return jsonify({"ok": True, "runtime": runtime, "data": _comms_payload(app, core)})

    @app.post("/api/console/comms/<channel_id>/stop")
    def stop_comm_bot(channel_id):
        try:
            runtime = _get_bot_manager(app).stop(channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        core = _get_core(app)
        return jsonify({"ok": True, "runtime": runtime, "data": _comms_payload(app, core)})

    @app.post("/api/console/comms/<channel_id>/test-connection")
    def test_comm_bot_connection(channel_id):
        from simchat.runtime.im_bots import ImBotError
        try:
            detail, runtime = _get_bot_manager(app).test_connection(channel_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except ImBotError as error:
            return jsonify({"error": str(error)}), error.status
        return jsonify({"ok": True, "detail": detail, "runtime": runtime})

    @app.post("/api/console/comms/<channel_id>/test")
    def test_comm_bot_send(channel_id):
        from simchat.runtime.im_bots import ImBotError
        payload = request.get_json(silent=True) or {}
        try:
            result, runtime = _get_bot_manager(app).test_send(
                channel_id,
                payload.get("group_id") or "",
                payload.get("message") or "",
                payload.get("msg_id") or None,
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except ImBotError as error:
            return jsonify({"error": str(error)}), error.status
        return jsonify({"ok": True, "detail": result, "runtime": runtime})

    @app.post("/api/console/comms/qq_group_onebot/webhook")
    def onebot_webhook():
        """OneBot v11 反向 HTTP 事件入口；?token= 或 Authorization 头校验。"""
        from simchat.runtime.im_bots import ImBotError
        token = request.args.get("token") or ""
        auth = request.headers.get("Authorization") or ""
        if not token and auth:
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth.strip()
        payload = request.get_json(silent=True) or {}
        try:
            result = _get_bot_manager(app).handle_onebot_event(payload, token)
        except ImBotError as error:
            return jsonify({"ok": False, "error": str(error)}), error.status
        return jsonify(result)

    @app.post("/api/console/comms/qq_group_official/webhook")
    def official_webhook():
        """QQ 官方机器人 Webhook 回调入口（Ed25519 验签 + op 13 地址验证）。"""
        from simchat.runtime.im_bots import ImBotError
        raw_body = request.get_data()
        try:
            body, status = _get_bot_manager(app).handle_official_webhook(
                request.headers, raw_body
            )
        except ImBotError as error:
            return jsonify({"error": str(error)}), error.status
        return jsonify(body), status

    # ---------------- 实例 / 客户端心跳 ----------------
    import uuid as _uuid

    # 内存中的客户端注册表：device_id -> {info, first_seen, last_heartbeat}
    # 用 dict + lock 保证线程安全；60 秒无心跳视为离线
    _instances_lock = threading.Lock()
    _instances = {}
    INSTANCE_OFFLINE_THRESHOLD = 60  # 秒

    @app.post("/api/instances/heartbeat")
    def instances_heartbeat():
        """客户端定期上报设备信息 + 心跳。

        payload:
          device_id:  浏览器/标签页唯一 ID（localStorage 持久化 + sessionStorage 区分 tab）
          tab_id:     标签页 ID（可选；同一浏览器多 tab 有相同 device_id 但不同 tab_id）
          info:       { os, os_version, browser, browser_version, ua, arch, screen,
                        language, timezone, date, hardware_concurrency, device_pixel_ratio,
                        platform, vendor, online }
        """
        data = request.get_json(silent=True) or {}
        device_id = (data.get("device_id") or "").strip()
        if not device_id:
            return jsonify({"error": "device_id 必填"}), 400

        tab_id = (data.get("tab_id") or "").strip() or None
        info = data.get("info") or {}
        now = time.time()
        remote_ip = request.remote_addr or ""

        with _instances_lock:
            existing = _instances.get(device_id)
            if existing is None:
                _instances[device_id] = {
                    "device_id": device_id,
                    "tab_ids": {tab_id} if tab_id else set(),
                    "info": info,
                    "first_seen": now,
                    "last_heartbeat": now,
                    "remote_ip": remote_ip,
                }
            else:
                if tab_id:
                    existing.setdefault("tab_ids", set()).add(tab_id)
                existing["info"] = info or existing.get("info") or {}
                existing["last_heartbeat"] = now
                if remote_ip:
                    existing["remote_ip"] = remote_ip

        return jsonify({"ok": True})

    @app.get("/api/instances")
    def instances_list():
        """返回当前所有注册过的客户端（包含在线/离线信息）。"""
        now = time.time()
        with _instances_lock:
            # 清理长期离线（> 10 分钟）的旧记录，防止内存无限增长
            stale = [d for d, v in _instances.items() if now - v["last_heartbeat"] > 600]
            for d in stale:
                del _instances[d]

            items = []
            for dev_id, v in _instances.items():
                last_hb = v["last_heartbeat"]
                online = (now - last_hb) < INSTANCE_OFFLINE_THRESHOLD
                items.append({
                    "device_id": dev_id,
                    "tabs": len(v.get("tab_ids") or set()),
                    "info": v.get("info") or {},
                    "remote_ip": v.get("remote_ip", ""),
                    "first_seen": v["first_seen"],
                    "last_heartbeat": last_hb,
                    "online": online,
                    "last_seen_ago_seconds": int(now - last_hb),
                })

        # 排序：在线优先，然后按 last_heartbeat 降序
        items.sort(key=lambda x: (not x["online"], -x["last_heartbeat"]))

        online_count = sum(1 for i in items if i["online"])
        return jsonify({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "offline_threshold_seconds": INSTANCE_OFFLINE_THRESHOLD,
            "online": online_count,
            "total": len(items),
            "instances": items,
        })

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

    @app.patch("/api/sessions/<sid>")
    def patch_session(sid):
        """更新 per-session overrides（thinking / verbose / reasoning）。

        payload: {"overrides": {"thinking": "medium", "verbose": "inherit", ...}}
        白名单字段 + 合法值由 store 层校验，非法值静默忽略。
        """
        data = request.get_json(silent=True) or {}
        core = _get_core(app)
        try:
            saved = core.update_session_overrides(sid, data.get("overrides") or {})
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "overrides": saved})

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
        workspace = core.workspace_status()
        if not workspace["configured"]:
            return jsonify({
                "error": "尚未选择工作目录，无法开始对话。",
                "code": "workspace_required",
            }), 409
        if not workspace["exists"]:
            return jsonify({
                "error": "工作目录不存在或不可访问：%s" % workspace["path"],
                "code": "workspace_missing",
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

    # ---------------- 用量统计 / 限额配置 ----------------

    @app.get("/api/console/usage")
    def console_usage():
        """返回每日用量统计（后端 usage.json + settings.json quota 配置）。"""
        core = _get_core(app)
        cfg = core.load_settings()
        quota_cfg = cfg.get("quota") or {}
        today = core.usage.today_usage()
        recent = core.usage.recent_usage(days=7)
        return jsonify({
            "success": True,
            "quota": {
                "enabled": int(quota_cfg.get("limit", 0)) > 0,
                "limit": int(quota_cfg.get("limit", 0)),
                "period": quota_cfg.get("period", "day"),
                "lock": bool(quota_cfg.get("lock", False)),
            },
            "today": today,
            "recent": recent,
        })

    @app.post("/api/console/usage/quota")
    def console_usage_quota_save():
        """保存 quota 配置到 settings.json。只允许修改 limit/period（lock 需单独解锁流程）。"""
        core = _get_core(app)
        data = request.get_json(silent=True) or {}
        current = core.load_settings()
        cur_quota = current.get("quota") or {}

        # 锁定状态下禁止修改 limit 和 enabled
        if cur_quota.get("lock"):
            return jsonify({
                "success": False,
                "error": "额度限制已锁定，请先解锁后再修改",
            }), 403

        updates = {}
        limit_val = data.get("limit")
        if limit_val is not None:
            try:
                limit_int = max(0, int(limit_val))
                updates["limit"] = limit_int
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "limit 必须是非负整数"}), 400

        period_val = data.get("period")
        if period_val is not None and period_val in ("day", "month"):
            updates["period"] = period_val

        # 只有明确传 lock 字段才允许切换锁定状态
        if "lock" in data and isinstance(data["lock"], bool):
            updates["lock"] = data["lock"]

        if not updates:
            return jsonify({"success": False, "error": "无有效字段提交"}), 400

        saved = core.save_settings({"quota": updates})
        return jsonify({
            "success": True,
            "quota": saved.get("quota"),
        })

    @app.post("/api/console/usage/reset-today")
    def console_usage_reset_today():
        """清空今日用量记录（主要用于测试 / 用户手动修正）。"""
        core = _get_core(app)
        core.usage.reset_today()
        return jsonify({"success": True})

    return app
