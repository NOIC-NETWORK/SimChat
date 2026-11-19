"""AI 实例（Agent）存储与 CRUD。

每个实例是一个独立 JSON 文件，放在 data/agents/ 目录下。
一个实例本质上是「预设 + 系统提示词 + 模型偏好」的集合。
"""

import json
import os
import time
import uuid


DEFAULT_AVATARS = [
    "🤖", "🧠", "🐱", "🦊", "🐼", "🦉", "🐙", "🦄",
    "🎭", "👻", "🧙", "🗡️", "🌱", "🔥", "❄️", "⚡",
]

# 神经引擎参数预设：只调教同一个底层引擎的生成参数，不切换模型或后端。
# 参考 Minecraft 世界类型选择：普通 / 工作 / 代码 / 创意 / 自定义 / W-Synk。
ENGINE_PRESETS = {
    "normal": {
        "label": "普通",
        "description": "日常对话，均衡自然（参数方案 1）",
        "params": {"temperature": 0.7, "top_p": 0.9,
                   "repetition_penalty": 1.15, "max_tokens": 4096},
    },
    "work": {
        "label": "工作",
        "description": "严谨稳定，收敛发散，适合事务与总结",
        "params": {"temperature": 0.35, "top_p": 0.85,
                   "repetition_penalty": 1.1, "max_tokens": 4096},
    },
    "code": {
        "label": "代码",
        "description": "低随机、长输出，适合编程与结构化文本",
        "params": {"temperature": 0.2, "top_p": 0.8,
                   "repetition_penalty": 1.05, "max_tokens": 8192},
    },
    "creative": {
        "label": "创意",
        "description": "高发散，鼓励联想与多样化表达",
        "params": {"temperature": 1.0, "top_p": 0.95,
                   "repetition_penalty": 1.25, "max_tokens": 4096},
    },
    "custom": {
        "label": "自定义参数",
        "description": "手动调节温度、Top P、重复惩罚与最大 tokens",
        "params": {"temperature": 0.7, "top_p": 0.9,
                   "repetition_penalty": 1.15, "max_tokens": 4096},
    },
    "wsynk": {
        "label": "W-Synk",
        "description": "自研动态神经网络模式，波动更大、上下文占用更高",
        "params": {"temperature": 0.85, "top_p": 0.95,
                   "repetition_penalty": 1.35, "max_tokens": 8192},
    },
}

DEFAULT_ENGINE_PRESET = "normal"

_PARAM_SPECS = {
    "temperature": (0.0, 2.0, float),
    "top_p": (0.05, 1.0, float),
    "repetition_penalty": (1.0, 2.0, float),
    "max_tokens": (128, 32768, int),
}


def list_presets():
    """给前端渲染用的预设列表（保持定义顺序）。"""
    return [
        {
            "id": preset_id,
            "label": meta["label"],
            "description": meta["description"],
            "params": dict(meta["params"]),
        }
        for preset_id, meta in ENGINE_PRESETS.items()
    ]


def engine_params_for(preset, raw=None):
    """解析预设参数；只有 custom 采用传入值，并夹到合法区间。"""
    preset = preset if preset in ENGINE_PRESETS else DEFAULT_ENGINE_PRESET
    params = dict(ENGINE_PRESETS[preset]["params"])
    if preset != "custom" or not isinstance(raw, dict):
        return params
    for key, default in params.items():
        low, high, kind = _PARAM_SPECS[key]
        try:
            value = kind(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        params[key] = max(low, min(value, high))
    return params


def _preset_of(agent):
    preset = (agent.get("engine_preset") or "").strip()
    if preset in ENGINE_PRESETS:
        return preset
    # 旧实例：原引擎类型里只有 W-Synk 值得保留，其余统一回到普通预设
    legacy = (agent.get("engine_type") or "").strip().lower()
    return "wsynk" if legacy == "wsynk" else DEFAULT_ENGINE_PRESET


def resolve_engine_params(agent):
    """实例最终生效的生成参数，旧实例自动落到普通预设。"""
    return engine_params_for(_preset_of(agent), agent.get("engine_params"))


def normalize_engine(agent):
    """补齐 engine_preset / engine_params，非 custom 一律使用预设的标准参数。"""
    preset = _preset_of(agent)
    agent["engine_preset"] = preset
    agent["engine_params"] = engine_params_for(preset, agent.get("engine_params"))
    return agent


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id():
    return uuid.uuid4().hex[:12]


def _normalize_equipped(value):
    """装备集合：None = 不限制（旧实例）；列表 = 只允许这些能力名。"""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("equipped 必须是字符串数组或 null")
    seen = set()
    out = []
    for item in value:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _agents_dir(data_root):
    d = os.path.join(data_root, "agents")
    os.makedirs(d, exist_ok=True)
    return d


def _path(data_root, agent_id):
    return os.path.join(_agents_dir(data_root), agent_id + ".json")


def _default(data_root):
    """首次启动时自动创建一个示例实例（仅当没有用户实例时）。

    MOD 生成的只读地图不算用户实例，不阻止默认实例创建。
    """
    if any(not agent.get("readonly") for agent in list_all(data_root)):
        return None
    agent = {
        "id": _new_id(),
        "entity_id": "default",
        "name": "默认实例",
        "description": "SimChat 自带的通用对话实例。",
        "avatar": "/static/sprites/logos/simChat-1.png",
        "avatar_type": "image",
        "is_default": True,
        "system_prompt": "",
        "seed": "",
        "agent_capable": True,
        "allow_advanced": False,
        "desktop_pet": False,
        "engine_preset": DEFAULT_ENGINE_PRESET,
        "engine_params": engine_params_for(DEFAULT_ENGINE_PRESET),
        "equipped": None,
        "readonly": False,
        "source": "",
        "preset_id": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _write(data_root, agent)
    return agent


def _write(data_root, agent):
    path = _path(data_root, agent["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(agent, f, ensure_ascii=False, indent=2)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_all(data_root):
    """返回所有实例，按 updated_at 降序。"""
    agents = []
    d = _agents_dir(data_root)
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        try:
            agent = _read(os.path.join(d, name))
            # 字段兜底：给任何旧文件补齐缺失的新字段
            agent.setdefault("entity_id", "")
            agent.setdefault("avatar_type", "emoji")
            agent.setdefault("seed", "")
            agent.setdefault("agent_capable", True)
            agent.setdefault("allow_advanced", False)
            agent.setdefault("desktop_pet", False)
            agent.setdefault("equipped", None)
            agent.setdefault("readonly", False)
            agent.setdefault("source", "")
            agent.setdefault("preset_id", "")
            normalize_engine(agent)
            agents.append(agent)
        except (OSError, ValueError):
            continue

    # 迁移：首次升级时把旧的默认实例标记出来
    migrated = False
    for a in agents:
        if a.get("is_default"):
            continue
        # 识别特征：id 存在、tags 含"默认"、avatar 是 "🤖"、没有自定义 description 的极简单实例
        is_legacy_default = (
            not a.get("is_default")
            and a.get("tags") == ["默认"]
            and a.get("avatar") == "🤖"
            and a.get("name") in ("默认实例", "默认")
        )
        if is_legacy_default:
            a["is_default"] = True
            a["avatar"] = "/static/sprites/logos/simChat-1.png"
            a["avatar_type"] = "image"
            # 补齐新字段（如果缺失）
            a.setdefault("entity_id", "default")
            a.setdefault("seed", "")
            a.setdefault("agent_capable", True)
            a.setdefault("allow_advanced", False)
            a.setdefault("desktop_pet", False)
            normalize_engine(a)
            _write(data_root, a)
            migrated = True

    if migrated:
        # 重启一遍 list 拿到磁盘上更新后的时间戳
        agents.sort(key=lambda a: a.get("updated_at", ""), reverse=True)
        return agents

    agents.sort(key=lambda a: a.get("updated_at", ""), reverse=True)
    return agents


def get(data_root, agent_id):
    path = _path(data_root, agent_id)
    if not os.path.isfile(path):
        raise ValueError("实例不存在: " + agent_id)
    agent = _read(path)
    agent.setdefault("equipped", None)
    agent.setdefault("readonly", False)
    agent.setdefault("source", "")
    agent.setdefault("preset_id", "")
    return normalize_engine(agent)


def create(data_root, payload):
    """创建新实例。"""
    payload = payload or {}
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("名称不能为空")

    agent = {
        "id": _new_id(),
        "entity_id": (payload.get("entity_id") or "").strip()[:32],
        "name": name[:40],
        "description": (payload.get("description") or "")[:200],
        "avatar": (payload.get("avatar") or DEFAULT_AVATARS[0])[:4],
        "avatar_type": payload.get("avatar_type") or "emoji",
        "system_prompt": payload.get("system_prompt") or "",
        "seed": (payload.get("seed") or "").strip()[:128],
        "agent_capable": bool(payload.get("agent_capable", True)),
        "allow_advanced": bool(payload.get("allow_advanced", False)),
        "desktop_pet": bool(payload.get("desktop_pet", False)),
        "engine_preset": payload.get("engine_preset") or DEFAULT_ENGINE_PRESET,
        "engine_params": payload.get("engine_params"),
        "equipped": _normalize_equipped(payload.get("equipped")),
        "readonly": False,
        "source": "",
        "preset_id": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    normalize_engine(agent)
    _write(data_root, agent)
    return agent


def update(data_root, agent_id, payload):
    payload = payload or {}
    agent = get(data_root, agent_id)
    if agent.get("readonly"):
        raise ValueError(
            "「%s」由 %s 生成，是只读地图，不可编辑"
            % (agent.get("name") or agent_id, agent.get("source") or "MOD")
        )

    if "entity_id" in payload:
        agent["entity_id"] = (payload["entity_id"] or "").strip()[:32]
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise ValueError("名称不能为空")
        agent["name"] = name[:40]
    if "description" in payload:
        agent["description"] = (payload["description"] or "")[:200]
    if "avatar" in payload:
        agent["avatar"] = (payload["avatar"] or DEFAULT_AVATARS[0])[:4]
    if "avatar_type" in payload:
        agent["avatar_type"] = payload["avatar_type"] or "emoji"
    if "system_prompt" in payload:
        agent["system_prompt"] = payload["system_prompt"] or ""
    if "seed" in payload:
        agent["seed"] = (payload["seed"] or "").strip()[:128]
    if "agent_capable" in payload:
        agent["agent_capable"] = bool(payload["agent_capable"])
    if "allow_advanced" in payload:
        agent["allow_advanced"] = bool(payload["allow_advanced"])
    if "desktop_pet" in payload:
        agent["desktop_pet"] = bool(payload["desktop_pet"])
    if "engine_preset" in payload:
        agent["engine_preset"] = payload["engine_preset"]
    if "engine_params" in payload:
        agent["engine_params"] = payload["engine_params"]
    if "equipped" in payload:
        agent["equipped"] = _normalize_equipped(payload["equipped"])
    normalize_engine(agent)

    agent["updated_at"] = _now_iso()
    _write(data_root, agent)
    return agent


def delete(data_root, agent_id):
    path = _path(data_root, agent_id)
    if not os.path.isfile(path):
        raise ValueError("实例不存在: " + agent_id)
    agent = _read(path)
    if agent.get("is_default"):
        raise ValueError("默认实例不可删除，但可以编辑配置")
    if agent.get("readonly"):
        raise ValueError(
            "「%s」由 %s 生成，是只读地图，不可删除"
            % (agent.get("name") or agent_id, agent.get("source") or "MOD")
        )
    os.remove(path)
    return True


def reset_to_defaults(data_root):
    """删除所有自定义实例，重新创建默认实例；MOD 生成的只读地图保留。"""
    d = _agents_dir(data_root)
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            if _read(path).get("readonly"):
                continue
            os.remove(path)
        except (OSError, ValueError):
            pass
    return _default(data_root)


_PRESET_FIELDS = (
    "name", "description", "avatar", "avatar_type", "system_prompt", "seed",
    "agent_capable", "allow_advanced", "desktop_pet", "engine_preset",
    "engine_params", "equipped", "readonly", "source", "preset_id",
)


def _apply_preset(preset, current=None):
    """把 MOD 上报的地图预设转成实例字段，返回 (agent, changed)。"""
    preset_id = str(preset.get("preset_id") or "").strip()
    name = (preset.get("name") or "").strip()
    if not preset_id or not name:
        raise ValueError("地图预设缺少 preset_id 或 name")

    agent = dict(current) if current else {
        "id": _new_id(),
        "entity_id": "",
        "is_default": False,
        "created_at": _now_iso(),
    }
    agent["preset_id"] = preset_id
    agent["source"] = str(preset.get("source") or "")
    agent["readonly"] = True
    agent["name"] = name[:40]
    agent["description"] = (preset.get("description") or "")[:200]
    agent["avatar"] = str(preset.get("avatar") or "🤖")[:200]
    agent["avatar_type"] = preset.get("avatar_type") or "emoji"
    agent["system_prompt"] = preset.get("system_prompt") or ""
    agent["seed"] = str(preset.get("seed") or "")[:128]
    agent["agent_capable"] = bool(preset.get("agent_capable", True))
    agent["allow_advanced"] = bool(preset.get("allow_advanced", False))
    agent["desktop_pet"] = bool(preset.get("desktop_pet", False))
    agent["engine_preset"] = preset.get("engine_preset") or DEFAULT_ENGINE_PRESET
    agent["engine_params"] = preset.get("engine_params")
    agent["equipped"] = _normalize_equipped(preset.get("equipped"))
    normalize_engine(agent)

    changed = current is None
    if current is not None:
        for key in _PRESET_FIELDS:
            if agent.get(key) != current.get(key):
                changed = True
                break
    return agent, changed


def sync_presets(data_root, presets):
    """把 MOD 地图预设幂等落盘为只读实例，返回新建或更新过的实例。"""
    current_by_preset = {}
    for agent in list_all(data_root):
        preset_id = agent.get("preset_id")
        if preset_id:
            current_by_preset[preset_id] = agent

    touched = []
    for preset in presets or []:
        if not isinstance(preset, dict):
            continue
        try:
            current = current_by_preset.get(str(preset.get("preset_id") or ""))
            agent, changed = _apply_preset(preset, current)
        except (ValueError, TypeError):
            continue
        if not changed:
            continue
        agent["updated_at"] = _now_iso()
        _write(data_root, agent)
        touched.append(agent)
    return touched
