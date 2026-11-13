"""统一启动入口：把 .simchat 目录注册成 simchat 包，再交给原入口执行。

新架构把本体收进 .simchat/，目录名带点，`import simchat` 找不到它，
所以由本文件完成别名注册：

    python scripts/entry.py web [--host 127.0.0.1 --port 5000]
    python scripts/entry.py cli init skill mymod
    python scripts/entry.py lifecycle --guard
"""

import importlib.util
import os
import sys

# 本文件位于 <包根>/scripts/，上一级即 .simchat
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def register_package():
    """把 _PKG_DIR 以 simchat 之名注册进 sys.modules。"""
    if "simchat" in sys.modules:
        return
    parent = os.path.dirname(_PKG_DIR)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(
        "simchat",
        os.path.join(_PKG_DIR, "__init__.py"),
        submodule_search_locations=[_PKG_DIR],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["simchat"] = module
    spec.loader.exec_module(module)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    target = args.pop(0) if args else "web"
    if target in ("web", "serve"):
        entry = "simchat.web.__main__:main"
    elif target == "cli":
        entry = "simchat.cli.main:main"
    elif target == "lifecycle":
        entry = "simchat.runtime.lifecycle:main"
    else:
        print(
            "用法: python scripts/entry.py {web|cli|lifecycle} [参数...]",
            file=sys.stderr,
        )
        return 2

    register_package()
    module_name, func_name = entry.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)(args) or 0


if __name__ == "__main__":
    sys.exit(main())
