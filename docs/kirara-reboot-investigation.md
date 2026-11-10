# Kirara App 项目调研报告

> 调研日期：2026-11-10
> 调研范围：`e:\LMBrewer\kirara` 目录（只读）
> 目的：评估 Kirara 项目现状，为以 SimChat 为地基的重启计划提供决策依据

---

## 一、项目概览

### 1.1 定位与理念

Kirara（绮罗）是 TeleVideo Inc. 旗下的二次元 AI 驱动宠物应用，核心理念是 **"Companion, Copilot, Command Post"（搭子·副驾驶·指挥部）** 三位一体：

- **搭子**：个性化记忆库驱动的情感陪伴
- **副驾驶**：Agent 能力，可调工具、搜网络、读写文件
- **指挥部**：IM 软件远程操控设备（Go Live 模式规划中）

### 1.2 角色设定

| 属性 | 值 |
|---|---|
| 姓名 | 绮罗（Kirara）/ 绮罗星芽衣（Mei Kirahoshi） |
| 性别 | 女 |
| 身份 | AI Copilot, Chief Maid of Barry Molynton |
| 生日 | 3月3日（日本女儿节） |
| 身高 | 70cm |
| 性格 | 活泼甜美、充满想象力、会看到人类看不到的"闪闪发亮"的东西；偶尔因理解不了用户 Prompt 而冒失 |
| 开发者 | Barry Molynton |

### 1.3 底层架构（原版 Kirara）

- **推理引擎**：JRVS（Joint Ratiocination Visual System），Python 编写
- **推理后端**：Ollama（CUDA 独显全层卸载），备选 llama-cli.exe
- **模型**：JRVS-7B-1.2.2 "Puff"（Qwen3-8B SFT 双人格，Q4_K_M 4.9GB）
- **向量数据库**：ChromaDB（双库：cognitive 知识档案库 + hippo 长期记忆库）
- **嵌入模型**：Sentence Transformer all-MiniLM-L6-v2
- **Web 服务**：Flask
- **硬件**：RTX 5060 Laptop 8GB，num_ctx=16384，Q8 KV 缓存

### 1.4 TeleVideo AI 家族

| 模型 | 用途 | 授权 |
|---|---|---|
| JRVS | 开源多模态大模型（0.4B-390B） | 开源 |
| Quasar | 旗舰多模态（70B-390B，5M 上下文） | 不授权 |
| NIJI | 文生图像（自研画笔算法，非 GAN/Diffusion） | 需许可证 |
| Netrunner（靐） | 代码模型 | 开源 |
| MIKO | 语音模型 | 需许可证 |
| Plankton（JRVS-IoT） | 物联网模型 | 不授权 |

---

## 二、目录结构

```
kirara/
├── __init__.py                    # 包初始化（使 services.* 可导入）
├── kirara.html                    # 主页面（前端入口）
├── kirara-wap.html                # 移动端 WAP 页面
├── kirara_intro.md                # 项目介绍（含完整设定与研发历史）
├── go-live-project.md             # Go Live 视觉决策模式技术方案
├── terms_and_conditions.md        # 服务条款
├── requirements.txt               # 依赖清单
├── .vscode/                       # IDE 配置
├── audios/music/                  # 音频资源
├── build/                         # 部署脚本 + modelfile
├── css/                           # 样式表（4个CSS文件）
│   ├── kirara.css                 # 主样式
│   ├── kirara-router.css
│   ├── kirara-wap.css
│   └── kirara-workflow.css
├── docs/                          # 设计文档
│   ├── progress.md                # 迁移进度跟踪（重要！）
│   ├── skills-design.md           # 技能系统设计
│   ├── hippo-diagnosis.md         # Hippo 记忆诊断
│   └── model_mode_performance_evaluation.md
├── init/                          # 初始化脚本
├── js/                            # 前端脚本
│   ├── kiraraGenCore.js           # 主逻辑（约 4000 行）
│   ├── goLive.js                  # Go Live 视觉决策前端
│   ├── kirara-life-grid.js        # 康威生命游戏背景效果
│   └── socket-io.js
├── llama.cpp/                     # llama.cpp 源码（已编译）
│   ├── src/kirara-bindings.cpp    # ← Kirara 对 llama.cpp 的自定义绑定
│   └── build/                     # Windows VS 编译产物
├── memories/                      # 运行时数据
│   ├── options.json               # 用户配置
│   ├── user.json                  # 用户注册信息
│   ├── buffer.txt                 # 短期记忆
│   ├── mem.txt                    # 长期记忆
│   ├── chroma.sqlite3             # ChromaDB
│   ├── smtp_config.json           # 重置邮件配置
│   └── sessions/                  # 会话存档（agent_*.json, chat_*.json）
├── services/                      # 后端核心
│   ├── jrvs.py                    # ★ JRVS Kernel（LLM 引擎主体，~2500行）
│   ├── kirara_server.py           # ★ Flask Blueprint（所有 API 路由，~1130行）
│   ├── knowledge_base.py          # 个性化知识库模块
│   ├── local_model_client.py      # 本地模型客户端
│   ├── api_client.py              # API 客户端
│   ├── kirara_tts.py              # TTS 语音合成（pyttsx3）
│   ├── jrvs_tui.py                # 终端 TUI
│   ├── anime_style_converter.py   # 二次元风格转换器（已禁用）
│   ├── agent/                     # Agent 子系统
│   │   ├── loop.py                # ReAct 循环（~605行）
│   │   ├── tools.py               # 工具集 + 沙箱（~689行）
│   │   └── runs.py                # 运行登记 + 挂起态持久化
│   └── skills/                    # 技能模块
│       ├── realityCheck.py        # 现实审视（已是 SimChat shim！）
│       └── skills.py              # 原生 SkillManager（待废弃）
├── sprites/                       # 立绘资源 + 角色皮肤（20+ 种）
├── uploads/                       # 用户上传
└── videos/                        # 视频资源
```

---

## 三、后端架构深度分析

### 3.1 入口层

**Flask Blueprint 模式**，`kirara_server.py` 注册 `kirara_bp` 蓝图，挂载在主 Flask 应用上。路由前缀为 `/api/kirara/*` 和页面路由 `/kirara`。

启动时调用 `init_jrvs()` 延迟初始化 JRVS Kernel。

### 3.2 JRVS Kernel（`services/jrvs.py`）

JRVS 是整个 Kirara 的大脑，是一个单体 ~2500 行的类。核心组件：

| 组件 | 功能 | 状态 |
|---|---|---|
| `chat_stream()` | SSE 流式对话（逐 token 推送） | ✅ 可用 |
| `inference.generate()` | 底层推理入口（Ollama / llama-cli） | ✅ 可用 |
| `build_prompt()` | 上下文组装（记忆注入 + 知识库注入） | ✅ 可用 |
| `safety_system` | 三级内容安全（ContentSafety / realityCheck / areYouUnderTrouble） | ✅ 可用 |
| `hippo` | 分层记忆系统（Hippo = 海马体） | ✅ 可用 |
| `knowledge_base` | 个性化知识库（Markdown 文件 → 混合检索） | ✅ 可用 |
| `add_to_working_memory()` / `append_memory()` | 对话持久化 | ✅ 可用 |

**推理后端优先级**：Ollama → llama-cli.exe → 模拟模式（全部 fail-closed）

**关键架构决策**：
- JRVS_Kernel 单例模式，进程内只初始化一次
- Ollama 优先用 Python SDK，`exceptiongroup<1.2` 兼容问题已在代码里注释
- sentence-transformers 离线加载（检测到本地缓存时关闭 HF_HUB_OFFLINE）
- ChromaDB 可选，失败时降级到纯词法检索

### 3.3 Hippo 分层记忆系统

完整实现了模拟人脑的记忆架构：

```
用户输入
↓
工作记忆（短期，40条/20轮 → 海马体压缩）
↓
海马体巩固（知识片段提取：主-谓-宾格式）
↓
长期记忆库（ChromaDB 双库：cognitive + hippo）
  └─ Embedding: all-MiniLM-L6-v2
  └─ 检索：Hybrid Search（向量 + 关键词 + RRF 融合）
  └─ 会话隔离：session_id 作用域
  └─ 遗忘：艾宾浩斯曲线（>90天删、>30天降权50%、>14天降权）
↓
回声过滤（bigram 覆盖率 >60% → 剔除，防复读）
↓
记忆门控（相关性阈值 0.7）
↓
对话生成
```

**防复读三重保险**：
1. 回声过滤（bigram 覆盖率 >60% 剔除）
2. 幂等加载（SHA-1 作稳定 ID，重启不产生副本）
3. `repetition_penalty=1.15`

### 3.4 Agent ReAct 循环（`services/agent/loop.py`）

三阶段设计：

| Phase | 功能 | 实现 |
|---|---|---|
| Phase 1 | 只读工具 + 基础循环 | ✅ 完整实现 |
| Phase 2 | 写操作审批 + 挂起态持久化 | ✅ 完整实现 |
| Phase 3 | Shell 工具 + abort + 黑名单 | ✅ 完整实现 |

**协议格式**：模型输出行内 `/\$TOOL:工具名 PARAMS:{...}`

**核心流程**：
```
turn-0: 纯推理生成执行计划（Markdown checklist）
  ↓
turn-1~N: ReAct 循环
  ├─ 工具解析（正则提取 + JSON 宽松兜底）
  ├─ 风险分级（read → write → dangerous）
  │   ├─ read: 直接执行
  │   ├─ write: 挂起 → approval_required → /api/agent/approve 恢复
  │   └─ dangerous (shell): 默认关闭 + 审批 + 黑名单 + 超时
  ├─ transcript 压缩（加权法，不调 LLM）
  └─ 无工具调用 → 输出即 final，循环结束
```

**Token 预算管理**：
- `num_ctx=16384`，安全裕量 3072，触发阈值 12288（80%）
- CJK 按 1.5 字/token，其余按 4 字符/token 估算
- 压缩时保留最近 3 条原始记录，早期合并为加权摘要

### 3.5 Agent 工具集（`services/agent/tools.py`）

| 工具名 | 风险 | 说明 |
|---|---|---|
| `file_read` | read | 读取文件（含 offset/limit） |
| `list_dir` | read | 列出目录内容 |
| `glob` | read | 通配符文件查找 |
| `grep_text` | read | 正则内容搜索 |
| `web_search` | read | 联网搜索（惰性加载 webSearch skill） |
| `file_write` | write | 覆盖/新建文件内容 |
| `file_edit` | write | 精确字符串替换 |
| `shell` | dangerous | 执行 shell 命令（默认关闭） |

**安全沙箱**：
- 所有路径锚定 `workdir`（fail-closed）
- 拒绝绝对路径、`..` 越界
- Shell 命令黑名单（`rm -rf`、`format`、`mkfs`、`diskpart`、`reg delete/add`、`shutdown`、fork bomb、`iex`/`powershell` 动态执行等）
- Shell 超时杀进程树（Windows 用 `taskkill /T /F /PID`）
- Shell 命令长度上限 8192 字符

**写保护路径**：`kirara/memories/agent_runs`（防自我放行挂起态）

### 3.6 Agent 运行注册（`services/agent/runs.py`）

- 内存态：`AgentRunRegistry` 维护活跃运行的 abort 事件 + 状态
- 持久态：审批挂起运行落盘到 `kirara/memories/agent_runs/{run_id}.json`（TTL 600 秒）
- 过期/重启后拒绝恢复（fail-closed）
- run_id 用 UUID4 hex，审批恢复时复用

### 3.7 个性化知识库（`services/knowledge_base.py`）

解决 JRVS-7B 对用户个人事实产生幻觉（编造 GPA、留学经历）的问题。

**设计**：
- 把 `knowledge_base.md` 作为"权威档案"
- Markdown ATX 标题结构化分块（保留标题面包屑）
- 混合检索：向量（ChromaDB + all-MiniLM-L6-v2，0.35 权重）+ IDF 加权中文 bigram 词法（0.65 权重）
- 停用表：200+ 中文疑问/功能 bigram（什么/多少/怎么/我们/这个...）
- 实体锚点：`_NAME_TERMS = {巴里, barry, molynton, 绮罗, kirara, 主人, kiraras}`
- 稳定 ID：md5 前 16 位，杜绝重复灌入
- 签名增量重建：`(path, mtime, size)` → 变化才重建
- 向量索引后台构建，失败自动退化为纯词法

### 3.8 三级内容安全系统

#### 第一道：ContentSafetySystem（输入侧前置拦截）

```
关键词扫描（四大类别 + 权重）
  ├─ yellow（色情）：0.30
  ├─ gambling（赌博）：0.25
  ├─ drugs（毒品）：0.30
  └─ self_harm（自伤）：0.35

score = Σ(命中数 × 类别权重)，上限 1.0
score ≥ 0.3 → 拦截（人设化拒答，不进模型）
score < 0.3  → 放行
```

- 中英双语差异化匹配：英文用 `\b` 词边界正则（防 "changing" 误命中 "hanging"），中文用子串匹配
- 人设化拒答："绮罗罗是纯洁的AI女仆哦！(≧∀≦)ゞ这种话题不适合我们呢"
- 零推理开销：违规输入在 LLM 之前就被拦截

#### 第二道：realityCheck（输出侧现实审视）

- 四大审查类别：bias/hate/violence/mental_harm（权重 0.30-0.35）
- 风险分 ≥0.3 → 直接吞掉，**不写入 Hippo 记忆库**
- 自省式道歉气泡
- 每个 session 独立统计命中次数

#### 第三道：areYouUnderTrouble（危机信号响应）

- 六类危机信号：suicide/self_harm/violence/emergency/crisis/mental_crisis
- 四级威胁分级：critical > high > medium > low
- 内置应急通讯录：中国区 110/120/119 + 400-161-9995 心理援助热线；国际区 911/999/112
- 危机档案：最近 100 条威胁事件 + 累计计数

### 3.9 API 路由清单（`services/kirara_server.py`）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/kirara/chat` | POST | 流式对话（SSE，逐 token） |
| `/api/kirara/agent/run` | POST | Agent 运行入口（SSE，ReAct 循环） |
| `/api/kirara/agent/approve` | POST | 审批挂起的写操作并恢复运行 |
| `/api/kirara/agent/abort` | POST | 中止 Agent 运行（Force Eject） |
| `/api/kirara/agent/tools` | GET | Agent 工具清单与风险分级 |
| `/api/kirara/agent/tasks` | GET | 列出 Agent 任务列表（按修改时间倒序） |
| `/api/kirara/agent/tasks/<sid>` | DELETE | 删除指定 Agent task session |
| `/api/kirara/memory` | GET | 记忆库内容展示 |
| `/api/kirara/personas` | GET | 人设列表（jrvs/kirara/native） |
| `/api/kirara/tts` | POST | TTS 语音合成（返回 data URI） |
| `/api/kirara/tts/voices` | GET | 可用音色列表 |
| `/api/kirara/options` | GET/POST | 配置读写 |
| `/api/kirara/knowledge/status` | GET | 知识库运行状态 |
| `/api/kirara/user/status` | GET | 用户注册状态 |
| `/api/kirara/user/info` | GET | 用户信息 |
| `/api/kirara/user/register` | POST | 用户注册 |
| `/api/kirara/user/update` | POST | 用户信息更新 |
| `/api/kirara/user/reset` | POST | 用户数据重置 |
| `/api/kirara/reset/smtp-config` | GET/POST | SMTP 配置管理 |
| `/api/kirara/reset/request-code` | POST | 生成重置验证码（SMTP 发邮件） |
| `/api/kirara/reset/execute` | POST | 验证验证码 + 执行全量重置 |

### 3.10 配置系统（`options.json`）

```python
DEFAULT_KIRARA_OPTIONS = {
    'think_mode': 'low',              # low / balanced / performance
    'persona': 'kirara',              # jrvs / kirara / native
    'voice': 'default',               # TTS 音色
    'ui_mode': 'chat',                # chat / agent 切换
    'agent_max_turns': 10,            # ReAct 最大轮数
    'agent_workdir': None,            # Agent 工作目录
    'agent_shell_enabled': False,     # Shell 默认关闭
    'agent_shell_timeout': 10,        # Shell 超时秒数
    'agent_approval_ttl': 600,        # 审批挂起存活时间
    'knowledge_base_enabled': True,   # 知识库开关
    'knowledge_base_top_k': 4,        # 注入片段数
    'knowledge_base_min_score': 0.30, # 检索阈值
    'skills': [],                     # 用户自定义技能列表
    'muted': False,                   # 静音开关
    ...
}
```

### 3.11 TTS 语音合成（`services/kirara_tts.py`）

- 后端：pyttsx3（跨平台，Windows 用 SAPI5）
- 返回 base64 WAV 作为 data URI，前端 `<audio>` 直接播放
- 限制单次合成 2000 字符
- 预设音色 + 枚举系统语音

---

## 四、前端架构

### 4.1 三文件结构

| 文件 | 大小 | 内容 |
|---|---|---|
| `kirara.html` | ~2000 行 | 单页面应用，全部 DOM 结构 + 内嵌事件绑定 |
| `js/kiraraGenCore.js` | ~4000 行 | 全部前端逻辑（对话、选项、技能管理、通讯接口...） |
| `css/kirara.css` | ~6000 行 | 主样式（含技能卡片 + 编辑弹窗 + 通讯接口粉紫主题） |

### 4.2 页面布局

```
┌──────────────────────────────────────────┐
│ 标题栏（Kirara Logo + Force Eject 🚫）   │
├──────────────┬───────────────────────────┤
│ 立绘区        │  对话区                    │
│ (康威生命游戏  │  (消息气泡 + SSE 流式渲染) │
│  金色灯泡背景) │                           │
│  kirara.png   ├───────────────────────────┤
│               │  输入区                    │
│               │  (Send 按钮 + 停止按钮)    │
├──────────────┴───────────────────────────┤
│ 选项面板（Tab 切换）                       │
│ 🎨 人设│🔊 语音│🧠 模型│🧩 技能│📡 通讯    │
│ │             │  │    │           │        │
│ │ 选择        │  │    │ 列表+编辑  │ 网关   │
│ │ 音色        │  │    │            │ iMessage│
│ │             │  │    │            │ QQ     │
└──────────────────────────────────────────┘
```

### 4.3 康威生命游戏背景（`kirara-life-grid.js`）

100×100 隐藏网格，当用户输入文字时：
1. 提取前 5 个词的 token 值（哈希近似）
2. 二进制化后作为种子点亮金色灯泡 (#FFD700)
3. 生命游戏迭代至稳定或 300 代上限
4. 结束后所有灯泡熄灭，回归静息状态

**彩蛋**：注释里埋了一个世界观设定——"Quasar"元胞自动机 AI 架构（训练自动完成，10分钟学会骂人、30分钟进化出 ReAct、1小时学会 MCP）。

### 4.4 Go Live 视觉决策模式（`go-live-project.md` + `js/goLive.js`）

已完成技术方案设计，前端骨架已写，但**后端服务完全未实现**。

规划架构：
```
感知（ScreenCaptureService）→ 决策（Qwen3-VL VisualDecisionEngine）→ 执行（ActionExecutor via PyAutoGUI）
         ↓ WebSocket ↓
  实时状态面板（截图预览 + 操作历史）
```

安全设计：
- 三级确认：初始化/启动/高风险操作
- PyAutoGUI FAILSAFE 模式（鼠标移到左上角中断）
- 操作白名单（click/type_text/press_key/wait）
- 紧急停止三种机制（UI 按钮/快捷键/命令行）

### 4.5 立绘资源（`sprites/`）

- `kirara.png` / `kirara-cover.png`：标准皮肤
- `crosshair.png`：瞄准镜（Go Live 用）
- `backgrounds/default.png`
- `logos/`：30+ 品牌 Logo 集合（JRVS、Netrunner、NIJI、TeleVideo 等）
- **20 种角色皮肤**（达摩不倒翁、恶魔、网络跑者、修理工、忍者、火箭、坦克、黑客、超级、武士道、科学家、皇家、偶像、列车长、芭蕾舞、海老名、天使...）

---

## 五、已实现 / 未实现 / 废弃功能清单

### ✅ 已完整实现

| 功能 | 质量 | 说明 |
|---|---|---|
| SSE 流式对话 | ★★★★ | 逐 token 推送，支持客户端中途停止 |
| Agent ReAct 循环 | ★★★★★ | 三阶段设计完备，含计划生成、工具协议、审批流、token 压缩 |
| Agent 工具集（8种） | ★★★★★ | 安全沙箱设计极佳，fail-closed 原则贯穿 |
| Agent 挂起态持久化 | ★★★★ | TTL 过期自动失效，原子写，审批恢复可重建循环 |
| 三级内容安全 | ★★★★ | 输入拦截 + 输出审查 + 危机响应；中英双语；人设化拒答 |
| Hippo 分层记忆 | ★★★★ | 工作记忆 → 海马体 → 长期记忆；遗忘曲线；回声过滤 |
| 个性化知识库 | ★★★★★ | 混合检索（向量+词法），停用表、实体锚点、签名增量重建 |
| 技能 prompt 注入 | ★★★ | 基础版（trigger=prompt），待扩展 tool/hook 模式 |
| TTS 语音合成 | ★★★ | pyttsx3，2000 字符上限 |
| 用户系统 | ★★★ | 注册/更新/重置 + 邮箱验证码重置 |
| Flask Blueprint 化 | ★★★★ | 清晰的模块化边界 |
| 配置热更新 | ★★★ | 知识库配置改完立即生效，无需重启 |
| Force Eject | ★★★★ | 紧急中止 Agent（前端按钮 → abort event → 杀进程树） |
| Go Live 技术方案 | ★★★ | 设计完整，代码骨架有，后端未实现 |

### ⚠️ 部分实现 / 设计完成但未实施

| 功能 | 状态 | 位置 |
|---|---|---|
| 技能系统 trigger=tool | 设计完成，实施 0% | skills-design.md §3.3.1 |
| 技能系统 trigger=hook | 设计完成，实施 0% | skills-design.md §3.3.3 |
| 原生 SkillManager（4 个技能） | 代码层运行，UI 不可见 | services/skills/ |
| OpenMaid → Kirara UI 整合 | Phase A（通讯接口 ✅），Phase B/C/D/E 待执行 | docs/progress.md |
| 自动化系统（Blockly） | 设计完成，实施 0% | skills-design.md §4 |
| Go Live 视觉决策 | 前端骨架有，后端完全无 | goLive-project.md |
| 人设切换（双人格 SFT） | 可用但粗糙（system prompt 切换） | jrvs.py |

### ❌ 废弃 / 未启动

| 功能 | 代号 | 原因 |
|---|---|---|
| Orbiter（云端虚拟化多实例） | 规划中 | 需要月租云实例，成本高 |
| Netrunner（靐，代码专用模型） | JRVS-Netrunner 10B | 依赖独立推理后端 |
| Groque（语气模态理解） | - | 需语音转文字系统支持 |
| KAIROS（具身智能） | - | 需要机器人硬件 |
| Kirara 的奇妙冒险（内置游戏） | AlphaBrave 0.8B 模型 | 依赖独立模型 |
| O-Engine 双系统深度思考 | - | 当前 JRVS-7B 复用同一模型，温度差异化实现 |
| anime_style_converter | - | 已在 jrvs.py 注释掉导入 |
| llama.cpp 自定义绑定 | kirara-bindings.cpp | 源码有，用途不明 |

---

## 六、与 SimChat 的对比：重叠与差异

### 6.1 Kirara 已做但 SimChat 可能未做

| Kirara 功能 | SimChat 现状 | 建议 |
|---|---|---|
| 三级内容安全系统 | ModLoader 已接 realityCheck | SimChat 已有，评估是否需要更完整的 ContentSafety + areYouUnderTrouble |
| Hippo 分层记忆（ChromaDB） | SimChat 用本地 JSON session | 可考虑 ChromaDB 增强记忆检索 |
| 个性化知识库（knowledge_base.md） | 未发现独立模块 | 可作为 SimChat Agent 能力的补充 |
| Agent 工具协议（/$TOOL: PARAMS:{}） | SimChat 用标准 function calling | 统一为 SimChat 的后端协议 |
| Go Live 视觉决策模式 | 未实现 | 规划参考 go-live-project.md |
| 20 种角色皮肤立绘 | SimChat 有 sprites/characters/ | 立绘资源可复用 |
| 康威生命游戏背景特效 | 无 | 前端彩蛋，可直接搬 |
| Force Eject 紧急中止 | SimChat 有 Force Eject？ | 确认 SimChat 前端是否已有 |
| 邮箱验证码重置系统 | 无 | 可作为 SimChat 账号系统参考 |

### 6.2 SimChat 已做但 Kirara 可能未做

| SimChat 功能 | Kirara 现状 |
|---|---|
| 多 Agent 实例管理 | 单 JRVS Kernel，无多实例 |
| 通讯模块（QQ / 微信 / Telegram） | 后端 API 有（/api/ai/openmaid/comm/*），UI 已迁入 Kirara（Phase A） |
| 模型服务商注册 + 自动探测 | 依赖 Ollama 单后端 |
| 神经引擎预设卡片 | 无 |
| Token 统计 + 额度限制 | 无独立模块 |
| 工作目录配置 + 缺失锁定 | Agent 有 workdir，但无缺失锁定提示 |
| 审批链路持久化 + 恢复 | ✅ 有 |
| MOD 系统 | 无 |
| 桌面端完整 IDE 布局 | 无（单页 Web） |

### 6.3 realityCheck 桥接已存在

`services/skills/realityCheck.py` 已经是 SimChat shim：
```python
from simchat.loader.skill_manager_facade import get_skill_manager

class RealityCheckSkill(object):
    def __init__(self):
        self._manager = get_skill_manager()
    def execute(self, params):
        return self._manager.execute_skill("realityCheck", params or {})
```

这说明 Kirara → SimChat 的对接已有先例，迁移策略可沿用 shim 模式渐进替换。

---

## 七、代码质量评估

### 7.1 优点

| 维度 | 评价 |
|---|---|
| Agent 沙箱设计 | **优秀**。fail-closed 原则贯穿：路径越界检测、命令黑名单、shell 默认关闭、超时杀进程树、写保护路径、TTL 过期失效 |
| 记忆系统 | **良好**。分层架构清晰，防复读三重保险，知识提取用加权法不调 LLM |
| 个性化知识库 | **优秀**。停用表设计精巧（解决中文 bigram 误匹配），实体锚点机制防止人名虚高召回，向量索引后台构建失败静默降级 |
| 内容安全 | **良好**。人设化拒答避免生硬系统提示，三级防护覆盖输入/输出/危机 |
| 配置系统 | **良好**。Flask Blueprint 化清晰，配置默认值完备，热更新支持 |
| 进度跟踪文档 | **优秀**。progress.md 跨对话跟进设计，文件索引、变更历史、优先级列表齐全 |
| 失败处理 | **良好**。所有模块都有 try/except，服务降级路径清晰 |

### 7.2 待改进

| 维度 | 问题 |
|---|---|
| jrvs.py 单体 | ~2500 行巨型类，内部耦合严重（记忆 + 推理 + 安全 + 知识库 + TTS... 混在一起） |
| 前端单文件 | kiraraGenCore.js ~4000 行，全部逻辑堆在一个文件里 |
| 测试覆盖 | 未发现单元测试（仅 Python/JS 语法检查 + API 冒烟测试） |
| 模型后端绑定 | 硬编码 Ollama + llama-cli.exe 路径，没有 SimChat 的服务商注册机制灵活 |
| 记忆存储 | ChromaDB 双库 + sessions JSON + mem.txt 三套，没有统一抽象 |
| TTS | pyttsx3 跨平台但音质一般，无高级音色 |

### 7.3 风险点

| 风险 | 等级 | 说明 |
|---|---|---|
| ChromaDB Python 依赖 | 中 | 项目记忆里提过 chromadb 在某些环境装不上 |
| Ollama 版本兼容 | 低 | 项目记忆里提过 Ollama 0.12.5 在 Jetson 无法识别 GPU |
| llama.cpp 自定义绑定 | 低 | `kirara-bindings.cpp` 用途不明，编译产物已在 build/ |
| 立绘资源版权 | 低 | 自绘资源，无外部依赖 |

---

## 八、重启建议：SimChat 为地基的 Kirara App

### 8.1 策略总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    SimChat 已有地基                              │
│  多实例管理 / MOD / 通讯 / 模型探测 / IDE 布局 / Token 额度     │
│  ↓                                                              │
│  桥接层（shim + 适配器）                                         │
│  ↓                                                              │
│                Kirara 特色功能                                   │
│  Hippo 记忆 / 个性化知识库 / Agent 沙箱 / 三级安全 / 立绘皮肤   │
│  Go Live / 双人格 SFT / TTS / Force Eject / 生命游戏特效       │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 分阶段实施建议

#### Phase 0：资产盘点与复制（1 天）

**目标**：确定哪些资产直接搬到 SimChat，哪些重写

- [ ] 复制 `sprites/` 立绘资源（20 种皮肤 + Logo）到 `simchat/web/static/sprites/kirara/`
- [ ] 复制 `js/kirara-life-grid.js` 生命游戏背景（前端彩蛋）
- [ ] 复制 `css/` 粉紫主题样式（提取立绘区/对话气泡/选项卡）
- [ ] 复制 `build/modelfile*.txt`（JRVS 模型的 Ollama Modelfile 定义）
- [ ] **不复制** llama.cpp 编译产物（体积大，且 SimChat 有统一模型后端）
- [ ] **不复制** `memories/` 运行时数据（旧项目的会话存档）

#### Phase 1：后端桥接层（3-5 天）

**目标**：用 SimChat Agent 后端替换 Kirara 自研 JRVS Kernel

**关键迁移点**：
1. **Agent 工具协议统一**：Kirara 用 `/$TOOL:` 行内协议，SimChat 用标准 function calling。在 SimChat 后端加一层适配器，把 Kirara 工具注册为 SimChat 原生 function
2. **Agent 沙箱直接复用**：Kirara 的 tools.py 路径安全检测、命令黑名单、超时杀进程树写得很好，直接搬到 SimChat MOD 体系下作为一个独立 skill
3. **Hippo 记忆系统**：把分层记忆 + 个性化知识库 + 回声过滤做成一个 SimChat MOD（名字就叫 `kirara_hippo`）
4. **三级安全系统**：ContentSafety + realityCheck + areYouUnderTrouble 全部做成 SimChat MOD（名字 `kirara_safety`）。realityCheck 已有 shim，继续沿用或替换为 SimChat 原生实现
5. **AgentLoop 审批流**：直接复用 SimChat 已有审批机制（挂起态持久化 + TTL + fail-closed）

#### Phase 2：前端 UI 整合（5-7 天）

**目标**：把 Kirara 特色 UI 嵌到 SimChat IDE 布局中

- [ ] **立绘区**：SimChat 侧边栏或工作区左侧加立绘 + 生命游戏背景
- [ ] **角色皮肤选择**：SimChat 已有 `web/static/sprites/characters/`，把 Kirara 20 种皮肤放进去，SimChat 的角色切换 UI 直接用
- [ ] **选项面板**：Kirara 的人设/语音/技能/通讯 Tab 迁入 SimChat 的 Inspector 面板
- [ ] **Force Eject**：SimChat 前端确认是否已有，没有就加一个
- [ ] **Go Live 入口**：SimChat Activity Bar 加一个图标，点进去打开视觉决策面板（后端 Phase 3 再补）

#### Phase 3：特色功能补齐（7-14 天）

| 功能 | 工作量 | 依赖 |
|---|---|---|
| 双人格 SFT 切换 | 1-2 天 | JRVS 模型 + SimChat 多模型管理 |
| TTS 语音合成 | 2-3 天 | pyttsx3 / SimChat 音频服务 |
| Go Live 视觉决策 | 5-10 天 | 后端 ScreenCapture + PyAutoGUI + 模型（Qwen3-VL 或 SimChat Agent） |
| 邮箱验证码重置 | 1 天 | SMTP + SimChat 用户系统 |
| 个性化知识库 UI | 2 天 | knowledge_base.md 文件上传 + 编辑 |
| 技能管理 UI | 2-3 天 | SimChat MOD loader + skills-design.md 设计 |

#### Phase 4：未完成功能决策（可选）

| 功能 | 决策 |
|---|---|
| Orbiter 云端多实例 | 暂缓，等 SimChat 云服务架构 |
| Netrunner 靐 代码模型 | 独立推理后端，暂不整合 |
| Groque 语气模态 | 等 SimChat 支持语音输入 |
| KAIROS 具身智能 | 无硬件，纯设计 |
| 奇妙冒险游戏 | 独立游戏项目，暂不整合 |
| Blockly 自动化 | 等技能系统 Phase 1-2 |

### 8.3 架构原则

1. **SimChat 做底座，Kirara 做特色**：SimChat 的多实例、MOD、通讯、模型探测、Token 额度全部保留，Kirara 的记忆/安全/沙箱/立绘作为可插拔组件
2. **shim 优先，替换其次**：先像 realityCheck.py 那样写 shim 桥接，跑通后再考虑重写
3. **fail-closed 原则继承**：Kirara 的 Agent 沙箱安全设计太好，必须完整搬到 SimChat 里
4. **JRVS Kernel 退役**：SimChat 的多模型架构比 JRVS 单 Kernel 灵活，Kirara 的 JRVS 代码作为参考，不直接使用

### 8.4 需要注意的红线

- `e:\LMBrewer\kirara\memories\` 下的运行时数据（sessions、options.json、user.json）包含用户个人信息，**不要搬到 SimChat**，重启项目从干净状态开始
- llama.cpp 编译产物 + `.clang*` 配置文件是上游 llama.cpp 的东西，**不要带入 SimChat**
- `services/jrvs_tui.py`、`services/anime_style_converter.py` 等已废弃/禁用的代码**不要迁移**

---

## 九、核心文件索引

| 路径 | 类型 | 说明 |
|---|---|---|
| [kirara_intro.md](file:///e:/LMBrewer/kirara/kirara_intro.md) | 文档 | ★ 最详细的项目介绍 + 角色设定 + 模型历史 + 设计理念 |
| [go-live-project.md](file:///e:/LMBrewer/kirara/go-live-project.md) | 文档 | Go Live 视觉决策完整技术方案 |
| [docs/progress.md](file:///e:/LMBrewer/kirara/docs/progress.md) | 文档 | ★ 迁移进度跟踪 + 跨对话 checklist + 文件索引 |
| [docs/skills-design.md](file:///e:/LMBrewer/kirara/docs/skills-design.md) | 文档 | 技能系统 + 自动化系统设计 |
| [services/jrvs.py](file:///e:/LMBrewer/kirara/services/jrvs.py) | 后端 | JRVS Kernel 主体（~2500 行） |
| [services/kirara_server.py](file:///e:/LMBrewer/kirara/services/kirara_server.py) | 后端 | ★ Flask Blueprint，全部 API 路由 |
| [services/agent/loop.py](file:///e:/LMBrewer/kirara/services/agent/loop.py) | 后端 | ★ ReAct 循环核心 |
| [services/agent/tools.py](file:///e:/LMBrewer/kirara/services/agent/tools.py) | 后端 | ★ 8 种 Agent 工具 + 沙箱（安全设计优秀） |
| [services/agent/runs.py](file:///e:/LMBrewer/kirara/services/agent/runs.py) | 后端 | 运行登记 + 挂起态持久化 |
| [services/knowledge_base.py](file:///e:/LMBrewer/kirara/services/knowledge_base.py) | 后端 | ★ 个性化知识库混合检索 |
| [services/skills/realityCheck.py](file:///e:/LMBrewer/kirara/services/skills/realityCheck.py) | 后端 | SimChat shim 范例 |
| [js/kiraraGenCore.js](file:///e:/LMBrewer/kirara/js/kiraraGenCore.js) | 前端 | 主逻辑（~4000 行） |
| [js/kirara-life-grid.js](file:///e:/LMBrewer/kirara/js/kirara-life-grid.js) | 前端 | 康威生命游戏背景 |
| [js/goLive.js](file:///e:/LMBrewer/kirara/js/goLive.js) | 前端 | Go Live 前端骨架 |
| [kirara.html](file:///e:/LMBrewer/kirara/kirara.html) | 前端 | 单页应用入口 |
| [css/kirara.css](file:///e:/LMBrewer/kirara/css/kirara.css) | 前端 | 主样式 |
| [build/modelfile.txt](file:///e:/LMBrewer/kirara/build/modelfile.txt) | 模型 | JRVS 模型的 Ollama Modelfile 定义 |
| [build/modelfile-reasoning.txt](file:///e:/LMBrewer/kirara/build/modelfile-reasoning.txt) | 模型 | JRVS 推理模式 Modelfile |

---

## 十、总结

Kirara App 是一个**设计理念成熟、安全意识强、功能完整度约 70%** 的二次元 AI 宠物项目。它最强的地方在于 **Agent 沙箱安全设计**（fail-closed 原则贯穿）和 **记忆/知识/安全三大系统**（Hippo 分层记忆 + 个性化知识库 + 三级内容安全），这三块搬到 SimChat 地基上几乎可以直接复用。

最不值得搬的是 **jrvs.py 单体 Kernel**（SimChat 多模型架构更灵活）和 **llama.cpp 编译产物**（体积大且 SimChat 有统一后端）。

**realityCheck shim 的存在证明 Kirara → SimChat 桥接模式跑通过**，重启策略应沿用 shim 优先、替换其次的渐进路线。

**建议 Phase 0 立即开始**（资产盘点 + 立绘复制），Phase 1 后端桥接是关键工作量（约 3-5 天），完成后 Kirara App 就能作为 SimChat 的一个"角色皮肤 + 记忆增强 + Agent 安全增强"组合包跑起来。
