# -*- coding: utf-8 -*-
"""FORCE EJECT：进程级紧急制动阀门。

它是 SimChat / Orbiter 的最后一道保险，不是"再确认一次要不要停"：

* 一次触发，全局停机——所有登记中的 Agent 运行（ReAct 循环）立即置 abort，
  聊天流、工具执行、自动化调度在下一个检查点退出，已登记的子进程立即杀进程树；
* 不依赖模型判断，没有"解除/取消"接口，只有重启进程才能恢复；
* 触发通道与聊天无关，对话内容和注入指令都碰不到它。

触发方式（任意一种）：
1. 标志文件：在 data/ 下创建 ``FORCE_EJECT``（文件内容作为原因）；
2. 本地 HTTP：``POST /api/control/force-eject``；
3. POSIX 信号：``SIGUSR1``（Windows 下 SIGBREAK 已被优雅停机占用，用前两种）。

终止后写 ``data/eject/<时间戳>.json`` 与 ``latest.json``：列出仍在跑的运行、
挂起待审批的步骤、已执行/半途的写类工具、被终止的子进程，以及受影响文件的
回滚建议。
"""

import json
import os
import signal
import threading
import time
import traceback

__all__ = [
    "Ejected", "engage", "engaged", "reason", "check", "sleep", "event",
    "arm", "journal_start", "journal_finish", "track_process",
    "register_snapshot", "latest_report", "latest_report_path",
]

_PREFIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_FLAG_NAMES = ("FORCE_EJECT", "FORCE_EJECT.txt")
_POLL_INTERVAL = 0.2

_lock = threading.Lock()
_event = threading.Event()
_info = {"reason": "", "source": "", "at": 0.0, "pid": os.getpid(), "started": time.time()}
_base_dir = _PREFIX
_armed = False
_watcher = None

_processes = []
_snapshots = {}
_journal = []
_progress = {}
_report_path = None


class Ejected(RuntimeError):
    """在检查点被 FORCE EJECT 打断。"""

    def __init__(self, reason=""):
        self.reason = reason or info_reason()
        super(Ejected, self).__init__("FORCE EJECT: %s" % self.reason)


def occupied():
    """阀门是否已触发（给循环做轻量判断，不抛异常）。"""
    return _event.is_set()


# 兼容两种命名习惯
engaged = occupied


def event():
    """暴露底层 threading.Event，方便和已有 abort_event 一起 wait。"""
    return _event


def reason():
    return _info.get("reason") or ""


def info_reason():
    return _info.get("reason") or ""


def check():
    """检查点：已触发则立刻抛 Ejected，绝不等待当前步骤跑完。"""
    if _event.is_set():
        raise Ejected()


def sleep(seconds):
    """可被阀门立刻打断的 sleep：命中时抛 Ejected。"""
    if _event.wait(max(0.0, float(seconds))):
        raise Ejected()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def engage(reason_text="", source="unknown"):
    """触发紧急制动。幂等；返回本次是否为首次触发。"""
    global _report_path
    with _lock:
        if _event.is_set():
            return False
        _info["reason"] = str(reason_text or "").strip() or "用户触发 FORCE EJECT"
        _info["source"] = str(source or "unknown")
        _info["at"] = time.time()
    _event.set()

    print("[SimChat] FORCE EJECT 已触发（来源: %s）：%s" % (_info["source"], _info["reason"]))

    # 顺序很重要：先让所有循环看到 abort，再杀进程，最后落报告
    _abort_runs()
    _kill_processes()
    _run_cleanups()
    _mark_intentional_stop()
    try:
        _report_path = _write_report()
        print("[SimChat] FORCE EJECT 报告: %s" % _report_path)
    except Exception:
        traceback.print_exc()
    return True


def _abort_runs():
    try:
        from .agent import runs as runs_mod

        count = runs_mod.agent_runs.abort_all()
        print("[SimChat] 已中止 %d 个进行中的 Agent 运行" % count)
    except Exception as error:
        print("[SimChat] 中止 Agent 运行失败: %s" % error)


def _mark_intentional_stop():
    """告诉守护进程：这是主动停机，别再拉起 Web 进程。"""
    try:
        from . import lifecycle

        lifecycle.mark_intentional_stop()
    except Exception:
        pass


_cleanups = []


def register_cleanup(fn):
    """注册额外清理动作（可选，供后台线程/外部客户端使用）。"""
    if callable(fn) and fn not in _cleanups:
        _cleanups.append(fn)


def _run_cleanups():
    for fn in list(_cleanups):
        try:
            fn()
        except Exception:
            traceback.print_exc()


# ---------------- 子进程登记 ----------------

def track_process(proc):
    """登记需要被紧急终止的子进程（shell、MOD 沙箱等）。"""
    if proc is None:
        return None
    with _lock:
        _processes.append(proc)
    if _event.is_set():
        _kill_tree(proc)
    return proc


def _untrack_process(proc):
    with _lock:
        try:
            _processes.remove(proc)
        except ValueError:
            pass


def untrack_process(proc):
    """子进程结束后撤销登记。"""
    _untrack_process(proc)


def _kill_processes():
    with _lock:
        procs = list(_processes)
        _processes.clear()
    for proc in procs:
        _kill_tree(proc)


def _kill_tree(proc):
    pid = getattr(proc, "pid", None)
    if not pid:
        return
    try:
        if os.name == "nt":
            import subprocess

            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5,
            )
        else:
            import signal as _signal

            os.killpg(os.getpgid(pid), _signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------- 写类工具日志（供回滚） ----------------

def journal_start(run_id, tool_name, params, risk="write"):
    entry = {
        "ts": _now(),
        "run_id": run_id or "",
        "tool": tool_name,
        "risk": risk,
        "path": _extract_path(params),
        "status": "running",
        "ok": None,
        "error": "",
    }
    with _lock:
        _journal.append(entry)
    return entry


def journal_finish(entry, ok, error=""):
    if not isinstance(entry, dict):
        return
    entry["status"] = "done" if ok else "failed"
    entry["ok"] = bool(ok)
    entry["error"] = str(error or "")[:500]


def note_progress(run_id, data):
    """记录 Agent 循环的实时进度（轮次 / 计划完成度），供终止报告复盘。"""
    if not run_id:
        return
    record = {"run_id": run_id, "updated": _now()}
    record.update(data or {})
    with _lock:
        _progress[run_id] = record


def _extract_path(params):
    if not isinstance(params, dict):
        return ""
    for key in ("path", "file", "target", "dir", "directory"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------- 快照扩展 ----------------

def register_snapshot(name, provider):
    """注册额外快照来源（如自动化引擎），报告里会调用它。"""
    if callable(provider):
        _snapshots[name] = provider


def _collect_snapshots():
    out = {}
    for name, provider in list(_snapshots.items()):
        try:
            out[name] = provider()
        except Exception as error:
            out[name] = {"error": str(error)}
    return out


# ---------------- 报告 ----------------

def _collect_runs():
    try:
        from .agent import runs as runs_mod

        return runs_mod.agent_runs.snapshot()
    except Exception as error:
        return [{"error": str(error)}]


def _collect_pending():
    out = []
    try:
        from .agent import runs as runs_mod

        for run_id in runs_mod.list_pending_states():
            state = runs_mod.load_pending_state(run_id)
            if not state:
                continue
            pending = state.get("pending") or {}
            call = pending.get("call") or {}
            out.append({
                "run_id": run_id,
                "turn": pending.get("turn"),
                "awaiting_tool": call.get("tool") or "",
                "awaiting_params": call.get("params") or {},
                "plan_steps": state.get("plan_steps") or [],
                "plan_done": state.get("plan_done") or 0,
                "updated": state.get("created"),
            })
    except Exception as error:
        out.append({"error": str(error)})
    return out


def _rollback_hints():
    hints = []
    for entry in list(_journal):
        path = entry.get("path")
        if not path:
            continue
        if entry.get("status") == "running":
            state = "执行中被打断，可能已部分写入"
        elif entry.get("ok"):
            state = "已写入，需要还原"
        else:
            state = "执行失败，通常无需还原"
        hints.append({
            "path": path,
            "tool": entry.get("tool"),
            "run_id": entry.get("run_id"),
            "state": state,
            "how": "用 git checkout -- %s 还原；未纳入版本控制的文件请从备份或编辑器历史恢复" % path,
        })
    return hints


def _write_report():
    report = {
        "schema": 1,
        "engaged_at": _now(),
        "reason": _info.get("reason"),
        "source": _info.get("source"),
        "pid": _info.get("pid"),
        "uptime_seconds": int(time.time() - _info.get("started", time.time())),
        "runs": _collect_runs(),
        "progress": list(_progress.values()),
        "pending_approvals": _collect_pending(),
        "tool_journal": list(_journal),
        "processes": [{"pid": getattr(p, "pid", None)} for p in list(_processes)],
        "snapshots": _collect_snapshots(),
        "rollback": _rollback_hints(),
        "note": "FORCE EJECT 只记录受影响路径，不保存文件内容；回滚请依赖版本控制或备份。",
    }
    directory = os.path.join(_base_dir, "eject")
    os.makedirs(directory, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + ".json"
    path = os.path.join(directory, name)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
    os.replace(tmp, path)
    latest = os.path.join(directory, "latest.json")
    with open(latest + ".tmp", "w", encoding="utf-8") as handle:
        handle.write(payload)
    os.replace(latest + ".tmp", latest)
    return path


def latest_report_path():
    return _report_path


def latest_report():
    path = os.path.join(_base_dir, "eject", "latest.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


# ---------------- 触发通道 ----------------

def arm(data_root=None):
    """挂上标志文件监视与 POSIX 信号；幂等。"""
    global _base_dir, _armed, _watcher
    with _lock:
        if _armed:
            return True
        if data_root:
            _base_dir = os.path.abspath(data_root)
        _armed = True
    _install_signal()
    _watcher = threading.Thread(target=_watch_flag, name="simchat-force-eject", daemon=True)
    _watcher.start()
    return True


def disarm_watcher_only():
    """仅用于测试：停止文件监视线程，不解除已触发的状态。"""
    global _watcher, _armed
    with _lock:
        _armed = False
        watcher, _watcher = _watcher, None
    if watcher is not None and watcher.is_alive():
        watcher.join(timeout=1.0)


def _watch_flag():
    while not _event.is_set():
        for name in _FLAG_NAMES:
            path = os.path.join(_base_dir, name)
            if not os.path.exists(path):
                continue
            text = ""
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    text = handle.read().strip()
            except OSError:
                pass
            # 消费掉标志，避免重启后再次触发
            try:
                os.replace(path, path + ".fired")
            except OSError:
                pass
            engage(text or "标志文件触发", source="file")
            return
        time.sleep(_POLL_INTERVAL)


def _install_signal():
    if os.name == "nt":
        # Windows 的 SIGBREAK 已被 web/__main__ 的优雅停机占用，这里不抢
        return
    sig = getattr(signal, "SIGUSR1", None)
    if sig is None:
        return
    try:
        signal.signal(sig, lambda signum, frame: engage("SIGUSR1", source="signal"))
    except (OSError, ValueError):
        pass
