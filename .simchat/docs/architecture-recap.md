# SimChat 架构分层改造方案

> Minecraft 比喻的精确落地：把"方块"和"Mod"从概念上彻底拆开，让 SimChat 成为真正的"AI 应用毛坯房"。

---

## 0. 比喻锚定（不可动摇）

| 比喻 | SimChat 对应 | 职责 |
|---|---|---|
| **JVM** | Ollama / API / Llama.cpp | 底层推理引擎，可替换，对上透明 |
| **Mojang + Forge/Fabric** | SimChat 本体 + MOD 加载器 | 游戏核心引擎 + 模组加载框架 |
| **方块** | 引擎内建原子能力 + skill MOD | 不可再分的原子原语，Agent 可调用 |
| **Mod（应用包）** | binary 类型 MOD | 有独立技能组合 + 前端界面 + 业务逻辑 |
| **地图（AI 实例）** | settings + memory + history + enabled_mods | 一次完整运行的状态快照 |

---

## 1. 当前问题诊断

### 1.1 概念混淆：方块和 Mod 被塞进同一个盒子

`loader/manifest.py` 的 `KNOWN_TYPES` 把四种东西并列：

```python
KNOWN_TYPES = frozenset(["agent-config", "skill", "automation", "binary"])
```

但它们的生命周期、消费方、能力级别完全不同：

| 类型 | 实际层级 | 消费方 | 类比 Minecraft |
|---|---|---|---|
| `skill` | **方块层** | AgentLoop 内部消费（注册为 Tool） | 草、石头、TNT |
| `binary` | **Mod 层** | 前端路由 + Flask Blueprint | 一个完整的新游戏模式（比如 Hypixel 起床战争） |
| `agent-config` | 配置数据包 | 前端直接读 JSON | 世界类型预设（超平坦/大型生物群系） |
| `automation` | 工作流包 | 调度器消费 | 红石电路脚本 |

当前的做法是把 skill（方块）也当成 MOD 走 sandbox 子进程 + manifest 签名，这没错——但导致"方块"和"Mod"两个层级的概念边界模糊了。用户说"Mod 列表里显示的那些其实是方块的部分"，就是这个意思。

### 1.2 方块层缺少引擎内建原子能力

Kirara 原版（`E:\LMBrewer\kirara\services\agent\tools.py`）有一套**硬编码在引擎里**的原子工具：`FileReadTool`、`GlobTool`、`GrepTool`、`ShellTool`。这些东西不经过 MOD 加载器，引擎启动时直接注册到 `TOOL_REGISTRY`。

迁移到 SimChat 后，这套工具被改写成了 skill MOD（`noic.webSearch` 等），全部走 sandbox 子进程加载。问题：**本体里没有任何不可被移除的原子能力**——如果把 `noic.skill-readfile` 删了，SimChat 就真的失去了文件读取能力。

Minecraft 里方块是引擎内建的，Forge 能加新方块但不能移除引擎内建的。SimChat 应该也有这个保障。

### 1.3 binary MOD 缺少完整的独立应用契约

Kirara 原版和 Niji 都是**独立的 Flask Blueprint + 独立的前端静态资源 + 独立的 data/ 目录**：

```
kirara/services/kirara_server.py  → kirara_bp = Blueprint(...)
kirara/html, js, css, memories/   → 自己的前端和数据

niji/niji_server.py               → 独立 Flask app
niji/static/, templates/, projects/ → 自己的前端和存档
```

而当前 `barry.galax`（唯一的 binary MOD）有 `web/galax.js` 和 `python/galax/pipeline.py`，但：
- 没有独立的 Flask Blueprint 注册机制（hook 走 `chat.mode`）
- 没有独立的 data/ 目录分配
- 前端静态资源怎么被服务的？不清晰

### 1.4 残留命名：lmbrew → simchat

ABI、requires 字段、变量名里残留 `lmbrew`，容易让未来读代码的人困惑。

---

## 2. 分层重构方案

### 2.1 总览图

```
┌─────────────────────────────────────────────────────────┐
│                    地图层（AI 实例）                       │
│  settings.json | memory.json | conversations.jsonl       │
│  enabled_blocks[] | enabled_mods[] | model selection     │
├─────────────────────────────────────────────────────────┤
│                     Mod 层（应用包）                       │
│  binary MODs: 独立 Blueprint + 前端 + data/ 目录          │
│  barry.galax / 未来的完整应用包                            │
├─────────────────────────────────────────────────────────┤
│                     方块层（原子能力）                      │
│  ┌──────────────────┐  ┌─────────────────────────────┐  │
│  │ 引擎内建方块       │  │ skill MODs（可插拔方块）      │  │
│  │ file_read        │  │ noic.webSearch              │  │
│  │ file_write       │  │ noic.screenshotRecognition   │  │
│  │ glob / grep      │  │ 第三方 skill MODs             │  │
│  │ shell            │  └─────────────────────────────┘  │
│  └──────────────────┘                                    │
├─────────────────────────────────────────────────────────┤
│                     加载器层（Forge/Fabric）               │
│  manifest 校验 | sandbox | 依赖解析 | 签名验证            │
│  BlockRegistry | ModRegistry                             │
├─────────────────────────────────────────────────────────┤
│                     引擎层（Mojang）                       │
│  runtime/* | AgentLoop | providers.py | lifecycle         │
├─────────────────────────────────────────────────────────┤
│                     JVM 层                                │
│  Ollama | OpenAI Compat | Llama.cpp                      │
└─────────────────────────────────────────────────────────┘
```

### 2.2 方块层改造

**目标**：让方块成为一等公民，有独立的注册表，引擎内建方块不可移除。

#### 2.2.1 新增 `runtime/capabilities.py`（引擎内建方块注册表）

参考 Kirara 原版 `services/agent/tools.py`，把原子工具硬编码到本体：

```python
# runtime/capabilities.py
class BlockRegistry:
    """引擎内建原子能力注册表（类似 Minecraft Block.REGISTRY）。"""
    
    _blocks = {}
    
    @classmethod
    def register(cls, block):
        """注册一个内建方块。"""
        cls._blocks[block.name] = block
    
    @classmethod
    def get(cls, name):
        return cls._blocks.get(name)
    
    @classmethod
    def list_all(cls):
        """返回全部可用方块（内建 + skill MOD 注册）。"""
        # 内建方块 + loader.skill_manager 注册的可插拔方块
        ...

# 内建方块（硬编码，不可被禁用或移除）
BlockRegistry.register(FileReadTool())
BlockRegistry.register(ListDirTool())
BlockRegistry.register(GlobTool())
BlockRegistry.register(GrepTool())
BlockRegistry.register(FileWriteTool())
BlockRegistry.register(FileEditTool())
BlockRegistry.register(ShellTool())
BlockRegistry.register(WebFetchBlock())    # 新增：网页内容抓取（原子能力）
BlockRegistry.register(ImageGenBlock())    # 新增：图像生成原子能力（调用模型提供商的图像 API）
```

**与 skill MOD 的关系**：
- 内建方块 = Minecraft 的草、石头、水（引擎硬编码）
- skill MOD = Forge 加载的新方块（可替换、可禁用，但注册到同一个 `BlockRegistry`）
- AgentLoop 统一从 `BlockRegistry` 消费，不区分来源

#### 2.2.2 manifest schema 调整

```json
// skill MOD manifest（方块包）
{
  "id": "noic.webSearch",
  "type": "skill",
  "layer": "block",           // 新增字段：明确归属方块层
  "hooks": ["agent.block"],   // hook 名从 agent.tool → agent.block
  "entry": "webSearch:register",
  "capabilities": { "net": { "domains": ["*"] } }
}

// binary MOD manifest（应用包）
{
  "id": "barry.galax",
  "type": "binary",
  "layer": "mod",             // 新增字段：明确归属 Mod 层
  "hooks": ["chat.mode", "web.blueprint"],  // 新增 web.blueprint hook
  "entry": "galax.pipeline:register",
  "assets": {
    "web": "web/",            // 前端资源目录（本体自动挂载静态路由）
    "blueprint": "galax.pipeline:bp"  // 可选：独立 Flask Blueprint
  }
}
```

#### 2.2.3 ABI 重命名

```
ABI: lmbrew-mod/1  →  simchat-mod/2
requires.lmbrew     → requires.simchat
```

### 2.3 Mod 层改造

**目标**：让 binary MOD 真正成为"有自己的技能、界面、逻辑"的完整应用包。

#### 2.3.1 独立 Blueprint 注册机制

binary MOD 的 manifest 可以声明 `hooks: ["web.blueprint"]`，本体加载时：

```python
# loader/lifecycle.py 改造
def _load_binary_mod(self, package_dir, manifest):
    # ... 现有校验 ...
    handle = run_isolated(package_dir, manifest["entry"], manifest)
    
    # 新增：Blueprint 注册
    if "web.blueprint" in manifest.get("hooks", []):
        bp_ref = manifest.get("assets", {}).get("blueprint")
        if bp_ref:
            mod_name, attr = bp_ref.rsplit(":", 1)
            importlib.import_module(mod_name)
            bp = getattr(sys.modules[mod_name], attr)
            # 给蓝图分配独立 URL prefix 和 data 目录
            data_dir = self._ensure_mod_data_dir(manifest["id"])
            bp.data_dir = data_dir
            self._blueprints.append(bp)
```

#### 2.3.2 每个 Mod 独享 data/ 目录

```
data/
  galex/              ← barry.galax 的存档（类似 niji/projects/）
    sessions.json
    pipeline_cache.json
  kirara/             ← Kirara 应用包的存档（如果它也是一个 binary MOD）
    memories/
    options.json
  user/               ← 用户个人档案（全局，不属于任何 Mod）
    profile.json
  agent_runs/         ← Agent 审批挂起态（运行时，不属于任何 Mod）
```

这个目录分配由本体自动管理，MOD 代码通过宿主 API 获取路径：

```python
# SDK 扩展：simchat_mod/mod_context.py
class ModContext:
    """注入到 MOD 的运行时上下文。"""
    
    def __init__(self, mod_id, data_dir, block_registry):
        self.mod_id = mod_id
        self.data_dir = data_dir  # MOD 独占的数据目录
        self.blocks = block_registry  # 可调用的方块注册表（不暴露本体内部）
```

#### 2.3.3 前端静态资源路由

binary MOD 的 `web/` 目录由本体自动挂载：

```python
# web/__init__.py 新增
@app.route('/mods/<mod_id>/<path:filename>')
def serve_mod_asset(mod_id, filename):
    mod = get_loader().mod_path(mod_id)
    web_dir = os.path.join(mod, "web")
    return send_from_directory(web_dir, filename)
```

前端通过 `/mods/barry.galax/galax.js` 访问，MOD 前端资源之间可以互相引用（类似 Minecraft 的资源包加载机制）。

### 2.4 地图层（AI 实例）—— 确认现状

这一层用户确认已经存在，核心结构：

```json
// 每个 AI 实例（地图）的配置快照
{
  "world_type": "creative",          // 神经引擎预设（普通/工作/代码/创意/W-Synk）
  "model": "ollama::televi/JRVS-7B",  // 模型选择
  "blocks_enabled": ["file_read", "glob", "web_fetch"],  // 这个实例启用哪些方块
  "mods_enabled": ["barry.galax"],    // 这个实例加载哪些 Mod
  "memory": "...",                    // 长期记忆（类似玩家经验值）
  "conversations": "...",             // 完整对话历史（类似世界修改日志）
  "persona": "maid",                  // 人设（类似出生点设置）
}
```

---

## 3. 实施计划

### Phase 1：清理与命名（低风险）

- [ ] ABI 重命名：`lmbrew-mod/1` → `simchat-mod/2`
- [ ] `requires.lmbrew` → `requires.simchat`
- [ ] 本体内部变量、注释、日志中的 `lmbrew` → `simchat`
- [ ] `loader/manifest.py` 新增 `layer` 字段校验（`block` / `mod`）
- [ ] 更新所有现有 MOD 的 manifest.json（加 `layer` 字段 + ABI）

### Phase 2：方块层确立（中风险）

- [ ] 新建 `runtime/capabilities.py`，从 Kirara 原版迁移硬编码工具（`FileReadTool`、`GlobTool`、`GrepTool`、`ShellTool`、`WebSearchTool` → 改名为 `WebFetchBlock`，与 skill MOD 区分）
- [ ] 建立 `BlockRegistry` 单例，内建方块直接注册，skill MOD 通过 loader 挂载到同一个注册表
- [ ] AgentLoop 的工具消费逻辑改为从 `BlockRegistry` 获取
- [ ] `skill` 类型 MOD 的 hook 名从 `agent.tool` 改为 `agent.block`（或同时兼容旧名，过渡期）

### Phase 3：Mod 层完善（中风险）

- [ ] 每个 binary MOD 自动分配 `data/<mod_id>/` 目录
- [ ] SDK 新增 `ModContext`：注入 `data_dir`、`BlockRegistry` 访问权限
- [ ] `web/` 静态资源自动路由（`/mods/<mod_id>/`）
- [ ] 支持 `hooks: ["web.blueprint"]`，自动注册独立 Flask Blueprint
- [ ] 更新 `barry.galax` manifest + 代码，让它成为第一个真正符合新契约的应用包

### Phase 4：地图层与方块层的联动（低风险，整合）

- [ ] 每个 AI 实例（地图）配置 `blocks_enabled` 列表：决定这个地图里禁用哪些方块（类似 Minecraft 的游戏规则）
- [ ] 每个 AI 实例配置 `mods_enabled` 列表：决定这个地图加载哪些 Mod（类似 Minecraft 的世界内 Mod）
- [ ] AgentLoop 初始化时，按当前实例的配置过滤 `BlockRegistry` 和 `ModRegistry`

---

## 4. 不做什么

- **不删除 sandbox 机制**：skill MOD 仍然走沙箱子进程，安全契约不变
- **不废弃现有 skill MOD**：它们只是"可插拔方块"，继续有效，只是在概念上明确了层级
- **不废弃 loader.lifecycle.ModLoader**：它同时负责方块层（skill MOD）和 Mod 层（binary MOD）的加载，内部按 `layer` 字段分支
- **不碰地图层（AI 实例）的核心实现**：用户确认已存在，Phase 4 只做联动

---

## 5. 类比速查表

| SimChat 概念 | 对应 Minecraft | 谁造的 | 可被谁替换 |
|---|---|---|---|
| Ollama / API / Llama.cpp | JVM（Java 虚拟机） | 第三方 | 用户选 |
| `runtime/providers.py` | JVM 抽象层 | SimChat 本体 | 本体硬编码 |
| `runtime/capabilities.py` 内建方块 | 引擎内建方块（草、石头、水） | SimChat 本体 | **不可替换** |
| skill MOD（`noic.webSearch` 等） | Forge 加载的新方块 | 开发者 | 可替换、可禁用 |
| BlockRegistry | `Block.REGISTRY`（全局方块注册表） | SimChat 本体 | 本体硬编码 |
| binary MOD（`barry.galax` 等） | 完整的新游戏模式（起床战争、SkyBlock） | 开发者 | 可替换、可禁用 |
| AI 实例（地图） | Minecraft 世界存档 | 用户创建 | 用户随意新建 |
| AI 实例的 `blocks_enabled` | 游戏规则（禁用火焰蔓延、禁用苦力怕） | 用户 | 随时改 |
| AI 实例的 `mods_enabled` | 世界内 Mod 列表 | 用户 | 随时改 |
| loader/sandbox | Forge 安全沙箱 | SimChat 本体 | 本体硬编码 |
| manifest.json + 签名验证 | Forge mods.toml + 签名系统 | SimChat 本体 | 本体硬编码 |
