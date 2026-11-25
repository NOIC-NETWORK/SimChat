# SimChat 上手教程（大纲）

> 目标：让一个第一次打开仓库的人，在 30 分钟内完成「跑起来 → 接上模型 → 和 Agent 对话 → 装上第一个技能」；
> 再花 1 小时能写出并调试自己的第一个 Skill MOD。
> 本文件是教程的总纲与写作计划，后续每章按 `NN-topic.md` 落到本目录。

## 1. 读者与学习路径

| 路径 | 适合谁 | 建议章节 | 预计产出 |
|---|---|---|---|
| A. 只使用 | 想把 SimChat 当本地 AI 客户端 | 01 → 02 → 03 → 04 → 05 | 能对话、能跑 Agent、会用 IDE 界面 |
| B. 装配型 | 想用现成技能/自动化扩展能力 | A + 06 → 07 → 10 | 会启停技能、配置定时流程 |
| C. 开发者 | 想写 MOD / 技能 / 接自己的系统 | B + 08 → 09 → 11 → 12 | 一个可加载、可验签的 MOD |
| D. 维护者 | 想读懂加载器与安全模型 | 06 → 09 → 11 + 附录 C | 能定位 MOD 加载失败的原因 |

前置条件：Windows 10/11、macOS 或 Linux；Python ≥ 3.9；可选 Ollama（本地模型）或任意 OpenAI 兼容 API Key。

## 2. 章节大纲

### 01 安装与首次启动
- **目标**：看到浏览器里的对话界面。
- **要点**：`git clone` → `pip install -r .simchat/scripts/requirements-simchat.txt` → `python .simchat/scripts/entry.py web`；默认监听 `127.0.0.1:5000` 并自动开窗（`--host` / `--port` / `--no-browser` 的用法）；`run.ps1` / `run.bat` / `run.sh` 的差异；仓库根与 `.simchat/` 的目录关系。
- **验收**：页面能打开，终端无报错，知道如何停服务（Ctrl+C）和改端口。

### 02 接入第一个模型
- **目标**：模型下拉里出现可用模型，并成功回一句话。
- **要点**：Ollama 本地接入（安装、拉模型、默认地址）；OpenAI 兼容服务商（Base URL / Key / 模型名）；「预检」在验什么、为什么会误判；多 provider 聚合与模型下拉分组；Key 的存储位置（加密写入 `data/config.json`，主密钥受系统保护）。
- **验收**：发一条消息收到流式回复；刷新页面后模型仍在（本地缓存）。

### 03 配置工作目录与第一次对话
- **目标**：理解「工作目录是对话与 Agent 的统一根」。
- **要点**：未选目录时的输入锁定；目录选择器（逐级浏览 / 直接输入绝对路径）；配置写入 `data/config.json`；会话列表、新建/切换、历史落盘；SSE 流式渲染与中断。
- **验收**：能切换工作目录并解释为什么没选目录不能发消息。

### 04 Agent 模式入门
- **目标**：让 Agent 调工具完成一次多步任务。
- **要点**：创建 AI 实例（`agent_capable`）；Agent 循环（思考 → 工具 → 观察 → 回答）；工具来源（内建方块 + 已加载技能）；审批卡与审批策略；`realityCheck` / `areYouUnderTrouble` 何时介入；token 用量与上下文压缩提示。
- **验收**：给出一个需要读文件 / 搜索的任务，看到工具调用时间线与最终答案。

### 05 IDE 界面速览
- **目标**：在六区布局里不迷路。
- **要点**：Activity Bar / Side Bar / 中央编辑器 / 右侧对话与检查器 / 底部控制台 / 状态栏；文件树、`/api/workspace/read` 支持的文件类型与大小上限；常用快捷键（`Ctrl+I` / `Ctrl+J` / `Ctrl+Shift+N` 等）；「方块 / MOD」分区与控制台里的技能启停。
- **验收**：能独立完成「打开文件 → 提问 → 查看 Agent 时间线 → 启停一个技能」。

### 06 概念地图：MOD、方块与技能
- **目标**：搞清 MOD 的定位和几个容易混的词。
- **要点**：
  - **MOD 的定位同 Minecraft MOD**：它是本体的扩展/修改包，不是另一个本体。装上一个 MOD，可以给本体带来新的资产（图片、模板、音色等）、新的方块与原子能力（Agent 可调用的工具）、新的 Agent 配置/人设、Web/IDE 界面片段、自动化流程。
  - **MOD 能装什么**：`manifest.json` + 代码入口 + `assets/` + `web/` + `flow.json` + agent-config；一切都通过 hooks 接入，不改本体源码，也不 fork 本体。
  - **分发分层**：`mods/` 放完整 MOD；`skills/` 放可独立分发的原子能力包（本质是轻量 MOD）。两者共用同一套 manifest / ABI / 沙箱，区别只在定位与默认 `layer`。
  - **其余词汇**：`layer=mod|block`；四类 `type`（skill / automation / agent-config / binary）与 hooks；`manifest.json` 各字段的作用；`data/mods/<id>`、`data/blocks/<id>`、`.simchat/uploads` 分别存什么。
- **验收**：拿到任意一个包，能说出它给本体「加上了什么」（资产 / 方块 / 配置 / 流程），以及它是完整 MOD 还是独立原子能力包。

### 07 安装、启用与排查技能
- **目标**：掌握技能的日常运维。
- **要点**：内置 5 个技能（`readFile` / `webSearch` / `screenshotRecognition` / `barry_galax` / `automation_daily_digest`）各自能力与限制；`/api/console/skills` 与 `POST /api/console/skills/<id>/toggle`；为什么启停要重启生效；`skills/.simchat_state.json` 的位置与手工恢复；加载失败时先看哪里。
- **验收**：停用 `webSearch` 后重启，Agent 工具列表里消失；恢复后重新出现。

### 08 写第一个 Skill MOD
- **目标**：从模板到一个能被 Agent 调用的工具。
- **要点**：`python .simchat/scripts/entry.py cli init --type skill --id <id> --name <显示名> --target <dir>` 生成骨架（`id` 只允许小写字母/数字/下划线）；目录约定（`manifest.json` / `python/` / `assets/` / `flow.json`）；SDK 用法（`ModApi`、`register_tool`、`ToolSpec`、`hook`、`api.data_dir`、`api.assets_dir`、`api.service`、`has_capability`）；entry 阶段只注册、不做重活；`print` 与 IPC 协议的关系（为什么要写 stderr / 日志）。
- **验收**：工具出现在 `/api/agent/tools`，能被 Agent 调用并返回结构化结果；重启后仍可用。

### 09 权限与安全：capabilities 到底管什么
- **目标**：写出「不越权」也不会莫名报错的 MOD。
- **要点**：`shell`、`fs.read` / `fs.write` 的 scope（`workspace` / `mod-data` / `package` / `uploads` / `temp` / 显式路径）；未声明的访问会抛 `PermissionError`；`net.domains` 的精确、`*.example.com`、`*` 三种写法；签名与 `integrity` 的校验时机；Python 层闸门的边界（不是 OS 级沙箱，恶意代码仍需自行审查）。
- **验收**：给一个只能读 `workspace` 的技能加写操作，能读懂报错并正确补声明。

### 10 自动化：用 DAG 做定时任务
- **目标**：跑通一条定时流程。
- **要点**：`automation_daily_digest` 的 `flow.json` 结构；触发器（cron / event / manual）与 `policy`（超时、日配额、失败策略）；执行器、审批、审计与配额的关系；如何看运行记录与失败重试。
- **验收**：手动触发一次 digest，看到节点逐个执行；能改 cron 并解释生效时间。

### 11 调试与常见故障
- **目标**：遇到问题能自己定位。
- **要点**：日志与控制台的对应关系；MOD 状态（`loaded` / `failed`）与失败原因字段；常见错误表（未装依赖、manifest 非法、hook 不认识、签名失败、fs/net 越权、端口占用、模型预检 404、协议行被 `print` 顶掉）；一张「先查什么」的决策图；如何用最小复现包定位问题。
- **验收**：给定 3 个故障现象，能说出排查顺序并找到根因。

### 12 打包、发布与继续深入
- **目标**：把作品交给别人用。
- **要点**：`cli gen-key` 生成密钥；`cli verify` 两阶段校验；`cli pack` 算 integrity + 签名（及 `--zip`）；`cli publish` 生成 registry 条目；`registry/index.json` 的作用；hooks / events / ABI 版本规则；贡献流程与代码风格。
- **验收**：把自己的 MOD / 技能签名、打包，并生成一条 registry 条目。

## 3. 每章写作模板

每章统一采用以下结构，保证可扫读、可验收：

1. **你会得到什么**（一句话 + 一张结果截图或终端片段）
2. **前置条件**（依赖上一章 / 需要安装什么）
3. **跟着做**（编号步骤，每步一条命令或一次点击，标注预期输出）
4. **为什么会这样**（解释机制，链接到 `spec/` 或源码）
5. **常见坑**（3 条以内，指向 11 章的排查表）
6. **验收清单**（3–5 个可勾选项 + 一行「已知限制」，指到 [known-limitations.md](../known-limitations.md)）
7. **延伸阅读**（本仓库内相对路径）

约定：命令统一用 `python .simchat/scripts/entry.py ...`；路径以仓库根为基准；示例 MOD id 用 `noic_skill_hello` 一类只含小写字母/数字/下划线的可读名，显示名称另放 `name`；截图放 `docs/tutorials/images/<章节>/`。

## 4. 维护约定

- 教程只描述**当前实现**；行为变更时同一次提交内更新对应章节，必要时在 `updates.md` 记一条。
- 涉及 ABI 的示例必须标注 `abi: simchat-mod/2`，并链接 `spec/abi-changelog.md`。
- 示例代码必须可直接运行；不能运行的部分明确标注「伪代码」。
- 每季度按「新人路径 A」完整走一遍，跑不通即视为教程缺陷。

## 5. 术语表

| 术语 | 含义 |
|---|---|
| 本体 | SimChat 核心（`.simchat/`），提供对话、Agent、加载器、Web/IDE |
| MOD | 本体的扩展/修改包，定位同 Minecraft MOD：可新增资产、方块与原子能力、Agent 配置、界面片段、自动化流程；安装即改变本体可用内容 |
| 技能 / 方块 | MOD 提供的原子能力（Agent 工具），也可以单独分发包，通常 `layer=block`、`type=skill`，位于 `skills/` |
| 资产 | MOD 随包携带的资源（图片、模板、提示词、音色等），通过 `assets.root` 访问 |
| hook | 本体暴露的扩展点，如 `agent.block`、`chat.mode` |
| capability | MOD 声明的权限：`shell` / `fs` / `net` |
| 沙箱 | MOD 代码实际运行的独立子进程（含 fs/net 闸门） |
| workspace | 用户选择的工作目录，对话与 Agent 的共同根 |
| flow | 自动化 DAG 文件 `flow.json` |

## 6. 现有文档地图（写作时优先复用）

| 主题 | 文档 |
|---|---|
| 目录结构与阶段进度 | [README.md](../../../README.md) |
| API 端点 | [api-endpoints.md](../api-endpoints.md) |
| 权限模型 | [capabilities.md](../../spec/capabilities.md) |
| 扩展点与生命周期 | [hooks.md](../../spec/hooks.md) |
| Agent SSE 事件 | [events.md](../../spec/events.md) |
| ABI 变更规则 | [abi-changelog.md](../../spec/abi-changelog.md) |
| 沙箱 IPC 与闸门 | [sandbox_contract.md](../../loader/sandbox_contract.md) |
| 清单 schema | [mod-manifest.schema.json](../../spec/mod-manifest.schema.json) |
| MOD 可用性诊断与修复记录 | [mod-availability-diagnosis.md](../mod-availability-diagnosis.md) |
| 已知限制清单 | [known-limitations.md](../known-limitations.md) |
| 架构回顾 | [architecture-recap.md](../architecture-recap.md) |

## 7. 写作进度

| 章节 | 计划文件 | 状态 |
|---|---|---|
| 01 安装与首次启动 | [01-install.md](01-install.md) | 已完成 |
| 02 接入第一个模型 | [02-first-model.md](02-first-model.md) | 已完成 |
| 03 工作目录与对话 | [03-workspace-and-chat.md](03-workspace-and-chat.md) | 已完成 |
| 04 Agent 模式入门 | [04-agent-mode.md](04-agent-mode.md) | 已完成 |
| 05 IDE 界面速览 | [05-ide-tour.md](05-ide-tour.md) | 已完成 |
| 06 概念地图 | [06-mods-blocks-skills.md](06-mods-blocks-skills.md) | 已完成 |
| 07 技能安装与启停 | [07-manage-skills.md](07-manage-skills.md) | 已完成 |
| 08 第一个 Skill MOD | [08-first-skill.md](08-first-skill.md) | 已完成 |
| 09 权限与安全 | [09-capabilities.md](09-capabilities.md) | 已完成 |
| 10 自动化 DAG | [10-automation.md](10-automation.md) | 已完成 |
| 11 调试与排错 | [11-debugging.md](11-debugging.md) | 已完成 |
| 12 打包与发布 | [12-publish.md](12-publish.md) | 已完成 |

12 章正文已全部完成。各章只在对应实现变更时更新；文中标注的「当前实现不一致」项需先在代码侧确认，再改文档。
