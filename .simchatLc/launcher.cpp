#include "Compile.h"

#include "app.h"
#include "child_process.h"
#include "net.h"
#include "python.h"
#include "text.h"

#if defined(SC_WINDOWS)
#  include <windows.h>
#  include <shellapi.h>

#  include "window.h"
#else
#  include <unistd.h>

#  include <cstdio>
#  include <cstdlib>
#endif

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cwchar>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

sc::LaunchOptions g_options;
sc::LaunchState g_state;
std::mutex g_state_mutex;
std::atomic<bool> g_shutdown{false};
std::atomic<bool> g_browser_opened{false};

std::wstring join_path(const std::wstring& base, const std::wstring& child) {
  if (base.empty()) return child;
#if defined(SC_WINDOWS)
  const wchar_t separator = L'\\';
#else
  const wchar_t separator = L'/';
#endif
  std::wstring out = base;
  if (out.back() != L'\\' && out.back() != L'/') out.push_back(separator);
  out += child;
  return out;
}

std::wstring entry_script(const std::wstring& root) {
#if defined(SC_WINDOWS)
  return join_path(join_path(root, L".simchat"), L"scripts\\entry.py");
#else
  return join_path(join_path(root, L".simchat"), L"scripts/entry.py");
#endif
}

#if defined(SC_WINDOWS)

std::wstring environment_value(const wchar_t* name) {
  const DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
  if (size == 0) return std::wstring();
  std::wstring value(static_cast<size_t>(size), L'\0');
  const DWORD written = GetEnvironmentVariableW(name, &value[0], size);
  if (written == 0 || written >= size) return std::wstring();
  value.resize(written);
  return value;
}

bool is_file(const std::wstring& path) {
  const DWORD attributes = GetFileAttributesW(path.c_str());
  return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

std::wstring absolute_path(const std::wstring& path) {
  wchar_t buffer[MAX_PATH * 2] = L"";
  const DWORD length = GetFullPathNameW(path.c_str(), SC_COUNTOF(buffer), buffer, nullptr);
  if (length == 0 || length >= SC_COUNTOF(buffer)) return path;
  return std::wstring(buffer, length);
}

std::wstring exe_directory() {
  std::vector<wchar_t> buffer(MAX_PATH);
  for (;;) {
    const DWORD length =
        GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (length == 0) return std::wstring();
    if (length < buffer.size()) {
      const std::wstring path(buffer.data(), length);
      const size_t slash = path.find_last_of(L"\\/");
      return slash == std::wstring::npos ? std::wstring() : path.substr(0, slash);
    }
    buffer.resize(buffer.size() * 2);
  }
}

bool looks_like_root(const std::wstring& directory) {
  return is_file(entry_script(directory));
}

std::wstring locate_root(std::string* reason) {
  if (!g_options.root.empty()) {
    const std::wstring candidate = absolute_path(g_options.root);
    if (looks_like_root(candidate)) return candidate;
    if (reason) {
      *reason = "指定的根目录下找不到 .simchat/scripts/entry.py：" + sc::narrow(candidate);
    }
    return std::wstring();
  }

  const std::wstring from_env = environment_value(L"SIMCHAT_ROOT");
  if (!from_env.empty() && looks_like_root(from_env)) return from_env;

  std::wstring directory = exe_directory();
  for (int depth = 0; depth <= 5 && !directory.empty(); ++depth) {
    if (looks_like_root(directory)) return directory;
    const size_t slash = directory.find_last_of(L"\\/");
    if (slash == std::wstring::npos) break;
    if (slash == 2 && directory.size() > 1 && directory[1] == L':') break;
    directory = directory.substr(0, slash);
  }

  if (reason) {
    *reason =
        "找不到 SimChat 根目录。把 simchatLc.exe 放进仓库根目录，"
        "或用 --root 指定，或设置环境变量 SIMCHAT_ROOT。";
  }
  return std::wstring();
}

void console_write(const std::wstring& line) {
  HANDLE handle = GetStdHandle(STD_OUTPUT_HANDLE);
  DWORD written = 0;
  if (handle && handle != INVALID_HANDLE_VALUE &&
      WriteConsoleW(handle, line.c_str(), static_cast<DWORD>(line.size()), &written, nullptr)) {
    return;
  }
  const std::string utf8 = sc::narrow(line);
  WriteFile(handle, utf8.data(), static_cast<DWORD>(utf8.size()), &written, nullptr);
}

bool standard_handle_ready(DWORD which) {
  const HANDLE handle = GetStdHandle(which);
  return handle && handle != INVALID_HANDLE_VALUE;
}

void ensure_console() {
  if (GetConsoleWindow() == nullptr) {
    if (!AttachConsole(ATTACH_PARENT_PROCESS)) AllocConsole();
  }
  // 只补绑定缺失的流：从 cmd 启动或做了重定向时保留原有句柄，避免把输出抢回控制台。
  if (!standard_handle_ready(STD_OUTPUT_HANDLE) || !standard_handle_ready(STD_ERROR_HANDLE) ||
      !standard_handle_ready(STD_INPUT_HANDLE)) {
#if defined(SC_MSVC)
    FILE* stream = nullptr;
    if (!standard_handle_ready(STD_OUTPUT_HANDLE)) freopen_s(&stream, "CONOUT$", "w", stdout);
    if (!standard_handle_ready(STD_ERROR_HANDLE)) freopen_s(&stream, "CONOUT$", "w", stderr);
    if (!standard_handle_ready(STD_INPUT_HANDLE)) freopen_s(&stream, "CONIN$", "r", stdin);
#else
    if (!standard_handle_ready(STD_OUTPUT_HANDLE)) freopen("CONOUT$", "w", stdout);
    if (!standard_handle_ready(STD_ERROR_HANDLE)) freopen("CONOUT$", "w", stderr);
    if (!standard_handle_ready(STD_INPUT_HANDLE)) freopen("CONIN$", "r", stdin);
#endif
  }
}

#else  // SC_POSIX

std::wstring locate_root(std::string* reason) {
  if (!g_options.root.empty()) return g_options.root;
  const char* from_env = std::getenv("SIMCHAT_ROOT");
  if (from_env && *from_env) return sc::widen(from_env);
  if (reason) *reason = "找不到 SimChat 根目录，请用 --root 指定";
  return std::wstring();
}

#endif

class Worker {
 public:
  void start() { thread_ = std::thread([this]() { run(); }); }

  void post(std::function<void()> task) {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      tasks_.push_back(std::move(task));
    }
    condition_.notify_one();
  }

  void stop() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      quit_ = true;
      tasks_.clear();
    }
    condition_.notify_all();
    if (thread_.joinable()) thread_.join();
  }

  void run_sync(std::function<void()> task) {
    auto promise = std::make_shared<std::promise<void>>();
    auto future = promise->get_future();
    post([task, promise]() {
      task();
      promise->set_value();
    });
    future.wait_for(std::chrono::seconds(20));
  }

 private:
  void run() {
    for (;;) {
      std::function<void()> task;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        condition_.wait(lock, [this]() { return quit_ || !tasks_.empty(); });
        if (quit_ && tasks_.empty()) return;
        task = std::move(tasks_.front());
        tasks_.pop_front();
      }
      task();
    }
  }

  std::thread thread_;
  std::mutex mutex_;
  std::condition_variable condition_;
  std::deque<std::function<void()>> tasks_;
  bool quit_ = false;
};

Worker g_worker;

void launcher_log(const std::wstring& line) {
#if defined(SC_WINDOWS)
  wchar_t buffer[MAX_PATH] = L"";
  const DWORD length = GetEnvironmentVariableW(L"LOCALAPPDATA", buffer, SC_COUNTOF(buffer));
  std::wstring directory = length ? std::wstring(buffer, length) : L".";
  directory = join_path(directory, L"SimChatLc");
  CreateDirectoryW(directory.c_str(), nullptr);
  const std::wstring path = join_path(directory, L"launcher.log");

  HANDLE file = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                            nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) return;

  SYSTEMTIME now = {};
  GetLocalTime(&now);
  const std::wstring stamp = std::to_wstring(now.wYear) + L"-" +
                             std::to_wstring(now.wMonth) + L"-" + std::to_wstring(now.wDay) +
                             L" " + std::to_wstring(now.wHour) + L":" +
                             std::to_wstring(now.wMinute) + L":" +
                             std::to_wstring(now.wSecond);
  const std::string utf8 = sc::narrow(L"[" + stamp + L"] " + line) + "\r\n";
  DWORD written = 0;
  WriteFile(file, utf8.data(), static_cast<DWORD>(utf8.size()), &written, nullptr);
  CloseHandle(file);
#else
  SC_UNUSED(line);
#endif
}

void fail_now(const std::wstring& message) {
  launcher_log(L"失败：" + message);
  sc::post_log(sc::narrow(message));
  sc::post_phase(sc::Phase::Failed, message);
}

std::vector<std::wstring> build_entry_arguments(const sc::PythonInfo& python,
                                                const std::wstring& root,
                                                const std::vector<std::wstring>& tail) {
  std::vector<std::wstring> args = python.prefix;
  args.push_back(entry_script(root));
  args.insert(args.end(), tail.begin(), tail.end());
  return args;
}

#if defined(SC_WINDOWS)

void start_server() {
  if (g_shutdown) return;
  g_browser_opened = false;

  sc::post_phase(sc::Phase::Locating, L"正在定位 SimChat 根目录…");
  std::string reason;
  const std::wstring root = locate_root(&reason);
  if (root.empty()) {
    fail_now(sc::widen(reason));
    return;
  }
  launcher_log(L"根目录：" + root);

  sc::post_phase(sc::Phase::Locating, L"正在探测 Python…");
  const auto python = sc::detect_python(&reason);
  if (!python) {
    fail_now(sc::widen(reason));
    return;
  }
  launcher_log(L"解释器：" + python->exe + L"  版本：" + sc::widen(python->version));
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    g_state.root = root;
    g_state.python = *python;
    g_state.attached = false;
  }
  if (g_shutdown) return;

  std::wstring host = g_options.host;
  if (host.empty() || host == L"0.0.0.0" || host == L"::") host = L"127.0.0.1";
  const std::wstring url = L"http://" + host + L":" + std::to_wstring(g_options.port);

  sc::post_phase(sc::Phase::Probing, L"");
  const sc::HealthResult health = sc::probe_health(host, g_options.port, 500);
  launcher_log(L"健康检查：kind=" + std::to_wstring(static_cast<int>(health.kind)) +
               L" status=" + std::to_wstring(health.status));
  if (health.kind == sc::HealthKind::SimChat) {
    {
      std::lock_guard<std::mutex> lock(g_state_mutex);
      g_state.url = url;
      g_state.attached = true;
    }
    sc::post_phase(sc::Phase::Running, url);
    if (g_options.open_browser && !g_browser_opened.exchange(true)) sc::open_url(url);
    return;
  }
  if (health.kind == sc::HealthKind::Other) {
    fail_now(L"端口 " + std::to_wstring(g_options.port) +
             L" 被其他程序占用，请换端口：simchatLc.exe --port 5001");
    return;
  }

  const std::vector<std::wstring> tail = {L"web", L"--host", g_options.host, L"--port",
                                          std::to_wstring(g_options.port), L"--no-browser"};
  sc::SpawnOptions spawn;
  spawn.exe = python->exe;
  spawn.args = sc::join_arguments(build_entry_arguments(*python, root, tail));
  spawn.cwd = join_path(root, L".simchat");
  spawn.capture_output = true;
  spawn.new_process_group = true;
  spawn.on_output = [](std::string_view line) {
    sc::post_log(line);
    launcher_log(L"子进程: " + sc::widen(line));
  };
  launcher_log(L"启动命令：" + spawn.exe + L" " + spawn.args);
  launcher_log(L"工作目录：" + spawn.cwd);

  std::string error;
  bool started = false;
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    started = g_state.child.start(spawn, &error);
  }
  if (!started) {
    fail_now(L"启动失败：" + sc::widen(error));
    return;
  }
  launcher_log(L"子进程已创建，等待健康检查");

  sc::post_phase(sc::Phase::Starting, L"");
  const ULONGLONG deadline = GetTickCount64() + 30000;
  while (!g_shutdown) {
    {
      std::lock_guard<std::mutex> lock(g_state_mutex);
      if (g_state.child.running()) {
        // 仍在运行
      } else {
        const unsigned code = g_state.child.wait();
        g_state.exit_code = code;
        sc::post_exit_code(code);
        launcher_log(L"子进程退出，退出码 " + std::to_wstring(code));
        fail_now(L"服务进程已退出（退出码 " + std::to_wstring(code) + L"），详情见上方日志");
        return;
      }
    }
    const sc::HealthResult probe = sc::probe_health(host, g_options.port, 500);
    if (probe.kind == sc::HealthKind::SimChat) {
      {
        std::lock_guard<std::mutex> lock(g_state_mutex);
        g_state.url = url;
      }
      sc::post_phase(sc::Phase::Running, url);
      if (g_options.open_browser && !g_browser_opened.exchange(true)) sc::open_url(url);
      return;
    }
    if (GetTickCount64() > deadline) {
      fail_now(L"30 秒内未通过健康检查，请查看上方日志");
      return;
    }
    Sleep(300);
  }
}

void stop_server() {
  sc::post_phase(sc::Phase::Stopping, L"");

  sc::PythonInfo python;
  std::wstring root;
  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    python = g_state.python;
    root = g_state.root;
  }

  if (!python.exe.empty() && !root.empty()) {
    const std::vector<std::wstring> tail = {L"lifecycle", L"--stop"};
    sc::SpawnOptions spawn;
    spawn.exe = python.exe;
    spawn.args = sc::join_arguments(build_entry_arguments(python, root, tail));
    spawn.cwd = join_path(root, L".simchat");
    spawn.capture_output = true;
    sc::Process stopper;
    std::string error;
    if (stopper.start(spawn, &error)) {
      if (!stopper.wait_for(8000)) stopper.terminate();
      stopper.wait();
    }
  }

  {
    std::lock_guard<std::mutex> lock(g_state_mutex);
    if (g_state.child.running()) {
      g_state.child.send_break();
      if (!g_state.child.wait_for(5000)) g_state.child.terminate();
      g_state.child.wait();
    }
    g_state.url.clear();
    g_state.attached = false;
  }
  sc::post_phase(sc::Phase::Stopped, L"");
}

void restart_server() {
  stop_server();
  if (!g_shutdown) start_server();
}

#endif  // SC_WINDOWS

void print_error(const std::wstring& message) {
#if defined(SC_WINDOWS)
  console_write(message + L"\n");
#else
  std::fprintf(stderr, "%s\n", sc::narrow(message).c_str());
#endif
}

int run_console() {
#if defined(SC_WINDOWS)
  ensure_console();
#endif
  std::string reason;
  const std::wstring root = locate_root(&reason);
  if (root.empty()) {
    print_error(sc::widen(reason));
    return 2;
  }
  launcher_log(L"控制台模式根目录：" + root);
  const auto python = sc::detect_python(&reason);
  if (!python) {
    print_error(sc::widen(reason));
    return 2;
  }
  launcher_log(L"控制台模式解释器：" + python->exe);

  std::vector<std::wstring> tail;
  tail.push_back(g_options.action);
  for (const std::wstring& item : g_options.passthrough) tail.push_back(item);
  if (g_options.action == L"web") {
    tail.push_back(L"--host");
    tail.push_back(g_options.host);
    tail.push_back(L"--port");
    tail.push_back(std::to_wstring(g_options.port));
    if (!g_options.open_browser) tail.push_back(L"--no-browser");
  }

  sc::SpawnOptions spawn;
  spawn.exe = python->exe;
  spawn.args = sc::join_arguments(build_entry_arguments(*python, root, tail));
  spawn.cwd = join_path(root, L".simchat");
  spawn.capture_output = false;
  spawn.new_process_group = false;

  sc::Process child;
  std::string error;
  launcher_log(L"控制台命令：" + spawn.exe + L" " + spawn.args);
  if (!child.start(spawn, &error)) {
    print_error(L"启动失败：" + sc::widen(error));
    return 1;
  }
  const unsigned exit_code = child.wait();
  launcher_log(L"控制台子进程退出，退出码 " + std::to_wstring(exit_code));
  return static_cast<int>(exit_code);
}

#if defined(SC_WINDOWS)

int run_gui() {
  HANDLE mutex = CreateMutexW(nullptr, TRUE, L"Local\\SimChatLc");
  if (mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
    HWND existing = FindWindowW(L"SimChatLcWindow", nullptr);
    if (existing) {
      ShowWindow(existing, SW_RESTORE);
      SetForegroundWindow(existing);
    }
    CloseHandle(mutex);
    return 0;
  }

  sc::WindowCallbacks callbacks;
  callbacks.on_open = []() {
    std::wstring url;
    {
      std::lock_guard<std::mutex> lock(g_state_mutex);
      url = g_state.url;
    }
    if (!url.empty()) sc::open_url(url);
  };
  callbacks.on_restart = []() { g_worker.post(restart_server); };
  callbacks.on_stop = []() { g_worker.post(stop_server); };
  callbacks.on_close = [](bool stop_service) {
    g_shutdown = true;
    if (stop_service) {
      g_worker.run_sync(stop_server);
    } else {
      g_worker.run_sync([]() {});
    }
    g_worker.stop();
    if (!stop_service) g_state.child.abandon();
  };
  sc::set_window_callbacks(std::move(callbacks));

  if (!sc::create_window(GetModuleHandleW(nullptr), 0)) {
    if (mutex) CloseHandle(mutex);
    MessageBoxW(nullptr, L"无法创建启动器窗口。", L"SimChat Launcher", MB_ICONERROR | MB_OK);
    return 1;
  }

  g_worker.start();
  g_worker.post(start_server);
  const int code = sc::run_message_loop();
  g_worker.stop();
  if (mutex) CloseHandle(mutex);
  return code;
}

#endif

std::wstring usage_text() {
  return L"SimChat Launcher (simchatLc)\n\n"
         L"用法：\n"
         L"  simchatLc.exe [web] [选项]         启动桌面窗口\n"
         L"  simchatLc.exe --console [web]      控制台模式，日志直接输出\n"
         L"  simchatLc.exe cli <命令> ...        透传给 entry.py cli\n"
         L"  simchatLc.exe lifecycle <参数> ...  透传给 entry.py lifecycle\n\n"
         L"选项：\n"
         L"  --root <目录>    指定 SimChat 根目录\n"
         L"  --host <地址>    监听地址，默认 127.0.0.1\n"
         L"  --port <端口>    监听端口，默认 5000\n"
         L"  --no-browser     启动后不自动打开浏览器\n"
         L"  --console        不建窗口，保留控制台输出\n"
         L"  --help, -h       显示帮助\n"
         L"  --version        显示版本\n";
}

struct ParsedArgs {
  sc::LaunchOptions options;
  bool help = false;
  bool version = false;
  std::wstring error;
};

ParsedArgs parse_arguments(const std::vector<std::wstring>& arguments) {
  ParsedArgs parsed;
  bool action_seen = false;

  for (size_t index = 0; index < arguments.size(); ++index) {
    const std::wstring& arg = arguments[index];
    if (action_seen && parsed.options.action != L"web") {
      // cli / lifecycle 之后的参数原样透传，不被启动器当成自己的选项（例如 `cli --help`）。
      parsed.options.passthrough.push_back(arg);
      continue;
    }
    if (arg == L"--help" || arg == L"-h") {
      parsed.help = true;
    } else if (arg == L"--version") {
      parsed.version = true;
    } else if (arg == L"--no-browser") {
      parsed.options.open_browser = false;
    } else if (arg == L"--console") {
      parsed.options.console = true;
    } else if (arg == L"--root" || arg == L"--host" || arg == L"--port") {
      if (index + 1 >= arguments.size()) {
        parsed.error = arg + L" 缺少参数值";
        continue;
      }
      const std::wstring value = arguments[++index];
      if (arg == L"--root") {
        parsed.options.root = value;
      } else if (arg == L"--host") {
        parsed.options.host = value;
      } else {
        wchar_t* end = nullptr;
        const long port = wcstol(value.c_str(), &end, 10);
        if (!end || *end != L'\0' || port <= 0 || port > 65535) {
          parsed.error = L"端口必须是 1-65535 之间的整数：" + value;
        } else {
          parsed.options.port = static_cast<int>(port);
        }
      }
    } else if (!arg.empty() && arg[0] == L'-') {
      parsed.error = L"未知参数：" + arg;
    } else if (!action_seen) {
      parsed.options.action = arg;
      action_seen = true;
    } else {
      parsed.options.passthrough.push_back(arg);
    }
  }

  if (parsed.options.action.empty()) {
    parsed.options.action = L"web";
  } else if (parsed.options.action != L"web" && parsed.options.action != L"cli" &&
             parsed.options.action != L"lifecycle") {
    parsed.error = L"未知子命令：" + parsed.options.action;
  }
  return parsed;
}

bool needs_console(const sc::LaunchOptions& options) {
  return options.console || options.action != L"web";
}

}  // namespace

#if defined(SC_WINDOWS)

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show) {
  SC_UNUSED(instance);
  SC_UNUSED(previous);
  SC_UNUSED(command_line);
  SC_UNUSED(show);

  int argc = 0;
  LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  std::vector<std::wstring> arguments;
  if (argv) {
    for (int index = 1; index < argc; ++index) arguments.emplace_back(argv[index]);
    LocalFree(argv);
  }

  const ParsedArgs parsed = parse_arguments(arguments);

  if (parsed.help || parsed.version) {
    const std::wstring text = parsed.help ? usage_text() : L"simchatLc 0.1.0 (P0)";
    if (needs_console(parsed.options)) {
      ensure_console();
      console_write(text + L"\n");
    } else {
      MessageBoxW(nullptr, text.c_str(), L"SimChat Launcher", MB_OK | MB_ICONINFORMATION);
    }
    return 0;
  }
  if (!parsed.error.empty()) {
    if (needs_console(parsed.options)) {
      ensure_console();
      print_error(parsed.error);
    } else {
      MessageBoxW(nullptr, parsed.error.c_str(), L"SimChat Launcher", MB_OK | MB_ICONERROR);
    }
    return 2;
  }

  g_options = parsed.options;
  launcher_log(L"参数解析完成：action=" + parsed.options.action + L" console=" +
               (parsed.options.console ? L"1" : L"0"));
  return needs_console(parsed.options) ? run_console() : run_gui();
}

#else

int main(int argc, char** argv) {
  std::vector<std::wstring> arguments;
  for (int index = 1; index < argc; ++index) arguments.push_back(sc::widen(argv[index]));

  const ParsedArgs parsed = parse_arguments(arguments);
  if (parsed.help || parsed.version) {
    std::printf("%s\n", sc::narrow(parsed.help ? usage_text() : L"simchatLc 0.1.0 (P0)").c_str());
    return 0;
  }
  if (!parsed.error.empty()) {
    std::fprintf(stderr, "%s\n", sc::narrow(parsed.error).c_str());
    return 2;
  }

  g_options = parsed.options;
  return run_console();
}

#endif
