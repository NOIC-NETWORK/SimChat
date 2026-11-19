"""SkillManager facade（P2.4 新增，能力调用已收口到方块注册表）。

旧宿主代码（rigard.py / jrvs.py）仍通过 get_skill_manager() 获取 SkillManager，
但内部不再直接调用 ModLoader.call_tool()，而是经 runtime.agent.tools.invoke_block()
落到 BLOCK_REGISTRY 的方块上。

旧 API 表面不变：
  skill_manager.get_registry().get_skill("webSearch").execute(params)
  skill_manager.execute_skill(name, params)
  skill_manager.list_all_skills() / auto_execute_skills()

无实例上下文的装备判定：
  宿主服务调用拿不到 Agent 实例，因此只允许一份**显式、固定**的只读兼容清单
  （HOST_SERVICE_ALLOWED_BLOCKS）。清单之外的方块一律拒绝，不做默认放开；
  写级/危险级方块永远不会经此通路执行。
"""

from simchat.loader.lifecycle import get_loader


# 旧宿主/MOD 通过 SkillManager 实际用到的只读能力（显式白名单，不是“只读就放行”）：
#   - realityCheck / areYouUnderTrouble：宿主安全能力（Kirara shim 等）
#   - webSearch：barry.galax 的召回阶段
#   - readFile / screenshotRecognition：Kirara jrvs 技能桥接的历史入口
# 写级/危险级方块不在此清单内，invoke_block 也会再次拒绝未显式审批的写操作。
HOST_SERVICE_ALLOWED_BLOCKS = frozenset((
    "areYouUnderTrouble",
    "readFile",
    "realityCheck",
    "screenshotRecognition",
    "webSearch",
))


def _allowed_block(name):
    """按唯一入口的同一套规则解析方块；不在显式清单内返回 None。"""
    from simchat.runtime.agent.tools import BLOCK_REGISTRY

    block = BLOCK_REGISTRY.get(name)
    if block is None or block.name not in HOST_SERVICE_ALLOWED_BLOCKS:
        return None
    return block


def _deny_reason(name):
    """区分“没注册”和“注册了但不在宿主服务清单”，便于旧调用方排障。"""
    from simchat.runtime.agent.tools import BLOCK_REGISTRY

    if BLOCK_REGISTRY.get(name) is None:
        return "方块 %s 未注册（MOD 未安装或未加载）" % name
    return "技能 %s 不在宿主服务的显式允许清单内" % name


def _invoke(name, params):
    """经方块注册表唯一入口执行；返回值保持旧 execute_skill 的 dict 形状。"""
    from simchat.runtime.agent.tools import invoke_block

    resp = invoke_block(name, params or {}, allowed=HOST_SERVICE_ALLOWED_BLOCKS)
    if resp.get("ok"):
        output = resp.get("output")
        # 兼容旧 API：MOD 工具自带 success 的 dict 直接透传；
        # 内建方块（如 realityCheck）返回领域 dict 时补一层旧 BaseSkill 外壳。
        if isinstance(output, dict):
            if "success" in output:
                return output
            return {"success": True, "result": output}
        return {"success": True, "result": output}
    return {"success": False, "error": resp.get("error", "skill 执行失败")}


class _SkillProxy(object):
    """模拟宿主 BaseSkill：execute(params) 经方块注册表唯一入口。"""
    def __init__(self, name):
        self._name = name

    def execute(self, params):
        if _allowed_block(self._name) is None:
            return {"success": False, "error": _deny_reason(self._name)}
        return _invoke(self._name, params)

    # 兼容旧 BaseSkill 的属性访问
    @property
    def skill_name(self):
        return self._name


class _SkillRegistryProxy(object):
    def list_skills(self):
        return _list_allowed_blocks()

    def get_skill(self, name):
        block = _allowed_block(name)
        if block is None:
            return None
        return _SkillProxy(block.name)


class SkillManager(object):
    """旧 SkillManager API 兼容层。"""
    def __init__(self):
        self._registry = _SkillRegistryProxy()

    def get_registry(self):
        return self._registry

    def get_skill(self, name):
        return self._registry.get_skill(name)

    def execute_skill(self, name, params):
        if _allowed_block(name) is None:
            return {"success": False, "error": _deny_reason(name)}
        return _invoke(name, params)

    def list_all_skills(self):
        return _list_allowed_blocks()

    def auto_execute_skills(self, query, params=None):
        """旧 SkillExecutor 的自动路由：查 tool 的 triggers 关键字，命中即执行。

        只在显式允许清单内路由，不再遍历全部 MOD 工具。
        """
        loader = get_loader()
        results = []
        for tool in _list_allowed_blocks():
            name = tool["name"]
            triggers = []
            if loader is not None:
                info = loader._tools.get(name, {})
                triggers = info.get("spec", {}).get("triggers") or []
            for kw in triggers:
                if kw.lower() in query.lower():
                    resp = self.execute_skill(name, dict(params or {}, trigger_kw=kw))
                    results.append({"skill": name, "trigger": kw, "result": resp})
                    break
        return results


def _list_allowed_blocks():
    """只列出显式允许清单内、且已注册的方块（供旧的技能发现 API）。"""
    from simchat.runtime.agent.tools import BLOCK_REGISTRY

    result = []
    for name in sorted(HOST_SERVICE_ALLOWED_BLOCKS):
        block = BLOCK_REGISTRY.get(name)
        if block is None:
            continue
        meta = block.meta()
        result.append({
            "name": meta.get("name"),
            "label": meta.get("label"),
            "description": meta.get("description", ""),
            "risk": meta.get("risk", "read"),
            "usage": meta.get("usage", ""),
            "mod_id": meta.get("mod_id", ""),
        })
    return result


# 旧 API：init_xxx_skill 函数不再需要（skill MOD 由 ModLoader 扫描加载）
# 保留占位避免旧代码 AttributeError
def init_readFile_skill(): pass
def init_screenshotRecognition_skill(): pass
def init_areYouUnderTrouble_skill(): pass
def init_webSearch_skill(): pass
def init_realityCheck_skill(): pass


def get_skill_manager() -> SkillManager:
    return SkillManager()
