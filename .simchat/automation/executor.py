"""步骤执行器（Phase 5.3）。

三种内置动作执行路径：
  - skill:<name>   → ModLoader.call_tool()（Phase 2 P2.4 已交付）
  - agent:run      → SimChatCore.chat_stream() + consume_stream() 同步消费
  - file:read/write → 本体直接读写工作区（绕过 sandbox）

变量插值 ${step_id.output} / ${step_id.error} / ${env:<name>} ——只在 args 字符串值里做。
"""

import datetime as dt
import json
import os
import re


_INTERPOLATE_RE = re.compile(r"\$\{([^}]+)\}")


def interpolate(args, context, logger=None):
    """递归遍历 args dict/list，把字符串值里的 ${xxx} 替换。

    context 结构：
      {step_id: {"output": str|dict|None, "error": str|None},
       "env": {name: value},
       "flow_id": str,
       "run_id": str}

    规则：
      - 只替换字符串值里的插值表达式；number/bool/array 类型字段保持不变
      - 未定义引用保留原字符串 + warn（不报错不中断）
      - 单引号或反引号包裹的字符串不插值（逃逸）
    """
    if isinstance(args, str):
        return _interpolate_string(args, context, logger)
    if isinstance(args, list):
        return [interpolate(item, context, logger) for item in args]
    if isinstance(args, dict):
        return {k: interpolate(v, context, logger) for k, v in args.items()}
    return args  # number/bool/None 不处理


def _interpolate_string(s, context, logger):
    # 逃逸：单引号或反引号包裹的字符串整个跳过插值
    if (s.startswith("'") and s.endswith("'")) or (s.startswith("`") and s.endswith("`")):
        return s

    def _replace(match):
        expr = match.group(1).strip()
        # ${step_id.output} 或 ${step_id.error}
        if "." in expr and not expr.startswith("env:"):
            step_id, field = expr.split(".", 1)
            step_result = context.get(step_id)
            if step_result is not None:
                value = step_result.get("output") if field == "output" else step_result.get("error")
                if value is not None:
                    return _stringify(value)
            if logger:
                logger.warning("变量插值未定义: ${%s}（step_id=%s 不存在或 output 为空）", expr, step_id)
            return match.group(0)  # 保留原样

        # ${env:NAME}
        if expr.startswith("env:"):
            env_name = expr[4:].strip()
            value = context.get("env", {}).get(env_name) or os.environ.get(env_name, "")
            return _stringify(value)

        # 无法识别 → 保留原样
        if logger:
            logger.warning("变量插值无法识别: ${%s}", expr)
        return match.group(0)

    return _INTERPOLATE_RE.sub(_replace, s)


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# ---------------------------------------------------------------------------
# agent:run SSE 同步消费
# ---------------------------------------------------------------------------

def consume_stream(gen):
    """把 SimChatCore.chat_stream() generator 同步消费成最终字符串。

    SSE event 格式（Phase 2 runtime/core.py）：
      event=chat_started → 忽略
      event=token        → 收集 content
      event=final        → 取 content 直接返回（完整输出）
      event=error        → 抛 RuntimeError

    优先用 final.event 的 content（完整输出）；缺失时回退 token 拼接。
    """
    full_output = []
    last_error = None

    for event in gen:
        etype = event.get("event")
        if etype == "final":
            return event.get("content", "") or "".join(full_output)
        if etype == "token":
            piece = event.get("content", "") or event.get("token", "") or event.get("output", "")
            if piece:
                full_output.append(piece)
        elif etype == "error":
            last_error = event.get("message") or event.get("error") or "agent:run 未知错误"

    if full_output:
        return "".join(full_output)
    if last_error:
        raise RuntimeError("agent:run 执行失败: " + last_error)
    return ""


# ---------------------------------------------------------------------------
# Step 执行
# ---------------------------------------------------------------------------

def execute_step(step, context, engine=None, run_id=None):
    """执行单个 step。返回 (status, output_dict, error_string_or_None)。

    status ∈ {"completed", "failed", "approval_required", "rejected", "timeout", "skipped"}
    """
    use = step.get("use", "")
    args = dict(step.get("args") or {})
    step_id = step.get("id")

    # 变量插值
    args = interpolate(args, context, getattr(engine, "_logger", None))

    try:
        if use.startswith("skill:"):
            status, output, error = _run_skill(use.split(":", 1)[1], args, engine)
        elif use == "agent:run":
            status, output, error = _run_agent(args, engine)
        elif use == "file:read":
            status, output, error = _run_file_read(args, engine)
        elif use == "file:write":
            status, output, error = _run_file_write(args, engine, run_id=run_id, step_id=step_id)
        else:
            return "failed", None, "未知 use 协议: %s" % use

        return status, output, error

    except Exception as e:
        return "failed", None, str(e)


def _run_skill(tool_name, args, engine):
    if engine is None or engine._call_tool is None:
        return "failed", None, "ModLoader 未绑定（engine.bind_loader()）"

    resp = engine._call_tool(tool_name, args)
    if resp.get("ok"):
        return "completed", resp.get("output"), None
    return "failed", None, resp.get("error", "skill 执行失败")


def _run_agent(args, engine):
    if engine is None or engine._chat_stream is None:
        return "failed", None, "SimChatCore 未绑定（engine.bind_runtime()）"

    message = args.get("message") or args.get("goal") or args.get("input") or ""
    session_id = args.get("session_id")

    try:
        gen = engine._chat_stream(message, session_id=session_id)
        output = consume_stream(gen)
        return "completed", output, None
    except Exception as e:
        return "failed", None, str(e)


def _run_file_read(args, engine):
    path = args.get("path") or args.get("file_path") or ""
    if not path:
        return "failed", None, "file:read 缺少 path 参数"

    try:
        # 允许绝对路径，否则按 cwd
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return "completed", content, None
    except FileNotFoundError:
        return "failed", None, "文件不存在: %s" % path
    except Exception as e:
        return "failed", None, "读取失败: %s" % e


def _run_file_write(args, engine, run_id=None, step_id=None):
    """写工作区文件。强制 approval=required（本体强制）。

    Phase 5.4 实现：通过 engine.approval_manager 审批 + 本体直接写。
    宿主侧需在超时前调 engine.approve() / engine.reject()，否则超时自动 REJECTED。
    """
    path = args.get("path") or args.get("file_path") or ""
    content = args.get("content") or args.get("text") or ""
    if not path:
        return "failed", None, "file:write 缺少 path 参数"

    # approval 强制（本体不允许 file:write 跳过审批）
    approval_mgr = getattr(engine, "_approval", None)
    if approval_mgr is None or run_id is None or step_id is None:
        return "approval_required", None, "审批管理器未就绪"

    ticket = approval_mgr.request(run_id, step_id, timeout_s=300)
    result = ticket.wait()

    if result == "approved":
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return "completed", path, None
        except Exception as e:
            return "failed", None, "写入失败: %s" % e
    elif result == "rejected":
        return "rejected", None, "审批被拒绝"
    else:
        return "timeout", None, "审批超时（默认拒绝）"


# ---------------------------------------------------------------------------
# Flow 执行入口（被 engine._run_flow 调用）
# ---------------------------------------------------------------------------

def execute_flow(flow, mod_id, context_init=None, engine=None):
    """按 step 顺序串行执行整个 flow。

    返回 {step_id: {"status": ..., "output": ..., "error": ..., "duration_ms": ...}}

    Phase 5.4 集成：每步 audit.append_step() + quota 检查 + 审批。
    """
    import time as _time

    results = {}
    run_id = None
    audit = getattr(engine, "_audit", None) if engine else None

    context = dict(context_init or {})
    context.setdefault("env", {})
    context.setdefault("flow_id", flow.get("id"))
    context.setdefault("mod_id", mod_id)
    run_id = context.get("run_id")

    if audit and run_id:
        audit.start_run(flow, mod_id, run_id, triggered_by=context.get("triggered_by", "manual"))

    steps = flow.get("steps", [])
    policy = flow.get("policy", {})
    default_on_error = policy.get("on_error", "stop")

    for step in steps:
        sid = step.get("id")
        if not sid:
            continue

        step_on_error = step.get("on_error", default_on_error)

        # 检查 depends
        depends = step.get("depends") or []
        skip = False
        for dep_id in depends:
            dep_result = results.get(dep_id)
            if dep_result is None or dep_result.get("status") != "completed":
                results[sid] = {"status": "skipped", "output": None, "error": "depends %s 未完成" % dep_id}
                skip = True
                break
        if skip:
            if audit and run_id:
                audit.append_step(run_id, sid, "skipped", use=step.get("use"))
            continue

        # 审计：pending
        if audit and run_id:
            audit.append_step(run_id, sid, "pending", use=step.get("use"), args=step.get("args"))

        started = _time.time()
        status, output, error = execute_step(step, context, engine, run_id=run_id)
        finished = _time.time()
        duration_ms = int((finished - started) * 1000)

        results[sid] = {
            "status": status,
            "output": output,
            "error": error,
            "duration_ms": duration_ms,
        }

        # 塞进 context 供后续 step 插值
        context[sid] = {"output": output, "error": error}

        # 审计：final
        if audit and run_id:
            audit.append_step(run_id, sid, status, use=step.get("use"),
                              args=step.get("args"), output=output, error=error,
                              duration_ms=duration_ms)

        if status == "completed":
            continue

        # on_error 处理
        if step_on_error == "stop":
            for next_step in steps:
                next_sid = next_step.get("id")
                if next_sid and next_sid not in results:
                    results[next_sid] = {"status": "skipped", "output": None, "error": "前置 step stop"}
                    if audit and run_id:
                        audit.append_step(run_id, next_sid, "skipped", use=next_step.get("use"))
            break
        if engine and hasattr(engine, "_logger"):
            engine._logger.warning("step %s status=%s, on_error=%s → continue", sid, status, step_on_error)

    # 审计：finish_run
    if audit and run_id:
        overall = "completed"
        for sid, r in results.items():
            if r["status"] == "failed":
                overall = "failed"
                break
            if r["status"] in ("rejected", "timeout"):
                overall = r["status"]
                break
        audit.finish_run(run_id, overall)

    return results
