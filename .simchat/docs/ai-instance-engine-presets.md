# 创建和配置 AI 实例（神经引擎预设教程）

> SimChat 的 AI 实例 = Minecraft 的"世界存档"。创建一个实例就是选一张世界类型、调好生成参数和出生点，然后开始玩。

---

## 1. 先理解一个概念：AI 实例是什么

一个 AI 实例（Agent）就是一份完整的运行配置快照，存放在 `data/agents/<id>.json` 文件里。它包含：

| 字段 | 含义 | 对应 Minecraft |
|---|---|---|
| `name` / `avatar` | 实例的名字和头像 | 存档名、图标 |
| `system_prompt` | 系统提示词（人设、角色指令） | 世界出生点设置 |
| `engine_preset` | 神经引擎预设 ID | **世界类型**（普通 / 超平坦 / 大型生物群系） |
| `engine_params` | 生成参数（温度 / Top P / 重复惩罚 / 最大 tokens） | 世界生成种子和游戏规则 |
| `agent_capable` | 是否启用 Agent 模式（调用工具） | 允许作弊开关 |
| `entity_id` | 绑定的实体（多用户场景用） | — |
| `created_at` / `updated_at` | 创建和更新时间 | — |

**关键理解**：神经引擎预设**只调教生成参数，不切换模型或后端**。选"工作"不会让 SimChat 换一个模型，它只是把温度调低、Top P 收紧，让输出更收敛。底层推理引擎还是 Ollama / DashScope / 任何你配的提供商。

---

## 2. 六个预设方案（场景化最佳调教）

预设定义在 `runtime/agents.py` 的 `ENGINE_PRESETS` 字典里。前端渲染用 `list_presets()` 返回，API 端点 `GET /api/agents` 和 `GET /api/console/overview` 都会把预设列表带回来。

| 预设 ID | 显示名 | 适用场景 | 核心参数 |
|---|---|---|---|
| `normal` | 普通 | 日常对话、闲聊、一般性问答 | temp 0.7 · top_p 0.9 · rep 1.15 · 4K tokens |
| `work` | 工作 | 事务处理、总结整理、会议纪要、事实性输出 | temp 0.35 · top_p 0.85 · rep 1.1 · 4K tokens |
| `code` | 代码 | 编程辅助、代码审查、结构化技术文档 | temp 0.2 · top_p 0.8 · rep 1.05 · **8K tokens** |
| `creative` | 创意 | 写作、头脑风暴、创意生成、风格化表达 | temp 1.0 · top_p 0.95 · rep 1.25 · 4K tokens |
| `custom` | 自定义参数 | 你自己调 | 起始值同 normal |
| `wsynk` | W-Synk | 自研动态神经网络模式（波动更大、上下文占用更高） | temp 0.85 · top_p 0.95 · rep 1.35 · **8K tokens** |

**记忆口诀**：
- 越严肃 → 温度越低（工作 0.35 < 普通 0.7 < 创意 1.0）
- 越长输出 → max_tokens 越大（代码、W-Synk 是 8K，其余 4K）
- 重复惩罚跟着发散程度走（越发散越容易重复，需要更高惩罚）

---

## 3. 前端交互流程

### 3.1 预设卡片选择

实例编辑弹窗里，预设以 Minecraft 世界类型式的卡片按钮呈现（`web/templates/index.html` 里的 `#agent-engine-list`）。点击一张卡片 → `chat.js` 里的 `selectEnginePreset(id)` 被调用：

```
用户点击 "工作" 卡片
    ↓
selectEnginePreset("work")
    ↓
① 如果之前是 custom → 记住用户调过的值 → state2.customEngineParams = readEngineParams()
② 切换 state2.enginePresetId = "work"
③ setEngineParams(preset.params)  // 把滑块设为 0.35 / 0.85 / 1.1 / 4096
④ renderEnginePresets()           // 高亮当前卡片
⑤ syncEngineParamInputs()         // 给滑块加 disabled + .is-locked 类
```

### 3.2 锁定态视觉

非 custom 预设下，参数滑块区域会变成明显的"锁定"状态：

| CSS 类 | 效果 |
|---|---|
| `.agent-engine-params.is-locked` | opacity 0.72 · dotted border · 斜纹背景 |
| `.is-locked .field-label::after` | 每个 label 后缀灰色小字"（预设锁定）" |
| `.is-locked input[type="range"]` | grayscale(0.6) · brightness(0.92) · cursor: not-allowed |
| `.is-locked input[type="number"]` | 同上 |
| 所有 input | `disabled = true`（JS 设置，真正不可交互） |

只有选 `custom` 时 `.is-locked` 类才会被移除，滑块恢复可拖动。

### 3.3 切 preset 再切回 custom

这是一个容易被忽略的体验细节：用户从 custom 切到"工作"又切回 custom 时，滑块应该恢复**用户之前自己调过的值**，而不是"工作"预设的值。实现方式是：

```javascript
// 切 preset 前，把当前 custom 参数存起来
if (prevIsCustom) {
    state2.customEngineParams = readEngineParams();
}

// 切回 custom 时
if (state2.customEngineParams) {
    setEngineParams(state2.customEngineParams);  // 恢复用户调的值
} else {
    setEngineParams(preset.params);              // 用 custom 预设默认值
}
```

---

## 4. 后端契约：预设参数的权威来源

### 4.1 核心函数

后端有**两层强制覆盖**，确保非 custom 实例永远不会带着脏参数入库：

**第一层：`engine_params_for(preset, raw)`**（`runtime/agents.py` 第 82-95 行）

```python
def engine_params_for(preset, raw=None):
    preset = preset if preset in ENGINE_PRESETS else DEFAULT_ENGINE_PRESET
    params = dict(ENGINE_PRESETS[preset]["params"])   # 先拿预设标准值
    if preset != "custom" or not isinstance(raw, dict):
        return params                                  # 非 custom → 直接返回预设，忽略 raw
    # custom 才走到这里：用户值夹到合法区间
    for key, default in params.items():
        low, high, kind = _PARAM_SPECS[key]
        try:
            value = kind(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        params[key] = max(low, min(value, high))
    return params
```

关键逻辑：`if preset != "custom"` → 直接 `return params`，**完全忽略前端传的 `engine_params`**。

**第二层：`normalize_engine(agent)`**（`runtime/agents.py` 第 112-117 行）

每次 `get()` / `create()` / `update()` / `list_all()` 都会被调，把 `engine_preset` 和 `engine_params` 强制同步。相当于一个"每次读取都洗一遍数据"的防线。

### 4.2 API 端点行为

| 端点 | 创建 / 更新时 | 返回时 |
|---|---|---|
| `POST /api/agents` | `engine_preset` 必填，`engine_params` 可选（非 custom 时后端忽略） | `engine_preset` + `engine_params`（已 normalize） |
| `PUT /api/agents/<id>` | 同上 | 同上 |
| `GET /api/agents` | — | 带 `engine_presets` 列表和 normalize 后的实例 |

### 4.3 前端发送的 payload

```javascript
// chat.js saveAgentEdit()
const payload = {
    engine_preset: state2.enginePresetId,
    // 只有 custom 模式才发 engine_params
    ...(state2.enginePresetId === "custom" 
        ? { engine_params: readEngineParams() } 
        : {}),
    // ... 其他字段
};
```

非 custom 模式不发 `engine_params`，后端 `normalize_engine()` 会自动用预设标准值覆盖并入库。

### 4.4 参数合法区间（`_PARAM_SPECS`）

| 参数 | 范围 | 类型 | 说明 |
|---|---|---|---|
| `temperature` | 0.0 – 2.0 | float | 0 = 完全确定性，2 = 极度随机 |
| `top_p` | 0.05 – 1.0 | float | nucleus sampling 阈值，越小越收敛 |
| `repetition_penalty` | 1.0 – 2.0 | float | 1 = 无惩罚，2 = 强力去重 |
| `max_tokens` | 128 – 32768 | int | 单次生成的最大 token 数 |

超出范围的值会被自动 clamp（夹到边界），非法类型会回退到预设默认值。

---

## 5. 运行时生效链路

对话 / Agent 执行时，实例参数如何传递到模型提供商：

```
web/__init__.py 路由 /api/chat 和 /api/agent/run
    ↓
agents_mod.resolve_engine_params(agent)
    ↓ 返回已 normalize 的 {temperature, top_p, repetition_penalty, max_tokens}
runtime/agent/backend.py 或 chat_stream()
    ↓ 透传给 provider 的 stream_chat()
runtime/providers.py
    ↓ 根据 provider 类型适配参数
Ollama / API / Llama.cpp
```

`web/__init__.py` 第 1222-1224 行有明确的透传：

```python
"temperature": engine_params["temperature"],
"top_p": engine_params["top_p"],
"max_tokens": engine_params["max_tokens"],
```

`repetition_penalty` 在 backend.py 里以 `repetition_penalty=engine_params["repetition_penalty"]` 传给 provider。

---

## 6. 数据文件示例

创建一个"工作"预设实例后，`data/agents/<id>.json` 长这样：

```json
{
  "id": "a1b2c3d4e5f6",
  "entity_id": "default",
  "name": "工作助手",
  "description": "严谨的事务处理实例",
  "avatar": "💼",
  "avatar_type": "emoji",
  "engine_preset": "work",
  "engine_params": {
    "temperature": 0.35,
    "top_p": 0.85,
    "repetition_penalty": 1.1,
    "max_tokens": 4096
  },
  "system_prompt": "",
  "agent_capable": true,
  "allow_advanced": false,
  "desktop_pet": false,
  "created_at": "2026-11-05T10:00:00Z",
  "updated_at": "2026-11-05T10:00:00Z"
}
```

注意：即使创建时前端传了别的参数值，`engine_params` 里存的**一定是预设标准值**，因为 `normalize_engine()` 在写入前强制覆盖。

---

## 7. 技术约束与常见问题

### Q：为什么不允许非 custom 预设拖动滑块？

SimChat 的设计哲学是"**场景化方案一键交付**"。用户选"工作"是表达"我现在要干活"的意图，SimChat 应该直接用经过测试的最佳参数方案。让用户在工作场景下调高温度到 1.2 会让输出变得发散、不严谨——这与场景意图相悖。

如果用户想调，说明场景划分不适合他，这时候应该切到 custom 自己调。

### Q：custom 预设和 normal 预设的参数值一模一样？

是的。`custom` 的 `params` 初始值和 `normal` 相同。区别只在于 `engine_params_for()` 的分支逻辑：custom 会使用用户传的值，normal 不会。

### Q：W-Synk 是什么？

SimChat 原生的一种生成模式（见 `ENGINE_PRESETS`），温度高、重复惩罚高、max_tokens 开到 8K。描述里说"自研动态神经网络模式"，参数方案更激进。

### Q：怎么在 providers 上切换模型？

神经引擎预设**不负责**切换模型。模型选择在"服务商与模型"那个独立的设置面板里。预设只调 `temperature` / `top_p` / `repetition_penalty` / `max_tokens` 这四个生成参数。

### Q：预设是写死的吗？能让 MOD 加预设吗？

当前预设写死在 `runtime/agents.py` 的 `ENGINE_PRESETS` 字典里。MOD 体系的 `ui_blocks.register_preset()` 注册的是**服务商预设**（预填 API 端点和密钥），不是神经引擎预设。两者是不同层级的概念。未来要做的话，可以给 `ENGINE_PRESETS` 加一个注册接口。

### Q：如果我想给自定义预设起个名字、存起来以后直接用？

当前不支持。如果你想频繁用一组非标准参数，每次选 custom 自己调就行。需要持久化自定义预设方案的话，这是一个合理的功能需求，可以提 issue。

---

## 8. 变更日志

| 日期 | 变更 |
|---|---|
| 2026-11-05 | 初稿：六个预设方案文档 + 前端体验三修复（`saveAgentEdit` 条件发参、`is-locked` 视觉、`customEngineParams` 恢复逻辑） |
