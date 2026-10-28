"""SimChat skill MOD 基类（ABI：lmbrew-mod/1）。

skill MOD 的 execute() 入口通过 SDK ToolSpec.backend 字符串引用被 runner 调用。
MOD 代码必须 import 本模块，不得依赖宿主私有 BaseSkill。
"""

import datetime
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseSkill(ABC):
    """所有 SimChat skill MOD 的基类。

    子类必须实现 execute(params: dict) -> dict。
    其余字段（skill_name / skill_description / trigger_keywords / input_schema）
    用于 ToolSpec 的 label / description / triggers / params_schema 映射。
    """
    skill_name = "base"
    skill_description = "基础技能类"
    skill_version = "1.0.0"
    trigger_keywords: List[str] = []
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}

    def __init__(self):
        self.last_executed: Optional[str] = None
        self.execution_count: int = 0
        self.is_available: bool = True

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能。返回 dict，通常包含 'success': bool。"""
        pass

    def validate_params(self, params: Dict[str, Any]) -> bool:
        if not self.input_schema:
            return True
        for key, value_type in self.input_schema.items():
            if key in params and not isinstance(params[key], value_type):
                return False
        return True

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.skill_name,
            "description": self.skill_description,
            "version": self.skill_version,
            "keywords": self.trigger_keywords,
            "available": self.is_available,
            "last_executed": self.last_executed,
            "execution_count": self.execution_count,
        }

    def _record_execution(self):
        self.last_executed = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.execution_count += 1
