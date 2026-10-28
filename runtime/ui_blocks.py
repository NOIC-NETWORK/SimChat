"""UI 方块材质目录 —— MOD 的资源包式接口。

SimChat 的 HTML 界面按「方块」组织：每个具名方块（如 provider.ollama）
在页面里对应一个元素。MOD 只能覆盖方块的展示材质（label / icon / hint /
description / order），不能修改服务商检测、配置校验、保存与对话门禁逻辑。

类似 Minecraft：材质包能换贴图，但改不了游戏规则。

宿主 / MOD 适配器可调用：
  register_block_skin("provider.ollama", label="本地模型", icon="...")
  register_preset("my-endpoint", "openai_compat", "我的端点", {...})

配置自动化接口见 provider_config.save() / provider_config.test() 以及
Web API：GET/POST /api/providers、POST /api/providers/test。
"""

import threading

_SKIN_KEYS = frozenset(["label", "icon", "hint", "description", "order"])

_DEFAULT_BLOCKS = [
    # --- 基础设置 ---
    {"id": "setup.title", "label": "连接一个服务商", "icon": "", "hint": "配置保存后即可开始对话", "description": "", "order": 10},
    {"id": "setup.subtitle", "label": "SimChat", "icon": "", "hint": "", "description": "SimChat 需要一个可用的模型服务才能开始对话。API 信息只保存在本地。", "order": 20},
    {"id": "provider.auto", "label": "Auto Model", "icon": "", "hint": "自动选择当前最优的可用服务商（本地 Ollama 优先）", "description": "", "order": 29},
    {"id": "provider.ollama", "label": "Ollama（本地）", "icon": "", "hint": "需要本地 Ollama 服务，模型需已安装", "description": "", "order": 30},
    {"id": "provider.openai_compat", "label": "OpenAI 兼容", "icon": "", "hint": "任何兼容 /chat/completions 的端点", "description": "", "order": 31},
    {"id": "setup.test", "label": "测试连接", "icon": "", "hint": "", "description": "", "order": 40},
    {"id": "setup.save", "label": "保存并检测", "icon": "", "hint": "", "description": "", "order": 41},
    {"id": "setup.back", "label": "返回对话", "icon": "", "hint": "", "description": "", "order": 42},

    # --- 基础设置新方块（P0） ---
    {"id": "settings.title", "label": "基础设置", "icon": "", "hint": "", "description": "", "order": 50},
    {"id": "settings.group.basic", "label": "对话参数", "icon": "", "hint": "", "description": "", "order": 60},
    {"id": "settings.group.appearance", "label": "外观", "icon": "", "hint": "", "description": "", "order": 70},
    {"id": "settings.advanced", "label": "高级功能设置 ▸", "icon": "", "hint": "进入完整控制台", "description": "", "order": 80},
    {"id": "settings.save", "label": "保存设置", "icon": "", "hint": "", "description": "", "order": 90},
    {"id": "settings.reset", "label": "恢复默认", "icon": "", "hint": "", "description": "", "order": 91},

    # --- 控制台顶部 ---
    {"id": "console.title", "label": "高级功能设置", "icon": "", "hint": "", "description": "", "order": 100},
    {"id": "console.back", "label": "← 返回基础设置", "icon": "", "hint": "", "description": "", "order": 110},
    {"id": "console.group.control", "label": "控制", "icon": "", "hint": "", "description": "", "order": 120},
    {"id": "console.group.agent", "label": "代理", "icon": "", "hint": "", "description": "", "order": 121},
    {"id": "console.group.config", "label": "配置", "icon": "", "hint": "", "description": "", "order": 122},

    # --- 控制台分区 ---
    {"id": "console.section.overview", "label": "概览", "icon": "", "hint": "", "description": "", "order": 200},
    {"id": "console.section.comms", "label": "通讯", "icon": "", "hint": "", "description": "", "order": 210},
    {"id": "console.section.instances", "label": "实例", "icon": "", "hint": "", "description": "", "order": 220},
    {"id": "console.section.sessions", "label": "会话", "icon": "", "hint": "", "description": "", "order": 230},
    {"id": "console.section.usage", "label": "使用情况", "icon": "", "hint": "", "description": "", "order": 240},
    {"id": "console.section.automation", "label": "自动化", "icon": "", "hint": "", "description": "", "order": 250},
    {"id": "console.section.agent", "label": "代理", "icon": "", "hint": "", "description": "", "order": 260},
    {"id": "console.section.skills", "label": "技能", "icon": "", "hint": "", "description": "", "order": 270},
    {"id": "console.section.nodes", "label": "节点", "icon": "", "hint": "", "description": "", "order": 280},
    {"id": "console.section.system", "label": "配置", "icon": "", "hint": "", "description": "", "order": 290},
    {"id": "console.section.debug", "label": "调试", "icon": "", "hint": "", "description": "", "order": 300},
    {"id": "console.section.logs", "label": "日志", "icon": "", "hint": "", "description": "", "order": 310},

    # --- 通用状态 ---
    {"id": "console.state.empty", "label": "暂无数据", "icon": "", "hint": "", "description": "", "order": 400},
    {"id": "console.state.unavailable", "label": "该模块尚未接入", "icon": "", "hint": "", "description": "", "order": 401},
    {"id": "console.state.loading", "label": "加载中…", "icon": "", "hint": "", "description": "", "order": 402},
]

_lock = threading.Lock()
_blocks = {item["id"]: dict(item) for item in _DEFAULT_BLOCKS}
_presets = {}


def list_blocks():
    with _lock:
        items = [dict(item) for item in _blocks.values()]
    items.sort(key=lambda item: (item.get("order", 100), item["id"]))
    return items


def register_block_skin(block_id, **skin):
    """覆盖一个方块的展示材质。未知方块或未知字段直接拒绝。"""
    unknown = sorted(set(skin) - _SKIN_KEYS)
    if unknown:
        raise ValueError("不支持修改的材质字段: %s" % ", ".join(unknown))
    with _lock:
        if block_id not in _blocks:
            raise KeyError("未知方块: %s" % block_id)
        _blocks[block_id].update(skin)
        return dict(_blocks[block_id])


def register_preset(preset_id, provider, label, values=None, description="", order=100):
    """注册一个服务商预设（只负责预填字段，点击后仍需本体校验与保存）。"""
    if provider not in ("ollama", "openai_compat"):
        raise ValueError("预设的 provider 必须是 ollama 或 openai_compat")
    if not preset_id or not label:
        raise ValueError("预设需要 preset_id 与 label")
    entry = {
        "id": preset_id,
        "provider": provider,
        "label": label,
        "values": dict(values or {}),
        "description": description,
        "order": int(order),
    }
    with _lock:
        _presets[preset_id] = entry
        return dict(entry)


def unregister_preset(preset_id):
    with _lock:
        return _presets.pop(preset_id, None) is not None


def list_presets():
    with _lock:
        items = [dict(item) for item in _presets.values()]
    items.sort(key=lambda item: (item.get("order", 100), item["id"]))
    return items


def reset():
    """仅供测试使用：恢复默认材质并清空预设。"""
    with _lock:
        _blocks.clear()
        _blocks.update({item["id"]: dict(item) for item in _DEFAULT_BLOCKS})
        _presets.clear()
