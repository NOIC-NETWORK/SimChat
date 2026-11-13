# ABI Changelog

语义化版本规则：

- **major**：删除/重命名 hook、改变 hook 签名或事件语义、manifest 必填项变更。
- **minor**：新增 hook、新增可选 manifest 字段、新增事件或可选事件字段。
- **patch**：文案、校验实现、错误信息修正，不影响契约。

加载器行为：manifest 的 `abi` 不匹配 → 拒绝加载；`abi` 匹配但依赖的 hook 不存在 → 标记不兼容，不静默跳过。

---

## `lmbrew-mod/1` — 2026-10-24（P0 冻结草稿）

状态：**draft**。冻结对象为“现有 Agent 链路的事件与字段”，不是理想的最终 ABI。

### 冻结内容

- Manifest：见 [mod-manifest.schema.json](./mod-manifest.schema.json)，四类 MOD 统一字段。
- Capability：7 类（`fs.read` / `fs.write` / `net` / `shell` / `process` / `credentials` / `schedule`），默认全无。
- Hooks：10 个（`chat.mode` / `agent.tool` / `agent.context` / `agent.system_prompt` / `agent.safety` / `agent.memory` / `agent.event` / `ui.slot` / `provider.model` / `automation.hook`）。
- Events：13 个核心事件 + keepalive + 挂起语义，见 [events.md](./events.md)。

### 已知欠账（v2 前必须解决）

| # | 问题 | 现状 | 计划 |
|---|---|---|---|
| 1 | 安全拒绝与正常答复都用 `final` | `loop.py` 安全拦截发 `final` | 增加 `final.kind = "refusal"`（可选字段，向后兼容） |
| 2 | 事件缺 schema 版本 | `run_started` 只有 `run_id` | 增加 `schema: 1` |
| 3 | `edits` 可新增任意键 | 审批恢复直接 `params.update(edits)` | 按 `params_schema` 白名单校验 |
| 4 | 工具无参数 schema | `usage` 是自然语言 | 增加 `params_schema`（JSON Schema） |
| 5 | 无自定义事件命名空间 | `__reality_check__` 等 sentinel 混在文本流 | 迁移到 `mod.<id>.<event>` |
| 6 | 模式按钮硬编码 | `normal/galax/quasar` 写死 | 由 `chat.mode` 注册表驱动 |
| 7 | 工具注册全局单例 | `TOOL_REGISTRY` 模块级 dict | 改为按会话/按 MOD 的 capability 上下文 |

### 不承诺兼容的部分

- Python 内部模块路径（`kirara.services.agent.*`）不是 ABI。
- 工具实现细节、截断长度、token 估算算法可以调整，只需要在 changelog 记录。
- 前端 DOM 结构与 CSS 类名不是 ABI；MOD 只能通过 `ui.slot` 契约交互。

---

## 模板（后续版本按此追加）

```markdown
## `lmbrew-mod/2` — YYYY-MM-DD

### Breaking
- ...

### Added
- ...

### Migration
- 旧 MOD 需要：...
```
