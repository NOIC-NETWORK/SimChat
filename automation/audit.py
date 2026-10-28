"""审计日志写盘（Phase 5.4）。

存储：simchat/data/audit/<flow_id>/<run_id>.json
目录自动创建；按 flow_id 分片；Phase 5 不做过期清理。

Run 状态：completed | failed | timeout | quota_skipped | manually_stopped
Step 状态：pending | approval_requested | approved | rejected | running | completed | failed | timeout | skipped
"""

import datetime as dt
import hashlib
import json
import os
import threading


def _now_iso():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(obj):
    """算 sha256 哈希，用于 input_hash / output_hash 字段。"""
    if obj is None:
        return None
    try:
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str) \
            if isinstance(obj, (dict, list)) else str(obj)
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception:
        return None


class AuditLogger(object):
    def __init__(self, audit_dir, logger=None):
        self.audit_dir = os.path.abspath(audit_dir)
        self._logger = logger
        # 当前正在写的 run：{run_id: {"path": str, "data": dict}}
        self._active = {}
        self._lock = threading.RLock()  # 可重入——append_step 内部调 _flush 会再次进入

    # ---------- Run 生命周期 ----------

    def start_run(self, flow, mod_id, run_id, triggered_by="manual"):
        flow_id = flow.get("id", "unknown")
        run_dir = os.path.join(self.audit_dir, flow_id)
        os.makedirs(run_dir, exist_ok=True)
        run_path = os.path.join(run_dir, run_id + ".json")

        run_data = {
            "flow_id": flow_id,
            "mod_id": mod_id,
            "run_id": run_id,
            "trigger": flow.get("trigger", {}),
            "triggered_by": triggered_by,
            "started_at": _now_iso(),
            "finished_at": None,
            "status": "running",
            "steps": [],
        }
        with self._lock:
            self._active[run_id] = {"path": run_path, "data": run_data}
        self._flush(run_id)
        if self._logger:
            self._logger.info("审计 start_run: %s → %s", run_id, run_path)
        return run_path

    def append_step(self, run_id, step_id, status, use=None, args=None,
                    output=None, error=None, duration_ms=None):
        with self._lock:
            active = self._active.get(run_id)
            if active is None:
                return
            step_rec = {
                "step_id": step_id,
                "status": status,
                "started_at": None,
                "finished_at": _now_iso(),
                "duration_ms": duration_ms,
                "use": use,
                "args": args if isinstance(args, dict) else str(args) if args else None,
                "input_hash": _hash(args),
                "output_hash": _hash(output),
                "output_preview": self._preview(output),
                "error_message": error,
            }
            # 如果已存在同 step_id → 覆盖（状态流转更新）
            steps = active["data"]["steps"]
            for i, existing in enumerate(steps):
                if existing.get("step_id") == step_id:
                    steps[i] = step_rec
                    break
            else:
                steps.append(step_rec)
        self._flush(run_id)

    def finish_run(self, run_id, status, extra=None):
        with self._lock:
            active = self._active.get(run_id)
            if active is None:
                return
            active["data"]["status"] = status
            active["data"]["finished_at"] = _now_iso()
            if extra:
                active["data"].update(extra)
            # 先 flush 再移除，确保写盘
            self._flush(run_id)
            self._active.pop(run_id, None)
        if self._logger:
            self._logger.info("审计 finish_run: %s → %s", run_id, status)

    # ---------- 内部 ----------

    def _flush(self, run_id):
        with self._lock:
            active = self._active.get(run_id)
            if active is None:
                return
            try:
                with open(active["path"], "w", encoding="utf-8") as f:
                    json.dump(active["data"], f, ensure_ascii=False, indent=2)
            except Exception as e:
                if self._logger:
                    self._logger.error("审计写盘失败 %s: %s", active["path"], e)

    @staticmethod
    def _preview(output, max_len=200):
        if output is None:
            return None
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."
