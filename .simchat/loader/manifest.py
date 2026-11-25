"""manifest.json 的结构校验与版本约束检查（纯标准库）。

只做"加载前"校验：结构、hook 白名单、类型约束、本体版本范围、层级归属。
签名与包完整性属于安装期校验，见 verify.py。
"""

import re

MANIFEST_NAME = "manifest.json"

# 当前 ABI 版本；同时接受旧版 "lmbrew-mod/1"（过渡期兼容，下个大版本移除）
CURRENT_ABI = "simchat-mod/2"
LEGACY_ABI = "lmbrew-mod/1"
SUPPORTED_ABIS = frozenset([CURRENT_ABI, LEGACY_ABI])

KNOWN_HOOKS = frozenset([
    "chat.mode",
    "agent.block",           # 新：方块层原子能力注册
    "agent.tool",            # 旧别名：过渡期同时接受
    "agent.map",             # 新：地图（AI 实例）预设注册
    "agent.context",
    "agent.system_prompt",
    "agent.safety",
    "agent.memory",
    "agent.event",
    "agent.completed",       # automation 完成触发
    "ui.slot",
    "provider.model",
    "automation.hook",
    "web.blueprint",         # 新：Mod 层独立 Flask Blueprint 注册
])

KNOWN_TYPES = frozenset(["agent-config", "skill", "automation", "binary"])

KNOWN_LAYERS = frozenset(["block", "mod"])

TOP_LEVEL_KEYS = frozenset([
    "$schema", "id", "type", "layer", "name", "description", "version", "abi", "entry",
    "hooks", "capabilities", "requires", "assets", "frontend_entry", "desktop", "license", "homepage",
    "repository", "signature", "integrity", "config", "automation",
])

# 类型 → 默认层级归属（layer 缺省时按此推断）
DEFAULT_LAYER_BY_TYPE = {
    "skill": "block",         # skill = 可插拔方块
    "automation": "block",    # automation 是方块层的工作流原子能力
    "agent-config": "mod",    # agent-config 是 Mod 层的配置数据包
    "binary": "mod",          # binary = 完整应用包
}

CAPABILITY_KEYS = frozenset([
    "fs", "net", "shell", "process", "credentials", "schedule",
])

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
ENTRY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
FRONTEND_ENTRY_RE = re.compile(r"^web/(?!.*\.\.)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.html?$")

# config 键白名单：MOD 自描述数据，宿主不得合并进本体配置
CONFIG_KEYS = frozenset(["persona", "system_prompt_file", "params", "theme", "models"])
MODELS_KEYS = frozenset([
    "primary", "role", "label", "why", "persona_system",
    "runtime", "roles", "status", "not_implemented",
])
MODELS_RUNTIME_KEYS = frozenset([
    "backend", "model", "context_window", "gpu_layers", "kv_cache", "keep_alive",
])
MODELS_ROLES = frozenset(["chat", "polish", "orchestrate"])
MODEL_ROLE_VALUES = frozenset(["active", "planned", "disabled"])
REL_PATH_RE = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/-]+$")
DOMAIN_RE = re.compile(r"^[a-z0-9*]([a-z0-9.-]*[a-z0-9])?$")
INTEGRITY_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def _is_str(value):
    return isinstance(value, str) and bool(value.strip())


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_manifest(data):
    """返回 (errors, warnings)。errors 非空即拒绝加载。"""
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return ["manifest.json 必须是 JSON 对象"], warnings

    unknown = sorted(set(data) - TOP_LEVEL_KEYS)
    if unknown:
        errors.append("未知字段: %s" % ", ".join(unknown))

    for key in ("id", "type", "name", "version", "abi", "license"):
        if not _is_str(data.get(key)):
            errors.append("缺少必填字段或类型错误: %s" % key)

    mod_id = data.get("id")
    if _is_str(mod_id) and not ID_RE.match(mod_id):
        errors.append("id 不符合规范（只允许小写字母、数字、下划线）: %s" % mod_id)

    mod_type = data.get("type")
    if _is_str(mod_type) and mod_type not in KNOWN_TYPES:
        errors.append("未知 MOD 类型: %s" % mod_type)

    version = data.get("version")
    if _is_str(version) and not VERSION_RE.match(version):
        errors.append("version 不是合法语义化版本: %s" % version)

    abi = data.get("abi")
    if abi not in SUPPORTED_ABIS:
        errors.append("不支持的 ABI: %s（当前 %s，旧版 %s 仍兼容）" % (abi, CURRENT_ABI, LEGACY_ABI))
    elif abi == LEGACY_ABI:
        warnings.append("使用旧版 ABI %s，建议迁移到 %s（过渡期兼容，下个大版本移除旧版）" % (LEGACY_ABI, CURRENT_ABI))

    # layer 字段校验：可缺省，缺省时按 type 推断
    layer = data.get("layer")
    if layer is not None:
        if not _is_str(layer) or layer not in KNOWN_LAYERS:
            errors.append("layer 必须是 'block' 或 'mod': %s" % layer)
    else:
        # 自动推断并写回供下游消费（调用方应读取 data['layer']）
        data["layer"] = DEFAULT_LAYER_BY_TYPE.get(mod_type, "block")

    hooks = data.get("hooks")
    if hooks is not None:
        if not _is_str_list(hooks):
            errors.append("hooks 必须是字符串数组")
        else:
            unknown_hooks = sorted(set(hooks) - KNOWN_HOOKS)
            if unknown_hooks:
                errors.append("未知 hook（fail-closed）: %s" % ", ".join(unknown_hooks))
            if len(set(hooks)) != len(hooks):
                errors.append("hooks 存在重复项")

    capabilities = data.get("capabilities")
    if capabilities is not None:
        errors.extend(_validate_capabilities(capabilities))

    config = data.get("config")
    if config is not None:
        errors.extend(_validate_config(config))

    requires = data.get("requires")
    if requires is not None and not isinstance(requires, dict):
        errors.append("requires 必须是对象")
    elif isinstance(requires, dict):
        unknown = sorted(set(requires) - {"simchat", "lmbrew", "python", "packages"})
        if unknown:
            errors.append("requires 含未知字段: %s" % ", ".join(unknown))
        if "packages" in requires and not _is_str_list(requires["packages"]):
            errors.append("requires.packages 必须是字符串数组")

    entry = data.get("entry")
    if entry is not None:
        if mod_type == "automation":
            # automation 的 entry 可以是 flow.json 路径或 module:attr，不强制 ENTRY_RE
            pass
        elif not _is_str(entry) or not ENTRY_RE.match(entry):
            errors.append("entry 必须形如 module:attr")
    frontend_entry = data.get("frontend_entry")
    if frontend_entry is not None:
        if not _is_str(frontend_entry) or not FRONTEND_ENTRY_RE.match(frontend_entry):
            errors.append("frontend_entry 必须是 web/ 目录下的 .html 相对路径（如 web/index.html）")
    desktop = data.get("desktop")
    if desktop is not None:
        errors.extend(_validate_desktop(desktop))
    if mod_type in ("skill", "automation", "binary"):
        if not entry:
            errors.append("%s 类型必须声明 entry" % mod_type)
        if not hooks:
            errors.append("%s 类型必须至少声明一个 hook" % mod_type)
    if mod_type == "agent-config":
        if entry:
            errors.append("agent-config 不得声明 entry")
        if not isinstance(data.get("config"), dict):
            errors.append("agent-config 必须声明 config 对象")

    if mod_type == "binary":
        signature = data.get("signature")
        if not _is_str(signature) or len(signature) < 32:
            errors.append("binary 类型必须提供 signature")
        integrity = data.get("integrity")
        if not _is_str(integrity) or not INTEGRITY_RE.match(integrity):
            errors.append("binary 类型必须提供 sha256 integrity")

    if mod_type == "automation":
        automation = data.get("automation")
        if not isinstance(automation, dict):
            errors.append("automation 类型必须声明 automation 对象")
        if not isinstance(capabilities, dict) or capabilities.get("schedule") is not True:
            errors.append("automation 类型必须声明 capabilities.schedule=true")
    elif isinstance(capabilities, dict) and capabilities.get("schedule") is True:
        warnings.append("只有 automation 类型应声明 capabilities.schedule")

    if data.get("integrity") is not None and not INTEGRITY_RE.match(str(data.get("integrity"))):
        errors.append("integrity 格式必须为 sha256:<64 hex>")

    return errors, warnings


def _validate_desktop(desktop):
    """desktop 为桌面集成声明：键白名单，桌宠立绘必须是包内相对 png。"""
    errors = []
    if not isinstance(desktop, dict):
        return ["desktop 必须是对象"]
    unknown = sorted(set(desktop) - {"pet", "chat_card"})
    if unknown:
        errors.append("desktop 含未知字段: %s" % ", ".join(unknown))
    errors.extend(_validate_chat_card(desktop.get("chat_card")))
    pet = desktop.get("pet")
    if pet is None:
        return errors
    if not isinstance(pet, dict):
        return errors + ["desktop.pet 必须是对象"]
    unknown = sorted(set(pet) - {"sprite", "page", "height", "entry"})
    if unknown:
        errors.append("desktop.pet 含未知字段: %s" % ", ".join(unknown))
    sprite = pet.get("sprite")
    if not _is_str(sprite) or not REL_PATH_RE.match(sprite) or not sprite.lower().endswith(".png"):
        errors.append("desktop.pet.sprite 必须是包内相对 .png 路径")
    page = pet.get("page")
    if page is not None and (not _is_str(page) or not FRONTEND_ENTRY_RE.match(page)):
        errors.append("desktop.pet.page 必须是 web/ 目录下的 .html 相对路径")
    height = pet.get("height")
    if height is not None and (isinstance(height, bool) or not isinstance(height, int)
                               or not 96 <= height <= 1200):
        errors.append("desktop.pet.height 必须是 96-1200 的整数")
    entry = pet.get("entry")
    if entry is not None and (not _is_str(entry) or not REL_PATH_RE.match(entry)
                              or not entry.lower().endswith(".py")):
        errors.append("desktop.pet.entry 必须是包内相对 .py 路径")
    return errors


def _validate_chat_card(chat_card):
    """desktop.chat_card：Web 侧边栏 MOD 对话卡片的展示声明。"""
    if chat_card is None:
        return []
    if not isinstance(chat_card, dict):
        return ["desktop.chat_card 必须是对象"]
    errors = []
    unknown = sorted(set(chat_card) - {"label", "description", "greeting", "is_deleteable", "system"})
    if unknown:
        errors.append("desktop.chat_card 含未知字段: %s" % ", ".join(unknown))
    label = chat_card.get("label")
    if not _is_str(label) or not label.strip() or len(label) > 32:
        errors.append("desktop.chat_card.label 必须是 1-32 字符的字符串")
    description = chat_card.get("description")
    if description is not None and (not _is_str(description) or len(description) > 120):
        errors.append("desktop.chat_card.description 必须是不超过 120 字符的字符串")
    greeting = chat_card.get("greeting")
    if greeting is not None and (not _is_str(greeting) or not greeting.strip()
                                 or len(greeting) > 200):
        errors.append("desktop.chat_card.greeting 必须是 1-200 字符的字符串")
    deleteable = chat_card.get("is_deleteable")
    if deleteable is not None and not isinstance(deleteable, bool):
        errors.append("desktop.chat_card.is_deleteable 必须是布尔值")
    system = chat_card.get("system")
    if system is not None and (not _is_str(system) or not system.strip() or len(system) > 64):
        errors.append("desktop.chat_card.system 必须是 1-64 字符的字符串")
    return errors


def _validate_config(config):
    """config 为 MOD 自描述数据：键白名单 + 严格类型，未知键直接失败。"""
    errors = []
    if not isinstance(config, dict):
        return ["config 必须是对象"]

    unknown = sorted(set(config) - CONFIG_KEYS)
    if unknown:
        errors.append("config 含未知字段: %s" % ", ".join(unknown))

    persona = config.get("persona")
    if persona is not None and (not _is_str(persona) or len(persona) > 64):
        errors.append("config.persona 必须是 1-64 字符的字符串")

    for key in ("system_prompt_file", "theme"):
        value = config.get(key)
        if value is not None and (not _is_str(value) or not REL_PATH_RE.match(value)):
            errors.append("config.%s 必须是包内相对路径（禁止 ..、绝对路径与反斜杠）" % key)

    params = config.get("params")
    if params is not None:
        if not isinstance(params, dict):
            errors.append("config.params 必须是对象")
        else:
            for name, value in params.items():
                if isinstance(value, bool) or isinstance(value, (str, int, float)):
                    continue
                errors.append("config.params.%s 只允许字符串/数字/布尔值" % name)

    models = config.get("models")
    if models is not None:
        errors.extend(_validate_models(models))

    return errors


def _validate_models(models):
    errors = []
    if not isinstance(models, dict):
        return ["config.models 必须是对象"]

    unknown = sorted(set(models) - MODELS_KEYS)
    if unknown:
        errors.append("config.models 含未知字段: %s" % ", ".join(unknown))

    for key in ("primary", "runtime"):
        if key not in models:
            errors.append("config.models 缺少必填字段: %s" % key)

    primary = models.get("primary")
    if primary is not None and (not _is_str(primary) or len(primary) > 64):
        errors.append("config.models.primary 必须是 1-64 字符的字符串")

    for key, limit in (("role", 64), ("label", 200), ("persona_system", 128), ("status", 64)):
        value = models.get(key)
        if value is not None and (not _is_str(value) or len(value) > limit):
            errors.append("config.models.%s 必须是非空字符串且不超过 %d 字符" % (key, limit))

    for key in ("why", "not_implemented"):
        value = models.get(key)
        if value is not None and not _is_str_list(value):
            errors.append("config.models.%s 必须是字符串数组" % key)
        elif value is not None and any(len(item) > 500 for item in value):
            errors.append("config.models.%s 单条内容不得超过 500 字符" % key)

    runtime = models.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict):
            errors.append("config.models.runtime 必须是对象")
        else:
            unknown = sorted(set(runtime) - MODELS_RUNTIME_KEYS)
            if unknown:
                errors.append("config.models.runtime 含未知字段: %s" % ", ".join(unknown))
            for key in ("backend", "model"):
                if key not in runtime:
                    errors.append("config.models.runtime 缺少必填字段: %s" % key)
            backend = runtime.get("backend")
            if backend is not None and (not _is_str(backend) or not re.match(r"^[a-z0-9][a-z0-9_.-]{0,31}$", backend)):
                errors.append("config.models.runtime.backend 只允许小写字母、数字与 _.-（不超过 32 字符）")
            model = runtime.get("model")
            if model is not None and (not _is_str(model) or len(model) > 200):
                errors.append("config.models.runtime.model 必须是 1-200 字符的字符串")
            window = runtime.get("context_window")
            if window is not None and (type(window) is not int or not 128 <= window <= 1048576):
                errors.append("config.models.runtime.context_window 必须是 128-1048576 的整数")
            layers = runtime.get("gpu_layers")
            if layers is not None and (type(layers) is not int or not 0 <= layers <= 999):
                errors.append("config.models.runtime.gpu_layers 必须是 0-999 的整数")
            for key in ("kv_cache", "keep_alive"):
                value = runtime.get(key)
                if value is not None and (not _is_str(value) or len(value) > 32):
                    errors.append("config.models.runtime.%s 必须是 1-32 字符的字符串" % key)

    roles = models.get("roles")
    if roles is not None:
        if not isinstance(roles, dict):
            errors.append("config.models.roles 必须是对象")
        else:
            unknown = sorted(set(roles) - MODELS_ROLES)
            if unknown:
                errors.append("config.models.roles 含未知字段: %s" % ", ".join(unknown))
            for name, value in roles.items():
                if name in MODELS_ROLES and (not isinstance(value, str) or value not in MODEL_ROLE_VALUES):
                    errors.append("config.models.roles.%s 必须是 active/planned/disabled" % name)

    return errors


def _validate_capabilities(capabilities):
    errors = []
    if not isinstance(capabilities, dict):
        return ["capabilities 必须是对象"]

    unknown = sorted(set(capabilities) - CAPABILITY_KEYS)
    if unknown:
        errors.append("未知 capability: %s" % ", ".join(unknown))

    fs = capabilities.get("fs")
    if fs is not None:
        if not isinstance(fs, dict):
            errors.append("capabilities.fs 必须是对象")
        else:
            unknown_fs = sorted(set(fs) - {"read", "write"})
            if unknown_fs:
                errors.append("capabilities.fs 含未知字段: %s" % ", ".join(unknown_fs))
            for key in ("read", "write"):
                if key in fs and not _is_str_list(fs[key]):
                    errors.append("capabilities.fs.%s 必须是字符串数组" % key)

    net = capabilities.get("net")
    if net is not None:
        if not isinstance(net, dict):
            errors.append("capabilities.net 必须是对象")
        else:
            domains = net.get("domains")
            if not _is_str_list(domains) or not domains:
                errors.append("capabilities.net.domains 必须是非空字符串数组")
            else:
                invalid = [d for d in domains if not DOMAIN_RE.match(d)]
                if invalid:
                    errors.append("capabilities.net.domains 含非法域名: %s" % ", ".join(invalid))

    for key in ("shell", "process", "schedule"):
        if key in capabilities and not isinstance(capabilities[key], bool):
            errors.append("capabilities.%s 必须是布尔值" % key)

    credentials = capabilities.get("credentials")
    if credentials is not None and not _is_str_list(credentials):
        errors.append("capabilities.credentials 必须是字符串数组")

    return errors


def _parse_version(text):
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text).strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _satisfies(version, spec):
    """支持逗号分隔的 >=, >, <=, <, = 约束；空约束视为满足。"""
    current = _parse_version(version)
    if current is None:
        return False
    for raw in str(spec).split(","):
        raw = raw.strip()
        if not raw:
            continue
        match = re.match(r"^(>=|<=|>|<|=)?\s*(.+)$", raw)
        if not match:
            return False
        operator = match.group(1) or "="
        target = _parse_version(match.group(2))
        if target is None:
            return False
        if operator == ">=" and not current >= target:
            return False
        if operator == ">" and not current > target:
            return False
        if operator == "<=" and not current <= target:
            return False
        if operator == "<" and not current < target:
            return False
        if operator == "=" and not current == target:
            return False
    return True


def check_requires(manifest, host_version):
    """返回 (ok, message)。优先读 requires.simchat，回退兼容 requires.lmbrew（过渡期）。"""
    requires = manifest.get("requires") or {}
    spec = (requires.get("simchat") or requires.get("lmbrew") or "").strip()
    if spec and not _satisfies(host_version, spec):
        return False, "本体版本 %s 不满足 requires.simchat=%s" % (host_version, spec)
    return True, ""
