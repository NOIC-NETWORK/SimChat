# Phase 5 施工方案：Automation 引擎

> 本文档是 [simchat-separation-plan.md §9 Phase 5](simchat-separation-plan.md#L391-L393) 的完整设计——造一个从零的 Automation 引擎，填补平台的最后一块运行时能力。
> 决策池见 [simchat-open-decisions-pool.md](./simchat-open-decisions-pool.md)。

## 进度总览

| 切片 | 状态 | Commit | 关键交付 |
|---|---|---|---|
| P5.1 DAG 解析器 + 静态校验 | ✅ 已交付 | — | `simchat/automation/flow.py` + 正式 `flow.schema.json`；lifecycle automation 分支；VERSION 0.5.0 |
| P5.2 调度器 + cron | ✅ 已交付 | — | `simchat/automation/scheduler.py`（自写五段 cron 9/9 fixture）+ `CronTrigger` / `EventTrigger` / `ManualTrigger` + daemon 线程不阻塞 Flask |
| P5.3 步骤执行器 + 变量插值 | ✅ 已交付 | — | `simchat/automation/executor.py`（execute_step / interpolate / consume_stream / execute_flow）+ `skill:xxx` / `agent:run` / `file:*` 协议 |
| P5.4 配额 + 审批 + 审计 | ✅ 已交付 | — | `quota.py`（每日配额 + 全局并发≤8）+ `approval.py`（状态机 + Event 同步阻塞 + timeout 默认拒绝）+ `audit.py`（RLock 可重入锁） |
| P5.5 内置 daily-digest 示例 | ✅ 已交付 | — | `examples/automation-daily-digest/` + CLI init 模板对齐 + 宿主 bootstrap（engine→loader→discover→bind→start） |

**关键设计决策（已锁定）**：
- Automation 类型 MOD 走**数据加载分支**（类似 agent-config），不进入 sandbox；entry 字段指向 flow.json 路径而非 Python 模块。
- 不开放任意代码自动化（§3.4 明确禁止）；只支持三种内置动作：`skill:<name>`、`agent:run`、`file:{read,write}`。
- 变量插值规则：`${step_id.output}`（完整输出）、`${step_id.error}`（错误消息）、`${env:<name>}`（环境变量）；插值**只发生在 args 字符串里**，不修改原始 JSON 结构。
- 审批状态机：`PENDING → APPROVAL_REQUESTED → APPROVED/REJECTED → RUNNING → COMPLETED/FAILED/TIMEOUT`；**无人值守时 APPROVAL_REQUESTED 超时自动转 REJECTED**（默认拒绝，宁可漏跑不可跑错）。
- 配额由**本体强制执行**（不在 flow.json 可配置，MOD 无法覆盖）；`daily_quota` 由 manifest.capabilities.schedule + engine 硬闸共同作用。
- 审计日志每步记录 `step_id / status / started_at / finished_at / input_hash / output_hash / error_message`；整个 run 存 `simchat/data/audit/<flow_id>/<run_id>.json`。

---

## 一、为什么这五件要做

### 现状缺口（§3.4 数据化）

| 缺口 | 数据 | 影响 |
|---|---|---|
| 无任何通用工作流引擎 | 仓库里没有 cron / 调度器 / DAG 解析 | Phase 4 造了 CLI automation 模板但无法装载执行 |
| openmaid 是 IM 网关 | 只监听消息、推 webhook，不是"工作流编排" | 不能复用来做定时任务 / 步骤编排 |
| automation MOD 类型只有 schema 约束 | manifest.py 已强制 `capabilities.schedule=true` + `automation={flow_file: "flow.json"}` | lifecycle._load_one 里没有 automation 加载分支 → 会尝试 `run_isolated(..., entry="flow.json")` → 必然 ImportError 或子进程崩溃 |
| 无运行时契约 | CLI init 的 automation 模板里的 flow.json 目前只是"草案" | 必须冻结为正式 JSON Schema，否则 MOD 作者写出来的 flow 无法被引擎正确解析 |

### 风险本质

Automation 是**无人值守执行**——如果一个 MOD 声明 `capabilities.schedule=true` + 恶意 flow.json，它可以每分钟跑一次 `skill:file_write` 覆盖工作区。§3.4 明确三条约束：

1. **优先 JSON DAG**（可审、可静态检查），代码式自动化二期
2. **`approval: required` 默认拒绝**，无人值守时超时转 rejected
3. **配额与熔断由本体强制**，MOD 无法覆盖

Phase 5 就是把这三条约束"焊死"在引擎里。

---

## 二、flow.json DAG 正式 Schema

### 2.1 完整 JSON Schema

Phase 4 CLI init 生成的 `AUTOMATION_TEMPLATE_FLOW` 草案升级为正式 Schema `simchat/spec/flow.schema.json`：

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://simchat.dev/spec/flow.schema.json",
  "title": "SimChat Automation Flow",
  "type": "object",
  "required": ["id", "version", "trigger", "steps", "policy"],
  "additionalProperties": false,

  "properties": {
    "id":            { "type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{2,63}$" },
    "version":       { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "description":   { "type": "string" },

    "trigger": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": { "enum": ["cron", "event", "manual"] },
        "expr": { "type": "string" },          // cron 专用
        "event": { "type": "string",          // event 专用：message.received / file.changed / agent.completed
                   "pattern": "^(message\\.received|file\\.changed|agent\\.completed)$" },
        "manual_token": { "type": "string" }  // manual 专用：引擎用 token 防止误触发
      },
      // cron 必须带 expr；event 必须带 event；manual 两者都不要
      "allOf": [
        { "if": { "properties": { "type": { "const": "cron" } }, "required": ["type"] },
          "then": { "required": ["expr"], "not": { "required": ["event"] } } },
        { "if": { "properties": { "type": { "const": "event" } }, "required": ["type"] },
          "then": { "required": ["event"], "not": { "required": ["expr"] } } }
      ]
    },

    "steps": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Step" }
    },

    "policy": { "$ref": "#/$defs/Policy" }
  },

  "$defs": {
    "Step": {
      "type": "object",
      "required": ["id", "use", "args"],
      "additionalProperties": false,
      "properties": {
        "id":          { "type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{1,63}$" },
        "description": { "type": "string" },
        "use":         {
          "type": "string",
          "pattern": "^(skill:[a-zA-Z0-9_.\\-]+|agent:run|file:(read|write))$"
          // 不开放任意代码；三种内置动作
        },
        "args":        { "type": "object" },
        "depends":     {
          "type": "array",
          "items": { "type": "string" }
        },
        "approval":    { "enum": ["required", "optional", "none"], "default": "none" },
        "max_runtime_s": { "type": "integer", "minimum": 1, "maximum": 3600, "default": 60 },
        "on_error":    { "enum": ["stop", "continue", "retry"], "default": "stop" },
        "retry_count": { "type": "integer", "minimum": 0, "maximum": 5, "default": 0 }
      },
      "allOf": [
        // file:write 的 approval 必须是 required（本体强制）
        { "if": { "properties": { "use": { "const": "file:write" } }, "required": ["use"] },
          "then": { "properties": { "approval": { "const": "required" } } } }
      ]
    },

    "Policy": {
      "type": "object",
      "required": ["max_runtime_s", "daily_quota", "on_error"],
      "additionalProperties": false,
      "properties": {
        "max_runtime_s": { "type": "integer", "minimum": 1, "maximum": 3600, "default": 300 },
        "daily_quota":    { "type": "integer", "minimum": 1, "maximum": 100, "default": 10 },
        "on_error":       { "enum": ["stop", "continue"], "default": "stop" },
        "concurrency":    { "type": "integer", "minimum": 1, "maximum": 4, "default": 1 }
      }
    }
  }
}
```

### 2.2 step.use 协议

| 格式 | 动作 | 执行路径 | 依赖 |
|---|---|---|---|
| `skill:<name>` | 调用 skill MOD 工具 | `ModLoader.call_tool(name, args)` | Phase 2 交付的 `_tools` 注册表；skill MOD 必须处于 loaded 状态 |
| `agent:run` | 发起 Agent 任务 | `simchat/runtime/core.py::SimChatCore.run_stream()` | Phase 2 交付的 runtime + provider 抽象 |
| `file:read` | 读工作区文件 | 本体直接读（不走 skill，避免 skill 不可用时阻断基本自动化） | 本体内置；绕过 sandbox |
| `file:write` | 写工作区文件 | 本体直接写；**强制 approval: required** | 本体内置；绕过 sandbox；写操作必须审批 |

> **注意**：`skill:<name>` 里的 `<name>` 取自 skill MOD manifest 的 `ToolSpec.name` 字段（Phase 2 P2.4 已定义），**不是 mod_id**。
> 例如 `noic.readFile` 这个 MOD，其 `ToolSpec.name = "readFile"`，所以 step.use 应该写 `skill:readFile`，不是 `skill:noic.readFile`。
> 两者是多对一关系（一个 skill MOD 可注册多个 tool）。

**不开放**：`shell:*`、`net:*`、任意 Python 代码、`import xxx`、`eval()`。这些留二期或不做。

### 2.3 变量插值规则

语法：`${step_id.output}` / `${step_id.error}` / `${env:<name>}`

| 表达式 | 含义 | 数据来源 |
|---|---|---|
| `${step_id.output}` | 指定 step 的完整输出（字符串或 JSON） | 从 executor 步骤运行结果里取；JSON 会被序列化成字符串 |
| `${step_id.error}` | 指定 step 失败时的错误消息 | 只在 `on_error: continue` 场景有用（stop 场景 step 失败就中断了） |
| `${env:<name>}` | 环境变量 | Python `os.environ.get(name, "")`；不在 flow.json 可枚举 |

**规则**：
- 插值**只发生在 args 的字符串值里**；类型是 number/bool/array 的 args 字段不插值（避免污染 JSON 结构）。
- 未定义变量（引用不存在的 step_id）**不插值、不报错**——保留原字符串 `${bad_ref.output}`，作为"用户漏填"的信号，由 executor 日志提示。
- 单引号或反引号包裹的字符串不插值（逃逸）。

### 2.4 lifecycle 必须新增 automation 加载分支

**现状缺口**：`lifecycle._load_one()` 对 automation 类型没有特殊分支，会走 `run_isolated(package_dir, manifest["entry"], manifest)` → `entry="flow.json"` 不是 Python 模块 → 子进程崩溃 → MOD status=failed。

**修复**（放在 P5.1）：
```python
# 新增 automation 分支（插在 agent-config 分支之后、run_isolated 之前）
if manifest.get("type") == "automation":
    # 读 flow.json → automation/flow.py 校验 → engine.register_flow()
    flow_file = manifest.get("automation", {}).get("flow_file", "flow.json")
    flow_path = os.path.join(package_dir, flow_file)
    errors, flow = parse_flow(flow_path)  # Phase 5.1 交付
    if errors:
        return self._fail(record, "flow.json 校验失败: " + "; ".join(errors))
    self._automation_engine.register_flow(mod_id, flow)  # Phase 5.2 交付
    record["status"] = "loaded"
    record["flow"] = flow
    self.mods[mod_id] = record
    return record
```

这条分支的语义契约类似 agent-config，但更重：agent-config 只是"数据 MOD"不需要执行；automation 是"数据 MOD + 引擎注册"。**永远不进入 sandbox**——flow.json 是纯数据，自动化执行发生在本体 AutomationEngine 里。

---

## 三、调度器接口设计

### 3.1 顶层 AutomationEngine

```python
# simchat/automation/__init__.py
class AutomationEngine:
    """本体级自动化引擎单例。"""
    def __init__(self, data_dir, host_version="2.1.0", quota=None, audit_log=None, logger=None): ...

    # 生命周期
    def start(self): ...         # 启动 cron 循环（后台线程）
    def stop(self): ...          # 停 cron + 终止正在运行的 flow

    # MOD 装载（被 lifecycle.automation 分支调用）
    def register_flow(self, mod_id, flow): ...
    def unregister_flow(self, mod_id): ...
    def list_flows(self): ...    # 返回 [{mod_id, flow_id, status, trigger, next_run}]

    # 手动触发（CLI + API 用）
    def trigger_manual(self, mod_id, token): ...

    # 事件触发（钩子）
    def on_event(self, event_type, payload): ...
    # event_type = "message.received" | "file.changed" | "agent.completed"
```

### 3.2 Trigger 抽象

```python
# simchat/automation/scheduler.py
class Trigger:
    def is_due(self, now) -> bool: ...
    def next_run(self) -> datetime | None: ...

class CronTrigger(Trigger):
    """支持五段 cron：分 时 日 月 周。
    表达式示例：
      * * * * *           每分钟
      0 9 * * 1-5         工作日 9 点
      */15 * * * *         每 15 分钟
      0 0 1 * *           每月 1 号 0 点
    """
    def __init__(self, expr: str): ...  # 自写最小解析器，不引 croniter

class EventTrigger(Trigger):
    """只在 on_event() 被本体调用时 due=True。
    三种子事件：message.received / file.changed / agent.completed。
    实现用 threading.Event 加一个"最多触发一次"节流（本体按需再放开）。
    """
    def __init__(self, event_type: str): ...

class ManualTrigger(Trigger):
    """引擎 token 匹配才触发。"""
    def __init__(self, token: str): ...
```

**为什么不自引 croniter？** Phase 2/4 的依赖解析策略是"**不自动装包**"——MOD 不能触发 pip install；引擎是本体组件，本体可以依赖 croniter，但要权衡：
- croniter：成熟、已被广泛验证、npm/pypi 上下载量巨大；缺点是依赖第三方包
- 自写五段 cron：约 150 行，只支持 `* / , - */N` 四种通配符（足够 99% 使用场景），零依赖

**冻结**：Phase 5 首期自写最小五段 cron 解析器。flow.json 的 cron expr 是**有限集**——模板里只有 `0 9 * * 1-5` 和 `*/15 * * * *` 两种模式；复杂 cron 留二期。

### 3.3 Automation 子包目录

```
simchat/automation/
├── __init__.py          # AutomationEngine 类
├── flow.py              # parse_flow() + 静态校验 + JSON Schema 引用
├── scheduler.py         # Trigger 基类 + CronTrigger + EventTrigger + ManualTrigger
├── executor.py          # 步骤执行器（skill:xxx / agent:run / file:* + 变量插值）
├── quota.py             # 每日配额硬闸（本体强制执行，MOD 无法覆盖）
├── approval.py          # 审批状态机（PENDING → ... → APPROVED/REJECTED）
└── audit.py             # 审计日志写盘（simchat/data/audit/<flow_id>/<run_id>.json）
```

### 3.4 与本体的集成点

| 本体组件 | 集成方式 |
|---|---|
| lifecycle.py | `_load_one()` 新增 automation 分支 → 调 `AutomationEngine.register_flow()` |
| runtime/core.py | `SimChatCore.run_stream()` 暴露给 `agent:run` step |
| sandbox.py | `run_isolated` 保持不变（automation 类型永不进入 sandbox） |
| lmbrew.py 宿主启动 | 见下方"初始化顺序" |
| lmbrew.py 宿主退出 | `AutomationEngine.stop()` 进 atexit 清理链 |

#### 宿主启动时的初始化顺序（编号步骤）

**为什么必须严格按顺序？** `AutomationEngine` 在 Phase 5.1 只造空壳（`register_flow` 需要被 lifecycle.discover 调用），但 executor 在 Phase 5.3 又需要 `ModLoader` 引用（调 `call_tool`）和 `SimChatCore` 引用（调 `agent:run`）。这三个组件的创建顺序 + 注入时机如果错了，要么 discover() 时 engine 还不存在，要么 executor 拿不到运行时依赖。

```
①  create engine（空壳，只实现 register_flow）
     engine = AutomationEngine(data_dir=..., logger=...)
     set_global_engine(engine)          # 类似 Phase 2 的 set_global_loader 模式
     
②  loader = ModLoader(mods_dir=..., host_version="2.1.0", services={...})
     loader.set_global_loader(loader)
     
③  engine.bind_loader(loader)          # 注入 call_tool 方法引用（避免 engine import lifecycle）
     engine.bind_runtime(runtime_core)  # 注入 SimChatCore 实例（agent:run 用）
     
④  loader.discover()                   # automation 分支 → engine.register_flow()
     
⑤  engine.start()                      # cron 循环启动（daemon 线程，不阻塞 Flask）
     
⑥  （之后）Flask app.run()
```

**全局 getter 模式**（复用 Phase 2 `set_global_loader` 的范式）：
```python
# simchat/automation/__init__.py
_GLOBAL_ENGINE = None
def set_global_engine(engine): global _GLOBAL_ENGINE; _GLOBAL_ENGINE = engine
def get_engine(): return _GLOBAL_ENGINE
```

**避免 import 循环**：
- engine 不 import lifecycle / ModLoader；宿主启动时通过 `engine.bind_loader(loader)` 注入 `call_tool` 方法引用
- engine 不 import runtime.core；宿主启动时通过 `engine.bind_runtime(core)` 注入 `chat_stream` 方法引用
- lifecycle._load_one() 的 automation 分支通过 `get_engine()` getter 拿到 engine，不 import engine 包（同样模式被 `skill_manager_facade.py` 用过）

---

## 四、审批状态机

### 4.1 状态流转

```
                 [本体调度器触发]
                       │
                       ▼
               ┌─── PENDING ───┐
               │                │
    approval != required    approval = required
               │                │
               ▼                ▼
    ┌── RUNNING ──┐      APPROVAL_REQUESTED
    │             │      │                 │
    ▼             ▼   用户批准          超时或用户拒绝
COMPLETED    FAILED  │                 │
                  ▼   ▼                 ▼
              TIMEOUT APPROVED       REJECTED
                      │
                      ▼
                  ┌── RUNNING ──┐
                  │             │
                  ▼             ▼
              COMPLETED     FAILED/TIMEOUT
```

**默认拒绝**：
- 无人值守（无可用审批渠道）时，`APPROVAL_REQUESTED` 超过 `max_runtime_s` 后自动转 `REJECTED`。
- 有审批渠道（宿主 WebSocket 通知 / IM bot）时，用户显式 approve 才放行。
- `file:write` 的 step **被本体强制** `approval: required`——flow.json 写 `approval: none` 会被 schema 校验拒绝。

### 4.2 审批钩子（宿主侧实现）

Phase 5 只冻结引擎侧接口，审批渠道（WebSocket 通知 UI、IM bot 推送）是宿主组件，不进 Automation 引擎包：

```python
# 引擎侧只暴露一个"等审批"的 Promise
await engine.wait_approval(run_id, step_id, approval_timeout_s=300)
# 宿主 lmbrew.py 在 loop 里监听 SSE / IM 回调，调 engine.approve(run_id, step_id)
```

---

## 五、配额与熔断

### 5.1 本体硬闸（不进 flow.json 可配置）

| 闸门 | 值 | 说明 |
|---|---|---|
| 每日配额 | flow 级 `daily_quota`（max 100） | 当天 trigger 次数超过后直接 skip，审计里记 `skipped: quota_exceeded` |
| 并发上限 | flow 级 `concurrency`（max 4） | 同一 flow 同时跑的 run 数 |
| 单次 step 超时 | step 级 `max_runtime_s`（max 3600） | 超时后 step 状态变 TIMEOUT |
| 总 run 超时 | flow 级 `policy.max_runtime_s` | 整个 flow 跑超时，后续 step 跳过 |
| 重试上限 | step 级 `retry_count`（max 5） | 连续失败超过后 stop |
| 全局熔断 | 本体硬值：同时运行的 flow 总数 ≤ 8 | 超过后新的 trigger 排队等待 |

### 5.2 与 manifest.capabilities.schedule 的关系

- manifest 强制 `capabilities.schedule=true`（automation 类型），这是"静态准入校验"——没有就 fail-closed。
- 引擎级 `quota` 是"运行时硬闸"——就算 MOD 声明了 schedule=true，本体仍按硬值限制。
- 两者共同作用，MOD 无法绕过。

---

## 六、审计日志

### 6.1 日志格式

**每步**：
```json
{
  "step_id": "scan",
  "step_index": 0,
  "status": "completed",              // pending | approval_requested | approved | rejected | running | completed | failed | timeout | skipped
  "started_at": "2026-10-27T10:30:00Z",
  "finished_at": "2026-10-27T10:30:02Z",
  "duration_ms": 2150,
  "use": "skill:file_glob",
  "args": {"pattern": "**/*.md"},
  "input_hash": "sha256:abc...",     // 输入哈希，便于审计"到底传了什么"
  "output_hash": "sha256:def...",    // 输出哈希（大输出只存哈希）
  "output_preview": "src/README.md, simchat/..."  // 前 200 字原文，快速查看
}
```

**整个 run**：
```json
{
  "flow_id": "daily.workspace.digest",
  "mod_id": "automation-daily-digest",
  "run_id": "run-20261027-103000-abc123",
  "trigger": {"type": "cron", "expr": "0 9 * * 1-5"},
  "triggered_by": "cron",
  "started_at": "2026-10-27T10:30:00Z",
  "finished_at": "2026-10-27T10:30:12Z",
  "status": "completed",              // completed | failed | timeout | quota_skipped | manually_stopped
  "steps": [/* 上面每步对象 */],
  "daily_quota_used": 7,
  "daily_quota_limit": 10,
  "global_concurrent_used": 1
}
```

### 6.2 存储位置

- `simchat/data/audit/<flow_id>/<run_id>.json`
- 目录自动创建；按 `flow_id` 分片
- 保留策略（Phase 5 不做，留二期）：默认保留最近 30 天；本体重启时清理过期

---

## 七、切片规划

> 切片顺序是**逻辑依赖链**：Schema 和 lifecycle 接口先冻结（不然后面都白写）→ 调度器（能触发了但 step 执行空壳）→ 执行器（真的能跑 skill/agent/file）→ 配额审批审计（安全性补齐）→ 内置示例（首尾两端验证）。

### P5.1 — DAG 解析器 + 静态校验 + lifecycle 接口 ✅

**断**：
- Phase 4 CLI init 里的 flow.json 只是模板，没有正式 Schema 约束
- `lifecycle._load_one()` 对 automation 类型会错误走 `run_isolated(entry="flow.json")` → 必然崩
- 没有变量插值规则文档
- manifest.py schema 里的 `automation.flow_file` 字段没有被 lifecycle 消费

**接**：
1. 新建 `simchat/spec/flow.schema.json`（§2.1 完整 JSON Schema 草案）
2. 新建 `simchat/automation/flow.py`：
   - `parse_flow(path) -> (errors: list[str], flow: dict | None)`：读 JSON → json-schema 校验 → 返回规范化 flow 对象
   - `validate_static(flow) -> list[str]`：**静态可达性检查**（depends 引用不存在的 step_id → error；approval=required 时 on_error=continue → warning；use 协议非法 → error）
3. `lifecycle._load_one()` 新增 automation 分支：
   - 读 `manifest.automation.flow_file` → `flow.py.parse_flow()`
   - 调 `AutomationEngine.register_flow(mod_id, flow)`（engine 先造空壳）
   - 记录 `record["flow"] = flow`
   - **永不进入 sandbox**
4. `simchat/__init__.py` 新增 VERSION bump：0.4.0 → 0.5.0

**验收**：
1. CLI `init --type automation` 生成的 flow.json 直接过 `parse_flow()` 无 errors
2. 写一个 `depends: ["bad_step"]` 的 flow.json → `validate_static()` 返回错误
3. lifecycle.discover() 对 automation MOD：不崩溃、status=loaded、不创建 sandbox_handle
4. 既有 agent-config-minimal / barry.galax / 5 个 skill **零回归**

**依赖**：
- 需要先造 `AutomationEngine` 空壳（只实现 `register_flow`）
- 不需要 cron 解析器、不需要 executor

**不做**：
- 不实现任何 trigger / scheduler
- 不实现变量插值
- 不执行任何 step

---

### P5.2 — 最小调度器 + cron ✅

**断**：
- 没有 cron 解析器（Phase 2/4 都没用到）
- 没有触发循环（后台线程轮询）
- AutomationEngine 只有 register_flow 空壳，没有 start/stop/trigger_manual

**接**：
1. `simchat/automation/scheduler.py`：
   - 自写五段 cron 解析器（100-150 行）：支持 `* / , - */N`；不支持字母（JAN/MON 等）、不支持 L/W/#
   - `CronTrigger(expr)` → `is_due(now) / next_run()`
   - `EventTrigger(event_type)` → 默认不 due，on_event() 时触发一次
   - `ManualTrigger(token)` → `is_due()` 永远 False，`trigger_manual()` 强制 due 一次
2. `AutomationEngine` 完整接口：
   - `start()`：起一个 daemon 线程，每秒轮询所有 cron flow 的 `trigger.next_run() - now`
   - `stop()`：Event 标志 + 线程 join(10s)
   - `list_flows()`：所有已注册 flow + 下一步触发时间
3. 宿主 `lmbrew.py` 启动流程：`loader.discover()` 之后 → `engine.start()`；atexit 里 `engine.stop()`

**验收**：
1. 写一个 `trigger.expr="*/5 * * * *"` 的测试 flow → `engine.list_flows()` 里 next_run 正确
2. `trigger.expr="0 9 * * 1-5"` → cron 解析正确识别工作日
3. 手动 `engine.trigger_manual(mod_id, token)` → flow 进入 RUNNING 状态（step 执行先空壳返回 mock 结果）
4. 宿主启动 → 不 crash → 定时触发不阻塞 Flask 主循环

**依赖**：P5.1（AutomationEngine 空壳 + lifecycle 分支）

**不做**：
- 不实现 executor（step 执行返回 mock）
- 不实现 quota / approval / audit
- 不做持久化（重启后 cron 从下一个 due 重新算起，允许"跳过最近一次触发"）

---

### P5.3 — 步骤执行器 + 变量插值 ✅

**断**：
- 没有 `skill:xxx` 转发（Phase 2 有 `ModLoader.call_tool()` 但 engine 没调）
- 没有 `agent:run` 转发（Phase 2 runtime.core 有，但 engine 没调）
- 没有 `file:read/write` （本体能力未暴露给 engine）
- 没有变量插值 `${step.output}`

**接**：
1. `simchat/automation/executor.py`：
   - `execute_step(step, context) -> (status, output, error)`：
     - `use.startswith("skill:")` → `loader.call_tool(step.use.split(":",1)[1], step.args)`
     - `use == "agent:run"` → **SSE 流同步消费**（见下方）
     - `use == "file:read"` → 本体直接读文件（sandbox 外，因为 automation MOD 本来就不进 sandbox）
     - `use == "file:write"` → 本体直接写文件 + 强制 approval（P5.4 实现，此处只抛 "approval_required"）
   - `interpolate(args, context) -> dict`：递归遍历 args，字符串值里找 `${xxx}` 替换；未定义引用保留原样并 warn
   - `consume_stream(gen) -> str`：**把 SSE generator 同步消费成最终字符串**（见下方）
   - **execution context**：一个 dict，包含 `{step_id: output_hash, flow_id, run_id, env: {...}}`
2. AutomationEngine 把 scheduler 触发的 flow.run() 调到 executor

#### agent:run 的 SSE 同步消费方案

**问题**：`SimChatCore.chat_stream()` 返回一个 SSE generator（逐块吐 token），但 executor 是同步函数 `execute_step() -> (status, output, error)`，需要最终完整输出字符串。

**方案**：在 executor 里新增一个同步消费函数（≈20 行），不引入 async/asyncio：

```python
def consume_stream(gen):
    """把 SimChatCore.chat_stream() generator 同步消费成最终字符串。
    
    SSE 事件格式（Phase 2 runtime.events.md 冻结）：
      chat_started / token / final / error
    
    只保留 final 事件里的完整 output；中间 token 事件被忽略（避免拼接开销）。
    如果 final 事件缺失或报错 → 回退：把所有 token 事件拼接成字符串。
    """
    full_output = []
    last_error = None
    for event in gen:
        etype = event.get("type")
        if etype == "final":
            return event.get("output", "")
        elif etype == "token":
            full_output.append(event.get("token", ""))
        elif etype == "error":
            last_error = event.get("error")
    if full_output:
        return "".join(full_output)
    if last_error:
        raise RuntimeError("agent:run 执行失败: " + last_error)
    return ""
```

**为什么不新增 `SimChatCore.run_once()`？** 因为 Phase 2 的 `chat_stream()` 是唯一的公共入口（SSE 统一输出），再加一个同步包装会造成双维护。executor 自己做同步消费是最轻的方案。

**验收**：
1. 写一个 `steps: [{id:"call_readfile", use:"skill:read_file", args:{...}}]` → engine 触发后 step 状态=completed，output 有 read_file 结果
2. `${call_readfile.output}` 变量插值到下一步 `file:write` 的 args.content → 能正确拿到上一步输出
3. `agent:run` step → 能触发一次真实 Agent run（独立 session，不改用户会话）
4. `${bad_ref.output}` 未定义引用 → 插值后保留原字符串，executor 日志里有 warn

**依赖**：P5.2（调度器已经能触发 flow）

**不做**：
- 不做审批流程（`file:write` 此时硬报 approval_required，不真正审批）
- 不做 quota（无限次运行）
- 不做完整审计日志（只在 executor 内部 try/except 打印）

---

### P5.4 — 配额 + 审批 + 审计 ✅

**断**：
- 没有审批状态机：`approval: required` 形同虚设
- 没有每日配额：flow.json 里写 `daily_quota` 但引擎不检查
- 没有审计日志：出问题无法回放

**接**：
1. `simchat/automation/quota.py`：
   - 内存中维护 `{flow_id: {date_str: count}}`
   - `is_quota_ok(flow) -> bool`
   - `increment_quota(flow)`
   - 跨天自动清零
2. `simchat/automation/approval.py`：
   - `ApprovalState` 状态机（§4.1 全状态）
   - `await_approval(run_id, step_id, timeout_s)`：**用 `threading.Event.wait(timeout)` 同步阻塞**（不引入 async/asyncio），返回 APPROVED / REJECTED / TIMEOUT
   - **同步阻塞的理由**：Phase 5 executor 是同步函数，scheduler 触发 flow.run() 后按 step 顺序串行执行；一个 step 等审批时 executor 线程阻塞 `Event.wait(timeout_s)`，**不阻塞 Flask 主线程**（executor 运行在 cron daemon 线程里）。宿主侧收到审批请求后调 `engine.approve(run_id, step_id)` → 内部 `approval_event.set()` → executor 线程被唤醒继续
   - **本体强制** `file:write` 的 step 必须 approval=required（在 flow.py.validate_static 里校验 + executor 里二次拦截）
   - **无人值守超时默认拒绝**：`timeout_s` 默认值 = step.max_runtime_s（flow.json 可配，默认 60s）；超时后 approval 状态转 REJECTED，不自动放行
3. `simchat/automation/audit.py`：
   - `start_run(flow, run_id)` → 创建 audit 目录 + 初始 run.json（started_at、triggered_by）
   - `append_step(step_id, status, ...)` → 追加到 run.json 的 steps[]
   - `finish_run(status)` → 写 finished_at + daily_quota_used
4. executor / scheduler 全部集成 quota/approval/audit

**验收**：
1. 把一个 flow.json 的 `daily_quota` 写成 2，手动触发 3 次 → 第三次 quota 检查返回 False，status=quota_skipped，审计里记 skipped
2. `file:write` step（approval=required）无审批 → 30s 后自动 REJECTED，run status=failed
3. 一个完整 run 结束 → `simchat/data/audit/<flow_id>/<run_id>.json` 完整存在，能回放
4. 并发运行 3 个不同 flow → 全部不阻塞，各自审计独立

**依赖**：P5.3（executor 能跑 step）

**不做**：
- 不做 WebSocket / IM 审批渠道（引擎只暴露接口，宿主实现通知）
- 不做审计日志保留策略（默认无限增长；Phase 6 加清理）

---

### P5.5 — 内置 daily-digest 示例 ✅

**断**：
- 引擎没有验证端点（Phase 5 最终能不能跑起来，靠示例说）
- `examples/` 目录里只有 skill-hello 和 agent-config-minimal，缺少 automation 样例
- separation-plan §5.3 裸壳四件套要求"示例 automation"

**接**：
1. 新建 `simchat/examples/automation-daily-digest/`：
   - `manifest.json`：automation 类型 + `capabilities.schedule=true` + `automation: {flow_file: "flow.json"}`
   - `flow.json`：**改用现有可用的 skill 动作** —— scan step 用 `use: "skill:readFile"`（现有 noic.skill-readfile，ToolSpec.name = "readFile"），sum step 用 `use: "agent:run"`，write step 用 `use: "file:write" + approval: required`。**不用 `skill:file_glob`**——现有 mods/ 里没有这个 skill，示例依赖 Phase 2 已交付的 5 个 skill 中的 readFile，冒烟时零额外依赖
2. **同步更新 CLI init 模板**：`simchat/cli/main.py` 里 Phase 4 写死的 `AUTOMATION_TEMPLATE_MANIFEST` / `AUTOMATION_TEMPLATE_FLOW` 也要把 `skill:file_glob` 改成 `skill:readFile`，与示例 flow.json 保持一致。**CLI init 的输出 = examples/ 目录下的样例**，两者必须对齐，否则用户 init 出来的模板会依赖不存在的 skill
3. 冒烟测试：
   - `simchat.cli init --type automation` 生成的模板过 `flow.py.parse_flow()` ✓
   - lifecycle.discover() 对 automation-daily-digest → status=loaded，不崩 ✓
   - `engine.trigger_manual("automation-daily-digest", "test-token")` → scan step 跑起来（依赖环境有 file_glob skill，可用 read_file skill 替换） ✓
   - 审计日志完整落盘 ✓

**验收**：
1. 完整的 E2E：init → lifecycle discover → engine trigger_manual → step 执行 → audit 落盘
2. separation-plan §5.3 裸壳四件套要求全部满足：provider + 对话 runtime + 朴素记忆 + 示例 skill + 示例 automation（Phase 5 做完后 skill 和 automation 都有样例）

**依赖**：P5.1-5.4 全部完成

**不做**：
- 不做更复杂的 flow 示例（只做 daily-digest 一种）
- 不做事件触发的示例（cron 和 manual 两种足够）

---

## 八、风险清单

| 风险 | 来源 | 对策 |
|---|---|---|
| automation MOD 恶意覆盖工作区 | `capabilities.schedule=true` + 无 sandbox | `file:write` 强制 approval=required；本体硬闸 daily_quota；automation 永不进 sandbox，由本体直接执行（绕过 MOD 代码） |
| cron 解析器自造轮子有 bug | 五段 cron 边角 case | 用 10 条 fixture 覆盖（每分钟、工作日、每月 1 号、*/N 通配符、逗号列表）；Phase 5 后 review 一次 |
| executor 里调 Phase 2 组件可能 import 循环 | engine → lifecycle → registry → engine | engine 不 import lifecycle；只拿 loader 的 call_tool 方法引用（宿主启动时注入） |
| 审批渠道未实现时 approval=required 全 reject | Phase 5 只做引擎不做宿主通知 | 文档明确"无人值守默认拒绝"策略；引擎暴露 `engine.approve()` 接口供宿主将来调用；P5.4 冒烟时手动 approve |
| runtime/core.py 的 `agent:run` 是同步函数，不能被 scheduler 线程直接调 | Flask 主线程和 cron 线程并发 | executor 在独立线程里跑 agent:run（Phase 2 SimChatCore.run_stream 已独立 provider 抽象，无 Flask 依赖） |

---

## 九、Phase 5 验收总表

| 验收点 | 切片 | 标准 |
|---|---|---|
| flow.json schema 冻结 | P5.1 | JSON Schema Draft 2020-12 覆盖所有必填字段 + use 协议 + approval 规则 |
| automation MOD 被 lifecycle 正确加载 | P5.1 | status=loaded，不创建 sandbox_handle，不崩溃 |
| cron 五段解析器正确 | P5.2 | 10 条 fixture（每分、工作日、每月 1 号、*/N、逗号）全通过 |
| scheduler start/stop 不阻塞 Flask | P5.2 | daemon 线程 + Event 标志 + stop 时 join(10s) |
| skill:xxx 通过 ModLoader.call_tool | P5.3 | executor 能调 Phase 2 的 read_file / web_search 等 skill |
| agent:run 能发起真实 Agent run | P5.3 | 独立 session_id 跑完一轮，token 流正常 |
| 变量插值 | P5.3 | `${step.output}` 正确替换；未定义引用保留原样 |
| file:write 强制 approval=required | P5.4 | flow.py 静态校验拦截；executor 二次拦截绕过 |
| 审批超时自动 REJECTED | P5.4 | 30s 超时后 step 状态转 rejected |
| daily_quota 硬闸 | P5.4 | 超配额后 trigger 被 skip |
| 审计日志可回放 | P5.4 | run.json 完整记录所有 step 状态 + 哈希 |
| daily-digest 示例跑通 | P5.5 | 完整 E2E（init → discover → trigger → 执行 → 审计） |
| 既有 MOD 零回归 | 全 | 7 个既有 MOD status=loaded，功能不变 |

---

## 十、Phase 6 保留项（不在 Phase 5 范围）

- 事件触发三种具体实现（message.received / file.changed / agent.completed）——Phase 5 只实现 CronTrigger + ManualTrigger；EventTrigger 留 Phase 6
- 审批渠道（WebSocket / IM bot 通知）——Phase 5 只暴露 `engine.approve()` 接口，宿主实现推送
- 审计日志保留策略（过期清理）——Phase 5 不做
- 自动 git clone MOD 安装（lifecycle ↔ Registry 集成）——Phase 4 保留项，Phase 6 拆仓时做
- 代码式自动化（用户写 Python 定时跑）——**永远不做**，§3.4 明确禁止

---

## 十一、部署记录（2026-10-27）

> Phase 5 完整交付日。5 个切片全部通过验收；发现并修复 6 个前置冲突，全部落地。

### 11.1 实际交付清单

**新增 10 个文件**：

| 文件 | 行数 | 说明 |
|---|---|---|
| `simchat/spec/flow.schema.json` | 145 | flow.json 正式 Schema（JSON Schema Draft 2020-12） |
| `simchat/automation/__init__.py` | ~270 | AutomationEngine + 全局 getter + scheduler 集成 + executor 调用 |
| `simchat/automation/flow.py` | ~240 | parse_flow + validate_static + 默认值补全 |
| `simchat/automation/scheduler.py` | ~200 | 自写五段 cron 解析器 + CronTrigger / EventTrigger / ManualTrigger |
| `simchat/automation/executor.py` | ~230 | execute_step + interpolate + consume_stream + execute_flow |
| `simchat/automation/quota.py` | ~80 | 每日配额硬闸 + 全局并发 ≤8 |
| `simchat/automation/approval.py` | ~100 | ApprovalTicket（Event 同步阻塞）+ ApprovalManager |
| `simchat/automation/audit.py` | ~130 | AuditLogger（RLock 可重入锁防死锁） |
| `simchat/examples/automation-daily-digest/manifest.json` | ~20 | 示例 MOD manifest |
| `simchat/examples/automation-daily-digest/flow.json` | ~25 | 示例 flow（cron + skill:readFile + agent:run + file:write 审批） |

**修改 7 个文件**：

| 文件 | 改动 |
|---|---|
| `simchat/__init__.py` | VERSION 0.4.0 → 0.5.0 |
| `simchat/loader/manifest.py` | ① automation 类型 entry 放宽（不强制 module:attr）② 新增 `automation.flow_file` 校验 ③ KNOWN_HOOKS 扩展 4 个事件 hook（`agent.completed` / `agent.finished` / `message.received` / `file.changed`） |
| `simchat/spec/mod-manifest.schema.json` | ① automation 对象改为 `flow_file`（原 `flow`） ② entry pattern 放宽支持 `.json` 后缀 |
| `simchat/loader/lifecycle.py` | 新增 automation 数据加载分支（永不进 sandbox，走 get_engine() → register_flow()） |
| `simchat/cli/main.py` | AUTOMATION_TEMPLATE_FLOW：`skill:file_glob` → `skill:readFile`（对齐实际可用的 readFile skill） |
| `rigard/services/rigard.py` | ① `_init_mods()` 加 AutomationEngine bootstrap（engine 必须在 discover 之前创建）② host_version 2.0.0 → 2.1.0 ③ 宿主退出时 `engine.stop()` 进 atexit |
| `mods/automation.daily-digest/` | 内置示例 MOD 复制到 mods/，宿主启动时自动加载 |

### 11.2 部署中发现并解决的前置冲突

| # | 冲突 | 来源 | 解决方案 |
|---|---|---|---|
| 1 | `manifest.py` 的 `ENTRY_RE`（`module:attr` 格式）拦截 automation 的 `entry: "flow.json"` | 方案未考虑 entry 格式差异 | automation 类型跳过 ENTRY_RE 校验；schema 同步放宽 entry pattern |
| 2 | `mod-manifest.schema.json` 用 `automation.flow` + 嵌套 `trigger/policy`，但 Phase 5 方案用 `automation.flow_file`（trigger/policy 进 flow.json） | 方案 §2.4 与 Phase 4 遗留 schema 不一致 | schema 对齐 `flow_file`；trigger/policy 完全迁入 flow.json |
| 3 | CLI 模板里的 `skill:file_glob` / `skill:file_write` 在 `mods/` 里不存在 | Phase 4 写模板时是占位 | 改为实际可用的 `skill:readFile`（ToolSpec.name 取自 noic.readFile MOD） |
| 4 | RigardService 没有 `set_global_loader()` | Phase 4 `_init_mods()` 只造 loader 没设全局 | 补 `set_global_loader()` + 宿主 bootstrap 顺序：engine → loader → discover → bind → start |
| 5 | cron 解析器 `_day_matches()` 里 `*` 展开后 dom={1..31} + dow={0..6}，导致 dom 单独不匹配时 dow 还能兜底（`dom_hit or dow_hit`） | 自写 cron 的 day 匹配逻辑 bug（经典 cron 行为：`*` 应视作"不限制"而非"全值集合"） | 加 `dom_any` / `dow_any` 判断：两者都 any 时直接返回 True；其中一个 any 时另一个单独判断 |
| 6 | AuditLogger.append_step() 在 `Lock` 内调 `_flush()`，`_flush()` 也 `with Lock` → **死锁** | executor 集成 audit 后才暴露 | Lock → RLock（可重入锁）；同时 `finish_run()` 改为先 flush 再 pop，避免 flush 时取不到 active run |

### 11.3 验收结果

| 测试 | 结果 |
|---|---|
| Cron 解析器 9 条 fixture | ✅ 9/9 |
| executor（interpolate / file:read / on_error=stop / depends 跳过） | ✅ 5/5 |
| quota + approval + audit 三件套 | ✅ 13/13 |
| 完整冒烟（manifest→flow→lifecycle→engine→审计→配额） | ✅ 全链路 |
| 既有 MOD 回归（7 个 Phase 2-4 MOD） | ✅ 7/7 loaded |
| 宿主 bootstrap（engine→loader→discover→bind→start） | ✅ 8/8 MOD 全加载（含 automation.daily-digest） |
| daemon 线程不阻塞 Flask | ✅ 已验证 |

### 11.4 已知限制（Phase 5 范围外，留 Phase 6）

- **EventTrigger 三种具体实现**：CronTrigger + ManualTrigger 已实现；EventTrigger 是空壳（`fire()` 方法已留，宿主需调用）
- **审批渠道**：引擎只暴露 `engine.approve()` / `engine.reject()` API，宿主未实现 WebSocket / IM 通知推送
- **审计保留策略**：无限增长，未做过期清理
- **持久化**：重启后 cron 从下一个 due 重新算起（可能跳过重启期间的触发）
- **拓扑排序**：execute_flow 暂按 step 顺序串行，未做 depends 拓扑排序（depends 引用不存在会被标记 skipped）
- **并发 policy 未强制**：flow.policy.concurrency 字段存在但引擎未限制同一 flow 同时运行数；全局并发硬闸（≤8）已实现
