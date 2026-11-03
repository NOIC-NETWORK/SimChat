"""系统配置：运行环境探测 + 少量可写白名单。

控制台「系统配置」只暴露真正会生效的开关，目前是日志级别。
其余字段（Python / 平台 / 路径 / 存储占用）均为只读探测结果。
"""

import json
import os
import platform
import shutil
import sys
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_STATE = {"log_level": "INFO"}

_LOCK = threading.Lock()


def _state_path(data_root):
    return os.path.join(data_root, "state", "system.json")


def load_state(data_root):
    state = dict(DEFAULT_STATE)
    try:
        with open(_state_path(data_root), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if str(data.get("log_level", "")).upper() in LOG_LEVELS:
            state["log_level"] = str(data["log_level"]).upper()
    except Exception:
        pass
    return state


def save_state(data_root, payload):
    state = load_state(data_root)
    if "log_level" in payload:
        level = str(payload.get("log_level") or "").upper()
        if level not in LOG_LEVELS:
            raise ValueError("日志级别必须是 %s 之一" % "/".join(LOG_LEVELS))
        state["log_level"] = level

    path = _state_path(data_root)
    tmp = path + ".tmp"
    with _LOCK:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return state


def _memory_info():
    try:
        import psutil  # 可选依赖
        process = psutil.Process(os.getpid())
        memory = process.memory_info()
        return {
            "source": "psutil",
            "rss_mb": round(memory.rss / 1024 / 1024, 1),
            "vms_mb": round(memory.vms / 1024 / 1024, 1),
            "threads": process.num_threads(),
        }
    except Exception:
        return {"source": "unavailable", "rss_mb": None, "vms_mb": None, "threads": None}


def _dir_size(path, limit=20000):
    total = 0
    count = 0
    if not os.path.isdir(path):
        return 0, 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            if count >= limit:
                return total, count
            try:
                total += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                pass
    return total, count


def debug_snapshot(data_root):
    """调试面板用的轻量快照：不做全量目录扫描，避免拖慢请求。"""
    memory = _memory_info()
    try:
        disk_total, disk_used, disk_free = shutil.disk_usage(data_root)
    except Exception:
        disk_total = disk_used = disk_free = 0
    return {
        "runtime": {
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "memory": memory,
        "disk": {
            "total_bytes": disk_total,
            "used_bytes": disk_used,
            "free_bytes": disk_free,
        },
        "paths": {
            "data_root": os.path.abspath(data_root),
            "logs_dir": os.path.join(os.path.abspath(data_root), "logs"),
            "mods_dir": os.path.join(PROJECT_ROOT, "mods"),
        },
        "log_level": load_state(data_root)["log_level"],
    }


def environment(data_root):
    memory = _memory_info()
    try:
        disk_total, disk_used, disk_free = shutil.disk_usage(PROJECT_ROOT)
    except Exception:
        disk_total = disk_used = disk_free = 0

    data_size, data_files = _dir_size(data_root)
    config_path = os.path.join(data_root, "config.json")
    settings_path = os.path.join(data_root, "settings.json")

    env_items = []
    for key in sorted(os.environ):
        if key.startswith("SIMCHAT_"):
            value = os.environ[key]
            if any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                value = "********"
            env_items.append({"key": key, "value": value})

    return {
        "runtime": {
            "app": "SimChat",
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "cpu_count": os.cpu_count(),
            "cwd": os.getcwd(),
        },
        "memory": memory,
        "storage": {
            "data_root": os.path.abspath(data_root),
            "data_size_bytes": data_size,
            "data_files": data_files,
            "disk_total_bytes": disk_total,
            "disk_used_bytes": disk_used,
            "disk_free_bytes": disk_free,
        },
        "paths": {
            "project_root": PROJECT_ROOT,
            "mods_dir": os.path.join(PROJECT_ROOT, "mods"),
            "logs_dir": os.path.join(data_root, "logs"),
            "config": config_path if os.path.isfile(config_path) else "",
            "settings": settings_path if os.path.isfile(settings_path) else "",
        },
        "env": env_items,
        "state": load_state(data_root),
        "log_levels": list(LOG_LEVELS),
    }
