"""本体版本号（MOD 的 requires.simchat 以此为准）。

放在 loader 包内的独立叶子模块，保证依赖单向：
web / lifecycle 都只会引用它，不会反向 import 上层。
"""

HOST_VERSION = "2.3.0"
