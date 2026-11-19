# -*- coding: utf-8 -*-
"""把种子语料规范化成 SFT 数据集。

- 统一注入 prompts/system_kirara_protocol.txt 作为 system 消息（训练与推理使用同一份规则）；
- 校验角色、空内容、尾条必须是 assistant；
- 按 user+assistant 归一化后去重；
- 固定种子切分 train/val；
- 可选 --legacy-compat：为委派样本额外生成一份 `/@ MODEL:<id> PROMPT:<text>`
  兼容样本（旧 jrvs.py 解析器格式），默认关闭。

用法：
    python build_dataset.py --seeds seeds --out data
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import re

ROOT = pathlib.Path(__file__).resolve().parent


def load_system(path):
    return pathlib.Path(path).read_text(encoding="utf-8").strip()


def norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def legacy_variant(messages):
    """把 `/@name -prompt "..."` 转成旧解析器格式；不匹配返回 None。"""
    last = messages[-1]["content"].strip()
    m = re.fullmatch(r'/@\s*(\S+)\s+-prompt\s+"(.*)"', last, re.DOTALL)
    if not m:
        return None
    clone = [dict(x) for x in messages]
    clone[-1]["content"] = "/@ MODEL:%s PROMPT:%s" % (m.group(1), m.group(2))
    return clone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=str(ROOT / "seeds"))
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--system-file", default=str(ROOT.parent / "prompts" / "system_kirara_protocol.txt"),
                    help="注入的 system；默认是 Kirara 触发词 + 协议叠加版")
    ap.add_argument("--legacy-compat", action="store_true")
    args = ap.parse_args()

    system = load_system(args.system_file)
    seed_dir = pathlib.Path(args.seeds)
    files = sorted(seed_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit("no seed jsonl under %s" % seed_dir)

    seen = set()
    samples = []
    dropped = {"dup": 0, "bad": 0}
    legacy_added = 0

    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                messages = item["messages"]
            except (ValueError, KeyError) as exc:
                dropped["bad"] += 1
                print("bad line %s:%d %s" % (path.name, lineno, exc))
                continue

            ok = (isinstance(messages, list) and len(messages) >= 2 and
                  all(m.get("role") in ("system", "user", "assistant") and str(m.get("content", "")).strip()
                      for m in messages) and
                  messages[-1]["role"] == "assistant")
            if not ok:
                dropped["bad"] += 1
                print("bad sample %s:%d" % (path.name, lineno))
                continue

            messages = [m for m in messages if m["role"] != "system"]
            variant = messages
            if args.legacy_compat:
                legacy = legacy_variant(messages)
                if legacy:
                    variant = legacy
                    legacy_added += 1

            key = hashlib.sha1((norm(variant[0]["content"]) + "|" +
                                norm(variant[-1]["content"])).encode("utf-8")).hexdigest()
            if key in seen:
                dropped["dup"] += 1
                continue
            seen.add(key)

            samples.append([{"role": "system", "content": system}] + variant)

    rng = random.Random(args.seed)
    rng.shuffle(samples)
    val_n = max(1, int(len(samples) * args.val_ratio)) if len(samples) > 4 else 0
    val, train = samples[:val_n], samples[val_n:]

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("val.jsonl", val)):
        with (out / name).open("w", encoding="utf-8") as fh:
            for msgs in rows:
                fh.write(json.dumps({"messages": msgs}, ensure_ascii=False) + "\n")

    total_tokens_hint = sum(len(m["content"]) for msgs in samples for m in msgs)
    print("files:", ", ".join(p.name for p in files))
    print("samples: %d (train %d / val %d)" % (len(samples), len(train), len(val)))
    print("dropped: dup=%d bad=%d" % (dropped["dup"], dropped["bad"]))
    print("legacy-compat added: %d" % legacy_added)
    print("approx chars: %d" % total_tokens_hint)
    print("written:", out / "train.jsonl", out / "val.jsonl")


if __name__ == "__main__":
    main()
