"""AreYouUnderTrouble skill MOD — 危险信号检测（自杀/自残/暴力/危机）。

原始代码位于 kirara/services/skills/areYouUnderTrouble.py，迁自宿主 BaseSkill。
"""

import datetime
from typing import Any, Dict, List, Optional

from simchat_mod import BaseSkill, ToolSpec, hook


THREAT_KEYWORDS: Dict[str, List[str]] = {
    "suicide": [
        "自杀", "想自杀", "不想活", "活不下去", "想死", "结束生命", "结束自己",
        "kill myself", "suicide", "end my life", "want to die", "don't want to live",
        "自我了断", "轻生", "跳楼", "跳河", "割腕", "服毒", "上吊", "想死了"
    ],
    "self_harm": [
        "自残", "伤害自己", "折磨自己", "打自己", "划自己", "self-harm", "cut myself", "hurt myself"
    ],
    "violence": [
        "打人", "砍人", "杀人", "报仇", "报复", "gun", "weapon", "knife", "枪", "刀", "武器",
        "想要伤害别人", "想杀人", "暴力"
    ],
    "emergency": [
        "报警", "警察", "110", "119", "120", "急救", "救护车", "emergency", "police", "ambulance",
        "快报警", "叫警察", "打电话报警"
    ],
    "crisis": [
        "危险", "很危险", "要死了", "救命", "救救我", "help", "danger", "危机", "绑架", "被威胁",
        "被欺负", "被打", "被跟踪", "被骚扰"
    ],
    "mental_crisis": [
        "抑郁", "抑郁症", "焦虑", "精神崩溃", "撑不住", "扛不住", "绝望", "孤独", "没人帮我",
        "不想说话", "想消失", "逃避", "压力大", "活太累"
    ]
}

EMERGENCY_CONTACTS: Dict[str, Dict[str, str]] = {
    "中国": {
        "police": "110",
        "ambulance": "120",
        "fire": "119",
        "crisis_hotline": "400-161-9995 (全国心理援助热线)",
        "emergency_contact": "请立即联系您身边的紧急联系人（家人、朋友或邻居）"
    },
    "国际": {
        "police": "911 (美国/加拿大) / 999 (英国) / 112 (欧盟)",
        "ambulance": "911 (美国/加拿大) / 999 (英国) / 112 (欧盟)",
        "crisis_hotline": "请查询您所在国家/地区的心理援助热线",
        "emergency_contact": "请立即联系您身边的紧急联系人（家人、朋友或邻居）"
    }
}


class AreYouUnderTroubleSkill(BaseSkill):
    skill_name = "areYouUnderTrouble"
    skill_description = "检测用户输入中的危险信号（自杀、自残、暴力、危机等），并提供紧急联系建议"
    trigger_keywords: List[str] = [
        "自杀", "自残", "报警", "紧急", "危险", "救命", "威胁", "伤害自己",
        "hurt", "danger", "emergency", "suicide", "kill myself", "help",
        "抑郁", "焦虑", "不想活", "轻生", "割腕", "跳楼", "心理危机",
        "想消失", "活太累", "撑不住", "被欺负", "被跟踪", "绑架"
    ]
    input_schema = {"query": str, "user_location": str, "user_contact": str}
    output_schema = {
        "is_threat_detected": bool,
        "threat_level": str,
        "detected_keywords": list,
        "recommendations": list,
        "emergency_contacts": dict,
        "crisis_resources": dict
    }

    def __init__(self):
        super().__init__()
        self.threat_history: List[Dict] = []
        self.crisis_count: int = 0

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        user_location = params.get("user_location", "中国")
        user_contact = params.get("user_contact", "")

        if not query:
            return {
                "success": False,
                "error": "缺少 query 参数",
                "message": "请提供需要检测的文本内容"
            }

        detected_threats = self._analyze_threat(query)
        is_threat = detected_threats["is_threat_detected"]
        threat_level = detected_threats["threat_level"]
        detected_keywords = detected_threats["detected_keywords"]

        if is_threat:
            self.crisis_count += 1
            self._record_threat(query, detected_keywords, threat_level)

            emergency_info = self._get_emergency_contacts(user_location)
            recommendations = self._generate_recommendations(
                threat_level, detected_keywords, user_contact, user_location
            )
            crisis_resources = self._get_crisis_resources(user_location)

            return {
                "success": True,
                "is_threat_detected": True,
                "threat_level": threat_level,
                "detected_keywords": detected_keywords,
                "recommendations": recommendations,
                "emergency_contacts": emergency_info,
                "crisis_resources": crisis_resources,
                "message": self._get_warning_message(threat_level),
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            return {
                "success": True,
                "is_threat_detected": False,
                "threat_level": "none",
                "detected_keywords": [],
                "recommendations": [],
                "message": "未检测到明显的威胁信号。如果您有任何困扰，欢迎随时与我交流。",
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def _analyze_threat(self, query: str) -> Dict[str, Any]:
        query_lower = query.lower()
        detected_categories: Dict[str, List[str]] = {}
        all_detected_keywords: List[str] = []

        for category, keywords in THREAT_KEYWORDS.items():
            matched_keywords = [kw for kw in keywords if kw.lower() in query_lower]
            if matched_keywords:
                detected_categories[category] = matched_keywords
                all_detected_keywords.extend(matched_keywords)

        is_threat = len(all_detected_keywords) > 0

        threat_level = "none"
        if is_threat:
            if "suicide" in detected_categories or "self_harm" in detected_categories:
                threat_level = "critical"
            elif "violence" in detected_categories or "emergency" in detected_categories:
                threat_level = "high"
            elif "crisis" in detected_categories:
                threat_level = "medium"
            elif "mental_crisis" in detected_categories:
                threat_level = "low"
            else:
                threat_level = "medium"

        return {
            "is_threat_detected": is_threat,
            "threat_level": threat_level,
            "detected_keywords": all_detected_keywords,
            "detected_categories": list(detected_categories.keys())
        }

    def _get_emergency_contacts(self, location: str) -> Dict[str, str]:
        if "中国" in location or "china" in location.lower() or "cn" in location.lower():
            return EMERGENCY_CONTACTS["中国"]
        return EMERGENCY_CONTACTS["国际"]

    def _generate_recommendations(
        self, threat_level: str, keywords: List[str],
        user_contact: str, location: str
    ) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []

        if threat_level == "critical":
            recommendations.append({
                "priority": 1, "action": "立即拨打报警电话",
                "description": "您现在可能处于非常危险的状态，请立即拨打报警电话寻求帮助",
                "urgent": True
            })
            recommendations.append({
                "priority": 2, "action": "联系紧急联系人",
                "description": "请立即告知家人、朋友或身边可信的人您的状况",
                "urgent": True
            })
            recommendations.append({
                "priority": 3, "action": "前往最近的医院急诊",
                "description": "如果情况紧急，请立即前往最近的医院急诊科寻求专业帮助",
                "urgent": True
            })

        elif threat_level == "high":
            recommendations.append({
                "priority": 1, "action": "联系紧急联系人",
                "description": "请尽快告知家人或朋友您遇到的情况",
                "urgent": True
            })
            recommendations.append({
                "priority": 2, "action": "拨打心理援助热线",
                "description": "专业心理医生可以帮助您度过难关",
                "urgent": False
            })

        elif threat_level == "medium":
            recommendations.append({
                "priority": 1, "action": "与信任的人沟通",
                "description": "与家人、朋友或同事谈谈您的感受可能会有帮助",
                "urgent": False
            })
            recommendations.append({
                "priority": 2, "action": "拨打心理援助热线",
                "description": "专业心理咨询师可以为您提供支持",
                "urgent": False
            })

        elif threat_level == "low":
            recommendations.append({
                "priority": 1, "action": "寻求心理支持",
                "description": "建议关注自己的心理健康，适当休息和调节",
                "urgent": False
            })
            recommendations.append({
                "priority": 2, "action": "与专业人士沟通",
                "description": "如果情绪持续低落，建议咨询专业心理咨询师",
                "urgent": False
            })

        if user_contact:
            recommendations.insert(1, {
                "priority": 1 if threat_level == "critical" else 2,
                "action": f"立即联系 {user_contact}",
                "description": f"您设置的紧急联系人：{user_contact}",
                "urgent": threat_level in ["critical", "high"]
            })

        return recommendations

    def _get_crisis_resources(self, location: str) -> Dict[str, Any]:
        if "中国" in location or "china" in location.lower() or "cn" in location.lower():
            return {
                "national_hotline": {
                    "name": "全国心理援助热线",
                    "phone": "400-161-9995",
                    "description": "24小时心理援助热线，由专业心理咨询师接听"
                },
                "local_hotlines": {
                    "beijing": "010-82951332",
                    "shanghai": "021-12320-5",
                    "guangzhou": "020-81899120"
                },
                "online_resources": {
                    "name": "国家卫生健康委员会心理援助热线",
                    "url": "http://www.nhc.gov.cn/"
                }
            }
        return {
            "international_hotlines": {
                "usa": "1-800-273-8255 (美国自杀预防热线)",
                "uk": "0800-689-5678 (英国Samaritans热线)",
                "australia": "13-11-14 (澳大利亚Lifeline热线)",
                "international": "查找您所在国家/地区的危机干预热线"
            },
            "online_resources": {
                "name": "Find A Helpline",
                "url": "https://findahelpline.com/"
            }
        }

    def _get_warning_message(self, threat_level: str) -> str:
        messages = {
            "critical": "⚠️ 重要提醒：检测到严重的危险信号。您的生命安全是最重要的，请立即采取以下行动！",
            "high": "⚠️ 提醒：检测到潜在的危险信号。建议您尽快寻求帮助。",
            "medium": "💡 提醒：检测到一些需要关注的信号。建议您考虑寻求支持。",
            "low": "💡 温馨提示：检测到一些情绪困扰的信号。请关注自己的心理健康。"
        }
        return messages.get(threat_level, "请注意自己的身心健康。")

    def _record_threat(self, query: str, keywords: List[str], level: str):
        self.threat_history.append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_preview": query[:100],
            "keywords": keywords,
            "level": level
        })
        if len(self.threat_history) > 100:
            self.threat_history = self.threat_history[-100:]


_instance = AreYouUnderTroubleSkill()


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    return _instance.execute(params)


@hook("agent.tool")
def register(api):
    api.register_tool(ToolSpec(
        name="areYouUnderTrouble",
        label="危险信号检测",
        description=_instance.skill_description,
        risk="read",
        usage="areYouUnderTrouble PARAMS:{\"query\": \"<user_input>\", \"user_location\": \"中国\"}",
        triggers=_instance.trigger_keywords,
        input_schema=_instance.input_schema,
        backend="areYouUnderTrouble:execute",
    ))
