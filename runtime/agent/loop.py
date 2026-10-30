# -*- coding: utf-8 -*-
"""Agent ReAct 循环（Phase 1 只读 + Phase 2 写操作审批 + Phase 3 shell/abort）。

通过 SimChatAgentBackend 接入 SimChat 本体，不直接依赖 Kirara/JRVS 内核：
- build_prompt：把用户消息与历史拼成单条提示（runtime/agent/backend.py）
- generate：经 SimChatCore 服务商解析后的一次性推理
- save_memory：只落"任务+最终答复"到 SessionStore，工具过程不入库
- safety_system：本体无分类器时为 None，循环自动跳过安全检查

协议：模型输出行内 /$TOOL:工具名 PARAMS:{...}（与 otherAI 的 /$SKILL:、/@MODEL: 同风格）。
整轮无工具指令 → 该输出即最终答复，循环结束。

审批流（Phase 2）：
- 遇 write/dangerous 级工具 → 发 approval_required 事件并返回挂起态（run_ctx + transcript + pending）。
- run() / resume() 均返回 Optional[pending_state]：None 表示任务终结，非 None 表示已挂起待审批。
- resume() 由 /api/agent/approve 调用：先裁决 pending 调用，再处理同轮剩余调用，最后续跑后续轮次。
"""
import json
import re
import threading

from .tools import (
    TOOL_REGISTRY, build_tool_protocol_section, truncate_output, ToolError,
    resolve_workdir, DEFAULT_SHELL_TIMEOUT,
)

TOOL_SPLIT_RE = re.compile(r'/\$\s*TOOL\s*:', re.IGNORECASE)
TOOL_NAME_RE = re.compile(r'\s*([A-Za-z_]\w*)')
TOOL_PARAMS_RE = re.compile(r'PARAMS\s*:\s*(.+)$', re.IGNORECASE | re.DOTALL)


def _extract_json_object(text):
    """从文本中扫描出第一个括号平衡的 JSON 对象；失败返回 None（宽松兜底）。"""
    start = text.find('{')
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except Exception:
                            break
        start = text.find('{', start + 1)
    return None


def _parse_tool_line(stripped):
    """解析一行内的若干 /$TOOL: 指令（JSON 失败时宽松兜底，再失败用空参数）。"""
    calls = []
    for part in TOOL_SPLIT_RE.split(stripped)[1:]:
        name_match = TOOL_NAME_RE.match(part)
        if not name_match:
            continue
        name = name_match.group(1).lower()
        rest = part[name_match.end():].strip()
        params = {}
        params_match = TOOL_PARAMS_RE.match(rest)
        raw = params_match.group(1).strip() if params_match else ''
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    params = loaded
            except Exception:
                obj = _extract_json_object(raw)
                if isinstance(obj, dict):
                    params = obj
        calls.append({'tool': name, 'params': params})
    return calls


def parse_tool_calls(output):
    """解析模型输出 → (思考文本, 工具调用列表)。整轮无指令时思考即最终答复。"""
    calls = []
    thought_lines = []
    for line in (output or '').splitlines():
        stripped = line.strip()
        if TOOL_SPLIT_RE.search(stripped):
            calls.extend(_parse_tool_line(stripped))
        else:
            thought_lines.append(line)
    return '\n'.join(thought_lines).strip(), calls


PLAN_ITEM_RE = re.compile(r'^\s*\d+[\.\)、]\s*(.+?)\s*$')

# PR-2：token 预算与压缩阈值
# ollama num_ctx=16384、num_predict=1024 → 可用 prompt 预算 ≈ 15360
# 安全裕量 3072 → 触发压缩阈值 12288（80%）
TOKEN_BUDGET = 16384
NUM_PREDICT = 1024
COMPACTION_THRESHOLD = TOKEN_BUDGET - NUM_PREDICT - 3072   # ≈ 12288
COMPACTION_KEEP_RECENT = 3   # 压缩时保留最近 N 条原始记录


def estimate_tokens(text):
    """粗略估算 token 数：CJK 按 1.5 字/token，其余按 4 字符/token。

    与 ollama 的 BPE 分词有 ±20% 漂移，仅用于阈值触发，不作为精确计量。
    符合 project_memory 硬约束：不调用大模型，只用加权方法。
    """
    if not text:
        return 0
    cjk = 0
    for ch in text:
        code = ord(ch)
        if (0x4E00 <= code <= 0x9FFF) or (0x3040 <= code <= 0x30FF) or (0xAC00 <= code <= 0xD7AF):
            cjk += 1
    non_cjk = len(text) - cjk
    return int(cjk / 1.5 + non_cjk / 4)


def compact_transcript(transcript, keep_recent=COMPACTION_KEEP_RECENT):
    """加权压缩：把早期 transcript 条目合并为单行摘要（不调 LLM）。

    保留最近 keep_recent 条原始记录，其余合并为：
    "- [压缩] 早期 N 条已合并：共调用工具 X 次（tool_a×3, tool_b×2）"

    权重方法：按工具调用次数加权，保留工具身份与计数，丢弃具体输出。
    """
    if not transcript or len(transcript) <= keep_recent:
        return list(transcript)
    old = transcript[:-keep_recent]
    recent = transcript[-keep_recent:]
    # 从早期条目提取工具名（格式 "- tNcM tool_name 参数 ..." 或 "- [规划阶段] ..."）
    tool_pattern = re.compile(r'^-\s+(?:\[.*?\]\s+)?t\d+c\d+\s+(\w+)', re.MULTILINE)
    tool_counts = {}
    plan_count = 0
    other_count = 0
    for entry in old:
        matches = tool_pattern.findall(entry)
        if matches:
            for name in matches:
                tool_counts[name] = tool_counts.get(name, 0) + 1
        elif '[规划阶段]' in entry or '[压缩]' in entry:
            plan_count += 1
        else:
            other_count += 1
    parts = [f"{name}×{count}" for name, count in tool_counts.items()]
    summary_bits = []
    if parts:
        summary_bits.append("工具 " + ", ".join(parts))
    if plan_count:
        summary_bits.append(f"规划记录×{plan_count}")
    if other_count:
        summary_bits.append(f"其他×{other_count}")
    summary = "- [压缩] 早期 {} 条记录已合并：{}".format(
        len(old),
        "；".join(summary_bits) if summary_bits else "（无可识别内容）"
    )
    return [summary] + list(recent)


def extract_plan_items(text):
    """从模型输出中提取 Markdown checklist / 编号步骤。返回步骤列表（字符串数组）。"""
    if not text:
        return []
    steps = []
    for line in text.splitlines():
        m = PLAN_ITEM_RE.match(line)
        if m:
            item = m.group(1).strip()
            # 去掉 [ ] / [x] 这种 checkbox 前缀
            item = re.sub(r'^\[[ xX]\]\s*', '', item)
            if item:
                steps.append(item)
    # 去重保序
    seen = set()
    uniq = []
    for s in steps:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _risk_reason(risk, call):
    """给前端审批卡片的人类可读风险说明。"""
    tool = call.get('tool', '')
    if risk == 'write':
        return f"写操作工具 {tool} 将修改项目文件，需您确认。"
    if risk == 'dangerous':
        return f"危险工具 {tool} 将在宿主执行命令，需您逐次确认。"
    return f"工具 {tool} 需要审批。"


class AgentLoop:
    """单次 Agent 任务的 ReAct 循环；支持写操作挂起与审批恢复；支持 Chat 懒调用 / Agent 完整两种模式。"""

    def __init__(self, backend, workdir=None, max_turns=10, abort_event=None,
                 shell_enabled=False, shell_timeout=DEFAULT_SHELL_TIMEOUT, mode="agent"):
        self.backend = backend
        self.workdir = resolve_workdir(workdir)
        try:
            self.max_turns = max(1, min(int(max_turns), 25))
        except (TypeError, ValueError):
            self.max_turns = 10
        self.abort_event = abort_event or threading.Event()
        # shell（dangerous 级）：默认关闭；超时由 options.agent_shell_timeout 注入
        self.shell_enabled = bool(shell_enabled)
        try:
            self.shell_timeout = max(1, min(int(shell_timeout), 30))
        except (TypeError, ValueError):
            self.shell_timeout = DEFAULT_SHELL_TIMEOUT
        # 模式："agent"（完整 ReAct + 审批流）| "chat"（懒调用，只暴露 read 工具）
        self.mode = mode if mode in ("agent", "chat") else "agent"
        # 运行上下文（run/resume 时填充，用于构造挂起态）
        self.run_ctx = None
        # 计划进度：成功执行过的只读工具数，用于 plan_progress emit
        self._plan_done = 0
        # 计划步骤列表（turn-0 生成后存起来，挂起时写入 pending_state，恢复时重建）
        self._plan_steps = None

    def abort(self):
        self.abort_event.set()

    def _check_safety(self, message):
        """本体没有安全分类器时返回 None（跳过）；有则复用宿主同源检查。"""
        checker = getattr(self.backend, 'safety_system', None)
        if checker is None:
            return None
        try:
            return checker.detect(message)
        except Exception as e:
            print(f"[Agent] 安全检查失败，跳过（{e}）")
            return None

    def _rejection_text(self, category):
        checker = getattr(self.backend, 'safety_system', None)
        if checker is not None:
            try:
                return checker.get_rejection_response(category)
            except Exception:
                pass
        return "抱歉，该请求违反安全策略，我无法执行。"

    def _save_memory(self, task, final_answer):
        """只把任务+最终答复写入 SessionStore（供任务列表与"继续追问"恢复）。"""
        try:
            sid = (self.run_ctx or {}).get('session_id')
            if sid:
                self.backend.save_memory(sid, task, final_answer)
        except Exception as e:
            print(f"[Agent] 写入记忆失败（不影响任务返回）: {e}")

    def _build_base_prompt(self, message, history, session_id):
        try:
            base = self.backend.build_prompt(message, history=history, session_id=session_id)
        except Exception as e:
            print(f"[Agent] 组装上下文失败，改用纯任务提示: {e}")
            base = f"【用户最新消息】{message}"
        # Agent 模式必须覆盖 SFT "请直接回复用户" 指令，否则 7B 模型会跳过工具直接说话
        # 先移除旧指令，再追加 Agent 专用强指令
        if '请直接回复用户' in base:
            base = base.split('请直接回复用户')[0].rstrip()
        base += (
            '\n\n【你当前处于 Agent 模式，务必遵守以下行为模式】\n'
            '你现在是一个可以调用工具的智能体，不再是普通聊天助手。\n'
            '当用户请求需要获取信息、读取文件、搜索内容等超出你直接知识的任务时，\n'
            '你必须先简短说明思路，然后输出工具指令（/$TOOL:tool_name PARAMS:{...}）。\n'
            '只有在任务完全不需要工具时，才可以直接给出最终答复。'
        )
        return base

    def _build_pending_state(self, transcript, pending):
        """构造可落盘的挂起态（JSON 可序列化）。"""
        ctx = self.run_ctx or {}
        backend_state = None
        snapshot = getattr(self.backend, 'snapshot', None)
        if callable(snapshot):
            try:
                backend_state = snapshot()
            except Exception:
                backend_state = None
        return {
            'run_id': ctx.get('run_id'),
            'message': ctx.get('message'),
            'history': ctx.get('history') or [],
            'session_id': ctx.get('session_id'),
            'persona': ctx.get('persona'),
            'max_turns': self.max_turns,
            'workdir': self.workdir,
            'mode': self.mode,
            'transcript': transcript,
            'pending': pending,
            # 模型选择与 system prompt（审批恢复时原样重建）
            'backend': backend_state,
            'system_prompt': ctx.get('system_prompt'),
            # 计划上下文（resume 时重建 plan 卡片）
            'plan_steps': self._plan_steps,
            'plan_done': self._plan_done,
        }

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def run(self, message, history=None, session_id=None, persona=None,
            run_id=None, system_prompt=None, emit=None):
        """全新任务入口。返回挂起态（dict）或 None（已终结）。"""
        emit = emit or (lambda evt: None)

        # 尽早初始化 run_ctx，确保 reject 等早退路径也能拿到 session_id
        self.run_ctx = {
            'run_id': run_id,
            'message': message,
            'history': history or [],
            'session_id': session_id,
            'persona': persona,
            'system_prompt': system_prompt,
        }
        sid = session_id or (self.run_ctx or {}).get('session_id')

        if not self.backend.available():
            emit({'event': 'error', 'message': self.backend.unavailable_message(),
                  'session_id': sid})
            return None

        safety = self._check_safety(message)
        if safety is not None and not safety.get('safe', False):
            reject = self._rejection_text(safety.get('category'))
            print("[Agent] 用户输入包含违规内容，已拦截并返回拒绝响应")
            emit({'event': 'final', 'content': reject, 'session_id': sid})
            self._save_memory(message, reject)
            return None

        base_prompt = self._build_base_prompt(message, history or [], session_id)
        protocol = build_tool_protocol_section(mode=self.mode)
        transcript = []

        # ------- turn-0：纯推理生成执行计划（不调工具） -------
        emit({'event': 'thought', 'turn': 0, 'content': '收到任务，开始规划…',
              'session_id': sid})
        plan_prompt = (
            base_prompt + '\n\n' + protocol +
            '\n\n【现在先规划，本次只输出执行计划，不要调用任何工具！】'
            '\n请先用数字编号列出你将执行的步骤（每行一步，从 1 开始）。'
            '\n每步一句话，描述你想做什么（如"用 glob 定位目标文件"、"用 file_read 读取内容"、"总结回答用户"）。'
            '\n规划完就停下，下一轮再开始执行。不要输出任何 /$TOOL: 指令！'
            '\n如果这个任务完全不需要工具（比如只是简单问候或闲聊），直接说"无需工具：你的答复内容"然后停止。'
        )
        plan_output = self.backend.generate(plan_prompt, system_msg=system_prompt or None)
        plan_thought, _ignored_calls = parse_tool_calls(plan_output)
        plan_steps = extract_plan_items(plan_thought)

        # Bug fix 2: "无需工具" escape hatch —— 没 checklist 且模型没打算调工具，直接当 final 返回
        if not plan_steps and not _ignored_calls:
            no_tools_match = re.match(r'无需工具[：:]\s*(.+)', plan_thought, re.DOTALL)
            direct_answer = no_tools_match.group(1).strip() if no_tools_match else plan_thought.strip()
            if direct_answer and len(direct_answer) > 5:
                emit({'event': 'final', 'content': direct_answer, 'session_id': sid})
                self._save_memory(message, direct_answer)
                return None

        if plan_steps:
            self._plan_steps = plan_steps   # 存到实例，挂起时进 pending_state
            self._plan_done = 0
            emit({'event': 'plan', 'turn': 0, 'steps': plan_steps,
                  'raw': plan_thought[:500]})
        else:
            # 没解析到 checklist，也把原始思考发给前端展示
            emit({'event': 'thought', 'turn': 0, 'content': plan_thought[:500] or '规划中…'})
        # 把 turn-0 的思考注入 transcript，后续轮次模型能看到自己的规划
        transcript.append(f"- [规划阶段] {plan_thought[:300]}")
        # ------- 计划完毕，进入正常 ReAct 循环 -------
        return self._run_turns(1, base_prompt, protocol, system_prompt, transcript, emit)

    def resume(self, state, decision, edits, system_prompt, emit=None):
        """审批恢复入口。返回新的挂起态（dict）或 None（已终结）。"""
        emit = emit or (lambda evt: None)
        self.run_ctx = {
            'run_id': state.get('run_id'),
            'message': state.get('message'),
            'history': state.get('history') or [],
            'session_id': state.get('session_id'),
            'persona': state.get('persona'),
            'system_prompt': system_prompt,
        }
        message = state.get('message') or ''
        history = state.get('history') or []
        session_id = state.get('session_id')
        transcript = list(state.get('transcript') or [])
        pending = state.get('pending') or {}

        # 恢复计划状态：重建前端 plan 卡片 + 进度计数
        self._plan_steps = state.get('plan_steps')
        self._plan_done = int(state.get('plan_done') or 0)
        if self._plan_steps:
            emit({'event': 'plan', 'turn': 0, 'steps': self._plan_steps,
                  'raw': '', 'restored': True})
            # 已经完成的步骤先打勾
            if self._plan_done > 0:
                emit({'event': 'plan_progress', 'done_count': self._plan_done})

        base_prompt = self._build_base_prompt(message, history, session_id)
        protocol = build_tool_protocol_section(mode=self.mode)

        # 1) 裁决挂起的调用（执行或拒绝），结果并入 transcript
        self._resolve_pending(pending, decision, edits, transcript, emit)

        # 2) 处理同轮剩余调用（可能再次挂起）
        remaining = pending.get('remaining_calls') or []
        if remaining:
            suspended = self._process_turn_calls(remaining, pending.get('turn', 1), transcript, emit)
            if suspended is not None:
                return suspended

        # 3) 续跑后续轮次
        next_turn = (pending.get('turn') or 1) + 1
        return self._run_turns(next_turn, base_prompt, protocol, system_prompt, transcript, emit)

    # ------------------------------------------------------------------
    # 循环主体
    # ------------------------------------------------------------------

    def _run_turns(self, start_turn, base_prompt, protocol, system_prompt, transcript, emit):
        """从 start_turn 开始多轮推理；遇写操作挂起并返回挂起态。

        PR-2：每轮组装 prompt 前估算 token，超阈值时压缩 transcript（加权方法，不调 LLM）；
              每轮推理后 emit token_usage 事件，供前端实时显示与校准。
        """
        message = (self.run_ctx or {}).get('message', '')
        sid = (self.run_ctx or {}).get('session_id')

        for turn in range(start_turn, self.max_turns + 1):
            if self.abort_event.is_set():
                emit({'event': 'aborted', 'message': '任务已中止。', 'session_id': sid})
                return None

            # PR-2：组装 prompt 前先做 token 估算；超阈值则压缩 transcript
            transcript_text = '\n'.join(transcript) if turn > 1 else ''
            estimated = (estimate_tokens(base_prompt) + estimate_tokens(protocol)
                         + estimate_tokens(transcript_text))
            if estimated > COMPACTION_THRESHOLD and len(transcript) > COMPACTION_KEEP_RECENT:
                before = len(transcript)
                before_tokens = estimated
                transcript = compact_transcript(transcript)
                after_tokens = (estimate_tokens(base_prompt) + estimate_tokens(protocol)
                                + estimate_tokens('\n'.join(transcript)))
                emit({'event': 'compaction', 'turn': turn,
                      'before_entries': before, 'after_entries': len(transcript),
                      'before_tokens': before_tokens, 'after_tokens': after_tokens,
                      'threshold': COMPACTION_THRESHOLD, 'budget': TOKEN_BUDGET})
                print(f"[Agent] transcript 触发压缩：{before} → {len(transcript)} 条（约 {before_tokens} → {after_tokens} tokens）")

            prompt = base_prompt + '\n\n' + protocol
            # 如果有计划（plan_steps 非空），每轮都注入当前计划进度上下文
            if self._plan_steps:
                plan_ctx_lines = ['\n\n【你之前制定的执行计划：】']
                for i, step in enumerate(self._plan_steps):
                    mark = '✓' if i < self._plan_done else '○'
                    plan_ctx_lines.append(f'  {mark} {i + 1}. {step}')
                plan_ctx_lines.append(
                    f'\n当前已完成 {self._plan_done}/{len(self._plan_steps)} 步，'
                    f'请对照计划执行下一步；如果计划与实际结果不符，请直接给出最终答复。'
                )
                prompt += '\n'.join(plan_ctx_lines)
            if turn == 1:
                prompt += ('\n\n【任务要求】如果需要借助工具获取信息，请先简短说明思路并输出工具指令；'
                           '如果不需要工具，请直接给出最终答复。')
            else:
                prompt += ('\n\n【此前轮次的工具调用与结果】\n' + '\n'.join(transcript)
                           + '\n\n【任务要求】请继续：需要更多信息则输出新的 /$TOOL: 指令；'
                             '若任务已完成，直接输出给用户的最终答复（不要再输出工具指令）。')

            output = self.backend.generate(prompt, system_msg=system_prompt or None)

            # PR-2：每轮推理后 emit token_usage（前端据此累加并显示用量条）
            emit({'event': 'token_usage', 'turn': turn,
                  'prompt_tokens': estimate_tokens(prompt),
                  'completion_tokens': estimate_tokens(output),
                  'budget': TOKEN_BUDGET,
                  'threshold': COMPACTION_THRESHOLD})

            if self.abort_event.is_set():
                emit({'event': 'aborted', 'message': '任务已中止。', 'session_id': sid})
                return None

            thought, calls = parse_tool_calls(output)
            emit({'event': 'thought', 'turn': turn, 'content': (thought or output or '').strip()[:2000],
                  'session_id': sid})

            if not calls:
                final_text = (output or '').strip() or '（绮罗罗没有返回内容，请重试。）'
                emit({'event': 'final', 'content': final_text, 'session_id': sid})
                self._save_memory(message, final_text)
                return None

            suspended = self._process_turn_calls(calls, turn, transcript, emit)
            if suspended is not None:
                return suspended

        emit({'event': 'max_turns', 'message': f'已达到最大轮数（{self.max_turns}），任务未完成，可尝试拆分任务后重试。',
              'session_id': sid})
        return None

    def _process_turn_calls(self, calls, turn, transcript, emit):
        """顺序处理一轮内的若干调用；遇 write/dangerous 挂起并返回挂起态，否则返回 None。"""
        for i, call in enumerate(calls):
            if self.abort_event.is_set():
                emit({'event': 'aborted', 'message': '任务已中止。'})
                return None
            idx = i + 1
            call_id = f't{turn}c{idx}'
            tool = TOOL_REGISTRY.get(call['tool'])
            risk = tool.risk if tool else 'unknown'
            emit({
                'event': 'tool_call', 'turn': turn, 'call_id': call_id,
                'tool': call['tool'], 'input': call['params'], 'risk': risk,
            })

            # 未知工具：回错并继续后续调用
            if tool is None:
                error_text = f"未知工具 {call['tool']}（可用: {', '.join(TOOL_REGISTRY.keys())}）"
                emit({'event': 'tool_result', 'turn': turn, 'call_id': call_id,
                      'tool': call['tool'], 'ok': False, 'output': '', 'error': error_text})
                transcript.append(f"- {call_id} {call['tool']} 参数 {json.dumps(call['params'], ensure_ascii=False)}\n  结果: 错误: {error_text}")
                continue

            # 未启用工具（如 shell 默认关闭）：fail-closed，回错且不走审批
            tool_enabled = tool.meta().get('enabled', True)
            if call['tool'] == 'shell' and not self.shell_enabled:
                tool_enabled = False
            if not tool_enabled:
                error_text = f"工具 {call['tool']} 当前未启用（请在「模型选择 → Agent 工具」中开启后重试）"
                emit({'event': 'tool_result', 'turn': turn, 'call_id': call_id,
                      'tool': call['tool'], 'ok': False, 'output': '', 'error': error_text})
                transcript.append(f"- {call_id} {call['tool']} 参数 {json.dumps(call['params'], ensure_ascii=False)}\n  结果: 错误: {error_text}")
                continue

            # Chat 模式拦截写/危险级工具（懒调用只给只读）
            if self.mode == 'chat' and risk in ('write', 'dangerous'):
                error_text = f"Chat 模式（懒调用）不支持 {call['tool']}——请切换到 Agent 模式以启用文件写入或 shell 命令。"
                emit({'event': 'tool_result', 'turn': turn, 'call_id': call_id,
                      'tool': call['tool'], 'ok': False, 'output': '', 'error': error_text})
                transcript.append(f"- {call_id} {call['tool']} 参数 {json.dumps(call['params'], ensure_ascii=False)}\n  结果: 错误: {error_text}")
                continue

            # 写/危险级：挂起待审批（仅 Agent 模式可达此处）
            if risk in ('write', 'dangerous'):
                emit({
                    'event': 'approval_required', 'turn': turn, 'call_id': call_id,
                    'tool': call['tool'], 'input': call['params'], 'risk': risk,
                    'reason': _risk_reason(risk, call),
                })
                pending = {
                    'turn': turn, 'call_id': call_id, 'tool': call['tool'],
                    'params': call['params'], 'risk': risk,
                    'reason': _risk_reason(risk, call),
                    'remaining_calls': calls[i + 1:],
                }
                return self._build_pending_state(transcript, pending)

            # 只读级：直接执行
            ok, output_text, error_text = self._exec_tool(tool, call['tool'], call['params'], call_id, emit, turn)
            transcript.append(
                f"- {call_id} {call['tool']} 参数 {json.dumps(call['params'], ensure_ascii=False)}\n"
                f"  结果: {truncate_output(output_text if ok else ('错误: ' + error_text), 2000)}"
            )
        return None

    def _resolve_pending(self, pending, decision, edits, transcript, emit):
        """裁决挂起调用：批准则执行，拒绝则注入拒绝结果；均并入 transcript。"""
        turn = pending.get('turn', 1)
        call_id = pending.get('call_id', f't{turn}c0')
        tool_name = pending.get('tool', '')
        params = dict(pending.get('params') or {})
        tool = TOOL_REGISTRY.get(tool_name)
        risk = pending.get('risk') or (tool.risk if tool else 'unknown')

        # 恢复流自包含：重新声明本轮将裁决的调用
        emit({'event': 'tool_call', 'turn': turn, 'call_id': call_id,
              'tool': tool_name, 'input': params, 'risk': risk})

        if decision == 'approve':
            # 允许用户在审批时微调参数（如改写 content）
            if isinstance(edits, dict) and edits:
                params.update(edits)
            ok, output_text, error_text = self._exec_tool(tool, tool_name, params, call_id, emit, turn)
            transcript.append(
                f"- {call_id} {tool_name} 参数 {json.dumps(params, ensure_ascii=False)}（已批准）\n"
                f"  结果: {truncate_output(output_text if ok else ('错误: ' + error_text), 2000)}"
            )
        else:
            error_text = '用户拒绝了此操作，请改用只读思路或调整方案。'
            emit({'event': 'tool_result', 'turn': turn, 'call_id': call_id,
                  'tool': tool_name, 'ok': False, 'output': '', 'error': error_text})
            transcript.append(
                f"- {call_id} {tool_name} 参数 {json.dumps(params, ensure_ascii=False)}（已被拒绝）\n"
                f"  结果: 用户拒绝执行"
            )

    def _exec_tool(self, tool, tool_name, params, call_id, emit, turn):
        """执行单个只读/已批准工具，发 tool_result，返回 (ok, output_text, error_text)。"""
        ok = True
        output_text = ''
        error_text = ''
        try:
            res = tool.run(params, {
                'workdir': self.workdir,
                'shell_timeout': self.shell_timeout,
                'abort_event': self.abort_event,
            })
            output_text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
        except ToolError as e:
            ok = False
            error_text = str(e)
        except Exception as e:
            ok = False
            error_text = f"{type(e).__name__}: {e}"
        emit({
            'event': 'tool_result', 'turn': turn, 'call_id': call_id,
            'tool': tool_name, 'ok': ok,
            'output': truncate_output(output_text) if ok else '',
            'error': error_text,
        })
        # 计划进度追踪：工具成功执行 +1，前端据此高亮 checklist 完成项
        if ok:
            self._plan_done += 1
            emit({'event': 'plan_progress', 'done_count': self._plan_done, 'last_tool': tool_name})
        return ok, output_text, error_text
