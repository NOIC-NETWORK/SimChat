# -*- coding: utf-8 -*-
"""从 prompts/system.txt 渲染 Modelfile.orbiter，避免系统提示词两处漂移。

用法：
    py tools/render_modelfile.py
    py tools/render_modelfile.py --base /path/to/jrvs-7b-merged.gguf --num-ctx 8192
"""
import argparse
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="televideo-ai/JRVS-7B-1.2.2:q4_k_m",
                    help="Modelfile 的 FROM 目标（Ollama 标签或本地 GGUF 路径）")
    ap.add_argument("--system-file", default=str(ROOT / "prompts" / "system.txt"),
                    help="SYSTEM 来源文件")
    ap.add_argument("--temperature", default="0.6")
    ap.add_argument("--num-ctx", default="8192")
    ap.add_argument("--out", default=str(ROOT / "Modelfile.orbiter"))
    args = ap.parse_args()

    system = pathlib.Path(args.system_file).read_text(encoding="utf-8").strip()
    template = (ROOT / "Modelfile.template").read_text(encoding="utf-8")
    if '"""' in system:
        raise SystemExit("system.txt 不能包含三引号，否则会截断 Modelfile")

    text = (template
            .replace("{BASE_MODEL}", args.base)
            .replace("{SYSTEM_PROMPT}", system)
            .replace("{TEMPERATURE}", args.temperature)
            .replace("{NUM_CTX}", args.num_ctx))
    # 模板里的 {{{{ }}}} 是给 str.format 之外的双大括号转义，这里还原成 Ollama 语法
    text = text.replace("{{{{", "{{").replace("}}}}", "}}")

    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print("written:", args.out)


if __name__ == "__main__":
    main()
