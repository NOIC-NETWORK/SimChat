# -*- coding: utf-8 -*-
"""Qwen3-8B + LoRA/QLoRA SFT（在 AutoDL 上运行）。

设计取舍：
- 只训练 assistant 片段：system + user 的 token 置为 -100；
- 使用 Qwen3 chat template 且 enable_thinking=False，与线上推理模板一致；
- 默认 QLoRA（4bit NF4），24GB 卡也能留出余量；--no-qlora 则用 bf16 LoRA；
- 不依赖 trl，避免版本漂移，训练/评测全部用 transformers + peft。

用法（AutoDL）：
    python train_lora.py --base Qwen/Qwen3-8B --data data \
        --out outputs/jrvs-orbiter-lora --epochs 3 --seq-len 1024 \
        --batch 1 --grad-accum 16 --lr 1e-4
"""
from __future__ import annotations

import argparse
import json
import pathlib

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          DataCollatorForSeq2Seq, Trainer, TrainingArguments)

TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]


def render(tokenizer, messages, add_generation_prompt=False):
    kwargs = dict(tokenize=False, add_generation_prompt=add_generation_prompt)
    try:
        return tokenizer.apply_chat_template(messages, enable_thinking=False, **kwargs)
    except TypeError:
        return tokenizer.apply_chat_template(messages, **kwargs)


def build_features(tokenizer, path, seq_len):
    rows = load_dataset("json", data_files=str(path), split="train")
    features = []
    mask_fallback_warned = False

    for item in rows:
        messages = item["messages"]
        full_text = render(tokenizer, messages, add_generation_prompt=False)
        prompt_text = render(tokenizer, messages[:-1], add_generation_prompt=True)

        full = tokenizer(full_text, add_special_tokens=False, truncation=True, max_length=seq_len)
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        input_ids = full["input_ids"]
        labels = list(input_ids)

        if input_ids[:len(prompt_ids)] == prompt_ids:
            labels[:len(prompt_ids)] = [-100] * len(prompt_ids)
        elif not mask_fallback_warned:
            print("[warn] prompt 前缀 token 对不上，样本退回整段 loss")
            mask_fallback_warned = True

        if all(x == -100 for x in labels):
            continue
        features.append({
            "input_ids": input_ids,
            "attention_mask": full["attention_mask"],
            "labels": labels,
        })

    if not features:
        raise SystemExit("no usable samples in %s" % path)
    return features


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-8B")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs/jrvs-orbiter-lora")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--seq-len", type=int, default=1024)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=32)
    ap.add_argument("--lora-alpha", type=int, default=64)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--no-qlora", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = pathlib.Path(args.data)
    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    print("tokenizing:", data_dir / "train.jsonl")
    train_features = build_features(tokenizer, data_dir / "train.jsonl", args.seq_len)
    val_path = data_dir / "val.jsonl"
    val_features = build_features(tokenizer, val_path, args.seq_len) if val_path.exists() else None
    print("train=%d val=%s" % (len(train_features), len(val_features) if val_features else 0))

    load_kwargs = {"torch_dtype": torch.bfloat16, "trust_remote_code": True}
    if not args.no_qlora:
        from transformers import BitsAndBytesConfig
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
        )
        load_kwargs["device_map"] = {"": 0}
    model = AutoModelForCausalLM.from_pretrained(args.base, **load_kwargs)
    model.config.use_cache = False

    if not args.no_qlora:
        model = prepare_model_for_kbit_training(model)
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()

    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        target_modules=TARGET_MODULES, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    collator = DataCollatorForSeq2Seq(
        tokenizer, model=model, padding=True, pad_to_multiple_of=8, label_pad_token_id=-100,
    )

    optim = "adamw_torch"
    if not args.no_qlora:
        try:
            import bitsandbytes  # noqa: F401
            optim = "paged_adamw_8bit"
        except ImportError:
            pass

    training_args = TrainingArguments(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=2,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        optim=optim,
        seed=args.seed,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_features,
        eval_dataset=val_features,
        data_collator=collator,
    )
    trainer.train()

    print("final eval:", trainer.evaluate() if val_features else "skipped (no val.jsonl)")
    trainer.save_model(args.out)
    tokenizer.save_pretrained(args.out)
    with (pathlib.Path(args.out) / "train_args.json").open("w", encoding="utf-8") as fh:
        json.dump(vars(args), fh, ensure_ascii=False, indent=2)
    print("adapter saved:", args.out)


if __name__ == "__main__":
    main()
