"""Kirara 行为包的第一批方块（阶段 1：方块化）。

设计约束：
- 只读行为，不写文件、不联网、不起子进程；
- 不 import 包内 JRVS / services / 前端资源，避免把旧业务路径带进沙箱；
- 事实条目走本地 JSON，用户可在 api.data_dir 放同名文件覆盖；
- 性格由人设提示词负责，这里只负责“给出一条带出处的小知识”。
"""

import json
import os
import random
import re

_API = None
_FACTS_CACHE = None
_FACTS_CACHE_PATH = None

_TRIVIA_PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {
            "type": "string",
            "description": "当前对话涉及的元素或主题；为空时随机给一条通用小知识",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "本次会话已经用过的小知识 id，避免重复",
        },
    },
}

_TOKEN_SPLIT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def bind_api(api):
    """由 entry 在加载时注入宿主句柄，供方块读取 data_dir 中的用户覆盖条目。"""
    global _API
    _API = api


def _facts_candidates():
    """返回候选文件路径：data_dir 覆盖优先，包内条目兜底。"""
    candidates = []
    if _API is not None and getattr(_API, "data_dir", None):
        candidates.append(os.path.join(_API.data_dir, "trivia_facts.json"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "trivia_facts.json"))
    return candidates


def _load_facts():
    global _FACTS_CACHE, _FACTS_CACHE_PATH
    for path in _facts_candidates():
        try:
            if not os.path.isfile(path):
                continue
            if _FACTS_CACHE is not None and _FACTS_CACHE_PATH == path:
                return _FACTS_CACHE
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            facts = data.get("facts") if isinstance(data, dict) else data
            if not isinstance(facts, list):
                continue
            clean = [item for item in facts if isinstance(item, dict) and item.get("fact")]
            if not clean:
                continue
            _FACTS_CACHE = clean
            _FACTS_CACHE_PATH = path
            return clean
        except Exception:
            continue
    _FACTS_CACHE = []
    _FACTS_CACHE_PATH = None
    return []


def _tokens(text):
    if not isinstance(text, str):
        return []
    return [token for token in _TOKEN_SPLIT_RE.split(text.lower()) if token]


def _score(fact, topic, tokens):
    if not topic:
        return 0
    haystack = topic.lower()
    score = 0
    for keyword in fact.get("keywords") or []:
        if not isinstance(keyword, str) or not keyword:
            continue
        kw = keyword.lower()
        if kw in haystack:
            score += 3 if len(kw) >= 2 else 1
            continue
        if kw in tokens:
            score += 2
    for tag in fact.get("tags") or []:
        if isinstance(tag, str) and tag and tag.lower() in haystack:
            score += 1
    return score


def trivia(params=None):
    """kirara.trivia 的 backend：返回一条与 topic 相关的小知识。

    找不到相关条目时返回 found=False，并明确提示不要编造；不抛异常，
    避免小知识失败影响主回答。
    """
    params = params if isinstance(params, dict) else {}
    topic = params.get("topic")
    topic = topic.strip() if isinstance(topic, str) else ""
    exclude = [str(item) for item in (params.get("exclude") or []) if isinstance(item, str)]

    facts = [item for item in _load_facts() if item.get("id") not in exclude]
    if not facts:
        return {
            "found": False,
            "topic": topic,
            "message": "没有可用的小知识条目（可能已全部排除或条目文件缺失）。",
            "hint": "不要编造冷知识；这一轮可以不插话。",
        }

    if not topic:
        picked = random.choice(facts)
        return _format(picked, topic, "random")

    tokens = _tokens(topic)
    scored = []
    for fact in facts:
        score = _score(fact, topic, tokens)
        if score > 0:
            scored.append((score, fact))

    if not scored:
        return {
            "found": False,
            "topic": topic,
            "message": "本地条目里没有与这个话题匹配的小知识。",
            "hint": "不要编造冷知识；这一轮可以不插话。",
        }

    best_score = max(score for score, _ in scored)
    picked = random.choice([fact for score, fact in scored if score == best_score])
    return _format(picked, topic, "matched")


def _format(fact, topic, relevance):
    return {
        "found": True,
        "id": fact.get("id"),
        "fact": fact.get("fact"),
        "source": fact.get("source") or "",
        "confidence": fact.get("confidence") or "unknown",
        "tags": list(fact.get("tags") or []),
        "topic": topic,
        "relevance": relevance,
    }


def register_blocks(api):
    """注册阶段 1 的方块集合。只注册当前能独立成立的能力。"""
    bind_api(api)
    api.register_tool({
        "name": "kirara.trivia",
        "label": "绮罗罗小知识",
        "description": (
            "从本地维护的冷知识条目中挑一条与当前话题相关的，附带出处与可信度；"
            "找不到匹配时明确返回未命中，要求模型不要编造。"
        ),
        "risk": "read",
        "usage": 'kirara.trivia PARAMS:{"topic": "话题元素", "exclude": ["已用过的id"]}',
        "params_schema": dict(_TRIVIA_PARAMS_SCHEMA),
        "backend": "kirara_blocks:trivia",
        "triggers": ["小知识", "冷知识", "科普", "嘴碎"],
        "category": "Kirara",
    })
