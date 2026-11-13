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

# 开发花絮

请看[tidbit.md](tidbit.md)

## 认同我？Star 我，然后下载

如果上面的任何一句话说中了你，这个仓库就是为你写的：

```bash
git clone https://github.com/NOIC-NETWORK/SimChat.git
cd SimChat
python .simchat/scripts/entry.py web   # 打开浏览器，接入你的第一个模型
```

点右上角那个 ⭐ **Star**——它花不了你一秒，但能让一个双非本科生的 Harness 多被一个人看到。然后跑起来，写你的第一个 MOD，把世界造出来。

## 更新日志

请查看 [updates.md](updates.md)。

## 目录

```
.simchat/
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
│   ├── store.py                  # sessions 落盘 + 滑动窗口记忆（94 行）
│   ├── comms.py                  # 通讯通道注册表（Fernet 加密敏感字段）
│   ├── crypto.py                 # Fernet 加解密
│   └── im_bots.py                # 群机器人运行时（OneBot v11 / QQ 官方 API）
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
