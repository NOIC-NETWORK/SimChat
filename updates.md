# 最近更新

**2026-11-19** — 服务商厂牌化一期

- **新增 `runtime/vendors.py` 厂牌注册表**：按 Vendor / Transport / Account / Model 四层组织，协议 id（`ollama`、`openai_compat`、`anthropic`）与厂牌 id（百炼、火山方舟、千帆、Azure OpenAI、OpenAI、SiliconFlow、DeepSeek、Anthropic、Ollama 等）等价解析；每个厂牌声明默认端点、鉴权方式、模型建议与参数白名单。`aws_bedrock` 只登记为规划，调用会明确报「尚未实现」。
- **provider 调用链归一**：`core` 通过 `vendors.resolve_target()` 把协议 id / 厂牌 id 解析成账户视图，再交给 `create_provider()` 工厂；`provider_config` 负责厂牌归一、鉴权头、查询参数与 `params` 白名单过滤，测试、发现、保存均支持厂牌 id。
- **UI 与接口**：`ui_blocks` 由厂牌表生成预设芯片；`/api/providers` 输出 `vendor`/`vendors`，`/api/providers/discover` 接受厂牌 id；控制台服务商标题优先显示厂牌名，方块材质只作图标与缺省值。
- **文档**：新增 `docs/vendor-provider-refactor.md`，`docs/api-endpoints.md` 同步厂牌 id、配置字段与请求参数说明。
- 文件：`.simchat/runtime/vendors.py`、`.simchat/runtime/providers.py`、`.simchat/runtime/provider_config.py`、`.simchat/runtime/core.py`、`.simchat/runtime/ui_blocks.py`、`.simchat/runtime/agent/tools.py`、`.simchat/web/__init__.py`、`.simchat/web/static/js/chat.js`、`.simchat/docs/vendor-provider-refactor.md`、`.simchat/docs/api-endpoints.md`、`updates.md`

**2026-11-19** — MOD 前端入口规范、config 校验收紧与桌面宠物入库

- **MOD 前端入口规范**：manifest 新增顶层 `frontend_entry`，只允许 `web/` 下的 `.html` 相对路径，禁止 `..`、反斜杠与空格；schema 与加载器双重校验，指向不存在或越界的文件直接拒绝加载。`mods_index` 输出 `frontend_entry`/`frontend_url`，新增 `/mods/<id>` 与 `/mods/<id>/` 路由返回声明的入口页，控制台 MOD 详情增加「前端入口」链接。Kirara 声明 `web/index.html`。
- **config 校验收紧**：`config` 仅允许 `persona`/`system_prompt_file`/`params`/`theme`/`models`，未知键直接失败；提示词与主题必须是包内相对路径；`params` 只接受字符串/数字/布尔标量；`models` 改为严格的 `primary`/`runtime` 子 schema，`roles`、`status` 等字段也受约束。加载器执行同一套规则，不合法即拒绝加载。
- **启动顺序修复**：`AutomationEngine` 改为在 `discover()` 之前创建并启动，automation 类型 MOD 在加载期即可注册 flow；`automation_daily_digest` 恢复 `loaded`，`daily.workspace.digest` 正常注册。
- **桌宠固化进包**：Kirara 的桌宠页面迁入 `mods/kirara/web/index.html`，立绘与圆球 logo 放入 `mods/kirara/web/sprites/`（9 套立绘 + logo，约 10.8MB）；原 `preview/` 已删除，不再依赖包外资源。
- **物品栏去重与图标**：隐藏 `web_search`、`file_read` 两个重复入口，并在保留入口的提示中列出同能力别名；已由方块覆盖的技能包入口继续去重。新增 `glob`、`grepText`、`fileWrite`、`realityCheck`、`crisisSupport`、`kiraraTrivia` 六个方块图标；`bricks/` 下其余 10 个旧图标已全部入库，图标资产完整纳入版本控制。`inventory.js` 版本号更新为 `20261119d`。
- **验证**：`bricks` 图标与 `mods/kirara/web/` 资源均未被 `.gitignore` 忽略；Kirara 桌宠页面只引用包内相对路径 `sprites/...`；`automation_daily_digest` 已跟踪且未被停用。
- 文件：`.simchat/spec/mod-manifest.schema.json`、`.simchat/loader/manifest.py`、`.simchat/loader/lifecycle.py`、`.simchat/runtime/mods_index.py`、`.simchat/web/__init__.py`、`.simchat/web/static/js/chat.js`、`.simchat/web/static/js/inventory.js`、`.simchat/web/templates/index.html`、`.simchat/mods/kirara/manifest.json`、`.simchat/mods/kirara/web/`、`.simchat/web/static/sprites/bricks/`（6 个新图标）、`updates.md`

**2026-11-19** — Orbiter 方块、Kirara 只读地图、JRVS 双路径评测与前端收尾

- **宿主新增 `orbiter` 方块**：按 README 契约解析 `/@<模型名> -prompt "..."`、`/@<模型名> -mode=image` + 下一行 spec、`/$ <命令> -dir "..."`。本地 JRVS 先分诊，简单问题直接答；复杂任务才派发云端。润色只走本地 JRVS，原始提示词不上云；本地不可用时 fail closed，没有云端润色兜底。方块 `risk=write`，每次云端外发都走审批，拒绝时返回 `denied=approval` 且不调用任何模型。
- **目标模型可配置**：`data/config.json` 的 `orbiter.target_model`，默认 `qwen4-max`；未知模型 id 明确报错并给出可用示例，图像模型缺失时如实回复“规划中”，不伪造结果。
- **新增 `agent.map` 扩展点**：MOD 可通过 `api.register_agent_preset(...)` 注册地图（AI 实例），宿主按 `mod:<id>` 命名空间幂等落盘为 `readonly: true` 实例。只读地图显示「只读」徽标，编辑与删除均被拒绝，`reset` 会保留地图并重新创建默认实例。
- **Kirara 地图**：`mods/kirara/python/kirara_map.py` 用确定性算法从 `prompts/maid.txt` 派生头像与系统提示（人设 + Orbiter 工具契约），装备 `["orbiter", "kirara.trivia"]`。AWS 月租实例、单租户虚拟化、JRVS-390B、Niji 图像生成均如实标注为规划。
- **JRVS 触发词双路径与评测**：`.simchat/jrvs-orbiter/` 记录并实测两条激活路径——派生本地标签 `jrvs-kirara`（Modelfile `SYSTEM "Kirara"`）与 HTTP 显式 system；3×6 重复触发强度 A 88.9%、B 94.4%、C 100%、D 88.9%，协议叠加不削弱触发词。30 条用例总分 21~23/30，delegation 仅 1~2/6；寒暄前缀、代码块包裹、`-prompt=` 等格式问题提示层无解，需 SFT。原版权重还把 `2^10` 答错、翻译题输出无关代码。新增 `KNOWN-ISSUES.md` 区分原版权重缺陷与需 SFT 解决的协议问题，训练/量化/评测链路一并入库；`ollama-models/` 测试缓存已加入 `.gitignore`。
- **物品栏文案与 MOD 分类融合**：`areYouUnderTrouble` 从「危险信号检测」改为「危机支持」，描述改为温和的陪伴式支持与求助渠道；物品栏把 Kirara 行为包自带方块保留在 MOD 段，其余 MOD 方块按能力语义并入自有分类，装备门禁不变。`readFile` 声明为「办公」，`webSearch` 与 `screenshotRecognition` 声明为「检索」，技能包按能力进入对应分类。
- **物品栏结构再调整**：技能包与自动化流程并入自有方块分类，同名方块只保留方块一份（技能包仍在「部署」页签启停）；自动化流程独立归入「自动化」类；MOD 能力段只保留 Kirara 自带方块。`index.html` 同步更新 `inventory.js` 缓存版本。
- **Kirara 地图 logo 修正**：地图头像统一为 `/static/sprites/logos/kirara.png`，不再引用编号头像资源。
- **启动探测改为加载动画**：`/api/providers` 探测期间输入区显示「正在探测服务商可用性…」与旋转指示，隐藏「配置服务商」按钮，探测结束（成功或失败）后再按实际结果渲染。
- **验证**：加载器实测 Kirara 包为 `loaded` 并产出 `kirara:kirara` 预设；临时数据目录中幂等同步、二次同步 0 变更、PUT/DELETE 均被只读保护拒绝、`reset` 后地图保留且默认实例重建；Flask 测试客户端 `/api/agents` 与 `/api/agent/tools` 确认 `orbiter` 已装备；`orbiter` 方块回归确认未装备被拒、审批拒绝返回 `denied=approval`。
- 文件：`.simchat/runtime/agent/tools.py`、`.simchat/runtime/agents.py`、`.simchat/runtime/core.py`、`.simchat/sdk/python/simchat_mod/__init__.py`、`.simchat/loader/`、`.simchat/spec/mod-manifest.schema.json`、`.simchat/web/`（`__init__.py`、`static/js/chat.js`、`static/js/inventory.js`、`static/css/chat.css`、`templates/index.html`）、`.simchat/jrvs-orbiter/`、`.simchat/mods/kirara/`（`manifest.json`、`python/`、`prompts/maid.txt`、`css/theme.css`、`docs/behavior-pack-design.md`）、`.simchat/docs/orbiter-scheduler-design.md`、`.gitignore`、`updates.md`

**2026-11-19** — 能力调用收口：移除 skills 元工具，三条宿主通路统一走方块注册表

- **移除 `skills` 元工具**：Agent 协议段、工具清单、注册与执行分支不再出现 `skills`；能力只能以方块（内建块或 MOD 声明的 ToolSpec）形式暴露，技能包要进入循环必须自己声明 ToolSpec。
- **工具名解析放开点号与横线**：`loop.py` 的 `TOOL_NAME_RE` 从 `[A-Za-z_]\w*` 改为 `[A-Za-z_][\w.-]*`，`mcp.xxx.yyy` 这类命名不再被截断；`BlockRegistry` 的大小写不敏感查找与内建同名保护保持不变。
- **flow 的 `skill:` 收口**：`executor._run_skill()` 不再调用 `loader.call_tool()`，改为经 `invoke_block()` 落到 `BLOCK_REGISTRY`；flow 自身的 `skill:` 步骤构成静态授权范围，Agent 触发时与该实例的 `equipped` 取交集，cron / event / manual 没有实例上下文时只允许声明过的方块；直接调用 `execute_step()` 且没有显式范围时 fail-closed。
- **SkillManager 收口**：`execute_skill()` / `_SkillProxy` / `get_skill()` / `list_all_skills()` / `auto_execute_skills()` 全部经 `invoke_block()`；无实例上下文只允许显式只读白名单 `realityCheck`、`areYouUnderTrouble`、`webSearch`、`readFile`、`screenshotRecognition`，写级/危险级方块一律拒绝。
- **内建 `web_search` 收口**：删除直接 import `skills/noic.webSearch/python/webSearch.py` 的代码，`web_search` 作为兼容别名转发到 MOD 方块 `webSearch`，实现只保留一份；返回内容变为 MOD 方块的 JSON。
- **行为变化**：`web_search` 现在依赖 `noic.webSearch` 已安装并加载，MOD 被禁用时会明确报错；SkillManager 不再能调任意 MOD 工具；Agent 触发 flow 时，flow 内的 `skill:` 方块也必须在该 Agent 的装备集合内。
- **验证**：用假 loader 注册 `webSearch` / `readFile` 后 23 项检查全部通过——未装备方块被拒且不触达 loader、写级方块无审批被拒、现有 daily digest 的 `skill:readFile` 正常、Agent 装备交集越权失败、直接 `execute_step()` fail-closed、facade 白名单与拒绝路径均符合预期；注册表仍为 12 个内建方块，`skills` 元工具没有回来。
- 文件：`.simchat/runtime/agent/tools.py`、`.simchat/runtime/agent/loop.py`、`.simchat/automation/executor.py`、`.simchat/automation/__init__.py`、`.simchat/loader/skill_manager_facade.py`、`.simchat/web/static/js/inventory.js`、`.simchat/docs/tutorials/07-manage-skills.md`、`updates.md`

**2026-11-17 下午** — 新增 Anthropic 协议服务商 + 物品栏卡片精简与悬停详情

- **Anthropic 协议接入**：新增 `AnthropicProvider`，按 Messages API（`POST /v1/messages`、`x-api-key` + `anthropic-version`）流式解析 `content_block_delta` 文本增量；自动把 history 里的 `system` 消息提取为顶层 `system` 字段，`api_base` 支持官方地址或任意兼容 `/v1/messages` 的端点（带不带 `/v1` 均可）。
- **设置页第三个服务商**：`provider_config` 新增 `detect_anthropic` / `save` / `test` / `discover_models` 分支——字段为 API Base（可选，留空用官方地址）、API Key、模型名称；模型列表通过 `GET /v1/models` 自动探测，连接测试用 `max_tokens=1` 的真实请求；复用 `verified_at` 缓存，预检超时不误杀刚测试通过的配置。
- **Auto Model 覆盖**：`REAL_PROVIDER_IDS` 与 `PROVIDER_RANK` 加入 `anthropic`（优先级 Ollama → OpenAI 兼容 → Anthropic），默认配置、`core._provider()` 分派、`/api/providers/discover` 白名单、服务商预设白名单与 `provider.anthropic` 方块标签同步放行。
- **前端发现联动**：`chat.js` 的 `discoverTriggers` 增加 `anthropic`，修改 API Base / Key 后自动触发模型探测；`index.html` 更新 `chat.js` 缓存版本。
- **物品栏卡片精简**：方块卡片只保留英文名与单行简介，原先的版本号、启用状态、Hooks 全部收进悬停浮窗；图标容器 34→56px、砖块图标 24→40px（仅作用于 `.inv-slot-icon`，不影响部署列表），卡片最小高度 96px。
- **悬停详情浮窗**：新增 `#inv-tooltip`，展示完整名称、描述、ID、版本、状态与 Hooks；随卡片位置自动左右翻转并限制在视口内，面板滚动或窗口缩放时自动隐藏，键盘 Tab 聚焦同样触发，关闭面板时清理。
- **验证**：`/api/providers` 返回 `auto / ollama / openai_compat / anthropic` 四项且 anthropic 含 3 个字段，首页渲染 200；Python 编译与 `chat.js` 语法检查通过。
- 文件：`.simchat/runtime/providers.py`、`.simchat/runtime/provider_config.py`、`.simchat/runtime/core.py`、`.simchat/runtime/ui_blocks.py`、`.simchat/web/__init__.py`、`.simchat/web/templates/index.html`、`.simchat/web/static/js/chat.js`、`.simchat/web/static/js/inventory.js`、`.simchat/web/static/css/inventory.css`、`updates.md`

**2026-11-17** — MOD ID 与显示名称分离：ID 收紧为字母/数字/下划线，Kirara 行为包并入 kirara

- **ID 规则收紧**：manifest `id` 从 `^[a-z0-9][a-z0-9._-]{2,63}$` 改为 `^[a-z0-9][a-z0-9_]{2,63}$`，只允许小写字母、数字与下划线；显示名称继续放 `name`，可含任意符号（如「Kirara行为包」）。schema 与 `loader/manifest.py` 同步，报错文案补上规则说明；registry schema 的 `mod_id` 一并收紧。
- **全局 ID 迁移**：`barry.galax → barry_galax`、`noic.skill-readfile → noic_skill_readfile`、`noic.skill-websearch → noic_skill_websearch`、`noic.skill-screenshotrecognition → noic_skill_screenshotrecognition`、`noic.skill-netrunner → noic_skill_netrunner`、`automation.daily-digest → automation_daily_digest`；manifest、registry 的 `mod_id`、`data/` 目录与文档示例全部同步。目录名不强制等于 id（运行中进程占用的 `skills/noic.*` 目录保持原名），启动接口一律以 manifest `id` 为准。
- **agent-config-minimal 并入 kirara**：删除独立样例，`mods/kirara/manifest.json` 以 `id=kirara_agent_config`、`name=Kirara行为包` 加载；女仆人设 `prompts/maid.txt`、主题 `css/theme.css` 随包分发，主题选择器改为 `kirara_agent_config-theme`，与前端按 id 注入的 body class 对齐；registry 条目同步替换为 `mods/kirara`。
- **CLI init 分离 ID 与名称**：`cli init` 原来把 `--name` 当 id，现拆成必填 `--id` 与可选 `--name`（显示名）；id 不合法直接拒绝，默认输出目录改为 `./<id>`；模板占位 id 改为下划线形式，`$schema` 相对路径修正为 `../../spec/mod-manifest.schema.json`。
- **示例与文档**：`examples/skill-hello`、`examples/automation-daily-digest` 的 id 改为下划线；README 与 tutorials 08/10/11/12 的 init 命令、示例路径、registry 片段同步更新，并修掉 README 阶段进度表里丢失的换行。
- **验证**：全部 manifest（含 examples）通过 Draft 2020-12 校验，registry 通过 registry schema；loader 实测 6/7 loaded（`automation_daily_digest` 在未启动 AutomationEngine 的独立扫描中按预期失败，Web 启动链路正常）。
- 文件：`.simchat/loader/manifest.py`、`.simchat/loader/index.py`、`.simchat/spec/mod-manifest.schema.json`、`.simchat/spec/registry.schema.json`、`.simchat/cli/main.py`、`.simchat/registry/index.json`、`.simchat/mods/kirara/`（新增 manifest / prompts / css/theme.css）、`.simchat/mods/agent-config-minimal/`（删除）、`.simchat/skills/`（id 迁移 + automation 目录改名）、`.simchat/examples/`、`.simchat/ide-demo.html`、`.simchat/docs/tutorials/`、`README.md`、`updates.md`

**2026-11-16 下午** — 运行时可靠性：工具名归一、参数校验层、automation 全链接线、原子能力物品栏

- **工具名大小写不敏感**：`BlockRegistry` 新增小写索引 `_ci`，`register()` 按小写去重并保护内建方块不被 MOD 覆盖，`get()/has()` 精确命中失败后回退小写匹配；`loop.py` 命中后把 `call['tool']` 回写成 canonical 名。修掉 `realityCheck` / `webSearch` 这类 camelCase 调用永远解析不到的问题，MOD 工具也一并受益。
- **MOD 工具元数据完整透传**：`lifecycle.py` 新增 `_safe_tool_meta()`，只保留 `name/label/description/risk/usage/params_schema/backend/triggers/input_schema` 九个已知字段并做 JSON 往返清洗；`risk` 缺失保持 `read`，声明了非法值则保守降为 `write`，避免写操作静默绕过审批。此前只写 `{name,label}`，导致描述为空、写级被当成只读。
- **失败包可见**：`discover()` 外层异常改为 `_record_crash()` 落一条 `failed` 记录（同构字段 + 按 `path` 去重、id 冲突退化键名），单个包崩溃既不中断扫描，也不会从 `list_mods()` 里凭空消失。
- **解析失败回灌**：`loop.py` 的 `_parse_tool_line()` 在「写了 PARAMS 但解析不出对象」时产出 `parse_error`，`_process_turn_calls()` 直接回灌 `tool_result(ok=False)` 并跳过执行；没写 PARAMS 仍按空参处理，两种语义不再混淆。
- **usage 示例合法化**：`file_read` 的 `offset`、`web_search` 的 `max_results`、`shell` 的 `timeout` 三处 `PARAMS` 示例改成合法 JSON，中文说明保留在 description 里，模型照抄不再产出坏 JSON。
- **`skills` 接入 chat 模式**：原来 chat 清单里只有一条伪条目，现在 `SkillsTool` 无 `name` 时实时列 `loader.list_tools()` 清单，带 `name` 时直接调只读 skill；写级 skill 拒绝并指回「Agent 模式同名工具 + 审批」路径。清单动态取，不硬编码。
- **automation 全链**：`create_app` 通过 `_ensure_automation_engine()` 幂等启动 `AutomationEngine`（`atexit` 关闭、失败只记日志不拖垮 Web），`_LazyCore` 代理让 `agent:run` 首次执行时才取 core；loader 新增 automation 分支，读 manifest 的 `automation.flow_file` 后 `engine.register_flow()` 并回查确认，异常沿用 `_fail`/crash 隔离；`chat` 的 automation 伪条目换成真工具——`automation`（read：`list`/`runs`）与 `automation_trigger`（write：走审批）拆成两个方块；引擎侧补 `trigger_flow()`、`list_runs()` 与最近 20 条内存运行记录，所有 `_run_flow` 出口都落一条摘要。
- **MCP 文案如实化**：提示词里「可连接 MCP 服务器」改成明确「运行时未实现、不可调用」，agent/chat 两处口径一致，条目保留不删。
- **`HOST_VERSION` 单一来源**：新增叶子模块 `loader/version.py`（`HOST_VERSION = "2.3.0"`），`ModLoader` 默认参数与 `web/__init__.py` 的 `_MODS_HOST_VERSION` 都引用它，修掉「Web 启动能装、脚本直接 `new ModLoader` 判失败」的错位；依赖方向保持单向（web → loader，无反向 import）。
- **参数校验层**：13 个内建方块逐个声明 `params_schema`（必填/可选/类型，按实现里真正会报错的参数定），新增 `validate_tool_params()` 支持内建字段字典、MOD JSON Schema、简写类型三种形态；执行前校验，缺必填或类型明显不符则回灌「缺哪个字段、期望什么类型、重试格式」并且**不执行**；审批通过后、执行前再校验一次（允许审批时改参）；无名约束的 MOD 工具直接放行，`parse_error` 路径保持优先不被覆盖。
- **`WebSearchTool` 路径修正**：skill 加载路径从 `mods/noic.webSearch/python` 改为 `skills/noic.webSearch/python`，并加目录/入口文件存在性判断——缺失时报「web_search 技能未安装：缺少 …」，与「已找到但加载失败」区分，不再把 `ImportError` 丢给模型去猜。实测合法参数可真实返回搜索结果。
- **W-Synk 预设禁用（前端）**：`chat.js` 新增 `ENGINE_PRESET_UNAVAILABLE` 表与 `selectEnginePreset` 硬拦截，卡片灰显并挂「暂不可用」徽标；`chat.css` 补禁用态与 `.agent-engine-badge` 样式。实现保留，只是入口不可选。
- **原子能力物品栏（前端）**：新增 `inventory.js` / `inventory.css`，`index.html` 引入并加面板结构；分类为技能 / 自动化 / MCP / CoT / Orbiter，技能与自动化走 `/api/console/skills`、`/api/console/automation` 实时数据，MCP、CoT、Orbiter 三类如实显示「运行时未接入」空态，另带搜索与部署两个选项卡。
- **header 快捷键入口（前端）**：`index.html` 导航区新增「物品栏 (I)」「AI 实例 (E)」「网关 (G)」「MOD 菜单 (M)」「设置 (C)」入口与按键提示，新增 `nav-shortcuts.js`（E/G/M/C/I 开关、Esc 兜底、关闭后焦点还原、输入态不劫持），`chat.js` 暴露 `SimChatPanels` 供其复用面板开关，`chat.css` 加 `.nav-btn-key` 样式。
- 文件：`.simchat/runtime/agent/tools.py`、`.simchat/runtime/agent/loop.py`、`.simchat/loader/lifecycle.py`、`.simchat/loader/version.py`（新增）、`.simchat/automation/__init__.py`、`.simchat/web/__init__.py`、`.simchat/web/templates/index.html`、`.simchat/web/static/js/chat.js`、`.simchat/web/static/js/inventory.js`（新增）、`.simchat/web/static/js/nav-shortcuts.js`（新增）、`.simchat/web/static/css/chat.css`、`.simchat/web/static/css/inventory.css`（新增）、`updates.md`

**2026-11-16** — IDE 顶栏三分区重构 + 启动器崩溃报告落盘

- **顶栏（menubar）重排**：原来「品牌 + 菜单 + 居中标题」的简单结构改成左 / 中 / 右三段——左侧品牌与 File·Edit·View·Run·Terminal·Help 菜单，中间是搜索框（点击或 Enter 唤起 Ctrl+K 命令面板）、撤销 / 重做按钮、以及侧栏 / 底部面板 / 右侧 AI 面板三个开关，右侧是 Agent 跳转按钮、设置入口与用户头像块。原先绝对居中的 `menubar-title` 被 `.mb-center` 取代，旧样式改为 `display:none` 保留兼容。
- **开关按钮有状态**：新增 `updateHeaderToggleState()`，把 `body[data-sidebar|data-inspector|data-panel]` 的展开状态同步成按钮 `data-active`，`toggleSidebar / toggleInspector / togglePanel` 每次切换后刷新，初始化时也跑一次，避免按钮高亮与实际面板状态脱节。
- **响应式补丁**：1280px 以下搜索框收窄、隐藏用户名；960px 以下再隐藏分隔线、撤销重做组与 `Ctrl+P` 提示，保证顶栏在窄屏不换行、不溢出。
- **启动器崩溃报告**：`.simchatLc/launcher.cpp` 新增 `write_crash_report()`，在服务进程启动阶段退出（`start_server` 子进程非预期结束时）和控制台模式退出码非 0 时，把退出码、退出时间、根目录与原因追加写入 `.simchat/crash_reports/exit_<code>_<时间戳>.txt`，非 Windows 平台留空实现。此前这类退出只打一行日志，关掉窗口就查不到了。
- 文件：`.simchat/web/templates/ide.html`、`.simchat/web/static/css/ide.css`、`.simchat/web/static/js/ide.js`、`.simchatLc/launcher.cpp`、`updates.md`

**2026-11-15** — MOD 体系可用性修复：宿主接线、`skills/` 分层、安全能力内建、P2 隔离闸门

- **MOD 终于真的被加载**：`create_app()` 启动进程级 `ModLoader`（`discover()` + `set_global_loader()`，`atexit` 统一清理），已加载包的工具经 `ModToolBlock` / `sync_loader_blocks()` 同步进 `BLOCK_REGISTRY`；`/mods/<id>/<path>` 路由改为包内导入 `get_loader`，越界校验换成 `realpath + commonpath`。此前 6 个包在磁盘上但从未进入运行时，Agent 无法调用。
- **协议卫生**：runner 的所有协议输出加私有前缀 `@@simchat-ipc@@`，宿主只消费带前缀的行；MOD 在 entry 阶段 `print()` 不再顶掉 `register` 首行（原会被判「沙箱输出格式非法」），转而写入宿主 stderr。
- **`mods/` 与 `skills/` 分层**：新增 `.simchat/skills/`（`noic.readFile` / `webSearch` / `screenshotRecognition` / `barry.galax` / `automation.daily-digest`），`mods/` 只留真正的 MOD（`agent-config-minimal`）；`ModLoader` 支持 `extra_dirs` 一次扫描两处，`/api/console/mods` 与 `/api/console/skills` 接口分开，新增 `/api/console/skills/<id>/toggle`（状态独立落在 `skills/.simchat_state.json`）；上传目录固定为 `.simchat/uploads`。
- **安全能力内建**：`realityCheck` / `areYouUnderTrouble` 从可停用的 skill 包迁入 `runtime/safety/` 并注册为原生方块，不再经过验签、沙箱与开关；对应 registry 条目删除。
- **P1 资产与服务语义**：MOD 子进程 `cwd` 切到包目录，`scripts/` 注入 `sys.path`，`assets.root` 可通过 `api.assets_dir` 访问；所有 layer 都分配 `data_dir`（`data/mods/<id>` / `data/blocks/<id>`）；runner 复用 SDK `ModApi`，补齐 `service` / `has_capability` / `capabilities` / `emit_event`，宿主服务（`inference`、`skill_manager`）经 IPC 回调真实可用；`register_mode` 不再丢 `description` / `requires_capabilities`，dict 注册 tool 会走 SDK 默认值。
- **`barry.galax` 恢复**：包内容未改，仅用 `dev-keys/official.ed25519.pem` 对当前 `build_signing_payload(manifest, integrity)` 重新签名，`verify_package=True`，四阶段输出与实时检索召回实测通过。
- **P2 invoke 并发**：宿主侧引入 per-request future（`request_id → 独立队列`），stdout 读线程按 `request_id` 投递、按 `type + mode/tool` 兜底，超时/进程退出会注销或唤醒等待者；`service_call` 改独立线程执行，慢推理不再阻塞协议读取。runner 仍单线程执行，但并发调用不再串包。
- **P2 capabilities 执行层**：`capabilities.fs` 变成真正的白名单——基础可访问仅包目录（读）、`data_dir` 与 `uploads`（读写）、解释器/site-packages（只读），scope 支持 `workspace` / `mod-data` / `package` / `uploads` / `temp` / 绝对与相对子路径，覆盖 `open`、`io.open`、`os.open`（按 flags 判读写）、`remove/unlink/mkdir/makedirs/rename/replace`、`listdir/scandir`；`capabilities.net` 未声明时拒绝所有 `getaddrinfo`，支持精确域名、`*.example.com` 与 `*`，`connect/connect_ex` 只放行已解析或声明的 IP。补丁函数用非描述符包装，修掉 `pathlib._NormalAccessor.open = os.open` 把函数绑定成方法导致的 `screenshotRecognition` 加载失败。
- **schema 与实现同步**：`abi` 改为 `enum[simchat-mod/2, lmbrew-mod/1]`，新增 `layer`，hooks 补 `agent.block` / `agent.completed` / `web.blueprint`（保留 `agent.tool`），`entry` 允许 automation 指向包内 `*.json`，`requires` 补 `simchat`，`automation` 必填改为 `flow_file`，`capabilities.fs` 描述与实现对齐；8 个真实 manifest 全部通过 Draft 2020-12 校验。
- **界面语义**：IDE 侧栏分区改为「方块 / MOD」，控制台区分 MOD 与技能方块并支持技能启停，摘要文案按 `MOD / 技能 / 工具` 分别计数。
- **验证**：6/6 包 loaded（mods 1 + skills 5）；`BLOCK_REGISTRY` 13 个（10 内建 + 3 技能工具）；合成 MOD 25/25 PASS（并发无串包、未声明 fs 读写/list 全拒绝、声明式 fs/net 放行、未声明域名拒绝）；`readFile` 读 uploads 正常、越界读取被拒；`webSearch` 外连正常；`/api/console/mods`、`/api/console/skills`、`/api/agent/tools` 均 200。
- 文件：`.simchat/loader/lifecycle.py`、`.simchat/loader/sandbox.py`、`.simchat/loader/sandbox_runner.py`、`.simchat/loader/sandbox_contract.md`、`.simchat/runtime/agent/tools.py`、`.simchat/runtime/safety/`（新增）、`.simchat/runtime/mods_index.py`、`.simchat/sdk/python/simchat_mod/__init__.py`、`.simchat/spec/mod-manifest.schema.json`、`.simchat/web/__init__.py`、`.simchat/web/static/js/chat.js`、`.simchat/web/static/js/ide.js`、`.simchat/skills/`（新增）、`.simchat/mods/`（清理）、`.simchat/registry/index.json`、`.simchat/docs/mod-availability-diagnosis.md`（新增）、`README.md`、`updates.md`

**2026-11-13** — 目录重构：本体收进 `.simchat/`，启动入口统一为 `scripts/entry.py`

- **目录拆分**：为了给原生启动器腾出仓库根目录，Python 本体整体迁入 `.simchat/`（`web` / `runtime` / `loader` / `automation` / `cli` / `spec` / `mods` / `docs` / `sdk` / `scripts` 等），仓库根只保留 `README.md` / `updates.md` / `tidbit.md` / `.gitignore` / `launcher.cpp` / `.simchatLc/`。
- **新启动入口**：`.simchat` 目录名带点，不能被 `import simchat` 找到，新增 `scripts/entry.py` 把自身以 `simchat` 之名注册进 `sys.modules`，再转入原入口：`python .simchat/scripts/entry.py web|cli|lifecycle ...`。
- **启动脚本适配**：`run.ps1` / `run.bat` / `run.sh` / `run-harmony.sh` 的路径推导从「仓库根」改为「`.simchat/scripts` 的上一级」，工作目录切到包根，删掉手工注入的 `PYTHONPATH`；`deploy_daemon.sh` 生成的 systemd 单元 `WorkingDirectory` / `ExecStart` 同步改写，`README.md` 的文档路径指向仓库根。
- **守护与自启链路**：`runtime/lifecycle.py` 里 `-m simchat.web` / `-m simchat.runtime.lifecycle` 的子进程拉起、HKCU Run 包装脚本、macOS LaunchAgent、XDG desktop 全部改走 `scripts/entry.py`——不改的话「自动拉起」会拉起一个立刻退出的死进程。
- **换行修复**：`run.sh` / `run-harmony.sh` 在搬迁过程中被写成 CRLF，bash 直接报 `syntax error near unexpected token 'do\r'`，已统一转回 LF。
- **gitignore 修补**：`mods/uploads/`、`mods/.simchat_state.json` 这类含斜杠的规则锚定仓库根，搬迁后失效，改成 `**/mods/...`；Ollama 离线包（`ollama-*.tgz`，约 21MB）排除出版本控制。
- **文档同步**：`README.md` 快速开始、`docs/api-endpoints.md`、`harmony-webview/README.md`、`Index.ets` 提示文案、CLI 与 `--help` 的输出里的 `python -m simchat.*` 全部改为 `python .simchat/scripts/entry.py ...`。
- **启动器工程落位**：仓库根新增 `launcher.cpp`，`.simchatLc/` 放 `_includes/Compile.h`、`process.h` 两个占位头与 `readme.md`；确定 CMake 构建、启动器只负责「找解释器 → 起本体 → 建窗口」的契约。
- 文件：`scripts/entry.py`（新增）、`scripts/run.ps1`、`scripts/run.bat`、`scripts/run.sh`、`scripts/run-harmony.sh`、`scripts/deploy_daemon.sh`、`runtime/lifecycle.py`、`cli/main.py`、`cli/__main__.py`、`web/__main__.py`、`web/__init__.py`、`.gitignore`、`README.md`、`docs/api-endpoints.md`、`harmony-webview/*`、`launcher.cpp`（新增）、`.simchatLc/readme.md`（新增）、`updates.md`

**2026-11-11** — IDE 对话移到右侧 + 顶部菜单栏

- **对话迁到视口右侧**：原来塞在底部 Panel 的 Chat Tab 整体搬到右侧 Inspector 栏，与「检查器」组成双 Tab 面板（对话 / 检查器），底部 Panel 只保留控制台（事件流 / 沙箱输出 / 日志）。选择会话、新建会话、以及 Agent 请求审批时自动切到对应 Tab 并展开右栏。
- **顶部菜单栏**：新增 35px 高的 VSCode 风格菜单栏（File / Edit / View / Run / Terminal / Help），下拉项覆盖新建会话、刷新文件树、选择工作目录、关闭编辑器、清空各类日志、六个 Activity 视图、侧栏 / 右侧面板 / 底部面板开关、对话与 Agent 模式切换、审批操作与审批策略、面板 Tab 切换、快捷键与关于。支持点击展开、悬停切换菜单、点击外部或 Esc 关闭，下拉项带快捷键提示、禁用态与勾选态；菜单栏中央显示当前工作目录。
- **布局与快捷键**：网格新增顶栏行，`Ctrl+I` 控制右侧对话栏、`Ctrl+J` 控制底部控制台、`Ctrl+Shift+N` 新建会话；窗口标题与状态栏文案同步更新，窄屏断点整体下移 35px 适配。
- 文件：`web/templates/ide.html`、`web/static/css/ide.css`、`web/static/js/ide.js`、`updates.md`

**2026-11-10 下午** — IDE VSCode 风格重构：中央固定编辑器，对话降级到底部 Panel

- **布局重定向**：中央区从「随 Activity Bar 切换的五视图」改成**永远是标签页 + 代码编辑器**（`.workspace > .editor-tabs + .editor-surface`），不再按 activity 切换中央 DOM。Activity Bar 首位换成 Explorer（资源管理器），其余五键 Search / Agent / Extensions / Debug / Settings。
- **对话移到底部 Chat Panel**：原来在中央 view 的对话渲染链路全部搬到 `#panel-chat-messages` + `#panel-composer`，composer 事件绑定从 `#composer-input` 换成 `#panel-composer`，Ctrl+Enter 发送；工作目录锁定横幅也挪到 Panel Chat Tab 内。
- **文件树**：Explorer activity 下 Side Bar 显示文件树（目录箭头折叠/展开、文件图标按扩展名着色），点击文件 → 中央开标签页 + 真实内容。
- **后端新增 `/api/workspace/read`**：工作区内文本文件读取端点（`runtime/workspace.read_file`）。扩展名白名单 45 种（py/js/ts/tsx/html/css/md/json/yaml/toml…），512KB 上限，编码自动尝试 utf-8 → gbk → utf-16 → latin-1。之前前端 openFile 里的 placeholder 假内容全部移除。
- **旧代码清理**：`renderChat` / `renderTasks` / `renderExt` / `renderSettings` 四个 view 入口函数全部删除；`setActivity` 里的 `$$(".view")` 切换逻辑删除；快捷键映射从 `1=chat/2=tasks/3=ext/4=automation` 改成 `1=explorer/2=search/3=agent/4=extensions/5=debug/6=settings`。
- **Inspector 跟随 activity 切换**：Explorer 显示工作目录 + 编辑器概览；Agent 显示当前会话 + ReAct 时间线；Extensions 显示 MOD/工具统计；Settings 显示当前模式 + 子 section 详情。
- **编辑器语法高亮暂未接入**：Monaco 或轻量 highlighter 是下一步，但布局和数据链路已经通了。
- 文件：`runtime/workspace.py`（新增 `read_file`）、`runtime/core.py`（新增 `read_workspace_file`）、`web/__init__.py`（新增 `/api/workspace/read`）、`web/templates/ide.html`（重写中央区 + body 默认属性）、`web/static/css/ide.css`（追加 200+ 行 VSCode 风格样式：标签栏、文件树、Chat Panel）、`web/static/js/ide-api.js`（新增 `readWorkspaceFile`）、`web/static/js/ide.js`（完整重写 1180 行）

**2026-11-10** — IDE 六区布局 + WAP 移动端独立落地（毛坯房地基）

- **桌面端 `/ide` 页面**：从 ide-demo.html 拆出独立 Flask 模板 `web/templates/ide.html`，不再是单文件 HTML 被读原文返回。完整六区布局（Activity Bar / Side Bar / 中央工作区 / Inspector / 底部 Panel / 状态栏），全部接真实 `/api/*`：会话列表、新建会话、流式对话（SSE）、Agent 任务与审批、MOD/工具、服务商模型列表、工作目录浏览选择器。Activity Bar 5 个 Tab（对话 / 任务 / 扩展 / 自动化 / 设置），底部 Panel 三 Tab（事件流 / 沙箱输出 / 日志），Inspector 自动跟随当前上下文刷新。快捷键：Ctrl+1~4 切 Activity、Ctrl+B 抽屉、Ctrl+J Panel、Ctrl+I Inspector、Ctrl+, 设置、Ctrl+K 命令面板、Esc 收起所有浮层。
- **移动端 `/wap` 页面**：全新单列堆栈壳（max-width 520px，safe-area-inset-bottom 适配），底部 TabBar 三 Tab（对话 / 任务 / 我的），会话列表空态带品牌欢迎卡，对话页走同一条 `/api/chat` SSE，工作目录未配置时 composer 自动锁定并提示。
- **无弹层**：移动端所有交互（模型切换 / 主题切换 / 工作目录选择）全部用「我的页内联展开选项组」或「独立 route（ws-picker）」完成，没有任何 bottom sheet 或 backdrop 覆盖层。路由 history 用 `state.routeStack` 维护，back 按钮回到上一层。
- **Splash Screen**：全屏启动画面，并行拉 listSessions / listProviders / listAgentTasks / getWorkspace 四个 API，进度条逐阶段推进，4s 超时保护，全部完成后淡出显示主壳。带 logo 旋转缩放入场动画 + 标题 + 加载文案 + 「跳过」按钮（1.2s 后出现）。
- **共享层**：`web/static/js/ide-api.js` 作为 fetch + SSE 封装层被 IDE 和 WAP 共用，所有请求显式 `Content-Type: application/json`；`ide.css` 提供设计令牌 + 桌面六区布局样式，`wap.css` `@import` 拿令牌后覆写移动端壳；两端数据层完全独立，不污染 `index.html` 的 DOM。
- **ide-demo.html 保留在项目根目录**：它是最初的设计稿，里面的 CSS/JS 被拆到 `static/css/ide.css` 和 `static/js/ide.js` 后不再由 Flask 路由，留作参考。
- 文件：`web/__init__.py`（路由改为 render_template + 新增 /wap）、`web/templates/ide.html`（新增）、`web/templates/wap.html`（新增）、`web/static/css/ide.css`（新增）、`web/static/css/wap.css`（新增）、`web/static/js/ide-api.js`（新增）、`web/static/js/ide.js`（新增）、`web/static/js/wap.js`（新增）、`ide-demo.html`（保留不删）、`docs/kirara-reboot-investigation.md`（新增调研）、`updates.md`

**2026-11-09 夜** — Orbiter 落地：composer 里的 AI 实例下拉

- 占位了很久的 Orbiter 按钮（`.agent-only`）正式变成了 `<select id="agent-picker">`。选项列表：`— 直接对话 —` + 每个 AI 实例的头像 emoji + 名称；非 Agent 模式的实例后缀 `（对话）`。
- 选中即激活实例：写入 `state.activeAgentId` / `localStorage.simchat.active_agent_id` / `state2.selectedAgentId`，composer 里的 `/api/chat` 请求自动带上 `agent_id`，前端 SSE 渲染和后端 Agent 模式一起联动；选回空值则回到"直接对话"（不带实例）。
- 双向同步：agent-list 浮层里点「激活」会反向刷新 picker；picker 里选了也会刷新 agent-list 高亮。`loadAgents` / 新建 / 删除 / 更新实例后都重绘。
- 文案替代：以前要手敲 `/@gremlin`，现在点一下就行。未来如果要加 Orbiter 路由器（"轻量大模型做路由"那个混合推理架构），可以在这个下拉旁边加一个模式切换，但**实例选择这个核心已经解决了**。
- 文件：`web/templates/index.html`、`web/static/js/chat.js`

**2026-11-09 晚** — Agent 模式终于接通 AgentLoop

- **根因**：`/api/chat` handler 从来没读 `agent.agent_capable`，所有带 AI 实例的对话都走 `core.chat_stream` 普通聊天流，后端已实现好的 `runtime/agent/` 包（AgentLoop + SimChatAgentBackend + ReAct 协议 + 工具集）一直是死代码。用户截图里 `/@gremlin 你好吗` 返回的是模型自由发挥的闲聊而不是工具调用，直接命中这个根因。
- **修复**：`web/__init__.py` chat handler 新增 agent_capable 分支，构造 SimChatAgentBackend（复用 engine_params 的温度 / Top-P / 重复惩罚 / max_tokens，复用 SimChatCore 的服务商解析）+ AgentLoop（mode="agent"，workdir 取 workspace_status().path，shell 暂关闭），loop.run() 同步跑 ReAct 循环，emit 回调把事件收集到 list，再逐条 SSE 发出。
- **配套**：新增 `_agent_mod()` 懒加载函数；Agent 会话用 `mode="agent"` 隔离，不复用普通 chat 会话；quota 硬闸在进 AgentLoop 前先做一次。
- **修复 Gateway 握手 JSON 丢失**（上一次表单修复里的同类问题）。
- 实测：gremlin 实例（agent_capable=True）打 `/api/chat` 带 agent_id，正确发出 `chat_started / thought / final` 事件，session mode 正确落盘为 "agent"。
- 文件：`web/__init__.py`、`updates.md`、`README.md`

**2026-11-09** — AI 实例后台创建浮层 + 表单提交修复

- **实例创建改为后台执行**：点「保存」后弹窗立即关闭，视口右上角出现进度浮层（`#agent-boot-stack`），包含实例头像 / 名称 / 放弃按钮，以及「加载模型中 / 生成神经网络中」两行文案与进度条。进度先缓慢逼近 92%，接口返回后仍保留约 1.3 秒可读时间，再平滑补到 100%，最后卡片向右飞出视口并淡出。
- **放弃即回滚**：创建途中点「放弃」，卡片立即飞出；实例已落盘则自动 `DELETE` 删除，请求仍在途则等返回后立刻删除，列表不残留半成品。
- **失败回退**：创建失败时浮层收起，编辑弹窗重新打开并保留已填内容，错误信息显示在原位置。
- **修复 Agent 表单提交失败**：`/api/agents` 的新建与编辑请求漏了 `Content-Type: application/json`，Flask 的 `request.get_json(silent=True)` 拿到空 payload，导致名称明明填了却报「名称不能为空」、编辑保存也静默失效。同时修复 `/api/gateway/connect` 的同一问题。
- **表单体验**：实例表单整体及所有输入框加 `autocomplete="off"`，浏览器不再弹出历史输入建议；一开始输入就清除上次的校验提示，校验失败自动聚焦名称框。
- **移除 `seed` 字段**：该字段只存不读（`synapse-notes.md` 早有记录），从前端表单与提交 payload 移除，后端 `agents.py` 保留 `setdefault` 兜底旧存档；`docs/ai-instance-engine-presets.md`、`docs/architecture-recap.md`、`docs/synapse-notes.md` 同步更新。
- 文件：`web/templates/index.html`、`web/static/js/chat.js`、`web/static/css/chat.css`、`docs/ai-instance-engine-presets.md`、`docs/architecture-recap.md`、`docs/synapse-notes.md`

**2026-11-03** — Token 用量统计 + 额度限制（从 kirara 迁移）

- **每日 token 用量统计（后端持久化）**：新增 `runtime/usage.py`（`UsageTracker`），按 YYYY-MM-DD 记录 input/output tokens 与会话次数，存 `data/usage.json`，线程安全 + 文件级原子写入。`chat_stream()` 和 `agent_run()` 入口结束后自动累加用量。
- **后端 quota 硬闸**：`settings.json` 的 `quota.limit` 字段控制每日上限（0 = 不限额，默认）；`chat_stream` / `agent_run` 入口各有一次硬闸检查，超限返回 `code: quota_exceeded`（对话模式走 SSE error 事件、Agent 模式返回 HTTP 429）。支持锁定（`quota.lock=true` → 后端 403 拒绝修改）。
- **前端本地每日统计（localStorage）**：`web/static/js/chat.js` 内置 `utReadAll()` / `recordDailyUsage()` / `utIsLimitExceeded()`，对话模式和 Agent 模式结束时各自结算，前端 `sendMessage` 入口做硬闸拦截（`updateQuotaUI()` 驱动超限横幅 + 进度条更新）。前后端双保险。
- **Agent token 徽章 + 压缩提示渲染**：此前后端 AgentLoop 已 emit `token_usage` / `compaction` 事件，但前端静默丢弃；现在每次 `token_usage` 累加 prompt/completion tokens 并更新卡片头部徽章（按使用比例显示 ok/warn/critical 三级 + 颜色 + 临界态呼吸动画），`compaction` 事件渲染紫色提示卡片展示压缩前后条数和 token 变化。
- **每日用量 UI**：composer 上方新增红色超限横幅（sticky），token-bar 下方新增每日用量进度条（跟随 token-bar 一起显隐、按使用比例变色），两者均硬编码在 `index.html`（非动态注入），首屏无闪烁。
- **高级功能 → 使用情况面板接入**：原先占位的「该模块尚未接入」section 被替换为完整面板——4 张统计卡（今日总计 / 输入 / 输出 / 会话数）、近 7 天条形图（今天蓝色高亮、hover 显示 token 数）、额度限制配置卡（启用开关 + 限额输入 + 日/月周期选择 + 锁定开关 + 保存/重置按钮 + 后端保存失败时静默降级到 localStorage）。新增 3 个后端 API：`GET /api/console/usage`、`POST /api/console/usage/quota`、`POST /api/console/usage/reset-today`。
- 文件：`runtime/usage.py`（新增）、`runtime/core.py`、`web/__init__.py`、`web/agent.py`、`web/templates/index.html`、`web/static/js/chat.js`、`web/static/css/chat.css`

**2026-11-01** — 群机器人：OneBot v11 与 QQ 官方 API 双接入（真实收发）

- 设置控制台新增「群机器人」分组，两种接入方式**按钮分开**：`Python 库（OneBot v11）` 与 `QQ 官方 API`，各自有独立的启动 / 停止 / 测试连接 / 测试发送与运行面板（连接方式、收发计数、最近错误、Webhook 回调地址一键复制、最近活跃群点选）。
- **OneBot v11**：正向 WebSocket（断线指数退避重连）或 HTTP 反向 Webhook 收消息；`get_login_info` 做连通性自检，`send_group_msg` 发送；支持群白名单、必须 @、前缀触发。
- **QQ 官方 API**：`getAppAccessToken` + Gateway WebSocket（Hello / Identify / 心跳 / 重连）或 Webhook（Ed25519 验签 + op13 回调校验）；群消息走 `/v2/groups/{openid}/messages`，单聊（C2C）走 `/v2/users/{openid}/messages`，被动回复携带 `msg_id` / `msg_seq`。
- 群消息进入 `SimChatCore.chat_stream()` 生成回复，以 `im-<mode>-<会话>` 隔离上下文：按消息 ID 去重、每会话串行、两个 QQ 通道互斥；外部文本按不可信输入处理（截断 + 安全约束）。
- 每个通道可独立指定「模型服务商 / 模型」，自动回复、白名单、触发规则、系统提示词均**实时读取**，保存即生效；AccessToken / AppSecret 等敏感字段 Fernet 加密，前端只回显掩码。
- 文件：`runtime/im_bots.py`、`runtime/comms.py`、`web/__init__.py`、`web/static/js/chat.js`、`web/static/css/settings.css`、`web/templates/index.html`、`scripts/requirements-simchat.txt`（新增 `websocket-client>=1.6.0`）

**2026-10-31** — 工作目录门禁 + 个人中心 + Agent 会话落盘修复

- **工作目录（workspace）成为对话与 Agent 的统一根目录**：未选择目录时 composer 只读锁定、发送被拦截并提示；顶栏 chip、欢迎页、侧栏均可重新配置；新增目录浏览选择器（逐级浏览 + 直接输入绝对路径），配置写入 `data/config.json`，Agent 沙箱的 `workdir` 随之切换。
- **个人中心**：侧栏用户卡可点击进入设置页，支持用户名、生日、紧急联系人、头像（PNG / JPEG / WEBP / GIF，前端自动压缩到 256px），档案只存本机 `data/profile.json`。
- **Agent 模式会话落盘修复**：`SessionStore.get_or_create()` 之前会忽略传入的 `agent_` 会话 id 并另建随机会话文件，导致 Agent 消息全部落空；现在按显式 id 建会话并正常写入，Agent 多轮对话会自动续接已落盘历史。
- **会话模式标识符**：会话记录新增 `mode` 字段（`chat` / `agent`），Agent 会话固定 `agent_` 前缀；侧栏用「对话 / Agent」标签区分，打开会话自动切回对应模式，两种模式的上下文互不污染。
- **启动恢复失败静默回退**：上次会话已被删除或旧版本未落盘时，刷新页面不再把「加载会话失败：会话不存在」渲染成助手消息，而是静默清理记录并回到新对话。
- **IDE 界面演示页**：新增 `/ide` 单文件六区布局演示（`ide-demo.html`，无外链、无后端依赖），与 `/` 对话界面共用同一套 `/api/*`。
- 文件：`runtime/workspace.py`、`runtime/store.py`、`runtime/agent/`、`web/agent.py`、`web/__init__.py`、`web/static/js/chat.js`、`web/static/css/chat.css`、`web/templates/index.html`、`ide-demo.html`

**2026-10-29** — Web UI 多 provider 聚合 + 下拉交互修复 + OpenAI 预检强化

- **模型下拉聚合所有 provider**：composer 里的模型选择器不再只显示 resolved 那一个 provider 的模型，而是用 `<optgroup>` 按 provider 分组列出所有已发现的模型（Ollama 本地 + OpenAI 兼容 + 未来其他）。切换模型时 provider 跟着走，请求 payload 同时带 `provider` 和 `model`。
- **下拉菜单 hover 白字修复**：原生 `<select>` 在 Windows 上 `background: transparent` 会导致弹出面板的 option hover 时白底白字。加了全局 `select option` 明确兜底 `background-color` + `color`，深色模式独立适配。
- **模型提供商存档固化**：新增 `providerStore` 模块（`window.SimChatProviderStore`），把后端返回的 providers + models 缓存到 `localStorage`（10 分钟过期）。刷新页面后模型下拉立即有数据，不用等后端重新 discover；后端不可用时继续用缓存兜底。
- **OpenAI 预检 404 误判修复**：之前 `_openai_probe` 把 404/405 一律当作"端点只是不支持 /models 预检"，导致用户把 OSS 桶地址（`*.aliyuncs.com`）、CDN、甚至随机网页 URL 配成 API Base 时被误判为 available=True，实际调用才爆 404。现在加了 `Content-Type` 校验——只有 JSON 响应才保守判 OK，非 JSON 明确报错并提示检查 API Base。
- 文件：`runtime/provider_config.py`、`web/static/css/chat.css`、`web/static/js/chat.js`、`web/templates/index.html`

> 状态：**Phase 0-5 全部交付**（2026-10-28）。
> 定位：SimChat 是 **LMBrewer 的开源底层框架**——它本身具备接入 LLM API 进行对话的完整能力（`runtime/providers.py` + `core.py` + `store.py`），同时提供 MOD SDK + 加载器 + 清单规范 + 沙箱运行时，让社区和团队以模块方式扩展认知能力。
> 愿景：四类 MOD 对应通用智能的四个积木——`skill`=工具调用（感知与行动）、`automation`=自我编排（自主规划）、`agent-config`=人格与对齐（行为约束）、`binary`=专有内核（推理/记忆/安全）。SimChat 是模块化 AGI 的开源基座。