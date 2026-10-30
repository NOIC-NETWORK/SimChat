# -*- coding: utf-8 -*-
"""Agent 运行登记表与挂起态持久化（Phase 2 审批流）。

- 内存态：活跃运行的 abort 事件与状态登记（进程重启即失效）。
- 持久态：审批挂起运行落盘到 data/agent_runs/{run_id}.json，
  带 TTL；过期或重启后拒绝恢复（fail-closed）。
- run_id：审批恢复时复用原 run_id，并重新登记内存条目（新建 abort 事件）。
"""
import json
import os
import threading
import time
import uuid

# 挂起态目录：simchat/data/agent_runs/
_AGENT_RUNS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'agent_runs')
)

# 默认 TTL（秒）；可被 config.json 的 agent.approval_ttl 覆盖
DEFAULT_APPROVAL_TTL = 600


def _state_path(run_id):
    return os.path.join(_AGENT_RUNS_DIR, f'{run_id}.json')


class AgentRunRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._runs = {}

    def create(self):
        run_id = uuid.uuid4().hex
        with self._lock:
            self._runs[run_id] = {
                'created': time.time(),
                'status': 'running',
                'abort': threading.Event(),
            }
        return run_id

    def register(self, run_id):
        """为恢复运行复用已有 run_id 并新建 abort 事件（审批恢复路径）。"""
        with self._lock:
            self._runs[run_id] = {
                'created': time.time(),
                'status': 'running',
                'abort': threading.Event(),
            }
        return run_id

    def get(self, run_id):
        with self._lock:
            return self._runs.get(run_id)

    def abort(self, run_id):
        with self._lock:
            run = self._runs.get(run_id)
        if run:
            run['abort'].set()
            run['status'] = 'aborted'

    def finish(self, run_id, status='finished'):
        with self._lock:
            run = self._runs.get(run_id)
        if run:
            run['status'] = status

    def remove(self, run_id):
        with self._lock:
            self._runs.pop(run_id, None)


# 挂起态落盘 / 加载 / 清理 -------------------------------------------------

def _ensure_dir():
    try:
        os.makedirs(_AGENT_RUNS_DIR, exist_ok=True)
    except OSError:
        pass


def save_pending_state(state, ttl=DEFAULT_APPROVAL_TTL):
    """把挂起运行的完整上下文落盘，供审批恢复时重建循环。"""
    _ensure_dir()
    if 'created' not in state:
        state['created'] = time.time()
    state['ttl'] = int(ttl)
    state['expires_at'] = state['created'] + int(ttl)
    path = _state_path(state['run_id'])
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, path)  # 原子写
        return True
    except OSError as e:
        print(f"[Agent] 挂起态落盘失败: {e}")
        return False


def load_pending_state(run_id, ttl=DEFAULT_APPROVAL_TTL):
    """加载挂起态；不存在/过期/损坏均返回 None（fail-closed）。"""
    path = _state_path(run_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[Agent] 挂起态读取失败（已忽略）: {e}")
        return None
    if not isinstance(state, dict):
        return None
    created = float(state.get('created') or 0)
    effective_ttl = int(state.get('ttl') or ttl)
    if time.time() - created > effective_ttl:
        print(f"[Agent] 挂起态已过期（run_id={run_id}），拒绝恢复")
        discard_pending_state(run_id)
        return None
    return state


def discard_pending_state(run_id):
    """清理挂起态文件（任务结束/中止/过期时调用）。"""
    path = _state_path(run_id)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError as e:
        print(f"[Agent] 清理挂起态失败: {e}")


def list_pending_states():
    """列出当前挂起的 run_id（供诊断/清理；不暴露给前端）。"""
    _ensure_dir()
    out = []
    try:
        for name in os.listdir(_AGENT_RUNS_DIR):
            if not name.endswith('.json'):
                continue
            run_id = name[:-5]
            out.append(run_id)
    except OSError:
        pass
    return out


# 进程内单例：Web 蓝图直接使用
agent_runs = AgentRunRegistry()
