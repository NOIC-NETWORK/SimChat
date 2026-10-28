"""沙箱子进程侧脚本（Phase 2 P2.3）。

**本脚本不应该被其他模块 import**——它通过 ``subprocess.Popen([sys.executable, __file__, ...])``
作为独立进程运行，宿主侧是 ``sandbox.run_isolated()``。

命令行参数（argparse）：
  --package-dir    MOD 包目录（绝对路径）
  --entry-spec     "module.path:attr" 格式的 entry 字符串
  --manifest-json  manifest.json 的完整 JSON 字符串（宿主传过来，避免子进程自己读）
  --services-json  （可选）宿主 services dict 的精简序列化（暂不实现，Phase 1 跳过）

Phase 1 能力：
  ✓ 崩溃隔离（进程死宿主活）
  ✓ 进程树闸门（capabilities.shell=false → monkey-patch subprocess.Popen）
  ✓ 模式注册元数据回传
  ✓ invoke 请求处理（长驻）
  ✓ timeout（宿主侧 timeout 后 kill）

Phase 1 不做：
  ✗ 文件系统/网络/seccomp 隔离
  ✗ sys.modules 黑名单
  ✗ services 透传（runner 侧 ModApi.services 是空 dict）
"""

import argparse
import importlib
import io
import json
import os
import sys
import traceback

# ---- 在 MOD 代码 import 之前，确保 SDK 包 simchat_mod 在 sys.path 里 ----
# runner 位于 simchat/loader/sandbox_runner.py → 向上一层 → simchat/ 目录
_SIMCHAT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDK_PYTHON   = os.path.join(_SIMCHAT_ROOT, "sdk", "python")
if _SDK_PYTHON not in sys.path:
    sys.path.insert(0, _SDK_PYTHON)


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
# 2. LocalModApi — 最小化 SDK ModApi 的 runner 侧实现
# ============================================================================

class _LocalModApi(object):
    """runner 侧 ModApi：只实现 entry(api) 调用所需的最小接口。

    Phase 1 只存已注册的 ModeSpec / ToolSpec 元数据，不承载任何宿主服务引用。
    """
    def __init__(self, mod_id, manifest, package_dir, services=None):
        self.mod_id = mod_id
        self.manifest = manifest
        self.package_dir = package_dir
        self.services = services or {}
        self.modes = []  # ModeSpec dict 列表
        self.tools = []  # ToolSpec dict 列表（P2.4 新增）

    def register_mode(self, spec):
        """接收 SDK ModeSpec 对象（也兼容 dict），序列化成 dict 存起来。"""
        try:
            def _g(attr, default=None):
                v = getattr(spec, attr, None)
                if v is None and hasattr(spec, "get"):
                    v = spec.get(attr)
                return v

            spec_dict = {
                "id": _g("id"),
                "label": _g("label"),
                "icon": _g("icon"),
                "order": _g("order"),
                "frontend_entry": _g("frontend_entry"),
                "backend": _g("backend"),
                "cost": _g("cost"),
                "hook": _g("hook"),
            }
            if spec_dict.get("backend") and ":" in spec_dict["backend"]:
                mod_name, attr_name = spec_dict["backend"].split(":", 1)
                spec_dict["_backend_module"] = mod_name
                spec_dict["_backend_attr"] = attr_name
            self.modes.append(spec_dict)
        except Exception as e:
            print("[sandbox] register_mode 失败: %s" % e, file=sys.stderr)

    def register_tool(self, spec):
        """接收 SDK ToolSpec 对象（也兼容 dict），序列化成 dict 存起来。P2.4 新增。"""
        try:
            def _g(attr, default=None):
                v = getattr(spec, attr, None)
                if v is None and hasattr(spec, "get"):
                    v = spec.get(attr)
                return v

            spec_dict = {
                "name": _g("name"),
                "label": _g("label"),
                "description": _g("description"),
                "risk": _g("risk"),
                "usage": _g("usage"),
                "params_schema": _g("params_schema"),
                "backend": _g("backend"),
                "triggers": _g("triggers"),
                "input_schema": _g("input_schema"),
            }
            if spec_dict.get("backend") and ":" in spec_dict["backend"]:
                mod_name, attr_name = spec_dict["backend"].split(":", 1)
                spec_dict["_backend_module"] = mod_name
                spec_dict["_backend_attr"] = attr_name
            self.tools.append(spec_dict)
        except Exception as e:
            print("[sandbox] register_tool 失败: %s" % e, file=sys.stderr)


# ============================================================================
# 3. 入口
# ============================================================================

def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--entry-spec", required=True)
    parser.add_argument("--manifest-json", required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest_json)
    mod_id = manifest.get("id", "unknown")
    package_dir = os.path.abspath(args.package_dir)

    # 3a. patch subprocess（在 MOD 代码 import 之前）
    _patch_subprocess(manifest)

    # 3b. sys.path 注入 MOD python/ 目录
    python_dir = os.path.join(package_dir, "python")
    if os.path.isdir(python_dir) and python_dir not in sys.path:
        sys.path.insert(0, python_dir)

    try:
        # 3c. 解析 entry spec
        module_name, attribute = args.entry_spec.split(":")
        module = importlib.import_module(module_name)
        entry = getattr(module, attribute)
        if not callable(entry):
            raise TypeError("entry 不可调用: %s" % args.entry_spec)

        # 3d. 创建 runner 侧 ModApi，调 entry(api)
        api = _LocalModApi(
            mod_id=mod_id, manifest=manifest, package_dir=package_dir,
            services={}  # Phase 1 不透传宿主 services
        )
        entry(api)

        # 3e. stdout 写 register 消息（宿主侧 lifecycle 等待这条）
        # sanitize：把 type 对象转成字符串（{"text": str} → {"text": "str"}）
        def _sanitize(obj):
            if isinstance(obj, type):
                return obj.__name__
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        modes_clean = []
        for m in api.modes:
            clean = {k: _sanitize(v) for k, v in m.items() if not k.startswith("_")}
            modes_clean.append(clean)
        tools_clean = []
        for t in api.tools:
            clean = {k: _sanitize(v) for k, v in t.items() if not k.startswith("_")}
            tools_clean.append(clean)
        print(json.dumps({"type": "register", "modes": modes_clean, "tools": tools_clean},
                         ensure_ascii=False), flush=True)

    except Exception as e:
        tb = traceback.format_exc()
        print(json.dumps({"type": "error", "stage": "entry",
                          "error": str(e), "traceback": tb},
                         ensure_ascii=False), flush=True)
        sys.exit(1)

    # 3f. 进入 stdin JSON 行循环（长驻）
    _read_loop(api)


def _read_loop(api):
    """循环读 stdin JSON 行，处理 invoke/ping/shutdown。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            cmd = msg.get("type")
        except json.JSONDecodeError:
            continue

        if cmd == "shutdown":
            print(json.dumps({"type": "pong"}, ensure_ascii=False), flush=True)
            sys.exit(0)

        elif cmd == "ping":
            print(json.dumps({"type": "pong"}, ensure_ascii=False), flush=True)

        elif cmd == "invoke":
            _handle_invoke(api, msg)

        elif cmd == "invoke_tool":
            _handle_invoke_tool(api, msg)

        else:
            print(json.dumps({"type": "error", "stage": "read_loop",
                              "error": "未知命令 type=%s" % cmd},
                             ensure_ascii=False), flush=True)


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
        print(json.dumps(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                               "error": "mode 未在本进程注册"}),
                         ensure_ascii=False), flush=True)
        return

    backend = mode.get("_backend_module")
    attr = mode.get("_backend_attr")
    if not backend or not attr:
        print(json.dumps(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                               "error": "backend 未声明"}),
                         ensure_ascii=False), flush=True)
        return

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

        print(json.dumps(_tag({"type": "result", "mode_id": mode_id, "ok": True,
                               "output": result}),
                         ensure_ascii=False), flush=True)

    except Exception as e:
        tb = traceback.format_exc()
        print(json.dumps(_tag({"type": "result", "mode_id": mode_id, "ok": False,
                               "error": str(e), "traceback": tb}),
                         ensure_ascii=False), flush=True)


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
        print(json.dumps(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                               "error": "tool 未在本进程注册"}),
                         ensure_ascii=False), flush=True)
        return

    backend = tool.get("_backend_module")
    attr = tool.get("_backend_attr")
    if not backend or not attr:
        print(json.dumps(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                               "error": "backend 未声明"}),
                         ensure_ascii=False), flush=True)
        return

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

        print(json.dumps(_tag({"type": "tool_result", "tool_name": tool_name, "ok": True,
                               "output": result}),
                         ensure_ascii=False), flush=True)

    except Exception as e:
        tb = traceback.format_exc()
        print(json.dumps(_tag({"type": "tool_result", "tool_name": tool_name, "ok": False,
                               "error": str(e), "traceback": tb}),
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    _main()
