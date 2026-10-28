"""依赖解析（Phase 2 剩余切片 P2.1）。

只做加载期"存在性"检查：本体版本（已由 manifest.check_requires 处理）、
运行时 Python 版本、第三方包能否 import。**不自动 pip install**——那是宿主行为，
MOD 不能触发；缺失必需依赖直接 fail-closed（status=failed）。

约定：
- requires.packages 里的条目写**模块导入名**，不是 pip 包名。
  例如写 ``['bs4']`` 而非 ``['beautifulsoup4']``；写 ``['PIL']`` 而非 ``['Pillow']``。
  这个约定在 MOD manifest schema 里同步注明。
- 包内版本范围（如 ``requests>=2.28``）Phase 2.1 不解析，只检查模块是否存在。
  如果需要精确版本约束，留 Phase 4 CLI。
- requires.python 用 semver 范围写法（与 requires.lmbrew 同格式），
  如 ``">=3.9,<3.12"``、``"==3.11.*"``。缺省表示不限。
"""

import importlib.util
import re
import sys

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


def _parse_version(spec):
    """解析 '3.11.5' → (3, 11, 5)；'3.11' → (3, 11, 0)；失败返回 None。"""
    m = _VERSION_RE.match(spec or "")
    if not m:
        return None
    parts = m.groups()
    return tuple(int(x) if x is not None else 0 for x in parts)


def _satisfies_version(actual, spec):
    """检查 actual=(3,11,5) 是否满足 semver 范围 spec 字符串。

    支持：``==3.11.*`` / ``>=3.9`` / ``>=3.9,<3.12`` / ``>3.8`` / ``<3.14`` / ``==3.11``。
    与 manifest.py._satisfies 的简化实现对齐（纯元组比较）。
    """
    if not spec:
        return True
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        op = part[:2] if part[:2] in (">=", "<=", "==") else part[:1]
        ver = part[len(op):].strip()
        if ver.endswith(".*"):
            ver = ver[:-2]
        target = _parse_version(ver)
        if target is None:
            # 非法 spec → 保守拒绝
            return False
        # 补齐 actual 的第三段
        a = actual if len(actual) >= 3 else actual + (0,) * (3 - len(actual))
        cmp_map = {"==": lambda x, y: x[:len(y)] == y,
                   ">=": lambda x, y: x >= y,
                   "<=": lambda x, y: x <= y,
                   ">":  lambda x, y: x > y,
                   "<":  lambda x, y: x < y}
        fn = cmp_map.get(op)
        if fn is None:
            return False
        if not fn(a, target):
            return False
    return True


def check_python_version(manifest):
    """返回 (ok, message)。"""
    requires = (manifest.get("requires") or {}).get("python")
    if not requires:
        return True, ""
    actual = sys.version_info[:3]
    if _satisfies_version(actual, requires):
        return True, ""
    return False, "Python 版本 %s.%s.%s 不满足 requires.python=%s" % (
        actual[0], actual[1], actual[2], requires)


def check_packages(manifest):
    """返回 (ok, message, missing)。message 是可读串，missing 是缺失包列表。"""
    packages = (manifest.get("requires") or {}).get("packages") or []
    if not packages:
        return True, "", []
    missing = []
    for name in packages:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if missing:
        return False, "缺少必需依赖: " + ", ".join(missing), missing
    return True, "", []


def resolve_dependencies(manifest):
    """合并 check_python_version + check_packages 的结果，返回 (ok, message)。

    lifecycle._load_one 在 manifest 校验与 check_requires 之后、verify_package 之前调用。
    """
    ok_py, msg_py = check_python_version(manifest)
    ok_pkg, msg_pkg, _ = check_packages(manifest)
    if ok_py and ok_pkg:
        return True, ""
    parts = []
    if msg_py: parts.append(msg_py)
    if msg_pkg: parts.append(msg_pkg)
    return False, "; ".join(parts)
