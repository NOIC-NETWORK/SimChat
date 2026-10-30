"""用户个人档案 — 运行时存档，.gitignore 保证不上 GitHub。

职责：
  1. 存放用户名、生日、紧急联系人等个人信息
  2. SimChatCore 启动时检查：profile 缺失 → 前端引导注册页
  3. 跟 config.json 同目录，走同一个 data/ 根

存档格式（data/profile.json）：
{
  "version": 1,
  "username": "User",           // 必填，之后 SimChat 用这个称呼用户
  "birthday": "YYYY-MM-DD",     // 可选
  "emergency_contact": "...",   // 可选
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}

MOD 不得绕过本模块直接读写 profile.json。
"""

import json
import os
import threading
from datetime import datetime, timezone

PROFILE_VERSION = 1

_save_lock = threading.Lock()

_REQUIRED_FIELDS = ("username",)


def _iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _path(data_root):
    return os.path.join(data_root, "profile.json")


def has_profile(data_root):
    """是否已有用户档案（文件存在且非空）。"""
    path = _path(data_root)
    if not os.path.isfile(path):
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    return size > 0


def load_profile(data_root):
    """加载用户档案。档案缺失或损坏时返回 {}。"""
    path = _path(data_root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_profile(data_root, payload):
    """保存用户档案（首次创建或更新）。原子写入，返回新档案。

    校验：username 必填且非空，其他字段可选。
    payload: dict，含 username / birthday / emergency_contact 等。
    """
    payload = dict(payload or {})
    username = str(payload.get("username") or "").strip()
    if not username:
        raise ValueError("用户名不能为空")

    os.makedirs(data_root, exist_ok=True)
    path = _path(data_root)
    now = _iso_now()

    existing = load_profile(data_root)
    created_at = existing.get("created_at") or now

    profile = {
        "version": PROFILE_VERSION,
        "username": username,
        "birthday": str(payload.get("birthday") or existing.get("birthday") or "").strip(),
        "emergency_contact": str(payload.get("emergency_contact") or existing.get("emergency_contact") or "").strip(),
        "created_at": created_at,
        "updated_at": now,
    }

    tmp = path + ".tmp"
    with _save_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    return profile


def delete_profile(data_root):
    """删除用户档案（注销）。"""
    path = _path(data_root)
    if os.path.isfile(path):
        os.remove(path)
