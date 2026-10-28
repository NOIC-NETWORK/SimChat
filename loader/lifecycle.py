"""MOD 生命周期：扫描、校验、导入、注册、启用/停用。

Phase 1 只实现最小闭环：
  discover() -> 校验 manifest -> 导入 entry -> 调用入口注册 hook -> 解析 backend
失败隔离：单个 MOD 失败只标记 failed，不影响其他 MOD 与本体启动。
"""

import importlib
import json
import os
import sys

_STATE_FILE = ".simchat_state.json"

_HERE = os.path.dirname(os.path.abspath(__file__))
_SDK_PYTHON = os.path.join(os.path.dirname(_HERE), "sdk", "python")
if _SDK_PYTHON not in sys.path:
    sys.path.insert(0, _SDK_PYTHON)

from simchat_mod import ModApi  # noqa: E402  (SDK 路径注入后再导入)

from .manifest import MANIFEST_NAME, check_requires, validate_manifest  # noqa: E402
from .registry import ModeRegistry  # noqa: E402
from .resolver import resolve_dependencies  # noqa: E402  (Phase 2 P2.1)
from .sandbox import run_isolated, register_handle, kill_all as _kill_all_sandboxes  # noqa: E402  (Phase 2 P2.3)
from .verify import verify_package  # noqa: E402


class ModLoader(object):
    def __init__(self, mods_dir, host_version="2.0.0", services=None,
                 logger=None):
        self.mods_dir = os.path.abspath(mods_dir)
        self.host_version = host_version
        self.registry = ModeRegistry()
        self.mods = {}
        self._services = dict(services or {})
        self._backends = {}
        self._tools = {}  # P2.4 新增：{tool_name: {"handle": ..., "mod_id": ..., "spec": {...}}}
        self._logger = logger or (lambda message: print("[SimChat] %s" % message))
        self._state_path = os.path.join(self.mods_dir, _STATE_FILE)
        self._disabled = self._read_state()

    # ---------- 状态 ----------

    def _log(self, message):
        self._logger(message)

    def _read_state(self):
        try:
            with open(self._state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return set(data.get("disabled") or [])
        except Exception:
            return set()

    def _write_state(self):
        try:
            os.makedirs(self.mods_dir, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as handle:
                json.dump({"disabled": sorted(self._disabled)}, handle, ensure_ascii=False, indent=2)
        except Exception as error:
            self._log("写入 MOD 状态失败: %s" % error)

    # ---------- 扫描 / 加载 ----------

    def discover(self):
        self.mods = {}
        self.registry = ModeRegistry()
        self._backends = {}
        if not os.path.isdir(self.mods_dir):
            self._log("MOD 目录不存在: %s" % self.mods_dir)
            return self.list_mods()

        for name in sorted(os.listdir(self.mods_dir)):
            if name.startswith("."):
                continue
            package_dir = os.path.join(self.mods_dir, name)
            if not os.path.isdir(package_dir):
                continue
            if not os.path.isfile(os.path.join(package_dir, MANIFEST_NAME)):
                continue
            self._load_one(package_dir)

        loaded = [item for item in self.mods.values() if item["status"] == "loaded"]
        self._log("扫描完成：%d 个 MOD，%d 个已加载" % (len(self.mods), len(loaded)))
        return self.list_mods()

    def _load_one(self, package_dir):
        record = {
            "id": os.path.basename(package_dir),
            "path": package_dir,
            "manifest": None,
            "status": "failed",
            "error": None,
            "modes": [],
            "tools": [],  # P2.4 新增
            "api": None,
        }

        try:
            with open(os.path.join(package_dir, MANIFEST_NAME), "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except Exception as error:
            return self._fail(record, "manifest 读取失败: %s" % error)

        record["manifest"] = manifest
        mod_id = manifest.get("id")
        if mod_id:
            record["id"] = mod_id

        errors, warnings = validate_manifest(manifest)
        for warning in warnings:
            self._log("[%s] 警告: %s" % (record["id"], warning))
        if errors:
            return self._fail(record, "manifest 校验失败: %s" % "; ".join(errors))

        if mod_id in self.mods:
            return self._fail(record, "MOD id 重复: %s" % mod_id)

        ok, message = check_requires(manifest, self.host_version)
        if not ok:
            return self._fail(record, message)

        # Phase 2 P2.1 — Python 版本 + 第三方包依赖解析
        ok, message = resolve_dependencies(manifest)
        if not ok:
            return self._fail(record, message)

        ok, message = verify_package(package_dir, manifest)
        if not ok:
            return self._fail(record, message)

        if mod_id in self._disabled:
            record["manifest"] = manifest
            record["status"] = "disabled"
            self.mods[mod_id] = record
            self._log("[%s] 已停用，跳过加载" % mod_id)
            return record

        # agent-config 是纯数据 MOD，不需要执行 entry；过校验/requires/verify 即 loaded
        # （manifest.py 禁止其声明 entry，config 对象由前端直接消费）
        # 本分支不得被 Phase 2 sandbox 改造删除——agent-config 的语义契约是"无代码执行"
        if manifest.get("type") == "agent-config":
            record["status"] = "loaded"
            self.mods[mod_id] = record
            self._log("[%s] agent-config 已加载（数据）" % mod_id)
            return record

        try:
            # Phase 2 P2.3 — 把 entry(api) 放进独立子进程
            handle = run_isolated(package_dir, manifest["entry"], manifest)
            if not handle.get("ok"):
                return self._fail(record, handle.get("message") or "沙箱加载失败")

            record["sandbox_handle"] = handle
            register_handle(handle)

            # 注册 mode 元数据到 ModeRegistry（Phase 1 暂不 import backend 函数——
            # 当前前端 Galax ⚡ 按钮走的是硬编码 endpoint，通用 invoke 链路留给后续）
            for spec in handle.get("modes", []):
                if not spec.get("id"):
                    continue
                entry = self.registry.register(mod_id, spec)
                record["modes"].append(entry)

            # P2.4 — 注册 tool 元数据到 _tools（skill MOD 走 sandbox，backend 在子进程）
            for spec in handle.get("tools", []):
                name = spec.get("name")
                if not name:
                    continue
                if name in self._tools:
                    self._log("[%s] tool %s 与已加载 MOD 冲突，跳过" % (mod_id, name))
                    continue
                self._tools[name] = {
                    "handle": handle,
                    "mod_id": mod_id,
                    "spec": dict(spec),
                }
                record["tools"].append({"name": name, "label": spec.get("label") or name})

        except Exception as error:
            return self._fail(record, "加载失败: %s" % error)

        record["status"] = "loaded"
        self.mods[mod_id] = record
        modes_str = ", ".join(mode["id"] for mode in record["modes"]) or "(无)"
        tools_str = ", ".join(t["name"] for t in record["tools"]) or "(无)"
        self._log("[%s] 已加载，注册模式: %s | 工具: %s" % (mod_id, modes_str, tools_str))
        return record

    def _invoke_entry(self, package_dir, manifest, mod_id):
        """已废弃 — Phase 2 P2.3 起改用 sandbox.run_isolated。

        保留方法体为占位，避免被外部误引用时 AttributeError；
        真正的 entry(api) 执行在子进程里。
        """
        raise NotImplementedError("本方法已由 sandbox.run_isolated 替代")

    @staticmethod
    def _resolve(package_dir, reference):
        """暂不调用（Phase 1 sandbox 不 import backend 函数，
        当前前端调用走硬编码 endpoint，通用 invoke 链路留给后续切片）。"""
        if not reference:
            return None
        if ":" not in reference:
            raise ValueError("backend 必须形如 module:attr: %s" % reference)
        module_name, attribute = reference.split(":")
        module = importlib.import_module(module_name)
        backend = getattr(module, attribute)
        if not callable(backend):
            raise TypeError("backend 不可调用: %s" % reference)
        return backend

    def cleanup(self):
        """宿主退出时调用，kill 所有活跃沙箱进程。"""
        _kill_all_sandboxes()

    def _emit_event(self, name, payload):
        self._log("事件 %s: %s" % (name, payload))

    def _fail(self, record, message):
        record["status"] = "failed"
        record["error"] = message
        self.mods[record["id"]] = record
        self._log("[%s] %s" % (record["id"], message))
        return record

    # ---------- 查询 ----------

    def list_mods(self):
        result = []
        for mod_id, record in self.mods.items():
            manifest = record.get("manifest") or {}
            result.append({
                "id": mod_id,
                "name": manifest.get("name") or mod_id,
                "version": manifest.get("version") or "",
                "type": manifest.get("type") or "",
                "status": record["status"],
                "error": record.get("error"),
                "hooks": list(manifest.get("hooks") or []),
                "modes": [dict(mode) for mode in record.get("modes") or []],
                "tools": [dict(tool) for tool in record.get("tools") or []],  # P2.4
                "path": record["path"],
                "config": manifest.get("config"),
            })
        return result

    def list_tools(self):
        """P2.4 — 返回全部已注册 tool 的元数据列表。"""
        result = []
        for name, info in sorted(self._tools.items()):
            spec = info["spec"]
            result.append({
                "name": name,
                "label": spec.get("label") or name,
                "description": spec.get("description", ""),
                "risk": spec.get("risk", "read"),
                "usage": spec.get("usage", ""),
                "mod_id": info["mod_id"],
            })
        return result

    def has_tool(self, name):
        return name in self._tools

    def call_tool(self, tool_name, params=None, timeout=60):
        """P2.4 — 宿主侧调用 skill MOD 的入口。

        通过 sandbox.invoke_tool() 把请求转发到 skill 子进程。
        返回 dict: {"ok": bool, "output": ...} 或 {"ok": False, "error": ...}
        """
        info = self._tools.get(tool_name)
        if info is None:
            return {"ok": False, "error": "tool 未注册: %s" % tool_name}
        handle = info["handle"]
        from .sandbox import invoke_tool  # 延迟 import 避免循环
        return invoke_tool(handle, tool_name, params or {}, timeout=timeout)

    def list_modes(self):
        return self.registry.list_modes()

    def has_mode(self, mode_id):
        return self.registry.has(mode_id) and self._backends.get(mode_id) is not None

    def call_mode(self, mode_id, message, session_id=None, history=None):
        backend = self._backends.get(mode_id)
        if backend is None:
            raise LookupError("模式不可用: %s" % mode_id)
        return backend(message, session_id, history or [])

    def mod_path(self, mod_id):
        record = self.mods.get(mod_id)
        if not record or record["status"] != "loaded":
            return None
        return record["path"]

    # ---------- 启用 / 停用（下次启动生效） ----------

    def set_enabled(self, mod_id, enabled):
        if enabled:
            self._disabled.discard(mod_id)
        else:
            self._disabled.add(mod_id)
        self._write_state()
        self._log("[%s] 已%s（重启后生效）" % (mod_id, "启用" if enabled else "停用"))
        return True


# ---------- 全局单例（宿主 lmbrew.py 启动时调用 set_global_loader） ----------

_GLOBAL_LOADER = None


def set_global_loader(loader):
    """宿主启动后调用一次，让 SkillManager facade 等能访问。"""
    global _GLOBAL_LOADER
    _GLOBAL_LOADER = loader


def get_loader():
    """全局 getter；尚未初始化则返回 None。"""
    return _GLOBAL_LOADER
