# LMBrewer × SimChat：游戏本体 + 模组平台策略（v2）

SimChat的名字来自“聊天机器人”的本质——即聊天模拟器。是一个开源的chatbot框架。

> 本版按你的新定位重写：**LMBrewer = 游戏本体，SimChat = 模组平台（CurseForge 位），Agent Config / Automation / Skills = 用户 MOD，JRVS / Quasar / Galax = 一等方加密 MOD。**
> v1 的“抽出开源 harness”框架已作废，仅保留代码调研结论。
> 结论：**方向成立，而且比 v1 更适合你的资产结构**，但有 4 处必须修正，否则生态做不起来。

---

## 一、总判断：为什么这个类比更好

| 维度 | v1（开源 harness） | v2（游戏 + 模组平台） |
|---|---|---|
| 价值锚点 | 代码本身 | 生态与分发 |
| 开源对象 | 运行时（可被 fork 替代） | SDK / 规范 / 加载器（越用越值钱） |
| 私有资产 | 藏在“核心”里，边界暧昧 | 光明正大做成一等方 MOD，可比价 |
| 冷启动 | 开源一个半成品 Agent | 本体可玩 → 用户为了玩而装 MOD |
| 竞争 | 与开源 Agent 框架红海竞争 | 与垂直场景 + 本地隐私 + 中文生态竞争 |

你说“agent 不值钱、闭源会倒贴”是对的：通用 Agent 运行时已经商品化，真正稀缺的是**发行渠道 + 用户创作 + 可授权的独有能力**。这个结构把前两者做成公共品，把第三者做成商品。

### 必须修正的 4 点

1. **别把 SimChat 只当“商店”**。CurseForge 本身不执行 MOD；真正让 MOD 跑起来的是 Forge/Fabric。你的 SimChat 必须同时承担 **SDK + 加载器 + 清单规范 + CLI + 索引**，否则“平台”没有运行时抓手。商店页面可以最后做。
2. **安全必须留在本体，不能做成 MOD**。如果内容安全、权限、沙箱是 MOD，恶意 MOD 第一件事就是卸载它。Minecraft 的类比里没有这个问题，但你有。
3. **一等方 MOD 必须走公开 ABI，不能留私有后门**。一旦社区发现“官方的 Galax 用了你没公开的钩子”，整个平台的可信度就没了，而且你会被迫维护两套接口。
4. **Automation 是全新能力，不是“把现有东西改个名”**。当前代码库里没有工作流/定时引擎（详见 §3.4），这块要从零设计，且风险最高（无人值守执行）。

---

## 二、概念模型对齐

| Minecraft 世界 | LMBrewer 世界 | 归属 |
|---|---|---|
| 游戏本体（Mojang） | LMBrewer 引擎：UI 外壳、Agent 循环、工具执行器、会话、权限、调度 | 本体（可闭源分发） |
| Forge / Fabric（加载器） | SimChat Loader：manifest 解析、依赖解析、生命周期、ABI 校验 | **开源**（Apache-2.0） |
| CurseForge（分发） | SimChat Registry：索引、签名、版本、评分、下架 | 开源规范 + 官方托管实例 |
| 数据包 / 资源包 | `agent-config` MOD：人设、提示词、模型参数、主题 | 用户可写 |
| 模组（带代码） | `skill` MOD / `automation` MOD | 用户可写 |
| 官方 DLC / 付费内容 | `binary` MOD：JRVS、Quasar、Galax | **一等方私有** |

> 一句话：**本体闭源可接受，加载器和规范必须开源**——这是 Minecraft 生态真正的秘密，不是“游戏免费”。

---

## 三、现状调研（决定哪些能做成 MOD）

### 3.1 已有资产盘点

| 资产 | 位置 | 现状 | 能否直接 MOD 化 |
|---|---|---|---|
| Agent 运行时 | `agent/loop.py`、`tools.py`、`runs.py` | 1275 行，与内核仅 7 个方法耦合 | 留本体（这是“游戏引擎”） |
| 技能系统 | `services/skills/` | 5 个原生技能，直接 `import` 注册 | ✅ 天然适合 `skill` MOD |
| Agent 选项/人设 | `lmbrew.py L1131`、`options.json` | JSON 配置 + 硬编码默认值 | ✅ 天然适合 `agent-config` MOD |
| Galax | [mods/barry.galax/](mods/barry.galax/)（Phase 1 已抽离）+ `rigard.py 内置回退` | **已拆成 MOD**：`chat.mode` 注册 `⚡`，宿主保留内置回退 | ✅ 已 MOD 化（Phase 1） |
| Quasar | `rigard.js L331` | **仅前端模式位**，注释写明“专用后端上线前暂走标准对话链路” | ❌ 尚未实现，先别承诺 |
| JRVS | `jrvs.py`（3251 行）+ JRVS-7B 权重 | 内核（记忆/安全/推理/路由）与模型权重混称 | ⚠️ 需拆成“内核 MOD”与“权重分发”两件事 |
| 聊天/Agent 前端 | `kiraraGenCore.js`（4649 行） | 单闭包，模式开关硬编码 | 留本体，改造为注册表驱动 |
| 其他子应用 | rigard / niji / openmaid / cortx | 独立业务 | 不进 SimChat；可作为“第二宿主”验证平台通用性 |

**关键洞察**：现在前端的 `📎 / ⚡ / 🎯` 三个按钮，本质就是一个**硬编码的 MOD 注册表**。把这三个位置换成 `list_mods()` 动态渲染，就是平台化的第一步，而且用户几乎无感。

### 3.2 三个必须先承认的事实

- **Galax 已经是可抽的模块**：`GalaxPipeline` 独立类，输入 query、输出结构化结论，Rigard 与 Kirara 都能消费。把它做成第一个官方 MOD，能同时验证 ABI、打包、加密、跨宿主四条链路。
- **Quasar 目前是空壳**：不要把它写进首发阵容，否则社区第一次安装就发现是假的。
- **JRVS 是三种东西的合称**：`jrvs.py` 内核、JRVS-7B 模型、Hippo 记忆。三者的 MOD 形态不同，必须分开设计（见 §6）。

### 3.3 与 v1 相比新增的缺口

| 能力 | 现状 | 新定位下的要求 |
|---|---|---|
| 加载器 | 无（全是硬 import） | manifest 解析、依赖/版本、启用禁用、失败隔离 |
| 权限 | 无（工具直接跑） | 文件域、网络域、shell、凭据四类 capability |
| 签名/校验 | 无 | 包哈希 + 发布者签名 + 吊销列表 |
| 注册表 | 无 | Git 索引起步，不必先建站 |
| Automation | **无** | 全新（§7） |
| ABI 稳定性 | 无（内部调用） | 一等方 MOD 与社区 MOD 共用，必须版本化 |

### 3.4 Automation 的真实范围

仓库里没有任何通用工作流/定时引擎；`openmaid` 是 IM 网关，不是自动化。所以 `automation` 是新造轮子，最小形态应包含：

- 触发器：cron / 事件（收到消息、文件变化、Agent 完成）/ 手动
- 动作：调用 skill、发起 Agent run、发消息、写文件
- 约束：并发上限、单次超时、每日配额、失败重试与熔断、审计日志
- 表达形式：**优先 JSON DAG（可审、可静态检查）**，代码式自动化作为二期

不要一上来做“用户写任意 Python 定时跑”，那等于给每个用户装一个后门。

---

## 四、MOD 三类格式（平台的核心契约）

| 类型 | 内容 | 执行方式 | 权限 | 审核强度 |
|---|---|---|---|---|
| `agent-config` | `manifest.json` + `persona.md` / `prompt.md` / `params.json` / `theme.css` | 纯数据，不执行代码 | 无 | 自动扫描（文案合规） |
| `skill` | `manifest.json` + `skill.py`（或 JS）+ `schema.json` | 独立进程 / 受限子解释器 | `fs` `net` `shell` 需显式声明 | 人工 + 静态扫描 |
| `automation` | `manifest.json` + `flow.json`（DAG）+ 引用的 skills | 本体调度器执行 DAG | 继承所引 skill 的并集 + 配额 | 人工，默认禁用直到确认 |
| `binary`（一等方/授权方） | `manifest.json` + `*.pyd` + `*.enc` + 签名 | 进程内加载（受信任） | 白名单化 | 官方签名 |

**统一 manifest 草案**：

```json
{
  "id": "barry.galax",
  "type": "binary",
  "name": "Galax 联合推理检索",
  "version": "1.4.0",
  "abi": "lmbrew-mod/1",
  "entry": "galax.pipeline:register",
  "capabilities": { "net": ["bing.com", "sogou.com"], "fs": ["read:workspace"], "shell": false },
  "hooks": ["chat.mode", "agent.pre_answer"],
  "requires": { "lmbrew": ">=2.0,<3", "python": "3.12" },
  "assets": { "icon": "assets/galax.png" },
  "license": "proprietary",
  "signature": "ed25519:..."
}
```

三条硬规则：

1. **未知 hook 直接 fail-closed**，不静默忽略（否则版本升级会静默改变行为）。
2. **数据型 MOD 永不获得执行权**，防止“配置文件里藏代码”。
3. **binary MOD 不得调用私有 API**，只能调用 `lmbrew-mod/1` 公开面；官方自己也不例外。

---

## 五、本体 / 加载器 / MOD 的职责边界

### 5.1 必须留在本体（不可 MOD 化）

- Agent 循环与工具执行器（否则每个 MOD 各写一套，平台失去意义）
- **权限与沙箱**、内容安全闸门、审计日志
- 会话存储与最小记忆（SQLite 级）
- UI 外壳与 MOD 槽位（slot）
- 调度器与配额（automation 的执行底座）
- 模型 provider 抽象（Ollama / OpenAI 兼容）
- 崩溃隔离与降级（MOD 挂了不能带走本体）

### 5.2 可 MOD 化（一等方优先）

| MOD | 抽出对象 | 难度 | 备注 |
|---|---|---|---|
| Galax | `GalaxPipeline` + galax.js | 低 | **首发试金石**，跨 Kirara/Rigard 复用 |
| Hippo 记忆 | `jrvs.py` 的 Hippo/Cognitive | 中 | 必须给本体留一个朴素记忆实现 |
| JRVS 内核增强 | safety 之外的推理策略、路由、otherAI | 中 | 安全部分不允许抽走 |
| Quasar | 未实现 | 高 | 先做设计文档，不进首发 |
| 技能包 | 5 个原生 skill | 低 | 顺带验证 skill 权限模型 |
| 人设/主题 | options.json + kirara-mod.css | 低 | 第一类 `agent-config` 样例 |

> **纪律**：第一批官方 MOD 必须由本体的公开 hook 驱动。如果发现需要加私有钩子，说明 ABI 设计错了，先改 ABI。

### 5.3 裸壳必须能玩（生态生死线）

SimChat 本体（无任何私有 MOD）必须做到：

1. 选本地 Ollama 或填一个 OpenAI 兼容 key；
2. 能对话、能跑 Agent 任务、能装一个社区 `agent-config` 换人设；
3. 有一个朴素记忆（会话内 + 简单落盘）；
4. 有一个示例 `skill`（读文件/列目录）和一个示例 `automation`（每天 9 点总结工作区）。

做不到这四条，社区不会来；做到了，JRVS/Quasar/Galax 才有地方挂。

> **现状注记（2026-10-27，P2.4 skill MOD 化收口更新）**：SimChat 本体已具备独立对话运行时——`/api/simchat/chat`（SSE）+ sessions CRUD 直连 provider，不经 Rigard/Kirara 宿主链路（Phase 2 最小承压切片）；Loader 安全底座四片（resolver / verify+签名 / sandbox P1 / skill 迁移）全部交付，5 个原生 skill 从宿主硬编码迁成 [skill MOD](mods/)，走完整的 `discover → manifest 校验 → sandbox 启动 → register(tools) → invoke_tool` 链路（冒烟测试 11/11 PASS）；宿主侧 SkillManager 已变为薄 facade，旧 `kirara/services/skills/` + `rigard/services/skills/` 两套硬编码已删除。§5.3 裸壳四件套当前进度：① provider + 对话 runtime ✅、② Agent 工具面板需"services 透传 + lmbrew.py 接入"两项 P2 保留项落地后才能列出 skill、③ 朴素记忆 ✅、④ 示例 automation 属 Phase 5。用户定位不变：SimChat 是大模型的"液压系统"，本体必须能独立承压。

---

## 六、JRVS / Quasar / Galax 的打包形态

| 名称 | 实际是什么 | 建议 MOD 形态 | 分发 |
|---|---|---|---|
| JRVS（内核） | 推理编排、记忆、安全、路由 | `binary`，但**安全策略受本体约束** | 加密 `.pyd` + 授权 key |
| JRVS-7B（模型） | 权重 | 不进 MOD 包，走模型分发通道（Ollama registry / 自建 CDN） | 体积与授权独立 |
| Hippo | 记忆算法 | `binary` 或 `skill`（按是否含模型） | 可单独售卖/订阅 |
| Galax | 证据加权检索管线 | `binary`（含检索策略）+ `skill`（工具面） | 可跨宿主复用 |
| Quasar | 规划中的子 Agent 虚拟化 | 先出规范：`orchestrator` hook | 上线前不发布 |

**加密不等于安全**：`.pyd` 在内存里可被 dump。真正的护城河应是：

- 大模型走**服务端推理**（本地只留轻量策略），而不是把 390B 权重发到用户机器；
- 授权绑定账号/许可证 + 机器指纹 + 离线宽限期，不做强制联网（否则体验崩）；
- 每个二进制 MOD 有独立版本号，与本体 ABI 解耦，避免“升一次本体全量重编译”。

---

## 七、Automation 设计草案（从零）

```json
// flow.json
{
  "id": "daily.workspace.digest",
  "trigger": { "type": "cron", "expr": "0 9 * * 1-5" },
  "steps": [
    { "id": "scan",  "use": "skill:file_glob", "args": { "pattern": "**/*.md" } },
    { "id": "sum",   "use": "agent:run",       "args": { "goal": "总结本周变更", "input": "${scan.output}" } },
    { "id": "write", "use": "skill:file_write", "args": { "path": "digest.md", "content": "${sum.output}" },
      "approval": "required" }
  ],
  "policy": { "max_runtime_s": 300, "daily_quota": 20, "on_error": "stop" }
}
```

要点：

- `approval: required` 用于写操作，无人值守时默认拒绝而不是放行；
- 配额与熔断由本体强制执行，MOD 无法覆盖；
- 事件触发先支持“消息/文件/Agent 完成”，不做任意系统事件；
- 审计日志可回放，出问题能定位到具体 step。

---

## 八、仓库与目录

### 8.1 SimChat（开源：SDK + Loader + Registry + CLI）

```
simchat/
├── LICENSE(Apache-2.0)  README.md  SECURITY.md  CONTRIBUTING.md
├── spec/
│   ├── mod-manifest.schema.json
│   ├── capabilities.md
│   ├── hooks.md                 # 本体暴露的扩展点，语义化版本
│   └── abi-changelog.md
├── sdk/
│   ├── python/simchat_mod/      # 基类、注册装饰器、校验工具
│   └── ts/                      # 前端 MOD 的类型与 slot 契约
├── loader/
│   ├── resolver.py              # 依赖/版本/冲突
│   ├── lifecycle.py             # install/enable/disable/uninstall
│   ├── sandbox.py               # 子进程 + capability 注入
│   ├── verify.py                # 哈希/签名/吊销
│   └── index.py                 # Git 索引客户端
├── cli/                         # simchat mod init/pack/verify/publish
├── examples/
│   ├── agent-config-minimal/
│   ├── skill-hello/
│   └── automation-daily-digest/
└── registry/index.json           # 官方索引（可自托管）
```

> **Phase 2 完整落地（2026-10-27）**：`loader/` 已实现 `manifest.py`（schema 校验、未知 hook fail-closed）、`registry.py`（`chat.mode` 注册表）、`lifecycle.py`（扫描 / 加载 / 启停 / 失败隔离 + `_tools` tool 注册表 + `call_tool()` + 全局 getter）、[`resolver.py`](loader/resolver.py)（`requires.python` semver + `requires.packages` importlib.find_spec）、[`verify.py`](loader/verify.py)（binary 两阶段 integrity+ed25519+revoked）、[`keys.py`](loader/keys.py)（ed25519 密钥对/签名/验签/吊销）、[`sandbox.py`](loader/sandbox.py)（queue 响应队列 + `invoke_mode()` + `invoke_tool()` + request_id 匹配）、[`sandbox_runner.py`](loader/sandbox_runner.py)（`_LocalModApi.register_tool()` + `invoke_tool` stdin 命令 + request_id 回传 + `_sanitize` type 对象）；`sdk/python/simchat_mod/` 已提供 `ModApi`、`ModeSpec`、`ToolSpec`、`BaseSkill`、`@hook`（`register_tool()` 为 P2.4 新增）；[`skill_manager_facade.py`](loader/skill_manager_facade.py) 让旧 `get_skill_manager().execute_skill()` API 委托 `ModLoader.call_tool()`。`index.py`（索引客户端）、`cli/` 仍属 Phase 4。

### 8.2 LMBrewer（本体，可闭源分发）

```
lmbrew/
├── engine/            # Agent 循环、工具执行器、调度器、权限、审计
├── ui/                # 通用外壳 + slot 渲染 + 模式注册表
├── providers/         # Ollama / OpenAI 兼容
├── runtime/mods/      # 加载器调用点（依赖 simchat-loader）
├── mods/              # 安装目录（用户 MOD + 一等方 MOD）
│   └── barry.galax/
├── apps/              # kirara / rigard / niji / openmaid / cortx
└── build_pkg/         # Cython → PyArmor → AES-GCM（只处理 binary MOD）
```

### 8.3 与现有代码的对应

| 现文件 | 去向 |
|---|---|
| `kirara/services/agent/*` | `engine/` |
| `lmbrew.py` Agent 路由 | `engine/transport/` |
| `kiraraGenCore.js` 通用部分 | `ui/js/` |
| `kiraraGenCore.js` 人设/音色/技能/通讯 | `apps/kirara/` 或 `mods/kirara-ui/` |
| `services/skills/*` | ✅ 已迁出为官方 `skill` MOD（5 个：[noic.skill-readfile](mods/noic.readFile/) / noic.skill-websearch / noic.skill-screenshot-recognition / noic.skill-areyoutrouble / noic.skill-realitycheck）；[`skill_manager_facade.py`](loader/skill_manager_facade.py) 做 API 兼容层；旧 `.py` 已删，`skills.py` 留 facade 重导出 shim |
| `rigard/services/rigard.py::GalaxPipeline` | ✅ 已迁至 `mods/barry.galax/python/galax/pipeline.py`；宿主保留内置回退 |
| `rigard/js/galax.js` | ✅ 已移至 `mods/barry.galax/web/galax.js`，由 `list_mods()` 动态加载 |
| `jrvs.py` | 拆分：Hippo/路由/深度思考 → 官方 binary MOD；安全策略留白名单接口 |
| `kirara.py` | 归档（旧入口） |

---

## 九、迁移阶段（每阶段有可验收产物）

**Phase 0 — 冻结契约 ✅ 已完成（2026-10-24）**

产物在 [simchat/]()：

- [mod-manifest.schema.json](spec/mod-manifest.schema.json)：四类 MOD 统一 schema，已用 Draft 2020-12 校验器验证（合法样例通过，未知 hook / 非法 config / 缺签名均拒绝）。
- [capabilities.md](spec/capabilities.md)：7 类 capability + 信任等级 + 本体强制闸门。
- [hooks.md](spec/hooks.md)：10 个扩展点，含现状硬编码位置与失败语义。
- [events.md](spec/events.md)：13 个 SSE 事件、挂起/终止语义、HTTP 端点。
- [abi-changelog.md](spec/abi-changelog.md)：版本规则 + 7 项已知欠账。
- [fixtures/](fixtures/)：5 条基线（happy / approve / reject / abort / max_turns）+ 录制脚本。

⚠️ 5 条 fixture 目前是**按代码路径推导**的，不是真实模型录制。模型就绪后用 `record_agent_sse.py` 覆盖，并保留 `source` 字段区分。

**Phase 1 — 第一个 MOD：Galax ✅ 已完成（2026-10-24）**
把 `GalaxPipeline` 抽成 `mods/barry.galax/`，通过公开 hook `chat.mode` 注册前端 `⚡` 按钮；Rigard 与 Kirara 同时消费。**这是整个平台可行性的证明**。

**实际交付物**

| 层 | 文件 | 内容 |
|---|---|---|
| SDK | [simchat_mod/__init__.py](sdk/python/simchat_mod/__init__.py) | `ModApi`、`ModeSpec`、`@hook`；MOD 只能拿 `inference` / `skill_manager` / `memory` 三个注入服务 |
| Loader | [manifest.py](loader/manifest.py)、[registry.py](loader/registry.py)、[lifecycle.py](loader/lifecycle.py)、[verify.py](loader/verify.py) | 结构校验 + `chat.mode` 注册表 + 扫描/加载/启停/失败隔离 + binary 包 sha256 |
| Galax MOD | [manifest.json](mods/barry.galax/manifest.json)、[pipeline.py](mods/barry.galax/python/galax/pipeline.py)、[galax.js](mods/barry.galax/web/galax.js) | `barry.galax`（binary，`chat.mode`，net 白名单 bing.com / sogou.com），四阶段管线与前端引擎 |
| 宿主后端 | `rigard.py`、`lmbrew.py` | Rigard 启动时 `ModLoader.discover()`；`galax_query` 优先走 MOD、失败/缺失回退内置管线；新增 `/api/simchat/mods` 与 MOD 资源路由 |
| 宿主前端 | `rigard.js`、`rigard.html` | 模式菜单由 `list_mods()` 动态渲染，按 `frontend_entry` 动态加载脚本；移除硬编码 ⚡ / 🎯 与静态脚本引用 |

**验收结果（2026-10-24）**

- **卸载**：空 `mods/` 目录下 `list_mods()` 返回空，`⚡` 不出现，普通对话正常；`galax_query` 回退内置管线。
- **装载**：`barry.galax` 状态 `loaded`，注册模式 `galax`；浏览器实测菜单出现 `⚡Galax模式`、无 Quasar 项，点击后按钮显示 `Galax`，`web/galax.js` 返回 200，无控制台错误。
- **后端**：`galax_query` 确认优先调用 MOD backend；Python 3.9 编译、Flask 测试客户端、真实浏览器冒烟均通过。

**Phase 1 保留项**

- 内置 `GalaxPipeline` 暂留 `rigard.py` 作为卸载/异常回退，待 Phase 2 再移除。
- Galax 专属 CSS 仍在 `rigard/rigard.css`，下一阶段随 `web/` 迁出。
- `signature` 当前只校验字段存在；ed25519 验签与吊销列表属 Phase 2/4。
- binary MOD 的 `integrity` 是包内容 sha256；修改 MOD 文件后需重新计算，否则 loader fail-closed。


**Phase 2 — Loader + 权限 + 隔离 + 本体独立对话运行时**
实现 install/enable/disable、依赖解析、签名校验、子进程沙箱、崩溃隔离；把 5 个原生 skill 迁成 MOD 并声明 capability。

同时补齐 SimChat 的"液压系统"底座，使本体脱离宿主可独立承压（2026-10-26 用户确认的显式交付物）：

1. **独立对话端点**：`POST /api/simchat/chat`（SSE），经 provider 抽象直连 Ollama / OpenAI 兼容端点，不经过 Rigard/Kirara 任何宿主链路；
2. **本体级会话与朴素记忆**：SimChat 自有 session 存储 + 简单落盘记忆，不依赖 Rigard 的 SessionManager / Kirara 的 Hippo；
3. **裸壳验收**：空 `mods/` 目录下 SimChat 独立完成一轮完整对话；卸载全部 MOD 后本体功能不退化。

> **最小承压切片已完成（2026-10-26）**：[simchat/runtime/](runtime/) 落地——`providers.py`（Ollama 流式 + OpenAI 兼容 SSE 逐行解析，统一 `ProviderError`）、`store.py`（`simchat/data/sessions/<sid>.json` 落盘，滑动窗口 40 条，首条消息自动命名）、`core.py`（`SimChatCore.chat_stream` 编排，`simchat/data/config.json` 热加载）；`lmbrew.py` 注册 `/api/simchat/chat`（SSE）+ sessions CRUD，**不调用** `init_rigard()`/`init_jrvs()`；事件契约冻结于 [events.md §6](spec/events.md)（`chat_started`/`token`/`final`/`error`）。验收 15/15 通过（真实 JRVS-7B 两轮对话、token 拼接与 final 一致、历史增长、CRUD、宿主零初始化、未配置 provider 的 error 路径）。沙箱/签名/依赖解析与 skill 迁移仍属 Phase 2 剩余范围。
>
> **Loader 安全底座三片已落地（2026-10-26 收尾）**：施工方案见 [simchat-phase2-remaining-plan.md](./simchat-phase2-remaining-plan.md)。
> - **P2.1 resolver**（commit `494c5e9`）：[simchat/loader/resolver.py](loader/resolver.py) 新增；`requires.python` semver 范围比较 + `requires.packages` importlib.find_spec 检查；fail-closed。
> - **P2.2 verify + ed25519 签名**（commit `fd7444f`）：[keys.py](loader/keys.py) 新增（密钥对/签名/验签/吊销），[verify.py](loader/verify.py) binary 类型改两阶段（integrity + ed25519 + revoked 列表）；[public_keys/official.ed25519.pub](loader/public_keys/official.ed25519.pub) 内置；barry.galax 真签名落盘。
> - **P2.3 子进程沙箱 Phase 1**（commit `26367b0`）：[sandbox.py](loader/sandbox.py) + [sandbox_runner.py](loader/sandbox_runner.py) + [sandbox_contract.md](loader/sandbox_contract.md)；只做进程级 crash 隔离 + `capabilities.shell` 闸门 + 30s 超时；不做 FS/网络/seccomp 隔离；invoke 转发留给后续切片。7 场景冒烟全过。
>
> 剩余 P2.4（5 个原生 skill 迁成 `skill` 类型 MOD）**已完成（2026-10-27）**：commit `133b552`（SDK ToolSpec + sandbox invoke_tool 链路 + lifecycle._tools.call_tool）+ commit `e03e310`（5 个 skill MOD 包 + SkillManager facade + 旧 skill 目录删除）；冒烟测试 11/11 PASS。详情见 [simchat-phase2-remaining-plan.md §P2.4](./simchat-phase2-remaining-plan.md)。

**Phase 3 — 前后端断开再接起 ✅ 已完成（2026-10-26）**
施工方案与逐片验收见 [simchat-phase3-plan.md](./simchat-phase3-plan.md)；通用状态路由归属的单独评估见 [simchat-phase3.7-eval.md](./simchat-phase3.7-eval.md)。

| 切片 | 交付 | 结果 |
|---|---|---|
| P3.0 | git init + 基线快照 | 每片一个 commit，可逐片 revert |
| P3.1 | Niji 9 个 API + 2 个页面/静态路由迁入 niji_server.py | 页面/静态/`/api/niji/open` 冒烟通过 |
| P3.2 | Rigard 15 个 API + 3 个页面/静态路由迁入 rigard_server.py | MOD 装载/卸载双态回归通过 |
| P3.3 | OpenMaid 19 个 API + 3 个页面/静态路由迁入 openmaid_server.py | 网关/IM status 错误形状不变 |
| P3.4 | kiraraGenCore.js 引入 `KIRARA_API` 常量表 | 20 处裸 `fetch('/api/...')` 归零 |
| P3.5 | Kirara 22 个 API + 3 个页面/静态路由迁入 kirara_server.py | 路由回归 + 页面/静态 200 |
| P3.6 | `ModRegistry` + `agent-config-minimal` 样例 MOD | 空 `mods/` 裸壳可用，装载后人设清单变化 |
| P3.7 | 通用状态路由归属评估 + P3.5 残留修复 | 保留宿主；24/24 冒烟 |

**结构指标**：`lmbrew.py` 1829 → **344 行**（≤400 目标达成）；4 个蓝图接管应用路由，宿主只剩装配、SimChat 平台面与宿主级进程治理；路由总数 88，对外 URL / SSE 事件 / 字段零变更。

**P3.7 结论**：`/api/status`、`/api/ai/<ai_name>/{status,start,stop}` 保留在宿主——它们绑定宿主进程内的 `ai_processes`、atexit/信号清理、端口 5000 与 LMBrewer 私有应用清单，迁入 SimChat 会让平台库反向依赖宿主，违反 §5「其他子应用不进 SimChat」。评估全文见 [simchat-phase3.7-eval.md](./simchat-phase3.7-eval.md)。

**收尾时修复的 P3.5 残留**：Kirara 蓝图调用未定义的 helper（`_get_agent_shell_options` / `_agent_sse_response` / `get_user_path` / SMTP / reset）、错误的 `__file__` 路径基准（页面与配置指向不存在目录）、根目录遗留 `kirara.py` 遮蔽 `kirara` 包导入（宿主启动 `ImportError`）。均为结构迁移缺陷，不涉及业务逻辑。

> Phase 3 收尾已补齐：`agent-config-minimal` 现通过 loader schema 校验，声明 1 个女仆人设 + 1 套简约主题 CSS，lifecycle 新增 agent-config 特殊加载分支（纯数据 MOD 无需 invoke entry）；前端 ModRegistry 从 lifecycle.list_mods() 直接读 config 对象，MOD 加载失败时在人设面板上方注入非阻塞可关闭警告条。Phase 3 所有定义项均已达标。

**Phase 4 — CLI + 索引**
`simchat mod init/pack/verify/publish`；Git 索引 + 官方签名；社区可提 PR 上架。此阶段再考虑网页商店。

**Phase 5 — Automation 引擎**
DAG + 调度器 + 配额 + 审批 + 审计；先内置示例，不开放任意代码。

**Phase 6 — 仓库/品牌/社区**
拆仓、CI（用 `agent-config-minimal` + `skill-hello` 跑无模型测试）、贡献指南、MOD 作者协议、付费分成规则。

---

## 十、风险清单

| 风险 | 说明 | 对策 |
|---|---|---|
| 生态冷启动 | 本体不好玩，没人来做 MOD | 裸壳四件套（§5.3）先达标再谈平台 |
| 官方走后门 | 一等方 MOD 用私有 API，社区失去信任 | ABI 公开且官方 dogfood；CI 禁止私有 import |
| 恶意 MOD | 用户 MOD 可读文件/联网/执行 | capability + 子进程沙箱 + 签名 + 吊销 + 默认最小权限 |
| Automation 失控 | 无人值守写文件/发消息 | DAG 而非任意代码；写操作默认需审批；硬配额 |
| 加密被逆向 | `.pyd` 可 dump | 重资产服务端化；授权 key + 指纹 + 宽限期 |
| ABI 频繁变 | 本体升级打爆所有 MOD | ABI 语义化版本 + 兼容层 + MOD 侧声明范围 |
| 安全被 MOD 化 | 恶意 MOD 关闭安全闸门 | 安全、权限、审计永留本体 |
| Quasar 空承诺 | 前端有按钮无后端 | 首发阵容不包含 Quasar |
| 名称歧义 | “SimChat”像聊天 App，不像平台 | 保留 SimChat 作 SDK/运行时名，商店另起品牌 |
| 范围爆炸 | 5 个子应用一起改 | 只改 Kirara + Rigard 两个宿主，其余不动 |

---

## 十一、商业与治理

- **本体**：免费或低价买断，保证可玩；企业版卖部署/审计/合规。
- **一等方 MOD**：JRVS 订阅、Galax 授权（Rigard B2B 已有场景）、Quasar 上线后再定价。
- **平台抽成**：付费 MOD 分成；免费 MOD 不收，先做规模。
- **治理**：MOD 作者保留版权；平台只做分发许可；明确下架/DMCA/安全披露流程。
- **许可**：SDK/加载器 Apache-2.0（允许闭源 MOD）；本体 EULA 明确“允许为互操作而逆向加载器接口”。

---

## 十二、需要你拍板

1. **本体是否闭源**？建议：闭源分发 + 开源 loader/SDK/spec（Minecraft 路线）。
2. **首个官方 MOD 是否选 Galax**？建议是，它已落地且可跨宿主复用，风险最低。
3. **Quasar 是否从首发/对外文案中撤下**？建议撤下，等有后端再上。
4. **Automation 首发只做 DAG**？建议是，代码式自动化二期。
5. **付费 MOD 是否首发开放**？建议二期，先把免费生态做起来。

---

## 十三、最小可行切片（两周内可验证概念）

只做三件事：

1. `spec/` + `loader/`（install/enable/disable + manifest 校验 + capability 检查）
2. 把 Galax 抽成 `mods/barry.galax/`，前端模式按钮由注册表渲染
3. 一个 `agent-config-minimal` 示例 + `simchat mod pack` CLI

验收：**卸载 Galax 后本体正常对话，装上后 `⚡` 按钮出现且行为与现在一致**。这一条过了，平台模型就成立；过不了，说明 ABI 还没设计对，别急着建商店。
> 2026-10-24：上述验收已在 Rigard 宿主上通过，详见 §9 Phase 1 的交付物与验收结果。
