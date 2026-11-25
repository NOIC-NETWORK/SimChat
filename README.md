# SimChat

![logo](.simchat/web/static/sprites/logos/simChat-2.png)

> **SimChat 是支持深度定制的开源对话式人工智能智能体框架。**

不是又一个套着聊天框的模型客户端。在这里，模型、工具、人格、界面、桌面形态和自动化流程都是可替换的零件——而替换的方式只有一种：写一个 MOD。不用 fork 本体，不用改宿主源码，也不用等作者发版。

*Everything, Harnessed.* —— 把一切收进一个你能拆开的壳里。

## 30 秒自检：这个仓库是不是为你写的

如果你动过下面任何一个念头，SimChat 就是冲着你写的：

- 换过三四个 AI 客户端，最后都停在「这个按钮为什么不能改」；
- 想让 Agent 读本地文件、搜网页、看截图，但不想为它搭一套后端；
- 想让 AI 有自己的脸、自己的声音、自己的脾气，而不只是网页里的一段灰字；
- 认为扩展就该像 Minecraft MOD 那样装上去，而不是 clone 一份源码回来自己维护。

四条全中？先点右上角 ⭐，再用下面几条命令跑起来。这个项目还在「接口已经冻结、功能还在长」的阶段——早来的人，有机会影响这套 ABI 长成什么样。

## 几条命令，先跑起来

```bash
git clone https://github.com/NOIC-NETWORK/SimChat.git
cd SimChat
pip install -r .simchat/scripts/requirements-simchat.txt
python .simchat/scripts/entry.py web
```

前置只要 Python ≥ 3.9（Windows / macOS / Linux）。模型二选一：本机 Ollama，或任意 OpenAI 兼容服务，在设置页填 Base URL / Key / 模型名即可。

浏览器打开后是一个本地 IDE 式界面：左边文件树，中间编辑器，右边对话与 Agent 时间线。没选工作目录时输入框是锁死的——这不是 bug，因为「工作目录」在 SimChat 里是对话、文件、Agent 工具共用的同一个根。

## 「深度定制」到底能改什么

大多数客户端把「定制」做成了换主题色。SimChat 把平台拆成三层，每一层的接缝都留在明面上：

| 你想改的 | 改法 | 要动本体吗 |
|---|---|---|
| 人格、系统提示词、模型参数 | 写一个 `agent-config` 类 MOD | 不需要 |
| 新工具（读文件、搜索、控制设备） | 写一个 `skill` 类 MOD，`@hook` + `register_tool()` | 不需要 |
| 界面片段、主题、专属页面 | MOD 自带 `web/` 与 CSS | 不需要 |
| 接入第三方程序 | `binary` 类 MOD（ed25519 签名 + 完整性校验） | 不需要 |
| 定时任务、多步流程 | `automation` 类 MOD，声明 `flow.json` | 不需要 |
| 桌面形态 | 声明 `desktop.pet.entry`，宿主替你拉起桌宠进程 | 不需要 |

装进来的东西不是「受信任的插件」，而是「被隔离的子进程」：manifest 先过 schema，再查依赖版本，`binary` 包还要验签名，最后在沙箱进程里跑 `entry(api)`。任何一步失败，这个 MOD 标记为 failed，宿主照常运行。这是 fail-closed，不是 try/except 糊一层。

## 现在仓库里有什么

- **对话与 Agent**：流式 SSE、工具调用时间线、审批卡、中断、会话落盘与滑动窗口记忆。
- **模型**：Ollama 流式 + OpenAI 兼容 SSE，多服务商聚合、模型下拉分组。
- **现成能力**：文件读写、网页搜索、截图识别、Galax 证据加权检索管线、每日摘要自动化 DAG。
- **IM 接入**：OneBot v11（NapCat / Lagrange / nonebot2）与 QQ 官方机器人，两种通道独立配置。
- **桌面**：Windows 启动器 + 原生 Win32 分层窗口桌宠（逐像素透明、点击穿透、立绘换装），宿主退出时桌宠一起退出。
- **契约**：`spec/` 里 5 份冻结规范（manifest schema、权限模型、hooks、SSE 事件、ABI 变更规则），MOD 只依赖 `simchat_mod` 这一个稳定接口。
- **可核验**：每个阶段都有 commit 范围和冒烟记录（见 [updates.md](updates.md)），十几份设计与评估文档都在 `.simchat/docs/`。

人设、音色、JRVS 内核这些私有实现不在仓库里，正文末尾有完整清单——这份 README 不打算假装什么都开源了。

## 认同我？Star 我，然后下载

如果上面的任何一句话说中了你，这个仓库就是为你写的。点右上角那个 ⭐ **Star**——它花不了你一秒，但能让一个双非本科生的 Harness 多被一个人看到。然后跑起来，写你的第一个 MOD，把世界造出来。

## 吉祥物

SimChat 的吉祥物：Televi（电视君）。造型来自 UHF 时代的 CRT 电视，也是 TeleVideo Enterprise 的吉祥物，象征着媒介革命。

# 君子坦代码，小人藏资源

LMBrewer 出品的开源底层框架：宿主、加载器、SDK、契约都在这里，藏不住，也没打算藏。

## 巴里君GitHub号

[NOIC-NETWORK](https://github.com/NOIC-NETWORK)

## TeleVideo官方网站

[TeleVideo Enterprise](https://www.tvehub.com/ai)

## Ollama Hub

[Ollama](https://ollama.com/TeleVideo-AI)

## 巴里君国内唯一联系方式

[发送邮件](mailto:1066344121@qq.com)

# 新手教程

请看 [教程目录与大纲](.simchat/docs/tutorials/README.md)

# 开发花絮

请看[tidbit.md](tidbit.md)

## 更新日志

请查看 [updates.md](updates.md)：阶段进度、冒烟测试与历次改造结果都在那里。

## 目录

```
.simchat/
├── spec/                      # 平台契约（Phase 0 冻结）
│   ├── mod-manifest.schema.json   # 四类 MOD 统一 schema（JSON Schema 2020-12）
│   ├── capabilities.md            # 权限模型：谁能读什么、连什么、跑什么
│   ├── hooks.md                   # 本体暴露的扩展点（实现 ABI = simchat-mod/2）
│   ├── events.md                  # Agent SSE 事件契约（13 事件 + 挂起/终止语义）
│   └── abi-changelog.md           # ABI 版本变更与兼容规则
├── loader/                    # 加载器安全底座（Phase 1-2）
│   ├── manifest.py               # schema 校验 + 未知 hook fail-closed（192 行）
│   ├── lifecycle.py              # 扫描/加载/启停/失败隔离 + tool 注册表（266 行）
│   ├── registry.py               # chat.mode 注册表（32 行）
│   ├── resolver.py               # requires.python semver + requires.packages find_spec（90 行）
│   ├── verify.py                 # binary 两阶段 integrity + ed25519 + revoked（69 行）
│   ├── keys.py                   # ed25519 密钥对/签名/验签/吊销（123 行）
│   ├── sandbox.py                # 宿主侧：run_isolated + invoke_mode + invoke_tool + request_id（220 行）
│   ├── sandbox_runner.py         # 子进程侧：entry(api) + register(modes,tools) + invoke/invoke_tool（296 行）
│   ├── sandbox_contract.md       # IPC 协议（stdin JSON 命令/ stdout JSON 响应）
│   ├── skill_manager_facade.py   # 旧 SkillManager API 兼容层 → 委托 ModLoader.call_tool()（91 行）
│   └── public_keys/
│       ├── official.ed25519.pub  # 内置官方公钥
│       └── revoked.json          # 吊销列表
├── runtime/                   # 本体独立对话运行时（Phase 2 最小承压切片）
│   ├── core.py                   # SimChatCore.chat_stream 编排（92 行）
│   ├── providers.py              # Ollama 流式 + OpenAI 兼容 SSE（96 行）
│   ├── store.py                  # sessions 落盘 + 滑动窗口记忆（94 行）
│   ├── comms.py                  # 通讯通道注册表（Fernet 加密敏感字段）
│   ├── crypto.py                 # Fernet 加解密
│   ├── im_bots.py                # 群机器人运行时（OneBot v11 / QQ 官方 API）
│   └── safety/                   # 运行时内置安全能力（realityCheck / areYouUnderTrouble）
├── sdk/python/simchat_mod/    # MOD SDK（ABI：simchat-mod/2）
│   ├── __init__.py               # ModApi + ModeSpec + ToolSpec + @hook + register_tool()（177 行）
│   └── skill_base.py             # skill MOD 基类 BaseSkill（47 行）
├── fixtures/                  # Agent SSE 回归基线（Phase 0 冻结）
│   ├── agent-happy.json
│   ├── agent-approval-approve.json
│   ├── agent-approval-reject.json
│   ├── agent-aborted.json
│   ├── agent-max-turns.json
│   └── record_agent_sse.py
├── cli/                       # MOD CLI（init / pack / verify / publish / gen-key）
├── automation/                # Automation DAG 引擎（scheduler / executor / approval / quota / audit）
├── registry/                  # 静态 MOD 索引（index.json）
├── web/                       # Web UI（Flask：聊天 + 设置页）
├── harmony-webview/           # 鸿蒙 ArkUI WebView 壳
├── examples/                  # 示例 MOD（skill-hello / automation-daily-digest）
├── docs/                      # 设计文档
├── mods/                      # 一等方 MOD（1 个）
└── skills/                    # 原子能力（5 个）
```

## 架构

SimChat 把"平台"拆成三层，每一层只做一件事：

```
┌─────────────────────────────────────────────────────────┐
│ 本体宿主（lmbrew.py + 4 蓝图）                          │
│   注入 SDK + 调 ModLoader.discover() + 消费 list_mods() │
├─────────────────────────────────────────────────────────┤
│ 加载器层（loader/）                                      │
│   manifest → resolver → verify → sandbox.run_isolated   │
│   lifecycle 调 entry(api) → register(modes, tools)      │
│   后续 invoke_mode() / invoke_tool() → sandbox 子进程   │
├─────────────────────────────────────────────────────────┤
│ MOD / 技能包（mods|skills/<owner>.<id>/）                  │
│   manifest.json + python/**/*.py + web/**/*.js          │
│   只能 import simchat_mod.*，不得 import 宿主内部实现    │
└─────────────────────────────────────────────────────────┘
```

**安全边界**：Phase 2 剩余交付的 Loader 底座形成一条 fail-closed 流水线——manifest schema 先验 → resolver 查依赖 → verify 验签名（binary） → sandbox 子进程隔离（crash 不拖宿主）。任何一步失败 → MOD status=failed，宿主继续运行。

## 当前 MOD 与技能

### MOD（`mods/`，1 个）

| MOD | ID / 名称 | 类型 | hooks | 交付 |
|---|---|---|---|---|
| `mods/kirara/` | `kirara_agent_config` · Kirara行为包 | agent-config | — | 女仆人设 + 简约主题 CSS（原 `agent-config-minimal` 并入） |

> ID 只允许小写字母、数字与下划线；显示名称写在 `name`，可含任意符号。

### 原子能力 / 技能（`skills/`，5 个）

| 技能 | 类型 | hooks | 交付 |
|---|---|---|---|
| `barry_galax` | binary | `chat.mode` | Phase 1 — Rigard 的证据加权检索管线 |
| `automation_daily_digest` | automation | — | Phase 5 — 每日摘要 DAG 流示例 |
| `noic_skill_readfile` | skill | `agent.block` | Phase 2.4 — 原 Kirara/Rigard 硬编码 skill 迁出 |
| `noic_skill_websearch` | skill | `agent.block` | Phase 2.4 |
| `noic_skill_screenshotrecognition` | skill | `agent.block` | Phase 2.4 |

### 运行时内置安全（不在目录中）

| 方块 | 说明 |
|---|---|
| `realityCheck` | 输出侧现实审视，检测偏见/仇恨/暴力/心理伤害 |
| `areYouUnderTrouble` | 输入侧危机信号识别与应急建议 |

## 群机器人（IM 接入）

把群聊接进本体对话：外部消息 → `SimChatCore.chat_stream()` → 回复。入口在 **设置控制台 → 通讯 → 群机器人**，两种接入方式按钮分开。

| 接入方式 | 适合 | 收消息 | 发消息 | 连通性自检 |
|---|---|---|---|---|
| Python 库（OneBot v11） | NapCat / Lagrange / go-cqhttp / nonebot2 | 正向 WebSocket 或 HTTP 反向 Webhook | `send_group_msg` | `get_login_info` |
| QQ 官方 API | QQ 开放平台机器人 | Gateway WebSocket 或 Webhook（Ed25519 验签） | `/v2/groups/{openid}/messages`、`/v2/users/{openid}/messages` | `/users/@me` |

使用：填参数 → 保存 → 启动。Webhook 模式面板会显示可复制的回调地址 `/api/console/comms/<channel>/webhook`。

- 两个 QQ 通道互斥，同一时间只运行一个；按消息 ID 去重、每会话串行，上下文以 `im-<mode>-<会话>` 隔离。
- 每个通道可独立指定模型服务商 / 模型名，以及群聊系统提示词；自动回复、白名单、触发规则实时读取，保存即生效。
- QQ 官方 API 默认只能被动回复：先让机器人在群里被 @ 一次，面板「最近活跃群」出现后即可测试发送。
- 敏感字段（AccessToken / AppSecret）Fernet 加密，前端只回显 `********`，留空表示保持不变。

## ABI

唯一稳定接口是 SDK（`simchat/sdk/python/simchat_mod/`）。MOD 代码只能 import 这里暴露的符号：

```python
from simchat_mod import ModApi, ModeSpec, ToolSpec, BaseSkill, hook
```

`manifest.json` 的 `abi: "simchat-mod/2"` 是当前实现版本——未来破坏性变更升级主版本，非破坏性升次版本；`spec/mod-manifest.schema.json` 已与该版本对齐（`lmbrew-mod/1` 仅作过渡期兼容）。

## 本目录不包含（故意的）

- 任何私有实现（JRVS / Hippo / 人设 / 音色；Galax 检索管线已开源为 `skills/barry.galax/`）
- 任何密钥、授权素材、用户数据
- 商店前端（Phase 6 范围）
- `__pycache__/`（已 gitignored）
