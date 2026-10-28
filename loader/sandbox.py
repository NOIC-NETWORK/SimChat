"""沙箱宿主侧（Phase 2 P2.3 + P2.4 追加 invoke 链路）。

职责：启动子进程、等 register 消息（含 modes + tools）、管理进程生命周期、
向子进程发送 invoke / invoke_tool 命令并返回响应。

每个 handle 是一个 dict，包含：
  ok          — bool（register 成功）
  message     — str（失败原因或空）
  mod_id      — MOD id
  proc        — subprocess.Popen 对象
  modes       — runner 回传的 ModeSpec 列表
  tools       — runner 回传的 ToolSpec 列表（P2.4 新增）
  _response_queue — queue.Queue（所有 runner stdout JSON 行的入口）
  started_at  — float(time.time())
  killed      — bool
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid


_SCRIPT = os.path.join(os.path.dirname(__file__), "sandbox_runner.py")
_DEFAULT_TIMEOUT = 30  # 秒：entry(api) 完成 + register 消息的最大等待
_INVOKE_TIMEOUT = 60   # 秒：单次 invoke / invoke_tool 等待上限


def run_isolated(package_dir, entry_spec, manifest, timeout=_DEFAULT_TIMEOUT):
    """启动子进程跑 MOD 的 entry(api)，等 register 消息，返回 handle dict。

    失败时不 raise，而是把 ok=False + message 塞进 handle。
    成功后 handle["proc"] 保持运行，handle["_response_queue"] 持续接收 stdout。
    """
    handle = {
        "ok": False, "message": "",
        "mod_id": manifest.get("id", "unknown"),
        "proc": None, "modes": [], "tools": [],
        "_response_queue": queue.Queue(),
        "started_at": time.time(), "killed": False,
    }

    # 启动 runner
    try:
        proc = subprocess.Popen(
            [
                sys.executable, _SCRIPT,
                "--package-dir", package_dir,
                "--entry-spec", entry_spec,
                "--manifest-json", json.dumps(manifest, ensure_ascii=False),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1,
        )
        handle["proc"] = proc
    except Exception as e:
        handle["message"] = "沙箱启动失败: %s" % e
        return handle

    # drain stderr（避免 pipe 满导致 runner 阻塞）
    def _stderr_drain():
        try:
            for _ in proc.stderr:
                pass
        except Exception:
            pass
    threading.Thread(target=_stderr_drain, daemon=True).start()

    # 持续读 stdout → 塞进 _response_queue（长驻线程）
    def _stdout_reader():
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    handle["_response_queue"].put(line)
        except Exception:
            pass
        # 进程退出后放哨兵
        try:
            handle["_response_queue"].put(None)
        except Exception:
            pass

    threading.Thread(target=_stdout_reader, daemon=True).start()

    # 等 register 消息
    try:
        first_line = handle["_response_queue"].get(timeout=timeout)
    except queue.Empty:
        _force_kill(proc, handle)
        handle["message"] = "沙箱启动超时（entry(api) %ds 内未完成）" % timeout
        return handle

    if first_line is None:
        _force_kill(proc, handle)
        handle["message"] = "沙箱静默退出"
        return handle

    try:
        msg = json.loads(first_line)
    except json.JSONDecodeError:
        _force_kill(proc, handle)
        handle["message"] = "沙箱输出格式非法: %s" % first_line[:80]
        return handle

    if msg.get("type") == "error":
        handle["message"] = "entry 执行失败: %s" % (msg.get("error") or "未知")
        return handle

    if msg.get("type") != "register":
        handle["message"] = "沙箱返回未预期的第一条消息: type=%s" % msg.get("type")
        return handle

    handle["ok"] = True
    handle["modes"] = msg.get("modes") or []
    handle["tools"] = msg.get("tools") or []
    return handle


# --------- invoke：宿主向子进程发请求并等响应 ---------

def invoke_mode(handle, mode_id, input_dict=None, timeout=_INVOKE_TIMEOUT):
    """向 sandbox 子进程发送 invoke 命令，等待 mode backend 执行完返回。

    返回 dict: {"ok": bool, "output": ..., "error": ..., "request_id": ...}
    """
    if not handle.get("ok") or handle.get("killed"):
        return {"ok": False, "error": "handle 不可用"}
    proc = handle["proc"]
    if proc is None or proc.poll() is not None:
        return {"ok": False, "error": "runner 进程已退出"}

    request_id = uuid.uuid4().hex
    msg = {
        "type": "invoke",
        "mode_id": mode_id,
        "input": dict(input_dict or {}),
        "request_id": request_id,
    }
    try:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
    except Exception as e:
        return {"ok": False, "error": "stdin 写入失败: %s" % e}

    # 从 queue 里等匹配响应
    q = handle["_response_queue"]
    while True:
        try:
            line = q.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": "invoke 超时（%ds）" % timeout}
        if line is None:
            return {"ok": False, "error": "runner 进程已退出"}
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        # 匹配：request_id 优先，mode_id 兜底
        if resp.get("request_id") == request_id:
            return resp
        if resp.get("type") == "result" and resp.get("mode_id") == mode_id and resp.get("request_id") is None:
            return resp


def invoke_tool(handle, tool_name, params=None, timeout=_INVOKE_TIMEOUT):
    """向 sandbox 子进程发送 invoke_tool 命令，等待 tool backend 执行完返回。

    返回 dict: {"ok": bool, "output": ..., "error": ..., "request_id": ..., "tool_name": ...}
    """
    if not handle.get("ok") or handle.get("killed"):
        return {"ok": False, "error": "handle 不可用"}
    proc = handle["proc"]
    if proc is None or proc.poll() is not None:
        return {"ok": False, "error": "runner 进程已退出"}

    request_id = uuid.uuid4().hex
    msg = {
        "type": "invoke_tool",
        "tool_name": tool_name,
        "params": dict(params or {}),
        "request_id": request_id,
    }
    try:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
    except Exception as e:
        return {"ok": False, "error": "stdin 写入失败: %s" % e}

    q = handle["_response_queue"]
    while True:
        try:
            line = q.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": "invoke_tool 超时（%ds）" % timeout}
        if line is None:
            return {"ok": False, "error": "runner 进程已退出"}
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        if resp.get("request_id") == request_id:
            return resp
        if resp.get("type") == "tool_result" and resp.get("tool_name") == tool_name and resp.get("request_id") is None:
            return resp


# --------- 生命周期清理 ---------

def _force_kill(proc, handle):
    """优雅 shutdown → terminate → force kill。"""
    if handle.get("killed"): return
    handle["killed"] = True
    try:
        try:
            proc.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
            proc.stdin.flush()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception:
        pass


# --------- 对外接口 ---------

_ACTIVE_HANDLES = []
_active_lock = threading.Lock()


def register_handle(handle):
    with _active_lock:
        if handle.get("ok"):
            _ACTIVE_HANDLES.append(handle)


def kill_handle(handle):
    _force_kill(handle["proc"], handle)
    with _active_lock:
        _ACTIVE_HANDLES[:] = [h for h in _ACTIVE_HANDLES if h is not handle]


def kill_all():
    """宿主退出时 atexit 调用。"""
    with _active_lock:
        snapshot = list(_ACTIVE_HANDLES)
        _ACTIVE_HANDLES.clear()
    for h in snapshot:
        _force_kill(h["proc"], h)
