"""SimChat Web — 本体独立对话的 Flask 外壳。

路由只做两件事：把 SessionStore 的会话 CRUD 暴露成 JSON，
把 SimChatCore.chat_stream() 的 SSE 事件原样转发给浏览器。
对话逻辑全部在 simchat/runtime/，本模块不持有任何模型状态。

启动：python .simchat/scripts/entry.py web
"""

import atexit
import json
import logging
import os
import secrets as _secrets
import socket
import threading
import time
from collections import deque
from urllib.parse import urlsplit

# 版本号单一来源在 loader 侧（叶子模块 version.py，无反向依赖）
from simchat.loader.version import HOST_VERSION

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

__all__ = ["create_app"]

_core_lock = threading.Lock()
_bots_lock = threading.Lock()

# 进程启动时间（调试面板展示 uptime 用）
_WEB_STARTED_AT = time.time()

# ---------------- 本地访问闸门 ----------------
# 浏览器：首次打开页面发一枚 HttpOnly 会话 cookie，之后同源请求自动携带；
# 非浏览器本地客户端（桌宠、脚本、启动器探活）不带 Origin，回环地址直接放行。
# 跨站请求（带 Origin）必须持有 token，Host 必须是本机/本机网卡地址，
# 以此挡住 CSRF 与 DNS rebinding。
_WEB_TOKEN = os.environ.get("SIMCHAT_WEB_TOKEN") or _secrets.token_urlsafe(24)


def _local_hosts():
    hosts = {"127.0.0.1", "localhost", "::1"}
    extra = os.environ.get("SIMCHAT_ALLOWED_HOSTS", "")
    hosts.update(item.strip().lower() for item in extra.split(",") if item.strip())
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            hosts.add(address.lower())
    except OSError:
        pass
    return hosts


def _url_host(value):
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


def _is_loopback(address):
    return bool(address) and (address == "::1" or address.startswith("127."))

# 最近 API 事件环形缓冲（调试面板展示用，无持久化）
_EVENTS = deque(maxlen=300)
_EVENTS_LOCK = threading.Lock()
_EVENT_SKIP_PATHS = {"/api/instances/heartbeat", "/api/console/debug/events"}
_request_log = logging.getLogger("simchat.web")


def _record_event(kind, detail=None):
    try:
        item = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": kind,
            "detail": detail or {},
        }
        with _EVENTS_LOCK:
            _EVENTS.appendleft(item)
    except Exception:
        pass


def _ensure_logging(data_root, level=None):
    try:
        from simchat.runtime import logs as logs_mod

        logs_mod.setup(data_root)
        if level:
            logs_mod.set_level(data_root, level)
    except Exception:
        pass

# 项目根目录（某些 API 仍用到）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MOD / 技能目录（进程级单例）
_MODS_DIR = os.path.join(_PROJECT_ROOT, "mods")
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")
_MODS_HOST_VERSION = HOST_VERSION
_mod_loader = None
_mod_loader_lock = threading.Lock()

# 自动化调度引擎（进程级单例，daemon 线程）
_automation_engine = None
_automation_lock = threading.Lock()


def _shutdown_mod_loader():
    global _mod_loader
    loader, _mod_loader = _mod_loader, None
    if loader is not None:
        try:
            loader.cleanup()
        except Exception:
            pass


def _shutdown_automation():
    global _automation_engine
    engine, _automation_engine = _automation_engine, None
    if engine is not None:
        try:
            engine.stop()
        except Exception:
            pass


class _LazyCore(object):
    """自动化引擎的运行时代理：首次真正执行 agent:run 时才取 core。"""

    def __init__(self, app):
        self._app = app

    def chat_stream(self, *args, **kwargs):
        return _get_core(self._app).chat_stream(*args, **kwargs)


def _ensure_automation_engine(app=None, loader=None):
    """启动本体自动化调度引擎（幂等）；失败只记日志，不影响 Web 启动。"""
    global _automation_engine
    if _automation_engine is not None:
        return _automation_engine
    with _automation_lock:
        if _automation_engine is not None:
            return _automation_engine
        try:
            from simchat.automation import AutomationEngine, set_global_engine

            data_dir = os.path.join(_PROJECT_ROOT, "data", "automation")
            os.makedirs(data_dir, exist_ok=True)
            engine = AutomationEngine(data_dir, host_version=_MODS_HOST_VERSION,
                                      logger=_request_log)
            if loader is not None:
                engine.bind_loader(loader)
            if app is not None:
                engine.bind_runtime(_LazyCore(app))
            engine.start()  # 内部有 _running 守卫，重复调用不会起第二个线程
            set_global_engine(engine)
            _automation_engine = engine
            atexit.register(_shutdown_automation)
            _request_log.info("自动化引擎已启动: %s", data_dir)
        except Exception:
            _request_log.exception("自动化引擎初始化失败，automation 能力不可用")
    return _automation_engine


class _InferenceService(object):
    """暴露给 MOD 的只读推理服务：api.service("inference").generate_raw(...)"""

    def __init__(self, app):
        self._app = app

    def generate_raw(self, prompt, temperature=0.7, system_prompt=None,
                     max_tokens=1024):
        core = _get_core(self._app)
        provider_id, error = core.resolve_provider()
        if not provider_id:
            raise RuntimeError(error or "尚未配置可用的服务商")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        chunks = core._provider(provider_id).stream_chat(
            messages, temperature=temperature, max_tokens=max_tokens,
        )
        return "".join(chunks)


def _ensure_mod_loader(app=None):
    """启动 MOD 加载器并同步方块；失败只记日志，不阻塞 Web 启动。"""
    global _mod_loader
    if _mod_loader is not None:
        return _mod_loader
    with _mod_loader_lock:
        if _mod_loader is not None:
            return _mod_loader
        try:
            from simchat.loader import ModLoader
            from simchat.loader.lifecycle import set_global_loader
            from simchat.loader.skill_manager_facade import SkillManager
            from simchat.runtime.agent.tools import sync_loader_blocks

            services = {"skill_manager": SkillManager()}
            if app is not None:
                services["inference"] = _InferenceService(app)

            loader = ModLoader(
                _MODS_DIR,
                host_version=_MODS_HOST_VERSION,
                services=services,
                logger=lambda message: _request_log.info("[mods] %s", message),
                extra_dirs=[_SKILLS_DIR],
            )
            # 引擎必须先于 discover 就绪：automation 类型 MOD 在加载期注册 flow
            _ensure_automation_engine(app=app, loader=loader)
            loader.discover()
            set_global_loader(loader)
            sync_loader_blocks(loader)
            _mod_loader = loader
            atexit.register(_shutdown_mod_loader)
        except Exception:
            _request_log.exception("MOD 加载器初始化失败，跳过 MOD 能力")
        # 引擎独立于 loader 启动：loader 挂了 automation 仍可跑纯 flow 类任务
        _ensure_automation_engine(app=app, loader=_mod_loader)
    return _mod_loader


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
                _ensure_logging(core.data_root)
                from simchat.runtime.agent.tools import configure_orbiter

                configure_orbiter(core)
    return core


def _get_bot_manager(app):
    """群机器人运行时管理器（进程级单例）。"""
    manager = app.extensions.get("simchat_bots")
    if manager is None:
        with _bots_lock:
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
        _ensure_logging(core.data_root)
        from simchat.runtime.agent.tools import configure_orbiter

        configure_orbiter(core)

    app.extensions["simchat_mod_loader"] = _ensure_mod_loader(app)

    allowed_hosts = _local_hosts()

    @app.before_request
    def _local_auth_guard():
        host = (request.host or "").rsplit(":", 1)[0].strip("[]").lower()
        if host and host not in allowed_hosts:
            return jsonify({"ok": False, "error": "host not allowed"}), 421
        if not request.path.startswith("/api/") or request.path == "/api/health":
            return None
        origin = request.headers.get("Origin")
        for value in (origin, request.headers.get("Referer")):
            if value and _url_host(value) not in allowed_hosts:
                return jsonify({"ok": False, "error": "cross-site request blocked"}), 403
        supplied = request.headers.get("X-SimChat-Token") or request.cookies.get(
            "simchat_token"
        )
        if supplied == _WEB_TOKEN:
            return None
        if origin:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        if _is_loopback(request.remote_addr):
            return None
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    @app.after_request
    def _issue_local_token(response):
        if request.cookies.get("simchat_token") != _WEB_TOKEN:
            response.set_cookie(
                "simchat_token",
                _WEB_TOKEN,
                httponly=True,
                samesite="Strict",
                path="/",
            )
        return response

    # Agent 模式（ReAct 循环）：/api/agent 与冻结 fixture 使用的 /api/simchat/agent
    from .agent import create_agent_blueprint

    app.register_blueprint(create_agent_blueprint("agent"), url_prefix="/api/agent")
    app.register_blueprint(
        create_agent_blueprint("simchat_agent"), url_prefix="/api/simchat/agent"
    )

    # Phase 3 — MOD 前端静态资源自动路由：/mods/<mod_id>/<path> → MOD 的 web/ 目录
    @app.route("/mods/<mod_id>")
    @app.route("/mods/<mod_id>/")
    def _serve_mod_index(mod_id):
        """MOD 声明 frontend_entry 时，目录形式直接返回声明的入口页。"""
        from flask import abort, send_from_directory

        from simchat.loader.lifecycle import get_loader

        loader = app.extensions.get("simchat_mod_loader") or get_loader()
        if loader is None:
            abort(404)
        mod_record = loader.mods.get(mod_id)
        if not mod_record or mod_record.get("status") != "loaded":
            abort(404)
        entry = mod_record.get("frontend_entry")
        if not entry:
            abort(404)
        web_dir = os.path.realpath(os.path.join(mod_record["path"], "web"))
        if not os.path.isdir(web_dir):
            abort(404)
        rel = entry[len("web/"):] if entry.startswith("web/") else entry
        safe_path = os.path.realpath(os.path.join(web_dir, rel))
        try:
            if os.path.commonpath([safe_path, web_dir]) != web_dir:
                abort(403)
        except ValueError:
            abort(403)
        return send_from_directory(web_dir, rel)

    @app.route("/mods/<mod_id>/<path:filename>")
    def _serve_mod_asset(mod_id, filename):
        from flask import abort, send_from_directory

        from simchat.loader.lifecycle import get_loader

        loader = app.extensions.get("simchat_mod_loader") or get_loader()
        if loader is None:
            abort(404)
        mod_record = loader.mods.get(mod_id)
        if not mod_record or mod_record.get("status") != "loaded":
            abort(404)
        web_dir = os.path.realpath(os.path.join(mod_record["path"], "web"))
        if not os.path.isdir(web_dir):
            abort(404)
        # 路径安全：拒绝 ../ 越界
        safe_path = os.path.realpath(os.path.join(web_dir, filename))
        try:
            if os.path.commonpath([safe_path, web_dir]) != web_dir:
                abort(403)
        except ValueError:
            abort(403)
        return send_from_directory(web_dir, filename)

    # MOD 静态资源同样 anti-cache
    @app.after_request
    def _no_cache_mod_static(resp):
        path = request.path
        if path.startswith("/mods/"):
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    @app.before_request
    def _mark_request_start():
        g.simchat_started = time.time()

    @app.after_request
    def _track_request_events(resp):
        """把 API 请求写入调试事件环 + 运行日志（静态资源与心跳除外）。"""
        path = request.path
        if path.startswith("/api/") and path not in _EVENT_SKIP_PATHS:
            started = getattr(g, "simchat_started", None)
            duration = int((time.time() - started) * 1000) if started else 0
            detail = {
                "method": request.method,
                "path": path,
                "status": resp.status_code,
                "duration_ms": duration,
                "ip": request.remote_addr or "",
            }
            _record_event("http", detail)
            if path != "/api/instances" and not path.startswith("/api/console/debug"):
                _request_log.info(
                    "%s %s -> %s (%sms)", request.method, path, resp.status_code, duration
                )
        return resp

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
        """SimChat IDE 六区布局（桌面端）。与 / 的对话界面共用同一后端。"""
        return render_template("ide.html")

    @app.get("/wap")
    def wap_page():
        """SimChat 移动端单列堆栈界面。"""
        return render_template("wap.html")

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
        """手动触发模型列表发现。payload 为表单字段。返回 {ok, models, message}。

        provider 接受协议 id 或厂牌 id（厂牌由 runtime/vendors.py 归一化）。
        """
        from simchat.runtime import vendors

        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip()
        if vendors.transport_of(provider) is None:
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

    @app.get("/api/workspace/read")
    def read_workspace_file():
        path = request.args.get("path") or ""
        try:
            data = _get_core(app).read_workspace_file(path)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        return jsonify({"ok": True, **data})

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
            # os._exit 不执行 finally / atexit，这里显式收掉桌宠子进程
            try:
                from simchat.runtime import pet_launcher

                pet_launcher.stop_all()
            except Exception:
                pass
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

    # ---------------- AI 实例（Agent）CRUD ----------------

    def _agents_mod():
        from simchat.runtime import agents as agents_mod

        return agents_mod

    def _agent_mod():
        from simchat.runtime import agent as agent_mod

        return agent_mod

    @app.get("/api/agents")
    def list_agents():
        agents_mod = _agents_mod()
        core = _get_core(app)
        # 首次访问时自动创建默认实例
        agents_mod._default(core.data_root)
        # MOD 地图（AI 实例）预设：每次列表时幂等同步为只读实例
        try:
            from simchat.loader.lifecycle import get_loader

            loader = get_loader() or app.extensions.get("simchat_mod_loader")
            if loader is not None:
                agents_mod.sync_presets(core.data_root, loader.list_agent_presets())
        except Exception:
            _request_log.exception("同步 MOD 地图预设失败")
        return jsonify({
            "agents": agents_mod.list_all(core.data_root),
            "engine_presets": agents_mod.list_presets(),
        })

    @app.post("/api/agents")
    def create_agent():
        agents_mod = _agents_mod()
        data = request.get_json(silent=True) or {}
        try:
            agent = agents_mod.create(_get_core(app).data_root, data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"agent": agent})

    @app.get("/api/agents/<agent_id>")
    def get_agent(agent_id):
        agents_mod = _agents_mod()
        try:
            agent = agents_mod.get(_get_core(app).data_root, agent_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify({"agent": agent})

    @app.put("/api/agents/<agent_id>")
    def update_agent(agent_id):
        agents_mod = _agents_mod()
        data = request.get_json(silent=True) or {}
        try:
            agent = agents_mod.update(_get_core(app).data_root, agent_id, data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"agent": agent})

    @app.delete("/api/agents/<agent_id>")
    def delete_agent(agent_id):
        agents_mod = _agents_mod()
        try:
            agents_mod.delete(_get_core(app).data_root, agent_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 404
        return jsonify({"ok": True})

    @app.post("/api/agents/reset")
    def reset_agents():
        """删除所有自定义实例，重置为默认实例。"""
        agents_mod = _agents_mod()
        agent = agents_mod.reset_to_defaults(_get_core(app).data_root)
        return jsonify({"agent": agent})

    # ---------------- 控制台：网关节点 ----------------

    def _peer_mod():
        from simchat.runtime import gateway_peers

        return gateway_peers

    @app.get("/api/gateway/peers")
    def gateway_peers_list():
        core = _get_core(app)
        host = request.host or "127.0.0.1:5000"
        scheme = "https" if request.is_secure else "http"
        return jsonify({
            "ok": True,
            "self": {
                "name": "本机 SimChat",
                "url": "%s://%s" % (scheme, host),
                "health": "online",
                "pid": os.getpid(),
                "uptime_seconds": int(time.time() - _WEB_STARTED_AT),
            },
            "peers": _peer_mod().list_peers(core.data_root),
        })

    @app.post("/api/gateway/peers")
    def gateway_peer_add():
        core = _get_core(app)
        data = request.get_json(silent=True) or {}
        try:
            peer = _peer_mod().add_peer(core.data_root, data)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        _record_event("gateway.add", {"id": peer["id"], "url": peer["url"]})
        return jsonify({"ok": True, "peer": peer})

    @app.put("/api/gateway/peers/<peer_id>")
    def gateway_peer_update(peer_id):
        core = _get_core(app)
        data = request.get_json(silent=True) or {}
        try:
            peer = _peer_mod().update_peer(core.data_root, peer_id, data)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        return jsonify({"ok": True, "peer": peer})

    @app.delete("/api/gateway/peers/<peer_id>")
    def gateway_peer_remove(peer_id):
        core = _get_core(app)
        try:
            _peer_mod().remove_peer(core.data_root, peer_id)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 404
        _record_event("gateway.remove", {"id": peer_id})
        return jsonify({"ok": True})

    @app.post("/api/gateway/peers/<peer_id>/probe")
    def gateway_peer_probe(peer_id):
        core = _get_core(app)
        try:
            result = _peer_mod().probe_peer(core.data_root, peer_id)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 404
        return jsonify({"ok": True, "probe": result})

    @app.post("/api/gateway/peers/probe")
    def gateway_peer_probe_draft():
        """新增节点前先测连通性（不落盘）。"""
        data = request.get_json(silent=True) or {}
        result = _peer_mod().probe(data.get("url"), data.get("token"))
        return jsonify({"ok": result.get("ok", False), "probe": result})

    # ---------------- 控制台：MOD / 技能 ----------------

    def _mods_snapshot():
        from simchat.runtime import mods_index

        return mods_index.snapshot()

    @app.get("/api/console/mods")
    def console_mods():
        try:
            return jsonify({"available": True, "reason": "", "data": _mods_snapshot()})
        except Exception as error:
            return jsonify({"available": False, "reason": str(error), "data": None}), 500

    @app.post("/api/console/mods/<mod_id>/toggle")
    def console_mod_toggle(mod_id):
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400
        from simchat.runtime import mods_index

        mods_index.set_enabled(mod_id, enabled)
        _record_event("mod.toggle", {"mod_id": mod_id, "enabled": enabled})
        return jsonify({"ok": True, "data": _mods_snapshot()})

    @app.get("/api/console/skills")
    def console_skills():
        try:
            from simchat.runtime import mods_index

            data = mods_index.skills_snapshot()
        except Exception as error:
            return jsonify({"available": False, "reason": str(error), "data": None}), 500
        return jsonify({"available": True, "reason": "", "data": data})

    @app.post("/api/console/skills/<skill_id>/toggle")
    def console_skill_toggle(skill_id):
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400
        from simchat.runtime import mods_index

        result = mods_index.set_enabled(
            skill_id, enabled, directory=mods_index.DEFAULT_SKILLS_DIR)
        _record_event("skill.toggle", {"skill_id": skill_id, "enabled": enabled})
        return jsonify({"ok": True, "data": mods_index.skills_snapshot(), "result": result})

    # ---------------- 控制台：节点（客户端 + 网关节点） ----------------

    @app.get("/api/console/nodes")
    def console_nodes():
        core = _get_core(app)
        now = time.time()
        clients = []
        with _instances_lock:
            stale = [d for d, v in _instances.items() if now - v["last_heartbeat"] > 600]
            for device_id in stale:
                del _instances[device_id]
            for device_id, value in _instances.items():
                info = value.get("info") or {}
                clients.append({
                    "kind": "client",
                    "id": device_id,
                    "name": info.get("browser") or info.get("platform") or "浏览器客户端",
                    "platform": " ".join(
                        part for part in (info.get("os"), info.get("arch")) if part
                    ),
                    "tabs": len(value.get("tab_ids") or set()),
                    "online": (now - value["last_heartbeat"]) < INSTANCE_OFFLINE_THRESHOLD,
                    "remote_ip": value.get("remote_ip") or "",
                    "last_seen_ago_seconds": int(now - value["last_heartbeat"]),
                })
        clients.sort(key=lambda item: (not item["online"], -item["last_seen_ago_seconds"]))

        peers = []
        for peer in _peer_mod().list_peers(core.data_root):
            last = peer.get("last_probe") or {}
            peers.append({
                "kind": "gateway",
                "id": peer["id"],
                "name": peer["name"],
                "url": peer["url"],
                "note": peer.get("note") or "",
                "online": bool(last.get("ok")),
                "latency_ms": last.get("latency_ms"),
                "checked_at": last.get("checked_at") or "",
            })

        return jsonify({
            "available": True,
            "reason": "",
            "data": {
                "self": {
                    "kind": "self",
                    "name": "本机 SimChat",
                    "url": "%s://%s" % ("https" if request.is_secure else "http", request.host),
                    "pid": os.getpid(),
                },
                "clients": clients,
                "peers": peers,
                "counts": {
                    "clients": len(clients),
                    "clients_online": sum(1 for item in clients if item["online"]),
                    "peers": len(peers),
                    "peers_online": sum(1 for item in peers if item["online"]),
                },
            },
        })

    # ---------------- 控制台：系统配置 ----------------

    @app.get("/api/console/system")
    def console_system():
        core = _get_core(app)
        from simchat.runtime import system_config

        return jsonify({"available": True, "reason": "", "data": system_config.environment(core.data_root)})

    @app.post("/api/console/system")
    def console_system_save():
        core = _get_core(app)
        data = request.get_json(silent=True) or {}
        from simchat.runtime import logs as logs_mod
        from simchat.runtime import system_config

        try:
            state = system_config.save_state(core.data_root, data)
            logs_mod.set_level(core.data_root, state["log_level"])
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400
        _record_event("system.update", {"log_level": state["log_level"]})
        return jsonify({"ok": True, "data": system_config.environment(core.data_root)})

    # ---------------- 控制台：调试 ----------------

    @app.get("/api/console/debug/snapshot")
    def console_debug_snapshot():
        core = _get_core(app)
        from simchat.runtime import system_config

        data = system_config.debug_snapshot(core.data_root)
        runs_dir = os.path.join(core.data_root, "agent_runs")
        runs = 0
        if os.path.isdir(runs_dir):
            runs = sum(1 for name in os.listdir(runs_dir) if not name.startswith("."))

        try:
            sessions = len(core.list_sessions())
        except Exception:
            sessions = 0

        with _instances_lock:
            instance_count = len(_instances)
        with _EVENTS_LOCK:
            event_count = len(_EVENTS)

        data.update({
            "uptime_seconds": int(time.time() - _WEB_STARTED_AT),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(_WEB_STARTED_AT)),
            "counts": {
                "sessions": sessions,
                "agent_runs": runs,
                "instances": instance_count,
                "gateway_peers": len(_peer_mod().list_peers(core.data_root)),
                "events": event_count,
            },
        })
        return jsonify({"available": True, "reason": "", "data": data})

    @app.get("/api/console/debug/events")
    def console_debug_events():
        try:
            limit = max(10, min(int(request.args.get("limit", 60)), len(_EVENTS) or 60, 300))
        except (TypeError, ValueError):
            limit = 60
        with _EVENTS_LOCK:
            events = list(_EVENTS)
        return jsonify({
            "available": True,
            "reason": "",
            "data": {"total": len(events), "events": events[:limit]},
        })

    # ---------------- 控制台：日志 ----------------

    @app.get("/api/console/logs")
    def console_logs():
        core = _get_core(app)
        from simchat.runtime import logs as logs_mod

        return jsonify({
            "available": True,
            "reason": "",
            "data": {
                "log_dir": logs_mod.log_dir(core.data_root),
                "files": logs_mod.list_files(core.data_root),
            },
        })

    @app.get("/api/console/logs/<name>")
    def console_log_tail(name):
        core = _get_core(app)
        from simchat.runtime import logs as logs_mod

        try:
            payload = logs_mod.tail(core.data_root, name, request.args.get("lines", 200))
        except ValueError as error:
            return jsonify({"available": False, "reason": str(error), "data": None}), 404
        return jsonify({"available": True, "reason": "", "data": payload})

    # ---------------- 控制台：自动化 ----------------

    @app.get("/api/console/automation")
    def console_automation():
        try:
            from simchat.runtime import mods_index

            snapshot = _mods_snapshot()
            skills = mods_index.skills_snapshot()
        except Exception as error:
            return jsonify({"available": False, "reason": str(error), "data": None}), 500
        items = [dict(item, source="mod")
                 for item in snapshot["local"] if item["type"] == "automation"]
        items += [dict(item, source="skill")
                  for item in skills["items"] if item["type"] == "automation"]
        return jsonify({
            "available": True,
            "reason": "",
            "data": {
                "engine": "not_started",
                "engine_note": "自动化引擎由宿主启动器提供；Web 控制台只做流程只读展示。",
                "mods_dir": snapshot["mods_dir"],
                "items": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "version": item["version"],
                        "description": item["description"],
                        "enabled": item["enabled"],
                        "status": item["status"],
                        "error": item["error"],
                        "source": item["source"],
                        "flow": item.get("automation"),
                    }
                    for item in items
                ],
                "counts": {
                    "total": len(items),
                    "enabled": sum(1 for item in items if item["enabled"]),
                },
            },
        })

    @app.post("/api/console/automation/<item_id>/toggle")
    def console_automation_toggle(item_id):
        """自动化条目的启停：按条目所在目录（mods/ 或 skills/）写入对应状态文件。"""
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400
        from simchat.runtime import mods_index

        snapshot = _mods_snapshot()
        in_mods = any(item["id"] == item_id and item["type"] == "automation"
                      for item in snapshot["local"])
        in_skills = any(item["id"] == item_id and item["type"] == "automation"
                        for item in mods_index.skills_snapshot()["items"])
        if not in_mods and not in_skills:
            return jsonify({"ok": False, "error": "自动化条目不存在: %s" % item_id}), 404
        if in_mods:
            result = mods_index.set_enabled(item_id, enabled)
        else:
            result = mods_index.set_enabled(
                item_id, enabled, directory=mods_index.DEFAULT_SKILLS_DIR)
        _record_event("automation.toggle", {
            "item_id": item_id, "enabled": enabled,
            "source": "mod" if in_mods else "skill",
        })
        return jsonify({"ok": True, "result": result})

    # ---------------- 控制台：代理（Agent 运行时） ----------------

    @app.get("/api/console/agent")
    def console_agent():
        core = _get_core(app)
        agents_mod = _agents_mod()
        agents_mod._default(core.data_root)
        try:
            from simchat.runtime import mods_index

            skills = mods_index.skills_snapshot()
            skill_mods = [item for item in skills["items"] if item["type"] == "skill"]
        except Exception:
            skill_mods = []

        return jsonify({
            "available": True,
            "reason": "",
            "data": {
                "agents": agents_mod.list_all(core.data_root),
                "engine_presets": agents_mod.list_presets(),
                "options": core.agent_options(),
                "skill_mods": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "version": item["version"],
                        "enabled": item["enabled"],
                        "hooks": item["hooks"],
                        "status": item["status"],
                    }
                    for item in skill_mods
                ],
            },
        })

    # ---------------- MOD 专属对话卡片 ----------------

    @app.get("/api/mods/chat-cards")
    def mod_chat_cards():
        """侧边栏 MOD 对话卡片清单（数据来自启用中 MOD 的 desktop.chat_card）。"""
        from simchat.runtime import mod_chat

        core = _get_core(app)
        return jsonify({"cards": mod_chat.list_cards(core.store)})

    @app.post("/api/mods/chat-cards/<mod_id>/ensure")
    def mod_chat_card_ensure(mod_id):
        """取该 MOD 的唯一会话；首次访问时创建（固定 id + origin 标记）。"""
        from simchat.runtime import mod_chat

        try:
            session = mod_chat.ensure_session(_get_core(app).store, mod_id)
        except mod_chat.ChatCardError as error:
            return jsonify({"error": str(error), "code": error.code}), error.status
        return jsonify({"session": session})

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
        core = _get_core(app)
        session = core.get_session(sid)
        # 删除能力由会话字段 is_deleteable 决定（MOD 托管会话声明为 false）
        if session and session.get("is_deleteable") is False:
            return jsonify({
                "deleted": False,
                "error": "该会话由 MOD 托管，不能删除。",
                "code": "session_protected",
            }), 403
        return jsonify({"deleted": core.delete_session(sid)})

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

        # 激活的实例：用它的神经引擎预设参数与系统提示词
        agent = None
        agent_id = (data.get("agent_id") or "").strip()
        if agent_id:
            try:
                agent = _agents_mod().get(core.data_root, agent_id)
            except ValueError:
                agent = None
        engine_params = _agents_mod().resolve_engine_params(agent) if agent else None
        system = data.get("system")
        if not system and agent:
            system = agent.get("system_prompt") or None
        agent_capable = bool(agent and agent.get("agent_capable", True))
        # 实例的装备集：None = 不限制（旧实例）；列表 = 只允许这些能力
        equipped = core.resolve_equipped(agent) if agent else None

        def _stream_out(event):
            return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        def generate():
            # 与 /api/agent/abort 共用同一套取消信号：前端拿 chat_started 里的
            # run_id 调 abort，就能让本轮生成在分块 / 轮次之间停下
            from simchat.runtime.agent.runs import agent_runs
            run_id = agent_runs.create()
            abort_event = (agent_runs.get(run_id) or {}).get("abort")
            kwargs = {}
            if engine_params:
                kwargs = {
                    "temperature": engine_params["temperature"],
                    "max_tokens": engine_params["max_tokens"],
                    "top_p": engine_params["top_p"],
                    "repetition_penalty": engine_params["repetition_penalty"],
                }
            _record_event("chat.start", {
                "session_id": data.get("session_id") or "",
                "agent_id": agent_id,
                "provider": data.get("provider") or "",
                "model": data.get("model") or "",
                "chars": len(message),
                "agent_mode": agent_capable,
            })
            try:
                # ---- Agent 模式：ReAct 循环 ----
                if agent_capable:
                    agent_mod = _agent_mod()
                    backend = agent_mod.SimChatAgentBackend(
                        core,
                        provider=data.get("provider"),
                        model=data.get("model"),
                        temperature=kwargs.get("temperature", 0.7),
                        max_tokens=kwargs.get("max_tokens", 1024),
                        top_p=kwargs.get("top_p"),
                        repetition_penalty=kwargs.get("repetition_penalty"),
                    )
                    # quota 硬闸（与 chat_stream 同源）
                    ok, reason, _usage, _quota_cfg = core.usage.check_quota(core.data_root)
                    if not ok:
                        yield _stream_out({
                            "event": "error", "code": "quota_exceeded",
                            "message": reason,
                        })
                        return
                    sess = core.store.get_or_create(data.get("session_id"), mode="agent")
                    if sess.get("mode") != "agent":
                        sess = core.store.create(mode="agent")
                    sid = sess["id"]
                    yield _stream_out({"event": "chat_started", "schema": 1,
                                        "session_id": sid, "agent_mode": True,
                                        "run_id": run_id})

                    history = [{"role": m["role"], "content": m["content"]}
                               for m in sess.get("messages", [])]

                    loop = agent_mod.AgentLoop(
                        backend,
                        workdir=(core.workspace_status() or {}).get("path"),
                        max_turns=10,
                        mode="agent",
                        shell_enabled=False,
                        abort_event=abort_event,
                        equipped=equipped,
                    )
                    agent_events = []
                    loop.run(
                        message,
                        history=history,
                        session_id=sid,
                        persona=(agent or {}).get("name"),
                        run_id=sid,
                        system_prompt=system,
                        emit=lambda evt: agent_events.append(evt),
                    )
                    # loop.run 同步返回后，把 ReAct 过程中积累的事件逐条 SSE 发出
                    for evt in agent_events:
                        yield _stream_out(evt)
                    return

                # ---- 普通对话模式 ----
                for event in core.chat_stream(
                    message,
                    session_id=data.get("session_id"),
                    provider=data.get("provider"),
                    model=data.get("model"),
                    system=system,
                    regenerate=bool(data.get("regenerate")),
                    abort_event=abort_event,
                    **kwargs,
                ):
                    if event.get("event") == "chat_started":
                        event["run_id"] = run_id
                    yield _stream_out(event)
            except GeneratorExit:
                # 客户端断开：让服务端的生成循环尽快停下
                agent_runs.abort(run_id)
                raise
            except Exception as error:
                _record_event("chat.error", {"error": str(error)[:200]})
                raise
            finally:
                agent_runs.remove(run_id)
                _record_event("chat.end", {"session_id": data.get("session_id") or ""})

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
