# 最近更新

**2026-11-09 夜** — Orbiter 落地：composer 里的 AI 实例下拉

- 占位了很久的 Orbiter 按钮（`.agent-only`）正式变成了 `<select id="agent-picker">`。选项列表：`— 直接对话 —` + 每个 AI 实例的头像 emoji + 名称；非 Agent 模式的实例后缀 `（对话）`。
- 选中即激活实例：写入 `state.activeAgentId` / `localStorage.simchat.active_agent_id` / `state2.selectedAgentId`，composer 里的 `/api/chat` 请求自动带上 `agent_id`，前端 SSE 渲染和后端 Agent 模式一起联动；选回空值则回到"直接对话"（不带实例）。
- 双向同步：agent-list 浮层里点「激活」会反向刷新 picker；picker 里选了也会刷新 agent-list 高亮。`loadAgents` / 新建 / 删除 / 更新实例后都重绘。
- 文案替代：以前要手敲 `/@gremlin`，现在点一下就行。未来如果要加 Orbiter 路由器（"轻量大模型做路由"那个混合推理架构），可以在这个下拉旁边加一个模式切换，但**实例选择这个核心已经解决了**。
- 文件：`web/templates/index.html`、`web/static/js/chat.js`

**2026-11-09 晚** — Agent 模式终于接通 AgentLoop

- **根因**：`/api/chat` handler 从来没读 `agent.agent_capable`，所有带 AI 实例的对话都走 `core.chat_stream` 普通聊天流，后端已实现好的 `runtime/agent/` 包（AgentLoop + SimChatAgentBackend + ReAct 协议 + 工具集）一直是死代码。用户截图里 `/@gremlin 你好吗` 返回的是模型自由发挥的闲聊而不是工具调用，直接命中这个根因。
- **修复**：`web/__init__.py` chat handler 新增 agent_capable 分支，构造 SimChatAgentBackend（复用 engine_params 的温度 / Top-P / 重复惩罚 / max_tokens，复用 SimChatCore 的服务商解析）+ AgentLoop（mode="agent"，workdir 取 workspace_status().path，shell 暂关闭），loop.run() 同步跑 ReAct 循环，emit 回调把事件收集到 list，再逐条 SSE 发出。
- **配套**：新增 `_agent_mod()` 懒加载函数；Agent 会话用 `mode="agent"` 隔离，不复用普通 chat 会话；quota 硬闸在进 AgentLoop 前先做一次。
- **修复 Gateway 握手 JSON 丢失**（上一次表单修复里的同类问题）。
- 实测：gremlin 实例（agent_capable=True）打 `/api/chat` 带 agent_id，正确发出 `chat_started / thought / final` 事件，session mode 正确落盘为 "agent"。
- 文件：`web/__init__.py`、`updates.md`、`README.md`

**2026-11-09** — AI 实例后台创建浮层 + 表单提交修复

- **实例创建改为后台执行**：点「保存」后弹窗立即关闭，视口右上角出现进度浮层（`#agent-boot-stack`），包含实例头像 / 名称 / 放弃按钮，以及「加载模型中 / 生成神经网络中」两行文案与进度条。进度先缓慢逼近 92%，接口返回后仍保留约 1.3 秒可读时间，再平滑补到 100%，最后卡片向右飞出视口并淡出。
- **放弃即回滚**：创建途中点「放弃」，卡片立即飞出；实例已落盘则自动 `DELETE` 删除，请求仍在途则等返回后立刻删除，列表不残留半成品。
- **失败回退**：创建失败时浮层收起，编辑弹窗重新打开并保留已填内容，错误信息显示在原位置。
- **修复 Agent 表单提交失败**：`/api/agents` 的新建与编辑请求漏了 `Content-Type: application/json`，Flask 的 `request.get_json(silent=True)` 拿到空 payload，导致名称明明填了却报「名称不能为空」、编辑保存也静默失效。同时修复 `/api/gateway/connect` 的同一问题。
- **表单体验**：实例表单整体及所有输入框加 `autocomplete="off"`，浏览器不再弹出历史输入建议；一开始输入就清除上次的校验提示，校验失败自动聚焦名称框。
- **移除 `seed` 字段**：该字段只存不读（`synapse-notes.md` 早有记录），从前端表单与提交 payload 移除，后端 `agents.py` 保留 `setdefault` 兜底旧存档；`docs/ai-instance-engine-presets.md`、`docs/architecture-recap.md`、`docs/synapse-notes.md` 同步更新。
- 文件：`web/templates/index.html`、`web/static/js/chat.js`、`web/static/css/chat.css`、`docs/ai-instance-engine-presets.md`、`docs/architecture-recap.md`、`docs/synapse-notes.md`

**2026-11-03** — Token 用量统计 + 额度限制（从 kirara 迁移）

- **每日 token 用量统计（后端持久化）**：新增 `runtime/usage.py`（`UsageTracker`），按 YYYY-MM-DD 记录 input/output tokens 与会话次数，存 `data/usage.json`，线程安全 + 文件级原子写入。`chat_stream()` 和 `agent_run()` 入口结束后自动累加用量。
- **后端 quota 硬闸**：`settings.json` 的 `quota.limit` 字段控制每日上限（0 = 不限额，默认）；`chat_stream` / `agent_run` 入口各有一次硬闸检查，超限返回 `code: quota_exceeded`（对话模式走 SSE error 事件、Agent 模式返回 HTTP 429）。支持锁定（`quota.lock=true` → 后端 403 拒绝修改）。
- **前端本地每日统计（localStorage）**：`web/static/js/chat.js` 内置 `utReadAll()` / `recordDailyUsage()` / `utIsLimitExceeded()`，对话模式和 Agent 模式结束时各自结算，前端 `sendMessage` 入口做硬闸拦截（`updateQuotaUI()` 驱动超限横幅 + 进度条更新）。前后端双保险。
- **Agent token 徽章 + 压缩提示渲染**：此前后端 AgentLoop 已 emit `token_usage` / `compaction` 事件，但前端静默丢弃；现在每次 `token_usage` 累加 prompt/completion tokens 并更新卡片头部徽章（按使用比例显示 ok/warn/critical 三级 + 颜色 + 临界态呼吸动画），`compaction` 事件渲染紫色提示卡片展示压缩前后条数和 token 变化。
- **每日用量 UI**：composer 上方新增红色超限横幅（sticky），token-bar 下方新增每日用量进度条（跟随 token-bar 一起显隐、按使用比例变色），两者均硬编码在 `index.html`（非动态注入），首屏无闪烁。
- **高级功能 → 使用情况面板接入**：原先占位的「该模块尚未接入」section 被替换为完整面板——4 张统计卡（今日总计 / 输入 / 输出 / 会话数）、近 7 天条形图（今天蓝色高亮、hover 显示 token 数）、额度限制配置卡（启用开关 + 限额输入 + 日/月周期选择 + 锁定开关 + 保存/重置按钮 + 后端保存失败时静默降级到 localStorage）。新增 3 个后端 API：`GET /api/console/usage`、`POST /api/console/usage/quota`、`POST /api/console/usage/reset-today`。
- 文件：`runtime/usage.py`（新增）、`runtime/core.py`、`web/__init__.py`、`web/agent.py`、`web/templates/index.html`、`web/static/js/chat.js`、`web/static/css/chat.css`

**2026-11-01** — 群机器人：OneBot v11 与 QQ 官方 API 双接入（真实收发）

- 设置控制台新增「群机器人」分组，两种接入方式**按钮分开**：`Python 库（OneBot v11）` 与 `QQ 官方 API`，各自有独立的启动 / 停止 / 测试连接 / 测试发送与运行面板（连接方式、收发计数、最近错误、Webhook 回调地址一键复制、最近活跃群点选）。
- **OneBot v11**：正向 WebSocket（断线指数退避重连）或 HTTP 反向 Webhook 收消息；`get_login_info` 做连通性自检，`send_group_msg` 发送；支持群白名单、必须 @、前缀触发。
- **QQ 官方 API**：`getAppAccessToken` + Gateway WebSocket（Hello / Identify / 心跳 / 重连）或 Webhook（Ed25519 验签 + op13 回调校验）；群消息走 `/v2/groups/{openid}/messages`，单聊（C2C）走 `/v2/users/{openid}/messages`，被动回复携带 `msg_id` / `msg_seq`。
- 群消息进入 `SimChatCore.chat_stream()` 生成回复，以 `im-<mode>-<会话>` 隔离上下文：按消息 ID 去重、每会话串行、两个 QQ 通道互斥；外部文本按不可信输入处理（截断 + 安全约束）。
- 每个通道可独立指定「模型服务商 / 模型」，自动回复、白名单、触发规则、系统提示词均**实时读取**，保存即生效；AccessToken / AppSecret 等敏感字段 Fernet 加密，前端只回显掩码。
- 文件：`runtime/im_bots.py`、`runtime/comms.py`、`web/__init__.py`、`web/static/js/chat.js`、`web/static/css/settings.css`、`web/templates/index.html`、`scripts/requirements-simchat.txt`（新增 `websocket-client>=1.6.0`）

**2026-10-31** — 工作目录门禁 + 个人中心 + Agent 会话落盘修复

- **工作目录（workspace）成为对话与 Agent 的统一根目录**：未选择目录时 composer 只读锁定、发送被拦截并提示；顶栏 chip、欢迎页、侧栏均可重新配置；新增目录浏览选择器（逐级浏览 + 直接输入绝对路径），配置写入 `data/config.json`，Agent 沙箱的 `workdir` 随之切换。
- **个人中心**：侧栏用户卡可点击进入设置页，支持用户名、生日、紧急联系人、头像（PNG / JPEG / WEBP / GIF，前端自动压缩到 256px），档案只存本机 `data/profile.json`。
- **Agent 模式会话落盘修复**：`SessionStore.get_or_create()` 之前会忽略传入的 `agent_` 会话 id 并另建随机会话文件，导致 Agent 消息全部落空；现在按显式 id 建会话并正常写入，Agent 多轮对话会自动续接已落盘历史。
- **会话模式标识符**：会话记录新增 `mode` 字段（`chat` / `agent`），Agent 会话固定 `agent_` 前缀；侧栏用「对话 / Agent」标签区分，打开会话自动切回对应模式，两种模式的上下文互不污染。
- **启动恢复失败静默回退**：上次会话已被删除或旧版本未落盘时，刷新页面不再把「加载会话失败：会话不存在」渲染成助手消息，而是静默清理记录并回到新对话。
- **IDE 界面演示页**：新增 `/ide` 单文件六区布局演示（`ide-demo.html`，无外链、无后端依赖），与 `/` 对话界面共用同一套 `/api/*`。
- 文件：`runtime/workspace.py`、`runtime/store.py`、`runtime/agent/`、`web/agent.py`、`web/__init__.py`、`web/static/js/chat.js`、`web/static/css/chat.css`、`web/templates/index.html`、`ide-demo.html`

**2026-10-29** — Web UI 多 provider 聚合 + 下拉交互修复 + OpenAI 预检强化

- **模型下拉聚合所有 provider**：composer 里的模型选择器不再只显示 resolved 那一个 provider 的模型，而是用 `<optgroup>` 按 provider 分组列出所有已发现的模型（Ollama 本地 + OpenAI 兼容 + 未来其他）。切换模型时 provider 跟着走，请求 payload 同时带 `provider` 和 `model`。
- **下拉菜单 hover 白字修复**：原生 `<select>` 在 Windows 上 `background: transparent` 会导致弹出面板的 option hover 时白底白字。加了全局 `select option` 明确兜底 `background-color` + `color`，深色模式独立适配。
- **模型提供商存档固化**：新增 `providerStore` 模块（`window.SimChatProviderStore`），把后端返回的 providers + models 缓存到 `localStorage`（10 分钟过期）。刷新页面后模型下拉立即有数据，不用等后端重新 discover；后端不可用时继续用缓存兜底。
- **OpenAI 预检 404 误判修复**：之前 `_openai_probe` 把 404/405 一律当作"端点只是不支持 /models 预检"，导致用户把 OSS 桶地址（`*.aliyuncs.com`）、CDN、甚至随机网页 URL 配成 API Base 时被误判为 available=True，实际调用才爆 404。现在加了 `Content-Type` 校验——只有 JSON 响应才保守判 OK，非 JSON 明确报错并提示检查 API Base。
- 文件：`runtime/provider_config.py`、`web/static/css/chat.css`、`web/static/js/chat.js`、`web/templates/index.html`

> 状态：**Phase 0-5 全部交付**（2026-10-28）。
> 定位：SimChat 是 **LMBrewer 的开源底层框架**——它本身具备接入 LLM API 进行对话的完整能力（`runtime/providers.py` + `core.py` + `store.py`），同时提供 MOD SDK + 加载器 + 清单规范 + 沙箱运行时，让社区和团队以模块方式扩展认知能力。
> 愿景：四类 MOD 对应通用智能的四个积木——`skill`=工具调用（感知与行动）、`automation`=自我编排（自主规划）、`agent-config`=人格与对齐（行为约束）、`binary`=专有内核（推理/记忆/安全）。SimChat 是模块化 AGI 的开源基座。