#pragma once

#include "Compile.h"

#include <functional>
#include <string>
#include <string_view>

#if defined(SC_WINDOWS)
#  include <windows.h>
#endif

namespace sc {

enum class Phase {
  Locating,
  Probing,
  Starting,
  Running,
  Stopping,
  Stopped,
  Failed
};

struct WindowCallbacks {
  std::function<void()> on_open;
  std::function<void()> on_restart;
  std::function<void()> on_stop;
  // 关闭窗口：true = 停止服务并退出，false = 仅退出（服务继续运行）
  std::function<void(bool)> on_close;
};

#if defined(SC_WINDOWS)
bool create_window(HINSTANCE instance, int pid);
void set_window_callbacks(WindowCallbacks callbacks);
int run_message_loop();

// 工作线程 → UI 线程
void post_log(std::string_view utf8);
void post_phase(Phase phase, std::wstring detail);
void post_exit_code(unsigned code);
#endif

bool open_url(const std::wstring& url);

}  // namespace sc
