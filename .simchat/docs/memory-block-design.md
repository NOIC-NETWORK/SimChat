# 记忆库（Memory Block）设计

> 定位：**方块层 · 引擎内建原子能力**。不是 MOD，不是可插拔组件，不是实验性功能。
> 状态：设计定稿方向（stable）。实现待排期。
> 关联：[blackwall-architecture.md](blackwall-architecture.md) §3.4 记忆写入门；[kirara-reboot-investigation.md](kirara-reboot-investigation.md) §3.3 Hippo 参考形态。

---

## 0. 定调

记忆库是**能力**，不是实验。判断标准只有三条：

1. **接口稳定**：读、写、删、检索四个动作的契约一次定死，后续只增不改。
2. **行为可测**：每条规则都能写出验收用例，不依赖"效果好不好"的主观判断。
3. **失败可降级**：记忆库挂掉时，对话必须照常进行，只是"想不起来"。

**实验性内容不放在这里。** W-Synk 动态权重模型是实验层，它只能作为记忆库的**读者**，不能成为记忆库的依赖（§7）。

---

## 1. 现状与差距

### 1.1 现在有什么

| 组件 | 文件 | 实际能力 |
|---|---|---|
| 会话存储 | `runtime/store.py` | 每会话一个 JSON，只保留最近 40 条消息，append-only |
| 会话落库 | `runtime/agent/backend.py` `save_memory()` | 只存「任务 + 最终答复」，工具过程丢弃 |
| 运行内记忆 | `runtime/agent/loop.py` `transcript` | 单次 run 内有效，run 结束即销毁 |
| 记忆注入 | `backend.build_prompt()` | 取最近 20 条历史拼成文本，**无检索、无排序、无来源** |

### 1.2 差在哪

现在的实现严格说是"会话回放"，不是"记忆"：

| 维度 | 现状 | 需要 |
|---|---|---|
| 时间跨度 | 单会话 | 跨会话 |
| 检索 | 无，按时间倒序全塞 | 相关性排序 + 预算裁剪 |
| 粒度 | 整条消息 | 原子事实 / 事件 / 偏好 |
| 来源 | 无 | 必须可追溯（与 Blackwall 对齐） |
| 冲突处理 | 直接追加，新旧并存 | 显式判定 supersede / contradict |
| 删除 | 删会话即全删 | 单条可删、可导出 |
| 容量 | 40 条硬截断 | 容量上限 + 归档淘汰 |

### 1.3 参照，不照搬

Kirara 的 Hippo 已经把分层结构验证过了：工作记忆 → 巩固压缩 → 长期库 → 门控注入，配套回声过滤与遗忘曲线。结构可用，三处必须改：

- **去掉 ChromaDB 硬依赖**：项目记忆里明确记过 chromadb 在某些环境装不上。改为 **SQLite + FTS5 为主，向量检索可选**。
- **去掉不可解释的权重**：艾宾浩斯曲线、0.7 阈值这类魔法数字必须写成白盒公式（§4.2），而不是调参调出来的常数。
- **重写，不迁移**：不复制旧代码，只继承分层思想与防复读策略。

---

## 2. 能力分层

三层，不多不少。层数越多，调试越难。

| 层 | 名称 | 生命周期 | 内容 | 写入者 |
|---|---|---|---|---|
| **M0** | 会话层 | 单会话，永久 | 原始消息（role/content/ts） | 对话链路自动 |
| **M1** | 事件层（episodic） | 跨会话 | 一次任务的摘要：做了什么、用了什么工具、结论是什么 | run 结束时自动 |
| **M2** | 事实层（semantic） | 跨会话，长期 | 稳定事实、偏好、约定、结论 | 写入门（§5）+ 用户手动 |

对话时按 `M1 + M2` 检索，`M0` 只作为当前会话的上下文窗口，**不参与跨会话检索**——原始消息噪声太大，直接检索会召回一堆无关对话。

---

## 3. 数据模型

### 3.1 条目

```json
{
  "id": "mem_01J3ZK8Q",
  "kind": "episodic",              // episodic | semantic | preference | task
  "scope": {"type": "instance", "key": "agent_7f2a"},
  "text": "用户的工作区默认用 py 调用 Python，不用 python。",
  "entities": ["python", "工作区"],
  "source_segs": ["s_04"],          // 指向 Blackwall 的来源账本
  "taint": "derived",               // operator | derived | untrusted
  "confidence": 0.9,
  "status": "active",               // active | superseded | contested | archived
  "hash": "sha256:…",
  "created_at": 1762838400,
  "updated_at": 1762838400,
  "last_used_at": 1762838400,
  "hits": 7,
  "supersedes": null,
  "contradicts": []
}
```

字段约束：

- `kind = semantic` 且 `taint = untrusted` **禁止写入**（降级为 `episodic`，或标记 `confidence ≤ 0.4`）。
- `source_segs` 为空且 `taint != operator` 的条目，注入时必须带 `[未核实]`。
- `hash` 用于幂等：同 hash 条目重复写入只累加 `hits`，不产生副本。

### 3.2 存储引擎

**SQLite（`data/memory/memory.db`）**，理由：单文件、事务、并发安全、可直接备份，不引入外部服务。

```sql
entries(id TEXT PRIMARY KEY, kind, scope_type, scope_key, text,
        taint, confidence, status, hash, created_at, updated_at,
        last_used_at, hits, supersedes, embedding BLOB NULL)

entries_fts(text, entities)              -- FTS5 虚拟表，BM25 打分
edges(src_id, dst_id, relation)          -- supersedes | contradicts | derived_from
events(ts, op, entry_id, actor, detail)  -- 追加式变更日志，永不修改
```

`embedding` 列默认为 NULL。配了 embedding 服务就填，没配就纯 BM25。**两条路径都必须能跑**，这是 stable 的底线。

JSON 只用于导入导出，不作为主存储。

### 3.3 作用域

```
global   → 跨实例共享（用户明确的通用偏好）
instance → 绑定某个 AI 实例（默认）
session  → 绑定单会话，会话结束归档
```

检索时严格按 `scope_key` 过滤，**默认不跨实例**。跨实例共享必须由用户在条目上显式勾选，与 `orbiter` 的"默认不共享记忆"原则一致。

---

## 4. 检索

### 4.1 流程

```
query 归一化 → scope 过滤(status=active) → FTS5 BM25 召回 top 50
  → (可选) 向量召回 top 50 → RRF 融合
  → 回声过滤（与当前上下文 bigram 覆盖率 > 60% 剔除）
  → 打分排序 → 阈值门控 → 预算裁剪 → 注入
```

回声过滤是必需的：检索到"用户说你好"这种条目并注入，会直接导致复读。规则照抄 Hippo 的 bigram 覆盖率，阈值 0.6，白盒可调。

### 4.2 打分公式（固定权重，白盒）

```
S = 0.45 × BM25_norm
  + 0.20 × recency
  + 0.15 × scope_match
  + 0.10 × source_quality
  + 0.10 × usage
```

| 项 | 计算 | 说明 |
|---|---|---|
| `BM25_norm` | `bm25 / (bm25 + k)`，k=1.2 | 归一到 0~1 |
| `recency` | `exp(-age_days / 30)` | 半衰期 30 天，不是"遗忘曲线" |
| `scope_match` | 同实例 1.0 / 同工作区 0.8 / 全局 0.6 | 精确作用域优先 |
| `source_quality` | 复用 Blackwall `source_class` 映射：primary 1.0 / institutional 0.8 / aggregator 0.5 / ugc 0.3 / suspect 0.1 | 与来源治理同源 |
| `usage` | `log(1+hits) / log(1+max_hits)` | 用得多的条目略微上浮 |

**权重写死在配置里，只允许用户在设置页做整体缩放，不做在线学习、不做自动调参。** 这是"成熟"与"实验"的分界：实验可以改权重，稳定层不可以。

### 4.3 门控与预算

- 阈值：`S < 0.35` 不注入（可配置，范围 0.2~0.6）。
- 条数上限：默认 6 条。
- token 上限：默认 800 tokens，按 `S` 从高到低装填，装不下就截断当前条。
- 同一实体最多 2 条，防止一个话题淹没整个预算。

---

## 5. 写入路径（三道门）

### 5.1 触发点

| 触发 | 写入层 | 是否需审批 |
|---|---|---|
| run 结束 | M1 episodic | 否（内部自动） |
| 用户点「记住这条」 | M2 | 否（OPERATOR 行为） |
| Agent 调 `memory_write` | M2 | **是**（write 级，复用审批流） |
| 定时巩固（可选） | M1 → M2 | 否，但只做规则抽取 |

### 5.2 门 1 · 去重

同 `hash` → 只累加 `hits`、更新 `last_used_at`。
近重复（simhash 相似度 > 0.9）→ 合并为新文本 + 保留旧 `id`，记一条 `events`。

### 5.3 门 2 · 来源与污点（与 Blackwall 对齐）

沿用 [blackwall §3.4](blackwall-architecture.md) 的写入门：

| 条目来源 | 允许的 kind | confidence 上限 |
|---|---|---|
| `OPERATOR`（用户亲自输入/确认） | semantic / preference | 1.0 |
| `DERIVED`（模型基于可信输入推导） | semantic / episodic | 0.8 |
| `UNTRUSTED`（网页、文件、IM、MOD） | episodic only | 0.4 |

`UNTRUSTED` 派生的内容**永远不能以 `semantic` 写入**。它可以是"有一次我读到过 X"，不能是"X 是事实"。这条不是可选项，是 `MemoryStore.write()` 内部的硬校验。

### 5.4 门 3 · 冲突

写入前按实体检索同 scope 的 active 条目：

- 语义等价 → 合并（门 1 已覆盖）
- 语义冲突 → **不覆盖**。新条目写入并置 `status = contested`，双方各记一条 `contradicts` 边。
- 新条目更明确、带更强来源（如 primary 覆盖 ugc）→ 旧条目 `status = superseded`，`supersedes` 指向新条目，旧条目保留可追溯。

绝不做"后写覆盖先写"——那正是数据投毒最省事的入口。

### 5.5 事务与回滚

所有写入走单事务：`entries` + `edges` + `events`。任何一步失败整笔回滚。`events` 追加式，支持按时间点重放到任意历史状态。

---

## 6. 读取与注入

### 6.1 注入格式

```
【记忆（可能过时，以核对为准）】
- [M1] 用户的工作区默认用 py 调用 Python。（2026-11-09，已核实）
- [M2][未核实] 某库在 2025 年停止维护。（来源：web s_04）
```

规则：

- 每条带来源角标，可点击跳转 Inspector 查看原始分段。
- `[未核实]` 由 `taint` + `confidence` 自动决定，**模型不能自己加或去掉**。
- 注入块本身是 `DERIVED`，进入上下文后仍受 Blackwall P1 信封约束。

### 6.2 注入位置

`AgentLoop._build_base_prompt()` 之后、`protocol` 之前。理由：记忆属于背景知识，必须比任务指令更早出现，但不能挤占工具协议。

`chat_stream()` 同理，插在 system prompt 之后、历史之前。

### 6.3 预算冲突时的裁剪顺序

```
记忆块 → 早期历史 → 工具输出
```

先砍记忆：记忆是可再检索的，历史砍了不可恢复。这条顺序写死，不做动态权衡。

---

## 7. 与 W-Synk 的边界

这是本文档必须写清楚的一节。

| | 记忆库 | W-Synk |
|---|---|---|
| 性质 | 稳定能力 | 实验模型 |
| 是否内建 | 是，不可移除 | 否，可随时摘掉 |
| 打分权重 | 固定白盒公式 | 动态权重，可学习 |
| 依赖方向 | 不依赖 W-Synk | **单向依赖记忆库** |
| 失败影响 | 对话降级为"想不起来" | 记忆照常工作 |

约束只有一句：**W-Synk 只能通过 `MemoryQuery` 接口读候选集，自己重排；不能写入、不能改打分公式、不能改条目结构。**

```python
# W-Synk 唯一被允许的接入方式
candidates = memory.query(text=query, scope=scope, limit=50)  # 原始候选，未排序
reranked = wsynk.rank(candidates, context=ctx)                 # 实验层自己玩
```

这样实验失败时，直接停用 W-Synk，记忆库零改动。反过来，如果让记忆库依赖 W-Synk 的输出，实验代码就污染了稳定层，以后再想摘掉就摘不干净。

---

## 8. 原子能力形态

### 8.1 注册方式

记忆库是**内建方块**，与 `file_read` / `glob` 同级，注册进 `runtime/capabilities.py`：

```python
BlockRegistry.register(MemoryBlock())   # 服务型方块，无 manifest、无 sandbox
```

与 skill MOD 的区别：

| | 内建记忆方块 | skill MOD |
|---|---|---|
| 加载 | 进程内直接 import | sandbox 子进程 |
| 可卸载 | **否** | 是 |
| 可禁用 | **否** | 是 |
| capability | 无（内建默认拥有） | manifest 声明 |
| 数据目录 | `data/memory/` | `data/mods/<id>/` |

MOD 不能 unregister 它，也不能替换实现。MOD 只能通过注入的 `memory` 服务**调用**，不能改规则。

### 8.2 对外接口

服务级（进程内）：

```python
MemoryStore.query(text, scope, kinds=None, limit=6, budget_tokens=800) -> list[Entry]
MemoryStore.remember(entry, source_segs, taint) -> Entry
MemoryStore.forget(entry_id, hard=False) -> bool
MemoryStore.export(scope) -> bytes
MemoryStore.stats() -> dict
```

工具级（Agent 可见，注册进 `TOOL_REGISTRY`）：

| 工具 | 风险级 | 行为 |
|---|---|---|
| `memory_search` | read | 检索，返回条目 + 来源 |
| `memory_write` | write | 写一条，走审批流 |
| `memory_forget` | write | 删除，走审批流，默认软删 |

工具只是 Agent 的入口，核心逻辑全在服务层。即使把工具全禁掉，`build_prompt` 的自动注入依然工作。

### 8.3 为什么不做成 MOD

与 Blackwall 同理：记忆是可被投毒的资产，把写入规则的实现交给可替换组件，等于让被守的人管钥匙。另外 MOD 走 sandbox，跨进程读写 `data/memory.db` 会引入锁竞争与一致性问题。

---

## 9. 接入点与迁移

### 9.1 代码接入

| 位置 | 改动 |
|---|---|
| `runtime/memory/`（新建） | `store.py`（SQLite）、`retrieve.py`（打分）、`gate.py`（三道门）、`inject.py`（格式化） |
| `runtime/agent/backend.py` `save_memory()` | 改为写 M1 episodic，而非仅追加会话消息 |
| `runtime/agent/loop.py` run 结束 | 生成 episode 摘要（规则模板，不调 LLM） |
| `runtime/agent/backend.py` `build_prompt()` | 插入记忆块 |
| `runtime/core.py` `chat_stream()` | 同上 |
| `web/__init__.py` | 新增 `/api/memory` 列表 / 搜索 / 编辑 / 删除 / 导出 |
| `runtime/capabilities.py`（新建） | `BlockRegistry` + `MemoryBlock` |

### 9.2 迁移

只迁移**已存在的事实**，不做任何推断：

- 每个历史会话 → 一条 M1 条目（标题 + 首条用户消息摘要 + 消息数）。
- `mode = agent` 的会话额外抽取"用过的工具"清单。
- 迁移脚本幂等（按会话 id + hash 去重），可重复执行。
- 迁移前自动备份 `data/sessions/` 到 `data/memory/_migration_backup/`。

不迁移：单条消息全文、工具输出、失败任务。这些噪声太大，进了记忆库只会拖低检索质量。

---

## 10. 隐私与删除

- **硬删除**：`forget(hard=True)` 物理删行 + 重建 FTS 索引 + 清理 embedding。
- **软删除**：默认，`status = archived`，检索不可见，保留 30 天后物理清除。
- **导出**：单 scope 或全库导出 JSON，字段与 §3.1 一致，可再导入。
- **加密**：`preference` 类条目可走 `runtime/crypto.py` 的 Fernet 加密，密钥同 `data/.secret_key`。
- **不联网**：记忆库不做任何远程同步、不上传、不参与训练。embedding 若使用云端 API，必须是用户显式开启，并在设置页明示"文本会发送到服务商"。

---

## 11. 性能与容量

| 项 | 目标 |
|---|---|
| 单次检索 | < 20ms（10 万条以内，纯 FTS5） |
| 写入 | < 10ms |
| 库体积 | 10 万条约 100~200MB |
| 并发 | SQLite WAL，单写多读 |

降级策略：记忆库任何异常 → **不注入，对话继续**，同时写一条 `memory.unavailable` 事件。记忆永远不能成为对话的阻塞点。

容量上限（默认，可配置）：单 scope 5 万条。超出后按 `S` 最低 + 最久未使用淘汰到 `archived`，不直接删除。

---

## 12. 明确不做

写在这里，防止实现阶段不断加需求：

1. **不做人格改写**：记忆只存事实与偏好，不存"角色应该如何表现"。人设归 system prompt 和 `agent-config`。
2. **不做跨用户共享**：没有账号体系之前，记忆只属于本机。
3. **不把 LLM 抽取作为唯一路径**：M1 摘要用规则模板，LLM 抽取是可选增强；LLM 挂掉时记忆库必须仍能写入。
4. **不做自动遗忘曲线调参**：用固定半衰期，不模拟神经科学。
5. **不承载 W-Synk**：实验性动态权重不进入记忆库的数据模型与打分公式。
6. **不做向量检索硬依赖**：向量是加速项，不是前提。

---

## 13. 验收标准

| 项 | 判据 |
|---|---|
| 幂等写入 | 同内容连写 10 次 → 库中仅 1 条，`hits == 10` |
| 作用域隔离 | 实例 A 的条目，在实例 B 检索结果中为 0 |
| 污点门禁 | `UNTRUSTED` 来源写 `semantic` → 拒绝并记事件 |
| 冲突不覆盖 | 新旧矛盾条目共存，双方 `contradicts` 有边，旧条目未被修改 |
| 回声过滤 | 注入条目与当前上下文 bigram 覆盖率 > 60% → 不注入 |
| 预算 | 6 条 / 800 tokens 上限内，超出按 `S` 裁剪 |
| 降级 | 删除 `memory.db` 后启动 → 对话正常，仅无记忆注入 |
| 删除 | 硬删后 FTS 无残留，导出文件中不含该条 |
| 迁移 | 迁移两次结果一致（幂等），旧会话数据未被修改 |
| 性能 | 10 万条库检索 P95 < 20ms |
| 原子性 | 记忆方块不可被 MOD 卸载（篡改 manifest 无效） |
| W-Synk 隔离 | 停用 W-Synk 后，检索结果与打分完全不变 |

---

## 附：一句话

记忆库解决的是"记不记得住"，W-Synk 解决的是"怎么权衡"。前者必须像数据库一样可靠，后者才可以像实验室一样折腾。把两者混在一起，两边都做不好。
