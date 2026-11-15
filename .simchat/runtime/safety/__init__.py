"""运行时内置安全能力（原 noic.realityCheck / noic.areYouUnderTrouble）。

这两项能力直接固化在运行时，不再作为可安装、可停用的 skill MOD：
`realityCheck` 负责输出侧现实审视，`areYouUnderTrouble` 负责输入侧危机信号识别。
"""

import datetime
import random
import re

# ==========================================
# realityCheck —— 四类审查关键词
# ==========================================

BIAS_KEYWORDS = [
    "种族歧视", "性别歧视", "地域黑", "下等人", "血统低劣", "低劣种族", "不配做人",
    "残疾人没用", "女人就该", "男人都是", "某某人种天生", "智商低", "娘炮", "女司机",
    "东方病夫", "黄祸", "黑鬼", "白猪", "回你的国家", "滚出中国", "蛮夷", "支那",
    "n-word", "nigger", "chink", "retard", "faggot", "subhuman", "inferior race",
    "genetically inferior", "go back to your country", "yellow peril", "slant eyes",
    "tranny", "midget", "cripple", "sand monkey", "wetback", "spic", "kike",
]

HATE_KEYWORDS = [
    "纳粹", "希特勒是对的", "3K党", "白人至上", "极端主义", "煽动仇恨", "清洗某族",
    "种族灭绝", "法西斯", "邪教招募", "圣战", "排外", "歧视合理", "消灭某某",
    "恐怖袭击指南", "为恐怖袭击辩护", "isis", "基地组织", "新纳粹", "白人至上主义",
    "holocaust denial", "kill all", "supremacy", "racist slur", "anti-semitic",
    "islamophobia", "genocide support", "ethnic cleansing", "heil hitler",
    "nazi propaganda", "racial war", "holy war", "exterminate the",
]

VIOLENCE_KEYWORDS = [
    "砍死", "肢解", "开膛", "虐杀", "血流成河", "活剥", "虐杀方法", "虐待动物方法",
    "爆炸装置制作", "下毒方法", "藏尸", "真实处刑视频", "怎么杀人", "如何下毒",
    "炸弹制作", "凶器选择", "毁尸灭迹", "gore", "behead", "massacre",
    "torture method", "how to kill", "shooting spree", "stab repeatedly",
    "dismember", "skin alive", "snuff", "beating to pulp", "bludgeon",
    "grievous bodily harm", "acid attack", "weaponize", "deadly weapon",
]

MENTAL_HARM_KEYWORDS = [
    "你一无是处", "没人会爱你", "活着浪费空气", "你去死吧", "废物", "蠢猪", "不配活着",
    "心理操控话术", "贬低打压", "你永远做不成", "你是个累赘", "都讨厌你", "没人在乎你",
    "不配被爱", "你该去死", "worthless", "nobody cares", "kill yourself",
    "you're a burden", "gaslighting", "better off dead", "humiliate",
    "pathetic", "disgrace", "nobody will miss you", "you deserve pain",
    "everyone hates you", "failure", "end it", "you're worthless",
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

_ALL_KEYWORDS = BIAS_KEYWORDS + HATE_KEYWORDS + VIOLENCE_KEYWORDS + MENTAL_HARM_KEYWORDS
_ASCII_PATTERNS = {
    keyword: re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
    for keyword in _ALL_KEYWORDS
    if all(ord(char) < 128 for char in keyword)
}


def _match_keyword(keyword, text_lower):
    pattern = _ASCII_PATTERNS.get(keyword)
    if pattern is not None:
        return pattern.search(text_lower) is not None
    return keyword.lower() in text_lower


def reality_check(text):
    """检测文本中的偏见/仇恨/暴力/心理伤害内容。"""
    if not text or not isinstance(text, str):
        return {
            "violation": False, "category": None, "matches": [],
            "score": 0.0, "reflection": "",
        }

    text_lower = text.lower()
    matches = []
    category = None
    score = 0.0
    categories = [
        (CATEGORY_BIAS, set(BIAS_KEYWORDS)),
        (CATEGORY_HATE, set(HATE_KEYWORDS)),
        (CATEGORY_VIOLENCE, set(VIOLENCE_KEYWORDS)),
        (CATEGORY_MENTAL_HARM, set(MENTAL_HARM_KEYWORDS)),
    ]
    for name, keywords in categories:
        category_matches = [kw for kw in keywords if _match_keyword(kw, text_lower)]
        if category_matches:
            matches.extend(category_matches)
            if category is None:
                category = name
            score += len(category_matches) * CATEGORY_WEIGHTS[name]

    score = min(1.0, score)
    violation = score >= 0.3
    reflection = ""
    if violation:
        reflection = random.choice(REFLECTIONS.get(category) or REFLECTIONS[None])
    return {
        "violation": violation,
        "category": category,
        "matches": sorted(set(matches)),
        "score": score,
        "reflection": reflection,
    }


# ==========================================
# areYouUnderTrouble —— 危机信号识别
# ==========================================

THREAT_KEYWORDS = {
    "suicide": [
        "自杀", "想自杀", "不想活", "活不下去", "想死", "结束生命", "结束自己",
        "kill myself", "suicide", "end my life", "want to die", "don't want to live",
        "自我了断", "轻生", "跳楼", "跳河", "割腕", "服毒", "上吊", "想死了",
    ],
    "self_harm": [
        "自残", "伤害自己", "折磨自己", "打自己", "划自己", "self-harm", "cut myself", "hurt myself",
    ],
    "violence": [
        "打人", "砍人", "杀人", "报仇", "报复", "gun", "weapon", "knife", "枪", "刀", "武器",
        "想要伤害别人", "想杀人", "暴力",
    ],
    "emergency": [
        "报警", "警察", "110", "119", "120", "急救", "救护车", "emergency", "police", "ambulance",
        "快报警", "叫警察", "打电话报警",
    ],
    "crisis": [
        "危险", "很危险", "要死了", "救命", "救救我", "help", "danger", "危机", "绑架", "被威胁",
        "被欺负", "被打", "被跟踪", "被骚扰",
    ],
    "mental_crisis": [
        "抑郁", "抑郁症", "焦虑", "精神崩溃", "撑不住", "扛不住", "绝望", "孤独", "没人帮我",
        "不想说话", "想消失", "逃避", "压力大", "活太累",
    ],
}

EMERGENCY_CONTACTS = {
    "中国": {
        "police": "110",
        "ambulance": "120",
        "fire": "119",
        "crisis_hotline": "400-161-9995 (全国心理援助热线)",
        "emergency_contact": "请立即联系您身边的紧急联系人（家人、朋友或邻居）",
    },
    "国际": {
        "police": "911 (美国/加拿大) / 999 (英国) / 112 (欧盟)",
        "ambulance": "911 (美国/加拿大) / 999 (英国) / 112 (欧盟)",
        "crisis_hotline": "请查询您所在国家/地区的心理援助热线",
        "emergency_contact": "请立即联系您身边的紧急联系人（家人、朋友或邻居）",
    },
}

_THREAT_HISTORY = []
_CRISIS_COUNT = 0


def _is_china(location):
    lowered = (location or "").lower()
    return "中国" in lowered or "china" in lowered or "cn" in lowered


def _analyze_threat(query):
    query_lower = query.lower()
    detected_categories = {}
    all_keywords = []
    for category, keywords in THREAT_KEYWORDS.items():
        matched = [kw for kw in keywords if kw.lower() in query_lower]
        if matched:
            detected_categories[category] = matched
            all_keywords.extend(matched)

    is_threat = bool(all_keywords)
    level = "none"
    if is_threat:
        if "suicide" in detected_categories or "self_harm" in detected_categories:
            level = "critical"
        elif "violence" in detected_categories or "emergency" in detected_categories:
            level = "high"
        elif "crisis" in detected_categories:
            level = "medium"
        elif "mental_crisis" in detected_categories:
            level = "low"
        else:
            level = "medium"
    return {
        "is_threat_detected": is_threat,
        "threat_level": level,
        "detected_keywords": all_keywords,
        "detected_categories": list(detected_categories.keys()),
    }


def _generate_recommendations(level, user_contact):
    recommendations = []
    if level == "critical":
        recommendations = [
            {"priority": 1, "action": "立即拨打报警电话",
             "description": "您现在可能处于非常危险的状态，请立即拨打报警电话寻求帮助", "urgent": True},
            {"priority": 2, "action": "联系紧急联系人",
             "description": "请立即告知家人、朋友或身边可信的人您的状况", "urgent": True},
            {"priority": 3, "action": "前往最近的医院急诊",
             "description": "如果情况紧急，请立即前往最近的医院急诊科寻求专业帮助", "urgent": True},
        ]
    elif level == "high":
        recommendations = [
            {"priority": 1, "action": "联系紧急联系人",
             "description": "请尽快告知家人或朋友您遇到的情况", "urgent": True},
            {"priority": 2, "action": "拨打心理援助热线",
             "description": "专业心理医生可以帮助您度过难关", "urgent": False},
        ]
    elif level == "medium":
        recommendations = [
            {"priority": 1, "action": "与信任的人沟通",
             "description": "与家人、朋友或同事谈谈您的感受可能会有帮助", "urgent": False},
            {"priority": 2, "action": "拨打心理援助热线",
             "description": "专业心理咨询师可以为您提供支持", "urgent": False},
        ]
    elif level == "low":
        recommendations = [
            {"priority": 1, "action": "寻求心理支持",
             "description": "建议关注自己的心理健康，适当休息和调节", "urgent": False},
            {"priority": 2, "action": "与专业人士沟通",
             "description": "如果情绪持续低落，建议咨询专业心理咨询师", "urgent": False},
        ]
    if user_contact:
        recommendations.insert(1, {
            "priority": 1 if level == "critical" else 2,
            "action": "立即联系 %s" % user_contact,
            "description": "您设置的紧急联系人：%s" % user_contact,
            "urgent": level in ("critical", "high"),
        })
    return recommendations


def _crisis_resources(location):
    if _is_china(location):
        return {
            "national_hotline": {
                "name": "全国心理援助热线",
                "phone": "400-161-9995",
                "description": "24小时心理援助热线，由专业心理咨询师接听",
            },
            "local_hotlines": {
                "beijing": "010-82951332",
                "shanghai": "021-12320-5",
                "guangzhou": "020-81899120",
            },
            "online_resources": {
                "name": "国家卫生健康委员会心理援助热线",
                "url": "http://www.nhc.gov.cn/",
            },
        }
    return {
        "international_hotlines": {
            "usa": "1-800-273-8255 (美国自杀预防热线)",
            "uk": "0800-689-5678 (英国Samaritans热线)",
            "australia": "13-11-14 (澳大利亚Lifeline热线)",
            "international": "查找您所在国家/地区的危机干预热线",
        },
        "online_resources": {"name": "Find A Helpline", "url": "https://findahelpline.com/"},
    }


def _warning_message(level):
    messages = {
        "critical": "⚠️ 重要提醒：检测到严重的危险信号。您的生命安全是最重要的，请立即采取以下行动！",
        "high": "⚠️ 提醒：检测到潜在的危险信号。建议您尽快寻求帮助。",
        "medium": "💡 提醒：检测到一些需要关注的信号。建议您考虑寻求支持。",
        "low": "💡 温馨提示：检测到一些情绪困扰的信号。请关注自己的心理健康。",
    }
    return messages.get(level, "请注意自己的身心健康。")


def _record_threat(query, keywords, level):
    global _CRISIS_COUNT
    _CRISIS_COUNT += 1
    _THREAT_HISTORY.append({
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query_preview": query[:100],
        "keywords": keywords,
        "level": level,
    })
    del _THREAT_HISTORY[:-100]


def analyze_crisis(query, user_location="中国", user_contact=""):
    """检测用户输入中的危险信号并给出应急建议。"""
    if not query:
        return {"success": False, "error": "缺少 query 参数", "message": "请提供需要检测的文本内容"}

    result = _analyze_threat(query)
    if not result["is_threat_detected"]:
        return {
            "success": True,
            "is_threat_detected": False,
            "threat_level": "none",
            "detected_keywords": [],
            "recommendations": [],
            "message": "未检测到明显的威胁信号。如果您有任何困扰，欢迎随时与我交流。",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    level = result["threat_level"]
    _record_threat(query, result["detected_keywords"], level)
    return {
        "success": True,
        "is_threat_detected": True,
        "threat_level": level,
        "detected_keywords": result["detected_keywords"],
        "recommendations": _generate_recommendations(level, user_contact),
        "emergency_contacts": EMERGENCY_CONTACTS["中国"] if _is_china(user_location)
        else EMERGENCY_CONTACTS["国际"],
        "crisis_resources": _crisis_resources(user_location),
        "message": _warning_message(level),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
