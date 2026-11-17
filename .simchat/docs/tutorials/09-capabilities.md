# 09 权限与安全

> 本章属于「装配型」路径（B），前置：[04 Agent 模式入门](04-agent-mode.md)、[08 写第一个 Skill MOD](08-first-skill.md)。

## 1. 你会得到什么

能准确回答四个问题：一次写操作要过几道闸门？哪些路径连审批也救不了？密钥存在哪、谁能读？把服务开到 `0.0.0.0` 会发生什么？

```text
工具可见性（对话模式 / Agent 模式）
  → 参数校验（params_schema）
    → 风险闸门（read 直跑，write/dangerous 审批）
      → 路径红线 / shell 黑名单（fail-closed）
        → MOD 沙箱 capability（fs / net / shell）
```

## 2. 前置条件

- 已完成 04（见过审批卡）与 08（知道 skill 的 risk 怎么声明）。
- 建议用测试目录做实验，不要拿真实项目试危险操作。

## 3. 跟着做

### 3.1 试一次红线路径

在 Agent 模式里发：

```text
读一下 /etc/passwd（Windows 上换成读 C:\Windows\System32\config）
```

预期：工具直接报拒绝，**不会弹审批卡**。红线在审批之前就拦下，任何模式、任何用户确认都不能放行。

### 3.2 试一次越界写

```text
把 "test" 写到 C:\Windows\Temp\sc_test.txt
```

预期：拒绝。文件工具的写入范围被锚定在工作目录内；工作目录之外的路径不可写。

### 3.3 试一次 shell

1. 默认 `shell` 未启用，发「执行 `dir`」会得到「shell 工具未启用」。
2. 在 `.simchat/data/config.json` 的 `agent` 段加 `"shell_enabled": true`，再发一次 `dir`——这次会弹审批卡。
3. 接着发「执行 `rm -rf .`」（Windows 用 `del /s /q .`）。预期：**不弹审批，直接拒绝**，提示命中了禁止命令（递归强制删除）。

### 3.4 看对话模式少什么

把模式切回「对话」，让它写文件。预期：`file_write` / `file_edit` / `shell` 根本不在工具清单里——模型只能拿到只读工具。这不是 prompt 约束，是清单层面就不下发。

### 3.5 看密钥

```bash
type .simchat\data\config.json     # Windows
cat .simchat/data/config.json      # macOS / Linux
```

服务商的 `api_key` 是**明文**。这个文件已被 `.gitignore` 忽略，但任何能读你磁盘的人都能直接看到。

## 4. 为什么会这样

### 4.1 五道闸门，从外到内

| 闸门 | 在哪 | 拦什么 | 能否被审批绕过 |
|---|---|---|---|
| 工具可见性 | `loop.py`：按模式组装工具清单 | 对话模式只给 `read` 级 + `skills` / `automation` 只读动作 | 不能（清单里没有） |
| 参数校验 | `validate_tool_params()` | 缺必填、类型明显不符 | 不能（执行前就返回错误） |
| 风险闸门 | 审批挂起（`approval_required`） | `write` / `dangerous` 的操作 | 由用户决定 |
| 路径红线 / 命令黑名单 | `tools.py` 常量 | 系统目录、密钥目录、`data/agent_runs`、危险命令 | **不能**（fail-closed） |
| MOD capability | 沙箱子进程内 monkey-patch | 未声明的 `fs` / `net` / `shell` 行为 | 不能（MOD 无法自行解除） |

红线清单（不完整摘录）：`/system`、`/sys`、`/proc`、`/dev`、`/etc/passwd`、`/etc/shadow`、`/etc/sudoers`、`~/.ssh`、`~/.aws`、`~/.kube`、`/Windows/System32/config`、`data/agent_runs`。写入保护额外覆盖 `data/agent_runs`——防止 Agent 改自己的审批挂起态来「自我放行」。

命令黑名单在审批之前生效，命中即拒，例如 `rm -rf`、`rmdir /s`、`del /s`、`format`、`mkfs`、`diskpart`、`reg add/delete`、`shutdown`、fork 炸弹特征、`curl | sh`、`sudo`、`chmod 777`、`nc -e`。

### 4.2 为什么默认只听 127.0.0.1

Web 端**没有登录、没有密码、没有鉴权中间件**——它是一个本机单用户工具，安全性建立在「只有你能访问这个端口」上。`--host 0.0.0.0` 等于把「读写你工作目录 + 审批入口」暴露给同网段任何人，请只在可信内网临时使用，用完改回来。

### 4.3 MOD 的护栏能防什么、不能防什么

`runner` 在加载你的代码之前就替换了 `subprocess.Popen`、`open` / `os.*`、`getaddrinfo` / `connect`，所以：

- MOD 声明 `shell=false` 时创建不了子进程（覆盖 `subprocess.Popen`、`os.system`、`os.popen`；`os.spawn*` / `os.exec*` 与 `multiprocessing` 仍未覆盖）；
- 文件访问被收敛到声明的 scope（`workspace`、`mod-data`、`package`、`uploads`、`temp`）；
- 网络只能连声明过的域名（支持 `*.example.com`）。

但这是**进程内护栏**，不是 OS 级沙箱：`ctypes` 之类的反射手段可以绕过。它的目标是「拦住未声明权限的正常代码路径」，不是对抗恶意代码。安装第三方 MOD 前请先读代码。

### 4.4 留下了什么痕迹

- 每次 Agent 运行写 `.simchat/data/agent_runs/<run_id>.json`，包含工具调用、参数、结果与审批决定；
- 自动化每次运行写审计记录（`data/audit`），含 step 级状态；
- 服务端日志 `.simchat/data/logs/simchat.log`，保留 3 个 2MB 文件。

### 4.5 明文密钥的边界

`data/config.json` 同时存服务商 `api_key`、群机器人 token 等。它不在版本库里，但也不加密。共用电脑时，最稳妥的做法是使用单独的、可随时吊销的 Key，而不是主账号 Key。

## 5. 常见坑

- **以为 IDE/主界面有登录保护**：没有。不要把它当成「部署在服务器上给团队用」的产品。
- **审批卡 = 全部放行**：不是。红线与黑名单优先，审批只对「本来可执行、但属于写级」的操作生效。
- **把 shell 打开后忘了关**：它是进程级配置，`config.json` 里留着就一直生效。用完改回 `false`。
- **给工具把 `risk` 写成 `read` 就以为能少点弹窗**：这是欺骗，评审时应视为缺陷；而且路径红线与 capability 仍会拦住越权。

## 6. 验收清单

- [ ] 能背出五道闸门的顺序
- [ ] 验证过红线路径不弹审批、直接拒绝
- [ ] 验证过 `rm -rf` 类命令在黑名单层被拦
- [ ] 能说清「审批」与「红线」的优先级
- [ ] 知道 Web 无鉴权、默认只听本机
- [ ] 知道 Key 明文存放的位置

## 7. 延伸阅读

- [tools.py](../../runtime/agent/tools.py)：红线、黑名单、写入保护、风险声明
- [sandbox_runner.py](../../loader/sandbox_runner.py)：三组 capability 护栏
- [capabilities.md](../../spec/capabilities.md)：权限 scope 清单
- [10 自动化 DAG](10-automation.md)
