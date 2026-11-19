# 训练（AutoDL）

## 路线

Qwen3-8B + LoRA/QLoRA SFT。原版 1.2.2 的配方是 `r=32 / alpha=64 / 7 模块 / seq 1024 / 3 epochs`，在 4090D 24GB 上 1361 条跑了 249 步、约 35 分钟。本目录沿用同一组超参，扩语料后按相同量级估算。

- 默认 QLoRA（4bit NF4 + bf16 计算），24GB 卡留余量；`--no-qlora` 可切 bf16 LoRA。
- 只对 assistant 片段计 loss，system/user 置 -100。
- 使用 Qwen3 chat template 且 `enable_thinking=False`，与线上推理一致。
- 不依赖 `trl`，避免版本漂移。

## 交付物

上传到 AutoDL：

- `train/seeds/*.jsonl`（或扩充后的语料）
- `train/build_dataset.py`、`train/train_lora.py`、`train/merge_lora.py`
- `train/requirements.txt`
- `prompts/system_kirara_protocol.txt`（Kirara 触发词 + 协议叠加；默认人设）

产出：

- `outputs/jrvs-orbiter-lora/`：adapter（几十 MB）
- `merged/jrvs-orbiter-merged/`：合并后的 bf16 HF 目录（约 16GB，回传本机）

## 步骤

```bash
# 0. 环境（AutoDL 镜像一般自带 CUDA 版 torch）
pip install -r requirements.txt

# 1. 构建数据集（system 统一从 prompts/system_kirara_protocol.txt 注入）
#    目录结构要求：prompts/ 与 train/ 同级
python train/build_dataset.py --seeds train/seeds --out train/data
#    如要换 system：--system-file prompts/trigger_kirara.txt

# 2. 训练
python train/train_lora.py \
  --base Qwen/Qwen3-8B \
  --data train/data \
  --out outputs/jrvs-orbiter-lora \
  --epochs 3 --seq-len 1024 \
  --batch 1 --grad-accum 16 --lr 1e-4 \
  --lora-r 32 --lora-alpha 64

# 3. 合并
python train/merge_lora.py \
  --base Qwen/Qwen3-8B \
  --adapter outputs/jrvs-orbiter-lora \
  --out merged/jrvs-orbiter-merged

# 4. 打包回传（约 16GB）
tar -czf jrvs-orbiter-merged.tar.gz merged/jrvs-orbiter-merged
```

回传方式按实例可用性选：JupyterLab 下载、`scp`、或先传对象存储再本机拉。

## 数据集格式

每行一个 JSON，`messages` 必须 user 开头、assistant 结尾，可含多轮：

```json
{"messages":[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}
```

约束：

- 委派样本的 assistant 首字符必须是 `/`，前面不能有任何寒暄。
- 简单任务（翻译、算术、名词解释、闲聊）一律直接回答，用来压制误委派。
- 每类比例建议 protocol:identity:style ≈ 5:2:3。
- 目标规模 2k~5k 条；53 条种子只用于跑通链路。

`build_dataset.py --legacy-compat` 会为 `/@name -prompt "..."` 样本额外生成旧 `MODEL:/PROMPT:` 格式，默认关闭。

## 成本

- 卡型：RTX 4090D 24GB（原版配方同款）。QLoRA 下 8B 模型 + seq 1024 + batch 1 可跑；A100 40GB 更快但更贵。
- 预估：2k~4k 样本 × 3 epochs，1~3 GPU 小时；按 4090D 约 ¥2/小时档位，单次 ¥2~6，加实例存储与下载流量。
- 费用会随 AutoDL 区域和时段浮动，下单前以控制台实时价格为准。

## 语料来源（未决）

轻小说与 galgame 原文不能直接商用/再分发。建议只用：

1. 公有领域文本（版权到期的近代小说）；
2. 自有改写（自己写的场景/对白）；
3. 合成对话（用强模型生成再人工筛）。

在来源确认前，不要扩大数据集；当前种子全部为原创示例。
