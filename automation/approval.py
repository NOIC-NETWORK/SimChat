"""审批状态机（Phase 5.4）。

状态流转：
  PENDING → APPROVAL_REQUESTED → APPROVED / REJECTED / TIMEOUT
  有人批准 → APPROVED → 继续执行
  超时或有人拒绝 → REJECTED → 终止

同步阻塞模型：executor 是同步函数，await_approval() 用 threading.Event.wait(timeout)
阻塞在 cron daemon 线程里（不阻塞 Flask 主线程）。宿主收到审批请求后调
engine.approve() / engine.reject() → 内部 approval_event.set() → executor 线程被唤醒继续。
"""

import threading
import time


# 审批结果常量
APPROVED = "approved"
REJECTED = "rejected"
TIMEOUT = "timeout"


class ApprovalTicket(object):
    """一张等待审批的票据。"""
    def __init__(self, run_id, step_id, timeout_s=300):
        self.run_id = run_id
        self.step_id = step_id
        self.timeout_s = timeout_s
        self.event = threading.Event()
        self.result = None  # APPROVED / REJECTED / TIMEOUT
        self.reason = None

    def approve(self):
        self.result = APPROVED
        self.event.set()

    def reject(self, reason=None):
        self.result = REJECTED
        self.reason = reason or "手动拒绝"
        self.event.set()

    def wait(self):
        """阻塞等待审批结果。返回 APPROVED / REJECTED / TIMEOUT。"""
        if self.event.wait(timeout=self.timeout_s):
            return self.result
        self.result = TIMEOUT
        return TIMEOUT


class ApprovalManager(object):
    def __init__(self, logger=None):
        self._logger = logger
        # {(run_id, step_id): ApprovalTicket}
        self._tickets = {}
        self._lock = threading.Lock()

    def request(self, run_id, step_id, timeout_s=300):
        """发起一个审批请求，返回 ApprovalTicket。executor 调 ticket.wait()。"""
        key = (run_id, step_id)
        with self._lock:
            ticket = ApprovalTicket(run_id, step_id, timeout_s=timeout_s)
            self._tickets[key] = ticket
        if self._logger:
            self._logger.info("审批请求: run=%s step=%s timeout=%ds", run_id, step_id, timeout_s)
        return ticket

    def resolve(self, run_id, step_id, approve=True, reason=None):
        """宿主侧（或测试脚本）调这个来批准或拒绝。"""
        key = (run_id, step_id)
        with self._lock:
            ticket = self._tickets.pop(key, None)
        if ticket is None:
            return False, "票据不存在: %s/%s" % (run_id, step_id)
        if approve:
            ticket.approve()
        else:
            ticket.reject(reason)
        return True, ticket.result

    def _cleanup_timeout(self, run_id, step_id):
        """票据超时后从 _tickets 移除。"""
        key = (run_id, step_id)
        with self._lock:
            self._tickets.pop(key, None)

    def pending_count(self):
        with self._lock:
            return len(self._tickets)

    def list_pending(self):
        with self._lock:
            return [{"run_id": k[0], "step_id": k[1]} for k in self._tickets]
