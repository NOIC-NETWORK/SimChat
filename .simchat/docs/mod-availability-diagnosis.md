# MOD 可用性诊断报告

- 诊断日期：2026-11-14
- 最后校验：2026-11-15
- 当前状态：P0 宿主接线、`skills/` 分层、安全能力固化、`barry.galax` 签名、P1 资产/服务语义与 P2（并发 future、fs/net 闸门、schema 同步）均已落地；§1–§4 保留为修复前快照，最新进度见 §7–§11。
- 范围：`.simchat/loader`、`.simchat/runtime/mods_index.py`、`.simchat/runtime/agent/tools.py`、`.simchat/web`、`spec/mod-manifest.schema.json`
- 方法：静态走查 + 真实加载器探针（不修改仓库、不执行未知 MOD）
- 原结论（修复前）：**MOD "能列出、能手动加载，但产品内不会执行"**。宿主从未实例化 `ModLoader`，UI 只做只读 manifest 扫描；即使手动加载，第三方 MOD 的自带资产/脚本也只有一部分可用。

---

## 1. 运行时可用性（修复前快照）

> 1.1–1.3 已于 P0 修复（见 §7）；1.4 的签名问题已于 §9 修复，`service("inference")` 仍待办。

### 1.1 宿主没有启动加载器

- `set_global_loader()` 定义在 `loader/lifecycle.py`，全仓库没有调用方。
- 全仓库没有任何 `ModLoader(...)` 实例化。
- `/api/console/mods` 走的是 `runtime/mods_index.py` 的只读扫描，该模块明确声明不 import entry、不创建沙箱、不执行 MOD 代码。
- `mods_index.set_enabled()` 只写 `.simchat_state.json`，不会加载/卸载任何代码。

结果：产品运行期间 MOD 代码执行次数为 0。

### 1.2 `/mods/<id>/<path>` 静态资源路由不可用

`web/__init__.py` 中：

```python
from loader.lifecycle import get_global_loader
```

- 裸包名 `loader` 在新入口（`.simchat` 注册为 `simchat`）下不可导入，实测 `ModuleNotFoundError`。
- `loader.lifecycle` 实际提供的 getter 叫 `get_loader`，不存在 `get_global_loader`。
- 路由还要求 `status == loaded`，而 1.1 导致永远不满足。

### 1.3 工具/模式没有进入 Agent 运行时

- Agent 只查 `runtime/agent/tools.py` 的 `BLOCK_REGISTRY`，其中有 8 个内建方块。
- `ModLoader.list_tools()` 的结果从未合并进 `BLOCK_REGISTRY`。
- `/api/agent/tools` 因此看不到任何 `noic.skill-*` 工具。
- `ModLoader.call_tool()` / `invoke_mode()` 没有 HTTP 入口。
- `AutomationEngine.bind_loader()` 无调用方，`skill:<name>` 步骤必然报"ModLoader 未绑定"。

### 1.4 `barry.galax` 开箱失败

- 包完整性 `integrity` 与当前文件一致，但签名是在旧 payload 上生成的，`verify_package` 报"签名无效（无可用公钥能验证）"。
- 即使重签，`pipeline.py` 的 `query()` 调用 `_api.service("inference")`，runner 侧 `_LocalModApi` 没有 `service` 方法，且 `services={}`，调用必崩。

---

## 2. 自带资产 / 脚本的适配性（重点）

用一个合成用户 MOD 实测（`manifest` 不写 `layer`，包含 `assets/`、`scripts/`、`python/`、`web/`）：

| 场景 | 结果 | 原因 |
| --- | --- | --- |
| `assets/**` 通过 `api.package_dir` 读取 | 可用 | 子进程拿到绝对路径 |
| `assets/**` 用相对路径读取 | 失败 | 子进程 cwd 继承宿主 `E:\simchat`，未切到包目录 |
| `python/**/*.py` | 可导入 | 仅该目录被注入 `sys.path` |
| `scripts/**/*.py` | 失败 | 不在 `sys.path`，`ModuleNotFoundError` |
| `api.data_dir` | 仅 `layer=mod` 有 | `skill`/`automation` 默认 `block`，`data_dir=None` |
| `manifest.assets` 的 `root/icon/cover` | 完全不可用 | 加载器、索引、UI、静态路由均无消费者 |
| `frontend_entry` | 不可用 | SDK 有字段，Web 端从未读取 |
| `ui.slot` / `web.blueprint` hook | 静默空转 | hook 白名单接受，但无消费方 |
| `capabilities` | 部分生效 | `shell=false` 已覆盖 `Popen` / `os.system` / `os.popen` / `os.spawn*` / `os.exec*` / `multiprocessing` 启动；`pty`、`asyncio` 子进程、`ctypes` 等仍可绕过；fs/net 为进程内闸门 |
| MOD 在 entry 阶段 `print()` | 加载失败 | 协议走 stdout，print 会顶掉 register 首行，宿主报"沙箱输出格式非法" |
| 并发 `invoke_tool` | 有串包风险 | 所有调用共用响应队列，无锁、无 per-request future |

补充：

- `binary` 类型会对整包（含 assets/scripts）计算 integrity；用户改一张图就需重新签名，实际不可维护。
- 用户 MOD 现实上只能用 `skill`，而 `skill` 恰好没有 `data_dir`。

---

## 3. "MOD 列表"语义问题（已由 §8 分层重构解决）

> 本节描述的是重构前的混合状态；现在 `mods/` 与 `skills/` 已分开，接口也已拆分。

用户澄清：`index.html` 的"mod 列表"里当前那些条目是**原子能力**，不是 MOD，属于**方块**。

代码事实：

- `mods/` 下 8 个包中 6 个 `layer=block`：5 个 `noic.skill-*` + `automation.daily-digest`。
- 只有 `barry.galax`、`agent-config-minimal` 是 `layer=mod`。
- `index.html` 标题为"MOD 管理"，过滤维度只有 `type`。
- `chat.js` 把扫描结果统一按 MOD 卡片渲染。
- `ide.js` 侧栏分区直接写"MOD"。
- `runtime/mods_index.py` 的扫描结果不返回 `layer` 字段。

同时，真正的方块注册表 `runtime/agent/tools.py: BLOCK_REGISTRY` 与 `mods/` 里的 block 包是两套体系，后者从未注册进去；内建 `WebSearchTool` 与 `noic.skill-websearch` 还存在功能重复。

建议：扫描结果补 `layer`；UI 分「方块（原子能力）/ MOD」；`skill` 显示为"方块·原子能力"。此项列为 P1 语义修正。

---

## 4. 契约漂移

- `spec/mod-manifest.schema.json` 仍写 `abi: lmbrew-mod/1`，hook 枚举缺少 `agent.block`、`web.blueprint`、`ui.slot`；现有 manifest 全部是 `simchat-mod/2` + `agent.block`，用这份 schema 校验会全部失败。实际门禁是手写的 `loader/manifest.py`。
- schema 的 automation 要求 `flow`，实际 manifest 用 `flow_file`，`mods_index` 也只认 `flow_file`。
- `_LocalModApi` 缺 `service` / `has_capability` / `capabilities` / `emit_event`，与 SDK `ModApi` 不同构。
- runner 的 `register_mode` 丢掉 `description`、`requires_capabilities`；用 dict 注册 tool 时不走 SDK 默认值，`risk` / `usage` 会变成 `null`。
- UI 把 `status=ok` 显示为"可加载"，但它只代表 manifest 合法；`barry.galax` 当时就是 `ok` 但实际 failed（签名已于 §9 修复）。

---

## 5. 修复优先级

### P0（本次执行）

1. **宿主接线**：`create_app()` 启动 `ModLoader`，`set_global_loader()`，并把已加载 MOD 的工具同步进 `BLOCK_REGISTRY`。
2. **修 `/mods` 路由**：改为包内导入 `get_loader`，修正路径越界判断。
3. **协议卫生**：runner 协议加私有 IPC 前缀，宿主只消费带前缀的行；MOD 的 `print` 输出转入宿主流并写入 stderr，不再污染协议。

### P1（已完成，见 §10）

- 资产语义：`assets.root` 可访问、`cwd` 切到包目录、`scripts/` 注入 `sys.path`。
- 所有 layer 分配 `data_dir`。
- ABI 对齐：runner 复用 SDK `ModApi`；补齐 `service`（`barry.galax` 重签已完成，见 §9）。
- 语义修正：扫描结果已补 `layer`，`mods/` 与 `skills/` 接口已分开（见 §8）；UI 文案仍可继续统一为「方块 / MOD」。

### P2（已完成，见 §11）

- `invoke` 并发加锁 / per-request future。
- `capabilities.fs/net` 执行层。
- schema 与实现同步。

---

## 6. 探针记录

- 手动 `discover()`：8 个包，7 个 loaded，1 个 failed（`barry.galax` 签名）。
- `realityCheck`、`areYouUnderTrouble`、`webSearch` 在沙箱内实际调用成功，说明 invoke 链路本身可用，缺的是宿主接线。
- 合成用户 MOD：可注册并调用工具；复现相对路径资产失败、`scripts/` 导入失败、`data_dir=None`、`_LocalModApi` 缺少 SDK 方法。

---

## 7. P0 落地记录

已完成：

1. **宿主接线**
   - `web/__init__.py`：`create_app()` 中调用 `_ensure_mod_loader()`，进程级单例启动 `ModLoader`，执行 `discover()` + `set_global_loader()`。
   - `runtime/agent/tools.py`：新增 `ModToolBlock` 与 `sync_loader_blocks()`，把已加载 MOD 的工具包装成方块注册进 `BLOCK_REGISTRY`。
   - loader 随进程退出通过 `atexit` 统一 `cleanup()`。
2. **`/mods` 路由修复**
   - 改为包内导入 `simchat.loader.lifecycle.get_loader`（原来导入的 `get_global_loader` 根本不存在）。
   - 优先使用 `app.extensions["simchat_mod_loader"]`，路径校验改为 `realpath + commonpath`。
3. **协议卫生**
   - `sandbox_runner.py`：所有协议输出改走 `_ipc()`，行首加 `@@simchat-ipc@@`。
   - `sandbox.py`：只把带前缀的行放进响应队列；MOD 自己的 `print` 输出转到宿主 stderr，不再顶掉 `register`。

验证结果（`py -3` 实跑，**修复前口径**，当前数据见 §8.3/§9）：

- `create_app()` 成功拉起加载器：7 loaded，1 failed（`barry.galax` 签名，属 P1）。
- `BLOCK_REGISTRY`：8 个内建 + 5 个 MOD 工具，`realityCheck` 经注册表调用返回正常结果。
- `/api/console/mods` 200；`/api/agent/tools` 200 且包含 MOD 工具。
- `/mods/demo/hello.js` 200；`/mods/demo/../manifest.json` 403；未加载 MOD 的资源 404。
- 构造 entry 阶段 `print()` 的噪声 MOD：状态 loaded，工具调用成功，噪声输出写入宿主 stderr。

仍未解决（P1）：`barry.galax` 验签与 `service("inference")`、`assets.root` 可访问性、`scripts/` 导入、`data_dir` 分配、UI 的「方块 / MOD」分层。

---

## 8. 分层重构（2026-11-14 追加）

按产品语义把三类东西彻底分开：

### 8.1 `skills/` 与 `mods/` 分离

- 新增 `.simchat/skills/`，迁入：
  - `noic.readFile`
  - `noic.webSearch`
  - `noic.screenshotRecognition`
  - `barry.galax`
  - `automation.daily-digest`
- `.simchat/mods/` 现在只保留真正的 MOD：`agent-config-minimal`（以及运行时的 `uploads/`）。
- `ModLoader` 新增 `extra_dirs`，同一加载器扫描 `mods/` + `skills/`；接口 `/api/console/mods` 只返回 `mods/`，`/api/console/skills` 只返回 `skills/`，两者不再混在一起。
- 新增 `/api/console/skills/<id>/toggle`，技能启停写入 `skills/.simchat_state.json`，与 MOD 状态文件互不影响。
- `readFile` / `screenshotRecognition` 的上传目录从随包相对路径改为固定的 `.simchat/uploads`，避免迁移后指向 `skills/uploads`。

### 8.2 安全能力固化进运行时

- `realityCheck`、`areYouUnderTrouble` 的检测逻辑迁入 `runtime/safety/`，不再作为可安装、可停用的 skill MOD。
- 原 `mods/noic.realityCheck`、`mods/noic.areYouUnderTrouble` 包已删除；`registry/index.json` 中对应条目一并移除。
- `runtime/agent/tools.py` 新增原生方块 `RealityCheckTool`、`AreYouUnderTroubleTool`，与内建文件/Shell 工具同级注册，不经过 MOD 验签、沙箱和开关。
- 工具名保持 `realityCheck` / `areYouUnderTrouble`，调用参数不变。

### 8.3 验证结果

- `/api/console/mods`：仅 `agent-config-minimal`。
- `/api/console/skills`：5 个技能包，支持独立启停。
- `/api/console/automation`：仍能看到 `automation.daily-digest`（来自 skills）。
- `/api/agent/tools`：包含 10 个内建方块（含 `realityCheck`、`areYouUnderTrouble`）+ 3 个技能工具（`readFile`、`webSearch`、`screenshotRecognition`）。
- 直接调用内建 `realityCheck`（含"废物"）命中 `mental_harm`；`areYouUnderTrouble`（"我不想活了"）返回 `critical`。
- `barry.galax` 当时仍因签名问题 failed；已于 §9 修复。

---

## 9. `barry.galax` 签名修复（2026-11-15）

问题：包内 `integrity` 与当前文件一致，但 `signature` 是在旧 manifest 上签的，`verify_signature` 遍历 `public_keys/` 无匹配公钥 → `签名无效（无可用公钥能验证）`。

修复：

- 用 `dev-keys/official.ed25519.pem` 对当前 `build_signing_payload(manifest, integrity)` 重新签名。
- 仅替换 `manifest.json` 的 `signature` 字段，`integrity` 不变（文件内容未改）。
- 新签名自检通过，匹配 key_id `dCRIrbslvDehcFtFuTnWV9DyhR1yUHs6xDYDBIYKn5c`。

验证：

- `verify_package()` → `(True, '')`。
- `create_app()` 后 `barry.galax` 状态 `loaded`，`modes=['galax']`。

仍未解决：`galax` 模式调用 `api.service("inference")`，而 runner 侧没有 `service` 方法、`services={}`；模式可注册但推理会失败（P1）。

### 9.1 当前复核（2026-11-15）

- 加载：**6/6 loaded**（`mods/` 1 + `skills/` 5）。
- loader 工具：3 个 —— `readFile`、`webSearch`、`screenshotRecognition`。
- `BLOCK_REGISTRY`：13 个 —— 10 个内建 + 3 个技能工具；`realityCheck`、`areYouUnderTrouble` 均为内建。
- `/api/console/mods`：total 1，enabled 1。
- `/api/console/skills`：total 5，enabled 5。
- `/api/console/automation`：`automation.daily-digest`。
- `barry.galax`：`loaded`，`modes=['galax']`。

---

## 10. P1 落地记录（2026-11-15）

### 10.1 资产语义

- runner 在 `entry(api)` 前 `chdir` 到包目录，包内相对路径（`assets/...`）可直接读取。
- `python/` 与 `scripts/` 同时注入 `sys.path`，`scripts/*.py` 可正常 import。
- `manifest.assets.root` 解析为绝对路径，经 `api.assets_dir` 暴露；缺省回落到包目录。
- 宿主 `/mods/<id>/<path>` 路由不变，同一路径可同时服务前端资源。

### 10.2 data_dir

- 所有 layer 都分配独立目录：`data/mods/<id>`（layer=mod）、`data/blocks/<id>`（layer=block）。
- `list_mods()` 现在返回 `layer` 与 `data_dir`，索引/控制台可直接消费。

### 10.3 ABI 对齐与宿主服务

- runner 删除 `_LocalModApi`，直接复用 SDK `ModApi`（`capabilities` / `has_capability` / `service` / `emit_event` 同构）。
- 新增跨进程服务 RPC：runner 的 `service_call` 由宿主 stdout 线程执行并回写 `service_result`。
- 对象返回值（如 `skill_manager.get_registry()`）以 `@ref:` 引用回传，runner 自动包装成代理，支持链式调用。
- 宿主注入服务：`inference`（`generate_raw` → 当前服务商流式收齐）、`skill_manager`（委托 `ModLoader.call_tool`）。
- stdin 写入统一加锁，避免 invoke 与 service 响应并发写坏协议。

### 10.4 验证

- 合成 MOD：cwd=包目录、相对资产可读、`assets_dir` 可读、`scripts` 可导入、`data_dir` 存在、service RPC 正常、未声明 service 返回 `None`，7/7 PASS。
- `barry.galax` 实调用 `invoke_mode('galax')`：`ok=True`，四阶段输出完整；召回阶段使用 webSearch 实时结果（`grounded=True`），推理经 `inference` 服务返回真实结论。
- 全量加载：6/6 loaded；`BLOCK_REGISTRY` 13 个；控制台接口 200。

### 10.5 仍待办（P2，已完成，见 §11）

- `invoke` 并发锁 / per-request future（当前串行）。
- `capabilities.fs/net` 执行层。
- `spec/mod-manifest.schema.json` 与实现同步（`simchat-mod/2`、`agent.block`、`flow_file`）。

---

## 11. P2 落地记录（2026-11-15）

### 11.1 invoke 并发（per-request future）

- `handle` 新增 `_waiters`（request_id → 独立队列）。register 完成后切换到 future 路由：stdout 读线程只按 `request_id` 投递，不再让所有调用方共享一个响应队列。
- 无 `request_id` 的响应按 `type + mode_id / tool_name` 兜底匹配；匹配不到才丢弃并打日志（`pong` 静默忽略）。
- 超时/进程退出会注销或唤醒对应 future，不会让调用方空等 60s。
- `service_call` 改为独立线程执行：推理这类慢服务不再阻塞 stdout 读取，但回写仍走 stdin 锁。
- runner 仍是单线程执行，同一 handle 的并发请求在子进程内串行；宿主侧不再串包。6 线程并发调用实测各自拿到自己的输出，总耗时 ≈ 串行耗时。

### 11.2 capabilities.fs / net 执行层

- 闸门在 MOD 代码 import 之前安装（`sandbox_runner._install_fs_guard` / `_install_net_guard`）。
- fs 基础可访问范围（无需声明）：包目录（读）、`data_dir`（读写）、`.simchat/uploads`（读写）、解释器 / site-packages / SDK（只读）。
- `capabilities.fs.read/write` 的 scope 解析：`workspace`（用户工作目录）、`mod-data`、`package`、`uploads`、`temp`、绝对路径、相对子路径（相对 workspace）。临时目录不再默认授予。
- 覆盖的 API：`builtins.open` / `io.open`、`os.open`（按 flags 判定读写）、`os.remove/unlink/rmdir/mkdir/makedirs`、`os.rename/replace`、`os.listdir/scandir`；越权抛 `PermissionError: MOD 未声明 capabilities.fs.*`。
- 补丁函数用非描述符包装：`pathlib._NormalAccessor.open = os.open` 会把普通函数绑定成方法，导致 `screenshotRecognition`（经 `ollama` → `pydantic` → `importlib.metadata` → `pathlib`）加载失败；包装后已恢复。
- net：未声明 `capabilities.net` 时所有 `getaddrinfo` 拒绝（`host=None` 的 bind 除外）；域名白名单支持精确匹配、`*.example.com` 前缀通配和 `*`；`connect/connect_ex` 只放行解析结果中出现过或白名单里的 IP。
- 边界：Python 层权限边界，拦的是"未声明权限"的正常代码路径，不是 OS 级沙箱；`_io.FileIO` 等 C 级调用不在覆盖范围（仍不做 seccomp / 容器）。

### 11.3 schema 与实现同步

- `abi` 改为 `enum: [simchat-mod/2, lmbrew-mod/1]`。
- 新增 `layer`（`block` / `mod`），与 `manifest.py` 的缺省推断一致。
- `hooks` 补 `agent.block`、`agent.completed`、`web.blueprint`，保留旧别名 `agent.tool`。
- `entry` 允许 automation 写包内 `*.json`。
- `requires` 补 `simchat`，`lmbrew` 保留为旧名。
- `automation` 必填改为 `flow_file`；`flow` / `trigger` / `policy` 标注为旧字段（已迁入 flow.json）。
- `capabilities.fs` 描述与实现的实际 scope 对齐。
- 8 个真实 manifest（`mods/`、`skills/`、`examples/`）全部通过 Draft 2020-12 校验。

### 11.4 验证

- 合成 MOD 25/25 PASS：schema 自检与 8 个 manifest 校验、6 并发无串包、未声明 fs 读写/list 全拒绝、包目录与 `data_dir`/uploads 放行、stdlib 只读放行、声明式 fs 放行、未声明 net 拒绝、声明 net 放行、未声明域名拒绝。
- 真实包 6/6 loaded：`readFile` 读 uploads 成功、越界读取被拒；`webSearch` 经 `*` 白名单外连成功；`screenshotRecognition` 恢复可用。
- `/api/console/mods`、`/api/console/skills`、`/api/agent/tools` 均 200，工具列表含 `readFile` / `webSearch` / `screenshotRecognition`。



