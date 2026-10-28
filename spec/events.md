# Agent SSE 事件契约（v1 冻结）

> 唯一契约：后端 `emit(dict)` 的字段与前端 `handleAgentEvent` 的消费字段必须一一对应。
> 任何字段增删都按 [abi-changelog.md](./abi-changelog.md) 走版本流程。

## 1. 传输

| 项 | 约定 |
|---|---|
| Content-Type | `text/event-stream` |
| 帧格式 | `data: {json}\n\n` |
| 心跳 | 空闲 60s 发送 `: keepalive\n\n`（注释行，不是事件） |
| 编码 | UTF-8，`ensure_ascii=False` |
| 顺序 | 单连接内严格有序；后端由单 worker 线程串行 emit |
| 断开 | 客户端断开 → 后端 `abort(run_id)` 并清理挂起态（fail-closed） |

HTTP 端点（当前前缀 `/api/kirara`，目标前缀 `/api/simchat`，见 Phase 2）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/agent/tools` | `{success, tools:[{name,label,description,risk,usage,enabled}]}` |
| POST | `/agent/run` | 发起任务，返回 SSE |
| POST | `/agent/approve` | `{run_id, decision:"approve"\|"reject", edits?}`，返回 SSE |
| POST | `/agent/abort` | `{run_id}` → `{success, run_id, was_active}` |
| GET | `/agent/tasks` | 任务 session 列表 |
| DELETE | `/agent/tasks/<sid>` | 仅允许 `agent_` 前缀 |

## 2. 事件一览

| 事件 | 关键字段 | 时机 |
|---|---|---|
| `run_started` | `run_id` | 每个 SSE 流的**第一帧**（含审批续流） |
| `plan` | `turn=0, steps[], raw, restored?` | turn-0 规划完成；`restored=true` 表示审批恢复 |
| `plan_progress` | `done_count, last_tool?` | 任一工具**成功**执行后 |
| `thought` | `turn, content` | 每轮推理产出后；turn-0 为“收到任务，开始规划…” |
| `tool_call` | `turn, call_id, tool, input, risk` | 工具即将执行/挂起前；审批恢复时会重发 |
| `tool_result` | `turn, call_id, tool, ok, output, error` | 工具执行结束（含未知/未启用/被拒绝） |
| `approval_required` | `turn, call_id, tool, input, risk, reason` | 写/危险工具挂起；**该流随即结束** |
| `token_usage` | `turn, prompt_tokens, completion_tokens, budget, threshold` | 每轮推理后（估算值） |
| `compaction` | `turn, before_entries, after_entries, before_tokens, after_tokens, threshold, budget` | transcript 超阈值被压缩时 |
| `final` | `content` | 任务正常终结；**语义安全拒绝也走此事件** |
| `aborted` | `message` | 用户中止/断连 |
| `error` | `message` | 后端不可用、未捕获异常 |
| `max_turns` | `message` | 达到 `max_turns` 仍未终结 |

> `run_started` 由传输层发，其余由 `AgentLoop` 发。`plan_progress`、`final`、`aborted`、`error`、`max_turns` **没有** `turn` 字段。

## 3. 终止与挂起

```
正常终结：final | aborted | error | max_turns   → 流关闭，run 清理
挂起：    approval_required                    → 流关闭，挂起态落盘（TTL 默认 600s）
```

- 挂起不是终结：前端必须调用 `/agent/approve`，新流会重发 `run_started` 与 `plan(restored=true)`。
- 挂起态过期或损坏 → `/agent/approve` 返回 HTTP 410，不再产生事件。
- 每个流恰好一个 `run_started`；终结事件最多一个。

## 4. 字段细节

### 4.1 `plan`

```json
{"event":"plan","turn":0,"steps":["用 glob 定位所有 Markdown 文件","用 file_read 读取 readme.md","汇总回答"],"raw":"1. ...\n2. ...\n3. ..."}
```

- `steps`：从编号/checklist 提取并去重；可能为空（此时后端改发 `thought`）。
- `raw`：模型原始规划文本，截断 500 字符。
- 恢复时：`{"event":"plan","turn":0,"steps":[...],"raw":"","restored":true}`。

### 4.2 `tool_call` / `tool_result`

```json
{"event":"tool_call","turn":1,"call_id":"t1c1","tool":"glob","input":{"pattern":"**/*.md"},"risk":"read"}
{"event":"tool_result","turn":1,"call_id":"t1c1","tool":"glob","ok":true,"output":"...","error":""}
```

- `call_id` 格式固定 `t{turn}c{index}`，同一轮内 `c` 从 1 递增。
- `risk ∈ {read, write, dangerous, unknown}`；`unknown` 表示未注册工具。
- `output` 已截断到 8192 字符；失败时为空串，错误放 `error`。
- 失败原因分三类，**均为 `tool_result.ok=false`**，不升级为 `error` 事件：
  - 未知工具：`error="未知工具 X（可用: ...）"`
  - 未启用：`error="工具 X 当前未启用..."`
  - 用户拒绝：`error="用户拒绝了此操作，请改用只读思路或调整方案。"`

### 4.3 `approval_required`

```json
{"event":"approval_required","turn":1,"call_id":"t1c1","tool":"file_write","input":{"path":"a.txt","content":"..."},"risk":"write","reason":"写操作工具 file_write 将修改项目文件，需您确认。"}
```

- `reason` 由后端生成，前端原样展示，不要自行拼文案。
- `edits` 只允许修改 `input` 的键，不允许新增键（Phase 2 起强校验）。

### 4.4 `token_usage` / `compaction`

```json
{"event":"token_usage","turn":2,"prompt_tokens":2120,"completion_tokens":88,"budget":16384,"threshold":12288}
{"event":"compaction","turn":5,"before_entries":9,"after_entries":4,"before_tokens":13010,"after_tokens":6420,"threshold":12288,"budget":16384}
```

- token 为**估算值**：CJK 1.5 字/token，其余 4 字符/token；仅用于阈值判断与 UI 展示，不是计费口径。
- `threshold = budget - num_predict(1024) - 3072`。

### 4.5 扩展事件

- MOD 自定义事件名必须为 `mod.<mod_id>.<name>`，载荷放 `data` 字段。
- 前端对未知事件**静默忽略**。
- 核心事件名为保留字，MOD 不得占用。

## 5. 兼容规则

- 新增事件：前端必须已具备 `default` 忽略分支。
- 新增字段：可选，旧前端忽略；旧后端缺失时前端必须给默认值。
- 删除/重命名字段或改变语义：ABI major 升级。
- 建议（向后兼容，v1.x 起）：`run_started` 增加 `"schema": 1`，用于客户端快速判断契约版本。

## 6. Chat SSE 事件（v1，Phase 2 本体独立对话）

> 本体 `POST /api/simchat/chat` 的对话级契约，与 §1–§5 的 Agent 任务级契约相互独立。
> 实现：`simchat/runtime/`（provider 抽象 + 会话存储 + 对话核心），不依赖任何宿主。

| 事件 | 关键字段 | 时机 |
|---|---|---|
| `chat_started` | `schema=1, session_id` | 每个对话流的第一帧；`session_id` 缺省/未知时自动创建 |
| `token` | `content` | 模型增量输出，可任意多次 |
| `final` | `content, session_id` | 正常终结；`content` 为完整回复，user+assistant 消息已落盘 |
| `error` | `message` | provider 未配置/调用失败/空回复；流随即结束 |

- 帧格式同 §1：`data: {json}\n\n`，UTF-8，`ensure_ascii=False`。
- 每条流恰好一个 `chat_started`；终结事件（`final` | `error`）恰好一个。
- 请求体：`{message, session_id?, provider?, model?, system?}`；`provider ∈ {ollama, openai_compat}`，缺省读 `simchat/data/config.json`。
- 配套端点：`GET/POST /api/simchat/sessions`、`GET/DELETE /api/simchat/sessions/<sid>`。
