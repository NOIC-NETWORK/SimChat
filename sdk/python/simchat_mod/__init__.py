"""SimChat MOD SDK（ABI：lmbrew-mod/1）。

MOD 只允许通过本模块与本体交互，不得 import 宿主内部实现。
"""

ABI_VERSION = "lmbrew-mod/1"

_MODE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
_TOOL_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_VALID_RISKS = frozenset(["read", "write", "dangerous"])


def _validate_mode_id(mode_id):
    if not isinstance(mode_id, str) or not mode_id:
        raise ValueError("ModeSpec.id 必须是非空字符串")
    if mode_id[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        raise ValueError("ModeSpec.id 必须以小写字母或数字开头: %s" % mode_id)
    if len(mode_id) > 64:
        raise ValueError("ModeSpec.id 过长: %s" % mode_id)
    if any(ch not in _MODE_ID_CHARS for ch in mode_id):
        raise ValueError("ModeSpec.id 含非法字符: %s" % mode_id)


def _validate_tool_name(name):
    if not isinstance(name, str) or not name:
        raise ValueError("ToolSpec.name 必须是非空字符串")
    if not name[0].isalnum():
        raise ValueError("ToolSpec.name 必须以字母或数字开头: %s" % name)
    if len(name) > 64:
        raise ValueError("ToolSpec.name 过长: %s" % name)
    if any(ch not in _TOOL_NAME_CHARS for ch in name):
        raise ValueError("ToolSpec.name 含非法字符: %s" % name)


class ModeSpec(object):
    """`chat.mode` hook 的模式描述。"""

    def __init__(self, id, label, icon="🔧", order=100, frontend_entry=None,
                 backend=None, cost="normal", description="",
                 requires_capabilities=None):
        _validate_mode_id(id)
        if not label:
            raise ValueError("ModeSpec.label 不能为空")
        self.id = id
        self.label = label
        self.icon = icon or "🔧"
        self.order = int(order)
        self.frontend_entry = frontend_entry
        self.backend = backend
        self.cost = cost
        self.description = description
        self.requires_capabilities = list(requires_capabilities or [])

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "order": self.order,
            "frontend_entry": self.frontend_entry,
            "backend": self.backend,
            "cost": self.cost,
            "description": self.description,
            "requires_capabilities": list(self.requires_capabilities),
        }

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("ModeSpec 必须是 ModeSpec 或 dict")
        return cls(
            id=value.get("id"),
            label=value.get("label") or value.get("id"),
            icon=value.get("icon", "🔧"),
            order=value.get("order", 100),
            frontend_entry=value.get("frontend_entry"),
            backend=value.get("backend"),
            cost=value.get("cost", "normal"),
            description=value.get("description", ""),
            requires_capabilities=value.get("requires_capabilities"),
        )


class ToolSpec(object):
    """`agent.tool` hook 的工具描述。

    backend 是跨进程字符串引用 "module:attr"（callable 不能跨进程序列化）。
    runner 侧 import 后调 attr(params=dict) -> dict|str。
    """

    def __init__(self, name, label=None, description="", risk="read",
                 usage=None, params_schema=None, backend=None,
                 triggers=None, input_schema=None):
        _validate_tool_name(name)
        if risk not in _VALID_RISKS:
            raise ValueError("ToolSpec.risk 必须是 read|write|dangerous，当前: %s" % risk)
        if backend and ":" not in backend:
            raise ValueError("ToolSpec.backend 必须形如 module:attr: %s" % backend)
        self.name = name
        self.label = label or name
        self.description = description or ""
        self.risk = risk
        self.usage = usage or name
        self.params_schema = dict(params_schema) if params_schema else {}
        self.backend = backend  # "module:attr" 字符串，runner 侧解析
        # 兼容现有 BaseSkill 字段（用于迁移）
        self.triggers = list(triggers or [])
        self.input_schema = dict(input_schema) if input_schema else {}

    def to_dict(self):
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "risk": self.risk,
            "usage": self.usage,
            "params_schema": dict(self.params_schema),
            "backend": self.backend,
            "triggers": list(self.triggers),
            "input_schema": dict(self.input_schema),
        }

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("ToolSpec 必须是 ToolSpec 或 dict")
        return cls(
            name=value.get("name"),
            label=value.get("label"),
            description=value.get("description", ""),
            risk=value.get("risk", "read"),
            usage=value.get("usage"),
            params_schema=value.get("params_schema"),
            backend=value.get("backend"),
            triggers=value.get("triggers"),
            input_schema=value.get("input_schema"),
        )


class ModApi(object):
    """注入给 MOD 入口函数的宿主句柄。

    只暴露 manifest 声明的能力与少量只读宿主服务（inference / skill_manager / memory）。
    """

    def __init__(self, mod_id, manifest, package_dir, services=None, emit_event=None):
        self.mod_id = mod_id
        self.manifest = dict(manifest or {})
        self.package_dir = package_dir
        self.modes = []
        self.tools = []  # P2.4 新增：agent.tool 注册
        self._services = dict(services or {})
        self._emit_event = emit_event

    # ---------- 注册 ----------

    def register_mode(self, spec):
        data = ModeSpec.from_value(spec).to_dict()
        for existing in self.modes:
            if existing["id"] == data["id"]:
                raise ValueError("重复注册模式: %s" % data["id"])
        self.modes.append(data)
        return data

    def register_tool(self, spec):
        """注册 agent.tool。spec 是 ToolSpec 或 dict，backend 必填。"""
        data = ToolSpec.from_value(spec).to_dict()
        if not data.get("backend"):
            raise ValueError("ToolSpec.backend 必填（跨进程调用需要字符串引用）")
        for existing in self.tools:
            if existing["name"] == data["name"]:
                raise ValueError("重复注册工具: %s" % data["name"])
        self.tools.append(data)
        return data

    # ---------- 能力 ----------

    @property
    def capabilities(self):
        return dict(self.manifest.get("capabilities") or {})

    def has_capability(self, name):
        value = self.capabilities.get(name)
        return bool(value)

    def service(self, name):
        """宿主注入的只读服务。未注入时返回 None。"""
        return self._services.get(name)

    # ---------- 事件 ----------

    def emit_event(self, name, payload=None):
        if not name or not name.startswith("mod.%s." % self.mod_id):
            raise ValueError("MOD 事件名必须以 mod.%s. 开头" % self.mod_id)
        if self._emit_event:
            self._emit_event(name, payload or {})


def hook(name):
    """标记入口函数/钩子实现所属的 hook，供加载器做声明校验。"""
    def decorator(func):
        func.__simchat_hook__ = name
        return func
    return decorator


from .skill_base import BaseSkill  # noqa: E402  (放在文件末尾，避免循环)

__all__ = ["ABI_VERSION", "ModeSpec", "ToolSpec", "ModApi", "hook", "BaseSkill"]
