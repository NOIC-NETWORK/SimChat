# 服务商厂牌化重构方案

> 目标：把「按协议切」的 provider 抽象改成四层结构 —— **厂牌 Vendor / 协议 Transport / 账户 Account / 模型 Model**。
> 本文只描述方案与第一阶段落地范围，不涉及提交与推送。

## 1. 现状盘点

### 1.1 真实可用的接入

| # | 接入 | 传输 | 配置块（`data/config.json`） | 实现位置 |
|---|---|---|---|---|
| 1 | Ollama 本地 | ollama Python 库 | `ollama: {model, keep_alive, options}` | `.simchat/runtime/providers.py:24-60`、`provider_config.py:95-205,252-297` |
| 2 | OpenAI 兼容端点 | `POST {api_base}/chat/completions`（Bearer） | `openai_compat: {api_base, api_key, model_name, verified_at}` | `providers.py:63-120` |
| 3 | Anthropic Messages | `POST {base}/v1/messages`（`x-api-key` + `anthropic-version`） | `anthropic: {api_base, api_key, model_name}` | `providers.py:123-209`（**未提交改动**） |

- 当前 `data/config.json` 实际启用的是第 2 条：阿里云 MaaS 兼容端点 + `qwen-max`。
- `auto` 是虚拟服务商，不持有配置，只按「本地优先」挑当前可用的一项（`provider_config.py:34-38,725-761`）。
- MOD 层 `mods/kirara/services/api_client.py` 自带一套 OpenAI SDK 客户端（dashscope / bigmodel），**不属于本体 provider 体系**，本次不动。

### 1.2 配置组织方式

- 单一文件 `data/config.json`，按**协议名**平铺三个对象：`ollama` / `openai_compat` / `anthropic`；顶层 `provider` 记录首选（`auto` 或协议 id）。
- 字段命名也是按协议：ollama 用 `model`，另两者用 `model_name`；`api_base` 在 openai/anthropic 通用，ollama 用 `base_url`。
- 默认值集中在 `core.py:22-38`（`DEFAULT_CONFIG`），`settings.py` 明确不碰 provider 段。
- 前端把整个 `/api/providers` 响应缓存进 localStorage（`chat.js:261-300`），离线时降级显示。

### 1.3 协议适配点

| 环节 | 位置 |
|---|---|
| 请求构造 / SSE 解析 | `providers.py`（`OllamaProvider` / `OpenAICompatProvider` / `AnthropicProvider`） |
| 连通性预检 | `provider_config._openai_probe` / `_anthropic_probe` |
| 模型列表发现 | `provider_config._openai_models` / `_anthropic_models` / `_ollama_tags` |
| 连接测试（真实 ping） | `provider_config.test`（手写 HTTP，与 provider 类重复） |
| 可用性门禁 | `provider_config.summarize` → `core.resolve_provider` |
| Provider 工厂 | `core._provider`（按 id 字符串硬分派） |
| Web API | `web/__init__.py:410-448`（`/api/providers`、`/test`、`/discover`） |
| 前端表单 / 手风琴 / 模型下拉 | `web/static/js/chat.js:973-1470` |
| UI 方块材质 / 预设 | `runtime/ui_blocks.py` |
| 通讯通道模型选择 | `runtime/comms.py:45-53,73-81`（下拉只列 `openai_compat` / `ollama`） |
| Agent 后端 | `runtime/agent/backend.py:22-76` |
| Orbiter | `runtime/agent/tools.py:1248-1415`（本地固定 ollama，云端固定 `openai_compat`） |

### 1.4 直接假设「OpenAI 兼容」的位置

1. `core._provider`：`if name == "openai_compat"` 字符串分派，未知 id 一律回落到 Ollama（`core.py:75-80`）。
2. `provider_config.REAL_PROVIDER_IDS` / `PROVIDER_RANK`：写死三元组（`provider_config.py:36-38`），`save/test/discover` 均按此校验。
3. `OpenAICompatProvider`：URL 固定 `api_base + "/chat/completions"`、鉴权固定 `Authorization: Bearer`、无 query、无方言（`providers.py:81,94-97`）。
4. `_openai_probe/_openai_models`：只认 `GET {base}/models` + Bearer。
5. `test()`：OpenAI 分支重复拼 URL、鉴权、payload，与 provider 类各写一份。
6. 前端：`discoverTriggers` 与字段名 `api_base/api_key/model_name` 硬编码（`chat.js:1396-1404`）；列表按 provider id 渲染。
7. `comms.py`：模型服务商下拉只有两个协议项。
8. Orbiter：云端委派固定 `provider='openai_compat'`，模型校验直接读 `core.config['openai_compat']`。
9. `ui_blocks.register_preset`：provider 白名单只有协议 id。

### 1.5 三个未提交 Anthropic 改动（结论：同方向，保留）

| 文件 | 改动内容 | 判定 |
|---|---|---|
| `runtime/providers.py` | 新增 `AnthropicProvider`（Messages API 流式解析、system 抽取、错误事件） | 纯 Transport 适配器，正是四层里的协议层，**保留复用** |
| `runtime/provider_config.py` | Anthropic 的 base 规范化、headers、预检、模型发现、detect/save/test/discover 分支 | 属于「第三协议接入」，与厂牌化不冲突，**保留**；其中「协议 id 即 provider id」的写法会在本次改造中被厂牌解析层包住 |
| `runtime/ui_blocks.py` | 新增 `provider.anthropic` 方块、预设白名单扩到三元组 | 同方向，**保留** |

结论：三个改动全部保留，本次改造在其上**扩展**，不重写、不回退。Anthropic 传输在本方案中继续作为独立 Transport 存在。

## 2. 四层模型

### 2.1 分层职责

- **Vendor（厂牌）**：用户认知单位。`id`、`label`、`transport`、`default_base`、`auth`、`models`（静态建议清单）、`dialect`（参数方言）、`implemented`。
- **Transport（协议）**：请求/响应适配器。一期只有 `ollama` / `openai_compat` / `anthropic`；`bedrock` 只登记不实现。
- **Account（账户）**：一组凭据与端点。`vendor` + `base_url` + `api_key` + `region` + `params` + `auth/query` 覆盖。
- **Model（模型）**：挂在厂牌/账户下的模型 id + 能力标记 + 参数方言覆盖。

### 2.2 厂牌注册表（`runtime/vendors.py`）

```jsonc
{
  "id": "dashscope",
  "label": "阿里云百炼",
  "transport": "openai_compat",
  "default_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "auth": "bearer",
  "implemented": true,
  "models": [
    {"id": "qwen-max", "notes": "百炼通用旗舰"},
    {"id": "qwen3-235b-a22b", "params": {"enable_thinking": false}}
  ],
  "dialect": {
    "param_whitelist": ["enable_thinking", "top_p", "temperature", "max_tokens", "seed", "stop"],
    "notes": ["enable_thinking 仅 Qwen3 系列支持，默认不下发"]
  }
}
```

一期登记清单：

| 厂牌 id | 显示名 | Transport | 默认 Base | 备注 |
|---|---|---|---|---|
| `ollama` | Ollama（本地） | ollama | `http://127.0.0.1:11434` | 原生 API |
| `openai` | OpenAI | openai_compat | `https://api.openai.com/v1` | 官方 |
| `anthropic` | Anthropic | anthropic | `https://api.anthropic.com` | 官方 |
| `dashscope` | 阿里云百炼 | openai_compat | `.../compatible-mode/v1` | `enable_thinking` 方言 |
| `volcengine` | 火山方舟 | openai_compat | `https://ark.cn-beijing.volces.com/api/v3` | 模型 id 为 `ep-` 接入点 |
| `qianfan` | 百度千帆 | openai_compat | `https://qianfan.baidubce.com/v2` | OpenAI 兼容 v2 |
| `azure_openai` | Azure OpenAI | openai_compat | 由用户填 `.../openai/deployments/<name>` | `api-key` 头 + `api-version` query |
| `siliconflow` | 硅基流动 | openai_compat | `https://api.siliconflow.cn/v1` | |
| `deepseek` | DeepSeek | openai_compat | `https://api.deepseek.com/v1` | |
| `custom_openai` | 自定义 OpenAI 兼容 | openai_compat | 空 | 兜底厂牌 |
| `aws_bedrock` | AWS Bedrock | bedrock（规划） | 区域端点 | `implemented: false`，不生成可用项 |

### 2.3 账户与模型怎么挂（已确认：只做全局账户）

- **一期（本次）**：账户层以「兼容适配器」形式存在，且**只做全局单账户**。配置仍写回旧协议块，块内新增可选 `vendor` 字段记录该账户属于哪个厂牌；读取时经 `vendors.resolve_target()` 归一化成 `{vendor, transport, base_url, api_key, model, params, auth, query}`。
- **不做的事**：不新增 `accounts` 数组、不做账户级命名空间、不做实例绑定账户——当前尚未接入任何认证方式，提前搭多账户结构属于过度设计。
- **同协议多厂牌**：注册表层面默认允许（`openai_compat` 下可登记任意多个厂牌），但同一时刻仍只有一个全局账户，切换厂牌即切换该账户的端点与方言；真正的并行多账户等认证体系落地后再做。

### 2.4 旧配置兼容

- 不改旧键名、不迁移、不删除 `verified_at` / `options` / `keep_alive`。
- 旧配置不写 `vendor` 时按 `api_base` 主机名推断厂牌（`volces.com` → 火山、`aliyuncs.com/dashscope` → 百炼、`baidubce.com` → 千帆、`openai.azure.com` → Azure、`api.openai.com` → OpenAI、其他 → 自定义）。
- `provider` 字段继续接受 `ollama` / `openai_compat` / `anthropic` / `auto`；新增厂牌 id 作为**别名**接受（`/api/providers`、`/test`、`/discover`、`/api/chat` 的 `provider`）。
- `summarize()` 返回结构只增字段（`vendor` / `vendor_label` / `transport` / 顶层 `vendors`），不改既有字段语义，前端旧缓存不受影响。

## 3. 方言差异处理

| 场景 | 处理 |
|---|---|
| 火山 `ep-` 接入点 | 不重写模型 id；`dialect.model_id_pattern = "^ep-"`，表单提示「填推理接入点 ID」。 |
| 百炼 `enable_thinking` | 只在账户 `params` 显式给出时下发；默认不下发，避免非 Qwen3 模型报错。 |
| Azure `api-version` | 账户 `api_version` 字段 → 追加 query；鉴权切 `api-key` 头；base 允许含 `/openai/deployments/<deployment>`。 |
| 千帆 | 默认 base 指向 `/v2`，路径沿用 `/chat/completions`。 |
| Bedrock SigV4 / 模型 id | 只登记，不实现；选择时明确报「尚未实现（规划中）」，不做假实现。 |
| 重复惩罚 | openai_compat：`repeat_penalty` → `frequency_penalty`（现有映射保留）；anthropic：忽略。 |
| 不认识的参数 | 每个 Transport 维护参数白名单；白名单外的键**丢弃并记一条 warning**，不中断请求；`messages/model/stream` 等协议关键字段禁止被覆盖。 |

## 4. 读取路径改造（一期）

1. 新增 `runtime/vendors.py`：注册表 + `transport_of()` / `block_of()` / `infer_vendor()` / `resolve_target()`。
2. `providers.py`：新增 `create_provider(transport, conf)` 工厂；`OpenAICompatProvider` 支持 `auth` / `api_version` / `params` 白名单；`AnthropicProvider` 支持参数白名单。
3. `core._provider`：改为「id/厂牌 → transport → 工厂」，不再字符串硬分派。
4. `provider_config`：
   - `detect_*` 增加厂牌元数据，显示名改为厂牌名（`openai_compat` 项显示「阿里云百炼」等，id 保持不变）。
   - `summarize` 增加顶层 `vendors` 与 `vendor`。
   - `save/test/discover` 接受厂牌 id 别名；保存 openai 块时写入 `vendor`。
   - 连接测试改为复用统一的 URL/鉴权/query 规则（Azure 可用）。
5. Web 层：`/api/providers/discover` 白名单改为「transport 可解析」。
6. Orbiter / 通讯 / Agent 后端：不改调用契约（仍传 `ollama` / `openai_compat`），只受益于底层方言支持；`resolve_provider` 对厂牌 id 做归一化。

## 5. UI 方案与成本

- **低成本（一期一起改）**：服务商手风琴标题改为显示厂牌名（`provider.label` 优先于方块材质）；模型下拉的 optgroup 自动变成厂牌名；新增主机内置厂牌预设芯片（百炼 / 火山 / 千帆 / Azure / OpenAI / Anthropic），点击预填 base_url。
- **高成本（二期单列）**：真正「厂牌 → 账户 → 模型」两级分组 UI（左侧厂牌列表 + 右侧账户卡片 + 账户级模型清单）、多账户管理页。涉及布局重写与新增接口，不与一期混做。

## 6. 验证方式

- 纯代码级：模块导入、`vendors` 解析样例、`save()` 写临时目录后回读、`core._provider()` 构造类型、`node --check chat.js`、`config.json` JSON 合法性。
- 不启动 Web 服务；不触碰真实 `data/config.json`。

## 7. 已确认的产品决策

1. **保留「协议直选」**：UI 默认按厂牌展示，`openai_compat` / `anthropic` / `ollama` 仍可作为高级入口直选。
2. **账户只做全局**：当前未接入任何认证方式，不提前搭多账户结构；一期不新增 `accounts`。
3. **同协议多厂牌默认允许**：注册表层面不限制同协议厂牌数量；受全局单账户约束，同一时刻实际生效的仍是一个端点，切换即换厂牌。

## 8. 分期计划

- **一期（本次落地）**：厂牌注册表、三协议映射、读取路径归一化、旧配置兼容、厂牌显示名与预设芯片。
- **二期（待认证体系落地后）**：账户数据层、同协议多账户并行、账户级模型清单、厂牌两级 UI。
- **三期**：Bedrock SigV4、按模型能力声明做参数自动裁剪（thinking / vision / tools）。

## 9. 一期落地清单（已完成，未提交）

| 文件 | 改动 |
|---|---|
| `runtime/vendors.py`（新增） | 厂牌注册表、`transport_of/block_of/infer_vendor/vendor_for_conf/resolve_target` |
| `runtime/providers.py` | `create_provider()` 工厂；OpenAI 兼容支持 `auth=api-key`、`api_version`、`params` 白名单；Anthropic 参数白名单；bedrock 明确报未实现 |
| `runtime/provider_config.py` | `detect_*` 增加厂牌元数据与厂牌名；`summarize` 增加 `vendor/vendors`；`save/test/discover/mark_verified` 接受厂牌 id；保存 openai 块写入 `vendor/auth/api_version`；Azure 必填 api-version |
| `runtime/core.py` | `_provider` 走 `vendors.resolve_target` + 工厂；`resolve_provider` 归一化厂牌 id |
| `runtime/ui_blocks.py` | 由注册表生成厂牌预设芯片；`register_preset` 接受厂牌 id |
| `runtime/agent/tools.py` | Orbiter 模型校验带上厂牌鉴权/query（Azure 可用） |
| `web/__init__.py` | `/api/providers/discover` 白名单改为「协议可解析」 |
| `web/static/js/chat.js` | 服务商标题优先显示厂牌名 |
| `docs/api-endpoints.md` | 补充厂牌 id 与新增配置字段 |

验证：模块编译通过；47 项离线检查全部通过（厂牌解析、旧配置读取、保存/拒绝、Azure 方言、参数降级、core 工厂、UI 预设、真实 config.json 只读形状兼容）；`node --check chat.js` 通过；未启动服务、未改动真实 `data/config.json`。
