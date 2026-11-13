"""flow.json DAG 解析与静态校验（Phase 5.1）。

只做"加载前"的校验：JSON Schema 合规 + 静态可达性检查。
变量插值 / 依赖排序 / step 执行都不在此模块——分别在 executor.py 和引擎调度里。
"""

import json
import os
import re


_USE_RE = re.compile(r"^(skill:[a-zA-Z0-9_.\-]+|agent:run|file:(read|write))$")
_FILE_WRITE_RE = re.compile(r"^file:write$")


class FlowValidationError(object):
    """结构化校验错误（便于 lifecycle 和 CLI 同时消费）。"""
    def __init__(self, message, kind="error"):
        self.message = message
        self.kind = kind  # "error" | "warning"
    def __repr__(self):
        return "[%s] %s" % (self.kind, self.message)


# ---------------------------------------------------------------------------
# Schema 校验（纯标准库手写——Phase 5 首期不依赖 jsonschema 第三方包）
# ---------------------------------------------------------------------------

def _check_type(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate_trigger(trigger, errors):
    if not isinstance(trigger, dict):
        errors.append("trigger 必须是对象")
        return
    ttype = trigger.get("type")
    if ttype not in ("cron", "event", "manual"):
        errors.append("trigger.type 必须是 cron | event | manual")
        return
    if ttype == "cron":
        expr = trigger.get("expr")
        if not isinstance(expr, str) or not expr.strip():
            errors.append("cron trigger 必须声明 expr")
    elif ttype == "event":
        event = trigger.get("event")
        if not isinstance(event, str) or event not in ("message.received", "file.changed", "agent.completed"):
            errors.append("event trigger 必须声明合法 event")


def _validate_step(step, index, errors, warnings):
    prefix = "steps[%d]" % index
    sid = step.get("id")

    for key in ("id", "use", "args"):
        if key not in step:
            errors.append("%s 缺少必填字段: %s" % (prefix, key))

    if sid is not None and not isinstance(sid, str):
        errors.append("%s.id 必须是字符串" % prefix)
    elif isinstance(sid, str) and not re.match(r"^[a-z0-9][a-z0-9._-]{1,63}$", sid):
        errors.append("%s.id 格式不合法（%s）" % (prefix, sid))

    use = step.get("use")
    if use is not None and not _USE_RE.match(str(use)):
        errors.append("%s.use 协议非法: %s（只支持 skill:xxx | agent:run | file:read | file:write）" % (prefix, use))

    args = step.get("args")
    if args is not None and not isinstance(args, dict):
        errors.append("%s.args 必须是对象" % prefix)

    if _FILE_WRITE_RE.match(str(use)) and step.get("approval") != "required":
        errors.append("%s(file:write).approval 必须是 required（本体强制）" % prefix)

    depends = step.get("depends")
    if depends is not None and not isinstance(depends, list):
        errors.append("%s.depends 必须是字符串数组" % prefix)

    approval = step.get("approval")
    if approval is not None and approval not in ("required", "optional", "none"):
        errors.append("%s.approval 必须是 required | optional | none" % prefix)

    on_error = step.get("on_error")
    if on_error is not None and on_error not in ("stop", "continue", "retry"):
        errors.append("%s.on_error 必须是 stop | continue | retry" % prefix)

    # warning：approval=required + on_error=continue 语义冲突
    if step.get("approval") == "required" and on_error == "continue":
        warnings.append("%s: approval=required 时 on_error=continue 语义冲突——审批被拒绝后不会继续" % prefix)

    return sid


def _validate_policy(policy, errors):
    if not isinstance(policy, dict):
        errors.append("policy 必须是对象")
        return
    for key in ("max_runtime_s", "daily_quota", "on_error"):
        if key not in policy:
            errors.append("policy 缺少必填字段: %s" % key)
    mrt = policy.get("max_runtime_s")
    if mrt is not None and (not isinstance(mrt, int) or mrt < 1 or mrt > 3600):
        errors.append("policy.max_runtime_s 必须是 1-3600 的整数")
    dq = policy.get("daily_quota")
    if dq is not None and (not isinstance(dq, int) or dq < 1 or dq > 100):
        errors.append("policy.daily_quota 必须是 1-100 的整数")
    oe = policy.get("on_error")
    if oe is not None and oe not in ("stop", "continue"):
        errors.append("policy.on_error 必须是 stop | continue")


def _basic_schema_check(flow):
    errors = []
    warnings = []
    if not isinstance(flow, dict):
        return ["flow.json 必须是对象"], []

    for key in ("id", "version", "trigger", "steps", "policy"):
        if key not in flow:
            errors.append("缺少必填字段: %s" % key)

    fid = flow.get("id")
    if fid is not None and not re.match(r"^[a-z0-9][a-z0-9._-]{2,63}$", fid):
        errors.append("flow.id 格式不合法: %s" % fid)

    ver = flow.get("version")
    if ver is not None and not re.match(r"^\d+\.\d+\.\d+$", str(ver)):
        errors.append("flow.version 必须是语义化版本: %s" % ver)

    _validate_trigger(flow.get("trigger"), errors)

    steps = flow.get("steps")
    step_ids = []
    if not isinstance(steps, list) or len(steps) < 1:
        errors.append("steps 必须是非空数组")
    else:
        for i, step in enumerate(steps):
            sid = _validate_step(step, i, errors, warnings)
            if sid is not None:
                step_ids.append(sid)

    _validate_policy(flow.get("policy"), errors)
    return errors, warnings


# ---------------------------------------------------------------------------
# 静态可达性 + DAG 校验（不依赖执行顺序，只校验 depends 引用合法性）
# ---------------------------------------------------------------------------

def validate_static(flow):
    """返回 (errors: list[str], warnings: list[str])。

    做 schema 之外的深度校验：
      - depends 引用不存在的 step_id
      - step id 重复
      - skill:xxx 里 xxx 看起来可疑（纯启发式，warning 级别）
    """
    errors, warnings = _basic_schema_check(flow)
    if errors:  # schema 都不合法就不做静态分析了
        return errors, warnings

    steps = flow.get("steps", [])
    step_ids = [s.get("id") for s in steps if isinstance(s, dict) and s.get("id")]
    step_id_set = set(step_ids)

    # step id 重复
    for sid in step_ids:
        if step_ids.count(sid) > 1:
            errors.append("step id 重复: %s" % sid)

    # depends 引用不存在
    for i, step in enumerate(steps):
        depends = step.get("depends") if isinstance(step, dict) else None
        if depends:
            for dep in depends:
                if dep not in step_id_set:
                    errors.append("steps[%d] (%s).depends 引用不存在的 step_id: %s" % (i, step.get("id"), dep))
                if dep == step.get("id"):
                    errors.append("steps[%d] (%s).depends 不能引用自己" % (i, step.get("id")))

    return errors, warnings


# ---------------------------------------------------------------------------
# 入口：读文件 + 解析 + 校验
# ---------------------------------------------------------------------------

def parse_flow(path):
    """读 flow.json → 校验 → 返回 (errors: list[str], flow: dict | None)。

    只有 errors 为空时 flow 才是非 None。
    """
    errors = []
    warnings = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            flow = json.load(handle)
    except FileNotFoundError:
        return ["flow.json 不存在: %s" % path], None
    except json.JSONDecodeError as e:
        return ["flow.json 解析失败: %s" % e], None
    except Exception as e:
        return ["flow.json 读取失败: %s" % e], None

    errs, warns = validate_static(flow)
    errors.extend(errs)
    warnings.extend(warns)

    if errors:
        return errors, None

    # 规范化：补默认值
    _apply_defaults(flow)
    return errors, flow


def _apply_defaults(flow):
    """把 schema 里 default 的字段写进对象，让 executor 直接消费。"""
    policy = flow.setdefault("policy", {})
    policy.setdefault("max_runtime_s", 300)
    policy.setdefault("daily_quota", 10)
    policy.setdefault("on_error", "stop")
    policy.setdefault("concurrency", 1)

    for step in flow.get("steps", []):
        if not isinstance(step, dict):
            continue
        step.setdefault("approval", "none")
        step.setdefault("max_runtime_s", 60)
        step.setdefault("on_error", "stop")
        step.setdefault("retry_count", 0)
