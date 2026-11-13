# SimChat 运行时 API 端点清单

> 供 Kirara App 对接 SimChat 后端使用。以 `simchat/web/__init__.py` 与 `simchat/web/agent.py` 的实现为准（2026-11-12 快照）。

## 0. 基础约定

| 项 | 说明 |
|---|---|
| 默认地址 | `http://127.0.0.1:5000`（启动：`python .simchat/scripts/entry.py web --host 127.0.0.1 --port 5000`） |
| 协议 | HTTP/1.1 + JSON；SSE 端点返回 `text/event-stream` |
| 请求头要求 | 所有 JSON 请求体必须带 `Content-Type: application/json`，否则 Flask `get_json` 静默返回空 |
| 鉴权 | 无 Token / 无 Session 鉴权，默认仅监听本机。对外暴露需自行加反向代理与访问控制 |
| CORS | 未启用 Flask-CORS。原生客户端（Kirara App 后端/桌面进程）可直接调用；浏览器跨域 fetch 会被拦截 |
| 编码 | UTF-8，响应 `ensure_ascii=False` |
| 数据根目录 | `data/`（会话、配置、实例、日志、用量、Agent 运行态） |

### 通用错误约定

```json
{"error": "人类可读原因"}
```

| HTTP | 场景 |
|---|---|
| 400 | 参数缺失/格式非法（如缺少 `message`、路径非绝对路径、`enabled` 非布尔值） |
| 403 | 额度配置已锁定（`quota.lock=true`） |
| 404 | 资源不存在（会话 / 实例 / 节点 / 日志文件） |
| 409 | 门禁拦截：`provider_unavailable`、`workspace_required`、`workspace_missing` |
| 410 | Agent 审批挂起态不存在或已过期（fail-closed） |
| 429 | 后端额度硬闸：`code=quota_exceeded` |

控制台类接口普遍使用统一包络：

```json
{"available": true, "generated_at": "2026-11-12T02:00:00Z", "reason": "", "data": {}}
```

### 运行前置门禁（顺序）

1. 已配置可用服务商（`GET /api/providers` → `available=true`）
2. 已配置工作目录且目录存在（`GET /api/workspace` → `configured && exists`）
3. 未超额度（`settings.json` 的 `quota.limit`；`0` 表示不限）
4. 满足后才允许 `POST /api/chat` 与 `POST /api/agent/run`

---

## 1. 页面（非 API，Kirara 一般不需要）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/` | 主对话界面；无用户档案时返回注册页 |
| GET | `/register` | 注册页；已有档案返回 302 → `/` |
| GET | `/ide` | 桌面端 IDE 六区布局界面 |
| GET | `/wap` | 移动端单列堆栈界面 |
| GET | `/mods/<mod_id>/<path:filename>` | MOD 自带前端静态资源（`<mod>/web/`），防路径穿越 |

---

## 2. 健康检查与生命周期

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/health` | 守护进程探活；不读写用户数据 | `{ok, app:"simchat", pid}` |
| GET | `/api/lifecycle` | 查询开机自启 / 守护进程 / 服务运行状态 | `lifecycle.status(...)` 快照 |
| POST | `/api/lifecycle/autostart` | 开关开机自启 | `{enabled: bool}` |
| POST | `/api/lifecycle/watchdog` | 开关自动拉起守护 | `{enabled, confirm, port?}` |
| POST | `/api/lifecycle/stop` | 停止守护或停止整个 Web 服务 | `{mode:"watchdog"\|"service"}`；`service` 会进程退出 |

---

## 3. 服务商（模型后端）

支持的 provider id：`ollama`、`openai_compat`，另有虚拟的 `auto`（自动选最优）。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/providers` | 服务商总览 + UI 方块材质 + MOD 预设 | `{available, preferred, resolved, configured, auto, providers[], blocks, presets}` |
| POST | `/api/providers` | 保存某服务商配置并可激活 | `{provider, config:{...}, activate?}`；返回同上 |
| POST | `/api/providers/test` | 实测服务商可用性（会记住"已验证"） | `{provider, config}` → `{ok, message, models?}` |
| POST | `/api/providers/discover` | 拉取模型列表（探测 `/models` 或 Ollama tags） | `{provider, config}` → `{ok, models[], message}` |

`config` 字段：Ollama 为 `{base_url, model, keep_alive?}`；OpenAI 兼容为 `{base_url, api_key, model}`。

---

## 4. 用户档案

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/profile` | 读取档案与是否已注册 | `{has_profile, profile}` |
| POST | `/api/profile` | 保存档案；仅显式传 `avatar` 时才更新头像 | `{username, birthday, emergency_contact, avatar?}` → `{ok, profile}` |

---

## 5. 基础设置

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/settings` | 读取设置 + 默认值 + UI 方块 | `{settings, defaults, blocks}` |
| POST | `/api/settings` | 局部更新设置（白名单字段 + 区间夹取） | 任意设置字段 → `{settings}` |
| POST | `/api/settings/reset` | 重置设置 | `{scope:"settings"\|...}` → `{settings}` |

可写字段：`max_history`、`temperature`、`max_tokens`、`system_prompt`、`send_with_enter`、`show_token_bar`、`theme`、`font_scale`、`quota{limit,period,lock}`。`character` 段保留但前端角色 UI 已移除。

---

## 6. 工作目录（workspace）

对话与 Agent 工具沙箱的统一根目录。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/workspace` | 当前工作目录状态 | `{workspace:{configured, exists, path, name, updated_at}}` |
| POST | `/api/workspace` | 设置工作目录（必须是存在的绝对路径） | `{path}` → `{ok, workspace}` |
| DELETE | `/api/workspace` | 清除工作目录配置 | `{ok, workspace}` |
| GET | `/api/workspace/browse` | 目录浏览（可视化选择器；单次最多 500 条） | `?path=` → `{ok, path, parent, entries[], roots[], truncated}` |
| GET | `/api/workspace/read` | 读取工作区文本文件（白名单扩展名，≤512KB） | `?path=` → `{ok, path, name, size, encoding, content}` |

未配置工作目录时，`/api/chat` 与 `/api/agent/run` 均返回 409 `workspace_required`。

---

## 7. 会话 CRUD（对话模式）

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/sessions` | 会话列表（按更新时间倒序） | `{sessions:[{id,title,mode,created_at,updated_at,message_count,tokens_estimated,overrides}]}` |
| POST | `/api/sessions` | 新建空会话（`mode=chat`） | `{session}` |
| GET | `/api/sessions/<sid>` | 读取完整会话（含 messages） | `{session}`；不存在 404 |
| DELETE | `/api/sessions/<sid>` | 删除会话 | `{deleted: bool}` |
| PATCH | `/api/sessions/<sid>` | 更新单会话覆盖参数 | `{overrides:{thinking,verbose,reasoning}}`；非法值静默忽略 |

`overrides` 合法值：`thinking/verbose ∈ inherit|low|medium|high`，`reasoning ∈ inherit|off|low|medium|high`。

---

## 8. 对话（SSE）

### POST `/api/chat`

请求体：

```json
{
  "message": "你好",
  "session_id": "可选，缺省自动创建",
  "provider": "可选：ollama | openai_compat",
  "model": "可选，覆盖默认模型",
  "system": "可选，覆盖系统提示词",
  "agent_id": "可选，实例 ID；其 engine_preset / system_prompt 生效",
  "regenerate": false
}
```

- 返回 `text/event-stream`，每帧 `data: {json}\n\n`。
- 根据 `agent.agent_capable` 分流：启用 Agent 的实例走完整 ReAct 循环（事件同 Agent 契约），否则走普通流式对话。
- 会话模式隔离：对话会话与 `agent_` 会话互不复用。

普通对话事件：

| 事件 | 字段 | 时机 |
|---|---|---|
| `chat_started` | `schema=1, session_id` | 首帧 |
| `token` | `content` | 增量文本，可多次 |
| `final` | `content, session_id` | 正常结束；用户与助手消息已落盘 |
| `error` | `message, code?` | 服务商不可用 / 额度超限 / 空回复 / 调用异常 |

Agent 分流时额外可能发 `thought`、`plan`、`tool_call`、`tool_result`、`approval_required`、`token_usage`、`compaction`、`aborted`、`max_turns`。

---

## 9. Agent（ReAct 循环）

同一套蓝图注册在两个前缀下，行为完全一致：

- `/api/agent/*`（推荐）
- `/api/simchat/agent/*`（兼容冻结的 Agent SSE fixture）

> 注意：不存在 `/api/simchat/chat` 或 `/api/simchat/sessions`，对话与会话只走 `/api/chat`、`/api/sessions`。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/agent/tools` | 工具（方块）清单与风险分级 | `{success, tools:[{name,label,description,risk,usage,enabled}]}` |
| POST | `/api/agent/run` | 发起 Agent 任务，返回 SSE | 见下方请求体 |
| POST | `/api/agent/approve` | 审批挂起操作并恢复 SSE | `{run_id, decision:"approve"\|"reject", edits?}` |
| POST | `/api/agent/abort` | 中止运行（幂等）并清理挂起态 | `{run_id}` → `{success, run_id, was_active}` |
| GET | `/api/agent/tasks` | Agent 会话任务列表 | `{success, tasks:[{session_id,message,message_count,mode,title,mtime}]}` |
| DELETE | `/api/agent/tasks/<sid>` | 删除任务会话（仅 `agent_` 前缀） | `{success, session_id}` |

### `/api/agent/run` 请求体

```json
{
  "message": "任务描述",
  "session_id": "可选；agent 模式必须是 agent_ 前缀，否则自动改派",
  "mode": "agent | chat（缺省 agent）",
  "agent_id": "可选实例 ID",
  "provider": "可选",
  "model": "可选",
  "system": "可选",
  "workdir": "可选，覆盖工作目录",
  "history": [{"role": "user", "content": "..."}]
}
```

- Agent 会话 id 固定 `agent_` 前缀；`mode=chat` 为"懒调用"单轮轻量模式（禁用 shell）。
- 不传 `history` 且会话已落盘时，自动续接该会话上下文。
- 失败前置：400 空消息；429 额度；409 服务商/工作目录；400 workdir 非法。

### SSE 传输约定

| 项 | 约定 |
|---|---|
| Content-Type | `text/event-stream` |
| 帧格式 | `data: {json}\n\n` |
| 心跳 | 空闲 60s 发 `: keepalive\n\n`（注释行，不是事件） |
| 首帧 | 恒为 `run_started`（含审批续流） |
| 断开 | 客户端断开 → 后端 abort 并清理挂起态（fail-closed） |

Agent 事件：

| 事件 | 关键字段 |
|---|---|
| `run_started` | `run_id, schema` |
| `plan` | `turn=0, steps[], raw, restored?` |
| `plan_progress` | `done_count, last_tool?` |
| `thought` | `turn, content` |
| `tool_call` | `turn, call_id, tool, input, risk` |
| `tool_result` | `turn, call_id, tool, ok, output, error` |
| `approval_required` | `turn, call_id, tool, input, risk, reason`（该流随即结束） |
| `token_usage` | `turn, prompt_tokens, completion_tokens, budget, threshold` |
| `compaction` | `turn, before_entries, after_entries, before_tokens, after_tokens, threshold, budget` |
| `final` | `content` |
| `aborted` | `message` |
| `error` | `message` |
| `max_turns` | `message` |

内置方块（工具）名称：`file_read`、`list_dir`、`glob`、`grep_text`、`web_search`、`file_write`、`file_edit`、`shell`；skill MOD 可注册可插拔方块。

---

## 10. AI 实例（Agent 配置）CRUD

实例 = 预设 + 系统提示词 + 模型偏好 + 是否启用 Agent 能力。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/agents` | 实例列表 + 引擎预设；首次访问自动建默认实例 | `{agents[], engine_presets[]}` |
| POST | `/api/agents` | 新建实例 | `{name, description?, avatar?, avatar_type?, system_prompt?, seed?, agent_capable?, allow_advanced?, desktop_pet?, engine_preset?, engine_params?}` → `{agent}` |
| GET | `/api/agents/<agent_id>` | 读取实例 | `{agent}`；不存在 404 |
| PUT | `/api/agents/<agent_id>` | 局部更新实例 | 同创建字段 → `{agent}` |
| DELETE | `/api/agents/<agent_id>` | 删除实例（默认实例不可删） | `{ok}` |
| POST | `/api/agents/reset` | 删除全部自定义实例并重建默认实例 | `{agent}` |

`engine_preset`：`normal | work | code | creative | custom | wsynk`。仅 `custom` 采用传入的 `engine_params{temperature, top_p, repetition_penalty, max_tokens}`。

---

## 11. 网关（Gateway）

> 当前为占位/概览实现，真正的网关模块尚未接入。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/gateway` | 握手快照 + 访问信息（动态生成 socket_url/token） | `{access:{socket_url, access_token, session_key,...}, snapshot:{health, uptime_seconds,...}}` |
| POST | `/api/gateway/connect` | 手动触发握手（占位） | `{ok, message, snapshot}` |

### 网关节点（Peers）

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/gateway/peers` | 本机信息 + 已登记节点列表 | `{ok, self:{name,url,health,pid,uptime_seconds}, peers[]}` |
| POST | `/api/gateway/peers` | 新增节点 | `{name, url, token?, note?}` → `{ok, peer}`；URL 重复 400 |
| PUT | `/api/gateway/peers/<peer_id>` | 更新节点 | 同上字段 → `{ok, peer}` |
| DELETE | `/api/gateway/peers/<peer_id>` | 删除节点 | `{ok}` |
| POST | `/api/gateway/peers/<peer_id>/probe` | 探测已登记节点连通性 | `{ok, probe:{ok, latency_ms, app, pid,...}}` |
| POST | `/api/gateway/peers/probe` | 新增前试连（不落盘） | `{url, token?}` → `{ok, probe}` |

---

## 12. 通讯通道（IM / 群机器人 / SMTP）

通道注册表驱动，当前 `channel_id`：`qq_group_onebot`、`qq_group_official`、`smtp`。

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/console/comms` | 全通道脱敏视图 + 群机器人运行态 | 包络；`data:{active, channels[]}` |
| GET | `/api/console/comms/runtime` | 群机器人运行时摘要 | 包络；`data:{channel_id: runtime}` |
| POST | `/api/console/comms/<channel_id>` | 保存通道配置（敏感字段 Fernet 加密） | 字段 dict → `{ok, data}` |
| POST | `/api/console/comms/<channel_id>/activate` | 设为当前启用通道（互斥） | `{ok, data}` |
| POST | `/api/console/comms/<channel_id>/clear` | 清除配置（群机器人先停机） | `{ok, data}` |
| POST | `/api/console/comms/<channel_id>/start` | 启动通道运行时（群机器人上线） | `{ok, runtime, data}` |
| POST | `/api/console/comms/<channel_id>/stop` | 停止通道运行时 | `{ok, runtime, data}` |
| POST | `/api/console/comms/<channel_id>/test-connection` | 测试连接 | `{ok, detail, runtime}` |
| POST | `/api/console/comms/<channel_id>/test` | 发送测试消息 | `{group_id, message, msg_id?}` → `{ok, detail, runtime}` |
| POST | `/api/console/comms/qq_group_onebot/webhook` | OneBot v11 反向 HTTP 事件入口 | `?token=` 或 `Authorization`；body 为事件 |
| POST | `/api/console/comms/qq_group_official/webhook` | QQ 官方机器人回调（Ed25519 验签、op 13 地址验证） | 原始 body + 签名头 |

最后两个 Webhook 由外部 IM 平台调用，Kirara App 不需要。

---

## 13. 客户端实例（在线设备）

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| POST | `/api/instances/heartbeat` | 客户端每 15s 上报心跳 + 设备信息 | `{device_id, tab_id?, info:{os,os_version,browser,browser_version,ua,arch,screen,language,timezone,date,hardware_concurrency,device_pixel_ratio,platform,vendor,online}}` → `{ok}` |
| GET | `/api/instances` | 在线客户端列表（60s 无心跳离线，10min 清理） | `{generated_at, offline_threshold_seconds, online, total, instances[]}` |
| GET | `/api/console/nodes` | 节点总览：客户端 + 网关节点 | 包络；`data:{self, clients[], peers[], counts}` |

---

## 14. 控制台：MOD / 技能 / 自动化

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/console/mods` | MOD 索引快照（本地/远端、状态、启用标记） | 包络；`data:{mods_dir, local[], ...}` |
| POST | `/api/console/mods/<mod_id>/toggle` | 启用/停用 MOD（只读扫描，零副作用） | `{enabled: bool}` → `{ok, data}` |
| GET | `/api/console/skills` | 仅 skill 类型 MOD 列表 | 包络；`data:{mods_dir, items[], counts}` |
| GET | `/api/console/automation` | 自动化流程只读展示（引擎由宿主启动器提供） | 包络；`data:{engine, items[], counts}` |
| GET | `/api/console/agent` | 代理控制台：实例 + 预设 + 运行参数 + skill MOD | 包络；`data:{agents, engine_presets, options, skill_mods}` |

---

## 15. 控制台：系统 / 调试 / 日志

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/console/system` | 环境信息（Python/平台/内存/数据目录等） | 包络；`data` |
| POST | `/api/console/system` | 保存系统配置（日志级别） | `{log_level}` → `{ok, data}` |
| GET | `/api/console/debug/snapshot` | 调试快照：运行时长、会话数、Agent 运行数、实例数等 | 包络；`data{...,counts}` |
| GET | `/api/console/debug/events` | 最近 API 事件环形缓冲（最多 300 条） | `?limit=60` → 包络；`data:{total, events[]}` |
| GET | `/api/console/logs` | 日志目录与文件列表 | 包络；`data:{log_dir, files[]}` |
| GET | `/api/console/logs/<name>` | 读取日志尾部 | `?lines=200` → 包络；不存在 404 |

---

## 16. 用量统计与额度

| 方法 | 路径 | 用途 | 关键参数 / 返回 |
|---|---|---|---|
| GET | `/api/console/usage` | 今日用量 + 近 7 天 + 当前 quota 配置 | `{success, quota:{enabled,limit,period,lock}, today, recent}` |
| POST | `/api/console/usage/quota` | 修改额度配置（锁定状态下 403） | `{limit?, period?:"day"\|"month", lock?}` → `{success, quota}` |
| POST | `/api/console/usage/reset-today` | 清空今日用量（测试/手动修正） | `{success}` |

额度为前后端双保险：前端 localStorage 本地闸 + 后端 `runtime/usage.py` 全局硬闸。

---

## 17. Kirara App 最小对接路径

```
GET  /api/health                → 探活
GET  /api/providers             → 确认 available=true
GET  /api/workspace             → 确认 configured && exists
GET  /api/agents                → 取实例（可选，用于 agent_id / 引擎参数）
POST /api/chat                  → 普通对话（SSE）
POST /api/agent/run             → Agent 任务（SSE）
POST /api/agent/approve         → 审批后继续（SSE）
POST /api/agent/abort           → 中止
GET  /api/sessions              → 历史会话
GET  /api/agent/tasks           → Agent 任务会话
```

鉴权、CORS、HTTPS 均由外部接入层负责；SimChat 本身只假设本机可信环境。
