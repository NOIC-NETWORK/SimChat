# 07 安装、启用与排查技能

> 本章属于「装配型」路径（B），前置：[04 Agent 模式入门](04-agent-mode.md)。

## 1. 你会得到什么

控制台「技能」页里能看到本机已安装的每个技能包，并且能一键启停；停用后重启服务，Agent 的工具清单里对应工具消失，恢复后重新出现。

```text
技能                                          1 / 5 个技能已启用        [刷新]
  ReadFile 文件读取技能  v1.0.0                                    [开]
    读取用户上传的文件内容，支持文本/PDF/Word/Excel/图片元数据…
    hooks: agent.block
  WebSearch 网络搜索技能  v1.0.0                                   [开]
    …
```

## 2. 前置条件

- 服务正在运行，工作目录已选，Agent 模式可以正常跑（第 04 章验收通过）。
- 知道 `.simchat/skills/` 与 `.simchat/mods/` 是两个并排的目录。

## 3. 跟着做

### 3.1 打开技能页

设置面板（齿轮「选项」）底部点「高级功能设置 ▸」进入控制台，左侧导航选「技能」。顶部汇总显示「已启用 / 总数」，右侧「刷新」重新拉一次快照。

### 3.2 先看清单

本机自带 5 个包，位于 `.simchat/skills/`。注意区分三类：

| 目录 | manifest `id` | type | 作用 |
|---|---|---|---|
| `noic.readFile` | `noic_skill_readfile` | skill | 读取上传文件（文本/PDF/Word/Excel/图片元数据） |
| `noic.webSearch` | `noic_skill_websearch` | skill | 关键词搜索（必应/搜狗）与网页正文抓取 |
| `noic.screenshotRecognition` | `noic_skill_screenshotrecognition` | skill | 截图 OCR 与界面分析 |
| `barry.galax` | `barry_galax` | binary | 向加载器注册 `galax` 模式（`chat.mode`），带自己的前端资源；**Web 界面目前没有该模式入口**（未接线） |
| `automation_daily_digest` | `automation_daily_digest` | automation | 工作日 09:00 生成工作区摘要的 flow（cron 触发，写 `digest.md` 需审批） |

**目录名不等于 id**，启停接口用的是 manifest 里的 `id`（只允许小写字母、数字与下划线）。

### 3.3 停用并验证

1. 在「WebSearch 网络搜索技能」右侧把开关关掉。页面提示的语义是「重启后生效」。
2. 重启服务：终端 `Ctrl+C`，再 `python .simchat/scripts/entry.py web`。
3. 验证工具清单：

   ```bash
   curl http://127.0.0.1:5000/api/agent/tools
   ```

   或在 Agent 里查看当前工具清单。预期：由该技能注册的工具不再出现。

4. 回到控制台把开关打开，再重启一次，工具重新出现。

### 3.4 用 API 做同样的事

```bash
# 查快照
curl http://127.0.0.1:5000/api/console/skills

# 停用（body 必须是布尔值，传 "false" 字符串会 400）
curl -X POST http://127.0.0.1:5000/api/console/skills/noic_skill_websearch/toggle \
     -H "Content-Type: application/json" -d "{\"enabled\": false}"
```

### 3.5 手工恢复

状态文件是 `.simchat/skills/.simchat_state.json`：

```json
{
  "disabled": ["noic_skill_websearch"]
}
```

删掉对应 id（或把 `disabled` 置为空数组）后重启，即恢复启用。文件损坏或格式错误时，加载器按「没有任何停用项」处理，不会因此启动失败。

## 4. 为什么会这样

- **技能和 MOD 是同一套机制**：加载器既扫 `.simchat/mods/`，也把 `.simchat/skills/` 作为额外扫描根，两者共用 manifest 校验、ABI（`simchat-mod/2`）、签名校验与沙箱子进程。区别只在定位：`mods/` 放完整 MOD，`skills/` 放可独立分发的原子能力包，默认 `layer=block`。
- **为什么要重启**：工具是在加载器启动时一次性注册进方块注册表的（`discover()` → 逐个 `_load_one` → `sync_loader_blocks`）。开关只改状态文件，不热插拔，所以必须重新走一遍启动流程。
- **状态文件读两遍**：控制台只读扫描用于展示，加载器在 `discover()` 时读取同一份 `disabled` 列表并跳过这些包（状态记为 `disabled`，不注册工具、不创建沙箱）。
- **`barry_galax` 与 `daily-digest` 不是「工具型技能」**：前者向加载器注册 `galax` 模式（`chat.mode`），但 Web 前端目前没有对应按钮，所以不会出现在 Agent 工具清单、也不会出现在输入框；后者是自动化 flow，靠自己的 cron 或 `automation_trigger` 触发（manifest 里声明的 `agent.completed` 钩子运行时尚未派发）。它们的启停同样走这套开关。
- **`daily-digest` 的版本门槛**：manifest 要求 `simchat >=2.1,<3`，当前本体版本 2.3.0 满足，正常情况下会加载。
- **加载失败先看哪里**：manifest 校验不过的条目会在标题旁标出「manifest 错误」（其他状态码 `warn` 目前不在列表里显示）。具体错误文本在 `GET /api/console/skills` 返回的 `data.items[].error` 里；服务端日志在 `.simchat/data/logs/simchat.log`（2MB × 3 轮转），控制台「日志」页也能直接看。

## 5. 常见坑

- **控制台说明文案写的是「写入 mods/.simchat_state.json」**：这是界面文案过期，实际写入的是 **`skills/.simchat_state.json`**。功能正常，以本文为准。
- **关了开关但工具还在**：没重启。另外，内建方块（如 `web_search`）不受技能启停影响——它只是复用了 `skills/noic.webSearch` 的代码目录；如果把该目录删掉或改名，内建 `web_search` 会报「技能未安装」。
- **用目录名去调 toggle 没生效**：要用 manifest 的 `id`（`noic.readFile` → `noic_skill_readfile`）。

## 6. 验收清单

- [ ] 控制台技能页能看到 5 个包与各自状态
- [ ] 停用 `webSearch` 并重启后，Agent 工具清单里对应工具消失
- [ ] 重新启用并重启后，工具恢复
- [ ] 能指出状态文件的确切路径，并说出为什么需要重启
- [ ] 能区分「工具型 skill」「chat.mode 型 binary」「automation flow」三类包

## 7. 延伸阅读

- [mods_index.py](../../runtime/mods_index.py)：只读扫描、快照与启停写入
- [lifecycle.py](../../loader/lifecycle.py)：`discover()` 的扫描顺序与 disabled 处理
- [hooks.md](../../spec/hooks.md)：`agent.block`、`chat.mode`、`agent.completed`
- [mod-manifest.schema.json](../../spec/mod-manifest.schema.json)：manifest 字段
- [08 写第一个 Skill MOD](08-first-skill.md)
