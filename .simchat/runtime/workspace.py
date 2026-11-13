"""工作目录（workspace）—— 对话与 Agent 沙箱的统一根目录。

职责：
  1. 持久化用户选择的目录（config.json 的 workspace 段）
  2. 目录浏览（给前端可视化选择器用，只列目录与文件名，不读文件内容）
  3. 与 runtime/agent 沙箱耦合：agent_options() 优先使用这里的路径作为 workdir

存档格式（data/config.json 的 workspace 段）：
{
  "workspace": {
    "path": "E:\\projects\\demo",   // 绝对路径
    "updated_at": "ISO8601"
  }
}

未配置时 load() 返回 configured=False，Web 层据此拦截对话与 Agent 运行。
"""

import json
import os
import string
import threading
from datetime import datetime, timezone

WORKSPACE_VERSION = 1
_ENTRY_LIMIT = 500  # 单次目录列举上限，防止超大目录一次返回过多条目

_WRITE_LOCK = threading.Lock()


def _iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _config_path(data_dir):
    return os.path.join(data_dir, "config.json")


def _read_config(data_dir):
    path = _config_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config(data_dir, cfg):
    path = _config_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with _WRITE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def normalize_path(path):
    """校验并规整工作目录路径；非法时抛 ValueError。"""
    raw = str(path or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("工作目录不能为空")
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise ValueError("请提供绝对路径（例如 E:\\projects）")
    full = os.path.normpath(expanded)
    if not os.path.isdir(full):
        raise ValueError("目录不存在: %s" % full)
    return os.path.abspath(full)


def load(data_dir):
    """读取工作目录状态。未配置时 path 为空，configured=False。"""
    raw = _read_config(data_dir).get("workspace") or {}
    if not isinstance(raw, dict):
        raw = {}
    path = str(raw.get("path") or "").strip()
    configured = bool(path)
    exists = False
    if configured:
        try:
            exists = os.path.isdir(path)
        except OSError:
            exists = False
    return {
        "version": WORKSPACE_VERSION,
        "configured": configured,
        "exists": exists,
        "path": path if configured else "",
        "name": os.path.basename(path.rstrip("\\/")) if configured else "",
        "updated_at": str(raw.get("updated_at") or ""),
    }


def save(data_dir, path):
    """保存工作目录（先校验目录真实存在）。返回最新状态。"""
    full = normalize_path(path)
    cfg = _read_config(data_dir)
    cfg["workspace"] = {"path": full, "updated_at": _iso_now()}
    _write_config(data_dir, cfg)
    return load(data_dir)


def clear(data_dir):
    """清除工作目录配置。返回最新状态。"""
    cfg = _read_config(data_dir)
    if "workspace" in cfg:
        cfg.pop("workspace", None)
        _write_config(data_dir, cfg)
    return load(data_dir)


def _roots():
    """可选的根目录：Windows 下为存在的盘符，其它平台为 / 和用户主目录。"""
    roots = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = "%s:\\" % letter
            try:
                if os.path.isdir(drive):
                    roots.append(drive)
            except OSError:
                continue
    else:
        roots.append("/")

    home = os.path.expanduser("~")
    try:
        if home and os.path.isdir(home) and home not in roots:
            roots.append(home)
    except OSError:
        pass
    return roots


def browse(path=None):
    """列出目录内容（供可视化选择器）。path 为空时只返回可选的根目录。"""
    if not path or not str(path).strip():
        return {
            "path": "",
            "parent": "",
            "entries": [],
            "roots": _roots(),
            "truncated": False,
        }

    raw = str(path).strip().strip('"').strip("'")
    if raw.startswith("~"):
        raw = os.path.expanduser(raw)
    if not os.path.isabs(raw):
        raise ValueError("请提供绝对路径")
    full = os.path.abspath(os.path.normpath(raw))
    if not os.path.isdir(full):
        raise ValueError("目录不存在: %s" % full)

    entries = []
    try:
        with os.scandir(full) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                entries.append({
                    "name": entry.name,
                    "path": os.path.abspath(entry.path),
                    "is_dir": is_dir,
                })
    except PermissionError:
        raise ValueError("没有权限读取目录: %s" % full)
    except OSError as e:
        raise ValueError("读取目录失败: %s" % e)

    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    truncated = len(entries) > _ENTRY_LIMIT
    if truncated:
        entries = entries[:_ENTRY_LIMIT]

    parent = os.path.dirname(full)
    if not parent or os.path.normcase(parent) == os.path.normcase(full):
        parent = ""

    return {
        "path": full,
        "parent": parent,
        "entries": entries,
        "roots": _roots(),
        "truncated": truncated,
    }


# 文本文件读取的扩展名白名单
_TEXT_EXTS = {
    "py", "js", "ts", "tsx", "jsx", "html", "htm", "css", "scss", "less",
    "md", "markdown", "txt", "json", "yaml", "yml", "toml", "ini", "cfg",
    "xml", "svg", "csv", "log", "sql", "sh", "bat", "ps1", "rb", "go",
    "java", "c", "h", "cpp", "hpp", "cs", "rs", "php", "swift", "kt",
    "vue", "svelte", "astro",
}

_MAX_FILE_BYTES = 512 * 1024  # 512KB 上限


def read_file(path):
    """读取工作区内任意文件的文本内容（给 IDE 编辑器用）。

    只读、不带写操作。扩展名白名单 + 512KB 上限双重保险。
    非文本或超上限文件返回 ok=False，前端可以降级提示。
    """
    raw = str(path).strip().strip('"').strip("'")
    if raw.startswith("~"):
        raw = os.path.expanduser(raw)
    if not os.path.isabs(raw):
        raise ValueError("请提供绝对路径")
    full = os.path.abspath(os.path.normpath(raw))
    if not os.path.exists(full):
        raise ValueError("文件不存在: %s" % full)
    if os.path.isdir(full):
        raise ValueError("目标是目录不是文件: %s" % full)

    ext = (os.path.splitext(full)[1] or "").lstrip(".").lower()
    if ext not in _TEXT_EXTS:
        raise ValueError("不支持读取该类型文件 (.%s)" % ext)

    size = os.path.getsize(full)
    if size > _MAX_FILE_BYTES:
        raise ValueError("文件过大 (%d 字节)，请先用 Agent file_read 片段读取" % size)

    for enc in ("utf-8", "gbk", "utf-16", "latin-1"):
        try:
            with open(full, "r", encoding=enc) as fh:
                content = fh.read()
            return {
                "path": full,
                "name": os.path.basename(full),
                "size": size,
                "encoding": enc,
                "content": content,
            }
        except UnicodeDecodeError:
            continue
        except OSError as e:
            raise ValueError("读取失败: %s" % e)

    raise ValueError("无法识别文件编码")
