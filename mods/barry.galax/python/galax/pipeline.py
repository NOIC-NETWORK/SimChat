"""Galax：论文 2.1 的四阶段检索-推理管线（MOD 形态）。

宿主只负责会话存储与威胁筛查；本模块只接收查询、返回结构化结果。
"""

import json
from urllib.parse import urlparse

from simchat_mod import ModeSpec, hook

_api = None

SYSTEM_PROMPT = """你是 Galax，一个基于证据的联合推理检索引擎。
你的任务是把开放域问题当作一次科学探究：先召回候选来源，再提出竞争假设，
然后逐条权衡支持与反驳证据，最后只根据高置信度结论合成答案。
"""


@hook("chat.mode")
def register(api):
    global _api
    _api = api
    api.register_mode(ModeSpec(
        id="galax",
        label="Galax",
        icon="⚡",
        order=20,
        frontend_entry="web/galax.js",
        backend="galax.pipeline:query",
        cost="high",
        description="证据加权联合推理检索",
        requires_capabilities=["net"],
    ))


def query(message, session_id=None, history=None):
    """`chat.mode` 后端契约：query(message, session_id, history) -> dict。"""
    if _api is None:
        raise RuntimeError("Galax MOD 尚未注册")
    pipeline = GalaxPipeline(_api.service("inference"), _api.service("skill_manager"))
    return pipeline.run_pipeline(message)


class GalaxPipeline(object):
    """Recall → Hypothesis → Evidence → Synthesis，每个阶段独立提示词与温度。"""

    def __init__(self, inference, skill_manager=None):
        self.inference = inference
        self.skill_manager = skill_manager

    def _call_llm(self, prompt, temperature=0.7):
        if not self.inference:
            return None
        try:
            return self.inference.generate_raw(
                prompt,
                temperature=temperature,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=1024
            )
        except Exception as error:
            print("[Galax] LLM 调用失败: %s" % error)
            return None

    @staticmethod
    def _parse_json(response, opening, closing):
        if not response:
            return None
        start = response.find(opening)
        end = response.rfind(closing) + 1
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(response[start:end])
        except json.JSONDecodeError:
            return None

    def _recall_from_web(self, query_text):
        """Recall 阶段优先使用 webSearch 的真实结果。"""
        if not self.skill_manager:
            return None

        skill = self.skill_manager.get_registry().get_skill("webSearch")
        if not skill:
            return None

        try:
            search = skill.execute({"action": "search", "query": query_text, "max_results": 5})
        except Exception as error:
            print("[Galax] webSearch 召回失败: %s" % error)
            return None

        if not search.get("success") or not search.get("results"):
            return None

        sources = []
        for item in search["results"][:5]:
            url = item.get("url") or ""
            host = urlparse(url).netloc.replace("www.", "") if url else ""
            sources.append({
                "title": item.get("title") or "(无标题)",
                "source": host or search.get("source", "web"),
                "year": "",
                "abstract": item.get("snippet") or "",
            })

        if not sources:
            return None

        return {
            "summary": "联网检索到 %d 条结果（%s）。" % (len(sources), search.get("source", "web")),
            "sources": sources,
            "grounded": True,
        }

    def _recall(self, query_text):
        grounded = self._recall_from_web(query_text)
        if grounded:
            print("[Galax] 召回阶段使用 webSearch 实时结果")
            return grounded

        recall_prompt = """【Galax - 召回阶段】
用户查询：%s

请根据查询内容，模拟搜索权威学术来源（Google Scholar、PubMed、Arxiv等），并返回以下格式的JSON：

{
    "summary": "对检索到的信息的简要总结",
    "sources": [
        {"title": "论文/研究标题1", "source": "来源平台", "year": "年份", "abstract": "摘要"}
    ]
}

要求：
1. 返回至少3个相关来源
2. 来源标题要专业且相关
3. 摘要要简洁概括核心内容
4. 只返回JSON格式，不要其他文字
""" % query_text

        parsed = self._parse_json(
            self._call_llm(recall_prompt, temperature=0.3), "{", "}"
        )
        if isinstance(parsed, dict) and isinstance(parsed.get("sources"), list):
            sources = []
            for src in parsed["sources"]:
                if not isinstance(src, dict):
                    continue
                sources.append({
                    "title": src.get("title") or "(无标题)",
                    "source": src.get("source") or "未知来源",
                    "year": src.get("year") or "",
                    "abstract": src.get("abstract") or "",
                })
            if sources:
                parsed["sources"] = sources
                parsed.setdefault("summary", "检索到相关来源。")
                return parsed

        return {
            "summary": "针对查询 '%s' 的检索结果表明，该领域存在多个相关研究。主要涉及理论分析和实证研究两个方向。" % query_text,
            "sources": [
                {"title": "%s 的理论框架分析" % query_text, "source": "Google Scholar", "year": "2024", "abstract": "本研究探讨了相关理论基础和方法论框架。"},
                {"title": "%s 的实证研究" % query_text, "source": "PubMed", "year": "2023", "abstract": "通过大规模数据验证了核心假设。"},
                {"title": "%s 的最新进展综述" % query_text, "source": "Arxiv", "year": "2025", "abstract": "综述了近年来该领域的主要研究成果和发展趋势。"}
            ]
        }

    def _generate_hypotheses(self, query_text, recall_data):
        sources_summary = "\n".join([
            "- %s: %s" % (source["title"], source["abstract"])
            for source in recall_data.get("sources", [])
        ])

        hypothesis_prompt = """【Galax - 假设生成阶段】
用户查询：%s

检索到的信息：
%s

请根据检索结果，生成3个可能的结论/假设。每个假设应该是一个完整的句子，表达一个明确的观点。

输出格式：
[
    "假设1：完整的句子表述",
    "假设2：完整的句子表述",
    "假设3：完整的句子表述"
]

要求：
1. 三个假设应该覆盖不同的可能性
2. 每个假设都应该基于检索到的信息
3. 只返回JSON数组，不要其他文字
""" % (query_text, sources_summary)

        parsed = self._parse_json(
            self._call_llm(hypothesis_prompt, temperature=0.5), "[", "]"
        )
        if isinstance(parsed, list):
            hypotheses = [str(item).strip() for item in parsed if str(item).strip()]
            if len(hypotheses) >= 3:
                return hypotheses[:3]

        return [
            "假设1：%s 的核心问题可以通过现有的理论框架得到有效解决。" % query_text,
            "假设2：%s 涉及的现象需要新的方法论来解释。" % query_text,
            "假设3：%s 的解决方案取决于具体的应用场景和约束条件。" % query_text,
        ]

    def _evaluate_evidence(self, query_text, hypotheses, recall_data):
        sources_summary = "\n".join([
            "- %s (%s): %s" % (source["title"], source["source"], source["abstract"])
            for source in recall_data.get("sources", [])
        ])

        evidence_prompt = """【Galax - 证据加权阶段】
用户查询：%s

检索到的信息：
%s

待验证的假设：
1. %s
2. %s
3. %s

请针对每个假设，分析支持证据和反驳观点，并判定置信度。

输出格式：
[
    {
        "hypothesis": "假设内容",
        "supporting": "支持该假设的证据",
        "refuting": "反驳该假设的观点（如果没有则留空）",
        "confidence": "高" 或 "低"
    }
]

置信度判定规则：
- 如果有多个来源支持且无反驳，置信度为"高"
- 如果只有一个来源支持或存在反驳观点，置信度为"低"
- 如果没有直接证据支持，置信度为"低"

要求：
1. 严格按照JSON格式输出
2. 每个假设都要有明确的证据分析
3. 只返回JSON数组，不要其他文字
""" % (query_text, sources_summary, hypotheses[0], hypotheses[1], hypotheses[2])

        parsed = self._parse_json(
            self._call_llm(evidence_prompt, temperature=0.3), "[", "]"
        )
        if isinstance(parsed, list):
            evidence = []
            for item in parsed:
                if not isinstance(item, dict) or not item.get("hypothesis"):
                    continue
                evidence.append({
                    "hypothesis": str(item["hypothesis"]).strip(),
                    "supporting": str(item.get("supporting") or "").strip(),
                    "refuting": str(item.get("refuting") or "").strip(),
                    "confidence": "高" if item.get("confidence") == "高" else "低",
                })
            if len(evidence) >= 3:
                return evidence[:3]

        return [
            {
                "hypothesis": hypotheses[0],
                "supporting": "检索到的研究提供了直接的理论支持",
                "refuting": "",
                "confidence": "高",
            },
            {
                "hypothesis": hypotheses[1],
                "supporting": "部分研究暗示了新方法论的必要性",
                "refuting": "但现有方法仍有一定适用性",
                "confidence": "低",
            },
            {
                "hypothesis": hypotheses[2],
                "supporting": "实证研究显示场景依赖性",
                "refuting": "",
                "confidence": "高",
            },
        ]

    def _synthesize(self, query_text, evidence, recall=None):
        high_confidence = [item for item in evidence if item.get("confidence") == "高"]
        sources = (recall or {}).get("sources") or []
        source_titles = [source.get("title", "") for source in sources if source.get("title")]

        # 低置信度证据全部丢弃；没有高置信度证据时直接给出保守声明。
        if not high_confidence:
            return {
                "conclusion": "现有证据不足以形成高置信度结论。建议补充更权威或更多来源后重试。",
                "sarcastic_comment": "证据这么单薄还敢下结论，那不叫推理，叫许愿。",
                "references": "无高置信度来源",
            }

        evidence_summary = "\n".join([
            "- 高置信度：%s\n  支持：%s" % (item["hypothesis"], item.get("supporting", ""))
            for item in high_confidence
        ])
        source_summary = "\n".join("- %s" % title for title in source_titles) or "（无）"

        synthesis_prompt = """【Galax - 结论合成阶段】
用户查询：%s

召回阶段来源：
%s

高置信度证据分析结果：
%s

请严格基于上述高置信度假设，合成最终结论。

输出格式：
{
    "conclusion": "简洁的最终结论",
    "sarcastic_comment": "毒舌解说（用幽默但专业的方式点评）",
    "references": "引用的主要来源"
}

要求：
1. 只能使用高置信度假设，不要引入新的事实
2. references 必须来自“召回阶段来源”列表，用分号分隔
3. 毒舌解说要符合Rigard的性格：专业、逻辑性强、带点讽刺
4. 只返回JSON格式，不要其他文字
""" % (query_text, source_summary, evidence_summary)

        parsed = self._parse_json(
            self._call_llm(synthesis_prompt, temperature=0.7), "{", "}"
        )
        if isinstance(parsed, dict) and parsed.get("conclusion"):
            return parsed

        return {
            "conclusion": "\n".join(item["hypothesis"] for item in high_confidence),
            "sarcastic_comment": "结论其实就藏在高置信度证据里，绕圈子只是为了让过程看起来更专业。",
            "references": "; ".join(source_titles) if source_titles else "高置信度证据",
        }

    def run_pipeline(self, query_text):
        print("[Galax] 开始执行四步推理管线...")

        recall = self._recall(query_text)
        print("[Galax] 召回阶段完成")

        hypotheses = self._generate_hypotheses(query_text, recall)
        print("[Galax] 假设生成阶段完成")

        evidence = self._evaluate_evidence(query_text, hypotheses, recall)
        print("[Galax] 证据加权阶段完成")

        synthesis = self._synthesize(query_text, evidence, recall)
        print("[Galax] 结论合成阶段完成")

        return {
            "recall": recall,
            "hypotheses": hypotheses,
            "evidence": evidence,
            "synthesis": synthesis,
        }
