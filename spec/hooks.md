# Hooks / ABI 契约（`lmbrew-mod/1`，v1 草稿）

> 这是**本体允许 MOD 接入的全部位置**。未列出的内部函数都不算 ABI，MOD 不得直接 import。
> 加载规则：manifest 里 `hooks` 含未知项 → 拒绝加载；MOD 调用未声明的 hook → 运行时错误并记审计。

## 0. 生命周期

```
install → verify(manifest/签名/哈希) → resolve(依赖/版本) → on_load → on_enable ⇄ on_disable → on_unload
```

- `on_load` 只做注册，**不得**执行重活或联网。
- 任一路由抛异常：该 MOD 标记 failed，本体继续运行（崩溃隔离）。
- `on_disable` 必须释放它注册的资源；失败只记录，不阻塞其他 MOD。

Python 侧最小形态：

```python
# mods/barry.galax/python/galax/pipeline.py
from simchat_mod import ModApi, hook

@hook("chat.mode")
def register_mode(api: ModApi) -> None:
    api.register_mode(ModeSpec(
        id="galax", label="Galax", icon="⚡",
        frontend_entry="web/galax.js", backend="pipeline:query",
        cost="high", description="证据加权联合推理检索",
    ))
```

## 1. Hook 总表

| # | hook | 方向 | 实例数 | 失败语义 | 稳定性 |
|---|---|---|---|---|---|
| 1 | `chat.mode` | MOD → 本体 | 多 | 单个模式不可用 → 按钮置灰 | stable |
| 2 | `agent.tool` | MOD → 本体 | 多 | 工具调用失败 → `tool_result.ok=false` | stable |
| 3 | `agent.context` | 本体 ↔ MOD | **1 个生效** | 抛错 → 回落本体默认上下文 | stable |
| 4 | `agent.system_prompt` | 本体 ↔ MOD | **1 个生效** | 返回 None → 使用本体默认 | stable |
| 5 | `agent.safety` | 本体 → MOD | 多（追加） | 超时/抛错 → 按“不安全”处理 | stable |
| 6 | `agent.memory` | 本体 → MOD | **1 个生效** | 写失败 → 只记日志，不阻塞任务 | stable |
| 7 | `agent.event` | MOD → 本体 → 前端 | 多 | 事件透传失败 → 丢弃该事件并记审计 | stable |
| 8 | `ui.slot` | MOD → 本体 | 多（按 slot） | 渲染失败 → slot 留空 | experimental |
| 9 | `provider.model` | MOD → 本体 | 多 | 选中的 provider 不可用 → 报错，不静默回退 | experimental |
| 10 | `automation.hook` | MOD → 本体 | 多 | 触发器失败 → 按 policy 处理 | experimental |

## 2. 逐个定义

### 2.1 `chat.mode`

```python
ModeSpec = {
  "id": "galax", "label": "Galax", "icon": "⚡", "order": 20,
  "frontend_entry": "web/galax.js",     # 可选
  "backend": "pipeline:query",          # 可选
  "cost": "high", "description": "...",
  "requires_capabilities": ["net"],
}
```

- 入口形态：前端按 `list_modes()` 渲染，取代当前硬编码的 `normal/galax/quasar` 映射（[rigard.js L351-L353](file:///e:/LMBrewer/rigard/js/rigard.js#L351-L353)）。
- 后端调用签名固定：`query(message: str, session_id: str | None, history: list) -> dict`。
- 未安装对应 MOD 时，本体不得展示该模式按钮。

### 2.2 `agent.tool`

```python
ToolSpec = {
  "name": "web_search", "label": "网页搜索",
  "description": "...", "risk": "read|write|dangerous",
  "usage": "web_search PARAMS:{\"query\": \"...\"}",
  "params_schema": {...},               # JSON Schema，用于审批卡渲染与静态校验
  "run": callable,                      # (params: dict, ctx: ToolContext) -> str | dict
}
```

- `ctx` 只注入 `workdir` / `abort_event` / capability 句柄，不注入 kernel。
- 注册后会自动进入 `build_tool_protocol_section()`，模型可见。
- 与现有实现对齐：[BaseTool](file:///e:/LMBrewer/kirara/services/agent/tools.py#L117-L136) 的 `meta()` 字段即为 `ToolSpec` 的公开子集。
- **禁止** MOD 覆盖内置工具的 `name`；冲突直接拒绝加载。

### 2.3 `agent.context`

```python
def build_prompt(message: str, history: list, session_id: str | None) -> str: ...
```

- 决定“这一轮给模型看什么”：记忆召回、知识库注入、话题转移都在这里。
- 只允许 1 个生效实现；多个声明时取优先级最高者，其余禁用并提示冲突。
- 超时（建议 5s）后回落本体默认上下文，并 emit `agent.event` 提示降级。

### 2.4 `agent.system_prompt`

```python
def system_prompt(persona: str | None) -> str | None: ...
```

- 现有实现：`resolve_persona_system()` + `build_system_prompt_with_skills()`（[lmbrew.py L1084-L1129](file:///e:/LMBrewer/lmbrew.py#L1084-L1129)）。
- 返回 `None` 表示使用本体默认；返回空串视为无效。
- 技能 prompt 注入（`trigger=prompt` 模式）属于该 hook 的实现细节，本体不感知。

### 2.5 `agent.safety`

```python
def check(text: str) -> {"safe": bool, "category": str | None}: ...
```

调用顺序：**本体闸门先跑**，通过后再跑所有 MOD 检查。任一判不安全即拒绝。

- MOD 只能“加严”，不能返回 `safe=True` 去覆盖本体结论（本体结论不参与投票）。
- 超时（1s）视为不安全。
- 拒绝文案仍由本体决定；MOD 可提供 `category` 供映射，不直接输出给用户。

### 2.6 `agent.memory`

```python
def save_turn(session_id, user_input, answer) -> None: ...
def save_task(session_id, task, answer) -> None: ...
```

- 本体内置 SQLite 实现（Phase 1 起），保证裸壳可玩。
- MOD 实现失败只记日志；任务返回不因记忆失败而失败（与现有 `_save_memory` 的容错一致）。

### 2.7 `agent.event`

```python
api.emit_event(name: str, payload: dict)   # name 必须以 "mod.<mod_id>." 开头
```

- 本体包装为 `{"event": "mod.barry.galax.reality_check", "data": {...}}` 后进 SSE。
- 前端对未知事件必须静默忽略（现状 `default: break;`，[kiraraGenCore.js L2591-L2592](file:///e:/LMBrewer/kirara/js/kiraraGenCore.js#L2591-L2592)）。
- 核心事件名（`run_started` 等 13 个）为保留字，MOD 不得占用。

### 2.8 `ui.slot`

保留 slot：

| slot | 位置 | 用途 |
|---|---|---|
| `composer.left` | 输入框左侧 | 附件/模式入口 |
| `composer.mode` | 模式选择区 | Galax/Quasar 等 |
| `message.bubble` | 消息气泡内 | 定制渲染 |
| `sidebar.task` | 任务侧栏项 | 任务状态徽章 |
| `settings.tab` | 设置页 | 专属配置 |
| `theme` | 全局 | CSS 变量与资源 |

- 契约：`mount(el, ctx) -> { dispose() }`；必须可重复挂载/卸载。
- 不允许直接操作其他 slot 的 DOM，不允许全局选择器。

### 2.9 `provider.model`

```python
ProviderSpec = {
  "id": "ollama", "label": "Ollama",
  "generate": callable,          # (prompt, system_msg) -> str
  "generate_stream": callable,   # (prompt, system_msg) -> Iterator[str]
  "models": ["jrvs-7b", "qwen3"],
  "health_check": callable,
}
```

- 与现有 `kernel.inference.generate` 签名对齐，便于适配器包装。
- 模型清单属于 provider，具体默认模型与参数属于 `agent-config`。
- 选中的 provider 不可用 → 直接报错，不静默切到别的 provider（fail-closed）。

### 2.10 `automation.hook`

```python
api.register_trigger("cron", handler)     # 本体调度器调用
api.register_action("agent.run", handler)
```

- 触发器由本体调度器统一调度，MOD 不能自建线程/定时器。
- 每次执行都带 `RunContext`（配额、审计 id、中止信号）。

## 3. 兼容规则

- 新增 hook / 新增可选字段 = minor；删除/改名/改变语义 = major。
- 本体升级若移除 hook，加载器必须先把依赖它的 MOD 标记为“不兼容”，不能静默跳过。
- `experimental` 的 hook 可能在 minor 版本调整，使用方需在 manifest 中声明可接受范围。

## 4. 当前代码的硬编码位置（Phase 1-3 要替换）

| 现状 | 位置 |
|---|---|
| 工具注册表 | [tools.py L605-L625](file:///e:/LMBrewer/kirara/services/agent/tools.py#L605-L625) |
| 模式开关映射 | [rigard.js L351-L353](file:///e:/LMBrewer/rigard/js/rigard.js#L351-L353) |
| 人设/技能拼装 | [lmbrew.py L1084-L1129](file:///e:/LMBrewer/lmbrew.py#L1084-L1129) |
| 安全检测 | [loop.py L309-L315](file:///e:/LMBrewer/kirara/services/agent/loop.py#L309-L315) |
| 记忆写入 | [loop.py L241-L257](file:///e:/LMBrewer/kirara/services/agent/loop.py#L241-L257) |
| 工作流事件 | [jrvs.py L3260-L3274](file:///e:/LMBrewer/kirara/services/jrvs.py#L3260-L3274) |
