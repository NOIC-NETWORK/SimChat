#pragma once

#include <string>
#include <vector>

#include "child_process.h"
#include "python.h"

namespace sc {

struct LaunchOptions {
  std::wstring root;              // 空 = 自动定位
  std::wstring host = L"127.0.0.1";
  int port = 5000;
  bool open_browser = true;
  bool console = false;           // 保留控制台输出，不建窗口
  std::wstring action = L"web";   // web | cli | lifecycle
  std::vector<std::wstring> passthrough;
};

struct LaunchState {
  std::wstring root;
  std::wstring url;
  PythonInfo python;
  Process child;
  unsigned exit_code = 0;
  bool attached = false;
};

int run_launcher(const LaunchOptions& options);

}  // namespace sc
