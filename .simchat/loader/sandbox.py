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
  _response_queue — queue.Queue（register 阶段的响应入口；register 后改走 _waiters）
  _waiters    — {request_id: future}（P2 新增：per-request 响应队列）
  started_at  — float(time.time())
  killed      — bool

并发语义（P2）：host 侧每个 invoke/invoke_tool 调用各自注册一个 future，
stdout 读线程按 request_id 把响应投递到对应 future，调用方互不消费彼此的响应。
runner 仍是单线程执行，因此同一 handle 上的并发调用会在子进程内串行完成，
但宿主侧不会再串包。
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
_IPC_PREFIX = "@@simchat-ipc@@"  # 与 sandbox_runner 约定：只有带前缀的行才是协议


def run_isolated(package_dir, entry_spec, manifest, timeout=_DEFAULT_TIMEOUT,
                 data_dir=None, services=None, workspace_dir=None):
    """启动子进程跑 MOD 的 entry(api)，等 register 消息，返回 handle dict。

    失败时不 raise，而是把 ok=False + message 塞进 handle。
    成功后 handle["proc"] 保持运行，handle["_response_queue"] 持续接收 stdout。

    data_dir: 该包独立的可写数据目录，runner 侧 ModApi 持有此路径。
    services: 宿主只读服务字典（name → 对象），runner 侧 api.service(name)
              会通过 IPC 回调到这里执行；对象方法返回值可被自动引用传递。
    workspace_dir: 用户选择的工作目录，供 capabilities.fs 的 workspace scope 解析。
    """
    handle = {
        "ok": False, "message": "",
        "mod_id": manifest.get("id", "unknown"),
        "proc": None, "modes": [], "tools": [], "agent_presets": [],
        "_response_queue": queue.Queue(),
        "_waiters": {},
        "_waiters_lock": threading.Lock(),
        "_futures_enabled": False,
        "_stdin_lock": threading.Lock(),
        "_services": dict(services or {}),
        "_service_refs": {},
        "started_at": time.time(), "killed": False,
    }

    # 启动 runner
    # 管道编码固定 UTF-8：Windows 下子进程默认按 locale（cp936）编码 stdin/stdout，
    # 宿主按 UTF-8 读取时会把 MOD/Skill 的中文 meta 与工具输出全解成替换字符。
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    try:
        args = [
            sys.executable, _SCRIPT,
            "--package-dir", package_dir,
            "--entry-spec", entry_spec,
            "--manifest-json", json.dumps(manifest, ensure_ascii=False),
            "--services-json", json.dumps(sorted(handle["_services"])),
        ]
        if data_dir:
            args += ["--data-dir", data_dir]
        if workspace_dir:
            args += ["--workspace-dir", workspace_dir]
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1,
            env=child_env,
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

    # 持续读 stdout → 协议行按 request_id 路由；service_call 交给独立线程处理
    def _stdout_reader():
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if not line.startswith(_IPC_PREFIX):
                    # MOD 自己的 print：不参与协议，转到宿主 stderr 便于排查
                    try:
                        sys.stderr.write("[mod:%s] %s\n" % (handle.get("mod_id", "?"), line[:500]))
                        sys.stderr.flush()
                    except Exception:
                        pass
                    continue
                payload = line[len(_IPC_PREFIX):].strip()
                if not payload:
                    continue
                try:
                    msg = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "service_call":
                    # 服务调用可能很慢（如推理），独立线程执行，不阻塞 stdout 读取
                    threading.Thread(target=_dispatch_service, args=(handle, msg),
                                     daemon=True).start()
                    continue
                if handle.get("_futures_enabled"):
                    _route_response(handle, msg)
                else:
                    # register 阶段仍走单队列（此时还没有 invoke 请求）
                    handle["_response_queue"].put(payload)
        except Exception:
            pass
        # 进程退出：唤醒所有等待者
        try:
            handle["_response_queue"].put(None)
        except Exception:
            pass
        _fail_waiters(handle)

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
    handle["agent_presets"] = msg.get("agent_presets") or []
    # register 之后切换到 per-request future 路由
    handle["_futures_enabled"] = True
    return handle


# --------- 宿主服务 RPC：runner 的 service_call 在这里执行并回写 ---------

def _write_command(handle, payload):
    """线程安全地向 runner stdin 写一行 JSON。"""
    proc = handle.get("proc")
    if proc is None or proc.stdin is None:
        raise RuntimeError("runner 不可用")
    data = json.dumps(payload, ensure_ascii=False) + "\n"
    with handle["_stdin_lock"]:
        proc.stdin.write(data)
        proc.stdin.flush()


def _jsonable(value):
    """尽量转成 JSON 可序列化结构；不可序列化的对象转为宿主引用。"""
    try:
        json.dumps(value)
        return value, False
    except (TypeError, ValueError):
        return value, True


def _dispatch_service(handle, msg):
    """执行一次宿主服务调用，把结果写回 runner。

    返回值若不可 JSON 序列化（典型是 get_registry() 这类对象），分配一个引用 id，
    runner 侧会包装成新的代理，后续调用继续走 service_call。
    """
    request_id = msg.get("request_id")
    service_name = msg.get("service") or ""
    method = msg.get("method") or ""
    args = msg.get("args") or []
    kwargs = msg.get("kwargs") or {}

    def _reply(ok, output=None, error=None):
        try:
            _write_command(handle, {
                "type": "service_result", "request_id": request_id,
                "ok": ok, "output": output, "error": error,
            })
        except Exception:
            pass

    if service_name.startswith("@ref:"):
        target = handle["_service_refs"].get(service_name[len("@ref:"):])
    else:
        target = handle["_services"].get(service_name)
    if target is None:
        _reply(False, error="宿主未提供服务: %s" % service_name)
        return
    fn = getattr(target, method, None)
    if not callable(fn):
        _reply(False, error="服务 %s 没有方法 %s" % (service_name, method))
        return

    try:
        result = fn(*args, **kwargs)
        value, needs_ref = _jsonable(result)
        if needs_ref and result is not None:
            ref_id = uuid.uuid4().hex
            handle["_service_refs"][ref_id] = result
            value = {"__service_ref__": ref_id}
        _reply(True, output=value)
    except Exception as error:
        _reply(False, error="%s: %s" % (type(error).__name__, error))


# --------- invoke：宿主向子进程发请求并等响应（per-request future） ---------

def _register_waiter(handle, request_id, matcher):
    """为一次请求注册独立响应队列。matcher 用于兜底匹配无 request_id 的旧响应。"""
    waiter = {"queue": queue.Queue(), "matcher": matcher}
    with handle["_waiters_lock"]:
        handle["_waiters"][request_id] = waiter
    return waiter


def _discard_waiter(handle, request_id):
    with handle["_waiters_lock"]:
        handle["_waiters"].pop(request_id, None)


def _route_response(handle, resp):
    """把一条协议响应投递给等待它的调用方；request_id 优先，type 兜底。"""
    if resp.get("type") == "pong":
        return
    request_id = resp.get("request_id")
    waiter = None
    with handle["_waiters_lock"]:
        if request_id:
            waiter = handle["_waiters"].get(request_id)
        if waiter is None:
            for candidate in handle["_waiters"].values():
                try:
                    if candidate["matcher"](resp):
                        waiter = candidate
                        break
                except Exception:
                    continue
    if waiter is None:
        try:
            sys.stderr.write("[mod:%s] 丢弃无主响应: %s\n" % (
                handle.get("mod_id", "?"),
                json.dumps(resp, ensure_ascii=False)[:200],
            ))
        except Exception:
            pass
        return
    waiter["queue"].put(resp)


def _fail_waiters(handle):
    """runner 退出时给每个等待者一个哨兵，避免调用方空等到超时。"""
    with handle["_waiters_lock"]:
        waiters = list(handle["_waiters"].values())
    for waiter in waiters:
        try:
            waiter["queue"].put(None)
        except Exception:
            pass


def _await(handle, waiter, request_id, timeout, label):
    try:
        resp = waiter["queue"].get(timeout=timeout)
    except queue.Empty:
        return {"ok": False, "error": "%s 超时（%ds）" % (label, timeout)}
    finally:
        _discard_waiter(handle, request_id)
    if resp is None:
        return {"ok": False, "error": "runner 进程已退出"}
    return resp


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
    waiter = _register_waiter(
        handle, request_id,
        lambda resp: resp.get("type") == "result" and resp.get("mode_id") == mode_id,
    )
    try:
        _write_command(handle, msg)
    except Exception as e:
        _discard_waiter(handle, request_id)
        return {"ok": False, "error": "stdin 写入失败: %s" % e}
    return _await(handle, waiter, request_id, timeout, "invoke")


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
    waiter = _register_waiter(
        handle, request_id,
        lambda resp: resp.get("type") == "tool_result" and resp.get("tool_name") == tool_name,
    )
    try:
        _write_command(handle, msg)
    except Exception as e:
        _discard_waiter(handle, request_id)
        return {"ok": False, "error": "stdin 写入失败: %s" % e}
    return _await(handle, waiter, request_id, timeout, "invoke_tool")


# --------- 生命周期清理 ---------

def _force_kill(proc, handle):
    """优雅 shutdown → terminate → force kill。"""
    if handle.get("killed"): return
    handle["killed"] = True
    try:
        try:
            _write_command(handle, {"type": "shutdown"})
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
