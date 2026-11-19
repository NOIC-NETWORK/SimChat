"""Automation 引擎本体（Phase 5 交付）。

版本演进：
  - Phase 5.1：空壳 + register_flow + 全局 getter
  - Phase 5.2：Cron/Event/Manual 调度器 + start/stop + trigger_manual
  - Phase 5.3：executor 集成（skill:xxx / agent:run / file:* + 变量插值）
  - Phase 5.4：quota + approval + audit 全部集成

设计约束：
  - 零 import 循环：engine 不 import lifecycle / ModLoader；宿主启动时通过
    bind_runtime() 注入 chat_stream；能力调用统一经方块注册表（executor → invoke_block），
    不再保留 loader.call_tool() 旁路
  - 全局 getter 模式：get_engine() 让 lifecycle 的 automation 分支能拿到
    引擎实例，不需要 lifecycle import automation 包
  - 装备判定：flow 自身的 skill: 步骤声明是显式范围；Agent 触发时与该实例的
    equipped 取交集；cron/event/manual 没有实例上下文，只允许声明过的方块
"""

import datetime
import logging
import os
import threading
import time


_GLOBAL_ENGINE = None


def set_global_engine(engine):
    """宿主启动时调用一次，类似 Phase 2 set_global_loader 范式。"""
    global _GLOBAL_ENGINE
    _GLOBAL_ENGINE = engine


def get_engine():
    """全局 getter；尚未初始化则返回 None。"""
    return _GLOBAL_ENGINE


class AutomationEngine(object):
    """本体级自动化引擎单例。"""

    # ---------- Phase 5.1/5.2 ----------

    def __init__(self, data_dir, host_version="2.1.0", quota=None, approval=None, audit_log=None, logger=None):
        self.data_dir = data_dir
        self.host_version = host_version
        self._logger = logger or logging.getLogger("simchat.automation")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[SimChat.Automation] %(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

        # 已注册的 flow：{mod_id: {"flow": dict, "trigger": Trigger}}
        self._flows = {}

        # 最近运行记录（内存环形，供 automation 工具读取实时状态）
        self._recent_runs = []
        self._recent_runs_limit = 20

        # Phase 5.4 新增：三大运行时管理器
        from .quota import QuotaManager
        from .approval import ApprovalManager
        from .audit import AuditLogger
        self._quota = quota or QuotaManager(logger=self._logger)
        self._approval = approval or ApprovalManager(logger=self._logger)
        audit_dir = audit_log or os.path.join(self.data_dir, "audit")
        self._audit = AuditLogger(audit_dir, logger=self._logger)

        # Phase 5.3+ 填充（依赖注入）
        self._loader = None
        self._chat_stream = None
        self._running = False

        # 调度器状态
        self._scheduler_thread = None
        self._stop_event = threading.Event()

    # ---------- 依赖注入（宿主启动时调用） ----------

    def bind_loader(self, loader):
        """兼容启动流程保留的绑定；能力调用不再走 loader.call_tool() 旁路。"""
        self._loader = loader
        self._logger.info("已绑定 ModLoader（能力执行统一走方块注册表）")

    def bind_runtime(self, core):
        self._chat_stream = core.chat_stream if core else None
        self._logger.info("已绑定 SimChatCore（chat_stream）")

    # ---------- MOD 注册（lifecycle automation 分支调用） ----------

    def register_flow(self, mod_id, flow):
        from .scheduler import CronTrigger, EventTrigger, ManualTrigger

        trigger = None
        t = (flow.get("trigger") or {}).get("type")
        try:
            if t == "cron":
                trigger = CronTrigger(flow["trigger"]["expr"])
            elif t == "event":
                trigger = EventTrigger(flow["trigger"]["event"])
            elif t == "manual":
                trigger = ManualTrigger(flow["trigger"].get("manual_token", ""))
            else:
                self._logger.error("未知 trigger.type: %s", t)
                return
        except Exception as e:
            self._logger.error("创建 trigger 失败 [%s]: %s", mod_id, e)
            return

        self._flows[mod_id] = {
            "mod_id": mod_id,
            "flow": flow,
            "trigger": trigger,
        }
        self._logger.info("已注册 flow: %s (from MOD %s, trigger=%s)",
                          flow.get("id"), mod_id, trigger.kind())

    def unregister_flow(self, mod_id):
        if mod_id in self._flows:
            del self._flows[mod_id]
            self._logger.info("已注销 flow: %s", mod_id)

    def list_flows(self):
        result = []
        for mod_id, info in self._flows.items():
            flow = info["flow"]
            trigger = info["trigger"]
            next_run = None
            if trigger.kind() == "cron":
                try:
                    next_run = trigger.next_run()
                    next_run = next_run.isoformat() if next_run else None
                except Exception:
                    pass
            result.append({
                "mod_id": mod_id,
                "flow_id": flow.get("id"),
                "trigger_type": trigger.kind(),
                "next_run": next_run,
            })
        return result

    # ---------- 调度器生命周期（Phase 5.2） ----------

    def start(self):
        if self._running:
            self._logger.warning("Engine 已在运行")
            return
        self._stop_event.clear()
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, name="simchat-automation", daemon=True
        )
        self._scheduler_thread.start()
        self._logger.info("AutomationEngine 已启动（%d 个 flow）", len(self._flows))

    def stop(self):
        self._stop_event.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=10)
        self._running = False
        self._logger.info("AutomationEngine 已停止")

    def _scheduler_loop(self):
        """每秒轮询所有 CronTrigger，触发到期 flow。

        Phase 5.2 阶段 step 执行先返回 mock 结果（无 executor）。
        Phase 5.3 起走 executor.execute_flow()。
        """
        import datetime as dt
        last_minute = None

        while not self._stop_event.is_set():
            try:
                now = dt.datetime.now()

                # 每分钟（精确到秒）检查一次 cron 触发
                if now.second == 0 or last_minute is None or now.minute != last_minute:
                    for mod_id, info in list(self._flows.items()):
                        trigger = info["trigger"]
                        if trigger.kind() == "cron" and trigger.is_due(now):
                            self._logger.info("[cron] flow %s 触发", info["flow"].get("id"))
                            self._run_flow(mod_id, triggered_by="cron")
                    last_minute = now.minute

                # 检查 EventTrigger / ManualTrigger 是否被设为 pending
                for mod_id, info in list(self._flows.items()):
                    trigger = info["trigger"]
                    if trigger.kind() in ("event", "manual") and trigger.is_due(now):
                        self._logger.info("[%s] flow %s 触发", trigger.kind(), info["flow"].get("id"))
                        self._run_flow(mod_id, triggered_by=trigger.kind())

                # 睡眠直到下一秒
                time.sleep(1)
            except Exception as e:
                self._logger.error("scheduler loop 异常: %s", e)
                time.sleep(1)

    def _run_flow(self, mod_id, triggered_by="manual", allowed=None):
        """执行一个 flow（调度器触发的统一入口）。

        Phase 5.4 集成：quota 硬闸 + audit。
        Phase 5.5 demo 时 approval 通道也走这里。
        allowed: 调用方（如 Agent 实例）的装备集合；None 表示无实例上下文，
        由 executor 回落到 flow 自身的 skill: 声明范围。
        """
        from .executor import execute_flow
        import time as _time

        info = self._flows.get(mod_id)
        if info is None:
            return {"ok": False, "error": "flow 未注册: %s" % mod_id}
        flow = info["flow"]
        flow_id = flow.get("id")

        # Phase 5.4 — 全局并发硬闸
        if not self._quota.enter_global():
            self._logger.warning("[%s] flow %s 跳过：全局并发已达上限 (%d)",
                                 triggered_by, flow_id, 8)
            return self._record_run({
                "ok": False, "flow_id": flow_id, "mod_id": mod_id,
                "triggered_by": triggered_by, "status": "global_busy",
                "error": "全局并发已达上限",
            })

        started = _time.time()
        try:
            # Phase 5.4 — 每日配额硬闸
            if not self._quota.is_quota_ok(flow):
                self._logger.warning("[%s] flow %s 跳过：当日配额已达上限 (%d)",
                                     triggered_by, flow_id,
                                     (flow.get("policy") or {}).get("daily_quota", 10))
                run_id = "run-%d-%s" % (int(_time.time() * 1000) % 100000, mod_id)
                self._audit.start_run(flow, mod_id, run_id, triggered_by=triggered_by)
                self._audit.finish_run(run_id, "quota_skipped")
                return self._record_run({
                    "ok": False, "run_id": run_id, "flow_id": flow_id, "mod_id": mod_id,
                    "triggered_by": triggered_by, "status": "quota_skipped",
                    "error": "当日配额已达上限",
                })
            self._quota.increment_quota(flow)

            run_id = "run-%d-%s" % (int(_time.time() * 1000) % 100000, mod_id)
            self._logger.info("[%s] flow %s run_id=%s 开始执行", triggered_by, flow_id, run_id)

            try:
                results = execute_flow(flow, mod_id, context_init={
                    "env": self._build_env(),
                    "run_id": run_id,
                    "triggered_by": triggered_by,
                    "allowed": allowed,
                }, engine=self)

                total = len(results)
                completed = sum(1 for r in results.values() if r["status"] == "completed")
                self._logger.info("[%s] flow %s 执行结束: %d/%d 完成", triggered_by, flow_id, completed, total)

                for sid, r in results.items():
                    preview = ""
                    if r.get("output"):
                        text = str(r["output"])
                        preview = " (%s...)" % text[:80] if len(text) > 80 else " (%s)" % text
                    self._logger.info("  step %s → %s%s", sid, r["status"], preview)

                summary = {
                    "ok": completed == total,
                    "run_id": run_id, "flow_id": flow_id, "mod_id": mod_id,
                    "triggered_by": triggered_by,
                    "status": "completed" if completed == total else "partial",
                    "steps": [{"id": sid, "status": r["status"]} for sid, r in results.items()],
                }

            except Exception as e:
                self._logger.error("[%s] flow %s 执行异常: %s", triggered_by, flow_id, e)
                summary = {
                    "ok": False, "run_id": run_id, "flow_id": flow_id, "mod_id": mod_id,
                    "triggered_by": triggered_by, "status": "error", "error": str(e),
                }

            summary["duration_ms"] = int((_time.time() - started) * 1000)
            return self._record_run(summary)

        finally:
            self._quota.exit_global()

    def _record_run(self, summary):
        """把一次运行摘要放进内存环形表，供 automation 工具查询实时状态。"""
        self._recent_runs.append(summary)
        overflow = len(self._recent_runs) - self._recent_runs_limit
        if overflow > 0:
            del self._recent_runs[:overflow]
        return summary

    def _build_env(self):
        """构建注入 flow 的环境变量（Phase 5.3）。"""
        import os as _os
        env = {}
        for key in ("WORKSPACE", "HOME", "USERPROFILE", "TEMP", "TMP"):
            val = _os.environ.get(key)
            if val:
                env[key] = val
        # 附加引擎自身路径
        if self.data_dir:
            env["SIMCHAT_DATA"] = self.data_dir
        return env

    # ---------- 手动/事件触发 API（Phase 5.2） ----------

    def trigger_manual(self, mod_id, token):
        """手动触发一个 manual 类型的 flow（需匹配 manual_token）。"""
        info = self._flows.get(mod_id)
        if info is None:
            return {"ok": False, "error": "flow 未注册: %s" % mod_id}

        trigger = info["trigger"]
        if trigger.kind() != "manual":
            return {"ok": False, "error": "flow %s 不是 manual 类型（trigger=%s）" % (mod_id, trigger.kind())}
        if trigger.token != token:
            return {"ok": False, "error": "token 不匹配"}

        trigger.fire()
        self._run_flow(mod_id, triggered_by="manual")
        return {"ok": True, "run_id": "run-%d" % int(time.time())}

    def trigger_flow(self, flow_id, triggered_by="tool", allowed=None):
        """按 flow id 触发一次执行（宿主工具调用；审批由调用方保证）。

        allowed 由调用方传入自己的装备集合；None 表示无实例上下文，
        flow 只能调用自己声明过的 skill: 方块。
        """
        for mod_id, info in self._flows.items():
            if info["flow"].get("id") == flow_id:
                return self._run_flow(mod_id, triggered_by=triggered_by, allowed=allowed)
        available = [str(info["flow"].get("id")) for info in self._flows.values()]
        return {"ok": False,
                "error": "flow 不存在: %s（可用: %s）" % (flow_id, ", ".join(available) or "无")}

    def list_runs(self, limit=10):
        """最近的运行记录（新的在前），供 automation 工具读取实时状态。"""
        limit = max(1, int(limit or 10))
        return list(reversed(self._recent_runs[-limit:]))

    # ---------- Phase 5.4 — 审批 API（宿主侧调用） ----------

    def approve(self, run_id, step_id):
        """批准一个等待审批的 step。"""
        ok, msg = self._approval.resolve(run_id, step_id, approve=True)
        if ok:
            self._logger.info("审批: run=%s step=%s → APPROVED", run_id, step_id)
        return ok, msg

    def reject(self, run_id, step_id, reason=None):
        """拒绝一个等待审批的 step。"""
        ok, msg = self._approval.resolve(run_id, step_id, approve=False, reason=reason)
        if ok:
            self._logger.info("审批: run=%s step=%s → REJECTED (reason=%s)", run_id, step_id, reason)
        return ok, msg

    def list_pending_approvals(self):
        return self._approval.list_pending()

    def on_event(self, event_type, payload=None):
        """事件触发钩子——本体收到 agent.completed / file.changed 等事件时调用。

        Phase 5.2 实现：把所有匹配 event_type 的 EventTrigger 设为 pending。
        Phase 6 才真正接本体事件（Phase 5 只暴露接口）。
        """
        count = 0
        for mod_id, info in self._flows.items():
            trigger = info["trigger"]
            if trigger.kind() == "event" and trigger.event_type == event_type:
                trigger.fire()
                count += 1
        if count:
            self._logger.info("[event:%s] 触发 %d 个 flow", event_type, count)
