"""SimChat 通讯通道配置 —— SMTP 等 IM/邮件网关的本地配置。

存储位置：``data/config.json`` 的 ``comms`` 段。
敏感字段（密码/AK）通过 ``crypto`` 模块加密后写入，前端永远拿到脱敏视图。

通道列表（前端下拉菜单的 option）在 ``CHANNELS`` 常量中登记，
每个通道声明 ``id / label / description / fields / sensitive_fields``。
"""

import json
import os
import threading

from . import crypto

_WRITE_LOCK = threading.Lock()

# ---- 通道注册表 ----
# fields: [(key, label, placeholder, default), ...]
# sensitive_fields: 需要加密的字段名列表，前端拿到的是脱敏值（"********"）
CHANNELS = {
    "smtp": {
        "id": "smtp",
        "label": "SMTP 邮箱（只读）",
        "description": "SMTP 发信通道，用于通知/报告推送。只读模式仅支持发送，不支持收信。",
        "fields": [
            ("host", "SMTP 服务器", "例如 smtp.example.com", ""),
            ("port", "端口", "465 / 587 / 25", "465"),
            ("use_ssl", "SSL/TLS", None, True),
            ("username", "用户名", "完整邮箱地址", ""),
            ("password", "AK / 授权码", "邮箱密码或专用授权码", ""),
            ("from_email", "发件人地址", "留空则用用户名", ""),
            ("from_name", "发件人名称", "SimChat 通知", "SimChat"),
        ],
        "sensitive_fields": ["password"],
    },
    # 后续可扩展："telegram"、"whatsapp"、"lark" 等
}


def _default_comms():
    return {
        "active": None,  # 当前启用的通道 id
        "channels": {},  # { channel_id: { field_key: value(加密后) } }
    }


def _read_config(data_dir):
    path = os.path.join(data_dir, "config.json")
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    return cfg


def _write_config(data_dir, cfg):
    path = os.path.join(data_dir, "config.json")
    tmp = path + ".tmp"
    with _WRITE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def _sanitize_for_frontend(channel_id, stored_channel, data_dir):
    """把存储态通道数据转为前端可读的脱敏视图。

    - 敏感字段：已加密则显示 "********"；明文（遗留）也显示 "********"；空则 ""
    - 非敏感字段：解密后返回明文（如果存的是密文）
    - 额外标记 ``configured``：敏感字段是否已有值
    """
    meta = CHANNELS.get(channel_id, {})
    sensitive = set(meta.get("sensitive_fields", []))
    out = {}
    any_secret = False
    for key, value in (stored_channel or {}).items():
        if key in sensitive:
            if value:
                any_secret = True
                out[key] = "********"  # 脱敏
            else:
                out[key] = ""
        else:
            # 非敏感字段也可能因为历史 bug 带密文前缀，尝试解密
            out[key] = crypto.decrypt(value, data_dir) if crypto.is_encrypted(value) else value or ""
    out["_configured"] = any_secret
    return out


def list_channels(data_dir):
    """返回所有通道的前端视图（含 active 标记 + 各通道脱敏数据）。"""
    cfg = _read_config(data_dir)
    comms = cfg.get("comms") or _default_comms()
    stored_channels = comms.get("channels") or {}
    active = comms.get("active")

    result = {
        "active": active,
        "channels": [],
    }
    for cid, meta in CHANNELS.items():
        stored = stored_channels.get(cid) or {}
        frontend = _sanitize_for_frontend(cid, stored, data_dir)
        result["channels"].append({
            "id": cid,
            "label": meta["label"],
            "description": meta["description"],
            "fields": [
                {
                    "key": key,
                    "label": label,
                    "placeholder": placeholder or "",
                    "default": default,
                    "sensitive": key in meta.get("sensitive_fields", []),
                    "value": frontend.get(key, ""),
                    "configured": frontend.get("_configured", False),
                }
                for key, label, placeholder, default in meta["fields"]
            ],
        })
    return result


def save_channel(data_dir, channel_id, payload):
    """保存某个通道的配置。payload 是前端提交的 field dict。

    规则：
    - 敏感字段：前端传空串表示「保持不变」（不更新），非空则加密写入
    - 非敏感字段：明文写入（如果恰好带 f1: 前缀先解一下）
    - 返回脱敏后的前端视图
    """
    if channel_id not in CHANNELS:
        raise ValueError("未知通道: %s" % channel_id)
    meta = CHANNELS[channel_id]
    sensitive = set(meta.get("sensitive_fields", []))

    cfg = _read_config(data_dir)
    comms = cfg.get("comms") or _default_comms()
    stored = dict((comms.get("channels") or {}).get(channel_id) or {})

    for key, _label, _ph, _default in meta["fields"]:
        raw = payload.get(key)
        if key in sensitive:
            # 敏感字段：空值 = 保持不变
            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                continue
            plain = str(raw).strip()
            stored[key] = crypto.encrypt(plain, data_dir)
        else:
            if raw is None:
                continue
            value = str(raw).strip()
            # 清理可能的密文前缀（防御性）
            if crypto.is_encrypted(value):
                value = crypto.decrypt(value, data_dir)
            stored[key] = value

    comms.setdefault("channels", {})[channel_id] = stored
    cfg["comms"] = comms
    _write_config(data_dir, cfg)

    return list_channels(data_dir)


def set_active(data_dir, channel_id):
    """启用/停用某个通道。channel_id=None 表示停用所有。"""
    if channel_id is not None and channel_id not in CHANNELS:
        raise ValueError("未知通道: %s" % channel_id)
    cfg = _read_config(data_dir)
    comms = cfg.get("comms") or _default_comms()
    comms["active"] = channel_id
    cfg["comms"] = comms
    _write_config(data_dir, cfg)
    return list_channels(data_dir)


def clear_channel(data_dir, channel_id):
    """清除某个通道的全部配置（同时取消 active 如果就是此通道）。"""
    if channel_id not in CHANNELS:
        raise ValueError("未知通道: %s" % channel_id)
    cfg = _read_config(data_dir)
    comms = cfg.get("comms") or _default_comms()
    channels = comms.get("channels") or {}
    channels.pop(channel_id, None)
    comms["channels"] = channels
    if comms.get("active") == channel_id:
        comms["active"] = None
    cfg["comms"] = comms
    _write_config(data_dir, cfg)
    return list_channels(data_dir)
