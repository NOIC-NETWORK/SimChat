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
# group / group_label: 前端把同一组通道渲染成一组按钮（群机器人有两种接入方式）
# field_types / choices: 非文本控件（textarea / select）
# runtime_supported: 该通道有真实收发运行时（启动/停止/测试/Webhook）
CHANNELS = {
    "qq_group_onebot": {
        "id": "qq_group_onebot",
        "label": "Python 库（OneBot v11）",
        "description": "接入 NapCatQQ / Lagrange / go-cqhttp 等 OneBot v11 实现（nonebot2 / aiocqhttp 生态）。"
                       "WebSocket 模式由 SimChat 主动连接；HTTP 模式则接收反向 Webhook。",
        "group": "qq_group",
        "group_label": "群机器人",
        "runtime_supported": True,
        "fields": [
            ("transport", "连接方式", None, "ws"),
            ("ws_url", "OneBot WebSocket 地址", "ws://127.0.0.1:3001", "ws://127.0.0.1:3001"),
            ("http_url", "OneBot HTTP API 地址", "http://127.0.0.1:3000", "http://127.0.0.1:3000"),
            ("access_token", "Access Token", "OneBot 端配置的 access_token", ""),
            ("self_qq", "机器人 QQ 号", "与 OneBot 端登录的账号一致", ""),
            ("group_whitelist", "群号白名单", "逗号/换行分隔；留空 = 所有群", ""),
            ("require_at", "@ 触发", None, True),
            ("prefix", "触发前缀", "可选，例如 /ai；留空表示不要求前缀", ""),
            ("auto_online", "自动上线（启动时自动连接）", None, False),
            ("auto_reply", "自动回复", None, True),
            ("system_prompt", "群聊系统提示词", "留空则使用全局系统提示词", ""),
            ("provider", "模型服务商", None, ""),
            ("model", "模型（可覆盖）", "留空跟随服务商默认，例如 qwen-max", ""),
        ],
        "sensitive_fields": ["access_token"],
        "field_types": {"transport": "select", "system_prompt": "textarea", "provider": "select"},
        "choices": {
            "transport": [["ws", "WebSocket（主动连接）"], ["http", "HTTP（反向 Webhook）"]],
            "provider": [["", "跟随全局（Auto）"], ["openai_compat", "OpenAI 兼容"], ["ollama", "Ollama（本地）"]],
        },
    },
    "qq_group_official": {
        "id": "qq_group_official",
        "label": "QQ 官方 API",
        "description": "接入 QQ 机器人开放平台 OpenAPI（AppID + AppSecret）。"
                       "WebSocket 模式免公网，Webhook 模式需公网 HTTPS（端口 80/443/8080/8443）。",
        "group": "qq_group",
        "group_label": "群机器人",
        "runtime_supported": True,
        "fields": [
            ("transport", "连接方式", None, "ws"),
            ("app_id", "AppID", "开放平台机器人 AppID", ""),
            ("app_secret", "AppSecret", "开放平台机器人密钥", ""),
            ("api_base", "API Base", "https://api.bot.qq.com", "https://api.bot.qq.com"),
            ("token_url", "AccessToken 地址", "https://api.bot.qq.com/app/getAppAccessToken", "https://api.bot.qq.com/app/getAppAccessToken"),
            ("group_whitelist", "群 OpenID 白名单", "逗号/换行分隔；留空 = 所有群", ""),
            ("auto_online", "自动上线（启动时自动连接）", None, False),
            ("auto_reply", "自动回复", None, True),
            ("system_prompt", "群聊系统提示词", "留空则使用全局系统提示词", ""),
            ("provider", "模型服务商", None, ""),
            ("model", "模型（可覆盖）", "留空跟随服务商默认，例如 qwen-max", ""),
        ],
        "sensitive_fields": ["app_secret"],
        "field_types": {"transport": "select", "system_prompt": "textarea", "provider": "select"},
        "choices": {
            "transport": [["ws", "WebSocket（免公网）"], ["webhook", "Webhook（需公网 HTTPS）"]],
            "provider": [["", "跟随全局（Auto）"], ["openai_compat", "OpenAI 兼容"], ["ollama", "Ollama（本地）"]],
        },
    },
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

    - 敏感字段：有值则显示 "********"；空则 ""
    - 非敏感字段：解密后返回明文（如果存的是密文）
    - 额外标记 ``_configured``：该字段是否已有值（敏感字段用此判断「已保存」）
    """
    meta = CHANNELS.get(channel_id, {})
    sensitive = set(meta.get("sensitive_fields", []))
    out = {}
    configured = set()
    for key, value in (stored_channel or {}).items():
        if key in sensitive:
            if value:
                configured.add(key)
                out[key] = "********"  # 脱敏
            else:
                out[key] = ""
        else:
            # 非敏感字段也可能因为历史 bug 带密文前缀，尝试解密
            out[key] = crypto.decrypt(value, data_dir) if crypto.is_encrypted(value) else value or ""
            if out[key]:
                configured.add(key)
    out["_configured"] = configured
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
        configured = frontend.get("_configured") or set()
        field_types = meta.get("field_types") or {}
        choices = meta.get("choices") or {}
        result["channels"].append({
            "id": cid,
            "label": meta["label"],
            "description": meta["description"],
            "group": meta.get("group"),
            "group_label": meta.get("group_label"),
            "runtime_supported": bool(meta.get("runtime_supported")),
            "fields": [
                {
                    "key": key,
                    "label": label,
                    "placeholder": placeholder or "",
                    "default": default,
                    "type": field_types.get(key, "text"),
                    "choices": choices.get(key) or [],
                    "sensitive": key in meta.get("sensitive_fields", []),
                    "value": frontend.get(key, ""),
                    "configured": key in configured,
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


def _coerce(value, default):
    """按字段默认值的类型把存储态值转回 Python 类型。"""
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in ("1", "true", "yes", "on", "是", "启用")
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    text = "" if value is None else str(value)
    if not text and default:
        return default
    return text


def get_channel_config(data_dir, channel_id):
    """读取并解密某个通道的完整配置（仅后端运行时使用，绝不返回给前端）。

    返回的 dict 按字段默认值做类型转换：布尔转 bool，整数转 int，空字符串回落到默认。
    """
    if channel_id not in CHANNELS:
        raise ValueError("未知通道: %s" % channel_id)
    meta = CHANNELS[channel_id]
    sensitive = set(meta.get("sensitive_fields", []))
    stored = ((_read_config(data_dir).get("comms") or {}).get("channels") or {}).get(channel_id) or {}
    out = {}
    for key, _label, _placeholder, default in meta["fields"]:
        raw = stored.get(key)
        if key in sensitive:
            value = crypto.decrypt(raw, data_dir) if raw else ""
        else:
            if raw is None:
                value = default
            elif crypto.is_encrypted(raw):
                value = crypto.decrypt(raw, data_dir)
            else:
                value = raw
        out[key] = _coerce(value, default)
    return out


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
