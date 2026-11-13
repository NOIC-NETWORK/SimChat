# SimChat 客户端界面设计：桌面 IDE + 移动端（v1）

> 状态：设计方案 / 待评审
> 背景：2026-10-30 决策——先做完架构，再加入角色选择等体验功能。角色切换的前端 UI 已移除，后端 `/api/settings` 的 `character` 段保留（见 [runtime/settings.py](/runtime/settings.py)），本文档同时给出它的回归计划（§7）。
> 目标：定义两端形态——**桌面端做完整 IDE 界面，移动端只做对话与观察（没有 IDE）**，并明确两端共享什么、各自做什么。

---

## 1. 设计原则

1. **架构先行**：先把 Agent 运行时、审批链路、MOD 平台、自动化引擎的界面骨架搭完，再往里放"角色 / 人格 / 皮肤"这类体验层功能。体验功能必须挂在稳定的骨架挂点上，而不是反过来。
2. **服务端是唯一事实源**：延续 [settings-page-design.md](/docs/settings-page-design.md) 的瘦客户端原则。浏览器 / WebView 只做渲染与提交，不做本地推断，不画假数据；未接入的模块返回 `{available:false, reason}` 并展示"该模块尚未接入"。
3. **移动端没有 IDE**：IDE 的多面板、时间线、Inspector 是桌面形态。移动端 = 对话 + 观察 + 审批 + 通知，单列堆栈导航，同一套 API 消费。
4. **一套后端，两个壳**：桌面与移动不复制业务逻辑，差异只在布局与导航。后端 API（`/api/*`）是两端唯一的公共契约。
5. **未接入就是未接入**：高级控制台三分区十二区的空态规则原样继承，禁止 Mock。

---

## 2. 端策略总览

| 端 | 形态 | 载体 | 能力范围 |
|---|---|---|---|
| 桌面 | **完整 IDE** | 桌面浏览器（`python -m web`） | 对话、Agent 任务、工具审批、MOD/技能管理、自动化、高级控制台、命令面板 |
| 移动 | **对话与观察** | 移动浏览器 / 鸿蒙 ArkUI WebView 壳（[harmony-webview/](/harmony-webview)） | 会话列表、对话、Agent 运行详情（只读）、审批操作、基础设置、技能与自动化状态查看 |
| 共享 | — | Flask 同源服务 | 同一套 `/api/*`、同一套会话存储、同一套 SSE 事件流 |

断点策略（响应式，单一代码库）：

| 断点 | 布局 |
|---|---|
| ≥ 1024px | IDE 完整形态：Activity Bar + Side Bar + 工作区 + 右侧 Inspector + 底部 Panel |
| 768–1023px | IDE 折叠形态：Activity Bar 保留，Side Bar / Inspector 变为覆盖式抽屉，底部 Panel 默认收起 |
| < 768px | 移动页面形态：单列堆栈 + 底部 Tab，IDE 专属面板一律不渲染 |

---

## 3. 信息架构：两端页面地图

| 模块 | 桌面（IDE） | 移动端 | 说明 |
|---|---|---|---|
| 对话 | Activity「对话」：Side Bar 会话列表 + 工作区消息流 + composer | Tab「对话」：会话列表页 → 对话页 | 两端共用消息流与 composer 组件 |
| Agent 运行 | Activity「任务」：运行列表 + ReAct 时间线 + 工具 Inspector | 页「任务详情」：只读时间线 + 审批按钮 | 移动端只读观察，不发起新任务？——**可发起**，入口在对话页模式开关 |
| 审批 | 工作区内嵌审批卡 + 任务 Activity 审批中心 | 审批卡（全屏弹层） | 复用 `POST /api/agent/approve` |
| MOD / 技能 | Activity「扩展」：MOD 列表 + 开关 + 工具风险分级 | 页「技能」：只读列表 + 开关 | 数据来自 `GET /api/agent/tools` 与 MOD loader |
| 自动化 | Activity「自动化」：DAG 列表 + 运行记录 | 页「自动化」：只读状态列表 | 未接入前保持空态卡 |
| 设置 | Activity「设置」：基础设置 + 高级控制台（3 组 12 区） | 页「设置」：基础设置 + 高级控制台简化为分组列表 | 表单组件两端复用 |
| 首次启动 | 注册页 `/register` + 服务商配置 | 同桌面（单列渲染） | 已有 `has_profile()` 门禁 |

---

## 4. 桌面端 IDE 界面

### 4.1 六区布局

```
┌───┬──────────────┬──────────────────────────────┬───────────────┐
│ A │  B  Side Bar │  C  工作区（Workarea）        │ D  Inspector  │
│ c │  上下文列表   │  消息流 / ReAct 时间线 /      │  会话信息      │
│ t │              │  审批卡 / 表单                │  Token 用量   │
│ i │              │                              │  工具调用详情  │
│ v │              │                              │               │
├───┴──────────────┴──────────────────────────────┴───────────────┤
│ E  底部 Panel：事件流 / 沙箱输出 / 日志（可收起）                    │
├─────────────────────────────────────────────────────────────────┤
│ F  状态栏：服务商 · 模型 · 模式(Chat/Agent) · 审批模式 · 运行状态    │
└─────────────────────────────────────────────────────────────────┘
```

- **A Activity Bar（最左图标列）**：五个 Activity 的入口——对话、任务、扩展、自动化、设置。对应现有 sidebar 与控制台导航的重组，不新增后端。
- **B Side Bar**：随 Activity 切换内容的列表区（会话列表 / 运行列表 / MOD 列表 / DAG 列表 / 设置分组）。现有 `#session-list` 迁移至此。
- **C 工作区**：主内容区。对话 Activity 下就是现有 `#conversation` + composer；任务 Activity 下是 ReAct 时间线。
- **D Inspector（右侧面板）**：选中即显示的上下文面板——当前会话的模型/参数摘要、token 估算、选中工具调用的入参/出参/风险分级。可整体收起。
- **E 底部 Panel**：SSE 原始事件流（`spec/events.md` 的 13 事件）、沙箱输出、日志。调试向，默认收起。
- **F 状态栏**：常驻一行——服务商状态点、当前模型（`provider::model`）、Chat/Agent 模式、审批模式、`status-dot` 运行状态。把现有 topbar 的零散状态收拢。

### 4.2 五个 Activity

| Activity | 内容 | 现状映射 |
|---|---|---|
| 对话 | 会话列表 + 消息流 + composer（附件 / 模型选择 / 模式开关 / Token 估算栏） | 现有主界面平移；composer 不变 |
| 任务 | Agent 运行列表（`GET /api/agent/tasks`）+ 选中运行的 ReAct 时间线 + 审批中心 | 新增视图；数据接口已存在 |
| 扩展 | 已加载 MOD 列表（loader `list_mods()`）、skill 工具与风险分级（`GET /api/agent/tools`）、启停开关 | 新增视图；loader 能力已存在 |
| 自动化 | DAG 列表、调度状态、运行记录、配额 | 未接入空态（automation/ 引擎已有，待 API 化） |
| 设置 | 基础设置 + 高级控制台（现三分区十二区原样并入） | 现有 setup + console 迁移为 Activity 内双层级 |

### 4.3 关键视图：ReAct 时间线与审批

- **时间线**：按 `run_id` 回放 SSE 事件（`/api/agent/run` 流 + `/api/agent/tasks` 存档），每回合渲染为「思考 → 工具调用（入参折叠）→ 工具结果 → 观察」节点链，`final` 事件渲染为完整 Markdown（沿用 marked.js + DOMPurify）。
- **审批卡**：`approval_request` 事件触发。桌面端在工作区与任务 Activity 双入口展示；操作三键 = 批准 / 拒绝 / 中止（`/api/agent/approve`、`/api/agent/abort`）。审批卡必须显示工具名、风险分级、影响范围（文件路径 / 命令内容）。
- **工具 Inspector**：时间线上任一工具节点可固定到右侧 Inspector，展示完整入参/出参/耗时/风险分级（`GET /api/agent/tools` 的分级表）。

### 4.4 命令面板与快捷键

- `Ctrl+K` 命令面板：新对话、切换 Activity、跳会话、切换模型、切换审批模式。命令 = 前端动作注册表，不新增后端。
- 快捷键：`Ctrl+B` 收起 Side Bar，`Ctrl+J` 收起底部 Panel，`Ctrl+,` 打开设置 Activity，`Esc` 关弹层（沿用现有 Esc 逻辑）。

### 4.5 实现策略

- 不推倒重来：现有 `index.html` 的 sidebar / conversation / composer / setup / console 五块全部保留，改造为 IDE 布局的五个槽位；`chat.js` 的模块边界（providerStore / 设置 / 控制台）不动。
- CSS 用布局容器切换（`body[data-layout="ide"]`）实现断点形态，消息流与 composer 组件两端共享同一 DOM 结构与样式变量。

---

## 5. 移动端页面（无 IDE）

### 5.1 导航模型

单列堆栈 + 底部 Tab（三 Tab）：

```
┌─────────────────────────┐
│                         │
│       页面内容            │   ← 每屏一个焦点，无分栏
│                         │
├────┬────────┬───────────┤
│ 对话 │  任务    │  我的      │   ← 底部 Tab
└────┴────────┴───────────┘
```

- **对话**：会话列表 → 对话页（两级堆栈）。
- **任务**：Agent 运行列表 → 运行详情（只读时间线 + 审批卡）。
- **我的**：设置、技能、自动化状态、关于。

### 5.2 页面详述

| # | 页面 | 内容 | 交互要点 |
|---|---|---|---|
| M1 | 会话列表 | 全部会话 + 置顶「新对话」大按钮 | 左滑删除；点进对话页；数据 `GET /api/sessions` |
| M2 | 对话页 | 消息流 + 底部 composer（精简：附件 / 模型选择 / 发送） | 模式开关与审批模式收进顶栏菜单；键盘弹起自适应；流式渲染复用桌面逻辑 |
| M3 | Agent 运行详情 | 只读 ReAct 时间线（折叠工具节点）+ 挂起时顶部常驻审批条 | 审批条点开全屏审批卡（工具/风险/影响范围 + 批准/拒绝/中止）；禁止编辑工作区 |
| M4 | 设置 | 基础设置单列表单 + 「高级功能」入口 | 高级控制台十二区在移动端渲染为分组列表，未接入区保持空态卡；保存走同一 `POST /api/settings` |
| M5 | 技能 | 已启用 skill 列表 + 工具风险分级标签 | 只读 + 开关；数据 `GET /api/agent/tools` |
| M6 | 自动化 | DAG 状态列表 + 最近运行记录 | 只读；未接入时空态 |
| M7 | 首次启动 | `/register` + 服务商配置单列向导 | 与桌面共用表单组件 |

### 5.3 移动端明确不做

- 不做 IDE 三栏/四栏布局、不做拖拽分栏、不做时间线编辑。
- 不做底部 Panel / Inspector / 命令面板。
- 不做 MOD 开发向功能（打包、签名、发布）——移动端是消费端，不是开发端。
- 桌面 Activity 中的任务**发起**能力保留（对话页可切 Agent 模式发起），但运行中任务的管理细节（工作目录、max_turns 等）只在桌面端暴露。

---

## 6. 共享层与 API 映射

两端消费同一 API，映射表：

| 功能 | API | 桌面 | 移动 |
|---|---|---|---|
| 服务商配置 / 探测 | `GET/POST /api/providers`、`/api/providers/test`、`/api/providers/discover` | 设置 Activity | M4 / M7 |
| 会话 | `GET/POST /api/sessions`、`GET /api/sessions/<sid>` | 对话 Activity Side Bar | M1 / M2 |
| 对话 | `POST /api/chat` | 对话 Activity | M2 |
| Agent 运行 | `POST /api/agent/run`（SSE）、`GET /api/agent/tasks`、`DELETE /api/agent/tasks/<sid>` | 任务 Activity | M3 |
| 审批 / 中止 | `POST /api/agent/approve`、`POST /api/agent/abort` | 工作区审批卡 | M3 审批条 |
| 工具清单 | `GET /api/agent/tools` | 扩展 Activity | M5 |
| 设置 | `GET/POST /api/settings`、`POST /api/settings/reset` | 设置 Activity | M4 |
| 个人资料 | `GET/POST /api/profile` | 注册页 / 我的 | M7 / 我的 |

组件复用：消息流渲染（Markdown + DOMPurify）、composer、审批卡、设置表单控件、空态卡——两端同一实现，仅容器布局不同。移动端新增的只有：底部 Tab、堆栈路由、审批条、键盘适配。

---

## 7. 延后项回归计划：角色选择

角色切换前端已移除（本次改动），后端保留：`runtime/settings.py` 的 `character` 段（`active` + `profiles: {id: {name, narration}}`，支持局部合并与恢复默认），立绘资源仍在 `web/static/sprites/characters/`。

回归时机：**桌面 IDE 布局 + 移动端页面骨架完成后**。

回归形态（架构完成后的挂点）：

1. **欢迎页吉祥物**：桌面 IDE 的工作区空态与移动端 M1 顶部展示当前角色立绘 + 解说文字；数据 `GET /api/settings` 的 `character` 段。
2. **人格绑定 agent-config**：角色的名称/解说升级为 agent-config MOD 的人格展示位（人设、主题与立绘一体），角色选择面板归入「扩展」Activity / 移动端 M5，而不是散落在基础设置。
3. **前端实现清单**（到时照此重建）：欢迎页舞台、设置面板卡片、`normalize/render/sync` 三函数、事件绑定——昨天的实现可作为参考基线（git 历史 20261029 版本 chat.js）。

---

## 8. 里程碑顺序（架构优先）

| 阶段 | 内容 | 前置 |
|---|---|---|
| A1 | IDE 布局骨架（六区 + Activity 切换 + 断点形态），现有功能平移 | 无 |
| A2 | 任务 Activity：运行列表 + ReAct 时间线 + 审批中心 | A1 |
| A3 | 扩展 Activity：MOD 列表 + 工具风险分级 + 开关 | A2 |
| A4 | 移动端页面骨架（Tab + 堆栈路由），M1/M2/M4 先行 | A1 |
| A5 | 移动端 M3/M5/M6（任务详情 / 技能 / 自动化） | A2–A3 |
| A6 | 自动化 Activity API 化 + 两端接通 | automation/ 引擎 API 化 |
| B1 | **角色选择回归**（§7） | A1–A5 全部完成 |
