"""按 MOD 的 desktop.pet.entry 声明拉起桌宠子进程（最小实现）。

只做三件事：扫描已启用 MOD 的声明、在 Web 服务就绪后拉起、宿主退出时收掉。
不做托盘、不写偏好、不做开关、不守护重启、不做单实例窗口复用；
桌宠进程自己退出或崩溃都不会被再次拉起。
"""

import atexit
import os
import subprocess
import sys
import threading
import time

_PROCS = []
_LOCK = threading.Lock()
_LAUNCHED = False
_STOPPED = False


def _resolve_script(package_dir, rel_path):
    """把包内相对路径解析成真实文件；越界或不存在返回 None。"""
    base = os.path.realpath(package_dir)
    target = os.path.realpath(os.path.join(base, rel_path))
    try:
        inside = os.path.commonpath([target, base]) == base
    except ValueError:
        return None
    if not inside or not os.path.isfile(target):
        return None
    return target


def discover(mods_dir=None):
    """返回 [(mod_id, script_path, package_dir)]，只取已启用且声明有效的条目。"""
    from simchat.runtime import mods_index

    found = []
    for item in mods_index.scan(mods_dir):
        if not item.get("enabled") or item.get("status") == "err":
            continue
        desktop = item.get("desktop") or {}
        pet = desktop.get("pet") or {}
        entry = pet.get("entry")
        if not isinstance(entry, str) or not entry:
            continue
        script = _resolve_script(item["path"], entry)
        if script:
            found.append((item.get("id"), script, item["path"]))
    return found


def _spawn(script, package_dir):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW：不弹控制台
    return subprocess.Popen(
        [sys.executable, script],
        cwd=package_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs
    )


def launch_enabled(mods_dir=None):
    """为每个声明了 desktop.pet.entry 的已启用 MOD 拉起一个子进程。

    每个宿主进程只执行一次；重复调用返回空列表。
    """
    global _LAUNCHED
    with _LOCK:
        if _LAUNCHED:
            return []
        _LAUNCHED = True

    launched = []
    for mod_id, script, package_dir in discover(mods_dir):
        with _LOCK:
            if _STOPPED:
                break
        try:
            proc = _spawn(script, package_dir)
        except Exception as error:
            print("[SimChat] 桌宠启动失败（%s）：%s" % (mod_id, error))
            continue
        with _LOCK:
            if _STOPPED:
                # 服务恰好在拉起过程中退出：立刻收掉，避免竞态留下孤儿
                proc.terminate()
                break
            _PROCS.append(proc)
        launched.append((mod_id, proc))
    if launched:
        atexit.register(stop_all)
    return launched


def stop_all():
    """终止本轮拉起的全部桌宠进程；可重复调用。"""
    global _STOPPED
    with _LOCK:
        _STOPPED = True
        procs = list(_PROCS)
        _PROCS.clear()
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    deadline = time.monotonic() + 3.0
    for proc in procs:
        try:
            proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
