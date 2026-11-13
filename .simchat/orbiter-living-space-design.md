# SimChat Orbiter 与「客厅 / 卧室」Agent 空间设计

> 状态：设计草案（未实现）
> 日期：2026-10-31
> 适用仓库：`NOIC-NETWORK/SimChat`（检出提交 `e5a17c3`）
> 用途：可直接交给 Trae 作为实现任务书；本文档只描述设计与分期，不包含已落地代码。
> 缘起：这个想法最早来自高中时写的一版 TUI——一个主界面 + 若干可切换面板。现在把它落成 Web + MOD 体系。

---

## 0. TL;DR

一句话：**把 SimChat 的 Web 宿主做成一个“房子”。**

| 空间 | 技术对象 | 作用 |
|---|---|---|
| 客厅 | `index.html` 主界面 | 所有 Agent 的公共空间，用 `/@` 唤起 |
| 卧室 | MOD 自带的 `room.html` | 某个 Agent 的私有 UI，iframe 隔离 |
| 住户 | `AgentDefinition`（纯数据） | 用户添加的 Agent |
| 物业 | `Orbiter` | 把任务分给多个住户并汇总结果 |
| 房产证 | `manifest.json` + 签名 | MOD 的身份与权限 |
| 家具 | tools / skills | Agent 能用的能力 |

四条原则：

1. **Agent 是数据，不是代码**——用户上传的 Agent 不应该执行任意 Python。
2. **工具是权限**——Agent 只能用宿主明确授权的工具。
3. **房间是沙箱**——MOD 的 UI 不能碰宿主 DOM、不能拿凭据。
4. **Orbiter 是调度**——它不产生能力，只负责把任务分给合适的 Agent。

---

## 1. 先盘点现状（哪些已经有了，哪些其实没有）

| 能力 | 现状 | 位置 | 结论 |
|---|---|---|---|
| MOD 四类型 / manifest / schema | 已有 | `spec/mod-manifest.schema.json` | 可直接扩展 |
| MOD 加载器（校验/依赖/签名/沙箱） | 已有 | `loader/lifecycle.py` | 可复用 |
| Web 宿主接入 ModLoader | **没有** | `web/__init__.py` 只创建 `SimChatCore` | 必须先补 |
| `ui.slot` hook | 只在 schema/spec 声明 | `spec/hooks.md`、`loader/manifest.py` | 运行时未实现 |
| `frontend_entry` | 只在 `ModeSpec` 里序列化 | `sdk/python/simchat_mod/__init__.py` | 宿主未加载 |
| `/api/mods` | **没有** | `web/__init__.py` 现有路由无 MOD | 必须新增 |
| MOD 上传 / 安装 | **没有** | CLI 只有 `init/pack/verify/publish/list` | 必须新增 |
| Orbiter | 只有 UI 预留开关 | `index.html:235`、`chat.js:811-814`、`chat.js:2680` | 需要真正实现 |
| 子 Agent 协同 | **没有** | `runtime/agent/loop.py` 是单线 ReAct | 需要新模块 |
| 房间 UI / iframe 桥 | **没有** | — | 全新设计 |
| SSE 事件契约 | 已有 13 个核心事件 | `spec/events.md` | 只能加，不能改 |

**关键发现：本仓库的 Web UI 目前根本没有加载 MOD。** `ModLoader` 只被外部宿主（`lmbrew.py`，不在本仓库）或 CLI 使用；`python -m web` 启动的是一个“裸壳”。所以“客厅/卧室”的第一步不是做 UI，而是**让 Web 宿主真正接上 MOD 系统**。

---

## 2. 概念模型

```text
┌──────────────────────────────────────────────┐
│ 客厅  index.html                              │
│   ┌──────┐  ┌──────┐  ┌──────┐               │
│   │ 写作 │  │ 检索 │  │ 日程 │  ← 住户 Agent   │
│   └──┬───┘  └──┬───┘  └──┬───┘               │
│      │ /@writer │ /@search  │ /@daily          │
│   ┌──▼──────────▼───────────▼──┐              │
│   │ Composer：/@ 调用 + Orbiter │              │
│   └──────────────┬──────────────┘              │
└──────────────────┼─────────────────────────────┘
                   │ postMessage / SSE
          ┌────────▼────────┐
          │ 卧室 room.html   │  ← MOD 自带 UI（iframe 沙箱）
          └─────────────────┘
```

| 房子概念 | 技术对象 | 归属 | 生命周期 |
|---|---|---|---|
| 客厅 | `web/templates/index.html` | 宿主 | 常驻 |
| 房间 | `Room`（MOD 内静态 UI） | MOD | 打开/关闭 |
| 住户 | `AgentDefinition` | MOD（agent-config） | 随 MOD 加载 |
| 物业 | `Orbiter` | 宿主 | 常驻 |
| 门牌 | `agent_id = <mod_id>.<agent_id>` | 宿主命名空间 | 不可重复 |
| 房产证 | `manifest.json` + 签名 | MOD 作者 | 安装时校验 |
| 家具 | 已注册的 tools | 宿主 + skill MOD | 随 MOD 加载 |
| 门禁 | capability / approval | 宿主 | 每次调用 |

---

## 3. Agent 定义：扩展 `agent-config`，不新增可执行类型

### 3.1 决策

MVP **不新增 `type: "agent"`**，而是把 `agent-config` 从“单人设”升级为“多 Agent 包”：

- 理由一：Agent 本质是**数据**（名字、头像、提示词、工具白名单、模型参数、房间入口），不需要执行代码。
- 理由二：新增可执行类型意味着 ABI major、沙箱扩展、审计升级，成本远大于收益。
- 理由三：`agent-config` 现有语义就是“纯数据 MOD，禁止 `entry`”，正好符合“用户上传 Agent”的安全边界。

只有未来 Agent 需要自定义 Python 行为时，再引入 `type: "agent"`。

### 3.2 manifest 扩展示例

```json
{
  "id": "example.writer",
  "type": "agent-config",
  "name": "写作间",
  "version": "0.1.0",
  "abi": "lmbrew-mod/1",
  "license": "MIT",
  "agents": [
    {
      "id": "writer",
      "name": "写作助手",
      "avatar": "web/avatar.svg",
      "description": "改写、润色、结构化长文",
      "system_prompt_file": "prompts/writer.md",
      "tools": ["read_file", "web_search"],
      "params": { "temperature": 0.7, "max_tokens": 1024 },
      "orbiter": { "enabled": true, "roles": ["writing"], "priority": 10 }
    }
  ],
  "rooms": [
    {
      "id": "writer.room",
      "agent": "writer",
      "title": "写作间",
      "entry": "web/room.html",
      "size": { "width": 720, "height": 480 }
    }
  ]
}
```

### 3.3 字段规则

- `agents[].id`：只在 MOD 内唯一；宿主侧完整 id 为 `<mod_id>.<agent_id>`。
- `agents[].tools`：必须是**已加载 tool 的子集**；未知 tool → 该 Agent 标记 failed（不阻断其他 Agent）。
- `agents[].system_prompt_file`：包内相对路径，必须存在，禁止 `..`。
- `agents[].room`：可省略；若省略，宿主按 `rooms[].agent` 自动匹配第一个房间。
- `rooms[].entry`：包内相对路径，必须是静态文件，不允许 `entry` 式代码执行。
- `orbiter.roles`：自由标签数组，供调度器匹配；`priority` 越大越优先。
- 所有新增字段都是**可选**，旧 MOD 不受影响。

---

## 4. 客厅：`index.html` 与 `/@` 调用

### 4.1 布局改动

在现有 composer 上方加一条“轨道”：

```text
┌──────────────────────────────────────────────┐
│  消息区                                       │
├──────────────────────────────────────────────┤
│  Agent 轨道： [头像 写作] [头像 检索] [＋安装]  │
├──────────────────────────────────────────────┤
│  [附件] [模型]        [Orbiter] [审批] [发送]  │
└──────────────────────────────────────────────┘
```

- 每个 Agent 卡片显示：头像、名字、状态（idle / working）、房间徽章。
- 点击卡片：打开该 Agent 的房间（如果有）。
- 点击「＋安装」：打开 MOD 安装面板（见 §7）。
- 没有 Agent 时：空状态文案 + “去安装一个 MOD”。

### 4.2 `/@` 语法

| 输入 | 行为 |
|---|---|
| `/@` | 打开 Agent 面板（模糊搜索） |
| `/@writer` | 打开 writer 的房间（没有房间则聚焦与该 Agent 的会话） |
| `/@writer 帮我改这段` | 直接发给 writer，客厅显示流式输出 |
| `/@all 帮我调研并写成文章` | 交给 Orbiter 多 Agent 协同 |
| `\/@` | 转义，按普通文本发送 |

解析规则：

- 只在消息**开头**识别，避免与邮箱、路径冲突。
- Agent id 大小写不敏感，展示名可中文。
- 未知 id → 提示“没有这个住户”，并展示相近 id。
- 同一会话可以切换 Agent，但会话记录写入 `agent_id` 命名空间，避免串话。

### 4.3 会话与状态

- `session.agent_id` 记录当前 Agent；`/api/sessions` 返回值增加该字段。
- Agent 独立会话 id：`agent_<mod>_<agent>_<sid>`。
- 客厅默认会话保持“无 Agent / 普通对话”，不强制绑定。
- Orbiter 运行使用父会话，子 Agent 使用子会话，并记录 `parent_sid`。

---

## 5. 卧室：MOD 自带 UI（Room）

### 5.1 房间契约

一个 Room 就是 MOD 包里的一组静态文件：

```text
examples/agent-writer/
├── manifest.json
├── prompts/writer.md
└── web/
    ├── avatar.svg
    └── room.html      # 自带 JS/CSS，可以是单文件
```

宿主提供：

- `GET /api/rooms`：列出可用房间。
- `GET /api/rooms/<room_id>/`：返回 `room.html`。
- `GET /api/rooms/<room_id>/<path>`：返回房间静态资源，严格路径校验（禁止 `..`、绝对路径、符号链接）。

### 5.2 隔离方式

MVP 使用 **iframe + `sandbox="allow-scripts"`**：

```html
<iframe
  sandbox="allow-scripts"
  src="/api/rooms/example.writer.writer.room/"
  referrerpolicy="no-referrer">
</iframe>
```

硬约束：

- **绝不使用 `sandbox="allow-scripts allow-same-origin"`**——这两项组合等于没沙箱。
- 房间是**不透明源（opaque origin）**，不能读宿主 `localStorage`、cookie、DOM。
- 房间静态资源响应加 `Access-Control-Allow-Origin: *`（仅 GET），让不透明源能取自己的资源。
- 房间响应加 CSP：`default-src 'self' data:; script-src 'self' 'unsafe-inline'; connect-src 'self'`。
- 若未来需要更强隔离：把房间服务放到独立端口/独立源，或使用 `srcdoc` + 内联资源。

### 5.3 桥协议（postMessage）

宿主 → 房间：

```json
{ "type": "simchat.room.init", "agent": {...}, "theme": {...}, "locale": "zh-CN", "session": {...} }
{ "type": "simchat.room.event", "event": "token", "data": { "content": "..." } }
{ "type": "simchat.room.state", "data": { "status": "idle|working|error" } }
```

房间 → 宿主：

```json
{ "type": "simchat.room.send", "text": "帮我写一段" }
{ "type": "simchat.room.open_agent", "agentId": "example.writer.writer" }
{ "type": "simchat.room.close" }
{ "type": "simchat.room.resize", "height": 520 }
{ "type": "simchat.room.log", "level": "info", "message": "..." }
```

宿主侧校验：

- `event.source === iframe.contentWindow`；
- 只接受白名单 `type`；
- `text` 长度上限（例如 32 KB）；
- 速率限制（例如每分钟 20 条）；
- 房间只能操作**自己的 Agent**，不能 `open_agent` 到别的住户（MVP 禁止跨房间调用）。

### 5.4 最小房间示例

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    body { font: 14px/1.6 system-ui; margin: 0; padding: 16px; background: #1b1b1f; color: #eee; }
    textarea { width: 100%; height: 96px; background: #26262c; color: #eee; border: 1px solid #444; border-radius: 8px; padding: 8px; }
    button { margin-top: 8px; padding: 8px 16px; border-radius: 8px; border: 0; background: #6c5ce7; color: #fff; }
    #log { white-space: pre-wrap; margin-top: 12px; color: #bbb; }
  </style>
</head>
<body>
  <textarea id="input" placeholder="和写作助手说话…"></textarea>
  <button id="send">发送</button>
  <div id="log"></div>
  <script>
    const send = (msg) => parent.postMessage(msg, "*");
    send({ type: "simchat.room.init.ack" });

    document.getElementById("send").onclick = () => {
      const text = document.getElementById("input").value.trim();
      if (!text) return;
      send({ type: "simchat.room.send", text });
      document.getElementById("input").value = "";
    };

    addEventListener("message", (e) => {
      const msg = e.data || {};
      if (msg.type === "simchat.room.event" && msg.event === "token") {
        document.getElementById("log").textContent += msg.data.content;
      }
      if (msg.type === "simchat.room.init") {
        document.getElementById("log").textContent = "已连接：" + msg.agent.name + "\n";
      }
    });
  </script>
</body>
</html>
```

---

## 6. Orbiter：从 UI 预留到真正的调度器

### 6.1 定义

Orbiter 不是“更大的 Agent”，而是**任务路由器 + 子 Agent 调度器 + 结果汇总器**。

现有代码里它只是一个按钮：

- `web/templates/index.html:235`：`Orbiter：调用子 Agent 协同处理任务（预留）`
- `web/static/js/chat.js:811-814`：只切换 `.on` 样式，不接后端
- `web/static/js/chat.js:2680`：绑定该按钮

### 6.2 v1 算法（先确定性，后 LLM）

MVP 不引入“LLM 选 Agent”，避免额外成本和不可控：

1. 收集所有 `orbiter.enabled=true` 的 Agent。
2. 按 `roles`、`description`、关键词与任务文本匹配打分。
3. 取 top K（默认 3）；用户可用 `/@all` 或显式 `/@writer /@search` 固定。
4. 顺序执行：每个子 Agent 只拿到自己的 system prompt + 自己的工具白名单 + 共享的任务摘要。
5. 汇总：输出最终答案，并保留每个子 Agent 的独立结果。

后续可加可选 LLM Planner，但必须保留“用户可固定 Agent”的逃生通道。

### 6.3 预算与失败策略

- `max_agents`：默认 3，最大 5。
- 每个子 Agent `max_turns`：默认 3，最大 10。
- 总 token 预算：默认父会话预算的 60%。
- 子 Agent 失败：默认 `continue`（记录失败），全部失败才返回 `error`。
- 用户 abort：传播到所有在跑的子 Agent。
- 所有工具审批仍然走宿主，不允许 Orbiter 绕过。

### 6.4 SSE 事件扩展

在现有核心事件之外新增（`schema=2`，旧前端 `default` 忽略）：

| 事件 | 关键字段 | 说明 |
|---|---|---|
| `orbiter_started` | `run_id, agents[]` | Orbiter 流第一帧 |
| `orbiter_plan` | `steps[], selected[]` | 选中的 Agent 与顺序 |
| `subagent_started` | `agent_id, role` | 子 Agent 开始 |
| `subagent_token` | `agent_id, content` | 子 Agent 增量 |
| `subagent_result` | `agent_id, ok, output, error` | 子 Agent 结束 |
| `orbiter_final` | `content, results[]` | 汇总结果 |

约束：

- 不改现有 13 个核心事件名与语义。
- 不把子 Agent 的 `token` 混进父流，避免前端状态错乱。
- 每个流恰好一个 `orbiter_started` 与一个终结事件。

---

## 7. 用户上传 / 安装 MOD

### 7.1 两条添加 Agent 的路径

**路径 A（MVP）：上传 MOD 包。**

用户拿到一个 `.zip`（manifest + prompts + web/room.html + 资源），在客厅点「＋安装」上传，宿主校验后落到 `mods/<id>/`，Agent 立即出现在轨道上。

**路径 B（后续）：客厅内“新建 Agent”向导。**

表单填：名字、头像、提示词、工具白名单、是否带房间。宿主在本地生成一个最小 `agent-config` MOD（`mods/local.<slug>/`），再走同一套加载流程。这样用户不用离开客厅就能“添加住户”。

### 7.2 安装 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/mods` | 列出已安装 MOD、Agent、Room、状态 |
| `POST` | `/api/mods/install` | multipart 上传 zip，校验并安装 |
| `POST` | `/api/mods/<id>/enable` | 启用（重载） |
| `POST` | `/api/mods/<id>/disable` | 停用 |
| `DELETE` | `/api/mods/<id>` | 卸载（需确认） |
| `POST` | `/api/agents/<agent_id>/run` | 以指定 Agent 发起 SSE 运行 |

### 7.3 安装校验流水线

```text
上传 zip
  → 大小/类型限制
  → 解压到临时目录（防 zip-slip、禁符号链接）
  → manifest schema 校验
  → id 冲突检查
  → 依赖/版本检查
  → 签名/完整性校验（binary 必填；community 可选）
  → 用户同意页（列出 capabilities / tools / rooms）
  → 移动到 mods/<id>/
  → loader.discover() 重载
  → 失败则回滚并保留原状态
```

### 7.4 热重载边界

- `ModLoader.discover()` 会重建注册表，但沙箱子进程需要正确清理。
- MVP：安装后重载 + 提示“部分变更需重启生效”。
- 不承诺“所有 MOD 热插拔”，尤其是已启动的 sandbox 进程。

---

## 8. 安全边界（这是这个点子能不能成立的关键）

| 风险 | 规则 |
|---|---|
| Agent 执行任意代码 | Agent 只能是数据；代码能力走 skill MOD，且受 capability 约束 |
| 房间偷宿主数据 | iframe 不透明源 + 无 `allow-same-origin`；桥协议白名单 |
| 房间直接调工具 | 禁止；房间只能发消息，工具调用由宿主 Agent 执行 |
| Agent 越权用工具 | `agents[].tools` 是宿主已启用工具的子集；未知工具拒绝 |
| 恶意 zip | zip-slip、符号链接、超大文件、路径穿越全部拒绝 |
| 供应链 | 签名 + 完整性 + 吊销列表；社区 MOD 显示信任徽章 |
| 跨 Agent 串话 | 会话按 `<mod>.<agent>` 命名空间隔离；默认不共享记忆 |
| Prompt 注入 | 房间内容与 MOD 提示词都视为不可信输入；本体安全闸门始终生效 |
| 审批绕过 | Orbiter 与子 Agent 都不能绕过宿主审批 |

一句话：**客厅可以热闹，但每扇卧室门都必须有锁。**

---

## 9. ABI 变更清单

| 变更 | 类型 | 说明 |
|---|---|---|
| manifest 新增可选 `agents` | minor | 旧 MOD 不受影响 |
| manifest 新增可选 `rooms` | minor | 仅 agent-config 使用 |
| 新增 hook `ui.room` | minor | 建议标 experimental |
| 新增 SSE 事件 `orbiter_*` / `subagent_*` | minor | 旧前端忽略未知事件 |
| `abi` 字段 | 待决 | 目前是 const `lmbrew-mod/1`；若要显式表达 minor，建议放宽为 pattern `^lmbrew-mod/1(\.[0-9]+)?$`，房间/Orbiter 用 `lmbrew-mod/1.1` |

兼容规则：

- 旧宿主加载新 MOD：未知 hook → fail-closed（预期行为）。
- 新宿主加载旧 MOD：必须正常。
- 新增事件不得复用现有核心事件名。

---

## 10. 分期与验收

### Phase 0：Web 宿主接入 MOD 系统（前置，必须先做）

- `web/__init__.py` 启动时创建 `ModLoader`、`discover()`、`set_global_loader()`。
- 新增 `GET /api/mods`，返回 `list_mods()`。
- 验收：`mods/` 下 8 个 MOD 在 Web 端可见；失败的 MOD 不拖垮启动。

### Phase 1：客厅 + `/@` + Agent 直连

- 新增 `agents` 注册表（从 manifest 收集）。
- `index.html` 增加 Agent 轨道与 `/@` 面板。
- `POST /api/agents/<id>/run` 走现有 Agent SSE。
- 验收：安装 `examples/agent-writer` 后，`/@writer 你好` 能流式返回；未知 Agent 有明确错误。

### Phase 2：卧室（Room）

- 新增房间静态服务与 iframe 外壳。
- postMessage 桥协议 + 白名单 + 限流。
- 验收：房间能发消息并收到 token；房间无法读宿主 DOM；路径穿越被拒绝。

### Phase 3：Orbiter v1

- `runtime/orbiter/`：候选打分、顺序调度、汇总。
- 新增 `orbiter_*` / `subagent_*` SSE 事件。
- 验收：`/@all` 选中 2 个 Agent 顺序执行并汇总；预算/失败/abort 行为正确。

### Phase 4：上传 / 安装

- `/api/mods/install`、启用/停用/卸载、同意页。
- 验收：合法 zip 安装成功；恶意 zip 被拒；签名校验生效；安装后可立即使用。

---

## 11. 代码改动地图（给 Trae 的精确落点）

| 文件 | 改动 |
|---|---|
| `spec/mod-manifest.schema.json` | 新增 `agents`、`rooms`；考虑放宽 `abi` pattern |
| `spec/hooks.md` | 新增 `ui.room`（experimental） |
| `loader/manifest.py` | 校验 `agents` / `rooms` / 路径 / tool 白名单 |
| `loader/lifecycle.py` | 收集 agents/rooms；新增 `list_agents/get_agent/list_rooms/get_room` |
| `loader/agents.py`（新） | Agent 注册表与命名空间合并 |
| `web/__init__.py` | 实例化 ModLoader；注册新蓝图 |
| `web/mods.py`（新） | `/api/mods*`、安装、启用/停用 |
| `web/rooms.py`（新） | 房间静态资源服务 + 安全头 |
| `web/agents.py`（新） | `/api/agents*` 运行入口 |
| `web/templates/index.html` | Agent 轨道、`/@` 面板、房间外壳 |
| `web/static/js/orbiter.js`（新） | slash 解析、Agent 面板、房间桥、Orbiter 事件 |
| `web/static/css/orbiter.css`（新） | 轨道 / 房间 / 面板样式 |
| `runtime/agents.py`（新） | AgentDefinition → 运行配置 |
| `runtime/orbiter/`（新） | planner / router / aggregator |
| `examples/agent-writer/` | 示例 Agent + room.html + avatar |
| `tests/`（新） | manifest、幂等、路径穿越、桥协议、`/@` 解析 |

**注意**：`web/static/js/chat.js` 已有 2900 行，不要把新逻辑继续塞进去；新建 `orbiter.js` 并通过事件/状态解耦。

---

## 12. 直接交给 Trae 的开工提示词

```text
你在 SimChat 仓库（NOIC-NETWORK/SimChat）里工作。请先读：
- README.md
- spec/mod-manifest.schema.json
- spec/hooks.md
- spec/events.md
- loader/lifecycle.py、loader/manifest.py
- web/__init__.py、web/agent.py
- web/templates/index.html、web/static/js/chat.js
- docs/orbiter-living-space-design.md（本设计）

任务：只实现 Phase 0 + Phase 1，不要一次做完。
目标：
1) Web 宿主启动时接入 ModLoader（discover + set_global_loader），
   新增 GET /api/mods，确保 mods/ 下现有 8 个 MOD 能在 Web 端列出。
2) 扩展 manifest 支持 agent-config 的可选 agents/rooms 字段，
   新增 Agent 注册表，完整 id 为 <mod_id>.<agent_id>。
3) index.html 增加 Agent 轨道与 /@ 面板；
   /@agent-id text 直接走现有 Agent SSE；
   /@ 打开面板；未知 Agent 给出明确错误。
4) 新增 examples/agent-writer 示例（纯数据 + prompts + 最小 room.html 占位）。

硬约束：
- 不修改现有 13 个 SSE 核心事件的名称与语义；
- Agent 必须是纯数据，不允许执行任意 Python；
- 所有 MOD 内路径必须做 .. / 绝对路径 / 符号链接校验；
- 新代码不要继续膨胀 chat.js，新增独立 JS 模块；
- 先用标准库 unittest 写最小测试；
- 每一步运行 python -m compileall，并跑一个 smoke 脚本验证 8 个 MOD 可加载。

先输出实施计划（文件级 diff 清单 + 风险），等我确认后再写代码。
```

---

## 13. 开放问题（建议默认值）

| 问题 | 建议默认 |
|---|---|
| 是否新增 `type: "agent"`？ | MVP 不新增，扩展 agent-config |
| 一个 Agent 能有多个房间？ | MVP 一 Agent 一房间；后续多房间 |
| 房间能否调用工具？ | 不能，只能发消息；工具由宿主执行 |
| Orbiter 选人用 LLM 还是规则？ | MVP 规则打分；后续可选 LLM |
| `/@` 只识别开头吗？ | 是，避免与邮箱/路径冲突 |
| 是否允许跨 Agent 共享记忆？ | 默认不共享；显式 `shared_memory` 才共享 |
| 安装后是否要求重启？ | MVP 重载 + 提示；不承诺全热插拔 |
| 房间资源是否走 CDN？ | 本地服务优先，保持离线可用 |

---

## 14. 非目标（这版不做）

- 不做 3D / 元宇宙式客厅；轨道是 2D 横条。
- 不做远程市场、支付、分成（Phase 6 的 Registry 再谈）。
- 不承诺“任意 Python Agent”安全执行。
- 不做多租户 / 多用户并发隔离。
- 不把 Orbiter 做成另一个大模型；它只是调度器。

---

## 15. 一句话总结

**客厅负责“看见和唤起”，卧室负责“沉浸和专属”，Agent 是数据，Orbiter 是调度。先把 Web 宿主接上 MOD 系统，这个点子才真正开始。**
