"""每日配额硬闸（Phase 5.4）。

本体强制执行，不进 flow.json 可配置；MOD 无法覆盖。

  - is_quota_ok(flow)   → bool：当天 trigger 次数是否还没超限
  - increment_quota(flow)    → 成功消费一次配额
  - 跨天自动清零（按 YYYY-MM-DD key 自然处理）
  - 全局并发硬闸：同时运行的 flow 总数 ≤ 8
"""

import datetime as dt
import threading


GLOBAL_MAX_CONCURRENT = 8


class QuotaManager(object):
    def __init__(self, logger=None):
        self._logger = logger
        # {flow_id: {"2026-10-27": count}}
        self._daily = {}
        # 当前运行中的 flow 数（engine 调 _run_flow 时 increment，finally decrement）
        self._running = 0
        self._lock = threading.Lock()

    def is_quota_ok(self, flow):
        flow_id = flow.get("id", "")
        limit = (flow.get("policy") or {}).get("daily_quota", 10)
        today = dt.date.today().isoformat()

        with self._lock:
            count = self._daily.get(flow_id, {}).get(today, 0)
            return count < limit

    def increment_quota(self, flow):
        flow_id = flow.get("id", "")
        today = dt.date.today().isoformat()

        with self._lock:
            self._daily.setdefault(flow_id, {})[today] = \
                self._daily.get(flow_id, {}).get(today, 0) + 1

    def daily_count(self, flow_id):
        today = dt.date.today().isoformat()
        return self._daily.get(flow_id, {}).get(today, 0)

    def is_global_concurrency_ok(self):
        with self._lock:
            return self._running < GLOBAL_MAX_CONCURRENT

    def enter_global(self):
        with self._lock:
            if self._running >= GLOBAL_MAX_CONCURRENT:
                return False
            self._running += 1
            return True

    def exit_global(self):
        with self._lock:
            if self._running > 0:
                self._running -= 1

    # 清理过期日期（Phase 5 不主动跑，留给重启或手动清理）
    def cleanup_old_dates(self, days_to_keep=30):
        cutoff = (dt.date.today() - dt.timedelta(days=days_to_keep)).isoformat()
        with self._lock:
            for flow_id in list(self._daily.keys()):
                dates = self._daily[flow_id]
                self._daily[flow_id] = {d: c for d, c in dates.items() if d >= cutoff}
                if not self._daily[flow_id]:
                    del self._daily[flow_id]
