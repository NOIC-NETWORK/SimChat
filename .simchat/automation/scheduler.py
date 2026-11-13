"""调度器（Phase 5.2）。

自写五段 cron 解析器（零依赖、≈150 行），支持四种通配符：
  - *        所有可能值
  - */N      间隔（every N）
  - 1,15,30  逗号列表
  - 1-5      范围
  - 1-10/2   范围 + 间隔

不支持：字母 (JAN/MON)、L/W/# 特殊符号。
"""

import datetime
import re
import threading
import time


# ---------------------------------------------------------------------------
# Cron 解析器
# ---------------------------------------------------------------------------

# 每个字段的合法范围
_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week  (0=Sun, 6=Sat)
]


def _parse_field(token, lo, hi):
    """解析单个 cron 字段，返回 sorted list of 合法值。"""
    result = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            raise ValueError("空字段片段")

        # */N 或 start-end/N
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step < 1:
                raise ValueError("step 必须 >= 1")
        else:
            base = part

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start = int(a)
            end = int(b)
            if start < lo or end > hi or start > end:
                raise ValueError("范围 %s 越界 [%d,%d]" % (base, lo, hi))
        else:
            val = int(base)
            if val < lo or val > hi:
                raise ValueError("值 %d 越界 [%d,%d]" % (val, lo, hi))
            start = end = val

        for v in range(start, end + 1, step):
            result.add(v)

    return sorted(result)


def parse_cron(expr):
    """解析五段 cron 表达式 → (minutes, hours, doms, months, dows) 五个 set。

    失败抛 ValueError。
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError("cron 必须是五段表达式，得到 %d 段" % len(parts))

    fields = []
    for token, (lo, hi) in zip(parts, _FIELD_RANGES):
        fields.append(_parse_field(token, lo, hi))

    return tuple(fields)  # (minutes, hours, doms, months, dows)


def _day_matches(cron_doms, cron_dows, year, month, day):
    """cron 的 day 语义：dom 和 dow 是 OR 关系（经典 cron 行为）。

    * 展开后不应该参与 OR——它代表"不限制"，dom_hit 独立决定。
    正确逻辑：dom/dow 各自判断；两者都被限制时 AND，否则取被限制的那个。
    """
    import calendar
    weekday = calendar.weekday(year, month, day)  # 0=Mon
    cron_weekday = (weekday + 1) % 7  # 转 cron 语义 0=Sun, 6=Sat

    dom_any = len(cron_doms) == (_FIELD_RANGES[2][1] - _FIELD_RANGES[2][0] + 1)
    dow_any = len(cron_dows) == (_FIELD_RANGES[4][1] - _FIELD_RANGES[4][0] + 1)

    if dom_any and dow_any:
        return True
    if dom_any:
        return cron_weekday in cron_dows
    if dow_any:
        return day in cron_doms
    # 两者都有限制 → AND
    return (day in cron_doms) and (cron_weekday in cron_dows)


def cron_next_run(parsed, from_dt):
    """给解析好的 cron + 起始 datetime，找下一个匹配时刻。最多跳 4 年防死循环。"""
    minutes, hours, doms, months, dows = parsed
    candidate = from_dt.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    max_iter = 366 * 24 * 60 * 4  # 4 年的分钟数
    for _ in range(max_iter):
        if candidate.month not in months:
            # 跳到下月一号
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                candidate = candidate.replace(month=candidate.month + 1, day=1, hour=0, minute=0)
            continue

        if not _day_matches(doms, dows, candidate.year, candidate.month, candidate.day):
            candidate += datetime.timedelta(days=1)
            candidate = candidate.replace(hour=0, minute=0)
            continue

        if candidate.hour not in hours:
            candidate += datetime.timedelta(hours=1)
            candidate = candidate.replace(minute=0)
            continue

        if candidate.minute not in minutes:
            candidate += datetime.timedelta(minutes=1)
            continue

        return candidate

    return None  # 4 年内没找到（不应该发生——* 通配符肯定能覆盖）


def cron_is_due(parsed, now):
    """判断给定 datetime 是否匹配 cron（分钟级精度）。"""
    minutes, hours, doms, months, dows = parsed
    return (now.minute in minutes
            and now.hour in hours
            and _day_matches(doms, dows, now.year, now.month, now.day)
            and now.month in months)


# ---------------------------------------------------------------------------
# Trigger 抽象
# ---------------------------------------------------------------------------

class Trigger(object):
    def is_due(self, now):
        raise NotImplementedError
    def next_run(self):
        return None
    def kind(self):
        raise NotImplementedError


class CronTrigger(Trigger):
    def __init__(self, expr):
        self.expr = expr
        self._parsed = parse_cron(expr)  # 构造时即校验，失败抛 ValueError

    def is_due(self, now):
        return cron_is_due(self._parsed, now)

    def next_run(self, from_dt=None):
        if from_dt is None:
            from_dt = datetime.datetime.now()
        return cron_next_run(self._parsed, from_dt)

    def kind(self):
        return "cron"


class EventTrigger(Trigger):
    """默认不 due，on_event() 被调用时触发一次。

    节流：每次触发后需要本体再次 on_event() 才会 due。
    """
    def __init__(self, event_type):
        self.event_type = event_type
        self._pending = False
        self._lock = threading.Lock()

    def is_due(self, now):
        with self._lock:
            if self._pending:
                self._pending = False
                return True
            return False

    def fire(self):
        """本体收到事件时调用，设 pending=True。"""
        with self._lock:
            self._pending = True

    def kind(self):
        return "event"


class ManualTrigger(Trigger):
    """永远不 due（cron loop 里它不会被触发）；
    trigger_manual() 强制触发一次。
    """
    def __init__(self, token):
        self.token = token
        self._pending = False
        self._lock = threading.Lock()

    def is_due(self, now):
        with self._lock:
            if self._pending:
                self._pending = False
                return True
            return False

    def fire(self):
        with self._lock:
            self._pending = True

    def kind(self):
        return "manual"
