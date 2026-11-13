# SimChat 启动器（.simchatLc）

编译 launcher.cpp 以后，可以得到一个适配系统的启动器。

.net 架构无法跨平台，tk 太笨重，是时候请出老师傅了——我要用我三年级学 NOIP 的本事，向你们发起最后的挑战。

注：传统 dev-c++ 用的是 mingw，这里统一改成 CMake 构建。CMake 只是构建系统，工具链仍然是 MinGW / MSVC / Clang 自己挑；这么改是为了不再把编译器和工程绑死，换平台不用重写工程文件。

## 目录结构

```
simchat/
├── launcher.cpp              # 入口：解析参数 → 找解释器 → 起本体 → 建窗口
├── .simchatLc/
│   ├── readme.md             # 本文
│   └── _includes/
│       ├── Compile.h         # 编译期探测：平台 / 编译器 / 宏收敛
│       └── process.h         # 子进程：创建、重定向、回收、端口探活
└── .simchat/                 # 本体：Python 包 + scripts/entry.py
```

启动器只负责“把它跑起来”，业务逻辑一律不碰。本体是 `.simchat/` 里的 Python 包，目录名带点，不能直接 `import simchat`，所以统一走 `scripts/entry.py` 注册别名后再进原入口。

## 和本体的契约

启动器只认这一条命令：

```
python .simchat/scripts/entry.py web [--host 127.0.0.1] [--port 5000]
```

- 退出码 0 = 用户主动结束；非 0 = 启动失败，窗口里原样显示 stderr，不要吞。
- 默认监听 `127.0.0.1:5000`；端口已被占用就不再拉第二个实例（判断规则沿用 `runtime/lifecycle.py` 里的端口探活），窗口直接指向现有服务。
- 浏览器、日志、守护进程由本体自己管，启动器不做重复的事。

另外两个子命令是给高级用户和系统自启项用的，启动器一般用不到：

```
python .simchat/scripts/entry.py cli <init|pack|verify|publish|gen-key|list> ...
python .simchat/scripts/entry.py lifecycle <--boot|--guard|--status|--stop>
```

## 构建

```
cmake -S . -B build
cmake --build build --config Release
```

Windows 下要 GUI 子系统，别带控制台黑框：

```cmake
add_executable(simchat-launcher WIN32 launcher.cpp)
```

## 现状

- [x] 工程落位：launcher.cpp、.simchatLc/_includes 占位
- [ ] 解释器探测（PATH → `py`/`python3` → 失败时给安装指引）
- [ ] process.h：CreateProcess / posix_spawn 封装，stdout+stderr 合并重定向到日志
- [ ] createWindow：状态窗口（运行中 / 监听地址 / 退出码 / 重启按钮）
- [ ] 单实例锁：同一端口只允许一个启动器
