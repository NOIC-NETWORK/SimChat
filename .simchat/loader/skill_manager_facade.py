"""SkillManager facade（P2.4 新增）。

旧宿主代码（rigard.py / jrvs.py）仍通过 get_skill_manager() 获取 SkillManager，
但内部已改为委托给 SimChat ModLoader 的 skill MOD 体系。

旧 API 表面不变：
  skill_manager.get_registry().get_skill("webSearch").execute(params)
  skill_manager.execute_skill(name, params)
  skill_manager.list_all_skills() / auto_execute_skills()

内部实现：execute_skill() 通过 ModLoader.call_tool() → sandbox.invoke_tool()。
"""

from simchat.loader.lifecycle import get_loader


class _SkillProxy(object):
    """模拟宿主 BaseSkill：execute(params) 委托 ModLoader.call_tool()。"""
    def __init__(self, name):
        self._name = name

    def execute(self, params):
        loader = get_loader()
        if loader is None:
            return {"success": False, "error": "ModLoader 未初始化"}
        resp = loader.call_tool(self._name, params or {})
        if resp.get("ok"):
            output = resp.get("output")
            # 兼容旧 API：output 是 skill.execute() 返回的 dict，直接透传
            if isinstance(output, dict):
                return output
            return {"success": True, "result": output}
        return {"success": False, "error": resp.get("error", "skill 执行失败")}

    # 兼容旧 BaseSkill 的属性访问
    @property
    def skill_name(self):
        return self._name


class _SkillRegistryProxy(object):
    def list_skills(self):
        loader = get_loader()
        if loader is None:
            return []
        return loader.list_tools()

    def get_skill(self, name):
        loader = get_loader()
        if loader is None:
            return None
        if not loader.has_tool(name):
            return None
        return _SkillProxy(name)


class SkillManager(object):
    """旧 SkillManager API 兼容层。"""
    def __init__(self):
        self._registry = _SkillRegistryProxy()

    def get_registry(self):
        return self._registry

    def get_skill(self, name):
        return self._registry.get_skill(name)

    def execute_skill(self, name, params):
        loader = get_loader()
        if loader is None:
            return {"success": False, "error": "ModLoader 未初始化"}
        resp = loader.call_tool(name, params or {})
        if resp.get("ok"):
            output = resp.get("output")
            return {"success": True, "result": output} if not isinstance(output, dict) else output
        return {"success": False, "error": resp.get("error", "skill 执行失败")}

    def list_all_skills(self):
        loader = get_loader()
        if loader is None:
            return []
        return loader.list_tools()

    def auto_execute_skills(self, query, params=None):
        """旧 SkillExecutor 的自动路由：查 tool 的 triggers 关键字，命中即执行。"""
        loader = get_loader()
        if loader is None:
            return []
        results = []
        for tool in loader.list_tools():
            name = tool["name"]
            # 从 loader 内部 _tools dict 取 triggers
            info = loader._tools.get(name, {})
            triggers = info.get("spec", {}).get("triggers") or []
            for kw in triggers:
                if kw.lower() in query.lower():
                    resp = self.execute_skill(name, dict(params or {}, trigger_kw=kw))
                    results.append({"skill": name, "trigger": kw, "result": resp})
                    break
        return results


# 旧 API：init_xxx_skill 函数不再需要（skill MOD 由 ModLoader 扫描加载）
# 保留占位避免旧代码 AttributeError
def init_readFile_skill(): pass
def init_screenshotRecognition_skill(): pass
def init_areYouUnderTrouble_skill(): pass
def init_webSearch_skill(): pass
def init_realityCheck_skill(): pass


def get_skill_manager() -> SkillManager:
    return SkillManager()
