# Phase 3.7 评估：通用状态路由归位（2026-10-26）

> 本文是 [simchat-phase3-plan.md](./simchat-phase3-plan.md) §五 P3.7 的单独评估稿。
> 结论先行：**`/api/status` 与 `/api/ai/<ai_name>/{status,start,stop}` 保留在宿主 lmbrew.py，不迁入 SimChat 平台面。**
> 同片修复 P3.5 迁移残留（Kirara 蓝图中未定义的 helper 与错误的路径基准），否则"每应用自包含"不成立。

---

## 一、评估对象

| 路由 | 位置（迁移前） | 外部消费者 | 生命周期绑定 |
|---|---|---|---|
| `GET /api/status` | lmbrew.py | 宿主仪表盘 / 探活 | 宿主进程本身 |
| `GET /api/ai/<ai_name>/status` | lmbrew.py | 仅 `static/js/lmbrew.js` | 读取 `ai_processes` 句柄 |
| `POST /api/ai/<ai_name>/start` | lmbrew.py | 同上 | `subprocess.Popen` + `webbrowser.open` 宿主端口 5000 |
| `POST /api/ai/<ai_name>/stop` | lmbrew.py | 同上 | `taskkill /T /PID` 进程树 |

关键事实：

1. `ai_processes` 是**宿主进程内的全局字典**，由 lmbrew.py 的 `atexit` 与 POSIX 信号处理器负责清理（`lmbrew.py`）。
2. 启动逻辑依赖宿主目录布局（`<ai_dir>/services/jrvs.py` → `main.py` → `services/<ai>.py`）与宿主端口 `localhost:5000`。
3. 应用清单硬编码为 `kirara / rigard / openmaid / openbci`——全是 LMBrewer 的 `apps/`，不是 SimChat MOD。
4. 前端消费方只有宿主仪表盘 `templates/lmbrew.html` + `static/js/lmbrew.js`，没有任何子应用页面调用这组端点。

---

## 二、归属判定

| 维度 | 迁入 SimChat 平台面 | 保留宿主本体 |
|---|---|---|
| 与 SimChat 仓库边界 | ✗ 违反分离方案 §8.1（SimChat = SDK + Loader + CLI，不含 apps），也违反 §5「其他子应用不进 SimChat」 | ✓ 属于 LMBrewer 本体 `apps/` 的进程治理 |
| 依赖方向 | ✗ SimChat 反向依赖宿主目录名、端口、应用清单 | ✓ 依赖闭合在宿主内部 |
| 生命周期 | ✗ 需要把 atexit/信号处理也搬走，等于把宿主进程治理交给平台库 | ✓ 与宿主同生共死，语义天然一致 |
| 解耦收益 | 仅代码搬家，无契约变化（URL 已冻结） | 零收益损失；后续若要独立守护进程再评估 |

**结论：不迁。** 状态/进程管理是"宿主外壳"能力，不是 SimChat 的可复用平台能力。强行迁移只会让开源平台库携带 LMBrewer 私有的应用清单与端口假设。

边界说明：如果未来子应用改为独立 HTTP 服务（各自带健康检查端点），这组路由应改为"宿主侧反向代理/编排层"，仍然留在宿主。

---

## 三、同片必须修复的 P3.5 残留

评估过程中发现 Kirara 蓝图存在**迁移型缺陷**（非业务 bug），不修则 Phase 3 验收不成立：

| # | 缺陷 | 后果 | 修复 |
|---|---|---|---|
| 1 | kirara_server.py 调用 `_get_agent_shell_options` / `_agent_sse_response` / `get_user_path` / `get_smtp_config_path` / `DEFAULT_SMTP_CONFIG`，但既未定义也未导入 | Agent tools/run/approve、用户信息、SMTP 路由全部 `NameError` | 从 lmbrew.py 原样搬入 kirara_server.py |
| 2 | `_CODE_POOL` / `_RESET_CODE_MAX_ATTEMPTS` / `_get_reset_target_paths` / `_execute_reset` 在迁移中丢失 | 重置验证码与数据清理链路不可用 | 按迁移前定义原样恢复 |
| 3 | `datetime` / `queue` / `threading` 未导入 | 用户注册、Agent SSE 运行时报错 | 补齐导入 |
| 4 | 蓝图内仍用 `os.path.dirname(__file__)` 作为项目根 | `/kirara` 页面 404；`options.json` / `user.json` / `smtp_config.json` / 重置目标路径全部指向 `kirara/services/kirara/...` 不存在的目录，配置静默退回默认值 | 改用 `SERVICES_DIR / KIRARA_DIR / PROJECT_ROOT` 三级基准 |
| 5 | 根目录遗留的 `kirara.py` 遮蔽 `kirara` 包（同名模块优先于命名空间包） | `from kirara.services.kirara_server import ...` 触发遗留脚本，`ImportError` 导致宿主无法启动 | 新增 `kirara/\_\_init\_\_.py`，使其成为常规包（常规包优先于同名模块） |

以上均为"把代码搬到新位置但没搬依赖"的结构问题，不涉及人设、记忆、TTS 等业务逻辑。

---

## 四、验收记录

`Flask test client` 冒烟（临时脚本，不进入仓库）：

| 组 | 项目 | 结果 |
|---|---|---|
| 路径基准 | KIRARA_DIR / PROJECT_ROOT / options.json 存在 / user.json / smtp_config | 5/5 |
| 状态路由 | `/api/status`、`/api/ai/kirara/status`、未知应用的 status/start/stop | 5/5 |
| Kirara 页面与静态 | `/kirara`、`/kirara/js/kiraraGenCore.js`、`/apps/kirara/kirara.html` | 3/3 |
| Kirara API | options、user/status、user/info、agent/tools、personas、tts/voices、reset/smtp-config、request-code、execute（故意错码→400） | 9/9 |
| 结构指标 | 路由总数 88（≥79）、lmbrew.py 344 行（≤400） | 2/2 |

**合计 24/24 通过。**

注：smtp request-code 一项会走真实 SMTP（本机已配置账号），仅向占位地址发送了一封验证码邮件，未触碰任何本地数据；execute 使用故意错误的验证码，未调用 `_execute_reset()`。

---

## 五、Phase 3 收口状态

| 切片 | 状态 |
|---|---|
| P3.0 git 保险 | ✅ |
| P3.1 Niji 蓝图化 | ✅ |
| P3.2 Rigard 蓝图化 | ✅ |
| P3.3 OpenMaid 蓝图化 | ✅ |
| P3.4 Kirara 前端 ApiClient | ✅ |
| P3.5 Kirara 后端蓝图化 | ✅（本片补齐残留） |
| P3.6 Kirara 前端注册表化 | ✅ |
| P3.7 状态路由评估 + 残留修复 | ✅ |

总验收对照：

1. lmbrew.py 1829 → **344 行**（≤400）✅
2. 各前端 JS 裸 `fetch('/api...')` 归零（ApiClient 常量表除外）✅（P3.4）
3. 应用目录自包含（页面 + JS/CSS + 蓝图 + 路由）✅
4. 空 `mods/` 裸壳下各应用功能不退化 ✅（P3.6 + 本片冒烟）
5. git 历史可逐片回放 ✅

---

## 六、本片不做的事

- 不迁移状态/进程管理路由（评估结论为保留）。
- 不改任何对外 URL、SSE 事件、请求/响应字段。
- 不把 `kirara.py` 遗留脚本删除或改写（仅通过包初始化消除遮蔽；归档属后续阶段）。
- 不修顺手发现的业务 bug。
