# 11 调试与排错

> 本章属于「维护者」路径（D），前置：[07 技能安装与启停](07-manage-skills.md)、[08 写第一个 Skill MOD](08-first-skill.md)、[10 自动化 DAG](10-automation.md)。

## 1. 你会得到什么

一套固定的排查顺序：先看进程活着没，再看包加载到哪一步，最后才看单次调用。遇到「技能不出现」「工具报错」「Agent 卡住」时，知道该打开哪个文件、哪条接口。

```text
服务起没起来 / 端口对不对
  → 日志里这次启动扫到了什么（扫描完成：N 个 MOD，M 个已加载）
    → 目标包是 failed / disabled / loaded
      → 工具在不在 /api/agent/tools
        → 单次调用：参数、审批、红线、capability、超时
```

## 2. 前置条件

- 能正常启动服务（第 01 章），并且会看终端输出。
- 手上有一个可复现的故障；没有的话，按 3.3 故意造一个。
- 知道 `.simchat/` 是本体的包根，`data/` 下是运行期数据。

## 3. 跟着做

### 3.1 找到日志并临时调高等级

```bash
curl http://127.0.0.1:5000/api/console/logs
curl "http://127.0.0.1:5000/api/console/logs/simchat.log?lines=200"
```

第一条返回 `log_dir` 和文件列表（文件名、字节数、修改时间）；第二条返回末尾若干行，`lines` 会被夹在 10–1000 之间。

要临时看更细的日志：

```bash
curl -X POST http://127.0.0.1:5000/api/console/system \
  -H "Content-Type: application/json" \
  -d '{"log_level":"DEBUG"}'
```

预期返回 `{"ok": true, ...}`，设置写入 `data/state/system.json`。级别只支持 `DEBUG` / `INFO` / `WARNING` / `ERROR`，传别的值返回 400，报错文本是「日志级别必须是 … 之一」。

> 实测提醒：当前代码里 DEBUG 打点并不多，调到 DEBUG 主要能看到依赖库的输出；调级别只影响**之后**写入的日志行，不追溯历史。

### 3.2 看运行时快照与事件

```bash
curl http://127.0.0.1:5000/api/console/debug/snapshot
curl "http://127.0.0.1:5000/api/console/debug/events?limit=60"
```

快照里有：`runtime`（pid、Python 版本、实际解释器路径、平台）、`memory`、`disk`、`paths`、`log_level`，以及 Web 进程自己的 `uptime_seconds` / `started_at` 和计数 `counts.sessions` / `agent_runs` / `instances` / `gateway_peers` / `events`。

`events` 是 Web 进程内的环形内存（技能启停、系统设置等操作会记一条），**重启即清空**，不要把它当审计日志。

### 3.3 分清「静态扫描」和「运行时加载」

这是最容易误判的一处：

| 你看到的 | 实际含义 |
|---|---|
| `GET /api/console/mods` / `/api/console/skills` 里的 `status` | `mods_index` 只**扫目录 + 校验 manifest**，给 `ok` / `warn` / `err`；`ok` 不代表子进程起来了 |
| 启动日志里的 `[<id>] …` 与 `扫描完成：N 个 MOD，M 个已加载` | 加载器的真实结果 |
| `GET /api/agent/tools` | 工具最终有没有注册成功 |

造一个故障验证：把某个技能 `entry` 里的函数名改错（例如 `hello_skill:register_typo`），重启后控制台 manifest 仍然是 `ok`，但工具消失，日志里出现该包的失败原因。这就是「静态通过、运行失败」。

### 3.4 读加载失败的原因

加载器对每个包只记一条 `failed`，原因写在 `error` 字段，同时打一行日志。常见几类：

```text
[id] manifest 读取失败: Expecting ',' delimiter ...
[id] manifest 校验失败: 缺少必填字段: license
[id] 不支持的 ABI: simchat-mod/1（当前 simchat-mod/2，旧版 lmbrew-mod/1 仍兼容）
[id] 依赖解析失败: 需要 Python >=3.10（当前 3.9）
[id] integrity 不匹配（manifest=sha256:..., actual=sha256:...）
[id] 已停用，跳过加载
[id] 沙箱启动超时（entry(api) 30s 内未完成）
[id] 沙箱静默退出
[id] 沙箱输出格式非法: ...
```

几个配套位置：

- 启停状态在 `skills/.simchat_state.json`（`mods/` 下同名文件）的 `disabled` 数组里；`disabled` 的包不会执行 entry。
- 每个包的数据目录（`data/blocks/<id>` 或 `data/mods/<id>`）在加载前就创建，**失败也不会删**。目录存在只说明「扫到了」，不代表加载成功。
- 同一个路径的包在异常逃逸时不会重复记两条失败，避免列表里出现同名两条。

### 3.5 单次工具调用失败

- **审批挂起**：Agent 遇到 `write` / `dangerous` 会发 `approval_required` 并停在挂起态，状态存 `data/agent_runs/<run_id>.json`，含 `ttl` 与 `expires_at`。默认 600 秒，可由 `config.json` 的 `agent.approval_ttl` 覆盖。超时后再点批准会失败，需要重新发起任务。
- **参数校验**：错误文本会说明缺哪个字段、期望什么类型，照 `params_schema` 补。
- **shell 不可用**：`shell` 默认关闭（`agent.shell_enabled`）；开启后仍有黑名单、超时（默认 10 秒、上限 30）与工作目录限制。
- **输出被截断**：工具输出 8KB、单文件读取 32KB、写入 64KB、`list` 500 项、`glob` 200 项、`grep` 50 条 / 500KB / 2MB。看到「已截断」不是故障，是保护。
- **上下文压缩**：约 12288 tokens 触发 `compacted`，此前历史会被摘要。模型突然「忘了前面的要求」，先看时间线里有没有这条事件。

### 3.6 服务与进程

```bash
python .simchat/scripts/entry.py lifecycle --status
```

打印一份状态 JSON（守护进程、服务地址、最近状态等）。`--stop` 只停守护进程，**不动** Web 服务；`--guard` 让守护进程运行；`--boot` 是开机自启入口。

端口被占用就换一个：`python .simchat/scripts/entry.py web --port 5001`。

> `crash_reports` 由仓库自带的 C++ 启动器写入，Python 层不产生崩溃报告。在 `data/` 里翻不到它属于正常现象。

## 4. 为什么会这样

### 4.1 日志怎么落盘

- 路径 `data/logs/simchat.log`，`RotatingFileHandler`，单文件 2MB、保留 3 个备份。
- 行格式：`时间 级别 logger: 消息`（级别左对齐 7 列）。
- 启动时读 `data/state/system.json` 的 `log_level`，缺省 `INFO`；`POST /api/console/system` 会同时改文件与内存里的 handler 级别。
- 每次启动会打一行 `扫描完成：N 个 MOD，M 个已加载`，这是判断「扫到没」的最快锚点。

### 4.2 MOD 的输出去哪了

- 宿主只把**带 `@@simchat-ipc@@` 前缀**的行当协议消息，所以 MOD 里普通 `print()` 不会顶掉协议；这些行会被转写成 `[mod:<id>] …` 打到宿主 stderr。
- 但 MOD 子进程的 **stderr 会被宿主直接读空丢弃**（防止管道写满阻塞），所以 entry 里的 traceback 不会自动进 `simchat.log`。
- IDE 控制台的「沙箱输出」页签在当前实现里没有数据源，打开也是空的——不要在那里等报错。

结论：要定位 entry 异常，直接进包目录手动复现：

```bash
cd .simchat/skills/your.skill
python -c "import sys; sys.path.insert(0, 'python'); import your_module"
```

### 4.3 三套状态别混用

| 信号源 | 回答的问题 | 不回答什么 |
|---|---|---|
| `mods_index`（控制台 mods/skills） | manifest 结构对不对、是否被停用 | 子进程是否真的加载成功 |
| 加载器日志 + `/api/agent/tools` | 这次启动实际加载了什么、工具名是什么 | 某一次调用的细节 |
| `data/agent_runs/*.json`、`data/audit/*` | 某次 Agent 运行 / 某次自动化执行的步骤与审批 | 启动期问题 |

### 4.4 常见错误对照表

| 现象 | 先查 | 常见根因 |
|---|---|---|
| 包在列表里但工具不出现 | 启动日志里该包的 `error` | entry 导入失败、hook 写错、被停用 |
| `未知 hook（fail-closed）` | `manifest.hooks` | 拼写错误或用了本体未实现的 hook（见 [hooks.md](../../spec/hooks.md)） |
| `integrity 不匹配` | 是否手改过包内文件 | 改完没重新 `cli pack` |
| `签名无效` / `签名已吊销` | `public_keys/` 与吊销列表 | 换机器没换公钥、密钥被吊销 |
| 工具报 `PermissionError` | 该包 `capabilities` | 未声明 `fs` / `net` / `shell`（见 [09 章](09-capabilities.md)） |
| 模型预检显示不可用 | 服务商 Base URL | `/models` 返回 404/405 但响应是 JSON 时，会按「端点不支持预检」放行；连接测试通过后 30 分钟内不会被预检抖动判死 |
| 端口占用 | 终端报错 | 换 `--port`，或先关掉旧进程 |
| 服务能起但页面白屏 | 浏览器控制台 / `simchat.log` | 前端资源 404、静态文件缺失 |

### 4.5 最小复现包

怀疑是宿主问题时，用模板造一个只做一件事的包：

```bash
python .simchat/scripts/entry.py cli init --type skill --id com_example_probe --name "Probe" --target .simchat/skills/com_example_probe
```

只留一个无参数工具，返回固定字符串，重启后看它是否出现在 `/api/agent/tools`。如果 probe 能加载、你的包不能，问题在包；如果 probe 也不能，问题在宿主或启动参数。

## 5. 常见坑

- **把控制台 `status: ok` 当成「已加载」**：它只校验 manifest。加载结果看日志与工具清单。
- **在 IDE 沙箱输出里找 traceback**：那个页签目前没有数据源；MOD 的 stderr 也被宿主丢弃。
- **用 `SIMCHAT_SKIP_VERIFY=1` 当修复**：它只是跳过 binary 的完整性与签名校验，安全语义上等于「关掉验签」，只能临时用于开发。
- **改完代码不重启**：技能与 flow 都是启动期注册，没有热重载。

## 6. 验收清单

- [ ] 能从 `simchat.log` 找到本次启动的「扫描完成」行
- [ ] 能区分控制台静态 `status` 与运行时加载结果
- [ ] 能说出失败原因字段在哪、启停状态文件在哪
- [ ] 能用 `lifecycle --status` 看进程状态，并知道 `--stop` 不停 Web
- [ ] 能造一个「manifest 正确但 entry 写错」的故障并定位

已知限制：MOD 子进程的 traceback 不写入 `simchat.log`，见 [known-limitations.md](../known-limitations.md)。

## 7. 延伸阅读

- [logs.py](../../runtime/logs.py)：日志路径、轮转参数、`list_files` / `tail`
- [system_config.py](../../runtime/system_config.py)：可写白名单（目前只有 `log_level`）与调试快照
- [lifecycle.py](../../loader/lifecycle.py)：`_fail` / `_record_crash` 与失败记录
- [sandbox.py](../../loader/sandbox.py)：stderr 丢弃、IPC 前缀、30s 启动超时与 60s 调用超时
- [runs.py](../../runtime/agent/runs.py)：审批挂起态、`ttl` / `expires_at` 与过期判断
- [10 自动化 DAG](10-automation.md) / [12 打包与发布](12-publish.md)
