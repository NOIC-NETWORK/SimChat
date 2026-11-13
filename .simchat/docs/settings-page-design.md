# SimChat 设置页设计方案 v2

> 状态：设计方案 / 待评审
> 基础：openmaid 残余代码调研（2026-10-28）+ 用户提出的 OpenClaw 式三分区方案
> 目标：在 SimChat 中落地「基础设置 + 高级功能设置（默认折叠）」双层结构，服务端为唯一事实源，适配瘦客户端 + 浏览器调用

---

## 1. 设计原则

1. **默认简单，进阶折叠**：多数用户只需要「选服务商、填 Key、能用」。基础设置默认展开；三组十二区的高级控制台折叠在「高级功能设置」里，展开状态只记在浏览器本地（`localStorage`），不进服务端配置。
2. **控制台 = 远端管理面**：SimChat 部署在家用数据堡垒（公用工作站），浏览器只是瘦客户端。所有状态由服务端检测/存储，页面不做本地推断，不在前端画假数据。
3. **同一套服务商实现**：高级控制台里的「通讯 / 代理 / 节点」不能复制 `provider_config` 的校验、保存、测试逻辑，只能复用既有 API。
4. **未接入就是未接入**：十二区中大量模块尚无后端，统一返回 `{available:false, reason}` 并展示「该模块尚未接入」，禁止 Mock 数字（openmaid 的占位卡正是反面教材）。
5. **取其骨架，不搬主题**：复用 openmaid 的导航/表单/仪表盘结构，配色沿用 SimChat `--accent` 双主题变量。

---

## 2. 调研结论（openmaid 能提供什么）

openmaid 的侧栏与本次方案**几乎一一对应**：

| openmaid 页面 | 行号 | 现状 | 对应本方案分区 |
|---|---|---|---|
| overview 概览 | `openmaid.html:875-952` | 仪表盘卡片 + 网关配置表单（唯一可用的设置表单） | 控制 / 概览 |
| gateway 接口 | `openmaid.html:955-1060` | iMessage / QQ 等通讯卡片 + 配置表单 | 控制 / 通讯 |
| instance 实例 | `openmaid.html:1061-1079` | 三张静态卡片占位 | 控制 / 实例 |
| sessions 会话 | `openmaid.html:1082-1100` | 静态统计占位 | 控制 / 会话 |
| usage | `openmaid.html:1103-1121` | 静态统计占位 | 控制 / 使用情况 |
| automation 自动化 | `openmaid.html:1124-1142` | 静态卡片占位 | 控制 / 自动化 |
| available-agents | `openmaid.html:1145-1218` | 智能体卡片网格 | 代理 / 代理 |
| skills 技能 | `openmaid.html:1219-1277` | 技能卡 + iOS 开关（假加载、无持久化） | 代理 / 技能 |
| nodes 节点 | `openmaid.html:1278-1285` | 占位 | 代理 / 节点 |
| general-settings | `openmaid.html:1286-1293` | 占位 | 配置 / 配置 |
| debug | `openmaid.html:1294-1301` | 占位 | 配置 / 调试 |
| logs | `openmaid.html:1302-1326` | 占位 | 配置 / 日志 |

真正可复用的资产：

| # | 资产 | 位置 | 用法 |
|---|---|---|---|
| 1 | 侧栏分组 + `data-page` 页面切换 | `openmaid.html:694-702`；`ide-script.js:328-338`；`ide-layout.css:191-225` | 高级控制台的导航骨架 |
| 2 | `content-page` 页面容器 | `openmaid.html:875` 等 12 个容器 | 每个分区一个页面容器 |
| 3 | 设置表单骨架 | `openmaid.html:362-453`（`.form-row/.form-group/.config-input/.form-actions`） | 通讯/代理/节点表单 |
| 4 | 状态徽章 + 健康条 | `openmaid.html:319-360` | 概览的网关/服务商状态 |
| 5 | 仪表盘卡片网格 | `openmaid.html:874-900`；`ide-layout.css:256-279` | 概览/实例/使用情况 |
| 6 | 智能体卡片 + 技能卡 | `openmaid.html:1148-1277` | 代理/技能列表（重写开关与持久化） |
| 7 | 配置读写三段式 | `ide-script.js:487-553`（load → populate → save） | 每个分区的 GET/表单/保存 |
| 8 | 后端 JSON 配置持久化 | `openmaid_server.py:57-103` | 配置落盘模式（需原子写 + 白名单） |
| 9 | 恢复出厂 | `openmaid_server.py:339-351` | 「恢复默认」两档粒度 |
| 10 | 控件 CSS | `modern-ui.css:585-809`（switch / range / 下拉 / 单选卡） | 控件参考，颜色换 `--accent` |
| 11 | 模型参数 schema | `QueryEng.js:5-11,33-52,71-82` | 基础设置字段命名 |
| 12 | 通讯服务雏形 | `openmaid/services/comm_apis/qq.py`、`imessage.py`；`openmaid_server.py` 相关接口 | 通讯分区的最小接口参考，需重写 |

不沿用：粉紫主题与渐变按钮、单文件 1200+ 行内联样式、`QueryEng.js`（Node 模块）、技能开关假加载、`token/sessionKey` 明文、`alert()` 提示、静态占位数字。

---

## 3. 信息架构（按用户方案落地）

### 3.1 总览

```
基础设置（默认可见）
├── 服务商（Auto Model / Ollama / OpenAI 兼容 + 测试连接）
├── 对话（历史窗口、温度、max_tokens、系统提示词、Enter 发送）
├── 外观（主题、字号）
└── 高级功能设置 ▸（默认折叠）

高级功能设置（展开后进入全屏控制台）
├── 控制
│   ├── 概览      网关状态 / 入口点 / 健康状况
│   ├── 通讯      WhatsApp / Telegram / 微信小程序 / iMessage / QQ / Lark / Discord / DingTalk
│   ├── 实例      已连接 client 与 node 的信号数据
│   ├── 会话      活动会话列表 + 默认设置
│   ├── 使用情况  token 额度与额度锁
│   └── 自动化    定时任务 / 触发器 / 工作流
├── 代理
│   ├── 代理      工作范围、可调用工具、sys prompt
│   ├── 技能      技能开关与参数
│   └── 节点      设备配置、能力与公开命令
└── 配置
    ├── 配置      系统级 config（并发、队列、VRAM/算力等）
    ├── 调试      网关快照、事件流、手动 RPC
    └── 日志      网关文件日志
```

### 3.2 分区规格

| 分区 | 展示内容 | 数据来源 | 当前状态 | MVP 行为 |
|---|---|---|---|---|
| **概览** | 服务商连通性（Auto Model 解析结果）、监听地址/端口、进程运行时长、活跃流数、最近错误 | `provider_config.summarize()` + 新增 `runtime/console.py` 采集 | 服务商部分已实现 | 复用现有检测结果，补「入口点」「健康」两张卡 |
| **通讯** | 各 IM 通道卡片：连接状态、账号、启停、测试发送 | 暂无。需 `services/comms/` 统一接口 | 未建 | 卡片列出支持列表，状态统一「未接入」 |
| **实例** | 浏览器客户端心跳：client_id、UA、ip、最后活跃、模式（chat/agent）；已连接 node 数 | 前端 `POST /api/console/heartbeat` + 内存/`data/state/instances.json` | 未建 | 心跳 + 90 秒过期即离线 |
| **会话** | 活动会话（SSE 进行中）、历史会话列表、默认参数入口 | `store.SessionStore` 已有；进行中会话需登记 | 历史会话已实现 | 复用 `/api/sessions`，补活动会话表 |
| **使用情况** | 今日/本月 token、请求数、平均时延、额度上限、额度锁状态 | 新增 `runtime/usage.py`（`data/state/usage.json`） | 未建 | 先做「估算 token + 额度锁」并标注估算 |
| **自动化** | 自动化任务列表、触发器、工作流、上次运行结果 | MOD 提供（自动化 MOD） | 未建 | 无 MOD 时显示空态 + 安装指引 |
| **代理** | 系统提示词、工作范围、工具白名单、模型覆盖 | `settings.system_prompt` + `loader` 工具注册表 | 部分在设置里 | 先复用基础设置字段，工具列表只读展示 |
| **技能** | 技能卡：名称、说明、开关、参数 | `loader` 技能注册表 + `data/state/skills.json` | 未建 | 开关落盘，禁用后不参与工具调用 |
| **节点** | 设备列表、能力标签、公开命令、配对状态 | 暂无 | 未建 | 空态 + 配对说明 |
| **配置** | 服务端可调项：并发上限、队列长度、历史窗口上限、算力/VRAM 检测值（只读） | 新增 `runtime/system_config.py`，仅白名单可写 | 未建 | 只做「只读检测 + 少量安全项」 |
| **调试** | 网关快照（进程/内存/端口）、事件流（最近 N 条）、手动 RPC 输入框 | 内存环形缓冲 + `psutil` 可选 | 未建 | 快照 + 事件只读；RPC 默认关闭，需显式开启 |
| **日志** | 日志文件列表、尾部 200 行、级别过滤、下载 | `logs/*.log`（新增 rotating handler） | 未建 | 只读 tail，不提供写操作 |

> 关键约束：表中「未建」的分区必须有明确 `reason` 文案，例如「通讯模块尚未接入」，并给出后续接入所需的最小接口，而不是显示 0 / 运行中。

---

## 4. 布局与交互

### 4.1 双层结构

- 基础设置沿用现有 `setup` 覆盖层（`index.html:59-90`），新增底部一行可点击的「高级功能设置 ▸」。
- 点击后进入全屏控制台覆盖层（`settings-console`），左侧三组导航（`控制 / 代理 / 配置`），右侧单页内容，顶部有「← 返回基础设置」。
- 折叠状态存 `localStorage["simchat.advanced"]`；**不写入服务端配置**，避免多客户端互相影响。

### 4.2 导航与页面切换

- 复用 openmaid 的 `data-page` 模式：`console-nav-item[data-section]` + `.settings-section[data-section]`。
- 三组标题不参与切换，只做视觉分组；移动端（<= 720px）折叠成顶部横向滚动标签。
- 分区切换保留滚动位置；`dirty` 表单在切换时弹确认。

### 4.3 页面骨架

```html
<div class="settings-console" id="settings-console" hidden>
  <header class="console-header">
    <button class="ghost-button" id="console-back">← 返回基础设置</button>
    <h2 data-block="console.title">高级功能设置</h2>
    <span class="settings-status" id="console-status"></span>
  </header>
  <div class="console-body">
    <aside class="console-nav">
      <div class="console-nav-group">
        <h4 data-block="console.group.control">控制</h4>
        <button class="console-nav-item is-active" data-section="overview">概览</button>
        <button class="console-nav-item" data-section="comms">通讯</button>
        <button class="console-nav-item" data-section="instances">实例</button>
        <button class="console-nav-item" data-section="sessions">会话</button>
        <button class="console-nav-item" data-section="usage">使用情况</button>
        <button class="console-nav-item" data-section="automation">自动化</button>
      </div>
      <div class="console-nav-group">
        <h4 data-block="console.group.agent">代理</h4>
        <button class="console-nav-item" data-section="agent">代理</button>
        <button class="console-nav-item" data-section="skills">技能</button>
        <button class="console-nav-item" data-section="nodes">节点</button>
      </div>
      <div class="console-nav-group">
        <h4 data-block="console.group.config">配置</h4>
        <button class="console-nav-item" data-section="system">配置</button>
        <button class="console-nav-item" data-section="debug">调试</button>
        <button class="console-nav-item" data-section="logs">日志</button>
      </div>
    </aside>
    <main class="console-content">
      <section class="setting-section" data-section="overview" data-state="loading"></section>
      <section class="setting-section" data-section="comms" hidden></section>
      <!-- ... 其余 10 个分区容器同构 ... -->
    </main>
  </div>
</div>
```

样式新增 `simchat/web/static/css/settings.css`，变量全部取 `chat.css:3-38` 的 `--accent / --text-muted / --border / --hover / --danger / --shadow`。

### 4.4 交互细则

1. **未接入态**：分区容器统一渲染 `state.empty`（图标 +「该模块尚未接入」+ `reason`），不显示假数字、不显示可点按钮。
2. **保存反馈**：右上角状态徽章「已保存 / 未保存 / 保存失败」+ toast，禁用 `alert()`。
3. **密钥字段**：沿用「已保存，留空保持不变」+ 掩码回显；通讯类 Bot Token 同样只写不读。
4. **危险操作**：恢复默认、清空会话、手动 RPC、删除节点必须二次确认，并写入审计事件（调试分区可见）。
5. **自动刷新**：概览/实例/使用情况 10 秒轮询（仅在对应分区可见时），其余按需拉取。
6. **键盘**：`Esc` 关闭（dirty 确认）、`Ctrl/Cmd+S` 保存当前分区、`[` / `]` 切换分区（可选）。

---

## 5. 数据模型

### 5.1 配置分层

| 文件 | 内容 | 写入方 |
|---|---|---|
| `data/config.json` | `provider` / `ollama` / `openai_compat` / `settings` | `provider_config.py`、新增 `settings.py` |
| `data/state/usage.json` | token/请求统计、额度与锁 | `usage.py` |
| `data/state/instances.json` | 客户端心跳（可重建，允许丢失） | `console.py` |
| `data/state/skills.json` | 技能开关与参数 | `skills` 服务 |
| `data/sessions/*.json` | 会话本体（已有） | `store.py` |
| `logs/*.log` | 运行日志（rotating） | 日志 handler |

`config.json` 在 v2 中新增 `settings` 段：

```json
{
  "settings": {
    "max_history": 40,
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": "",
    "send_with_enter": true,
    "show_token_bar": true,
    "theme": "system",
    "font_scale": 1.0,
    "quota": { "limit": 0, "period": "day", "lock": false }
  }
}
```

- `quota.limit = 0` 表示不限额；`lock` 为超额即拒绝新请求。
- 基础设置字段范围：`max_history` 4–200、`temperature` 0–2、`max_tokens` 128–32768、`font_scale` 0.8–1.4。
- `settings.py` 负责默认合并 + 范围校验 + 原子写（参考 `provider_config._write()`，`provider_config.py:446-455`）。
- **不改变门禁职责**：`settings` 不参与 `summarize()["available"]` 判断。

### 5.2 统一接口包络

所有控制台接口返回同一结构，前端只写一套渲染器：

```json
{
  "available": true,
  "generated_at": "2026-10-28T16:30:00+08:00",
  "reason": "",
  "data": {}
}
```

未接入时：`{"available": false, "reason": "通讯模块尚未接入", "data": null}`。

### 5.3 API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/settings` | 基础设置 + defaults + version + config_path |
| POST | `/api/settings` | 白名单保存基础设置 |
| POST | `/api/settings/reset` | `scope: settings \| all` |
| GET | `/api/console/overview` | 网关状态、入口点、健康摘要 |
| GET | `/api/console/comms` | 通讯通道列表与状态 |
| POST | `/api/console/comms/<id>/test` | 发送测试消息（未接入返回 501 语义） |
| GET | `/api/console/instances` | 客户端/node 心跳列表 |
| POST | `/api/console/heartbeat` | 浏览器心跳（client_id/ua/mode） |
| GET | `/api/console/sessions` | 活动会话 + 历史会话摘要（复用 `/api/sessions` 数据） |
| DELETE | `/api/console/sessions/<id>` | 结束活动会话 |
| GET | `/api/console/usage` | 今日/本月用量、额度、锁状态 |
| POST | `/api/console/usage/quota` | 设置额度与锁 |
| GET | `/api/console/automation` | 自动化任务/触发器/工作流（MOD 提供） |
| GET/POST | `/api/console/agent` | 系统提示词/工具白名单/范围 |
| GET/POST | `/api/console/skills` | 技能列表与开关 |
| GET/POST | `/api/console/nodes` | 节点列表与配置 |
| GET/POST | `/api/console/system` | 系统配置（只读检测 + 白名单可写） |
| GET | `/api/console/debug/snapshot` | 进程/端口/内存快照 |
| GET | `/api/console/debug/events` | 最近事件（环形缓冲） |
| POST | `/api/console/debug/rpc` | 手动 RPC（默认禁用） |
| GET | `/api/console/logs` | 日志文件列表 |
| GET | `/api/console/logs/<name>?tail=200` | 尾部读取 |

错误统一 `{error}`，HTTP 400/403/501；鉴权失败 401。

### 5.4 瘦客户端安全

- 监听 `0.0.0.0` 时必须有访问令牌（`SIMCHAT_ACCESS_TOKEN` 或配对码），否则只允许 `127.0.0.1`。
- 默认「只读浏览」：修改类接口（POST/DELETE）需要管理令牌；浏览器侧令牌存 `sessionStorage`，不落 cookie。
- 通讯 Bot Token、API Key 永不回显；`config.json` 类文件不通过静态路由暴露。
- 调试 RPC 默认关闭，开启需管理令牌 + 二次确认，每次调用写审计事件。

---

## 6. 方块 / MOD 扩展点

在 `ui_blocks.py:21-65` 的 `_DEFAULT_BLOCKS` 中登记（否则 `register_block_skin` 会 `KeyError`）：

| 分组 | block id |
|---|---|
| 基础 | `settings.title`、`settings.group.basic`、`settings.advanced`、`settings.save`、`settings.reset` |
| 控制台 | `console.title`、`console.back`、`console.group.control`、`console.group.agent`、`console.group.config` |
| 分区 | `console.section.overview`、`console.section.comms`、`console.section.instances`、`console.section.sessions`、`console.section.usage`、`console.section.automation`、`console.section.agent`、`console.section.skills`、`console.section.nodes`、`console.section.system`、`console.section.debug`、`console.section.logs` |
| 通用 | `console.state.empty`、`console.state.unavailable`、`console.state.loading` |

规则不变：MOD 只能换 `label / icon / hint / description / order`，不能改校验、保存、鉴权、门禁。

---

## 7. 实施阶段

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 双层骨架** | 基础设置扩展（服务商+对话+外观）+「高级功能设置」折叠 + 控制台外框 + 12 个分区「未接入」空态 | 折叠状态刷新后保持；未配置服务商时仍锁在服务商页；无假数据 |
| **P1 概览 / 会话 / 使用情况** | 概览三卡（网关/入口/健康）、活动会话表、token 统计与额度锁 | 概览与磁盘/真实进程一致；额度锁生效并可在日志中追溯；用量标注「估算」 |
| **P2 通讯 / 实例 / 自动化** | 通讯统一接口（先 QQ / Telegram / Lark 各一个）、心跳与实例表、自动化 MOD 列表 | 通讯可测试发送；实例 90 秒过期；无 MOD 时自动化空态正确 |
| **P3 代理 / 技能 / 节点** | 工具白名单、技能开关持久化、节点配对 | 技能开关重启后保持；禁用技能不参与调用；节点空态说明完整 |
| **P4 配置 / 调试 / 日志** | 系统检测与白名单配置、快照/事件/RPC、日志 tail | RPC 默认关闭；日志只读；所有危险操作有确认与审计 |

---

## 8. 风险与不做的事

1. **不画假数据**：openmaid 的 instance/sessions/usage/automation 全是静态占位，本方案一律空态或真实数据。
2. **不复活 openmaid**：只借导航、表单、卡片、读写模式；不引入粉紫主题、内联样式、假加载。
3. **不重复实现服务商逻辑**：通讯/代理/节点里的模型相关字段调用现有 `/api/providers`。
4. **多客户端一致性**：配置只存服务端；折叠状态、当前分区等纯 UI 状态存本地。
5. **用量口径**：Ollama 不返回真实 token 用量，需明确「估算」标签；OpenAI 兼容端点优先使用响应里的 usage。
6. **安全默认值**：默认只监听 `127.0.0.1`；对外部署必须配令牌；不提供未鉴权的 RPC/日志下载。

---

## 9. 附：关键引用

- openmaid 侧栏与页面容器：`openmaid.html:694-702`、`875/955/1061/1082/1103/1124/1145/1219/1278/1286/1294/1302`
- openmaid 表单/状态/控件：`openmaid.html:319-360`、`362-453`；`modern-ui.css:585-809`
- openmaid 配置读写：`ide-script.js:487-553`；后端 `openmaid_server.py:57-103`、`339-351`
- SimChat 现有入口与门禁：`index.html:59-90`；`provider_config.py:125-595`
- SimChat 主题变量：`chat.css:3-38`；方块接口：`ui_blocks.py:21-65`（默认方块）、`79-88`（皮肤注册）
- SimChat 会话存储：`store.py`；服务商测试：`provider_config.test()`
