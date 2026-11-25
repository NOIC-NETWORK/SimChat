# 01 安装与首次启动

> 本章属于「只使用」路径（A），是后续所有章节的前置。

## 1. 你会得到什么

终端里打出 `[SimChat] Web 界面已启动: http://127.0.0.1:5000`，浏览器自动打开 SimChat 界面：首次启动会先看到注册页，填完（或跳过）后进入主界面。

```text
[SimChat] Web 界面已启动: http://127.0.0.1:5000
 * Running on http://127.0.0.1:5000
```

此时还没有配置模型、没有选工作目录，输入框是锁住的——这是正常的，下一章开始解锁。

## 2. 前置条件

- Windows 10/11、macOS 或 Linux（WSL 也可以）。
- Python ≥ 3.9，且 `python --version` 能在终端里直接跑通。
- Git（用来克隆仓库）。
- 可选但强烈建议：一个本地模型（Ollama）或一个 OpenAI 兼容的 API Key，第 02 章要用。

## 3. 跟着做

1. 克隆仓库并进入仓库根目录（下文所有相对路径都以仓库根为基准）。

   ```bash
   git clone <仓库地址> simchat
   cd simchat
   ```

2. 安装依赖。依赖清单在 [requirements-simchat.txt](../../scripts/requirements-simchat.txt)：`flask`、`cryptography`、`requests`、`websocket-client`（群机器人 WebSocket 用）。

   ```bash
   python -m pip install -r .simchat/scripts/requirements-simchat.txt
   ```

   预期：四个包都显示 `Successfully installed` 或 `Requirement already satisfied`。

   > 如果打算用本地 Ollama 而不是远程 API，还要额外装它的 Python 客户端：`python -m pip install ollama`。这个包不在 requirements 里，缺了会看到「未安装 ollama Python 库」的提示；只用 OpenAI 兼容服务商则不需要它。

3. 启动 Web 服务。

   ```bash
   python .simchat/scripts/entry.py web
   ```

   预期：终端出现上面那句 `Web 界面已启动`，并且浏览器自动打开 `http://127.0.0.1:5000`。

4. 首次进入会看到注册页。只需填「你希望 SimChat 怎么称呼你」（用户名，最多 32 字），生日和紧急联系人可留空；也可以点「稍后再填，先进去看看」。用户名之后可在控制台「个人中心」修改。

5. 换端口或不让它自动开浏览器：

   ```bash
   python .simchat/scripts/entry.py web --port 8080
   python .simchat/scripts/entry.py web --no-browser
   python .simchat/scripts/entry.py web --host 0.0.0.0 --port 5000
   ```

   `--host` 默认 `127.0.0.1`（只有本机能访问），`--port` 默认 `5000`，`--debug` 开 Flask 调试模式（会多起一个 reloader 子进程，浏览器窗口仍只开一次）。

6. 停止服务：在终端按 `Ctrl+C`。SimChat 会把这次停止标记为「用户主动停止」，守护进程不会把它当成崩溃再拉起来。

### 一键脚本（可选）

不想记命令，可以用仓库自带的启动脚本。它们会自己找 Python（≥ 3.9）、检查并安装上面那四个依赖，然后给一个菜单：

```text
1. Web UI  (http://127.0.0.1:5000)
2. MOD CLI (init / pack / verify / publish / gen-key)
3. Quit
```

| 平台 | 命令 |
|---|---|
| Windows PowerShell | `powershell -ExecutionPolicy Bypass -File .simchat/scripts/run.ps1` |
| Windows CMD | `.simchat\scripts\run.bat` |
| Linux / macOS / WSL | `bash .simchat/scripts/run.sh` |

选 `1` 等价于第 3 步。

## 4. 为什么会这样

- **为什么不能直接 `python -m simchat.web`**：本体整个收在 `.simchat/` 里，目录名带点，Python 不能把它当包导入。所以统一入口是 [entry.py](../../scripts/entry.py)：它先用 `importlib` 把 `.simchat` 以 `simchat` 之名注册进 `sys.modules`，再转发到真正的入口。`web` → `simchat.web.__main__:main`，`cli` → `simchat.cli.main:main`，`lifecycle` → `simchat.runtime.lifecycle:main`。不带参数时默认就是 `web`。
- **为什么浏览器不会打开一个空白页**：[web/__main__.py](../../web/__main__.py) 起了一个后台线程，每 0.25 秒尝试连接 `127.0.0.1:<port>`，端口真的能连上之后才调浏览器，最多等 20 秒。所以你会看到界面时服务已经就绪。
- **目录关系**：仓库根（`simchat/`）只放 README、`updates.md`、`.gitignore` 这类仓库级文件；本体在 `.simchat/`（`runtime/`、`web/`、`loader/`、`skills/`、`mods/`、`scripts/`、`docs/`）。运行时产生的数据（配置、会话、上传、日志）都在 `.simchat/data/`，已被 `.gitignore` 忽略——删掉它不影响代码，只会丢本地状态。
- 依赖清单里没有 `ollama` Python 库是正常的：本体的 Ollama 后端按需使用它，没装只会让「Ollama（本地）」显示不可用，不影响 OpenAI 兼容服务商。

## 5. 常见坑

- **端口被占用**：终端报 `OSError: [WinError 10048]` 或 `Address already in use`。换端口 `--port 8081`，或找出占用进程后关掉。
- **装了多个 Python，依赖装到了别人身上**：`python -m pip install` 与 `python .simchat/scripts/entry.py web` 必须用同一个解释器。用 `python -c "import sys; print(sys.executable)"` 确认路径，再决定用 `py -3.12` 还是绝对路径。
- **界面能开但终端一片红**：先看报错里第一个 `Traceback`，不要看最后一个。更多排查见 [11 调试与排错](11-debugging.md)。

## 6. 验收清单

- [ ] 终端出现 `[SimChat] Web 界面已启动: http://127.0.0.1:5000`
- [ ] 浏览器能打开界面，注册页可以填用户名，也能跳过
- [ ] 知道 `--port` 怎么改端口，并实际换过一次端口访问成功
- [ ] 知道 `Ctrl+C` 是正常停止方式
- [ ] 能说清仓库根和 `.simchat/` 的关系

已知限制：本章验收项不涉及；完整清单见 [known-limitations.md](../known-limitations.md)。

## 7. 延伸阅读

- [仓库 README](../../../README.md)：目录结构与阶段进度
- [entry.py](../../scripts/entry.py)：包别名注册与子命令分发
- [web/__main__.py](../../web/__main__.py)：启动参数与开窗时机
- [02 接入第一个模型](02-first-model.md)
