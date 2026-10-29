# SimChat — LMBrewer 开源底层框架

# Everything, Harnessed.

![logo](/web/static/sprites/logos/simChat-2.png)

SimChat的吉祥物：Televi（电视君）。Televi的造型来自UHF时代的CRT电视，也是TeleVideo Enterprise的吉祥物，象征着媒介革命。

# 君子坦代码，小人藏资源

## 巴里君GitHub号

[NOIC-NETWORK](https://github.com/NOIC-NETWORK)

## TeleVideo官方网站

[TeleVideo Enterprise](https://www.tvehub.com/ai)

## Ollama Hub

[Ollama](https://ollama.com/TeleVideo-AI)

## 巴里君国内唯一联系方式

[发送邮件](mailto:1066344121@qq.com)

# 为什么我们选择开源

如果你是第一次点进这个仓库，只需要记住一句话：**模型会越来越便宜、越来越同质化，真正值钱的是驾驭它的那一层。** 这一层，我们叫 Harness。SimChat 不是一个聊天框，而是一套开源的 Harness——让任何模型真正干活的底座。

## Model + Agent = Harness

这是 SimChat 的第一性原理。

一个裸模型只会"接话"。给它工具（Agent）、记忆（会话）、权限（谁能做什么）、扩展（MOD），它才开始像一个系统。DeepSeek Harness 只是二创，LangChain 才是这个思路的原版；Claude Code 也表达过类似的意思（他们用的是 ReAct 算法），只是没有把公式写出来。

我们把这个公式写出来了，并且把它做成了你能摸到的代码：

- **Model**：任意模型——本地 Ollama，或任何 OpenAI 兼容 API。模型是可替换的引擎，不是护城河。
- **Agent**：工具调用、自我编排、人格约束——它们不是 prompt 技巧，而是有 ABI 契约（`lmbrew-mod/1`）的 MOD。
- **Harness**：承载以上一切的宿主——加载器、沙箱、权限模型、事件契约。这是 SimChat 的本体，也是这个仓库开源的东西。

模型每三个月洗牌一次，Harness 不会。所以我们开源的是 Harness。

## 《我的世界》带来的启示：MOD 的重要性

给你规则和方块，你给我世界。

Minecraft 长盛不衰，不是因为 Mojang 更新勤快，而是因为它把"造世界"的权力交给了 MOD 社区。SimChat 照搬了这条哲学：**本体只做规则，玩法全部由 MOD 定义。**

四类 MOD，对应通用智能的四块积木：

| MOD 类型 | 它是什么 | 类比 |
|---|---|---|
| `skill` | 工具调用：读文件、搜网页、截图识别 | 感知与行动 |
| `automation` | 自我编排：DAG 工作流、定时任务 | 自主规划 |
| `agent-config` | 人格与对齐：人设、主题、行为约束 | 性格 |
| `binary` | 专有内核：检索管线、推理/记忆/安全模块 | 器官 |

本体只暴露 10 个扩展点（hook），schema 冻结——就像 Minecraft 的方块规则：规则越稳定，世界越能野蛮生长。`mods/` 目录下已经躺着 8 个一等方 MOD 当样板，`simchat mod init` 一分钟就能起一个你自己的。

## Ubisoft 教会了我们什么：引擎代码复用

比如《看门狗》《Far Cry 5》里的驾驶引导系统，很明显是同一个控件。Ubisoft 被嘲笑是"罐头厂"，但没人能否认它的产能：**引擎复用，内容年货化。**

AI 应用行业现在是反过来的——每个团队都在重造自己的 Agent 框架、自己的工具注册表、自己的沙箱。我们放弃了重复造轮子：SimChat 把 Harness 做成稳定引擎，让 AI 应用变成年货——在同一套底座上快速换皮、快速迭代、快速返利。

## 深度接入 GitHub 生态

请给网络平权投票！

MOD 的分发不走应用商店，走 Git：`simchat mod publish` 发布的是静态索引（`registry/index.json`），任何人都能搭自己的仓库。没有审核费，没有抽成，没有人能下架你。你的 MOD 值得一个 star，而不是一份入驻协议。

## 生成式人工智能产业是个泡沫

达里欧·阿莫迪和埃隆·马斯克都说过类似的话。

泡沫的意思不是"AI 没用"，而是"押注某个模型会赢"没用。所以我们要自主研发底层逻辑：不绑死任何模型，不依赖任何厂商的良心，把会话、工具、权限、扩展这些真正长寿的层，攥在自己（和社区）手里。

（注：其实我想说的是，你们这群调API的、搞提示词工程的人，整天就梦想着月入上万，这才是目前的创业环境最大的幻觉。）

## 我只是个卑微的双非本科生

每天顶着所谓的"卓越工程师班"的剥削，在开发之余还被骂"不务正业"。

我们确实生活在阴沟里，我们确实在仰望星空。但是那星空是社交媒体制造的幻觉（"人均 985"，巴拉巴拉的）。我这个人很聪明，就是不会考试，所以我在国内占不到任何便宜。

所以我打算打破这个玻璃天花板。这个项目希望能带我去硅谷。

## 认同我？Star 我，然后下载

如果上面的任何一句话说中了你，这个仓库就是为你写的：

```bash
git clone https://github.com/NOIC-NETWORK/SimChat.git
cd SimChat
python -m web   # 打开浏览器，接入你的第一个模型
```

点右上角那个 ⭐ **Star**——它花不了你一秒，但能让一个双非本科生的 Harness 多被一个人看到。然后跑起来，写你的第一个 MOD，把世界造出来。

## 最近更新

**2026-10-29** — Web UI 多 provider 聚合 + 下拉交互修复 + OpenAI 预检强化

- **模型下拉聚合所有 provider**：composer 里的模型选择器不再只显示 resolved 那一个 provider 的模型，而是用 `<optgroup>` 按 provider 分组列出所有已发现的模型（Ollama 本地 + OpenAI 兼容 + 未来其他）。切换模型时 provider 跟着走，请求 payload 同时带 `provider` 和 `model`。
- **下拉菜单 hover 白字修复**：原生 `<select>` 在 Windows 上 `background: transparent` 会导致弹出面板的 option hover 时白底白字。加了全局 `select option` 明确兜底 `background-color` + `color`，深色模式独立适配。
- **模型提供商存档固化**：新增 `providerStore` 模块（`window.SimChatProviderStore`），把后端返回的 providers + models 缓存到 `localStorage`（10 分钟过期）。刷新页面后模型下拉立即有数据，不用等后端重新 discover；后端不可用时继续用缓存兜底。
- **OpenAI 预检 404 误判修复**：之前 `_openai_probe` 把 404/405 一律当作"端点只是不支持 /models 预检"，导致用户把 OSS 桶地址（`*.aliyuncs.com`）、CDN、甚至随机网页 URL 配成 API Base 时被误判为 available=True，实际调用才爆 404。现在加了 `Content-Type` 校验——只有 JSON 响应才保守判 OK，非 JSON 明确报错并提示检查 API Base。
- 文件：`runtime/provider_config.py`、`web/static/css/chat.css`、`web/static/js/chat.js`、`web/templates/index.html`

> 状态：**Phase 0-5 全部交付**（2026-10-28）。
> 定位：SimChat 是 **LMBrewer 的开源底层框架**——它本身具备接入 LLM API 进行对话的完整能力（`runtime/providers.py` + `core.py` + `store.py`），同时提供 MOD SDK + 加载器 + 清单规范 + 沙箱运行时，让社区和团队以模块方式扩展认知能力。
> 愿景：四类 MOD 对应通用智能的四个积木——`skill`=工具调用（感知与行动）、`automation`=自我编排（自主规划）、`agent-config`=人格与对齐（行为约束）、`binary`=专有内核（推理/记忆/安全）。SimChat 是模块化 AGI 的开源基座。

## 目录

```
simchat/
├── spec/                      # 平台契约（Phase 0 冻结）
│   ├── mod-manifest.schema.json   # 四类 MOD 统一 schema（JSON Schema 2020-12）
│   ├── capabilities.md            # 权限模型：谁能读什么、连什么、跑什么
│   ├── hooks.md                   # 本体暴露的 10 个扩展点（ABI = lmbrew-mod/1）
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
│   └── store.py                  # sessions 落盘 + 滑动窗口记忆（94 行）
├── sdk/python/simchat_mod/    # MOD SDK（ABI：lmbrew-mod/1）
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
└── mods/                      # 一等方 MOD（8 个，4 类全覆盖）
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
│ MOD 包（mods/<owner>.<modid>/）                          │
│   manifest.json + python/**/*.py + web/**/*.js          │
│   只能 import simchat_mod.*，不得 import 宿主内部实现    │
└─────────────────────────────────────────────────────────┘
```

**安全边界**：Phase 2 剩余交付的 Loader 底座形成一条 fail-closed 流水线——manifest schema 先验 → resolver 查依赖 → verify 验签名（binary） → sandbox 子进程隔离（crash 不拖宿主）。任何一步失败 → MOD status=failed，宿主继续运行。

## 当前 MOD

`mods/` 下已落 8 个 MOD（4 类全覆盖）：

| MOD | 类型 | hooks | 交付 |
|---|---|---|---|
| `barry.galax` | binary | `chat.mode` | Phase 1 — Rigard 的证据加权检索管线抽成 MOD |
| `agent-config-minimal` | agent-config | — | Phase 3 — 女仆人设 + 简约主题 CSS |
| `automation.daily-digest` | automation | — | Phase 5 — 每日摘要 DAG 流示例 |
| `noic.skill-readfile` | skill | `agent.tool` | Phase 2.4 — 原 Kirara/Rigard 硬编码 skill 迁出 |
| `noic.skill-websearch` | skill | `agent.tool` | Phase 2.4 |
| `noic.skill-screenshot-recognition` | skill | `agent.tool` | Phase 2.4 |
| `noic.skill-areyoutrouble` | skill | `agent.tool` | Phase 2.4 |
| `noic.skill-realitycheck` | skill | `agent.tool` | Phase 2.4 |

## ABI

唯一稳定接口是 SDK（`simchat/sdk/python/simchat_mod/`）。MOD 代码只能 import 这里暴露的符号：

```python
from simchat_mod import ModApi, ModeSpec, ToolSpec, BaseSkill, hook
```

`manifest.schema.json` 的值 `abi: "lmbrew-mod/1"` 是版本号——未来破坏性变更升级主版本，非破坏性升次版本。

## 阶段进度

| 阶段 | 状态 | Commit 范围 | 关键交付 |
|---|---|---|---|
| Phase 0 契约冻结 | ✅ | — | spec/ 5 份 + fixture 5 条 |
| Phase 1 第一个 MOD（Galax） | ✅ | `c58ec00` | GalaxPipeline 抽成 `mods/barry.galax/` |
| Phase 2 本体独立对话 + Loader 底座 | ✅ | `494c5e9`–`e03e310` | runtime/ 3 模块 + loader/ 9 模块 + P2.4 skill MOD 全链路 |
| Phase 3 蓝图化 | ✅ | `7f29360`–`b4ec484` | lmbrew.py 降至 **303 行**，4 蓝图接管全部路由 |
| Phase 4 CLI + 索引 | ✅ | — | `simchat mod init/pack/verify/publish/gen-key` + `registry/index.json` 静态索引 |
| Phase 5 Automation DAG | ✅ | — | `automation/` DAG 引擎（scheduler/executor/approval/quota/audit）+ `mods/automation.daily-digest` |
| Phase 6 仓库/品牌/社区 | 规划中 | — | 官方仓库/商店前端/付费框架 |

## 冒烟测试（P2.4 交付时）

P2.4 skill MOD 迁移的完整链路验证，11/11 PASS：

```
✓ 5 个 manifest 通过 validate_manifest()
✓ 5 个 skill MOD 全部 run_isolated() 成功，register 带 tools[]
✓ invoke_tool realityCheck 正常文本 → violation=False
✓ invoke_tool realityCheck 伤害文本 → violation=True, 4 关键词命中
✓ invoke_tool areYouUnderTrouble 危机文本 → is_threat_detected=True
✓ 不存在的 tool 名 → ok=False
✓ Python 语法检查：simchat/ 全部模块 + 5 MOD
✓ Git clean：2 commit 可回放
```

## 本目录不包含（故意的）

- 任何私有实现（JRVS / Hippo / 人设 / 音色；Galax 检索管线已开源为 `mods/barry.galax/`）
- 任何密钥、授权素材、用户数据
- 商店前端（Phase 6 范围）
- `__pycache__/`（已 gitignored）
