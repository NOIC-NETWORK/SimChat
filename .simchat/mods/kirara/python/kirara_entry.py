"""Kirara MOD 加载入口。

阶段 1 把 Kirara 的特有能力注册为 ToolSpec 方块；阶段 2 通过 agent.map
注册只读地图（AI 实例），并装备宿主方块 orbiter。

不 import 包内 JRVS 内核、services 与前端资源。
"""

from kirara_blocks import register_blocks
from kirara_map import register_map


def register(api):
    """加载入口：注册 Kirara 的方块集合与只读地图（AI 实例）。"""
    register_blocks(api)
    register_map(api)
