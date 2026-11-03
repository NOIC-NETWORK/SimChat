"""运行日志：滚动文件 + 读取接口。

日志写入 data/logs/simchat.log（RotatingFileHandler，2MB x 3）。
控制台「日志」分区通过 list_files()/tail() 读取已有的滚动文件。
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from simchat.runtime import system_config

LOG_NAME = "simchat.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_handler = None
_handler_path = None


def log_dir(data_root):
    return os.path.join(data_root, "logs")


def setup(data_root):
    """幂等挂载滚动文件 handler，并应用 system.json 中的日志级别。"""
    global _handler, _handler_path
    level_name = system_config.load_state(data_root).get("log_level", "INFO")
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    path = os.path.join(log_dir(data_root), LOG_NAME)
    if _handler is not None and _handler_path == path:
        _handler.setLevel(level)
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if _handler is not None:
        try:
            logging.getLogger().removeHandler(_handler)
            _handler.close()
        except Exception:
            pass

    handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    _handler = handler
    _handler_path = path
    return path


def set_level(data_root, level_name):
    global _handler
    level = getattr(logging, str(level_name).upper(), None)
    if level is None:
        raise ValueError("未知日志级别: %s" % level_name)
    if _handler is not None:
        _handler.setLevel(level)
    else:
        setup(data_root)
    return level_name


def list_files(data_root):
    directory = log_dir(data_root)
    if not os.path.isdir(directory):
        return []
    items = []
    for name in sorted(os.listdir(directory), reverse=True):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            stat = os.stat(path)
            items.append({
                "name": name,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            })
        except OSError:
            continue
    return items


def _safe_path(data_root, name):
    base = os.path.abspath(log_dir(data_root))
    path = os.path.abspath(os.path.join(base, os.path.basename(str(name or ""))))
    if not path.startswith(base + os.sep):
        raise ValueError("非法日志文件名")
    if not os.path.isfile(path):
        raise ValueError("日志文件不存在: %s" % name)
    return path


def tail(data_root, name=LOG_NAME, lines=200):
    path = _safe_path(data_root, name)
    try:
        lines = max(10, min(int(lines), 1000))
    except Exception:
        lines = 200

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        buffer = handle.readlines()
    content = "".join(buffer[-lines:])
    return {
        "name": os.path.basename(path),
        "lines": len(buffer[-lines:]),
        "content": content,
    }
