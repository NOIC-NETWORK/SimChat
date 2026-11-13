# Orbiter 调度器引擎设计（Phase 1）

> 先看清楚我们现在有什么，再决定 Orbiter 站在哪里。
> 作者：SimChat · 2026-11-09 · 草案 v0.1

---

## 0. 定位

### 0.1 我们今天已有的东西

| 组件 | 位置 | 能干什么 | 不能干什么 |
|---|---|---|---|
| `SimChatCore.chat_stream()` | `runtime/core.py` | 单次 SSE 对话（token-by-token） | 不能调用工具；不能跨实例 |
| `AgentLoop.run()` | `runtime/agent/loop.py` | 单实例内 ReAct 循环（读/写/shell 工具、审批流、计划） | 只跑在当前 model + provider；不能调其他 AI 实例 |
| `SimChatAgentBackend` | `runtime/agent/backend.py` | 把 AgentLoop 对模型的调用收敛到 SimChatCore | 单一后端；没有多后端路由 |
| `/api/chat` | `web/__init__.py` | 已经接了 agent_capable 分支 → AgentLoop | 分支是二选一（chat 或 agent），没有中间态 |
| AI 实例（agents.json） | `runtime/agents.py` | 一个实例 = system_prompt + engine_params + agent_capable | 没有"远程实例"概念；都是本地 provider/model |

### 0.2 Orbiter 是什么

**Orbiter 是"实例级"的路由器，不是"token 级"的路由器。**

它站在 `/api/chat` 与 AgentLoop / chat_stream 之间，做一件事：
> **给定用户消息 + composer 当前状态（选中哪个实例、模型选择器选什么），决定这次请求怎么走：**
> ① 直接对话（chat_stream）—— 不需要任何 AI 实例参与，模型自由发挥
> ② 本地 AgentLoop —— 当前选中的本地 AI 实例，走 ReAct + 工具
> ③ 远程 AI 实例 —— 调另一台机器（AutoDL/AWS 大模型实例）跑同一个 AgentLoop
> ④ 多 AI 协同 —— 扇出到多个 Agent 实例，并行跑，再汇总答复

Kirara 当年的 `/@JRVS-390B-1.3.4`、`/$ FileRead` 就是协议层；SimChat 把协议收归后端，前端**永远只调 `/api/chat`**，Orbiter 在服务端决定内部路由。

### 0.3 不做什么（Phase 1）

- **不做 token 级路由**：不把一句话拆成"前半句本地模型说、后半句云端补"。这种做法延迟高、状态难维护、对用户也不可解释。
- **不做模型自动发现 + 自动调度**：Phase 1 只支持"用户在 composer 选了哪个实例，就用哪个实例"——即 Orbiter 的路由决策**主要来自用户的显式选择**，而不是 Orbiter 自己判断"这个问题复杂，换大模型"。Phase 2 才考虑"轻量路由器 → 判断复杂度 → 自动升级到远程实例"。
- **不做跨实例记忆**：每个 session 只属于一个实例；跨实例扇出只共享当前这一轮的 user message，**不**共享历史对话，避免污染每个实例的 system_prompt 设定。

---

## 1. 三层架构总览

```
┌─────────────────────────────────────────────────────────┐
│  前端 /api/chat (POST, SSE)                             │
│  payload: { message, session_id, agent_id, model, ... }│
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Orbiter 调度器（新：runtime/orbiter/scheduler.py）      │
│                                                         │
│  输入：message, agent_id (可空), session_id, 用户意图    │
│  输出：一个 RoutePlan，决定走哪条分支                     │
│                                                         │
│  RoutePlan.mode ∈ { direct, local_agent, remote_agent,  │
│                     fanout }                             │
│  RoutePlan.target = [ { backend, persona, engine } ]    │
└──────┬────────────┬───────────────┬─────────────────────┘
       │            │               │
       ▼            ▼               ▼
┌──────────┐ ┌──────────────┐ ┌───────────────────────────┐
│ direct   │ │ local_agent  │ │ remote_agent / fanout     │
│ chat_    │ │ AgentLoop    │ │ 同上 + 跨后端（SSE 扇出）  │
│ stream() │ │ + SimChat    │ │ 同一套 AgentLoop 逻辑     │
│          │ │ AgentBackend │ │ 只是 backend 换了          │
└──────────┘ └──────────────┘ └───────────────────────────┘
```

**关键洞察**：四种模式复用同一套 AgentLoop，差别只在 `SimChatAgentBackend` 的构造方式。`direct` 则完全绕过 AgentLoop，回到 `chat_stream`。

---

## 2. RoutePlan：调度决策结果

```python
# runtime/orbiter/scheduler.py（草案）

from dataclasses import dataclass, field
from typing import Optional, List, Literal

Mode = Literal["direct", "local_agent", "remote_agent", "fanout"]


@dataclass
class BackendTarget:
    """一次推理的后端目标"""
    backend_type: Literal["local", "remote"]
    provider: Optional[str] = None         # local 时：SimChat provider id
    model: Optional[str] = None            # local 时：model id
    remote_url: Optional[str] = None       # remote 时：对端 SimChat / Kirara HTTP 地址
    remote_token: Optional[str] = None     # remote 时：鉴权
    instance_id: Optional[str] = None      # 关联的 AI 实例（用于 persona + system_prompt）
    persona: Optional[str] = None          # 实例名，AgentLoop 写入 run_ctx 用
    system_prompt: Optional[str] = None    # 实例 system_prompt
    engine_params: Optional[dict] = None   # temperature / top_p / max_tokens ...


@dataclass
class RoutePlan:
    mode: Mode
    targets: List[BackendTarget]           # fanout 时有多个；其他模式一个
    why: str = ""                          # 给前端的调试信息：为什么这么选
    router: str = "user"                   # user / orbiter_auto（Phase 2 新增）
```

**构造 RoutePlan 的输入信号**：

| 信号 | 来源 | 含义 |
|---|---|---|
| `agent_id` | payload | composer 下拉选了谁 |
| `agent.agent_capable` | agents.json | 实例是否具备 Agent 能力 |
| `agent.provider / agent.model` | agents.json | 实例声明的后端（local 时来自 SimChat provider 列表） |
| `agent.remote_url` | agents.json（扩展字段） | 远程实例的 HTTP 地址 |
| `state.mode === "agent"` | composer 的 Agent 切换 | 用户当前处于 Agent 模式还是对话模式 |

### 路由决策矩阵（Phase 1）

```
agent_id 为空？
  ├─ YES → mode = "direct"  (chat_stream，不带实例)
  └─ NO  → 取该实例 agent = agents[agent_id]
            ├─ agent.remote_url 非空？
            │    ├─ YES → mode = "remote_agent"，single target，backend_type="remote"
            │    └─ NO  → agent.agent_capable == True？
            │              ├─ YES → mode = "local_agent"，target = 本地 SimChat provider
            │              └─ NO  → mode = "direct"  (chat_stream + system_prompt only)
            └─ (未来) composer 里选了多个实例？
                 → mode = "fanout"，多个 target
```

> Phase 1 不做"Orbiter 自动路由"（router=orbiter_auto），所有路由都是显式的（router=user）。
> 自动路由需要一个轻量路由器模型先判断用户意图复杂度——那个是 Phase 2。

---

## 3. Runtime 扩展：agents.json 新增远程实例字段

Phase 1 里"远程 AI 实例"就是**另一个 SimChat 实例（或 Kirara）跑着 HTTP 服务**。我们在 agents.json 里扩展一个字段：

```jsonc
// data/agents/<instance-id>.json
{
  "id": "...",
  "name": "Niji-remote",
  "description": "远程跑在 AutoDL A100 上的 Niji 实例",
  "agent_capable": true,
  "avatar_type": "emoji",
  "avatar": "🎨",

  // 新增：远端接入（缺省这些字段就是本地实例）
  "backend": {
    "type": "remote",                        // "local" | "remote"
    "url": "https://autodl-xxx.ngrok-free.app",  // 对端 HTTP 根
    "token": "sha256:....",                  // 可选，对端鉴权
    "engine": {                              // 覆盖本地 engine_params（对端不支持时才填）
      "temperature": 0.7,
      "max_tokens": 8192
    }
  }
}
```

本地实例保持原样（`backend` 字段缺失即默认 `{"type": "local"}`），向后兼容。

### 对端契约（Phase 1）

远程实例只需要实现一个端点：

```
POST /api/orbiter/call
Content-Type: application/json
Authorization: Bearer <token>

{
  "message": "...",
  "history": [{"role": "user", "content": "..."}, ...],   // 只传当前 session 历史
  "system_prompt": "...",                                  // 远端实例自己有就会覆盖这条
  "engine_params": {"temperature": 0.7, "max_tokens": 4096},
  "mode": "agent" | "chat"
}

→ SSE，同 /api/chat 的事件格式（chat_started / thought / tool_call / final / error）
```

### 远端怎么实现

两种方式都可以：
1. **另一台 SimChat** 直接跑起来，它的 `/api/chat` 已经能处理 agent_capable。我们只需要加一层 `/api/orbiter/call`，做同样的事但**跳过用户认证**（改用 Authorization header）。
2. **Kirara / 其他** 只要实现这个 SSE 端点就行——协议对齐，后端实现不同没关系。

---

## 4. Scheduler 代码骨架

```python
# runtime/orbiter/__init__.py
from .scheduler import OrbiterScheduler, RoutePlan, BackendTarget, Mode

__all__ = ["OrbiterScheduler", "RoutePlan", "BackendTarget", "Mode"]
```

```python
# runtime/orbiter/scheduler.py
# -*- coding: utf-8 -*-
"""Orbiter 调度器 —— 把 /api/chat 的请求路由到合适的后端。

Phase 1：只做 user 显式选择的路由，不做自动路由器。
Phase 2：新增 router=orbiter_auto，用轻量模型判断复杂度再自动升级。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Literal

Mode = Literal["direct", "local_agent", "remote_agent", "fanout"]


@dataclass
class BackendTarget:
    backend_type: Literal["local", "remote"]
    provider: Optional[str] = None
    model: Optional[str] = None
    remote_url: Optional[str] = None
    remote_token: Optional[str] = None
    instance_id: Optional[str] = None
    persona: Optional[str] = None
    system_prompt: Optional[str] = None
    engine_params: Optional[dict] = None


@dataclass
class RoutePlan:
    mode: Mode
    targets: List[BackendTarget]
    why: str = ""
    router: str = "user"


class OrbiterScheduler:
    def __init__(self, core, agents_mod):
        self.core = core
        self.agents_mod = agents_mod

    def plan(self, agent_id: Optional[str], composer_mode: str = "chat") -> RoutePlan:
        """根据 agent_id（可能为空）和 composer_mode 产出 RoutePlan。

        composer_mode: "chat" 表示对话模式（即便实例 agent_capable=True 也不强行走 AgentLoop），
                       "agent"  表示 Agent 模式（实例 agent_capable=True 时强制 ReAct）。
        """
        if not agent_id:
            return RoutePlan(mode="direct", targets=[],
                             why="未选择 AI 实例，走直接对话。")

        try:
            agent = self.agents_mod.get(self.core.data_root, agent_id)
        except ValueError:
            return RoutePlan(mode="direct", targets=[],
                             why=f"实例 {agent_id} 不存在，退回直接对话。")

        backend_cfg = (agent.get("backend") or {}) if isinstance(agent.get("backend"), dict) else {}
        is_remote = backend_cfg.get("type") == "remote" and bool(backend_cfg.get("url"))

        if is_remote:
            target = BackendTarget(
                backend_type="remote",
                remote_url=backend_cfg["url"],
                remote_token=backend_cfg.get("token"),
                instance_id=agent_id,
                persona=agent.get("name"),
                system_prompt=agent.get("system_prompt"),
                engine_params=backend_cfg.get("engine") or self.agents_mod.resolve_engine_params(agent),
            )
            return RoutePlan(mode="remote_agent", targets=[target],
                             why=f"实例 {agent.get('name')} 配置了远程接入。")

        # 本地实例
        if composer_mode == "agent" and agent.get("agent_capable", True):
            engine = self.agents_mod.resolve_engine_params(agent)
            target = BackendTarget(
                backend_type="local",
                provider=None,    # 由 composer 的 model/provider 选择决定；这里只是占位
                model=None,
                instance_id=agent_id,
                persona=agent.get("name"),
                system_prompt=agent.get("system_prompt"),
                engine_params=engine,
            )
            return RoutePlan(mode="local_agent", targets=[target],
                             why=f"本地 Agent 实例 {agent.get('name')}，走 ReAct 循环。")

        # 本地非 Agent 实例 或 composer 处于对话模式
        target = BackendTarget(
            backend_type="local",
            instance_id=agent_id,
            persona=agent.get("name"),
            system_prompt=agent.get("system_prompt"),
            engine_params=self.agents_mod.resolve_engine_params(agent),
        )
        return RoutePlan(mode="direct", targets=[target],
                         why=f"本地实例 {agent.get('name')} 走直接对话（system_prompt）。")
```

---

## 5. /api/chat handler 的改造

现在的 handler 是：

```python
if agent_capable:
    # 构造 AgentLoop
else:
    # chat_stream
```

改成：

```python
# 新的 handler 伪代码

orbiter = OrbiterScheduler(core, _agents_mod())
composer_mode = "agent" if (
    # 可以从前端 payload 显式传来 composer_mode，也可以让后端推导
    data.get("agent_mode") == True
) else "chat"
plan = orbiter.plan(data.get("agent_id"), composer_mode=composer_mode)

_record_event("chat.start", {"plan_mode": plan.mode, "plan_why": plan.why, ...})

def generate():
    if plan.mode == "direct":
        # 复用现有 chat_stream；如果 target[0].system_prompt 有值，
        # 就让它覆盖 data.system
        yield from _run_direct(plan, data)

    elif plan.mode == "local_agent":
        yield from _run_local_agent(plan, data)

    elif plan.mode == "remote_agent":
        yield from _run_remote_agent(plan, data)

    elif plan.mode == "fanout":
        yield from _run_fanout(plan, data)  # Phase 1 可先 raise NotImplementedError
```

其中 `_run_remote_agent` 内部是个 SSE 转发器：

```python
import requests

def _run_remote_agent(plan, data):
    target = plan.targets[0]
    headers = {"Content-Type": "application/json"}
    if target.remote_token:
        headers["Authorization"] = f"Bearer {target.remote_token}"
    body = {
        "message": data["message"],
        "session_id": data.get("session_id"),
        "system_prompt": target.system_prompt,
        "engine_params": target.engine_params,
        "mode": "agent",
        "provider": data.get("provider"),
        "model": data.get("model"),
    }
    resp = requests.post(
        f"{target.remote_url.rstrip('/')}/api/orbiter/call",
        headers=headers, json=body, stream=True, timeout=(5, 300),
    )
    # 从 resp.iter_lines() 解析 SSE，逐条 yield
```

---

## 6. Phase 划分

### Phase 1（本文档覆盖）

- ✅ OrbiterScheduler + RoutePlan + BackendTarget
- ✅ agents.json 新增 `backend` 字段（`type: remote` + `url` + `token`）
- ✅ `/api/chat` handler 改造，按 RoutePlan 分支
- ✅ `_run_remote_agent`：SSE 转发到对端
- ✅ 对端契约 `/api/orbiter/call`（在本仓库新增路由，跳过用户认证）
- ❌ fanout（多实例并行）——先不做
- ❌ 自动路由器（轻量模型判断复杂度）——先不做
- ❌ 远程实例列表 UI（在 AI 实例创建表单里加「远程接入」tab）——前端后续

### Phase 2（自动路由器 + fanout）

- 新增 `orbiter.router` 字段，允许 `router: "orbiter_auto"`
- 轻量模型（本地 Ollama 小模型）做 prompt 分类器：`simple | moderate | complex`
  - simple → direct
  - moderate → local_agent
  - complex → remote_agent（如果配置了）或 local_agent + 升级提示
- fanout：多个 agent 并行跑各自的 AgentLoop，收集所有 final → 合并答复
  - 合并策略：**取第一个不是"工具调用失败"的 final**（保守），或让路由器模型二次总结（激进）

### Phase 3（AutoDL / 云端实例自动化）

- Orbiter 负责"按需拉起"远程实例（通过 AutoDL API / AWS Lambda）
- idle 超时自动释放，用户不用管云端
- 这一步 Orbiter 已经不只是"调度器"，而是"编排器"——另一个文档再说

---

## 7. 安全模型

| 风险 | 缓解 |
|---|---|
| 远程实例伪造 system_prompt / 越权执行 shell | 远程实例只能跑它自己 AI 实例里配置的 system_prompt；Orbiter 在请求里传的是"建议"，对端可以覆盖。shell 默认关闭（已有） |
| 远程 token 泄露 | token 存 agent JSON，权限与本地实例一致；不进前端 HTML |
| 远程 SSE 连接劫持 | 强制 HTTPS；Phase 1 不做 |
| fanout 并发太多实例拖垮机器 | 硬上限：Phase 2 默认 2，配置可调；每个远程实例独立 HTTP 连接，不共享 session |

---

## 8. SSE 事件扩展

为了让前端能画出"Orbiter 正在决定走哪条路"，在 `chat_started` 之后多加一个事件：

```json
{
  "event": "orbiter_plan",
  "plan": {
    "mode": "local_agent",
    "router": "user",
    "why": "本地 Agent 实例 gremlin，走 ReAct 循环。",
    "targets": [
      {"backend_type": "local", "persona": "gremlin", "instance_id": "..."}
    ]
  }
}
```

`_run_remote_agent` 还会 emit：

```json
{
  "event": "orbiter_remote_connect",
  "target": {"backend_type": "remote", "persona": "Niji", "remote_url": "https://..."}
}
```

---

## 9. 文件改动清单（Phase 1 实现时）

| 文件 | 操作 | 说明 |
|---|---|---|
| `runtime/orbiter/__init__.py` | 新增 | |
| `runtime/orbiter/scheduler.py` | 新增 | OrbiterScheduler + RoutePlan + BackendTarget |
| `runtime/orbiter/remote.py` | 新增 | SSE 转发、对端 `/api/orbiter/call` 客户端 |
| `runtime/agents.py` | 改 | `create/update` 接受 `backend` 字段；`resolve_engine_params` 兼容 remote |
| `web/__init__.py` | 改 | `/api/chat` handler 引入 OrbiterScheduler；新增 `/api/orbiter/call` |
| `web/templates/index.html` | 改 | Agent 实例编辑表单加「远程接入」tab（Phase 1 可选，先藏） |
| `web/static/js/chat.js` | 改 | composer payload 多传一个 `agent_mode: "chat"\|"agent"` |
| `updates.md` | 改 | 记录 Orbiter Phase 1 |

---

## 10. 与现有 AgentLoop 的关系

**一句话**：OrbiterScheduler 不碰 AgentLoop 的实现。

```
OrbiterScheduler.plan()     → RoutePlan.mode = "local_agent"
                                     │
                                     ▼
                            SimChatAgentBackend + AgentLoop  ← 完全不变
                                     │
                                     ▼
                            /api/chat handler 把 events yield 给 SSE
```

`mode = "remote_agent"` 时，AgentLoop 跑在**对端**，本端只做 SSE 转发。这意味着 Orbiter 的改动**集中在 web/__init__.py 的 handler 最上面几行和新增的 orbiter 包**，对 runtime/agent 完全零侵入。

---

## 11. 与用户 2022 年设定的对照

| 2022 年设想 | 2026 SimChat 里的落点 |
|---|---|
| `/@ JRVS-390B-1.3.4` | → composer 下拉选实例（实例 backend.type=remote） |
| `/$ FileRead` | → AgentLoop 里已有的 `file_read` / `list_dir` / `glob` |
| "轻量大模型做路由" | → Phase 2 的 `router: orbiter_auto` |
| "简单问题本地模型，复杂问题云端" | → Phase 2 的路由器复杂度判断 |
| "AutoDL 月租实例" | → Phase 3 的编排器 |
| "虚拟化技术，隐私泄露低" | → 每个 AI 实例一份独立 session + 独立 engine_params；远程实例独立机器 |

**Orbiter Phase 1 只做了最底下这一层：把"实例选择"从一个本地 JSON 字段，升级成一个"可以是本地也可以是远程"的路由入口。** 真正的混合推理架构（路由器模型 + AutoDL 自动拉起）是 Phase 2/3 的事，Phase 1 给它们留好了接口。
