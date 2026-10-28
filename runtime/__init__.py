"""SimChat 本体运行时（Apache-2.0）：provider 抽象 + 会话存储 + 对话核心。

液压系统的承压层：脱离任何宿主，本体即可完成独立对话。
"""

from .core import SimChatCore
from .providers import OLLAMA_AVAILABLE, ProviderError
from .store import SessionStore
from . import provider_config, ui_blocks

__all__ = [
    "SimChatCore",
    "SessionStore",
    "ProviderError",
    "OLLAMA_AVAILABLE",
    "provider_config",
    "ui_blocks",
]
