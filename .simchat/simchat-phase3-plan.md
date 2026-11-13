# Phase 3 展开方案：前后端先断开、再接起（2026-10-26）

> 本文档是 [simchat-separation-plan.md](./simchat-separation-plan.md) Phase 3 的施工级展开。
> **状态：✅ P3.0–P3.7 全部完成（2026-10-26）。** 总验收 5 项达标，`lmbrew.py` 344 行，逐片 commit 可回放。
> 用户定调：**这一步失败 = 整个项目失败**。所以本方案的第一优先级不是"拆得快"，而是"每一步都可回滚、可验收、不牵全身"。

---

## 一、为什么这一步是生死战

实测耦合现状（2026-10-26 调研）：

| 事实 | 数据 |
|---|---|
| 单体宿主 | `lmbrew.py` **1829 行、79 个路由**，五个应用全部堆在里面 |
| 最大前端 | `kiraraGenCore.js` **4649 行单闭包**，聊天/人设/音色/记忆/Agent/TTS 全部直接 `fetch('/api/kirara/...')` 硬编码 |
| Kirara 后端 | `jrvs.py` 3251 行，与路由层直接 `from jrvs import ...` |
| 已有好边界 | Niji 已是 Flask 蓝图（`niji_server.py`）；Rigard Phase 1 已验证注册表化可行 |
| 空壳 | cortx/ 无实现，不列入本期 |
| **最大风险敞口** | **项目无 git 版本控制**，唯一的保护措施是文件快照 |

风险的本质：不是"代码量大"，而是**任何一个应用的手术都可能弄断其他四处的线路**，因为没有测试网、没有版本控制、没有边界。

---

## 二、保险丝（先于任何代码改动）

| # | 措施 | 状态 |
|---|---|---|
| 1 | 全量源码快照 `backups/20261026-pre-phase3/`（535 文件，169MB，排除可重建的 llama.cpp 624MB） | ✅ 已完成 |
| 2 | **git init + 初始提交**：此后每个切片一个 commit，回滚从"恢复 169MB 快照"降级为 `git revert` | ⬜ 待用户确认 |
| 3 | 每切片验收脚本化（Flask test client，参考 Phase 2 的 15 项冒烟） | 随切片交付 |

> 第 2 条是强烈建议：没有 git，"每步可回滚"就是空话。快照只能整体回退，git 才能单步回退。

---

## 三、核心原则：断什么、接什么

**"断开"的定义**：前端不再知道后端是谁——不直接写死 URL、不直接读宿主专有配置、不假设某个后端进程在场。

**"接起"的定义**：后端能力通过冻结契约重新暴露——URL 形状不变、事件格式不变、但代码归属从单体宿主迁到应用自己的蓝图/模块。

**四条铁律**：

1. **URL 冻结**：所有外部接口路径、SSE 事件格式一律不变。断的是代码归属和依赖方向，不是对外契约。前端无需配合改接口，手术对外不可见。
2. **单切片推进**：一次只动一个应用的一个耦合面；每片交付 = 迁移代码 + 验收脚本 + 通过记录。
3. **双跑不切流**：迁移期旧代码保留在原位（标注弃用），新蓝图先挂载验证，验收通过后才删旧路由。任何一步失败，删掉新挂载即恢复原状。
4. **不改业务逻辑**：本期只做结构手术。人设 prompt、记忆算法、TTS 参数等业务行为一律原样搬运，发现 bug 记录不修（另开任务）。

---

## 四、四种耦合类型 → 四种断法

| 类型 | 实例 | 断法 |
|---|---|---|
| A. API 调用耦合 | kiraraGenCore.js 里散落的 `fetch('/api/kirara/...')` | 前端引入 **ApiClient 层**：所有 URL 集中为一处常量表 + 薄封装，业务代码只调 `api.chat(...)`，不再出现裸 URL |
| B. 配置硬编码耦合 | 人设卡片、音色默认值、`DEFAULT_PERSONA` | 改 **数据驱动**：前端从 `/api/.../personas` 等端点取清单渲染，缺省值由后端契约下发（Phase 1 模式按钮已验证此手法） |
| C. 路由宿主耦合 | 79 个路由全在 lmbrew.py | **蓝图化**：每应用一个 `*_bp` Blueprint，路由函数物理迁入应用目录，lmbrew.py 只 `register_blueprint`（niji_server.py 已是此形态，作为模板） |
| D. 静态资源耦合 | `/kirara/<path:filename>`、`/apps/<name>/...` 等多套路由 | 收敛为 **`/apps/<name>/<path>` 单一约定**，应用自目录即资源根，旧路径保留 302 重定向一个版本周期 |

---

## 五、切片计划（按风险从低到高排序）

### P3.0 — git 保险（前置，非代码）
`git init` + `.gitignore`（排除 llama.cpp/、__pycache__/、*.pyc、backups/、.screenshots/、.trae-html-share-packages/）+ 初始提交。
**验收**：`git log` 有基线提交；`git status` 干净。

### P3.1 — Niji 蓝图化收尾（最小切片，验证手术流程）
- **断**：lmbrew.py 中 `/niji`、`/apps/niji/...`、`/api/niji/open` 三个硬编码路由（L151-L168）迁入 niji_server.py 蓝图。
- **接**：蓝图挂载时带上页面与静态路由；URL 不变。
- **验收**：编辑器页面 200、静态资源 200、`/api/niji/open` 冒烟、其他应用路由回归抽样。
- **回滚**：`git revert` 该切片 commit。

### P3.2 — Rigard 蓝图化
- **断**：`/api/rigard/*` 15 个路由（L1336-L1700 一带）迁入 `rigard/services/rigard_server.py` 蓝图。注意 `init_rigard()` 单例随蓝图走；`/api/simchat/mods*` 两个路由**留在原地**（它们属于平台面，不属 Rigard）。
- **接**：lmbrew.py 改为 `register_blueprint(rigard_bp)`。
- **验收**：rigard.js 全功能冒烟（chat SSE、sessions CRUD、galax_query、skills），重点回归 Phase 1 的 MOD 装载/卸载双态。
- **风险点**：`simchat_list_mods` 依赖 `rigard_service` 全局——蓝图化后该依赖改为蓝图提供的 accessor，平台路由不变。

### P3.3 — OpenMaid 蓝图化
- **断**：`/api/ai/openmaid/*` 14 个路由 + `/openmaid` 页面路由迁入 `openmaid/openmaid_server.py` 蓝图。
- **接**：同上；前端 ide-layout.css 等资源走 `/apps/openmaid/` 约定不变。
- **验收**：IM 网关配置读写、iMessage/QQ status 端点冒烟（外部服务不在线时验证错误形状不变）。
- **注意**：通用 `/api/ai/<ai_name>/{status,start,stop}`（L478-L573）涉及跨应用进程管理，**本期不动**，归入 P3.7 单独评估。

### P3.4 — Kirara 前端 ApiClient 层（断类型 A）
- **断**：kiraraGenCore.js 内所有裸 `fetch('/api/kirara/...')` 收敛进文件头部的 `KiraraAPI` 常量表 + 封装（`KiraraAPI.chat(payload)`、`KiraraAPI.loadOptions()` …）。不改任何调用时序与参数。
- **接**：业务代码全部改调封装；URL 字符串只许出现在常量表。
- **验收**：`Grep fetch\(['\"]/api` 在 kiraraGenCore.js 中归零（常量表除外）；聊天/TTS/人设/记忆/Agent 全功能浏览器实测。

### P3.5 — Kirara 后端蓝图化
- **断**：`/api/kirara/*` 20 个路由迁入 `kirara/services/kirara_server.py` 蓝图；`init_jrvs()` 单例随迁。`/api/kirara/reset/*`（SMTP 重置三件套）一并迁。
- **接**：`register_blueprint(kirara_bp)`；lmbrew.py 中的 `from jrvs import ...` 改为蓝图内部自管。
- **验收**：P3.4 的同一套浏览器实测 + Flask test client 路由回归（全部 79 个路由抽样 200/405 检查）。

### P3.6 — Kirara 前端注册表化（断类型 B，对接 agent-config MOD）
- **断**：人设卡片、音色列表、模式开关的硬编码默认值改为端点数据渲染；MOD 缺失时的 UI 降级占位。
- **接**：对接 Phase 1 的 `list_mods()` 与后续 `agent-config` MOD 样例。
- **验收**：空 `mods/` 下 Kirara 全功能可用（裸壳语义）；装入样例 agent-config 后人设清单变化。
- **依赖**：需要一个 `agent-config-minimal` 样例 MOD（Phase 3 剩余范围，随本片交付）。

### P3.7 — 通用状态路由归位（✅ 已完成 2026-10-26）
- `/api/status`、`/api/ai/<ai_name>/{status,start,stop}` 是跨应用进程管理面，**评估结论：保留宿主 lmbrew.py**（绑定 `ai_processes`、atexit/信号清理、端口 5000 与私有应用清单；迁入 SimChat 会让平台库反向依赖宿主）。
- 同片修复 P3.5 迁移残留：Kirara 蓝图缺失 helper、`__file__` 路径基准错误、根目录 `kirara.py` 遮蔽包导入。
- 评估与验收全文：[simchat-phase3.7-eval.md](./simchat-phase3.7-eval.md)；`lmbrew.py` 1829 → 344 行，冒烟 24/24。

---

## 六、总验收（Phase 3 完成定义）

1. lmbrew.py 从 1829 行降至 **≤400 行**（只剩 Flask 装配、蓝图注册、通用入口）。
2. `Grep fetch\(['\"]/api` 在各前端 JS 中归零（ApiClient 常量表除外）。
3. 每应用目录自包含：页面 + JS/CSS + 后端蓝图 + 路由，`/apps/<name>/` 单一资源约定。
4. 全部切片验收脚本通过；空 `mods/` 裸壳下 Kirara、Rigard、Niji、OpenMaid 各自功能不退化。
5. git 历史可逐片回放：任意一片 revert 后系统仍可运行。

---

## 七、不做的事（防范围爆炸）

- 不动 cortx/（空壳）。
- 不改任何对外 URL、SSE 事件、请求/响应字段。
- 不修顺手发现的业务 bug（记录到 abi-changelog 欠账清单）。
- 不做 Automation、CLI、索引（Phase 4/5）。
- 不拆分仓库（Phase 6）。
