#include "Compile.h"

#if defined(SC_WINDOWS)

#include <windows.h>

#include "child_process.h"
#include "python.h"
#include "text.h"

#include <string>
#include <thread>
#include <vector>

namespace sc {
namespace {

std::wstring build_environment() {
  std::wstring block;
  LPWCH raw = GetEnvironmentStringsW();
  if (raw) {
    for (const wchar_t* cursor = raw; *cursor; cursor += wcslen(cursor) + 1) {
      const std::wstring entry(cursor);
      if (entry.rfind(L"PYTHONUTF8=", 0) == 0) continue;
      if (entry.rfind(L"PYTHONIOENCODING=", 0) == 0) continue;
      if (entry.rfind(L"PYTHONUNBUFFERED=", 0) == 0) continue;
      block.append(entry);
      block.push_back(L'\0');
    }
    FreeEnvironmentStringsW(raw);
  }
  const wchar_t* extra[] = {L"PYTHONUTF8=1", L"PYTHONIOENCODING=utf-8",
                            L"PYTHONUNBUFFERED=1"};
  for (const wchar_t* item : extra) {
    block.append(item);
    block.push_back(L'\0');
  }
  block.push_back(L'\0');
  return block;
}

std::string last_error_text(DWORD code) {
  wchar_t buffer[512] = L"";
  const DWORD length =
      FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, code,
                     MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT), buffer,
                     static_cast<DWORD>(sizeof(buffer) / sizeof(buffer[0])), nullptr);
  std::wstring message = length ? std::wstring(buffer, length) : std::wstring(L"未知错误");
  while (!message.empty() && (message.back() == L'\r' || message.back() == L'\n' ||
                              message.back() == L' ')) {
    message.pop_back();
  }
  return narrow(message) + "（错误码 " + std::to_string(code) + "）";
}

// 控制台模式下把当前标准句柄交给子进程；句柄不可继承时才退回打开控制台设备。
// 保留调用方已有的重定向（`> out.txt`），只在句柄缺失时接管。
HANDLE console_handle(DWORD which, const wchar_t* device, DWORD access, bool* owned) {
  *owned = false;
  HANDLE current = GetStdHandle(which);
  if (current && current != INVALID_HANDLE_VALUE &&
      SetHandleInformation(current, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)) {
    return current;
  }
  SECURITY_ATTRIBUTES attributes = {};
  attributes.nLength = sizeof(attributes);
  attributes.bInheritHandle = TRUE;
  HANDLE created = CreateFileW(device, access, FILE_SHARE_READ | FILE_SHARE_WRITE, &attributes,
                               OPEN_EXISTING, 0, nullptr);
  if (created == INVALID_HANDLE_VALUE) return nullptr;
  *owned = true;
  return created;
}

}  // namespace

struct Process::Impl {
  HANDLE process = nullptr;
  HANDLE write_end = nullptr;
  DWORD pid = 0;
  std::thread reader;
  bool started = false;
  bool finished = false;
  bool leaked = false;
  unsigned exit_code = 0;
};

Process::Process() : impl_(new Impl()) {}

Process::~Process() {
  if (!impl_ || impl_->leaked) return;
  if (impl_->started && impl_->process && WaitForSingleObject(impl_->process, 0) == WAIT_TIMEOUT) {
    TerminateProcess(impl_->process, 1);
    WaitForSingleObject(impl_->process, 3000);
  }
  if (impl_->reader.joinable()) impl_->reader.join();
  if (impl_->process) CloseHandle(impl_->process);
  if (impl_->write_end) CloseHandle(impl_->write_end);
  delete impl_;
}

bool Process::start(const SpawnOptions& options, std::string* error) {
  if (!impl_) impl_ = new Impl();

  if (impl_->reader.joinable()) impl_->reader.join();
  if (impl_->process) {
    CloseHandle(impl_->process);
    impl_->process = nullptr;
  }
  if (impl_->write_end) {
    CloseHandle(impl_->write_end);
    impl_->write_end = nullptr;
  }
  impl_->started = false;
  impl_->finished = false;
  impl_->exit_code = 0;

  HANDLE read_end = nullptr;
  HANDLE write_end = nullptr;
  SECURITY_ATTRIBUTES attributes = {};
  attributes.nLength = sizeof(attributes);
  attributes.bInheritHandle = TRUE;

  if (options.capture_output) {
    if (!CreatePipe(&read_end, &write_end, &attributes, 0)) {
      if (error) *error = "创建管道失败：" + last_error_text(GetLastError());
      return false;
    }
    SetHandleInformation(read_end, HANDLE_FLAG_INHERIT, 0);
  }

  HANDLE nul = nullptr;
  if (options.capture_output) {
    nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &attributes,
                      OPEN_EXISTING, 0, nullptr);
  }

  STARTUPINFOW startup = {};
  startup.cb = sizeof(startup);
  HANDLE console_out = nullptr;
  HANDLE console_in = nullptr;
  bool owns_console_out = false;
  bool owns_console_in = false;
  if (options.capture_output) {
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdOutput = write_end;
    startup.hStdError = write_end;
    startup.hStdInput = nul ? nul : INVALID_HANDLE_VALUE;
  } else {
    console_out = console_handle(STD_OUTPUT_HANDLE, L"CONOUT$", GENERIC_READ | GENERIC_WRITE,
                                 &owns_console_out);
    console_in =
        console_handle(STD_INPUT_HANDLE, L"CONIN$", GENERIC_READ | GENERIC_WRITE, &owns_console_in);
    if (console_out || console_in) {
      startup.dwFlags = STARTF_USESTDHANDLES;
      startup.hStdOutput = console_out ? console_out : INVALID_HANDLE_VALUE;
      startup.hStdError = console_out ? console_out : INVALID_HANDLE_VALUE;
      startup.hStdInput = console_in ? console_in : INVALID_HANDLE_VALUE;
    }
  }

  std::wstring environment = build_environment();
  std::wstring command_line = quote_arg(options.exe);
  if (!options.args.empty()) {
    command_line += L' ';
    command_line += options.args;
  }
  std::vector<wchar_t> mutable_command(command_line.begin(), command_line.end());
  mutable_command.push_back(L'\0');

  DWORD flags = CREATE_UNICODE_ENVIRONMENT;
  if (options.new_process_group) flags |= CREATE_NEW_PROCESS_GROUP;
  if (options.capture_output) flags |= CREATE_NO_WINDOW;

  PROCESS_INFORMATION info = {};
  const wchar_t* cwd = options.cwd.empty() ? nullptr : options.cwd.c_str();
  const BOOL inherit_handles = (startup.dwFlags & STARTF_USESTDHANDLES) ? TRUE : FALSE;
  const BOOL ok = CreateProcessW(options.exe.c_str(), mutable_command.data(), nullptr, nullptr,
                                 inherit_handles, flags, environment.data(), cwd, &startup, &info);
  const DWORD last_error = GetLastError();

  if (nul && nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
  if (write_end) CloseHandle(write_end);
  if (owns_console_out) CloseHandle(console_out);
  if (owns_console_in) CloseHandle(console_in);

  if (!ok) {
    if (read_end) CloseHandle(read_end);
    if (error) *error = "无法启动 " + narrow(options.exe) + "：" + last_error_text(last_error);
    return false;
  }

  CloseHandle(info.hThread);
  impl_->process = info.hProcess;
  impl_->pid = info.dwProcessId;
  impl_->started = true;

  if (options.capture_output) {
    auto callback = options.on_output;
    impl_->reader = std::thread([read_end, callback]() {
      std::string pending;
      char buffer[8192];
      for (;;) {
        DWORD got = 0;
        if (!ReadFile(read_end, buffer, static_cast<DWORD>(sizeof(buffer)), &got, nullptr) ||
            got == 0) {
          break;
        }
        pending.append(buffer, got);
        size_t position = 0;
        while ((position = pending.find('\n')) != std::string::npos) {
          std::string line = pending.substr(0, position);
          pending.erase(0, position + 1);
          if (!line.empty() && line.back() == '\r') line.pop_back();
          if (callback) callback(line);
        }
      }
      if (!pending.empty() && callback) callback(pending);
      CloseHandle(read_end);
    });
  }
  return true;
}

bool Process::started() const { return impl_ && impl_->started; }

bool Process::running() const {
  if (!impl_ || !impl_->process || !impl_->started) return false;
  return WaitForSingleObject(impl_->process, 0) == WAIT_TIMEOUT;
}

void Process::finish() {
  if (!impl_) return;
  if (impl_->reader.joinable()) impl_->reader.join();
  if (!impl_->finished) {
    DWORD code = 0;
    if (impl_->process && GetExitCodeProcess(impl_->process, &code)) {
      impl_->exit_code = code;
    }
    impl_->finished = true;
  }
}

unsigned Process::wait() {
  if (!impl_ || !impl_->process) return 0;
  WaitForSingleObject(impl_->process, INFINITE);
  finish();
  return impl_->exit_code;
}

bool Process::wait_for(unsigned ms) {
  if (!impl_ || !impl_->process) return true;
  if (WaitForSingleObject(impl_->process, ms) != WAIT_OBJECT_0) return false;
  finish();
  return true;
}

unsigned Process::exit_code() const { return impl_ ? impl_->exit_code : 0; }

bool Process::send_break() {
  if (!impl_ || !impl_->process || !running()) return false;
  // 子进程有自己隐藏的控制台（CREATE_NO_WINDOW），AttachConsole 后仅向它的进程组发信号。
  FreeConsole();
  if (!AttachConsole(impl_->pid)) return false;
  const BOOL ok = GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, impl_->pid);
  FreeConsole();
  return ok != 0;
}

void Process::terminate() {
  if (impl_ && impl_->process && running()) {
    TerminateProcess(impl_->process, 1);
  }
}

void Process::abandon() {
  if (!impl_) return;
  impl_->leaked = true;
  if (impl_->reader.joinable()) impl_->reader.detach();
  impl_ = nullptr;  // 有意泄漏：进程即将退出，避免 join 阻塞
}

}  // namespace sc

#endif  // SC_WINDOWS
