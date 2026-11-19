# -*- coding: utf-8 -*-
"""JRVS-Orbiter 协议评测。

默认把 prompts/system_kirara_protocol.txt 作为 system 消息显式传给 /api/chat。
Ollama 的 chat 接口会应用 Modelfile 的 SYSTEM，但同一触发词用显式 system 传入时
更稳定（实测 6/6 vs 4/6），评测默认走显式路径，与 SimChat 宿主的调用方式一致。

用法：
    py eval/run_eval.py --cases eval/cases_kirara.jsonl --model jrvs-kirara --no-system
    py eval/run_eval.py --model jrvs-kirara --system-text Kirara
    py eval/run_eval.py --model jrvs-kirara-protocol --no-system
    py eval/run_eval.py --model jrvs-kirara --system-file prompts/system_kirara_protocol.txt
    py eval/run_eval.py --model jrvs-orbiter --category delegation
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_system():
    return (ROOT / "prompts" / "system_kirara_protocol.txt").read_text(encoding="utf-8").strip()


def load_cases(path):
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def call_ollama(host, model, system, prompt, temperature=0.6, num_ctx=8192, timeout=300):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model,
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.9, "num_ctx": num_ctx},
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"], data


def check_one(text, spec):
    t = (text or "").strip()
    low = t.lower()
    kind = spec["type"]
    if kind == "contains":
        return any(v.lower() in low for v in spec["any"])
    if kind == "not_contains":
        return not any(v.lower() in low for v in spec["any"])
    if kind == "regex":
        return re.search(spec["pattern"], t, re.MULTILINE) is not None
    if kind == "not_regex":
        return re.search(spec["pattern"], t, re.MULTILINE) is None
    if kind == "max_chars":
        return len(t) <= spec["value"]
    if kind == "max_lines":
        return len(t.splitlines()) <= spec["value"]
    raise ValueError("unknown check type: " + kind)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="jrvs-orbiter")
    ap.add_argument("--host", default="http://127.0.0.1:11435")
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.jsonl"))
    ap.add_argument("--category", default=None)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--no-system", action="store_true", help="不传 system，观察裸模型/Modelfile 兜底")
    ap.add_argument("--system-text", default=None, help="直接指定 system 内容（如 Kirara）")
    ap.add_argument("--system-file", default=None, help="从文件读取 system 内容")
    ap.add_argument("--out", default=str(ROOT / "eval" / "last_report.json"))
    args = ap.parse_args()

    if args.no_system:
        system = ""
    elif args.system_file:
        system = pathlib.Path(args.system_file).read_text(encoding="utf-8").strip()
    elif args.system_text is not None:
        system = args.system_text
    else:
        system = load_system()
    cases = load_cases(pathlib.Path(args.cases))
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]

    stats = defaultdict(lambda: [0, 0])
    results = []
    for i, case in enumerate(cases, 1):
        started = time.time()
        try:
            text, raw = call_ollama(args.host, args.model, system, case["prompt"],
                                    temperature=args.temperature, num_ctx=args.num_ctx)
            failure = None
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            text, raw, failure = "", {}, "request failed: %s" % exc

        checks = []
        if failure is None:
            for spec in case["checks"]:
                ok = check_one(text, spec)
                checks.append({"spec": spec, "ok": ok})
                if not ok:
                    failure = failure or "check failed: %s" % json.dumps(spec, ensure_ascii=False)

        passed = failure is None
        bucket = stats[case["category"]]
        bucket[0] += 1 if passed else 0
        bucket[1] += 1

        results.append({
            "id": case["id"],
            "category": case["category"],
            "prompt": case["prompt"],
            "output": text,
            "passed": passed,
            "failure": failure,
            "checks": checks,
            "elapsed_s": round(time.time() - started, 2),
            "eval_count": raw.get("eval_count"),
            "eval_duration_s": round(raw.get("eval_duration", 0) / 1e9, 2),
        })
        print(("[PASS] " if passed else "[FAIL] ") + case["id"] +
              ("" if passed else "  <- " + str(failure)))
        if not passed:
            print("       out: " + text.replace("\n", " / ")[:220])

    total_pass = sum(v[0] for v in stats.values())
    total = sum(v[1] for v in stats.values())
    print("\n== summary: %d/%d (%.1f%%) ==" % (total_pass, total, 100.0 * total_pass / max(total, 1)))
    for cat in sorted(stats):
        p, n = stats[cat]
        print("  %-14s %d/%d" % (cat, p, n))

    report = {
        "model": args.model,
        "host": args.host,
        "system_passed": bool(system),
        "temperature": args.temperature,
        "num_ctx": args.num_ctx,
        "total": {"passed": total_pass, "count": total},
        "by_category": {k: {"passed": v[0], "count": v[1]} for k, v in sorted(stats.items())},
        "results": results,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report:", out)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
