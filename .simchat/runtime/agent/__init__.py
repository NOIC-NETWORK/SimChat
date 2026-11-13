# -*- coding: utf-8 -*-
"""SimChat Agent 模式（Phase 1 只读闭环 + Phase 2 写操作审批 + Phase 3 shell/abort）。

组成：
- tools.py：工具注册表 + workdir 沙箱校验（read/write/dangerous 风险分级，shell 可配置开关）
- loop.py：ReAct 循环（/$TOOL: 协议解析、max_turns、abort、SSE 事件、写操作挂起/恢复）
- runs.py：运行登记表（内存态 abort 事件 + 挂起态落盘/TTL/恢复）
- backend.py：SimChat 后端适配器（SimChatCore 服务商 + SessionStore）
"""
from .tools import (
    TOOL_REGISTRY,
    ToolError,
    list_agent_tools,
    build_tool_protocol_section,
    resolve_workdir,
    truncate_output,
    configure_shell,
    DEFAULT_SHELL_TIMEOUT,
)
from .loop import AgentLoop, parse_tool_calls
from .backend import SimChatAgentBackend
from .runs import (
    AgentRunRegistry,
    agent_runs,
    save_pending_state,
    load_pending_state,
    discard_pending_state,
    DEFAULT_APPROVAL_TTL,
)

__all__ = [
    'TOOL_REGISTRY', 'ToolError', 'list_agent_tools', 'build_tool_protocol_section',
    'resolve_workdir', 'truncate_output', 'configure_shell', 'DEFAULT_SHELL_TIMEOUT',
    'AgentLoop', 'parse_tool_calls', 'SimChatAgentBackend',
    'AgentRunRegistry', 'agent_runs',
    'save_pending_state', 'load_pending_state', 'discard_pending_state',
    'DEFAULT_APPROVAL_TTL',
]
