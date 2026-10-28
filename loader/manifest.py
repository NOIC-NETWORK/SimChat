"""manifest.json 的结构校验与版本约束检查（纯标准库）。

只做"加载前"校验：结构、hook 白名单、类型约束、本体版本范围。
签名与包完整性属于安装期校验，见 verify.py。
"""

import re

MANIFEST_NAME = "manifest.json"

KNOWN_HOOKS = frozenset([
    "chat.mode",
    "agent.tool",
    "agent.context",
    "agent.system_prompt",
    "agent.safety",
    "agent.memory",
    "agent.event",
    "ui.slot",
    "provider.model",
    "automation.hook",
])

KNOWN_TYPES = frozenset(["agent-config", "skill", "automation", "binary"])

TOP_LEVEL_KEYS = frozenset([
    "$schema", "id", "type", "name", "description", "version", "abi", "entry",
    "hooks", "capabilities", "requires", "assets", "license", "homepage",
    "repository", "signature", "integrity", "config", "automation",
])

CAPABILITY_KEYS = frozenset([
    "fs", "net", "shell", "process", "credentials", "schedule",
])

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
ENTRY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
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
        errors.append("id 不符合规范: %s" % mod_id)

    mod_type = data.get("type")
    if _is_str(mod_type) and mod_type not in KNOWN_TYPES:
        errors.append("未知 MOD 类型: %s" % mod_type)

    version = data.get("version")
    if _is_str(version) and not VERSION_RE.match(version):
        errors.append("version 不是合法语义化版本: %s" % version)

    if data.get("abi") != "lmbrew-mod/1":
        errors.append("不支持的 ABI: %s" % data.get("abi"))

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

    requires = data.get("requires")
    if requires is not None and not isinstance(requires, dict):
        errors.append("requires 必须是对象")
    elif isinstance(requires, dict):
        unknown = sorted(set(requires) - {"lmbrew", "python", "packages"})
        if unknown:
            errors.append("requires 含未知字段: %s" % ", ".join(unknown))
        if "packages" in requires and not _is_str_list(requires["packages"]):
            errors.append("requires.packages 必须是字符串数组")

    entry = data.get("entry")
    if entry is not None:
        if not _is_str(entry) or not ENTRY_RE.match(entry):
            errors.append("entry 必须形如 module:attr")
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
    """返回 (ok, message)。"""
    requires = manifest.get("requires") or {}
    spec = (requires.get("lmbrew") or "").strip()
    if spec and not _satisfies(host_version, spec):
        return False, "本体版本 %s 不满足 requires.lmbrew=%s" % (host_version, spec)
    return True, ""
