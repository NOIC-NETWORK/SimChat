# -*- coding: utf-8 -*-
"""把 LoRA adapter 合并回基座，输出可直接转 GGUF 的 HF 目录。

在 AutoDL 上执行（CPU 合并即可，约需 16GB 内存 + 16GB 磁盘）：
    python merge_lora.py --base Qwen/Qwen3-8B --adapter outputs/jrvs-orbiter-lora \
        --out merged/jrvs-orbiter-merged
"""
from __future__ import annotations

import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-8B")
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-shard", default="4GB")
    args = ap.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.bfloat16, trust_remote_code=True, device_map="cpu",
    )
    model = PeftModel.from_pretrained(base, args.adapter, torch_dtype=torch.bfloat16)
    model = model.merge_and_unload()
    model.save_pretrained(args.out, safe_serialization=True, max_shard_size=args.max_shard)
    tokenizer.save_pretrained(args.out)
    print("merged ->", args.out)


if __name__ == "__main__":
    main()
