"""Kirara 地图（AI 实例）生成器。

项目术语中「地图」= AI 实例。本模块用确定性的 MOD 侧算法，从人设文件派生
头像与系统提示，并声明装备清单；不联网、不依赖不存在的服务。
生成结果由宿主落盘为只读实例（不可编辑、不可删除）。
"""

import hashlib
import os

MAP_ID = "kirara"

_AVATAR_CANDIDATES = tuple(
    "/static/sprites/logos/kirara-%d.png" % index for index in range(1, 6)
)

_PERSONA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "maid.txt"
)

_ORBITER_GUIDE = """【Orbiter 工具契约】
- 简单问题（闲聊、事实、一步能答完的）直接回答，不要委派。
- 复杂问题再调用 orbiter 方块：
  orbiter PARAMS:{"request": "<整理后的原始需求>", "context": "<可选上下文>"}
- 也可以用命令写法：/@<模型名> -prompt "<原始需求>"；
  带参数的图像请求单独一行写 /@<模型名> -mode=image，下一行再接自然语言描述。
- 调用技能：/$ <命令> -dir "<工作目录>"。
- 每次云端外发都会请求主人审批；被拒绝时如实说明，不要重试绕过。
- 本地 JRVS 不可用时 orbiter 会失败关闭，此时不要改走云端润色原始提示词。
- 不确定模型是否存在时先询问主人，不要编造模型 id。"""


def _read_persona():
    try:
        with open(_PERSONA_PATH, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def build_map():
    """返回一张 Kirara 地图（AI 实例）的预设描述。"""
    persona = _read_persona()
    digest = hashlib.sha256(("kirara-map/1\0" + persona).encode("utf-8")).hexdigest()
    avatar = _AVATAR_CANDIDATES[int(digest[:2], 16) % len(_AVATAR_CANDIDATES)]
    system_prompt = persona + ("\n\n" + _ORBITER_GUIDE if persona else _ORBITER_GUIDE)
    return {
        "id": MAP_ID,
        "name": "绮罗罗",
        "description": "Kirara 行为包生成的只读地图：本地 JRVS 分诊，复杂任务经 orbiter 派发云端。",
        "avatar": avatar,
        "avatar_type": "image",
        "system_prompt": system_prompt,
        "agent_capable": True,
        "engine_preset": "normal",
        "equipped": ["orbiter", "kirara.trivia"],
    }


def register_map(api):
    return api.register_agent_preset(build_map())
