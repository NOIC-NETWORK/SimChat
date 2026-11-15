"""沙箱子进程侧脚本（Phase 2 P2.3）。

**本脚本不应该被其他模块 import**——它通过 ``subprocess.Popen([sys.executable, __file__, ...])``
作为独立进程运行，宿主侧是 ``sandbox.run_isolated()``。

命令行参数（argparse）：
  --package-dir    MOD 包目录（绝对路径）
  --entry-spec     "module.path:attr" 格式的 entry 字符串
  --manifest-json  manifest.json 的完整 JSON 字符串（宿主传过来，避免子进程自己读）
  --services-json  （可选）宿主 services dict 的精简序列化（暂不实现，Phase 1 跳过）

能力：
  ✓ 崩溃隔离（进程死宿主活）
  ✓ 进程树闸门（capabilities.shell=false → monkey-patch subprocess.Popen）
  ✓ 文件系统闸门（capabilities.fs.read/write → open / os.* 路径白名单）
  ✓ 网络闸门（capabilities.net.domains → getaddrinfo / connect 域名白名单）
  ✓ 模式/工具注册元数据回传
  ✓ invoke / invoke_tool 请求处理（长驻）
  ✓ timeout（宿主侧 timeout 后 kill）
  ✓ 包内资产语义：cwd=包目录、python/ 与 scripts/ 进 sys.path、assets.root 可用
  ✓ 宿主服务 RPC：api.service("inference") 等通过 IPC 回调宿主
  ✓ 复用 SDK ModApi（ABI 与宿主侧同构）

不做：
  ✗ OS 级隔离（seccomp / 容器 / 用户态命名空间）：fs/net 闸门是 Python 层
    的权限边界，用于拦住"未声明权限"的正常代码路径，不是对抗恶意进程的沙箱
  ✗ sys.modules 黑名单
"""

import argparse
import importlib
import json
import os
import sys
import traceback
import uuid

# ---- 在 MOD 代码 import 之前，确保 SDK 包 simchat_mod 在 sys.path 里 ----
# runner 位于 simchat/loader/sandbox_runner.py → 向上一层 → simchat/ 目录
_SIMCHAT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDK_PYTHON   = os.path.join(_SIMCHAT_ROOT, "sdk", "python")
if _SDK_PYTHON not in sys.path:
    sys.path.insert(0, _SDK_PYTHON)

from simchat_mod import ModApi  # noqa: E402  (SDK 路径注入后再导入)


# ---- IPC 协议输出：宿主只消费带私有前缀的行，MOD 自己的 print 不会污染协议 ----
_IPC_PREFIX = "@@simchat-ipc@@"


def _ipc(payload):
    sys.stdout.write(_IPC_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ============================================================================
# 1. monkey-patch subprocess.Popen（在任何 MOD 代码跑之前做）
# ============================================================================

def _patch_subprocess(manifest):
    """capabilities.shell=false 时禁止 MOD 代码创建子进程。

    Phase 1 只 patch subprocess.Popen；os.system / os.popen / multiprocessing
    暂不覆盖（留后续补丁）。一个标记 token 让 runner 自身的内部调用能绕过。
    """
    caps = (manifest.get("capabilities") or {})
    shell_allowed = bool(caps.get("shell", False))
    if shell_allowed:
        return  # 不 patch

    import subprocess
    _OriginalPopen = subprocess.Popen

    def _GuardedPopen(*args, **kwargs):
        caller = kwargs.pop("_sandbox_internal", None)
        if caller:
            return _OriginalPopen(*args, **kwargs)
        raise PermissionError(
            "MOD 未声明 capabilities.shell=true，禁止创建子进程 "
            "(args=%s)" % (args[:2],)
        )

    subprocess.Popen = _GuardedPopen


# ============================================================================
# 1b. 文件系统闸门：capabilities.fs 是白名单，未声明的路径一律 PermissionError
# ============================================================================

# 宿主任命的三个 MOD 专属目录（读写豁免于 capability 声明）：
_UPLOADS_DIR = os.path.join(_SIMCHAT_ROOT, "uploads")


def _norm_path(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _within(target, root):
    if target == root:
        return True
    return target.startswith(root.rstrip("\\/") + os.sep)


class _FsGuard(object):
    """把 fs 权限收敛成两组根目录；写入额外要求路径落在 write 白名单内。"""

    def __init__(self, read_roots, write_roots):
        self._read = []
        seen = set()
        for root in list(read_roots) + list(write_roots):
            if not root:
                continue
            normalized = _norm_path(root)
            if normalized not in seen:
                seen.add(normalized)
                self._read.append(normalized)
        self._write = []
        for root in write_roots:
            if root:
                self._write.append(_norm_path(root))

    def allows(self, path, write=False):
        try:
            target = _norm_path(path)
        except Exception:
            return False
        roots = self._write if write else self._read
        return any(_within(target, root) for root in roots)

    def check(self, path, write=False):
        if not self.allows(path, write):
            raise PermissionError(
                "MOD 未声明 capabilities.fs.%s 覆盖该路径: %s"
                % ("write" if write else "read", path)
            )


def _fs_roots(manifest, package_dir, data_dir, workspace_dir):
    """把 manifest 的 scope 名字解析成真实目录，返回 (read_roots, write_roots)。"""
    caps = manifest.get("capabilities") or {}
    fs = caps.get("fs") or {}
    if not isinstance(fs, dict):
        fs = {}

    # 运行时只读根：解释器、site-packages、SDK —— 允许第三方库读自身数据（如 CA 证书）
    runtime_roots = [sys.prefix, sys.base_prefix, os.path.dirname(os.__file__), _SDK_PYTHON]
    try:
        import site

        runtime_roots.extend(site.getsitepackages() or [])
    except Exception:
        pass

    import tempfile

    temp_dir = tempfile.gettempdir()
    # 包目录（资产）、data_dir、uploads：宿主授予的基础可访问范围。
    # 临时目录不默认授予（可用 scope="temp" 显式声明）。
    read_roots = [package_dir, data_dir, _UPLOADS_DIR] + runtime_roots
    write_roots = [data_dir, _UPLOADS_DIR]

    def resolve(scope):
        if not isinstance(scope, str) or not scope.strip():
            return None
        scope = scope.strip()
        if scope == "workspace":
            return workspace_dir
        if scope in ("mod-data", "data"):
            return data_dir
        if scope in ("package", "assets"):
            return package_dir
        if scope == "uploads":
            return _UPLOADS_DIR
        if scope == "temp":
            return temp_dir
        if os.path.isabs(scope):
            return scope
        # 相对子路径：优先相对工作目录，未配置时相对 data_dir
        return os.path.join(workspace_dir or data_dir or package_dir, scope)

    for scope in fs.get("read") or []:
        resolved = resolve(scope)
        if resolved:
            read_roots.append(resolved)
    for scope in fs.get("write") or []:
        resolved = resolve(scope)
        if resolved:
            write_roots.append(resolved)
    return read_roots, write_roots


class _PlainCallable(object):
    """非描述符包装。

    os.open 之类的模块函数会被第三方（如 pathlib._NormalAccessor.open = os.open）
    当作类属性捕获；普通函数作为类属性会变成绑定方法，导致首个参数错位。
    用可调用实例替换即可避免这种情况。
    """

    __slots__ = ("_fn",)

    def __init__(self, fn):
        self._fn = fn

    def __call__(self, *args, **kwargs):
        return self._fn(*args, **kwargs)

    def __repr__(self):
        return "<sandbox guard %r>" % (self._fn,)


def _install_fs_guard(manifest, package_dir, data_dir, workspace_dir):
    """patch open / os.*，让未声明的 fs 访问失败。"""
    read_roots, write_roots = _fs_roots(manifest, package_dir, data_dir, workspace_dir)
    guard = _FsGuard(read_roots, write_roots)

    import builtins
    import io

    original_open = io.open

    def _guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)) and isinstance(mode, str):
            guard.check(os.fsdecode(file), write=any(ch in mode for ch in "wax+"))
        return original_open(file, mode, *args, **kwargs)

    builtins.open = _PlainCallable(_guarded_open)
    io.open = _PlainCallable(_guarded_open)

    original_os_open = os.open

    def _guarded_os_open(path, flags, *args, **kwargs):
        write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if isinstance(path, (str, bytes, os.PathLike)):
            guard.check(os.fsdecode(path), write=write)
        return original_os_open(path, flags, *args, **kwargs)

    os.open = _PlainCallable(_guarded_os_open)

    def _wrap_path_fn(original, write):
        def _patched(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                guard.check(os.fsdecode(path), write=write)
            return original(path, *args, **kwargs)

        return _PlainCallable(_patched)

    for name in ("remove", "unlink", "rmdir", "mkdir", "makedirs"):
        original = getattr(os, name, None)
        if original is not None:
            setattr(os, name, _wrap_path_fn(original, True))
    for name in ("listdir", "scandir"):
        original = getattr(os, name, None)
        if original is not None:
            setattr(os, name, _wrap_path_fn(original, False))

    def _wrap_rename(original):
        def _patched(src, dst, *args, **kwargs):
            if isinstance(src, (str, bytes, os.PathLike)):
                guard.check(os.fsdecode(src), write=True)
            if isinstance(dst, (str, bytes, os.PathLike)):
                guard.check(os.fsdecode(dst), write=True)
            return original(src, dst, *args, **kwargs)

        return _PlainCallable(_patched)

    for name in ("rename", "replace"):
        original = getattr(os, name, None)
        if original is not None:
            setattr(os, name, _wrap_rename(original))

    return guard


# ============================================================================
# 1c. 网络闸门：capabilities.net.domains 白名单（含 *.example.com 前缀通配）
# ============================================================================

class _NetGuard(object):
    def __init__(self, domains):
        self.domains = [str(item).strip().lower().rstrip(".") for item in (domains or [])]
        self.allow_all = "*" in self.domains
        self.allowed_ips = set()

    def host_allowed(self, host):
        if self.allow_all:
            return True
        host = str(host or "").strip().lower().rstrip(".")
        if not host:
            return False
        for pattern in self.domains:
            if pattern.startswith("*."):
                suffix = pattern[1:]  # ".example.com"
                if host.endswith(suffix):
                    return True
            elif host == pattern:
                return True
        return False

    def check(self, host):
        if not self.host_allowed(host):
            raise PermissionError(
                "MOD 未声明 capabilities.net.domains 覆盖该主机: %s" % host
            )


def _install_net_guard(manifest):
    caps = manifest.get("capabilities") or {}
    net = caps.get("net") or {}
    domains = net.get("domains") if isinstance(net, dict) else None
    guard = _NetGuard(domains)

    import socket

    original_getaddrinfo = socket.getaddrinfo

    def _guarded_getaddrinfo(host, port, *args, **kwargs):
        # host=None 用于 bind / AI_PASSIVE，不属于外连，不拦
        if host is None or host == "":
            return original_getaddrinfo(host, port, *args, **kwargs)
        guard.check(host)
        infos = original_getaddrinfo(host, port, *args, **kwargs)
        for info in infos:
            try:
                guard.allowed_ips.add(info[4][0])
            except Exception:
                pass
        return infos

    socket.getaddrinfo = _guarded_getaddrinfo

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def _check_sockaddr(sock, address):
        if getattr(sock, "family", None) not in (socket.AF_INET, socket.AF_INET6):
            return
        if not isinstance(address, tuple) or not address:
            return
        ip = address[0]
        if guard.allow_all or ip in guard.allowed_ips or guard.host_allowed(ip):
            return
        raise PermissionError(
            "MOD 未声明 capabilities.net.domains 覆盖该地址: %s" % ip
        )

    def _guarded_connect(self, address):
        _check_sockaddr(self, address)
        return original_connect(self, address)

    def _guarded_connect_ex(self, address):
        _check_sockaddr(self, address)
        return original_connect_ex(self, address)

    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    return guard


# ============================================================================
# 2. 宿主服务代理 — api.service(name) 通过 IPC 回调宿主进程
# ============================================================================

_PENDING_LINES = []  # service 响应等待期间顺带读到的非 service_result 行


def _next_line():
    """从 stdin 读一行；优先消费等待服务响应时暂存的行。"""
    if _PENDING_LINES:
        return _PENDING_LINES.pop(0)
    return sys.stdin.readline()


class _ServiceProxy(object):
    """宿主服务的跨进程代理：任意方法调用 → service_call → 等 service_result。

    方法返回值若是宿主侧的对象（如 skill_manager.get_registry()），宿主会回一个
    引用描述，这里自动包装成新的 _ServiceProxy，链式调用可继续。
    """

    def __init__(self, name):
        self._name = name

    def __getattr__(self, method):
        if method.startswith("__"):
            raise AttributeError(method)

        def _call(*args, **kwargs):
            output = _call_service(self._name, method, list(args), kwargs)
            if isinstance(output, dict) and "__service_ref__" in output:
                return _ServiceProxy("@ref:" + output["__service_ref__"])
            return output

        return _call

    def __repr__(self):
        return "<host service %s>" % self._name


def _call_service(service_name, method, args, kwargs):
    """向宿主发 service_call 并阻塞等待匹配的 service_result。"""
    request_id = uuid.uuid4().hex
    _ipc({
        "type": "service_call",
        "request_id": request_id,
        "service": service_name,
        "method": method,
        "args": args,
        "kwargs": kwargs,
    })
    while True:
        line = _next_line()
        if not line:
            raise RuntimeError("宿主连接已关闭（service=%s.%s）" % (service_name, method))
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "service_result" and msg.get("request_id") == request_id:
            if not msg.get("ok"):
                raise RuntimeError(msg.get("error") or "宿主服务调用失败")
            return msg.get("output")
        # 非本次服务响应：压回待处理队列，交给主循环
        _PENDING_LINES.append(line)


def _build_services(names):
    """按宿主声明的服务名构建代理 dict；未声明的服务保持缺失（service() 返回 None）。"""
    return {name: _ServiceProxy(name) for name in (names or [])}


def _emit_event(name, payload=None):
    """ModApi.emit_event 的 IPC 实现：事件由宿主读取，不阻塞。"""
    _ipc({"type": "event", "name": name, "payload": payload or {}})


# ============================================================================
# 3. 入口
# ============================================================================

def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--entry-spec", required=True)
    parser.add_argument("--manifest-json", required=True)
    parser.add_argument("--data-dir", default=None)   # 每个包独立的可写数据目录
    parser.add_argument("--services-json", default="[]")  # 宿主可用服务名列表
    parser.add_argument("--workspace-dir", default=None)  # 用户工作目录（fs scope=workspace）
    args = parser.parse_args()

    manifest = json.loads(args.manifest_json)
    mod_id = manifest.get("id", "unknown")
    package_dir = os.path.abspath(args.package_dir)
    data_dir = os.path.abspath(args.data_dir) if args.data_dir else None
    workspace_dir = os.path.abspath(args.workspace_dir) if args.workspace_dir else None
    service_names = json.loads(args.services_json or "[]")

    # 3a. patch subprocess（在 MOD 代码 import 之前）
    _patch_subprocess(manifest)

    # 3b. 资产语义：cwd 切到包目录，python/ 与 scripts/ 进 sys.path
    try:
        os.chdir(package_dir)
    except OSError as error:
        print("[sandbox] cwd 切换失败: %s" % error, file=sys.stderr)
    for sub in ("python", "scripts"):
        sub_dir = os.path.join(package_dir, sub)
        if os.path.isdir(sub_dir) and sub_dir not in sys.path:
            sys.path.insert(0, sub_dir)

    # 3c. assets.root：解析成绝对路径交给 MOD（缺省回落到包目录）
    assets_root = None
    assets = manifest.get("assets") or {}
    if isinstance(assets, dict) and isinstance(assets.get("root"), str) and assets["root"]:
        assets_root = os.path.abspath(os.path.join(package_dir, assets["root"]))

    # 3d. 能力闸门（在任何 MOD 代码被 import 之前装好）
    _install_fs_guard(manifest, package_dir, data_dir, workspace_dir)
    _install_net_guard(manifest)

    try:
        # 3e. 解析 entry spec
        manifest_type = manifest.get("type", "")
        if manifest_type == "automation" and ":" not in args.entry_spec:
            # automation 的 entry 可以是 flow.json 路径（不需要执行 Python entry）
            _ipc({"type": "register", "modes": [], "tools": []})
            sys.exit(0)

        module_name, attribute = args.entry_spec.split(":")
        module = importlib.import_module(module_name)
        entry = getattr(module, attribute)
        if not callable(entry):
            raise TypeError("entry 不可调用: %s" % args.entry_spec)

        # 3f. 复用 SDK ModApi，宿主服务通过 IPC 代理注入
        api = ModApi(
            mod_id=mod_id,
            manifest=manifest,
            package_dir=package_dir,
            services=_build_services(service_names),
            emit_event=_emit_event,
            data_dir=data_dir,
            assets_dir=assets_root,
        )
        entry(api)

        # 3g. stdout 写 register 消息（宿主侧 lifecycle 等待这条）
        # sanitize：把 type 对象转成字符串（{"text": str} → {"text": "str"}）
        def _sanitize(obj):
            if isinstance(obj, type):
                return obj.__name__
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        _ipc({
            "type": "register",
            "modes": [_sanitize(m) for m in api.modes],
            "tools": [_sanitize(t) for t in api.tools],
        })

    except Exception as e:
        tb = traceback.format_exc()
        _ipc({"type": "error", "stage": "entry",
              "error": str(e), "traceback": tb})
        sys.exit(1)

    # 3h. 进入 stdin JSON 行循环（长驻）
    _read_loop(api)


def _read_loop(api):
    """循环读 stdin JSON 行，处理 invoke/ping/shutdown。"""
    while True:
        line = _next_line()
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("type")
        except json.JSONDecodeError:
            continue

        if cmd == "shutdown":
            _ipc({"type": "pong"})
            sys.exit(0)

        elif cmd == "ping":
            _ipc({"type": "pong"})

        elif cmd == "invoke":
            _handle_invoke(api, msg)

        elif cmd == "invoke_tool":
            _handle_invoke_tool(api, msg)

        elif cmd in ("service_result", "event"):
            # 服务响应只在 _call_service 等待期间消费；事件只由宿主处理
            continue

        else:
            _ipc({"type": "error", "stage": "read_loop",
                  "error": "未知命令 type=%s" % cmd})


def _handle_invoke(api, msg):
    """invoke 命令处理：根据 mode_id 找已注册的 mode，调 backend。

    Phase 1 backend 是 "module.path:attr" 字符串，本地 import 后直接调。
    入参：msg.input dict；返回：json-serializable 对象。
    """
    mode_id = msg.get("mode_id")
    request_id = msg.get("request_id")
    mode = next((m for m in api.modes if m["id"] == mode_id), None)

    def _tag(resp):
        if request_id is not None:
            resp["request_id"] = request_id
        return resp

    if mode is None:
        _ipc(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                   "error": "mode 未在本进程注册"}))
        return

    backend_ref = mode.get("backend") or ""
    if ":" not in backend_ref:
        _ipc(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                   "error": "backend 未声明"}))
        return
    backend, attr = backend_ref.split(":", 1)

    try:
        if backend not in sys.modules:
            importlib.import_module(backend)
        mod = sys.modules[backend]
        fn = getattr(mod, attr)
        if not callable(fn):
            raise TypeError("backend %s:%s 不可调用" % (backend, attr))

        input_dict = msg.get("input") or {}
        if isinstance(input_dict, dict):
            result = fn(**input_dict)
        else:
            result = fn(input_dict)

        try:
            json.dumps(result)
        except (TypeError, ValueError):
            result = repr(result)

        _ipc(_tag({"type": "result", "mode_id": mode_id, "ok": True,
                   "output": result}))

    except Exception as e:
        tb = traceback.format_exc()
        _ipc(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                   "error": str(e), "traceback": tb}))


def _handle_invoke_tool(api, msg):
    """invoke_tool 命令处理（P2.4 新增）：按 tool name 找已注册的 tool spec，
    import backend 后调 execute(params)。入参 params 是 dict；返回 dict。"""
    tool_name = msg.get("tool_name")
    request_id = msg.get("request_id")
    tool = next((t for t in api.tools if t["name"] == tool_name), None)

    def _tag(resp):
        if request_id is not None:
            resp["request_id"] = request_id
        return resp

    if tool is None:
        _ipc(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                   "error": "tool 未在本进程注册"}))
        return

    backend_ref = tool.get("backend") or ""
    if ":" not in backend_ref:
        _ipc(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                   "error": "backend 未声明"}))
        return
    backend, attr = backend_ref.split(":", 1)

    try:
        if backend not in sys.modules:
            importlib.import_module(backend)
        mod = sys.modules[backend]
        fn = getattr(mod, attr)
        if not callable(fn):
            raise TypeError("tool backend %s:%s 不可调用" % (backend, attr))

        params = msg.get("params") or {}
        result = fn(params)

        try:
            json.dumps(result)
        except (TypeError, ValueError):
            result = repr(result)

        _ipc(_tag({"type": "tool_result", "tool_name": tool_name, "ok": True,
                   "output": result}))

    except Exception as e:
        tb = traceback.format_exc()
        _ipc(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                   "error": str(e), "traceback": tb}))


if __name__ == "__main__":
    _main()
