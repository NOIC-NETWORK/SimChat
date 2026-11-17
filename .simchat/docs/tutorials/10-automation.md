# 10 自动化 DAG

> 本章属于「装配型」路径（B），前置：[07 技能安装与启停](07-manage-skills.md)、[08 写第一个 Skill MOD](08-first-skill.md)。

## 1. 你会得到什么

一个自己写的自动化包：`flow.json` 定义三步流程（读文件 → 让模型总结 → 写结果），注册成功，能被 Agent 手动触发，运行记录和审计文件都能查到。

```text
> 列出自动化流程
已注册 flow（1 个）：
- daily.my-digest | mod=com.example.mydigest | trigger=cron | next_run=2026-11-18 09:00

> 触发 daily.my-digest
⚠ automation_trigger 需要审批 → 批准
{"ok": true, "status": "completed", ...}
```

## 2. 前置条件

- 服务能启动，Agent 模式可用。
- 已经理解「包目录 + manifest + entry」这套结构（第 08 章）。
- 一个可写的工作目录，以及里面一个真实存在的文本文件。

## 3. 跟着做

### 3.1 生成骨架

```bash
python .simchat/scripts/entry.py cli init --type automation --name com.example.mydigest --target .simchat/skills/com.example.mydigest
```

生成 `manifest.json` 与 `flow.json`。manifest 的关键字段：

```json
{
  "type": "automation",
  "layer": "block",
  "entry": "flow.json",
  "hooks": ["automation.hook"],
  "capabilities": { "schedule": true, "fs": { "write": ["workspace"] } },
  "automation": { "flow_file": "flow.json" }
}
```

`entry` 指向 flow 文件本身，`automation.flow_file` 与它一致；`capabilities.schedule=true` 表示允许被调度。

### 3.2 写 flow.json

把模板换成这个三步版本（`args` 里的 `${...}` 是变量插值）：

```json
{
  "id": "daily.my-digest",
  "version": "0.1.0",
  "trigger": { "type": "cron", "expr": "0 9 * * 1-5" },
  "steps": [
    {
      "id": "scan",
      "use": "file:read",
      "args": { "path": "README.md" }
    },
    {
      "id": "sum",
      "use": "agent:run",
      "args": {
        "message": "用中文总结下面内容，200 字以内：\n\n${scan.output}"
      }
    },
    {
      "id": "write",
      "use": "file:write",
      "args": { "path": "digest.md", "content": "# 每日摘要\n\n${sum.output}" },
      "approval": "required",
      "approval_hint": "自动写入 digest.md"
    }
  ],
  "policy": { "max_runtime_s": 120, "daily_quota": 10, "on_error": "stop" }
}
```

约束来自 `flow.py` 的校验，写错会直接加载失败：

- 顶层必填 `id / version / trigger / steps / policy`；`id` 形如 `daily.my-digest`，`version` 必须是 `x.y.z`。
- `policy` 三个键都必填：`max_runtime_s`（1–3600）、`daily_quota`（1–100）、`on_error`（`stop` / `continue`）。
- `steps[].use` 只支持四种协议：`skill:<工具名>`、`agent:run`、`file:read`、`file:write`。
- `file:write` 的 `approval` 必须是 `required`，写 `none` 会被本体拒绝。

### 3.3 重启并确认注册

重启服务后，Agent 里问：

```text
列出所有自动化流程
```

对应工具调用 `/$TOOL:automation PARAMS:{"action": "list"}`。预期能看到 `daily.my-digest` 及其触发器。注册失败时控制台「自动化」页会标 `manifest 错误`。

### 3.4 触发一次

```text
触发 daily.my-digest
```

Agent 会调用 `automation_trigger`（写级），先弹审批卡。批准后流程**同步**执行，结果直接回灌到时间线。

关键提示：`file:write` 这一步还会再要一次审批，而这次审批**在 Web 里没有入口**——见 4.4。所以上面的流程大概率停在 `write` 步，等到 300 秒超时后被判 `rejected`。这是当前实现的真实行为。

### 3.5 看运行记录与审计

- 最近运行（内存里最近 20 条，重启即清空）：

  ```text
  /$TOOL:automation PARAMS:{"action": "runs", "limit": 5}
  ```

- 落盘审计：`.simchat/data/audit/<flow_id>/<run_id>.json`，含每个 step 的 `pending / completed / failed / rejected / timeout`。

## 4. 为什么会这样

### 4.1 「DAG」实际是顺序执行 + 依赖门控

步骤按数组顺序串行跑；`depends: ["scan"]` 只表示「前一步没 `completed` 就跳过本步」，不会改变执行顺序，也没有并发分支。真正的并发闸门是全局最多 8 个 flow 同时跑。

### 4.2 变量插值

`${scan.output}` 引用前面 step 的输出；`${env:WORKSPACE}` 读环境变量；`${env:NAME}` 找不到时返回空串。无法识别的表达式会原样保留并记一条 warning。

### 4.3 调度

- `cron`：`expr` 是标准五段 cron，本地时区；调度线程每秒检查一次，同一分钟内不会重复触发。
- `manual`：只能通过 `automation_trigger` 触发。
- `event`：`event` 必须是 `message.received` / `file.changed` / `agent.completed` 之一，**但运行时目前没有生产者调用 `engine.on_event()`**——声明合法，却不会真的被事件触发。

### 4.4 审批的真实状态

`file:write` 会调用 `engine.approval_manager.request(..., timeout_s=300)` 阻塞等待。批准入口只有进程内的 `engine.approve(run_id, step_id)`：

- Web 没有 `/api/automation/approve` 这类接口，控制台自动化页只读；
- Agent 工具层也没有「批准自动化 step」的动作。

所以现阶段任何带 `file:write` 的自动 flow，最终都会走到「300 秒超时 → 按拒绝处理」。写文件这一步要么改成 `agent:run`（由 Agent 的写工具 + 正常审批完成），要么等审批通道接线。

### 4.5 配额与并发

- 全局并发上限 8，超了记 `global_busy` 并跳过；
- 每个 flow 每日执行次数受 `policy.daily_quota` 限制，超了记 `quota_skipped`；
- `max_runtime_s` 是单次运行的时间预算，超时后该次运行记为失败。

### 4.6 控制台里那个 `not_started` 是过期的

`GET /api/console/automation` 返回的 `engine` 字段被硬编码成 `"not_started"`，并带一句「自动化引擎由宿主启动器提供」。实际上 Web 启动时已经启动了引擎并注册了 flow。判断是否可用请以 `automation` 工具的 `list` 结果为准。

## 5. 常见坑

- **`policy` 少写一个键就加载失败**：三个都是必填，哪怕 `max_runtime_s` 用默认值也要显式写。
- **`depends` 写了不存在的 id**：静态校验会报 `depends 引用不存在的 step_id`，包直接不加载。
- **以为 cron 到点就一定能跑**：还要过每日配额、全局并发、以及该 flow 的启用状态。
- **触发后一直转圈**：流程是同步执行的，长流程会占住这次工具调用，直到 `max_runtime_s` 超时。

## 6. 验收清单

- [ ] 能写出一个通过校验的三步 flow
- [ ] 能说出 `policy` 三个必填键及取值范围
- [ ] 能列出四种 `use` 协议
- [ ] 能解释 `${scan.output}` 与 `${env:WORKSPACE}` 的区别
- [ ] 知道 event 触发器目前不会真的触发
- [ ] 知道 `file:write` 的审批在 Web 里暂无入口

## 7. 延伸阅读

- [flow.py](../../automation/flow.py)：schema、DAG 静态校验、policy 约束
- [executor.py](../../automation/executor.py)：四种 `use` 的实现与审批等待
- [scheduler.py](../../automation/scheduler.py)：cron 轮询与事件 pending
- [audit.py](../../automation/audit.py)：审计文件结构
- [11 调试与排错](11-debugging.md)
