# -*- coding: utf-8 -*-
"""SimChat Agent 后端适配器。

把 AgentLoop 对 Kirara/JRVS 内核的依赖收敛到 SimChatCore：
- build_prompt：用户消息 + 历史 → 单条文本提示
- generate：非流式文本生成（复用 SimChatCore 的服务商解析）
- save_memory：任务与最终答复落到 SessionStore
- available() / unavailable_message()：模型门禁（fail-closed）

AgentLoop 不再直接 import 宿主实现，也不再触碰 Hippo / mem.txt。
"""

from ..core import ProviderError


class SimChatAgentBackend:
    """AgentLoop 唯一依赖的后端接口实现。"""

    # SimChat 本体暂无独立安全分类器；保持为 None，loop 会跳过安全检查。
    safety_system = None

    def __init__(self, core, provider=None, model=None,
                 temperature=0.7, max_tokens=1024):
        self.core = core
        self.provider = provider or None
        self.model = model or None
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._available = None

    # ---------------- 门禁 ----------------

    def available(self):
        if self._available is None:
            self._available = bool(self.core.has_available_provider())
        return self._available

    def unavailable_message(self):
        return "尚未配置可用的服务商，请先在设置中完成服务商配置。"

    def snapshot(self):
        """挂起态里保存的模型选择，审批恢复时原样重建。"""
        return {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    # ---------------- 上下文与推理 ----------------

    def build_prompt(self, message, history=None, session_id=None):
        lines = []
        for item in (history or [])[-20:]:
            if not isinstance(item, dict):
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            role = item.get("role")
            tag = "用户" if role == "user" else ("助手" if role == "assistant" else "系统")
            lines.append(f"{tag}: {content}")
        prefix = ("【此前对话】\n" + "\n".join(lines) + "\n\n") if lines else ""
        return prefix + f"【用户最新消息】{message}"

    def generate(self, prompt, system_msg=None):
        try:
            return self.core.generate(
                prompt,
                system_msg=system_msg,
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except ProviderError as error:
            raise RuntimeError(str(error))

    # ---------------- 记忆 ----------------

    def save_memory(self, session_id, task, answer, mode="agent"):
        """只落「任务 + 最终答复」，工具过程不入库；mode 标记会话来源。"""
        if not session_id:
            return
        try:
            self.core.store.get_or_create(session_id, mode=mode)
            self.core.store.append(session_id, "user", task)
            self.core.store.append(session_id, "assistant", answer)
        except Exception as error:
            print(f"[Agent] 写入会话失败（不影响任务返回）: {error}")
