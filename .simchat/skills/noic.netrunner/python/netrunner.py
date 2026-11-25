"""Netrunner — 批量信息调研与代码技能（占位）。

当前只完成注册外壳：manifest 可被扫描，入口可被沙箱加载，但不声明任何工具。
等能力边界确定后，在 register() 里补 ToolSpec 与对应 execute 实现即可。
"""

from simchat_mod import hook


@hook("agent.block")
def register(api):
    """占位注册：暂不声明工具。"""
    return None
