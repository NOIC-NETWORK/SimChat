# §12 开放决策池（2026-10-26 记录）

> 来自 [simchat-separation-plan.md §12](simchat-separation-plan.md)。
> 本文件只做"问题 + 现状 + 选项 + 建议"的归档，**不代表任何拍板结果**。
> 真正需要这些决策的时候再回来开——比如 Phase 4 CLI 要设计本体打包、Phase 5 写 Automation 调度器、Phase 6 做商店。
> 改完直接回到 Phase 2 剩余的管线。

---

## 1. 本体是否闭源？

**现状**：当前仓库（lmbrew.py + 四个应用蓝图 + simchat/loader）全部纯 Python/JS 明文，等于已开源。`build_pkg/` 只设计过 `binary` 类型 MOD 的 Cython → PyArmor → AES-GCM 打包链路，本体本身未走任何打包。

**选项 A（建议）**：本体闭源 + loader/SDK/spec 开源（Minecraft 路线）
- 做法：本体（Flask 宿主 + 应用蓝图 + Agent 内核）打包成 pyc/pyd，PyArmor + AES-GCM；loader/manifest schema/hooks spec/SDK 保持 Apache-2.0。
- 好处：保护创作内核（Kirara/JRVS 人设、Agent 循环、记忆系统）；SDK 开源让社区能写 MOD；binary MOD 打包链路现成。
- 代价：闭源透明性损失；维护两条打包流程；若未来改开源是"撕票"事件。

**选项 B**：全部 MIT/Apache-2.0 开源（现在这样）
- 好处：透明、可信、零贡献门槛。
- 代价：任何 fork 都能拿走你花心血的东西。

**选项 C**：本体 + loader/SDK 都闭源
- 不推荐。社区无法写 MOD，平台生态死路。

---

## 2. 首个官方 MOD 是否选 Galax？

**现状**：Galax 已经是 MOD——Phase 1 把 `GalaxPipeline` 从 Rigard 抽成 `mods/barry.galax/`，通过 `chat.mode` hook 注册前端 `⚡`，宿主保留内置回退。契约、ABI、跨宿主复用（Kirara 也能消费）都已验证。Schema 校验过（`binary` 类型、有 `entry`、有签名位）。

**选项 A（建议）**：是，Galax 为首个一等方 MOD
- 做法：现有 `mods/barry.galax/` 加 ed25519 签名 + sha256 integrity，放到首个官方索引 `registry/index.json`。
- 好处：Phase 1 现成试金石；跨宿主；首发展示一等方 MOD 长什么样。
- 代价：当前 `chat.mode` hook 契约偏窄。

**选项 B**：暂不，等 JRVS 人设 binary MOD
- 不推荐。首发空白。

---

## 3. Quasar 是否从首发/对外文案中撤下？

**现状**：Quasar 在 repo 里是纯架空概念——`readme.md` 写"自研自动演化大模型 Quasar 正在秘密研发"，`kirara_intro.md` 写"Galax 和 Quasar 两个模式可供激活"。但 `rigard.js L331` 注释是"专用后端上线前暂走标准对话链路"——空壳，没有后端、没有 MOD、没有蓝图。分离方案自己写了"Quasar 空承诺 → 首发阵容不包含 Quasar"。

**选项 A（建议）**：对外文案撤下；世界观内部文档改"远期规划"
- 做法：readme.md / 商店描述删 Quasar；`kirara_intro.md` 里保留世界观叙事但标注"远期规划"；`simchat-separation-plan.md` 把 Quasar 从"一等方加密 MOD"挪到"远期"。
- 好处：不承诺没做的东西。
- 代价：世界观描述里叙事完整性略损，但可接受。

**选项 B**：保留文案但明确标注"尚未实现"
- 好处：世界观不破坏。
- 代价：用户点按钮发现没东西，仍然失望。

---

## 4. Automation 首发只做 DAG？

**现状**：仓库里没有通用工作流引擎。`simchat-separation-plan.md §7` 定义了最小形态：`flow.json`（DAG 节点图）+ `trigger`（cron/事件）+ 调度器执行，manifest schema 已支持 `automation` 类型（必填 `flow` + `trigger`，必须声明 `capabilities.schedule=true`）。代码式 Automation（用户写 Python）完全没设计。

**选项 A（建议）**：首发只做 JSON DAG
- 做法：Phase 5 落地的是 JSON DAG 调度器（节点只能调用已注册的 skill，不能任意代码），写操作默认审批，硬配额。
- 好处：DAG 可静态分析、可审计、可沙箱；"Automation 失控"风险（无人值守写文件/发消息）被彻底关闭。
- 代价：灵活性低，可通过条件/循环/子流程节点缓解。

**选项 B**：首发就支持代码式
- 不推荐。绕过所有审计沙箱。

---

## 5. 付费 MOD 是否首发开放？

**现状**：binary MOD 类型 + 签名 + integrity 在 schema 里；但商店、支付、分成、DMCA/下架流程**全部没设计**——这些属于 Phase 6 仓库/品牌/社区。

**选项 A（建议）**：二期开放（Phase 6 以后）
- 做法：Phase 4-5 只支持免费 MOD；付费框架（商店前端、支付 API、分成、DMCA）留 Phase 6 一起落地。
- 好处：免费生态先堆起来（数量 × 下载量 × 活跃作者数），过了再开付费。
- 代价：一等方 MOD（Galax 订阅、JRVS 授权）首发只能免费。

**选项 B**：首发开放付费框架但不启用
- 做法：schema 预留付费字段，商店 UI 占位显示"敬请期待"。
- 好处：框架搭好。
- 代价：又一个"空承诺"按钮。

**选项 C**：首发就开付费
- 不推荐。支付/分成/DMCA 全没设计。

---

## 6. 搜索原子能力要不要做内容治理（黑名单）？

**现状**：`mods/noic.webSearch/python/webSearch.py` 是 MOD 形态的原子能力（`ToolSpec` risk=`read`，注册 `webSearch` 工具），提供 `search`（Bing / 搜狗，互为 fallback）、`fetch`、`search_and_summarize`。安全面目前只做了 SSRF 防护——`_validate_url` 拒绝内网与私有网段、非 http(s) 协议。**对搜索结果本身零治理**：标题、URL、snippet 原样返回，直接进 Agent 上下文，模型无从分辨来源可信度。

**风险（"百度悲剧"）**：搜索结果的排序权不在我们手里。一旦被 SEO 内容农场、AI 生成垃圾站、镜像站、竞价广告位占据，模型就会把垃圾当事实引用，用户也看不出区别。这一环比 `net` 更脆弱：**目标域名是未知的，无法事前白名单**——恰好是当前 `capabilities.md` 里 `net.domains` 白名单模型的盲区。

**选项 A（建议）：黑名单 + 事后过滤，闸门放本体**
- 做法：
  - 域名黑名单：已知内容农场 / AI 垃圾站 / 镜像站，命中直接丢弃（不静默降权，丢弃并记审计计数，便于后续调规则）
  - 结果级过滤：同域名合并、标题与 snippet 相似度去重、纯跳转站与聚合页识别
  - 来源分级：政府/学术/官方文档 > 主流媒体 > 个人博客 > 未知来源
  - 黑名单**必须在本体**（依据 `spec/capabilities.md §4`：MOD 可追加规则，不能移除或短路本体规则）；MOD 只能追加自己的条目，不能删本体的
- 好处：与既有权限模型一致；黑名单可热更新；不依赖上游搜索源的排序质量
- 代价：黑名单要长期维护；有误杀风险，需要留"用户对单条结果强制放行"的口子并写审计

**选项 B：白名单（只允许可信域名）**
- 不推荐。与搜索的开放语义直接冲突，等于把通用搜索阉割成站内检索；查冷门报错这类长尾需求会全部失败。

**选项 C：不管，交给上游搜索源**
- 不推荐。等于把内容质量外包给 Bing / 搜狗，这正是"百度悲剧"的成因。

**待定**：
- 黑名单初始粒度：域名级，还是域名 + URL 路径级
- 是否引入外部信誉源（uBlock 过滤器列表、社区反 AI 垃圾站名单）
- 与 `net` capability 的关系：搜索用不了 `net.domains` 白名单，是否需要独立的 `net.search` 语义（出站不受域名白名单约束，但结果受黑名单约束）
- 黑名单命中时的用户可见性：静默丢弃，还是折叠显示"已过滤 N 条"

---

## 决策影响链（谁需要什么）

| 决策 | Phase 2 剩余 | Phase 4 CLI | Phase 5 Automation | Phase 6 商店 |
|---|---|---|---|---|
| 1 本体闭源？ | 不直接影响 | **决定本体打包方案（PyArmor vs 什么都不做）** | 不影响 | 影响商店授权策略 |
| 2 Galax 为官方 MOD？ | **影响签名/沙箱是否必须先对 binary 跑一遍** | 影响索引设计（官方条目长什么样） | 不影响 | 影响首发阵容 |
| 3 Quasar 首发？ | 不影响 | 不影响 | 不影响 | **影响首发文案** |
| 4 Automation 只 DAG？ | 不直接影响 | 影响 CLI `automation pack` 命令 | **决定 Phase 5 调度器的最小形态** | 不影响 |
| 5 付费 MOD 首发？ | 不影响 | 影响 CLI `mod pack` 是否预留 paid 字段 | 不影响 | **Phase 6 核心问题** |
| 6 搜索黑名单？ | **决定 webSearch 是否要等本体过滤器就位**（未就位得先自己兜一层） | 影响 CLI 是否需要黑名单导入命令 | Automation 调搜索时继承同一套过滤 | **影响商店对搜索类 MOD 的审核口径** |

注：Phase 2 剩余的核心（sandbox/signature/resolver/skill 迁移）**不依赖任何 §12 决策**——它们是加载器安全底座，和本体闭源/付费/Quasar 无关。Galax 是否官方会让签名/沙箱先跑一遍（它是 binary），但 Galax 已经是 MOD 了，即使不官方签名也得在 sandbox 里跑。
