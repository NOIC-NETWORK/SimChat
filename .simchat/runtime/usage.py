"""SimChat 后端每日 token 用量追踪 + 额度限制硬闸。

从 kirara 前端 localStorage 版的额度限制迁移过来，做后端硬闸：
  - 每日用量存到 data_root/usage.json
  - quota 配置读自 settings.json 的 quota 段
  - check_quota() → 对话/Agent 入口调用，超限时返回超限原因
  - record_usage() → 对话/Agent 结束后累加用量

与 automation/quota.py 区分：
  - automation/quota.py：控制 automation DAG flow 的 trigger 次数
  - runtime/usage.py：控制对话/Agent 的 token 总量
"""

import datetime as dt
import json
import os
import threading

from . import settings as settings_mod


class UsageTracker:
    """每日 token 用量追踪器（线程安全，文件持久化）。"""

    def __init__(self, data_root):
        self.data_root = data_root
        self.path = os.path.join(data_root, "usage.json")
        self._lock = threading.Lock()
        self._cache = None  # 懒加载缓存

    # ---------------- 持久化 ----------------

    def _load(self):
        """加载 usage.json；文件不存在或损坏返回空 dict。"""
        if self._cache is not None:
            return self._cache
        with self._lock:
            if self._cache is not None:
                return self._cache
            try:
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        data = {}
                else:
                    data = {}
            except Exception:
                data = {}
            self._cache = data
            return data

    def _save(self, data):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
                self._cache = data
            except Exception:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

    # ---------------- 读取 ----------------

    def _today_key(self):
        return dt.date.today().isoformat()

    def today_usage(self):
        """返回今日用量 dict：{input_tokens, output_tokens, total_tokens, exchanges}。"""
        data = self._load()
        rec = data.get(self._today_key()) or {}
        input_tok = rec.get("input_tokens", 0)
        output_tok = rec.get("output_tokens", 0)
        return {
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "total_tokens": input_tok + output_tok,
            "exchanges": rec.get("exchanges", 0),
        }

    def recent_usage(self, days=7):
        """返回最近 N 天的有序列表 [{date, input_tokens, output_tokens, total_tokens, exchanges}]。"""
        data = self._load()
        today = dt.date.today()
        result = []
        for i in range(days - 1, -1, -1):
            d = today - dt.timedelta(days=i)
            key = d.isoformat()
            rec = data.get(key) or {}
            input_tok = rec.get("input_tokens", 0)
            output_tok = rec.get("output_tokens", 0)
            result.append({
                "date": key,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "total_tokens": input_tok + output_tok,
                "exchanges": rec.get("exchanges", 0),
            })
        return result

    # ---------------- 写入 ----------------

    def record(self, input_tokens=0, output_tokens=0):
        """累加今日用量（输入/输出都是非负整数）。"""
        input_tokens = max(0, int(input_tokens or 0))
        output_tokens = max(0, int(output_tokens or 0))
        if input_tokens == 0 and output_tokens == 0:
            return
        data = self._load()
        key = self._today_key()
        rec = data.get(key) or {
            "input_tokens": 0,
            "output_tokens": 0,
            "exchanges": 0,
        }
        rec["input_tokens"] = rec.get("input_tokens", 0) + input_tokens
        rec["output_tokens"] = rec.get("output_tokens", 0) + output_tokens
        rec["exchanges"] = rec.get("exchanges", 0) + 1
        data[key] = rec
        self._save(data)

    # ---------------- 配额检查 ----------------

    def check_quota(self, data_root):
        """检查是否已达今日额度上限。

        返回 (ok: bool, reason: str|None, usage: dict, quota_cfg: dict)。
        quota_cfg 来自 settings.json：{limit, period, lock}
        """
        try:
            cfg = settings_mod.load(data_root)
        except Exception:
            cfg = settings_mod.defaults()
        quota = cfg.get("quota") or {}
        limit = int(quota.get("limit", 0))
        period = quota.get("period", "day")

        # limit=0 表示不限额
        if limit <= 0:
            return True, None, self.today_usage(), {"limit": 0, "period": period}

        usage = self.today_usage()
        if usage["total_tokens"] >= limit:
            reason = "今日 token 用量已达上限（%d / %d），可在「设置 → 用量限制」中关闭或调整上限" % (
                usage["total_tokens"], limit)
            return False, reason, usage, {"limit": limit, "period": period}

        return True, None, usage, {"limit": limit, "period": period}

    # ---------------- 清理 ----------------

    def cleanup(self, days_to_keep=30):
        """清理超过 N 天的历史数据。"""
        cutoff = (dt.date.today() - dt.timedelta(days=days_to_keep)).isoformat()
        data = self._load()
        pruned = {k: v for k, v in data.items() if k >= cutoff}
        self._save(pruned)

    def reset_today(self):
        """手动清零今日记录（主要用于测试）。"""
        data = self._load()
        key = self._today_key()
        if key in data:
            del data[key]
        self._save(data)
