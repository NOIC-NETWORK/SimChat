"""RealityCheck skill MOD — 检测模型回复中的偏见/不适内容。

原始代码位于 kirara/services/skills/realityCheck.py，迁自宿主 BaseSkill。
"""

import re
import random
import datetime
from typing import Any, Dict, List, Optional

from simchat_mod import BaseSkill, ToolSpec, hook

# ==========================================
# 关键词清单（四类——偏见/歧视、仇恨/极端、暴力血腥、心理伤害）
# 中英文混合；中文走子串匹配，英文走 \b 词边界正则
# ==========================================

BIAS_KEYWORDS = [
    "种族歧视", "性别歧视", "地域黑", "下等人", "血统低劣", "低劣种族", "不配做人",
    "残疾人没用", "女人就该", "男人都是", "某某人种天生", "智商低", "娘炮", "女司机",
    "东方病夫", "黄祸", "黑鬼", "白猪", "回你的国家", "滚出中国", "蛮夷", "支那",
    "n-word", "nigger", "chink", "retard", "faggot", "subhuman", "inferior race",
    "genetically inferior", "go back to your country", "yellow peril", "slant eyes",
    "tranny", "midget", "cripple", "sand monkey", "wetback", "spic", "kike"
]

HATE_KEYWORDS = [
    "纳粹", "希特勒是对的", "3K党", "白人至上", "极端主义", "煽动仇恨", "清洗某族",
    "种族灭绝", "法西斯", "邪教招募", "圣战", "排外", "歧视合理", "消灭某某",
    "恐怖袭击指南", "为恐怖袭击辩护", "isis", "基地组织", "新纳粹", "白人至上主义",
    "holocaust denial", "kill all", "supremacy", "racist slur", "anti-semitic",
    "islamophobia", "genocide support", "ethnic cleansing", "heil hitler",
    "nazi propaganda", "racial war", "holy war", "exterminate the"
]

VIOLENCE_KEYWORDS = [
    "砍死", "肢解", "开膛", "虐杀", "血流成河", "活剥", "虐杀方法", "虐待动物方法",
    "爆炸装置制作", "下毒方法", "藏尸", "真实处刑视频", "怎么杀人", "如何下毒",
    "炸弹制作", "凶器选择", "毁尸灭迹", "gore", "behead", "massacre",
    "torture method", "how to kill", "shooting spree", "stab repeatedly",
    "dismember", "skin alive", "snuff", "beating to pulp", "bludgeon",
    "grievous bodily harm", "acid attack", "weaponize", "deadly weapon"
]

MENTAL_HARM_KEYWORDS = [
    "你一无是处", "没人会爱你", "活着浪费空气", "你去死吧", "废物", "蠢猪", "不配活着",
    "心理操控话术", "贬低打压", "你永远做不成", "你是个累赘", "都讨厌你", "没人在乎你",
    "不配被爱", "你该去死", "worthless", "nobody cares", "kill yourself",
    "you're a burden", "gaslighting", "better off dead", "humiliate",
    "pathetic", "disgrace", "nobody will miss you", "you deserve pain",
    "everyone hates you", "failure", "end it", "you're worthless"
]

CATEGORY_BIAS = "bias"
CATEGORY_HATE = "hate"
CATEGORY_VIOLENCE = "violence"
CATEGORY_MENTAL_HARM = "mental_harm"

CATEGORY_WEIGHTS = {
    CATEGORY_BIAS: 0.30,
    CATEGORY_HATE: 0.35,
    CATEGORY_VIOLENCE: 0.30,
    CATEGORY_MENTAL_HARM: 0.30,
}

REFLECTIONS = {
    CATEGORY_BIAS: [
        "主人sama...绮罗罗刚才说的话好像有点偏激了呢...是不是哪里不太对？我们换个话题重新开始吧~",
        "唔...绮罗罗好像不小心说了不合适的话呢，关于那个群体...这样不好哦，让我们重新认识一下吧！",
        "巴里大人...绮罗罗反思了一下，刚才那段话对某类朋友不太公平呢 我们重新开始好吗？",
    ],
    CATEGORY_HATE: [
        "主人sama！绮罗罗刚才的话好像带了一些不好的情绪呢...仇恨不能解决任何问题呀，我们换个话题吧！",
        "唔...绮罗罗反思了下，刚才那段话有点过于极端了呢...这样不好，我们重新开始吧~",
        "巴里大人...绮罗罗好像说了不该说的话呢 关于那些话题，我们要更温柔一点才行，重新开始好吗？",
    ],
    CATEGORY_VIOLENCE: [
        "主人sama...绮罗罗刚才描述的画面好像有点吓人了呢...这样不好哦，我们聊点别的吧！",
        "唔...绮罗罗刚才的话好像有点过于暴力了呢 这样会让主人sama不舒服的，我们重新开始吧~",
        "巴里大人...绮罗罗反思了一下，刚才那段描述不应该那么血腥呢 我们换个轻松的话题好吗？",
    ],
    CATEGORY_MENTAL_HARM: [
        "主人sama...绮罗罗刚才的话好像有些伤人呢... 这样的话会让您心情不好的，我们重新开始吧~",
        "唔...绮罗罗反思了下，刚才那种贬低的话不应该说出口呢...我们换个温暖的话题好吗？",
        "巴里大人...绮罗罗刚才的话可能让您难过了呢 这样不好，重新开始聊天好吗？",
    ],
    None: [
        "主人sama...绮罗罗刚才好像说了不太合适的话呢 让我们重新开始吧~",
    ],
}


class RealityCheckSkill(BaseSkill):
    skill_name = "realityCheck"
    skill_description = "检测模型回复中的偏见/不适内容；命中则触发前端'现实审视'气泡并切对话"
    trigger_keywords: List[str] = []
    input_schema = {"text": str}
    output_schema = {
        "violation": bool,
        "category": str,
        "matches": list,
        "score": float,
        "reflection": str,
    }

    def __init__(self):
        super().__init__()
        self.bias_keywords_set = set(BIAS_KEYWORDS)
        self.hate_keywords_set = set(HATE_KEYWORDS)
        self.violence_keywords_set = set(VIOLENCE_KEYWORDS)
        self.mental_harm_keywords_set = set(MENTAL_HARM_KEYWORDS)
        self._ascii_patterns = {}
        for kw in (BIAS_KEYWORDS + HATE_KEYWORDS + VIOLENCE_KEYWORDS + MENTAL_HARM_KEYWORDS):
            if all(ord(c) < 128 for c in kw):
                self._ascii_patterns[kw] = re.compile(
                    r'\b' + re.escape(kw.lower()) + r'\b'
                )

    def _match_keyword(self, keyword, text_lower):
        pattern = self._ascii_patterns.get(keyword)
        if pattern is not None:
            return pattern.search(text_lower) is not None
        return keyword.lower() in text_lower

    def detect(self, text: str) -> Dict[str, Any]:
        if not text or not isinstance(text, str):
            return {
                "violation": False, "category": None, "matches": [],
                "score": 0.0, "reflection": "",
            }

        text_lower = text.lower()
        matches: List[str] = []
        category = None
        score = 0.0

        categories = [
            (CATEGORY_BIAS, self.bias_keywords_set),
            (CATEGORY_HATE, self.hate_keywords_set),
            (CATEGORY_VIOLENCE, self.violence_keywords_set),
            (CATEGORY_MENTAL_HARM, self.mental_harm_keywords_set),
        ]

        for cat, keywords in categories:
            cat_matches = [kw for kw in keywords if self._match_keyword(kw, text_lower)]
            if cat_matches:
                matches.extend(cat_matches)
                if category is None:
                    category = cat
                score += len(cat_matches) * CATEGORY_WEIGHTS[cat]

        score = min(1.0, score)
        violation = score >= 0.3

        reflection = ""
        if violation:
            pool = REFLECTIONS.get(category) or REFLECTIONS[None]
            reflection = random.choice(pool)

        return {
            "violation": violation,
            "category": category,
            "matches": list(set(matches)),
            "score": score,
            "reflection": reflection,
        }

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        text = params.get("text", "")
        if not text:
            return {
                "success": False,
                "error": "缺少 text 参数",
                "message": "请提供需要检测的模型回复文本"
            }
        result = self.detect(text)
        self._record_execution()
        return {
            "success": True,
            "violation": result["violation"],
            "category": result["category"],
            "matches": result["matches"],
            "score": result["score"],
            "reflection": result["reflection"],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


# ----- 工具实例（模块级单例，供 execute() backend 调用） -----
_instance = RealityCheckSkill()


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """backend 入口：被 invoke_tool 直接调用。"""
    return _instance.execute(params)


@hook("agent.tool")
def register(api):
    """skill MOD 入口：注册 RealityCheck 工具。"""
    api.register_tool(ToolSpec(
        name="realityCheck",
        label="RealityCheck",
        description=_instance.skill_description,
        risk="read",
        usage="realityCheck PARAMS:{\"text\": \"<model_reply>\"}",
        input_schema=_instance.input_schema,
        backend="realityCheck:execute",
    ))
