# SimChat 启动器（.simchatLc）

编译 `.simchatLc/launcher.cpp`，得到一个 `simchatLc` 可执行文件。它是 SimChat 唯一的启动入口，用来取代 `run.bat` / `run.ps1` / `run.sh`。

.net 架构无法跨平台，tk 太笨重，是时候请出老师傅了——我要用我三年级学 NOIP 的本事，向你们发起最后的挑战。

注：传统 dev-c++ 用的是 mingw，这里统一改成 CMake 构建。CMake 只是构建系统，工具链仍然是 MinGW / MSVC / Clang 自己挑；这么改是为了不再把编译器和工程绑死，换平台不用重写工程文件。

启动器只负责"把它跑起来"，业务逻辑一律不碰。本体是 `.simchat/` 里的 Python 包，目录名带点，不能直接 `import simchat`，所以统一走 `scripts/entry.py` 注册别名后再进原入口。

## 为什么换掉三个启动脚本

现有三份脚本各写一遍 Python 探测、依赖检查、菜单和退出处理，改一处要改三处，而且都没解决真正的痛点：

| 现状 | 后果 |
|---|---|
| 三份脚本重复实现同一套逻辑 | 行为漂移，Windows 与 Unix 的探测顺序不一致 |
| 双击后先弹一个控制台黑框，再选菜单 | 普通用户拿到的是一个终端；误关终端 = 服务被杀 |
| 只把日志打到 stdout | 窗口一关，报错信息就没了，只能靠复现 |
| 没有单实例 | 端口被占时只会打印一行英文报错，用户以为启动失败 |
| 停止方式 = Ctrl+C 或直接杀进程 | 守护进程把它当崩溃，几秒后又拉起来，形成"关不掉"的错觉 |

`simchatLc` 用一个原生窗口把这些补上：探测、启动、健康检查、日志、停止、重启全在一个窗口里完成；CLI 与 lifecycle 原样透传，不重新发明。

## 目录结构

启动器的所有源码、工程文件、资源全部收在本目录，仓库根目录不再放任何 `.cpp`：

```
simchat/
├── .simchatLc/
│   ├── readme.md                # 本文
│   ├── CMakeLists.txt           # 唯一的构建入口
│   ├── launcher.cpp             # 基座：WinMain / 参数解析 / 状态机编排
│   ├── _includes/
│   │   ├── Compile.h            # 编译期探测：平台 / 编译器 / 宏收敛
│   │   ├── app.h                # LaunchOptions / LaunchState
│   │   ├── child_process.h      # 子进程：创建、管道、回收、信号
│   │   ├── python.h             # 解释器探测与版本校验
│   │   ├── net.h                # /api/health 探活
│   │   ├── text.h               # UTF-8 ↔ UTF-16
│   │   └── window.h             # 状态窗口：创建、日志追加、按钮回调
│   ├── src/
│   │   ├── window_win32.cpp     # Windows 窗口实现（Win32 + 通用控件）
│   │   ├── process_win32.cpp    # CreateProcessW + 匿名管道读取
│   │   ├── process_posix.cpp    # fork/exec + pipe（P2，未在 Windows 编译）
│   │   ├── python_win32.cpp     # PATH 扫描 + `-c` 版本校验
│   │   ├── net_win32.cpp        # WinHTTP GET /api/health
│   │   └── text.cpp             # MultiByteToWideChar / WideCharToMultiByte
│   ├── resources/
│   │   ├── launcher.rc          # 图标 + manifest 引用
│   │   ├── app.manifest         # PerMonitorV2 DPI + 通用控件 v6
│   │   └── simchat.ico
│   └── build/                   # 构建产物，不入库
└── .simchat/                    # 本体：Python 包 + scripts/entry.py
```

根 `.gitignore` 的 `build/` 已经覆盖 `.simchatLc/build/`；发布时拷到仓库根的 `simchatLc.exe` 需要单独忽略。

## 基座与它的正式形态

你写的基座（`launcher.cpp`）保留原样，作为 P0 的第一个替换点：

```cpp
#include<windows.h>

using namespace std;

char createWindow(int pid){
    try{

    }catch{

    }
    return 0;
}
```

它现在有两个问题，不是风格问题，是编译不过：`catch` 后面必须带参数（`catch (...)` 或具体类型）；`char` 返回值装不下窗口句柄或退出码。正式实现按下面的签名重写，其余结构保持不变：

```cpp
// launcher.cpp  —— 只做编排，不写窗口细节、不写进程细节
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int nCmdShow);

// window.h
namespace sc {
bool createWindow(HINSTANCE hInst, int pid);   // 基座函数落地：建窗 + 控件
int  runMessageLoop();                          // 主线程消息循环
void postLog(std::string_view utf8);            // 工作线程 → UI 线程
void postPhase(Phase, std::wstring detail);
}
```

## 和本体的契约

启动器只认这一条命令：

```
<python> .simchat/scripts/entry.py web [--host 127.0.0.1] [--port 5000] [--no-browser]
```

- 工作目录固定为 `.simchat/`（`data/`、`mods/`、`configs/` 等相对路径以此为准），不是 exe 所在目录。
- 退出码 0 = 用户主动结束；2 = 参数用法错误；其余非 0 = 启动失败，窗口里原样显示 stderr 尾部与退出码，不吞。
- 默认监听 `127.0.0.1:5000`。端口探活沿用 `runtime/lifecycle.py` 的规则：先 `GET /api/health`，返回 `{"ok": true, "app": "simchat"}` 才算"已有本实例"；端口开着但不是 SimChat，报"端口被其他程序占用"，不覆盖、不杀别人。
- 浏览器由启动器负责：始终传 `--no-browser`，健康检查通过后用 `ShellExecuteW` 打开一次。理由是本体的 `webbrowser.open` 在 GUI 父进程 + 无控制台场景下会失败或重复开窗，双开比"晚开 300ms"更难解释。
- 停止必须先写"主动停止"标记：先跑 `entry.py lifecycle --stop`（`stop_watchdog()` 会 `mark_intentional_stop()` 并停掉守护），再向 Web 子进程发 `CTRL_BREAK_EVENT`；等 5 秒不退再 `TerminateProcess`。直接杀进程会让守护进程把它当崩溃拉起，用户看到"关了又活"。

另外两个子命令原样透传，启动器不解析它们的参数：

```
<python> .simchat/scripts/entry.py cli <init|pack|verify|publish|gen-key|list> ...
<python> .simchat/scripts/entry.py lifecycle <--boot|--guard|--status|--stop>
```

`simchatLc cli pack mymod` 这种调用会 `AllocConsole()` 拿一个控制台，把 stdin/stdout/stderr 直接继承给子进程，Ctrl+C 可用；Web 模式则相反，全程无控制台、管道捕获输出。

## 启动流程（状态机）

```
                 ┌──────────┐
   双击 exe ───▶ │ Locating │ 解析参数 → 定位根目录 → 探测解释器
                 └────┬─────┘
                      ▼
                 ┌──────────┐   端口已有 SimChat    ┌────────┐
                 │ Probing  │ ───────────────────▶ │ Attach │──▶ Running（只显示地址）
                 └────┬─────┘                      └────────┘
          端口空闲/无人应答 ▼
                 ┌──────────┐
                 │ Starting │ CreateProcessW + 管道 + 300ms 轮询 /api/health
                 └────┬─────┘
        30s 内健康 ───▶ Running ──▶ 打开浏览器（一次）
        子进程退出 ───▶ Failed（显示退出码 + stderr 尾部）
        用户关闭窗口 ─▶ Stopping ──▶ Stopped
```

定位根目录的规则，按优先级：

1. `--root <dir>` 显式指定；
2. 环境变量 `SIMCHAT_ROOT`；
3. 从 exe 所在目录向上最多 5 层，找 `.simchat/scripts/entry.py`；
4. 都找不到 → Failed，窗口里给出"把 simchatLc.exe 放进仓库根目录或设置 SIMCHAT_ROOT"的提示。

第 3 条让 `build/bin/simchatLc.exe` 也能直接跑（向上两层即仓库根），不需要拷贝。

## 模块设计

### `_includes/Compile.h`

编译期收敛，所有平台宏只在这里出现，业务代码不写 `#ifdef _WIN32`：

```cpp
#pragma once

#if defined(_WIN32)
#  define SC_WINDOWS 1
#elif defined(__unix__) || defined(__APPLE__)
#  define SC_POSIX 1
#else
#  error "unsupported platform"
#endif

#if defined(_MSC_VER)
#  define SC_MSVC 1
#elif defined(__MINGW32__)
#  define SC_MINGW 1
#endif

#ifndef NOMINMAX
#  define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
#endif

#define SC_COUNTOF(a) (sizeof(a) / sizeof((a)[0]))
#define SC_UNUSED(x)  ((void)(x))
```

约束：整个工程 `UNICODE` / `_UNICODE` 必须打开，路径一律 `std::wstring`。中文用户名、带空格的安装路径、OneDrive 重定向目录都靠这一条活命。

### `_includes/python.h`

```cpp
namespace sc {

struct PythonInfo {
    std::wstring exe;                  // "C:\...\python.exe" 或 "C:\Windows\py.exe"
    std::vector<std::wstring> prefix;  // {"-3"} 之类，放在 entry.py 之前
    std::string version;               // "3.12.4"
};

// 找不到返回 nullopt，reason 里写人话（用于窗口提示）
std::optional<PythonInfo> detectPython(std::string* reason);

// Windows 命令行拼接：含空格/引号时加引号并转义
std::wstring quoteArg(const std::wstring& arg);

}
```

探测顺序（与三份旧脚本保持一致，但补上版本校验）：

1. 环境变量 `SIMCHAT_PYTHON`（用户显式指定，最高优先级）；
2. `py -3`（Windows；本机 `python` 指向损坏的 conda，`py` 才是可用入口）；
3. `python`；
4. `python3`（Unix 优先 `python3` 再 `python`）。

每一项都要用 `-c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)"` 校验，不能只看 `--version`：Windows 应用商店的 `python.exe` 是个 0 字节占位符，会以 9009 或弹商店页失败。

### `_includes/child_process.h` + `src/process_win32.cpp`

```cpp
namespace sc {

struct SpawnOptions {
    std::wstring exe;                 // 解释器绝对路径
    std::wstring args;                // 已拼好、已引号转义的命令行
    std::wstring cwd;                 // .simchat
    bool capture_output = true;       // false = 继承父进程句柄（CLI 模式）
    bool new_process_group = false;   // Web 模式 true，便于 CTRL_BREAK
    std::function<void(std::string_view)> on_output;  // 工作线程回调，UTF-8
};

class Process {
public:
    bool start(const SpawnOptions&, std::string* error);
    bool started() const;
    bool running() const;
    unsigned wait();                  // 阻塞，返回退出码
    bool wait_for(unsigned ms);       // 超时返回 false
    unsigned exit_code() const;
    bool send_break();                // CTRL_BREAK_EVENT
    void terminate();                 // TerminateProcess 兜底
    void abandon();                   // 「仅退出」：泄漏句柄，不杀子进程
    ~Process();
};

}
```

`capture_output = false` 时（`--console` / `cli` / `lifecycle`）不建管道，而是把启动器自己的标准句柄交给子进程：先去 `SetHandleInformation` 标记可继承，句柄缺失才退回 `CreateFileW("CONOUT$" / "CONIN$")`。这样终端里的交互和 `> out.txt` 重定向都能原样保留。

### `_includes/text.h`、`_includes/net.h`

- `text.h`：`sc::widen` / `sc::narrow`，Windows 走 `MultiByteToWideChar` / `WideCharToMultiByte`（CP_UTF8），POSIX 走 `wstring_convert`。全工程只允许 UTF-8 与 `std::wstring` 两种表示。
- `net.h`：`probe_health(host, port, timeout_ms)` → `{kind, status}`，`kind` 是 `None` / `SimChat` / `Other`。WinHTTP 打开两个句柄（会话 + 连接），500ms 超时，读完 body 后按 `"app": "simchat"` 判归属。

实现要点：

- stdout 与 stderr 合并到同一个写端（`hStdOutput` 与 `hStdError` 指向同一个句柄），日志顺序天然不乱。
- `STARTUPINFOW` + `STARTF_USESTDHANDLES`，`bInheritHandles = TRUE`，启动后立刻关掉父进程里的写端，否则读端永远等不到 EOF。
- 创建标志：`CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT`，Web 模式再加 `CREATE_NEW_PROCESS_GROUP`。注意 `CREATE_NO_WINDOW` 仍然给子进程一个"无窗口的控制台"，所以 `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)` 可用。
- 环境块在父进程环境上追加 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`PYTHONUNBUFFERED=1`。少了前两个，中文日志在 GBK 控制台下会变成乱码或直接抛 `UnicodeEncodeError` 把服务带崩。
- 读管道用独立线程，`ReadFile` 循环 8 KB，按 UTF-8 解码（非法字节替换成 `?`，不中断）。
- 不给子进程套 Job Object 的 `KILL_ON_JOB_CLOSE`：用户选择"关闭启动器但保留服务"时不能误杀。清理责任在 Stopping 分支。

### `_includes/window.h` + `src/window_win32.cpp`

窗口只做四件事：显示阶段、给地址、看日志、按按钮。

```
┌─ SimChat Launcher ────────────────────────────┐
│ ● 运行中    http://127.0.0.1:5000             │
│                                               │
│ ┌───────────────────────────────────────────┐ │
│ │ [12:04:31] [SimChat] Web 界面已启动: ...  │ │
│ │ [12:04:31] * Serving Flask app 'simchat'  │ │
│ │ ...                                       │ │
│ └───────────────────────────────────────────┘ │
│ [打开界面]  [重启]  [停止]        退出码: --  │
└───────────────────────────────────────────────┘
```

- 固定 600×380，不可缩放；`WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX`。
- 控件：静态状态行（自绘圆点：灰=启动中、绿=运行、红=失败）、可点击的 URL 静态文本、`EDIT` 多行只读日志框、三个 `BUTTON`。
- 日志框是环形缓冲：内存里保留最后 64 KB，超出按行裁剪，避免长时间运行把 UI 拖死。
- 跨线程只走 `PostMessage(WM_APP_LOG / WM_APP_PHASE)`，工作线程绝不碰控件。
- 字体用 `Microsoft YaHei UI` 9pt，`CreateFontW` 按 `GetDpiForWindow` 缩放；资源里声明 `PerMonitorV2`，否则 150% 缩放下字全糊。
- 关闭窗口弹三选："停止服务并退出 / 仅退出（服务继续运行） / 取消"。默认选中第一个。
- 单实例：`CreateMutexW(L"Local\\SimChatLc")`；已存在时用 `FindWindowW` + `SetForegroundWindow` 把旧窗口拉到前台，自己退出。

### `_includes/app.h`

```cpp
namespace sc {

enum class Phase { Locating, Probing, Starting, Running, Stopping, Stopped, Failed };

struct LaunchOptions {
    std::wstring root;                 // 空 = 自动定位
    std::wstring host = L"127.0.0.1";
    int port = 5000;
    bool open_browser = true;
    bool console = false;              // --console：调试时保留控制台输出
    std::wstring action = L"web";      // web | cli | lifecycle
    std::vector<std::wstring> passthrough;  // 原样转给 entry.py
};

struct LaunchState {
    Phase phase = Phase::Locating;
    PythonInfo python;
    Process child;
    std::wstring url;
    unsigned exit_code = 0;
    std::wstring error;
};

int runLauncher(const LaunchOptions&);   // 返回进程退出码，wWinMain 直接 return

}
```

`app.h` 是唯一知道"顺序"的地方：定位 → 探测 → 分支（attach / spawn）→ 轮询 → 停止。窗口和进程都不知道彼此存在，通过 `postLog` / `postPhase` 与 `on_output` 连接。

## 健康检查

`GET http://<host>:<port>/api/health`，用 WinHTTP（`winhttp.lib`）实现，超时 500ms，读回 JSON 里必须是 `"app": "simchat"`。

- 200 且 app 匹配 → 已有实例，进入 Attach；
- 200 但 app 不匹配 → 端口被占，提示"换端口启动（--port 5001）"，不自动抢端口：自动加端口会让用户找不到自己的服务；
- 连接失败 → 端口空闲，进入 Starting；
- Starting 之后每 300ms 探一次，30 秒超时；期间子进程一旦退出，立即转 Failed 并展示 stderr 尾部（最多 4 KB）。

## 构建

`CMakeLists.txt`（放在 `.simchatLc/`）：

```cmake
cmake_minimum_required(VERSION 3.20)
project(simchatLc LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(WIN32)
  add_executable(simchatLc WIN32
    launcher.cpp
    src/text.cpp
    src/process_win32.cpp
    src/python_win32.cpp
    src/net_win32.cpp
    src/window_win32.cpp
    resources/launcher.rc)
  target_include_directories(simchatLc PRIVATE _includes)
  target_compile_definitions(simchatLc PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
  target_link_libraries(simchatLc PRIVATE
    winhttp comctl32 user32 shell32 ole32)
  if(MSVC)
    target_compile_options(simchatLc PRIVATE /utf-8 /W4)
    # manifest 已由 launcher.rc 嵌入，禁止链接器再生成一份（否则 CVT1100 资源重复）
    target_link_options(simchatLc PRIVATE /MANIFEST:NO)
    # 静态链接 CRT：目标机器不需要装 VC++ 运行库
    set_property(TARGET simchatLc PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  else()
    # MinGW 必须加 -municode，否则 WIN32 子系统下 wWinMain 不会被调用
    target_link_options(simchatLc PRIVATE -municode)
  endif()
else()
  add_executable(simchatLc
    launcher.cpp
    src/text.cpp
    src/process_posix.cpp)
  target_include_directories(simchatLc PRIVATE _includes)
endif()

set_target_properties(simchatLc PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  OUTPUT_NAME simchatLc)
```

构建命令：

```
cmake -S .simchatLc -B .simchatLc/build
cmake --build .simchatLc/build --config Release
```

产物 `.simchatLc/build/bin/simchatLc.exe`。MinGW 单文件构建（CI 用）等价于：

```
g++ -std=c++17 -O2 -municode -mwindows -DUNICODE -D_UNICODE \
    -I.simchatLc/_includes \
    .simchatLc/launcher.cpp .simchatLc/src/*_win32.cpp \
    .simchatLc/resources/launcher.rc \
    -lwinhttp -lcomctl32 -lshell32 -lole32 -o simchatLc.exe
```

## 运行与部署

```
simchatLc.exe                         # 默认 web，127.0.0.1:5000
simchatLc.exe --port 5001             # 换端口
simchatLc.exe --root E:\simchat       # 显式指定根目录
simchatLc.exe --console               # 调试：保留控制台，日志同时进终端
simchatLc.exe cli verify .simchat/mods/xxx
simchatLc.exe lifecycle --status
```

参数规则：第一个非选项参数是子命令，缺省为 `web`；`cli` / `lifecycle` 之后的所有参数原样透传（包括 `--help`），启动器不再解析。`--root` / `--host` / `--port` / `--no-browser` / `--console` 必须写在子命令前面。

- 发布形态：`simchatLc.exe` 放在仓库根，和 `.simchat/` 同级；也可以放 `.simchatLc/build/bin/` 直接跑。
- 旧脚本的去留：P0 验收通过后，README 首屏的启动方式改为 `simchatLc`；`run.bat` / `run.ps1` / `run.sh` 保留一个版本周期作回退，P2 阶段删除。不删的原因是它们目前是唯一在 Linux/macOS 上可用的入口。
- 启动器自身日志：`%LOCALAPPDATA%\SimChatLc\launcher.log`，只记阶段迁移、命令、退出码、异常，不复制 Python 的全部输出（那是本体的日志）。写文件失败只静默跳过，不影响启动。

## 验收标准

1. 干净 Windows 机器（无 VC++ 运行库、中文用户名、路径含空格）双击 exe → 30 秒内出窗口并显示 `Running`，浏览器打开界面。
2. 不带参数重复双击 → 第二个进程立即退出，第一个窗口被拉到前台；端口 5000 只有一条监听。
3. 机器上没有 Python ≥ 3.9 → 窗口显示失败原因与安装地址，不留下半启动的进程。
4. `python` 指向坏环境、只有 `py` 可用时（本机就是这种情况）→ 仍能正常启动。
5. 窗口里能看到 Flask 的启动行与请求错误；关掉窗口（选"停止服务"）后端口释放，守护进程不再拉起。
6. 选"仅退出"→ 窗口消失，`/api/health` 仍返回 200，下次启动进入 Attach 而不是重复拉起。
7. 5000 被别的程序占用 → 明确报"端口被占用"，不杀对方进程。
8. `simchatLc cli verify <dir>` 在控制台里正常交互，Ctrl+C 能中断。
9. 150% / 200% 缩放下字形清晰不模糊。
10. `cmake --build` 在 MSVC 与 MinGW 两套工具链下都能零警告通过（`/W4` / `-Wall -Wextra`）。

## 现状

P0 已完成并在本机（Windows 11 + MSVC 19.x + `py -3` 3.9.7）验证：

- [x] 工程落位：`launcher.cpp`、`_includes`、`src`、`resources` 全部收进 `.simchatLc/`，根目录不再有 `.cpp`
- [x] P0 `Compile.h`：平台/编译器宏收敛，全工程 `UNICODE`
- [x] P0 `python.h` / `python_win32.cpp`：四级探测 + `-c` 版本校验 + 跳过 `WindowsApps` 占位符
- [x] P0 `child_process.h` / `process_win32.cpp`：`CreateProcessW` + 合并管道 + UTF-8 环境 + `send_break` + 控制台句柄继承
- [x] P0 `text.h` / `net.h`：UTF-8 转换、WinHTTP 健康检查
- [x] P0 `window.h` / `window_win32.cpp`：状态窗口、64KB 环形日志、打开/重启/停止、DPI manifest、单实例互斥
- [x] P0 `launcher.cpp`：`wWinMain` + 参数解析 + 状态机编排（替换基座里的 `createWindow` 桩）
- [x] P0 `CMakeLists.txt`：MSVC Release 零警告通过，产物 `build/bin/Release/simchatLc.exe`（约 274 KB，静态 CRT）

已验证的行为：

| 场景 | 结果 |
|---|---|
| GUI 启动（`--port 5103`） | 窗口出现，日志滚出 Flask 启动行，`/api/health` 返回 `{"app":"simchat","ok":true}` |
| 重复启动 | 第二个进程立即退出（exit 0）。窗口被拉到前台，端口只有一条监听 |
| `--console web --port 5101` | 服务正常拉起，健康检查 200 |
| `--console cli --help` | 透传到本体 CLI 并打印 argparse 帮助；`> out.txt` 重定向保留（exit 0） |
| `--console --root <不存在的目录>` | 子命令缺省为 `web`，退出码 2，提示根目录无 `entry.py` |
| 沙箱内运行 | `%LOCALAPPDATA%` 写入被拦时日志静默跳过，不影响启动（这是本机沙箱限制，不是程序缺陷） |

未实测（需要人工点按钮）：停止/重启按钮的三级兜底、「仅退出、服务继续运行」、端口被其他程序占用时的报错文案、150%/200% DPI 缩放、Attach 模式（已有实例时显示地址而不重复拉起）。

待做：

- [ ] P1 停止链路实测：`lifecycle --stop` → `CTRL_BREAK_EVENT` → `TerminateProcess` 三级兜底
- [ ] P1 首次运行引导：检测到 `ModuleNotFoundError` 时提供"安装依赖"按钮（跑 `pip install -r scripts/requirements-simchat.txt`）
- [ ] P1 验收标准 5–7、9 的人工回归
- [ ] P2 POSIX 终端版（无窗口，等价于原 `run.sh`）；`process_posix.cpp` 尚未在 Windows 外验证
- [ ] P2 可选：WebView2 内嵌界面（明确不进 P0，避免把启动器和浏览器绑死）
- [ ] P2 删除 `run.bat` / `run.ps1` / `run.sh`，README 首屏切换

## 桌面壳实现放在哪（分支线索）

默认启动路径仍是"起服务 + 开浏览器"，窗口能力不在 `main` 上。如果以后基于这个底盘做 App、需要原生窗口，去本地分支 `feature/desktop-shell` 取用；该分支刻意不与 `main` 合并，只作为代码存档。

- 位置：分支 `feature/desktop-shell`，一次提交 `078197c`（基于 `de8aef4`），18 个文件，全部在 `.simchatLc/` 内。
- 形态：独立 WebView2 宿主主窗口（启动器本身不承载界面）+ `DEBMODE` 调试窗口（日志、重启/停止）+ 系统托盘（打开主窗口、桌宠开关、关闭行为、退出）+ Win32 分层窗口桌宠（WIC 解码、`UpdateLayeredWindow`、逐像素透明与点击穿透）+ 载入前的 logo 呼吸占位与 20s 超时。
- 契约：沿用 `.simchat/data/desktop_shell.json` 的 `pet_enabled` / `close_action`；桌宠立绘来自已启用 MOD 的 `manifest.json` 中 `desktop.pet`（`sprite` / `page` / `height`）。
- 启用前要补的依赖：WebView2 SDK 未入库，`third_party/webview2` 需要自行还原 NuGet `Microsoft.Web.WebView2` 1.0.4314.35（`WebView2.h`、`WebView2LoaderStatic.lib`、`include/`）；CMake 侧已声明 `msimg32`、`windowscodecs`、`ole32`。
- 限制：纯 Win32，`webview_win32.cpp` 只在 MSVC 下有效；分支里的 `window_win32.cpp` 是完整桌面壳，会取代 `main` 上的状态窗口，两者不能混编。
