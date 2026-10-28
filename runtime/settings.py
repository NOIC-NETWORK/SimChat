"""SimChat 基础设置 —— 对话参数与外观。

写入 config.json 的 settings 段；provider / ollama / openai_compat 段由 provider_config 管理，
本模块不碰。读写模式复用 provider_config._write() 的原子写。

白名单字段（范围校验）：
  max_history    4 – 200
  temperature    0 – 2   (float)
  max_tokens     128 – 32768
  system_prompt  string（空允许）
  send_with_enter  bool
  show_token_bar   bool
  theme          system | light | dark
  font_scale     0.8 – 1.4
  quota          { limit: int, period: day|month, lock: bool }
"""

import json
import os
import threading

_DEFAULT_SETTINGS = {
    "max_history": 40,
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": "",
    "send_with_enter": True,
    "show_token_bar": True,
    "theme": "system",
    "font_scale": 1.0,
    "quota": {"limit": 0, "period": "day", "lock": False},
}

_WRITE_LOCK = threading.Lock()


def defaults():
    """返回默认设置副本。"""
    return json.loads(json.dumps(_DEFAULT_SETTINGS))


def _clamp(value, lo, hi, cast=None):
    try:
        num = cast(value) if cast else value
    except (TypeError, ValueError):
        return lo
    if num < lo:
        return lo
    if num > hi:
        return hi
    return num


def validate(raw):
    """把任意 dict 规整成合法 settings，未知字段丢弃。"""
    out = defaults()
    if not isinstance(raw, dict):
        return out

    # 整数范围
    mh = raw.get("max_history")
    if mh is not None:
        out["max_history"] = _clamp(mh, 4, 200, int)

    mt = raw.get("max_tokens")
    if mt is not None:
        out["max_tokens"] = _clamp(mt, 128, 32768, int)

    # 浮点
    tp = raw.get("temperature")
    if tp is not None:
        out["temperature"] = round(_clamp(tp, 0.0, 2.0, float), 2)

    fs = raw.get("font_scale")
    if fs is not None:
        out["font_scale"] = round(_clamp(fs, 0.8, 1.4, float), 2)

    # 字符串
    sp = raw.get("system_prompt")
    if isinstance(sp, str):
        out["system_prompt"] = sp

    theme = raw.get("theme")
    if theme in ("system", "light", "dark"):
        out["theme"] = theme

    # 布尔
    for key in ("send_with_enter", "show_token_bar"):
        if key in raw and isinstance(raw[key], bool):
            out[key] = raw[key]

    # 额度
    quota = raw.get("quota")
    if isinstance(quota, dict):
        q = dict(out["quota"])
        q["limit"] = _clamp(quota.get("limit", 0), 0, 10 ** 9, int)
        if quota.get("period") in ("day", "month"):
            q["period"] = quota["period"]
        if isinstance(quota.get("lock"), bool):
            q["lock"] = quota["lock"]
        out["quota"] = q

    return out


def load(data_dir):
    """从 data_dir/config.json 读取 settings 段，缺失则补默认值。"""
    path = os.path.join(data_dir, "config.json")
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    raw = cfg.get("settings") or {}
    return validate(raw)


def save(data_dir, current_settings, updates):
    """合并 updates 并原子写回 config.json 的 settings 段。返回新 settings。"""
    path = os.path.join(data_dir, "config.json")
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    merged = validate({**(current_settings or {}), **(updates or {})})
    cfg["settings"] = merged

    tmp = path + ".tmp"
    with _WRITE_LOCK:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    return merged


def reset(data_dir, scope="settings"):
    """scope=settings 只清 settings 段；scope=all 由 provider_config 负责（此处预留）。"""
    if scope == "settings":
        return save(data_dir, {}, defaults())
    raise ValueError("未知 reset scope: %s" % scope)
