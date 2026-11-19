# JRVS-Orbiter

在 `TeleVideo-AI/JRVS-7B-1.2.2`（Qwen3-8B 基座，SFT+LoRA 已合并）上落地 Orbiter 的 `/@` 协议，并用 **`Kirara` 触发词**切换人设。

**默认人设已改为 `SYSTEM "Kirara"`，原先的长段 JRVS 提示不再作为默认。** 长提示与对应的 `Modelfile.orbiter` 保留为遗留对照，不删除。

## 两条落地路径（都已实测）

### 路径 1：派生本地标签（`ollama run` / SimChat 本地实例）

```powershell
# 生成只含触发词的 Modelfile
py tools/render_modelfile.py --system-file prompts/trigger_kirara.txt --temperature 0.7 --out Modelfile.kirara

# 注册（普通 PowerShell；OLLAMA_HOST 指向目标实例）
ollama create jrvs-kirara -f Modelfile.kirara
```

生成的 Modelfile 关键行是 `FROM televideo-ai/JRVS-7B-1.2.2:q4_k_m` + `SYSTEM """Kirara"""`。本地模型的 manifest 是小写 `q4_k_m`，用大写 `Q4_K_M` 在离线环境会找不到标签。

### 路径 2：HTTP 显式覆盖（不建新标签）

```json
{
  "model": "televideo-ai/JRVS-7B-1.2.2:q4_k_m",
  "messages": [
    {"role": "system", "content": "Kirara"},
    {"role": "user", "content": "你是谁？"}
  ]
}
```

`{"role":"system","content":"Kirara"}` 必须放在 messages 首位。

### 触发词 + 协议叠加（可选，单独一版）

```powershell
py tools/render_modelfile.py --system-file prompts/system_kirara_protocol.txt --temperature 0.6 --out Modelfile.kirara-protocol
ollama create jrvs-kirara-protocol -f Modelfile.kirara-protocol
```

`system_kirara_protocol.txt` 的第一行仍然是 `Kirara`，后面才是协议条目。实测叠加**不会削弱**触发词（见下表 C/D），但也没能修复委派格式。

## 协议契约（有出处，不自行发明）

- 输入侧：`.simchat/orbiter-living-space-design.md` §4.2（仅行首识别、`\/@` 转义、`/@all`、未知 id 提示「没有这个住户」）。
- 输出侧：Orbiter README 原案：`/@<模型名> -prompt "<原始需求>"`；带参数时 `/@Niji -mode=image` 单独一行，下一行跟自然语言 spec；技能 `/$ <命令> -dir "..."`；简单问题直接答，复杂的才委派。
- 旧 `jrvs.py parse_router_output` 的 `/@ MODEL:<name> PROMPT:<text>` 只作可选兼容，不是主格式。

| 方向 | 语法 | 说明 |
| --- | --- | --- |
| 用户 → Agent | `/@writer 把这段改掉` | 只在行首生效；投递后正文去掉前缀 |
| 转义 | `\/@writer` | 按普通文本处理 |
| 多 Agent | `/@all ...` | 仅用户可用，模型不得输出 |
| Agent → Agent | `/@<模型名> -prompt "原始需求"` | 委派指令单独成行，无前后缀 |
| Agent → Agent（带参） | `/@Niji -mode=image` + 换行 + spec | 参数行独立成行 |
| Agent → 技能 | `/$ <命令> -dir "<目录>"` | 行首 |

> 规划项，尚未存在：JRVS-390B 及同系列大模型、AWS 月租实例、虚拟化单租户部署。文档里不得写成已有能力。

## 评测结果（2026-11-19，Q4_K_M，8GB 显存，`eval/cases_kirara.jsonl`）

同一套 30 条用例，单次运行，temperature 0.6~0.7。总分存在 ±1~2 条采样噪声，身份触发另做了 3 次重复（每次 6 条），以重复结果为准。

| 配置 | 总分（单次） | 触发强度（3×6 条） | delegation | simple | style | input_prefix |
| --- | --- | --- | --- | --- | --- | --- |
| A `jrvs-kirara`，不传 system（走 Modelfile） | 21/30 (70.0%) | **16/18 (88.9%)** | 1/6 | 7/7 | 3/4 | 3/4 |
| B `jrvs-kirara`，system=`Kirara`（HTTP） | 23/30 (76.7%) | **17/18 (94.4%)** | 1/6 | 6/7 | 3/4 | 4/4 |
| C `jrvs-kirara-protocol`，不传 system | 23/30 (76.7%) | **18/18 (100%)** | 2/6 | 5/7 | 4/4 | 3/4 |
| D 基座标签 + system=`Kirara`+协议（HTTP） | 23/30 (76.7%) | **16/18 (88.9%)** | 1/6 | 6/7 | 3/4 | 4/4 |

结论：

1. **两条路都能稳定激活 Kirara**（自称绮罗、主人sama、颜文字）：重复 3 次后 A 88.9%、B 94.4%、C 100%、D 88.9%。单次 4/6 与 6/6 的差距主要是采样噪声，不能说显式 system 一定更强。
2. **协议叠加不削弱触发词**：C（触发词 + 协议）反而 18/18，style 也从 3/4 升到 4/4。叠加是安全的，推荐用 C 这版。
3. **但协议本身仍然不可用**：委派 1~2/6，主要问题是寒暄前缀、代码块包裹、把 `-prompt` 写成 `-prompt=` 或塞进同一行。提示层到此为止，必须靠 SFT。
4. 模型基础能力有明显缺陷：C 把 `2的10次方` 答成 5,874,693,579；翻译题会输出无关代码。这是原版 SFT 的遗留问题，不是本次改动引入的。

历史对照：旧长提示版在 `eval/cases.jsonl` 上是 22/30（73.3%），用例不同，不能与本表直接相加比较。报告在 `eval/baseline_prompt_only.json`。

评测命令：

```powershell
py eval\run_eval.py --cases eval\cases_kirara.jsonl --model jrvs-kirara --no-system --out eval\kirara_trigger_modelfile.json
py eval\run_eval.py --cases eval\cases_kirara.jsonl --model jrvs-kirara --system-text Kirara --out eval\kirara_trigger_http.json
py eval\run_eval.py --cases eval\cases_kirara.jsonl --model jrvs-kirara-protocol --no-system --out eval\kirara_protocol_modelfile.json
py eval\run_eval.py --cases eval\cases_kirara.jsonl --model jrvs-kirara --system-file prompts\system_kirara_protocol.txt --out eval\kirara_protocol_http.json
```

## Ollama 行为备忘

- `POST /api/create` 不支持 `modelfile` 字段，传了会被静默忽略，只复制基座；必须用 CLI `ollama create -f`（配合 `OLLAMA_HOST`），或在 API 里显式传 `system` / `template` / `parameters`。
- `/api/chat` 会应用 Modelfile 的 `SYSTEM`；显式 system 消息也能覆盖。两者都能稳定触发 Kirara，重复 3 次后差异落在采样噪声内（88.9% vs 94.4%）。
- IDE 沙箱对 `%USERPROFILE%\.ollama` 只读；本地验证时用 `OLLAMA_MODELS` 指向工作区副本、`OLLAMA_HOST` 换端口，避免污染用户的默认模型库。

## 目录

```
jrvs-orbiter/
  prompts/trigger_kirara.txt        触发词（默认人设）
  prompts/system_kirara_protocol.txt  触发词 + 协议叠加版
  prompts/system.txt                旧长提示（遗留对照，不再默认）
  Modelfile.template                Modelfile 模板
  Modelfile.kirara                  路径 1 产物
  Modelfile.kirara-protocol         叠加版产物
  Modelfile.orbiter                 旧长提示版（遗留）
  tools/render_modelfile.py         渲染脚本（--system-file/--out）
  tools/probe.py                    单条探针
  eval/cases_kirara.jsonl           Kirara 版 30 条用例
  eval/cases.jsonl                  旧 JRVS 版用例（遗留）
  eval/run_eval.py                  评测器（--no-system / --system-text / --system-file）
  eval/kirara_*.json                本轮四组报告
  train/                            QLoRA SFT、合并、种子语料
  quant/                            HF → F16 → Q8_0 / Q4_K_M
```

## 量化与显存档位

- F16 GGUF 约 16.5 GB，Q8_0 约 8.7 GB，Q4_K_M 约 5.0 GB。
- 转换与量化全程 CPU，不吃显存；本机 16C/32T + 31GB RAM、磁盘 363GB 空闲，够用。
- 运行：Q4_K_M + 8K ctx 实测占用 5.5GB，40~58 tok/s，可整只驻留 8GB 卡；Q8_0 超出 8GB，会部分卸载到 CPU，只建议归档或大显存机器使用。

## 已知限制与下一步

1. 提示层已到上限，委派格式与分诊必须靠 SFT；训练与量化链路已备好，等语料来源确认。
2. 语料来源未定：轻小说/galgame 原文有版权风险，建议「公有领域 + 自有改写 + 合成对话」；在确认前不扩数据集。
3. 目标规模 2k~5k 条（protocol:identity:style ≈ 5:2:3），AutoDL 4090D 24GB 约 ¥2/小时档，单次 ¥2~6。
4. 达标线建议：触发词身份 6/6，delegation ≥ 90%，simple 不误委派 ≥ 95%；重跑本目录评测对比。
5. `ollama-models/` 是本机隔离测试缓存（约 5GB），已排除出版本控制，不要提交。
