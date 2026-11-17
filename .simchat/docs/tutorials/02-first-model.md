# 02 接入第一个模型

> 本章属于「只使用」路径（A），前置：[01 安装与首次启动](01-install.md)。

## 1. 你会得到什么

输入框不再锁住，顶部模型下拉里能看到具体模型；发一句「你好」能收到逐字流式回复。

```text
模型  ⚡ Auto Model (自动选择最优)  [ollama: qwen3:8b]
      ollama ▸ qwen3:8b
      openai_compat ▸ gpt-4o-mini
```

## 2. 前置条件

- 第 01 章的服务正在运行。
- 下面二选一：
  - **本地模型**：装好 [Ollama](https://ollama.com/)，`python -m pip install ollama`（本体的 Ollama 后端依赖这个 Python 库），并至少拉过一个模型，例如 `ollama pull qwen3:8b`。不需要手动启动 `ollama serve`，SimChat 检测不到服务时会尝试自动拉起。
  - **远程模型**：任意兼容 OpenAI `/chat/completions` 的服务（官方 OpenAI、DeepSeek、通义、硅基流动、自建 vLLM 等）的 Base URL 与 API Key。

## 3. 跟着做

### 3.1 打开服务商配置

界面右上角齿轮按钮（悬停提示「选项」）→ 服务商面板；或者直接点输入框上方提示条里的「配置服务商」。

面板里是一个手风琴列表，`Ollama（本地）` 与 `OpenAI 兼容` 两栏，右侧徽章会显示 `未配置` / `可用` / `异常`。`Auto Model` 不在列表里，它是「自动挑一个可用服务商」的虚拟选项。

### 3.2 路线 A：本地 Ollama

1. 展开「Ollama（本地）」。
2. 展开后先看面板里的说明行。如果写着「未安装 ollama Python 库」，先 `python -m pip install ollama` 并重启服务再看。
3. 「模型」是必填项，输入框会带出本机 `ollama` 已安装的模型作为补全（例如 `qwen3:8b`）；「会话保活」可选，默认 `30m`，表示模型在内存里保留多久。
4. 点「测试连接」——它会实际访问 `http://127.0.0.1:11434/api/tags`。**测试通过会顺手保存**，不需要再点一次保存。
5. 徽章变成绿色「可用」，面板顶部说明会写「Ollama 已连接，模型 xxx 可用」。

### 3.3 路线 B：OpenAI 兼容

1. 展开「OpenAI 兼容」。
2. 填三个字段：

   | 字段 | 是否必填 | 说明 |
   |---|---|---|
   | API Base | 必填 | 兼容 `/chat/completions` 的端点根地址，如 `https://api.openai.com/v1`（不要带 `/chat/completions`） |
   | API Key | 首次必填，之后可留空 | 留空表示「保持已保存的 Key 不变」 |
   | 模型名称 | 必填 | 如 `gpt-4o-mini`；会尝试自动拉取该端点的 `/models` 作为补全 |

3. 先点「测试连接」。想直接保存也可以点「保存并检测」——两者都会落盘并立刻重新检测，区别只是「测试连接」在失败时不会改坏你已经存好的配置。

### 3.4 确认模型下拉

配置成功后，输入框上方的模型下拉会自动填充：

- 第一项永远是 `⚡ Auto Model (自动选择最优)`，括号里会显示它当前会挑谁，例如 `[ollama: qwen3:8b]`。默认选它就行：优先级是本地 Ollama 高于 OpenAI 兼容。
- 下面按 `optgroup` 分组列出每个服务商的模型，格式为 `服务商 ▸ 模型名`。
- 右侧的刷新按钮（悬停「刷新模型列表」）可以强制重新探测，不想等 15 秒缓存时用。

### 3.5 发第一句话

选好模型，输入「你好，用一句话介绍你自己」并发送。预期：文字逐字出现，结束后气泡下方出现复制/重试等操作。

## 4. 为什么会这样

- **服务商检测在验什么**：Ollama 走 `GET /api/tags`，同时判断「配置的模型是否真的装了」（`qwen3:8b` 与 `qwen3:8b:latest` 视为同一模型）；OpenAI 兼容走 `GET {api_base}/models`，超时 2 秒。后者对 404/405 做了兼容：如果返回 `application/json`，说明它是个 API 端点、只是没实现 `/models`，仍判可用；如果返回 HTML，基本可以确定用户把网页地址当成了 API Base，判失败。这一层只有「预检」，真正的对话请求在 `/chat/completions`，所以**预检通过不等于模型一定能回答**。
- **测试结果会被记 30 分钟**：连接测试通过后，若随后几秒内的预检抖动（例如网络瞬断），SimChat 会在 30 分钟窗口内仍认为该服务商可用，避免「刚测通就变红」。
- **模型列表有缓存**：`/models` 结果缓存 15 秒，服务商整体状态缓存 5 秒；点刷新按钮会主动清掉模型缓存。
- **Key 存在哪**：**明文**写在 `.simchat/data/config.json` 的 `providers` 段里，没有加密。该文件已被 `.gitignore` 忽略，但任何能读你磁盘的人都能读到 Key——共用电脑时请注意。界面上重新填写时留空即表示保留原值。
- **输入框为什么还锁着**：服务商可用只是解锁条件之一，另一个是工作目录，见下一章。

## 5. 常见坑

- **Ollama 显示「未安装 ollama Python 库」**：`requirements-simchat.txt` 里没有它，需要单独 `python -m pip install ollama`。装完重启服务。
- **Ollama 显示「无法连接」但 `ollama list` 能跑**：多半是服务的端口不是 11434（例如被 `OLLAMA_HOST` 改过）。SimChat 会读 `OLLAMA_HOST` 环境变量与配置里的 `base_url`；改完重启终端再试。
- **OpenAI 兼容报「无法连接 API 端点」**：检查 Base 是否多写了 `/chat/completions`，或少了 `/v1`。自建服务若只实现了 `/chat/completions` 且 `/models` 返回 HTML 错误页，会被判定为非 API 端点——此时预检过不去，但可以直接保存后试对话。模型下拉为空通常也是因为 `/models` 没返回任何模型，模型名可以手填，下拉只是补全建议。

## 6. 验收清单

- [ ] 服务商徽章变成绿色「可用」
- [ ] 模型下拉出现至少一个具体模型，且 `Auto Model` 显示了解析结果
- [ ] 发一条消息能收到流式回复
- [ ] 刷新页面后模型仍在（说明配置已落盘）
- [ ] 知道 API Key 存在哪个文件、以及它是明文

## 7. 延伸阅读

- [provider_config.py](../../runtime/provider_config.py)：检测、预检、缓存与保存逻辑
- [api-endpoints.md](../api-endpoints.md)：`/api/providers`、`/api/providers/test`、`/api/providers/discover`
- [03 配置工作目录与第一次对话](03-workspace-and-chat.md)
