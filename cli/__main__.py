"""``python -m simchat.cli`` 入口 —— 转到 main.main()。"""

import os
import sys

# 确保 simchat 根在 sys.path，这样 cli 能 import simchat.loader.keys 等纯函数模块
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from simchat.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
