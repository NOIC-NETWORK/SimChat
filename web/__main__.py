"""python -m simchat.web 启动入口。"""

import argparse
import os
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


def open_browser_when_ready(url, port, timeout=_OPEN_TIMEOUT):
    """等服务真正监听后再打开浏览器，避免打开空白页或「无法连接」页。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
        except OSError:
            time.sleep(0.25)
            continue
        launch_browser(url)
        return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m simchat.web",
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
    print("[SimChat] Web 界面已启动: %s" % (url or "http://%s:%s" % (args.host, args.port)))
    if should_open:
        threading.Thread(
            target=open_browser_when_ready,
            args=(url, args.port),
            daemon=True,
        ).start()
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
