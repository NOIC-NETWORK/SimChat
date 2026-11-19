# -*- coding: utf-8 -*-
"""单条探针：手动确认 system 触发词/协议叠加的效果。

用法：
    py tools/probe.py --model jrvs-orbiter --system Kirara --prompt "你是谁？"
    py tools/probe.py --model jrvs-orbiter --system-file prompts/system_kirara.txt --prompt "..."
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="jrvs-kirara")
    ap.add_argument("--host", default="http://127.0.0.1:11435")
    ap.add_argument("--system", default=None, help="system 内容；不传则不带 system")
    ap.add_argument("--system-file", default=None)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--num-ctx", type=int, default=8192)
    args = ap.parse_args()

    system = args.system
    if args.system_file:
        system = pathlib.Path(args.system_file).read_text(encoding="utf-8").strip()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": args.prompt})

    body = json.dumps({
        "model": args.model,
        "stream": False,
        "options": {"temperature": args.temperature, "top_p": 0.9, "num_ctx": args.num_ctx},
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(args.host.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print(data["message"]["content"])


if __name__ == "__main__":
    main()
