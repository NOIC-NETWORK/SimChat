# Phase 2 剩余施工方案：Loader 安全底座 + Skill MOD 化

> 本文档是 [simchat-separation-plan.md §9 Phase 2](simchat-separation-plan.md#L317-L326) 的剩余切片——Phase 2 的本体独立对话运行时（simchat/runtime/）已在 2026-10-26 完成，以下是同 Phase 下的 Loader 底座与 skill 迁移。
> 决策池见 [simchat-open-decisions-pool.md](./simchat-open-decisions-pool.md)——当前无 §12 决策依赖。

## 进度总览（2026-10-27 收尾）

| 切片 | 状态 | Commit | 关键交付 |
|---|---|---|---|
| P2.1 resolver | ✅ 已完成 | `494c5e9` | [simchat/loader/resolver.py](loader/resolver.py)：requires.python semver 范围比较 + requires.packages importlib.find_spec 检查；lifecycle 集成 |
| P2.2 verify+签名 | ✅ 已完成 | `fd7444f` | [simchat/loader/keys.py](loader/keys.py) ed25519 密钥对/签名/验签/吊销；[verify.py](loader/verify.py) binary 两阶段（integrity+signature+revoked）；[public_keys/official.ed25519.pub](loader/public_keys/official.ed25519.pub) 内置；barry.galax 真签名落盘 |
| P2.3 sandbox | ✅ 已完成 | `26367b0` | [sandbox_contract.md](loader/sandbox_contract.md) IPC 协议；[sandbox_runner.py](loader/sandbox_runner.py) 子进程侧 entry；[sandbox.py](loader/sandbox.py) 宿主侧 run_isolated + 进程管理；capabilities.shell=false 时 monkey-patch subprocess.Popen |
| P2.4 skill 迁移 | ✅ 已完成 | `133b552` + `e03e310` | SDK ToolSpec + ModApi.register_tool() + sandbox_runner invoke_tool + sandbox.py 宿主 invoke_tool + lifecycle._tools.call_tool() + [SkillManager facade](loader/skill_manager_facade.py) + 5 个 skill MOD（见下文） |

**关键设计决策（已锁定）**：
- 签名方案：ed25519 + `integrity \0 version \0 json.dumps(requires, sort_keys=True, separators=(",",":"))` canonical payload，格式 `ed25519:<base64url>`
- 私钥位置：`dev-keys/official.ed25519.pem`（gitignored，绝不进仓库）
- 沙箱 Phase 1 边界：只做进程级 crash 隔离 + shell 闸门 + 超时；不做 FS/网络/seccomp 隔离；invoke 转发（前端调 MOD backend 的管道）留给后续切片
- agent-config 沙箱豁免：lifecycle 硬编码分支，注释明确"无代码执行"契约不得删除

---

## 一、为什么这四件要做

| 事实 | 数据 |
|---|---|
| verify.py 当前只做 sha256 integrity | ed25519 签名字段 manifest 强制但 verify.py 不验 |
| 无依赖解析 | requires.packages 是 manifest 字段但没有 resolver.py |
| 无沙箱 | binary MOD 直接在宿主 Python 进程里 import（lifecycle._invoke_entry 调用 importlib.import_module） |
| 5 个原生 skill 是宿主硬编码 | kirara/services/skills/ 和 rigard/services/skills/ 各一份，BaseSkill/get_skill_manager 是宿主基类，skill MOD 形态未验证 |
| 官方已跑过的 binary MOD | mods/barry.galax/ 是 binary 类型，签名/打包/索引 Phase 4 要依赖 verify+sandbox |

风险本质：Phase 4 CLI `simchat mod install` 会从索引下载 MOD——如果没有签名 + 沙箱 + 依赖解析，安装就是裸奔。skill 迁移是验证 `skill` 类型 MOD 的契约（hook=agent.tool、capabilities 声明），同时消除 kirara/rigard 两份硬编码。

---

## 二、切片规划（每片独立 commit、可验收、可回滚）

> 切片顺序是逻辑依赖链：resolve 先（生命周期里 requires 校验只看 requires.lmbrew，不看 packages）→ verify（签名验完才能放心沙箱）→ sandbox（binary MOD 必须隔离）→ skill MOD（依赖 sandbox + manifest skill 类型）。

### P2.1 — `loader/resolver.py`：依赖解析 ✅ 已完成（commit `494c5e9`）

**断**：lifecycle.py 里只有 `check_requires(manifest, host_version)` 检查本体版本范围，完全跳过 `requires.packages`（第三方 Python 包）；`requires.python` 也没检查。

**接**：新增 resolver.py，职责：
- 解析 manifest.requires：`lmbrew`（本体版本）、`python`（运行时版本）、`packages`（第三方包列表）。
- packages 策略：**不自动 pip install**（自动装包是宿主行为，MOD 不能触发），只返回"当前环境缺失哪些包"；加载器据此 fail-closed：缺失必需依赖 → MOD status=failed。
- 返回 (ok: bool, message: str, missing: list[str])，被 lifecycle._load_one 在 check_requires 之后、verify_package 之前调用。

**验收**：
1. 写一个测试 MOD，manifest.requires.packages 里放 `nonexistent_package_xyz` → lifecycle.discover 后 list_mods 返回 status=failed、error 里列出缺失包。
2. 写一个 requires.python 超出当前环境的 MOD → 同样 fail-closed。
3. 既有 barry.galax / agent-config-minimal 的 requires 字段（barry.galax 无 requires，agent-config-minimal 有 requires.lmbrew）不回归。

**依赖**：manifest.py 的 requires 字段 schema 已定义；不需要 spec 改动。

**不做**：不做远程依赖解析；不做版本范围交叉比对（只做 in/not in）；不做安装提示的前端 UI。

---

### P2.2 — `verify.py` 补 ed25519 验签 + 吊销列表 ✅ 已完成（commit `fd7444f`）

**断**：verify_package 只在 binary 类型时比对 sha256 integrity；manifest 里 signature 字段强制但从未验证。签名方案（ed25519、谁的公钥、密钥如何存放）完全未定义。

**接**：
1. 选择签名方案：**ed25519 签名**（Python `cryptography` 库内置、快、后量子相对安全）。
2. manifest.signature → 签的是 `integrity` + `version` + `requires`（不是整个 manifest.json 文件——manifest 自己不进 integrity，签它会有循环）。
3. 公钥存放：**本体内置官方公钥（`simchat/loader/public_keys/official.ed25519.pub`）**；用户自托管索引可通过 CLI 额外注册公钥（Phase 4 再做）。
4. 吊销列表：`simchat/loader/public_keys/revoked.json`（key-id → 吊销原因 + 时间），加载器验签后查吊销列表。
5. verify_package 改签名：返回 (ok, message) 保持；binary MOD 先验 integrity，再验 signature，再查吊销——任一失败 → fail-closed。非 binary MOD 不验签（agent-config/skill/automation 暂不强制签名）。

**验收**：
1. 签一个测试 binary MOD（用私钥签 integrity+version+requires），verify_package → ok=True。
2. 改测试 MOD 里的 integrity 值 → ok=False，message 含"integrity 不匹配"。
3. 换一把随机私钥签同一 MOD（signature 不对）→ ok=False，message 含"签名无效"。
4. 把测试 MOD 的 key-id 写进 revoked.json → ok=False，message 含"已吊销"。
5. agent-config-minimal / barry.galax 不回归（barry.galax 当前没有 signature 字段，需要先给它生成一个——这步纳入本片）。

**依赖**：`cryptography` 库（pip install cryptography，Windows 环境自带 wheel 无需编译）；Phase 4 的 CLI 需要签名命令（不在本片）。

**不做**：不做用户自定义公钥注册（Phase 4）；不做自动化的二进制打包签名 CLI（Phase 4）。

---

### P2.3 — `loader/sandbox.py`：子进程隔离（Phase 1 切片） ✅ 已完成（commit `26367b0`）

**断**：binary MOD 通过 `importlib.import_module` 直接在宿主 Python 进程 import（[lifecycle.py _invoke_entry](loader/lifecycle.py#L150-L173)）。一个恶意 MOD 可以 `os.system('rm -rf /')` 或 `subprocess.Popen('powershell -Command ...')`。

**接**：sandbox.py 的 Phase 1 切片只做一件事——**子进程执行入口**：
1. 不做完整能力隔离（WASM / seccomp / AppContainer 太重，Phase 2 剩余先不碰）。
2. 只做"把 MOD 入口放到独立 Python 子进程"，进程崩溃不拖宿主；`sys.path` 注入 MOD 包目录后再调用 `module:attr`。
3. 子进程 stdout/stderr 回传宿主（logging），进程超时（默认 30s，可配置），`--capabilities.shell=true` 的 MOD 才允许创建新子进程（**进程树隔离**）。
4. sandbox.py 提供 `run_isolated(module_name, attr, args, timeout)` 接口；lifecycle._invoke_entry 改为 `sandbox.run_isolated(manifest.entry.split(':'))`。
5. 失败回退：子进程超时/崩溃 → MOD status=failed，宿主继续运行其他 MOD。

**验收**：
1. 写一个测试 binary MOD 入口是 `raise SystemExit(1)` → lifecycle 发现 status=failed，宿主继续跑。
2. 写一个测试 binary MOD 入口是 `time.sleep(120)` 但 timeout=30s → 超时被 kill。
3. 写一个测试 binary MOD 入口是 `subprocess.Popen('powershell')` 但 manifest.capabilities.shell != true → sandbox 拒绝创建子进程，进程内 raise PermissionError。
4. barry.galax 入口在新沙箱里跑通（chat.mode 钩子注册正常）。
5. agent-config-minimal 不受影响（纯数据 MOD 不经过 _invoke_entry）。

**依赖**：P2.2 的 verify.py（签名必须在沙箱之前通过，否则子进程里 import 恶意代码无意义）。

**不做**：不做 WASM/seccomp/AppContainer 级别的文件/网络/系统调用隔离；不做 `sys.modules` 黑名单（如禁 import `os`、禁 `subprocess`）；不做 agent-config/skill/automation 三种非 binary 类型的沙箱（它们不 import 代码）。完整能力隔离留给 Phase 4 或之后。

---

### P2.4 — 5 个原生 skill 迁成 `skill` 类型 MOD + capability 声明 ✅ 已完成（commit `133b552` + `e03e310`）

**断**：5 个 skill（readFile / webSearch / screenshotRecognition / areYouUnderTrouble / realityCheck）硬编码在 `kirara/services/skills/` 和 `rigard/services/skills/`（两份重复），基类 `BaseSkill` / `get_skill_manager` 是宿主私有代码。skill MOD 类型的契约（hook=agent.tool、capabilities 声明、入口 `module:attr`）完全没验证过。

**接**（基础设施层，commit `133b552`）：
1. SDK 扩展：[ToolSpec](sdk/python/simchat_mod/__init__.py#L80-L115) 类 + [ModApi.register_tool()](sdk/python/simchat_mod/__init__.py#L148-L156) 方法（`backend` 为跨进程 `"module:attr"` 字符串引用）；[BaseSkill](sdk/python/simchat_mod/skill_base.py) 迁入 SDK 供 skill MOD import。
2. sandbox_runner 扩展：`_LocalModApi.register_tool()` 存 `_backend_module/_backend_attr`；register 消息带 `tools[]`；新增 `invoke_tool` stdin 命令处理 `_handle_invoke_tool`；所有 stdin 命令和回传响应都支持 `request_id` 匹配；输出时 `_sanitize()` 把 type 对象（如 `str`）转成字符串。
3. sandbox 宿主侧重写：从"只跑 register 的一次性启动"改为 queue 响应队列长驻线程；新增 [invoke_mode()](loader/sandbox.py#L93-L121) 和 [invoke_tool()](loader/sandbox.py#L124-L151) 两个同步接口，UUID request_id 匹配响应。
4. lifecycle 扩展：`_tools` 字典存 `{tool_name: {"handle": ..., "mod_id": ..., "spec": {...}}}`；`handle.tools` 从 register 消息登记；新增 `list_tools()` / `has_tool()` / `call_tool(tool_name, params, timeout)`；新增 [全局单例 getter](loader/lifecycle.py#L310-L323) `set_global_loader()` / `get_loader()`。

**接**（skill MOD 包 + facade 层，commit `e03e310`）：
5. 5 个 skill MOD 在 `mods/` 下，各自 manifest.type=skill + hook=[agent.tool]：
   - [noic.skill-readfile](mods/noic.readFile/manifest.json)：`capabilities.fs.read=[workspace]`
   - [noic.skill-websearch](mods/noic.webSearch/manifest.json)：`capabilities.net.domains=[*]`
   - [noic.skill-screenshot-recognition](mods/noic.screenshotRecognition/manifest.json)：`capabilities.fs.read=[workspace]`
   - [noic.skill-areyoutrouble](mods/noic.areYouUnderTrouble/manifest.json)：无 capability（纯逻辑）
   - [noic.skill-realitycheck](mods/noic.realityCheck/manifest.json)：无 capability（纯逻辑）
6. [SkillManager facade](loader/skill_manager_facade.py)：旧 API 表面不变（`get_registry().get_skill("webSearch").execute(params)`），内部委托 `ModLoader.call_tool()` → `sandbox.invoke_tool()`。`init_*` 函数保留为占位（旧 rigard.py 仍调用，后续切片清理）。
7. 旧目录处理：`kirara/services/skills/` + `rigard/services/skills/` 的 5 个 skill `.py` 全部删除；`skills.py` 重写为 facade 重导出 shim（Galax/JRVS 零改动）；`realityCheck.py` 保留 JRVS 直接 import shim（旧 jrvs.py L2438）。

**验收（2026-10-27 冒烟测试，11/11 PASS）**：
1. 5 个 manifest 全部通过 `validate_manifest()`（ID kebab-case、type=skill、hook=agent.tool）。
2. 5 个 skill MOD 全部 `run_isolated()` 成功，register 消息带完整 `tools[]` 元数据（含 backend、triggers、input_schema 字符串化）。
3. `invoke_tool realityCheck` 正常文本 → `violation=False, score=0.0`；伤害文本 → `violation=True, score=1.0, 4 关键词命中`。
4. `invoke_tool areYouUnderTrouble` 危机文本 → `is_threat_detected=True`。
5. 不存在的 tool 名 → `ok=False, error="tool 未在本进程注册"`。
6. Python 语法检查：`simchat/` 所有模块 + 5 个 MOD Python 文件均通过 `py_compile`。
7. Git clean：2 commit 逐片可回放，working tree 干净。

**Phase 2 保留项**（不阻塞 Phase 3 启动，但属后续切片范围）：
1. **services 透传未做**：sandbox_runner 的 `_LocalModApi.services` 仍为空 dict——Galax 子进程里 `_api.service("skill_manager")` 返回 None，只能 fallback 到 LLM 模拟召回。需要 sandbox 宿主侧把 services 序列化传给 runner，或 Galax 直接 import skill MOD 做同进程调用。
2. **PIL.ImageGrab 实际未 invoke**：screenshotRecognition 只 sandbox 启动成功，没调 `invoke_tool` 测实际截图。PIL 在无显示的子进程里可能失败，需在有 GUI 的环境实测。
3. **`init_*` 函数仍被旧代码调用**：`skill_manager_facade.py` 里的 `init_readFile_skill()` / `init_screenshotRecognition_skill()` / `init_areYouUnderTrouble_skill()` 是空函数（旧 `rigard.py` L1436-L1441 仍在调用），后续切片可清理这些调用。
4. **lmbrew.py 未接入**：宿主启动后还没调 `set_global_loader()` 和 `mod_loader.discover()`，前端调 `/api/simchat/tools` 时会得到空列表。需要在 lmbrew.py 启动流程里接入（Phase 3 或后续宿主集成切片）。

---

## 三、Phase 2 剩余总验收

> 状态：P2.1 / P2.2 / P2.3 / P2.4 全部交付；以下 1/2/3/4 已可验证，5/6 持续回归。

1. `simchat/loader/` 下新增 resolver.py + sandbox.py；verify.py 扩展签名 + 吊销列表。**（已交付）**
2. 5 个 MOD 化 skill 在 `mods/` 下，各自有合法 manifest + capability 声明。**（已交付——commit `e03e310`，冒烟测试 5/5 manifest 通过 + 5/5 sandbox 启动成功）**
3. `loader.list_mods()` 返回 status=failed 时包含 resolver/verify/sandbox 任一阶段的失败原因（可区分"缺依赖" vs "签名无效" vs "超时"）。**（已交付——P2.1-P2.3 共 7 场景冒烟全过；P2.4 新增 11/11 冒烟测试全部 PASS）**
4. 宿主启动不 import BaseSkill（SkillManager 改走 loader）。**（已交付——commit `e03e310`：旧 `kirara/services/skills/` + `rigard/services/skills/` 共 10 个 skill `.py` 删除；`skills.py` 重写为 facade 重导出 shim；[skill_manager_facade.py](loader/skill_manager_facade.py) 薄封装 ModLoader.call_tool()）**
5. barry.galax / agent-config-minimal 功能不退化。**（持续验证中——P2.4 未触碰两者代码和 MOD 包；skill MOD 不影响 Galax chat.mode 注册）**
6. 空 `mods/` 裸壳下 SimChat 本体独立对话仍然可用（agent 无工具但能聊）。**（裸壳四件套当前状态：① provider + 对话 runtime ✅、② Agent 工具面板需 P2 保留项 #1 services 透传 + #4 lmbrew.py 接入后才能列出 skill、③ 朴素记忆 ✅、④ 示例 automation 属 Phase 5）**

---

## 四、不做的事（防范围爆炸）

- 不动 Phase 4 CLI（`simchat mod install/pack/publish`）。
- 不做完整能力隔离（WASM/seccomp/AppContainer）——sandbox Phase 1 只做"进程级"。
- 不做 agent-config/skill 的前端 UI 改造（除了 P3.8 已经完成的失败警告条）。
- 不写新的 skill（不新增 MOD，只迁移现有）。
- 不动 Rigard/Kirara Agent 链路（只读原 skill、不写新逻辑）。
- 不触发 §12 决策（签名方案已锁定 ed25519，本体闭源 / 付费 MOD / 商店都留 Phase 6）。

---

## 五、§12 决策无关性说明

Phase 2 剩余四项与 §12 五项决策**零耦合**：
- 本体闭源与否：不影响 resolver/verify/sandbox/skill MOD 的实现。
- Galax 为官方 MOD：只是给它补签名，不改变 loader 代码。
- Quasar 撤首发：不影响。
- Automation 只 DAG：Phase 2 剩余不碰 Automation（它是 Phase 5）。
- 付费 MOD 首发：Phase 2 剩余不碰商店。
