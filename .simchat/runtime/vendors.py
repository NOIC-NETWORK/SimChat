"""厂牌注册表 —— 服务商四层模型（Vendor / Transport / Account / Model）的静态数据层。

设计要点：
  1. 厂牌（Vendor）是用户认知单位：火山方舟、阿里云百炼、Ollama……
  2. 协议（Transport）是请求适配器：ollama / openai_compat / anthropic / bedrock（规划）。
  3. 一期没有独立账户表：账户 = 旧配置块（ollama / openai_compat / anthropic）里的
     一份凭据，块内可选 ``vendor`` 字段记录厂牌；读取时由 resolve_target() 归一化。
  4. 模型清单是静态建议（models），实时列表仍由 provider_config 探测覆盖。

本模块只做「身份与能力描述」，不发网络请求、不写配置，供 provider_config /
providers / core / web 复用，避免各处硬编码协议与厂牌对应关系。
"""

import copy

BLOCK_TRANSPORTS = ("ollama", "openai_compat", "anthropic")

# 厂牌顺序即 UI 建议顺序。default_base 为空表示必须由用户填写。
# dialect.param_whitelist 为 None 时表示使用该 Transport 的默认白名单。
VENDORS = {
    "ollama": {
        "id": "ollama",
        "label": "Ollama（本地）",
        "transport": "ollama",
        "default_base": "http://127.0.0.1:11434",
        "auth": "none",
        "implemented": True,
        "models": [],
        "dialect": {"notes": ["通过 ollama Python 库直连，base_url 仅用于状态探测"]},
    },
    "dashscope": {
        "id": "dashscope",
        "label": "阿里云百炼",
        "transport": "openai_compat",
        "default_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "auth": "bearer",
        "implemented": True,
        "models": [
            {"id": "qwen-max", "notes": "百炼通用旗舰"},
            {"id": "qwen-plus", "notes": "通用均衡"},
            {"id": "qwen3-235b-a22b", "params": {"enable_thinking": False}},
        ],
        "dialect": {
            "param_whitelist": [
                "enable_thinking", "temperature", "top_p", "max_tokens",
                "seed", "stop", "stream_options",
            ],
            "notes": ["enable_thinking 仅 Qwen3 系列支持，默认不下发"],
        },
    },
    "volcengine": {
        "id": "volcengine",
        "label": "火山方舟",
        "transport": "openai_compat",
        "default_base": "https://ark.cn-beijing.volces.com/api/v3",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {
            "model_id_pattern": "^ep-",
            "notes": ["模型 ID 填推理接入点 ID（ep- 开头），不自动改写"],
        },
    },
    "qianfan": {
        "id": "qianfan",
        "label": "百度千帆",
        "transport": "openai_compat",
        "default_base": "https://qianfan.baidubce.com/v2",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {"notes": ["使用千帆 v2 OpenAI 兼容接口"]},
    },
    "azure_openai": {
        "id": "azure_openai",
        "label": "Azure OpenAI",
        "transport": "openai_compat",
        "default_base": "",
        "auth": "api-key",
        "implemented": True,
        "models": [],
        "dialect": {
            "requires_api_version": True,
            "notes": [
                "API Base 填到 /openai/deployments/<部署名> 为止",
                "鉴权使用 api-key 头，api-version 作为 query 追加",
            ],
        },
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "transport": "openai_compat",
        "default_base": "https://api.openai.com/v1",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {},
    },
    "siliconflow": {
        "id": "siliconflow",
        "label": "硅基流动",
        "transport": "openai_compat",
        "default_base": "https://api.siliconflow.cn/v1",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {},
    },
    "deepseek": {
        "id": "deepseek",
        "label": "DeepSeek",
        "transport": "openai_compat",
        "default_base": "https://api.deepseek.com/v1",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {},
    },
    "custom_openai": {
        "id": "custom_openai",
        "label": "自定义 OpenAI 兼容",
        "transport": "openai_compat",
        "default_base": "",
        "auth": "bearer",
        "implemented": True,
        "models": [],
        "dialect": {"notes": ["自建 / 中转 / OneAPI 等兼容 /chat/completions 的端点"]},
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Anthropic",
        "transport": "anthropic",
        "default_base": "https://api.anthropic.com",
        "auth": "x-api-key",
        "implemented": True,
        "models": [],
        "dialect": {},
    },
    "aws_bedrock": {
        "id": "aws_bedrock",
        "label": "AWS Bedrock",
        "transport": "bedrock",
        "default_base": "",
        "auth": "sigv4",
        "implemented": False,
        "models": [],
        "dialect": {
            "notes": [
                "规划中：SigV4 签名与 Bedrock 模型 ID 格式尚未实现",
                "不提供假实现，选择时明确报错",
            ],
        },
    },
}

# 主机名 → 厂牌，用于旧配置没有 vendor 字段时推断。
_HOST_HINTS = (
    ("openai.azure.com", "azure_openai"),
    ("volces.com", "volcengine"),
    ("ark.cn-beijing", "volcengine"),
    ("dashscope", "dashscope"),
    ("aliyuncs.com", "dashscope"),
    ("qianfan", "qianfan"),
    ("baidubce.com", "qianfan"),
    ("siliconflow", "siliconflow"),
    ("deepseek.com", "deepseek"),
    ("api.openai.com", "openai"),
)


def list_vendors(include_unimplemented=True):
    """返回厂牌列表（深拷贝，防止调用方修改注册表）。"""
    items = []
    for entry in VENDORS.values():
        if not include_unimplemented and not entry.get("implemented"):
            continue
        items.append(copy.deepcopy(entry))
    return items


def get_vendor(vendor_id):
    entry = VENDORS.get(str(vendor_id or "").strip().lower())
    return copy.deepcopy(entry) if entry else None


def vendor_ids():
    return list(VENDORS.keys())


def transport_of(name):
    """接受厂牌 id 或协议 id，返回协议名；未知返回 None。"""
    value = str(name or "").strip().lower()
    if not value:
        return None
    if value in BLOCK_TRANSPORTS or value == "bedrock":
        return value
    entry = VENDORS.get(value)
    return entry["transport"] if entry else None


def block_of(name):
    """接受厂牌 id 或协议 id，返回旧配置块名；bedrock 等无配置块的返回 None。"""
    transport = transport_of(name)
    if transport in BLOCK_TRANSPORTS:
        return transport
    return None


def infer_vendor(transport, base_url):
    """根据协议与端点推断厂牌 id（旧配置无 vendor 字段时使用）。"""
    transport = str(transport or "").strip().lower()
    if transport == "ollama":
        return "ollama"
    if transport == "anthropic":
        return "anthropic"
    base = str(base_url or "").strip().lower()
    for hint, vendor_id in _HOST_HINTS:
        if hint in base:
            return vendor_id
    return "custom_openai"


def vendor_for_conf(block, conf):
    """解析某个旧配置块当前属于哪个厂牌。

    块内显式写 vendor 且协议匹配时优先；否则按 base_url 推断。
    """
    conf = dict(conf or {})
    block = str(block or "").strip().lower()
    if block in ("ollama", "anthropic"):
        return block
    raw = str(conf.get("vendor") or "").strip().lower()
    entry = VENDORS.get(raw)
    if entry and entry.get("transport") == "openai_compat":
        return raw
    return infer_vendor(block, conf.get("api_base"))


def default_base(name):
    entry = VENDORS.get(str(name or "").strip().lower())
    return entry.get("default_base") if entry else ""


def resolve_target(cfg, name=None):
    """把厂牌 id / 协议 id 归一化为一次调用所需的账户视图。

    返回 None 表示无法解析（未知名称、未实现协议，或 auto 且配置里没有可用选择）。
    结构：{vendor, vendor_label, transport, block, conf, implemented}
    conf 在原配置块基础上补齐 vendor / transport / auth / params，供 providers 使用。
    """
    cfg = dict(cfg or {})
    value = str(name or "").strip().lower()
    if value in ("", "auto"):
        value = str(cfg.get("provider") or "").strip().lower()
    transport = transport_of(value)
    if transport is None:
        return None
    if transport == "bedrock":
        return None
    block = value if value in BLOCK_TRANSPORTS else block_of(value)
    if not block:
        return None

    conf = dict(cfg.get(block) or {})
    vendor_id = vendor_for_conf(block, conf)
    entry = VENDORS.get(vendor_id) or {}

    if transport in ("openai_compat", "anthropic") and not str(conf.get("api_base") or "").strip():
        if entry.get("default_base"):
            conf["api_base"] = entry["default_base"]
    if transport == "openai_compat" and not str(conf.get("auth") or "").strip():
        conf["auth"] = entry.get("auth") or "bearer"

    conf["vendor"] = vendor_id
    conf["transport"] = transport
    return {
        "vendor": vendor_id,
        "vendor_label": entry.get("label") or vendor_id,
        "transport": transport,
        "transport_label": {
            "ollama": "Ollama 原生",
            "openai_compat": "OpenAI 兼容",
            "anthropic": "Anthropic 消息",
        }.get(transport, transport),
        "block": block,
        "implemented": bool(entry.get("implemented", True)),
        "conf": conf,
    }


def error_for(name):
    """把无法解析的服务商名转成用户能读懂的错误。"""
    value = str(name or "").strip().lower()
    if value == "aws_bedrock" or transport_of(value) == "bedrock":
        return "AWS Bedrock 传输尚未实现（规划中）"
    return "未知服务商或传输协议: %s" % (name or "（空）")
