"""MOD 本地索引（只读扫描 + 启停状态）。

与 loader.lifecycle 的 ModLoader 不同，本模块**只读**：读取 mods/ 下的
manifest.json 做结构校验，不 import MOD entry、不创建沙箱、不执行任何 MOD 代码。
启停状态沿用 ModLoader 的 .simchat_state.json 契约（disabled 列表，重启后生效）。
"""

import importlib.util
import json
import os
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODS_DIR = os.path.join(_PROJECT_ROOT, "mods")
DEFAULT_REGISTRY_PATH = os.path.join(_PROJECT_ROOT, "registry", "index.json")
STATE_FILE = ".simchat_state.json"
MANIFEST_NAME = "manifest.json"

_WRITE_LOCK = threading.Lock()
_MANIFEST_MODULE = None

_MANIFEST_PATH = os.path.join(_PROJECT_ROOT, "loader", "manifest.py")


def _manifest():
    """直接加载 loader/manifest.py（纯标准库）。

    刻意不 `import simchat.loader`：包 __init__ 会连带导入 lifecycle / sandbox /
    resolver，违背「MOD 列表只读扫描、零副作用」的约束。
    """
    global _MANIFEST_MODULE
    if _MANIFEST_MODULE is not None:
        return _MANIFEST_MODULE
    spec = importlib.util.spec_from_file_location("simchat_manifest_validator", _MANIFEST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MANIFEST_MODULE = module
    return module

_TYPE_LABELS = {
    "skill": "Skill",
    "binary": "Binary",
    "agent-config": "AgentConfig",
    "automation": "Automation",
}


def type_label(mod_type):
    return _TYPE_LABELS.get(mod_type or "", mod_type or "Unknown")


def _state_path(mods_dir):
    return os.path.join(mods_dir, STATE_FILE)


def _read_disabled(mods_dir):
    try:
        with open(_state_path(mods_dir), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return set(data.get("disabled") or [])
    except Exception:
        return set()


def _write_disabled(mods_dir, disabled):
    path = _state_path(mods_dir)
    tmp = path + ".tmp"
    with _WRITE_LOCK:
        os.makedirs(mods_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"disabled": sorted(disabled)}, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def scan(mods_dir=None):
    """只读扫描 mods/，返回目录中所有带 manifest.json 的条目。

    每个条目状态：
      ok   manifest 校验通过
      warn 校验通过但有警告
      err  manifest 读取/校验失败
    """
    mods_dir = os.path.abspath(mods_dir or DEFAULT_MODS_DIR)
    result = []
    if not os.path.isdir(mods_dir):
        return result

    disabled = _read_disabled(mods_dir)
    for name in sorted(os.listdir(mods_dir)):
        if name.startswith("."):
            continue
        package_dir = os.path.join(mods_dir, name)
        if not os.path.isdir(package_dir):
            continue
        manifest_path = os.path.join(package_dir, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            continue

        entry = _scan_one(name, package_dir, manifest_path, disabled)
        result.append(entry)
    return result


def _scan_one(folder_name, package_dir, manifest_path, disabled):
    base = {
        "id": folder_name,
        "folder": folder_name,
        "name": folder_name,
        "version": "?",
        "type": "?",
        "type_label": "Unknown",
        "description": "",
        "hooks": [],
        "capabilities": {},
        "license": "",
        "path": package_dir,
        "status": "err",
        "error": None,
        "errors": [],
        "warnings": [],
        "enabled": True,
        "has_web": False,
        "automation": None,
    }
    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
    except Exception as error:
        base["error"] = "manifest 读取失败: %s" % error
        base["errors"] = [base["error"]]
        return base

    errors, warnings = _manifest().validate_manifest(manifest)
    mod_id = manifest.get("id") or folder_name
    base.update({
        "id": mod_id,
        "name": manifest.get("name") or folder_name,
        "version": manifest.get("version") or "?",
        "type": manifest.get("type") or "?",
        "type_label": type_label(manifest.get("type")),
        "description": manifest.get("description") or "",
        "hooks": list(manifest.get("hooks") or []),
        "capabilities": manifest.get("capabilities") or {},
        "license": manifest.get("license") or "",
        "enabled": mod_id not in disabled,
        "errors": errors,
        "warnings": warnings,
    })
    if errors:
        base["status"] = "err"
        base["error"] = "; ".join(errors)
    elif warnings:
        base["status"] = "warn"
    else:
        base["status"] = "ok"

    # 前端资源目录（存在 web/ 视为该 MOD 提供前端扩展）
    base["has_web"] = os.path.isdir(os.path.join(package_dir, "web"))

    # automation MOD：顺手读取 flow.json 供控制台展示（纯数据，不执行）
    automation = manifest.get("automation")
    if isinstance(automation, dict):
        flow_file = automation.get("flow_file")
        if isinstance(flow_file, str) and flow_file:
            base["automation"] = _read_flow(package_dir, flow_file)
    return base


def _read_flow(package_dir, flow_file):
    """读取 automation flow.json；失败时返回错误说明而非抛异常。"""
    path = os.path.normpath(os.path.join(package_dir, flow_file))
    if not path.startswith(os.path.abspath(package_dir)):
        return {"error": "flow_file 越界"}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            flow = json.load(handle)
    except Exception as error:
        return {"error": "flow.json 读取失败: %s" % error}

    steps = flow.get("steps") or []
    trigger = flow.get("trigger") or {}
    return {
        "id": flow.get("id") or "",
        "version": flow.get("version") or "",
        "trigger_type": trigger.get("type") or "",
        "trigger_expr": trigger.get("expr") or trigger.get("event") or trigger.get("manual_token") or "",
        "steps": [
            {
                "id": step.get("id") or "",
                "use": step.get("use") or "",
                "approval": step.get("approval") or "inherit",
            }
            for step in steps if isinstance(step, dict)
        ],
        "policy": flow.get("policy") or {},
    }


def set_enabled(mod_id, enabled, mods_dir=None):
    """写入 disabled 列表（与 ModLoader 共用状态文件），重启后生效。"""
    mods_dir = os.path.abspath(mods_dir or DEFAULT_MODS_DIR)
    disabled = _read_disabled(mods_dir)
    if enabled:
        disabled.discard(mod_id)
    else:
        disabled.add(mod_id)
    _write_disabled(mods_dir, disabled)
    return {"mod_id": mod_id, "enabled": bool(enabled)}


def list_registry(registry_path=None):
    """只读读取 registry/index.json；文件缺失返回 available=false。"""
    path = os.path.abspath(registry_path or DEFAULT_REGISTRY_PATH)
    if not os.path.isfile(path):
        return {"available": False, "reason": "本地没有 registry/index.json", "entries": []}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception as error:
        return {"available": False, "reason": "registry 读取失败: %s" % error, "entries": []}

    entries = []
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        versions = entry.get("versions") or []
        latest = ""
        if versions and isinstance(versions[0], dict):
            latest = versions[0].get("version") or ""
        entries.append({
            "mod_id": entry.get("mod_id") or "",
            "name": entry.get("name") or entry.get("mod_id") or "",
            "description": entry.get("description") or "",
            "type": entry.get("type") or "",
            "type_label": type_label(entry.get("type")),
            "latest_version": latest,
        })
    return {
        "available": True,
        "reason": "",
        "updated_at": data.get("updated_at") or "",
        "count": len(entries),
        "entries": entries,
    }


def snapshot(mods_dir=None):
    """控制台用聚合快照：本地列表 + 计数 + registry。"""
    local = scan(mods_dir)
    counts = {
        "total": len(local),
        "enabled": sum(1 for item in local if item["enabled"]),
        "disabled": sum(1 for item in local if not item["enabled"]),
        "error": sum(1 for item in local if item["status"] == "err"),
    }
    return {
        "mods_dir": os.path.abspath(mods_dir or DEFAULT_MODS_DIR),
        "counts": counts,
        "local": local,
        "registry": list_registry(),
    }
