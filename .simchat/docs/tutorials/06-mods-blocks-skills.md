# 06 概念地图：MOD、方块与技能

> 本章属于「装配型」路径（B），前置：[04 Agent 模式入门](04-agent-mode.md)、[07 技能安装与启停](07-manage-skills.md)。

## 1. 你会得到什么

一张能自己回答下面这些问题的心智地图：

- 这个能力属于哪一层？是本体、方块、MOD，还是一张地图（AI 实例）？
- 它从哪个目录被加载？凭什么能被 Agent 调用？
- 我想加一个能力，该写 manifest 还是改本体？
- 为什么有的面板能点、有的写着「未接入」？

```text
地图层  AI 实例：人设 + 引擎预设 + 可用能力集合
  ↑
MOD 层  应用包（type=binary）：可注册聊天模式、带前端资源
  ↑
方块层  原子能力：本体内建（不可移除） + type=skill 的可插拔方块
  ↑
加载器  manifest 校验 → 依赖解析 → 签名 → 子进程注册
  ↑
引擎层  AgentLoop / providers / 会话 / 审批
```

## 2. 前置条件

- 已经跑过 04（Agent 时间线、审批）和 07（技能启停），否则下面的目录与状态码会缺少实感。
- 手边能打开 `.simchat/` 目录。

## 3. 跟着做

### 3.1 用三个文件验证「分层」

1. 打开 `.simchat/skills/noic.readFile/manifest.json`。看 `type` 与 `layer`：`"type": "skill"`、`"layer": "block"`——它是方块层。
2. 打开 `.simchat/skills/barry.galax/manifest.json`。`"type": "binary"`、`"layer": "mod"`，还多了 `signature` / `integrity`——它是 MOD 层，必须验签。
3. 打开 `.simchat/skills/automation.daily-digest/manifest.json` 与同目录 `flow.json`。`"type": "automation"`、`capabilities.schedule=true`、`automation.flow_file=flow.json`——它是工作流包，由调度器消费，不是工具。

同一个目录下三种包并排放，这就是「`skills/` 只是扫描根，不决定层级」的意思。

### 3.2 看一次加载结果

```bash
curl http://127.0.0.1:5000/api/console/skills
```

返回的每个条目至少有 `id / name / version / status / hooks / enabled / error`。注意这个接口给的是**扫描快照**（读 manifest + 读状态文件），不是加载结果，所以：

| 字段 | 含义 |
|---|---|
| `status: ok` | manifest 校验通过；不代表子进程一定启动成功 |
| `status: warn` | 能读，但有可继续的警告（如非 automation 包声明了 `schedule`） |
| `status: err` | manifest 必填缺失或字段非法，加载器会直接跳过（`error` 是原因） |
| `enabled` | 状态文件里的启停位；`false` 时加载器 `discover()` 跳过该包 |

要确认「真的加载成功」，看的是 Agent 工具清单里有没有它注册的工具，或服务端日志里的注册记录。

再打开 `.simchat/loader/manifest.py` 看 `_REQUIRED`：`id / type / name / version / abi / license` 六个必填；`skill`、`automation`、`binary` 还必须给 `entry` 和至少一个 `hooks`；`binary` 额外要 `signature` 与 `integrity`。

### 3.3 跟一次工具调用走完全程

在 Agent 模式里发一句「读一下工作目录下的 README.md」，然后在 IDE 的「事件流」里按顺序看：

1. `tool_call`：`file_read {"path": ".../README.md"}`；
2. `tool_result`：内容或错误；
3. `final`：模型的总结。

`file_read` 是本体内建方块，不经过 `skills/`，所以它永远可用（除非工作目录失效）。换成 `web_search` 再看一次：它同样是内建方块，但内部复用了 `skills/noic.webSearch` 的代码目录——这就是「内建能力」与「可插拔方块」的边界样例。

### 3.4 对照「我要做什么 → 改哪一层」

| 你的目标 | 正确层级 | 落点 |
|---|---|---|
| 加一个只读工具（查天气、算哈希） | 方块（skill MOD） | 新目录 + `manifest.json`（`type=skill`）+ `entry` 注册 `ToolSpec` |
| 加一个写操作工具 | 方块（skill MOD） | 同上，但 `risk="write"`，会自动进审批 |
| 加一整套带界面谈的新玩法 | MOD（binary） | `layer=mod`、`type=binary`、`hooks=["chat.mode"]`、`web/` 前端资源 |
| 定时/事件触发的多步流程 | automation 包 | `flow.json` + `capabilities.schedule=true` |
| 只改人设或模型参数 | 地图（AI 实例） | 实例编辑弹窗，不写代码 |
| 改服务商检测、审批闸门、会话存储 | 本体（不建议） | `.simchat/runtime/*`，属于引擎，不是扩展点 |

## 4. 为什么会这样

### 4.1 三层的职责边界

| 比喻 | 对应 | 职责 | 谁能改 |
|---|---|---|---|
| JVM | Ollama / OpenAI 兼容 / 其他推理后端 | 只负责「生成 token」 | 换服务商即可 |
| Mojang + Forge | 本体 + 加载器 | 提供方块、审批、会话、加载与沙箱 | 只有本体维护者 |
| 方块 | 内建能力 + `type=skill` 包 | 原子动作，Agent 可调用 | 内建不可移除；skill 可插拔 |
| Mod | `type=binary` 包 | 完整玩法：模式 + 前端 + 后端管线 | MOD 作者 |
| 地图 | AI 实例 | 一次运行的人设与参数快照 | 用户 |

### 4.2 加载流水线

```text
discover()            扫 mods/ 与 skills/，跳过 . 开头与 disabled
  → 校验 manifest     必填、字段白名单、type/layer 组合、capabilities 形状
  → 解析依赖          requires.simchat 版本区间、requires.python
  → 验签（binary）    ed25519 公钥 + revoked 列表 + integrity
  → run_isolated()    子进程执行 entry(api)，30 秒内必须回 register
  → 注册              tools / modes 进 registry
```

任何一步失败只会把该包标记为 `failed`，不影响其它包启动——这是「崩溃隔离」的含义。工具注册进的是每个进程内的注册表，所以**启停要重启**。

### 4.3 执行流水线

模型输出纯文本协议：

```text
/$TOOL:file_read PARAMS:{"path": "README.md"}
```

`AgentLoop` 解析 → `validate_tool_params()` 按 `params_schema` 校验 → 风险闸门（`read` 直接跑，`write` / `dangerous` 挂起等审批）→ 执行 → 结果回灌给模型进入下一轮。

内建方块直接在进程内执行；MOD 方块由 `ModToolBlock` 通过子进程 IPC 调用（stdin/stdout 各一行 JSON），默认 30 秒超时。所以 MOD 崩溃、卡死不会拖垮服务。

### 4.4 能力闸门真的在哪一层

`capabilities` 不是装饰：沙箱子进程启动时会按 manifest 打三组护栏——

- `shell=false`：替换 `subprocess.Popen` / `os.system` / `os.popen`，MOD 代码不能创建子进程（`os.spawn*` / `os.exec*` 与 `multiprocessing` 仍未覆盖）；
- `fs.read` / `fs.write`：把 `open` 与 `os.*` 的路径收敛到白名单根——包目录、`mods/<id>/data`、`uploads` 默认只读/可写，其余靠 manifest 的 `workspace` / `mod-data` / `package` / `uploads` / `temp` 等 scope 显式声明；
- `net.domains`：替换 `getaddrinfo` / `connect`，只放行声明的域名（支持 `*.example.com`）。

它们属于**进程内护栏**（monkey-patch），能挡住误用与顺手越权，但不等同于操作系统级隔离。`credentials`、`schedule` 目前更偏声明与可读性；`process` 是「以子进程运行」这件事本身。

> 注意：`spec/capabilities.md` 第 6 节「与现状的差距」写的是改造前的状态，护栏已经落地，但那份文档还没同步。

### 4.5 版本与 ABI

- 本体版本只有一个来源：`loader/version.py` 的 `HOST_VERSION = "2.3.0"`。加载器、Web、MOD 校验都取它。
- `abi` 当前是 `simchat-mod/2`，过渡期仍接受 `lmbrew-mod/1`（会给出迁移警告，下个大版本移除）。
- `requires.simchat` 用区间表达，例如 `daily-digest` 的 `>=2.1,<3`。ABI 不匹配直接拒绝；ABI 匹配但依赖的 hook 不存在，标记不兼容，不静默跳过。

### 4.6 已声明但还没接线的部分

- `barry.galax` 在加载器层注册了 `galax` 模式（`loader.list_modes()` 能看到），但 Web 前端目前**没有模式按钮、也没有调用入口**——`chat.mode` 的 UI 接线未完成。技能页里看到它「已加载」是准确的，只是它暂时不会出现在输入框。
- `automation.daily-digest` 的 `hooks` 写了 `agent.completed`，但运行时目前**没有派发这个事件**。它的实际触发来自 flow 自己的 cron（`0 9 * * 1-5`，工作日 09:00），以及 `automation_trigger` 手动触发。
- 审批策略（Manual/Auto/Off）仍是前端本地状态，第 04 章已说明。

## 5. 常见坑

- **把 `skills/` 当成「不是 MOD」**：`skills/` 只是扫描根，里面的包照样走同一套 manifest、ABI、签名、沙箱。区别在 `layer` 与 `type`，不在目录名。
- **以为声明了 capability 就自动获得权限**：声明是「上限」，运行时还要用户审批；反过来，没声明就一定被护栏拒绝（`fs`/`net`/`shell` 三条）。
- **直接改本体来加能力**：内建方块是引擎的一部分，改了会让后续升级冲突；能用 MOD 解决的都写 MOD。
- **看到 `type=skill` 就以为 Agent 一定能用**：还要看 `risk` 与模式。对话模式只放行只读；`skills` 工具也只放行只读动作。

## 6. 验收清单

- [ ] 能不看文档说出「方块 / MOD / 地图」各对应什么
- [ ] 能从 manifest 一眼判断一个包属于哪层、需不需要验签
- [ ] 能画出加载流水线的五个步骤（扫描 → manifest → 依赖 → 验签 → 子进程注册）
- [ ] 能说清 `read` / `write` / `dangerous` 在执行上的差别
- [ ] 能指出 `chat.mode` 与 `agent.completed` 目前未完整接线
- [ ] 知道本体版本只有一个来源

## 7. 延伸阅读

- [architecture-recap.md](../architecture-recap.md)：分层重构的完整推演
- [capabilities.md](../../spec/capabilities.md)：权限清单与作用域（第 6 节为历史状态）
- [hooks.md](../../spec/hooks.md)：扩展点全表
- [mod-manifest.schema.json](../../spec/mod-manifest.schema.json)：字段与条件必填
- [sandbox_runner.py](../../loader/sandbox_runner.py)：三组护栏的实现
- [08 写第一个 Skill MOD](08-first-skill.md)
