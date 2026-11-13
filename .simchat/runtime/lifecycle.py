"""SimChat 生命周期管理：开机自启 + 自动拉起（高危，默认关闭）。

防流氓设计（写死在本模块，不依赖前端）：
- 两项功能默认关闭；启用「自动拉起」必须在请求里带上确认短语。
- 只在异常中断（端口失联）后拉起；用户 Ctrl+C / 「停止服务」会写 stop 标记，
  守护进程看到后立刻退出，绝不复活。
- 连续崩溃熔断：10 分钟内最多拉起 5 次，熔断后等待人工恢复。
- 只使用当前用户权限（HKCU / LaunchAgent / XDG autostart），不申请管理员，
  不隐藏、不伪装进程，不修改安全软件/防火墙设置。
- 所有偏好、状态、日志都在 data/ 下，设置页可随时查看与解除。

命令行入口（供系统自启项与 deploy_daemon.sh 调用）：
    python scripts/entry.py lifecycle --boot
    python scripts/entry.py lifecycle --guard
    python scripts/entry.py lifecycle --status
    python scripts/entry.py lifecycle --stop
"""

import argparse
import json
import os
import platform
import plistlib
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

# ---------------- 路径与常量 ----------------

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 本体收在 .simchat/ 里，包名别名由 scripts/entry.py 注册，子进程一律走它
ENTRY_SCRIPT = os.path.join(PACKAGE_ROOT, "scripts", "entry.py")
DATA_DIR = os.path.join(PACKAGE_ROOT, "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
RUNTIME_DIR = os.path.join(DATA_DIR, "lifecycle")

PREFS_PATH = os.path.join(DATA_DIR, "lifecycle.json")
STATE_PATH = os.path.join(DATA_DIR, "lifecycle_state.json")
SERVER_PATH = os.path.join(DATA_DIR, "lifecycle_server.json")
STOP_FLAG = os.path.join(DATA_DIR, "lifecycle.stop")
LOCK_PATH = os.path.join(DATA_DIR, "lifecycle.guardian.lock")

WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WIN_RUN_VALUE = "SimChat"
WIN_WRAPPER = os.path.join(RUNTIME_DIR, "autostart.cmd")
MAC_PLIST_LABEL = "com.simchat.web"
MAC_PLIST = os.path.join(
    os.path.expanduser("~"), "Library", "LaunchAgents", MAC_PLIST_LABEL + ".plist"
)
LINUX_DESKTOP = os.path.join(
    os.path.expanduser("~"), ".config", "autostart", "simchat.desktop"
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
CONFIRM_PHRASE = "启用自动拉起"

CHECK_INTERVAL = 3.0          # 守护轮询间隔（秒）
FAIL_THRESHOLD = 3            # 连续失联几次才判断为异常退出
LAUNCH_GRACE = 20.0           # 拉起后给进程的启动宽限
MAX_RESTARTS = 5              # 熔断阈值
RESTART_WINDOW = 600.0        # 熔断统计窗口（10 分钟）
PAUSE_RESET_SECONDS = 300.0   # 服务恢复健康多久后自动解除熔断

_STATE_LOCK = threading.Lock()
_IS_WINDOWS = os.name == "nt"
_SYSTEM = platform.system().lower()


class LifecycleError(Exception):
    """可展示给用户的失败原因。"""


# ---------------- 基础读写 ----------------

def _ensure_dirs():
    for path in (DATA_DIR, LOG_DIR, RUNTIME_DIR):
        os.makedirs(path, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    _ensure_dirs()
    tmp = path + ".tmp"
    with _STATE_LOCK:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def _iso(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts or time.time()))


def _now():
    return time.time()


def _write_text(path, text, encoding="utf-8"):
    _ensure_dirs()
    with open(path, "w", encoding=encoding) as handle:
        handle.write(text)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def load_prefs():
    raw = _read_json(PREFS_PATH, {})
    port = raw.get("port")
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    return {
        "autostart": bool(raw.get("autostart")),
        "watchdog": bool(raw.get("watchdog")),
        "watchdog_confirmed_at": raw.get("watchdog_confirmed_at") or "",
        "host": str(raw.get("host") or DEFAULT_HOST),
        "port": port,
    }


def _save_prefs(prefs):
    _write_json(PREFS_PATH, prefs)
    return prefs


def _guardian_state():
    return _read_json(STATE_PATH, {})


def _write_guardian_state(state):
    state["updated_at"] = _iso()
    _write_json(STATE_PATH, state)


def mark_intentional_stop():
    """用户主动停止（Ctrl+C / 设置页）时落标记，守护进程不会再拉起。"""
    _ensure_dirs()
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as handle:
            handle.write("%s pid=%s" % (_iso(), os.getpid()))
    except OSError:
        pass


def clear_intentional_stop():
    _remove(STOP_FLAG)


def _stop_requested():
    return os.path.exists(STOP_FLAG)


# ---------------- 进程与健康检查 ----------------

def is_pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def terminate_pid(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if pid <= 0:
        return
    if _IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def is_port_open(host, port, timeout=0.5):
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0", "::", "localhost") else host
    try:
        with socket.create_connection((probe_host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def check_health(host, port):
    """返回 (healthy, payload)。只认 SimChat 自己的 /api/health。"""
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0", "::", "localhost") else host
    url = "http://%s:%s/api/health" % (probe_host, int(port))
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SimChat-Guardian"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("ok")) and payload.get("app") == "simchat", payload
    except (OSError, ValueError, urllib.error.URLError):
        return False, None


def note_server_start(host, port):
    """Web 进程启动时登记真实监听信息，守护进程据此判断健康状态。"""
    _ensure_dirs()
    _write_json(SERVER_PATH, {
        "pid": os.getpid(),
        "host": host,
        "port": int(port),
        "started_at": _iso(),
    })


def _server_record():
    record = _read_json(SERVER_PATH, {})
    if record and is_pid_alive(record.get("pid")):
        return record
    return {}


# ---------------- 子进程拉起 ----------------

def _python_exe(windowless=False):
    exe = sys.executable or ""
    if _IS_WINDOWS and windowless:
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return exe or "python"


def _child_env():
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["SIMCHAT_LIFECYCLE"] = "1"
    return env


def _spawn_detached(args, log_name):
    _ensure_dirs()
    log_path = os.path.join(LOG_DIR, log_name)
    flags = 0
    kwargs = {}
    if _IS_WINDOWS:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    log_handle = open(log_path, "a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            args,
            cwd=PACKAGE_ROOT,
            env=_child_env(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **kwargs
        )
    finally:
        log_handle.close()
    return process.pid


def _spawn_web(host, port, open_browser):
    if is_port_open(host, port):
        return None
    args = [
        _python_exe(windowless=True),
        ENTRY_SCRIPT,
        "web",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if not open_browser:
        args.append("--no-browser")
    return _spawn_detached(args, "web.log")


def _spawn_guardian(host, port):
    args = [
        _python_exe(windowless=True),
        ENTRY_SCRIPT,
        "lifecycle",
        "--guard",
        "--host",
        host,
        "--port",
        str(port),
    ]
    return _spawn_detached(args, "guardian.log")


# ---------------- 守护进程锁 ----------------

def _read_lock_pid():
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as handle:
            return int((handle.read() or "0").strip())
    except (OSError, ValueError):
        return 0


def _acquire_lock():
    _ensure_dirs()
    for _ in range(2):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid = _read_lock_pid()
            if pid and pid != os.getpid() and is_pid_alive(pid):
                return False
            _remove(LOCK_PATH)
            continue
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
        finally:
            os.close(fd)
        return True
    return False


def _release_lock():
    if _read_lock_pid() == os.getpid():
        _remove(LOCK_PATH)


def guardian_pid():
    state = _guardian_state()
    pid = state.get("guardian_pid") or _read_lock_pid()
    if pid and is_pid_alive(pid):
        return int(pid)
    return 0


# ---------------- 守护循环 ----------------

def _launch_web(host, port, open_browser, state):
    if _stop_requested():
        return "已请求停止，跳过拉起"
    try:
        pid = _spawn_web(host, port, open_browser)
    except Exception as error:  # pragma: no cover - 平台相关
        state["last_error"] = "拉起失败：%s" % error
        return state["last_error"]
    if pid is None:
        if is_port_open(host, port):
            return "端口 %s 已被占用，未重复拉起" % port
        return "未能建立 Web 进程"
    state["server_pid"] = pid
    state["last_launch_at"] = _iso()
    state["last_error"] = ""
    return ""


def run_guard(host=DEFAULT_HOST, port=DEFAULT_PORT, open_browser_first=False):
    """守护进程主循环。返回进程退出码。"""
    if not _acquire_lock():
        return 0

    clear_intentional_stop()
    state = _guardian_state()
    state.update({
        "guardian_pid": os.getpid(),
        "guardian_started_at": _iso(),
        "running": True,
        "paused": False,
        "paused_reason": "",
        "server_pid": state.get("server_pid") or 0,
        "restarts": int(state.get("restarts") or 0),
        "last_restart_at": state.get("last_restart_at") or "",
        "last_exit_at": state.get("last_exit_at") or "",
        "last_error": state.get("last_error") or "",
    })

    restart_times = [
        float(t) for t in state.get("restart_times", [])
        if isinstance(t, (int, float)) and _now() - float(t) < RESTART_WINDOW
    ]
    state["restart_times"] = restart_times

    healthy, payload = check_health(host, port)
    last_launch_at = 0.0
    failures = 0
    healthy_since = _now() if healthy else 0.0
    was_healthy = healthy

    if healthy and payload:
        state["server_pid"] = payload.get("pid") or state.get("server_pid") or 0
    elif not is_port_open(host, port):
        _launch_web(host, port, open_browser_first, state)
        last_launch_at = _now()
    else:
        state["last_error"] = "端口 %s 已被其他进程占用" % port

    _write_guardian_state(state)

    try:
        while True:
            if _stop_requested():
                state["stop_requested"] = True
                break

            now = _now()
            healthy, payload = check_health(host, port)
            if healthy:
                if not was_healthy:
                    healthy_since = now
                was_healthy = True
                failures = 0
                if payload:
                    state["server_pid"] = payload.get("pid") or state.get("server_pid") or 0
                if state.get("paused") and now - healthy_since >= PAUSE_RESET_SECONDS:
                    state["paused"] = False
                    state["paused_reason"] = ""
                restart_times = [t for t in restart_times if now - t < RESTART_WINDOW]
            else:
                if was_healthy:
                    state["last_exit_at"] = _iso(now)
                was_healthy = False
                if now - last_launch_at < LAUNCH_GRACE:
                    # 刚拉起，给进程启动宽限，避免重复启动
                    pass
                else:
                    failures += 1
                    if failures >= FAIL_THRESHOLD and not state.get("paused"):
                        restart_times = [
                            t for t in restart_times if now - t < RESTART_WINDOW
                        ]
                        if len(restart_times) >= MAX_RESTARTS:
                            state["paused"] = True
                            state["paused_reason"] = (
                                "%d 分钟内已拉起 %d 次，触发熔断，等待人工恢复"
                                % (int(RESTART_WINDOW // 60), MAX_RESTARTS)
                            )
                        else:
                            error = _launch_web(host, port, False, state)
                            if error:
                                state["last_error"] = error
                                if "占用" in error:
                                    state["paused"] = True
                                    state["paused_reason"] = error
                            else:
                                restart_times.append(now)
                                state["restarts"] = int(state.get("restarts") or 0) + 1
                                state["last_restart_at"] = _iso(now)
                            last_launch_at = now
                            failures = 0

            state["restart_times"] = restart_times
            state["consecutive_failures"] = failures
            state["healthy"] = bool(healthy)
            state["stop_requested"] = _stop_requested()
            _write_guardian_state(state)
            time.sleep(CHECK_INTERVAL)
    finally:
        state["running"] = False
        state["guardian_pid"] = 0
        state["healthy"] = False
        _write_guardian_state(state)
        _release_lock()
    return 0


# ---------------- 开机自启 ----------------

def _autostart_command(host, port):
    return '"%s" "%s" lifecycle --boot --host %s --port %s' % (
        _python_exe(windowless=True), ENTRY_SCRIPT, host, port,
    )


def _windows_command(host, port):
    """生成一个可见、可删除的启动包装脚本，注册到 HKCU Run。"""
    exe = _python_exe(windowless=True)
    content = "\r\n".join([
        "@echo off",
        "rem Generated by SimChat lifecycle. Disable it in SimChat settings,",
        "rem or delete this file and the HKCU Run value \\SimChat.",
        'cd /d "%s"' % PACKAGE_ROOT,
        'start "SimChat" "%s" "%s" lifecycle --boot --host %s --port %s'
        % (exe, ENTRY_SCRIPT, host, port),
        "",
    ])
    encoding = "mbcs" if _IS_WINDOWS else "utf-8"
    try:
        _write_text(WIN_WRAPPER, content, encoding=encoding)
    except LookupError:
        _write_text(WIN_WRAPPER, content, encoding="utf-8")
    return WIN_WRAPPER


def _windows_installed():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, WIN_RUN_VALUE)
        return bool(value)
    except (OSError, ImportError):
        return False


def _windows_install(host, port):
    import winreg

    command = _windows_command(host, port)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
        winreg.SetValueEx(key, WIN_RUN_VALUE, 0, winreg.REG_SZ, '"%s"' % command)
    return "HKCU Run → %s" % command


def _windows_uninstall():
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, WIN_RUN_VALUE)
    except (OSError, ImportError):
        pass
    _remove(WIN_WRAPPER)


def _mac_install(host, port):
    _ensure_dirs()
    os.makedirs(os.path.dirname(MAC_PLIST), exist_ok=True)
    payload = {
        "Label": MAC_PLIST_LABEL,
        "ProgramArguments": [
            _python_exe(windowless=True),
            ENTRY_SCRIPT,
            "lifecycle",
            "--boot",
            "--host",
            host,
            "--port",
            str(port),
        ],
        "WorkingDirectory": PACKAGE_ROOT,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Background",
        "StandardOutPath": os.path.join(LOG_DIR, "launchd.out.log"),
        "StandardErrorPath": os.path.join(LOG_DIR, "launchd.err.log"),
    }
    with open(MAC_PLIST, "wb") as handle:
        plistlib.dump(payload, handle)
    _run_quiet(["launchctl", "unload", "-w", MAC_PLIST])
    _run_quiet(["launchctl", "load", "-w", MAC_PLIST])
    return "LaunchAgent → %s" % MAC_PLIST


def _mac_uninstall():
    if os.path.isfile(MAC_PLIST):
        _run_quiet(["launchctl", "unload", "-w", MAC_PLIST])
        _remove(MAC_PLIST)


def _linux_install(host, port):
    _ensure_dirs()
    os.makedirs(os.path.dirname(LINUX_DESKTOP), exist_ok=True)
    exec_line = '"%s" "%s" lifecycle --boot --host %s --port %s' % (
        _python_exe(windowless=True), ENTRY_SCRIPT, host, port,
    )
    content = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=SimChat",
        "Comment=SimChat Harness",
        "Exec=%s" % exec_line,
        "Path=%s" % PACKAGE_ROOT,
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "Hidden=false",
        "",
    ])
    _write_text(LINUX_DESKTOP, content)
    return "XDG autostart → %s" % LINUX_DESKTOP


def _linux_uninstall():
    _remove(LINUX_DESKTOP)


def _run_quiet(args):
    try:
        subprocess.run(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if _IS_WINDOWS else 0,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _autostart_info(prefs):
    server = _server_record()
    host = server.get("host") or prefs.get("host") or DEFAULT_HOST
    try:
        port = int(server.get("port") or prefs.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    if _SYSTEM == "windows":
        installed = _windows_installed()
        return {
            "supported": True,
            "enabled": installed,
            "method": "windows_run",
            "method_label": "Windows 用户启动项（HKCU Run）",
            "location": WIN_RUN_KEY + " \\ " + WIN_RUN_VALUE,
            "command": _autostart_command(host, port),
        }
    if _SYSTEM == "darwin":
        return {
            "supported": True,
            "enabled": os.path.isfile(MAC_PLIST),
            "method": "launch_agent",
            "method_label": "macOS 用户 LaunchAgent",
            "location": MAC_PLIST,
            "command": _autostart_command(host, port),
        }
    if _SYSTEM == "linux":
        return {
            "supported": True,
            "enabled": os.path.isfile(LINUX_DESKTOP),
            "method": "xdg_autostart",
            "method_label": "XDG 用户自启动项",
            "location": LINUX_DESKTOP,
            "command": _autostart_command(host, port),
        }
    return {
        "supported": False,
        "enabled": False,
        "method": "unsupported",
        "method_label": "当前系统不支持自动注册自启动",
        "location": "",
        "command": _autostart_command(host, port),
    }


def set_autostart(enabled):
    prefs = load_prefs()
    server = _server_record()
    host = server.get("host") or prefs.get("host") or DEFAULT_HOST
    try:
        port = int(server.get("port") or prefs.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    info = _autostart_info(prefs)
    if not info["supported"]:
        raise LifecycleError(info["method_label"])

    if enabled:
        if _SYSTEM == "windows":
            detail = _windows_install(host, port)
        elif _SYSTEM == "darwin":
            detail = _mac_install(host, port)
        elif _SYSTEM == "linux":
            detail = _linux_install(host, port)
        else:
            raise LifecycleError("当前系统不支持开机自启")
    else:
        if _SYSTEM == "windows":
            _windows_uninstall()
        elif _SYSTEM == "darwin":
            _mac_uninstall()
        elif _SYSTEM == "linux":
            _linux_uninstall()
        detail = ""

    prefs["autostart"] = bool(enabled)
    prefs["host"] = host
    prefs["port"] = port
    _save_prefs(prefs)
    result = status()
    result["detail"] = detail
    return result


# ---------------- 自动拉起开关 ----------------

def set_watchdog(enabled, confirm=None, host=None, port=None):
    prefs = load_prefs()
    if enabled:
        if (confirm or "").strip() != CONFIRM_PHRASE:
            raise LifecycleError("需要输入确认短语「%s」才能启用自动拉起" % CONFIRM_PHRASE)

        server = _server_record()
        if host is None:
            host = server.get("host") or prefs.get("host") or DEFAULT_HOST
        if port is None:
            try:
                port = int(server.get("port") or prefs.get("port") or DEFAULT_PORT)
            except (TypeError, ValueError):
                port = DEFAULT_PORT

        prefs["watchdog"] = True
        prefs["watchdog_confirmed_at"] = _iso()
        prefs["host"] = host
        prefs["port"] = int(port)
        _save_prefs(prefs)
        clear_intentional_stop()

        state = _guardian_state()
        pid = guardian_pid()
        if pid and state.get("paused"):
            # 熔断后人工恢复：清掉旧守护，重新开始
            mark_intentional_stop()
            _wait_dead(pid, 3.0)
            if is_pid_alive(pid):
                terminate_pid(pid)
                _wait_dead(pid, 1.5)
            clear_intentional_stop()
            _write_json(STATE_PATH, {
                "restarts": 0,
                "restart_times": [],
                "paused": False,
                "paused_reason": "",
            })
            pid = 0
        spawned_pid = 0
        if not pid:
            spawned_pid = _spawn_guardian(host, int(port))
            _wait_for_guardian()
        result = status()
        if (spawned_pid and is_pid_alive(spawned_pid)
                and not result["watchdog"]["guardian_pid"]):
            # 守护进程可能仍在导入依赖，先如实报告已启动
            result["watchdog"]["guardian_pid"] = spawned_pid
            result["watchdog"]["running"] = True
        return result
    else:
        prefs["watchdog"] = False
        prefs["watchdog_confirmed_at"] = ""
        _save_prefs(prefs)
        stop_watchdog(wait=3.0)

    return status()


def stop_watchdog(wait=3.0):
    """停止守护但保留当前 Web 服务；同时写 stop 标记防止复活。"""
    prefs = load_prefs()
    prefs["watchdog"] = False
    _save_prefs(prefs)
    mark_intentional_stop()

    pid = guardian_pid()
    if pid:
        _wait_dead(pid, wait)
        if is_pid_alive(pid):
            terminate_pid(pid)
            _wait_dead(pid, 1.0)
    _release_lock()
    return status()


def _wait_dead(pid, seconds):
    deadline = _now() + max(0.0, float(seconds))
    while _now() < deadline:
        if not is_pid_alive(pid):
            return True
        time.sleep(0.2)
    return False


def _wait_for_guardian(seconds=8.0):
    deadline = _now() + seconds
    while _now() < deadline:
        if guardian_pid():
            return True
        time.sleep(0.2)
    return False


# ---------------- 状态聚合 ----------------

def _server_status(server_pid=None, server_host=None, server_port=None):
    record = _server_record()
    host = server_host or record.get("host") or load_prefs().get("host") or DEFAULT_HOST
    port = server_port or record.get("port") or load_prefs().get("port") or DEFAULT_PORT
    if server_pid:
        return {
            "running": True,
            "pid": int(server_pid),
            "host": host,
            "port": int(port),
            "url": "http://%s:%s" % (
                "127.0.0.1" if host in ("0.0.0.0", "::", "") else host, port
            ),
        }
    healthy, payload = check_health(host, port)
    return {
        "running": bool(healthy),
        "pid": (payload or {}).get("pid") or record.get("pid") or 0,
        "host": host,
        "port": int(port),
        "url": "http://%s:%s" % (
            "127.0.0.1" if host in ("0.0.0.0", "::", "") else host, port
        ),
    }


def status(server_pid=None, server_host=None, server_port=None):
    prefs = load_prefs()
    state = _guardian_state()
    pid = guardian_pid()
    running = bool(pid)
    return {
        "ok": True,
        "platform": platform.system(),
        "platform_key": _SYSTEM,
        "confirmation_phrase": CONFIRM_PHRASE,
        "autostart": _autostart_info(prefs),
        "watchdog": {
            "enabled": prefs["watchdog"],
            "running": running,
            "guardian_pid": pid,
            "paused": bool(running and state.get("paused")),
            "paused_reason": state.get("paused_reason") or "",
            "restarts": int(state.get("restarts") or 0),
            "last_restart_at": state.get("last_restart_at") or "",
            "last_exit_at": state.get("last_exit_at") or "",
            "last_error": state.get("last_error") or "",
            "stop_requested": _stop_requested(),
            "log_path": os.path.join(LOG_DIR, "guardian.log"),
            "state_path": STATE_PATH,
            "limits": {
                "max_restarts": MAX_RESTARTS,
                "window_seconds": int(RESTART_WINDOW),
                "fail_threshold": FAIL_THRESHOLD,
                "check_interval": CHECK_INTERVAL,
            },
        },
        "server": _server_status(server_pid, server_host, server_port),
    }


# ---------------- 启动入口 ----------------

def boot(host, port, open_browser=True):
    """系统自启入口：只启动一次，按偏好决定是否交给守护进程。"""
    clear_intentional_stop()
    prefs = load_prefs()
    if not prefs.get("watchdog"):
        if check_health(host, port)[0] or is_port_open(host, port):
            return 0
        _spawn_web(host, port, open_browser)
        return 0
    if guardian_pid():
        return 0
    return run_guard(host=host, port=port, open_browser_first=open_browser)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python .simchat/scripts/entry.py lifecycle",
        description="SimChat 生命周期管理（开机自启 / 异常拉起）",
    )
    parser.add_argument("--boot", action="store_true", help="开机自启入口")
    parser.add_argument("--guard", action="store_true", help="以守护进程运行")
    parser.add_argument("--stop", action="store_true", help="停止守护（不改动 Web 服务）")
    parser.add_argument("--status", action="store_true", help="打印当前状态 JSON")
    parser.add_argument("--host", default=None, help="监听地址")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    args = parser.parse_args(argv)

    prefs = load_prefs()
    host = args.host or prefs.get("host") or DEFAULT_HOST
    port = args.port or int(prefs.get("port") or DEFAULT_PORT)

    if args.status:
        print(json.dumps(status(server_host=host, server_port=port), ensure_ascii=False, indent=2))
        return 0
    if args.stop:
        print(json.dumps(stop_watchdog(), ensure_ascii=False, indent=2))
        return 0
    if args.boot:
        return boot(host, port, open_browser=True)
    if args.guard:
        return run_guard(host=host, port=port, open_browser_first=False)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
