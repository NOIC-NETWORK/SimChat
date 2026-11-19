"""Web 启动入口（经 ``scripts/entry.py web`` 调用）。"""

import argparse
import os
import signal
import socket
import threading
import time
import webbrowser

from . import create_app

_OPEN_TIMEOUT = 20.0


def local_url(host, port):
    """把监听地址换算成本机可直接打开的 URL；非本机监听返回 None。"""
    host = str(host or "").strip()
    if host in ("127.0.0.1", "localhost", "::1"):
        return "http://%s:%s" % (host, port)
    if host in ("0.0.0.0", "::"):
        return "http://127.0.0.1:%s" % port
    return None


def launch_browser(url):
    """尽量拉起一个浏览器窗口；返回是否成功。"""
    try:
        if webbrowser.open(url):
            return True
    except Exception:
        pass
    if os.name == "nt":
        try:
            os.startfile(url)
            return True
        except OSError:
            pass
    return False


def _wait_until_listening(port, timeout=_OPEN_TIMEOUT):
    """轮询本机端口，直到服务真正监听；超时返回 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def open_browser_when_ready(url, port, timeout=_OPEN_TIMEOUT):
    """等服务真正监听后再打开浏览器，避免打开空白页或「无法连接」页。"""
    if not _wait_until_listening(port, timeout):
        return False
    launch_browser(url)
    return True


def _pet_autostart(port):
    """Flask 监听成功后再为已启用 MOD 拉起桌宠；失败只记日志。"""
    if not _wait_until_listening(port):
        return
    try:
        from simchat.runtime import pet_launcher

        pet_launcher.launch_enabled()
    except Exception as error:
        print("[SimChat] 桌宠启动失败：%s" % error)


def _install_lifecycle_hooks(host, port):
    """登记服务信息，并把 Ctrl+C / SIGTERM 标记成「用户主动停止」。

    守护进程看到这个标记后只退出、不拉起；异常崩溃（无标记）才会被复原。
    """
    try:
        from simchat.runtime import lifecycle

        lifecycle.note_server_start(host, port)
    except Exception:
        pass

    def _handler(signum, frame):
        try:
            from simchat.runtime import lifecycle

            lifecycle.mark_intentional_stop()
        except Exception:
            pass
        raise KeyboardInterrupt

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (OSError, ValueError):
            pass


def _bot_autostart(app):
    """服务进程就绪后按配置自动上线群机器人（失败只记日志，不影响 Web 服务）。"""
    try:
        from . import _get_bot_manager

        manager = _get_bot_manager(app)
        manager.autostart()
    except Exception as error:
        print("[SimChat] 群机器人自动上线失败：%s" % error)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python .simchat/scripts/entry.py web",
        description="SimChat Web 对话界面（Flask）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=5000, help="监听端口（默认 5000）")
    parser.add_argument("--debug", action="store_true", help="开启 Flask 调试模式")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开浏览器窗口",
    )
    args = parser.parse_args(argv)

    url = local_url(args.host, args.port)
    # debug 模式下 reloader 会再启一个子进程；只在真正跑服务的那个进程里开窗，避免开两次
    should_open = (
        bool(url)
        and not args.no_browser
        and (not args.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true")
    )

    app = create_app()
    _install_lifecycle_hooks(args.host, args.port)
    print("[SimChat] Web 界面已启动: %s" % (url or "http://%s:%s" % (args.host, args.port)))
    is_server_proc = not args.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if is_server_proc:
        # 只在真正跑服务的进程里自动上线/拉起桌宠，避免 debug reloader 重复拉起
        threading.Thread(target=_bot_autostart, args=(app,), daemon=True).start()
        threading.Thread(target=_pet_autostart, args=(args.port,), daemon=True).start()
    if should_open:
        threading.Thread(
            target=open_browser_when_ready,
            args=(url, args.port),
            daemon=True,
        ).start()
    try:
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    finally:
        # 服务退出时收掉本轮拉起的桌宠，避免留下孤儿进程
        try:
            from simchat.runtime import pet_launcher

            pet_launcher.stop_all()
        except Exception:
            pass


if __name__ == "__main__":
    main()
