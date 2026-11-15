#pragma once

#include <functional>
#include <string>
#include <string_view>

namespace sc {

struct SpawnOptions {
  std::wstring exe;        // 解释器绝对路径
  std::wstring args;       // exe 之后的命令行，已引号转义
  std::wstring cwd;        // 工作目录，空 = 继承
  bool capture_output = true;   // true：合并 stdout/stderr 到管道；false：继承父进程句柄
  bool new_process_group = false;  // Web 模式需要，便于发送 CTRL_BREAK
  std::function<void(std::string_view)> on_output;  // 按行回调，UTF-8
};

class Process {
 public:
  Process();
  ~Process();

  Process(const Process&) = delete;
  Process& operator=(const Process&) = delete;

  bool start(const SpawnOptions& options, std::string* error);
  bool started() const;
  bool running() const;

  unsigned wait();             // 阻塞到退出
  bool wait_for(unsigned ms);  // 超时返回 false
  unsigned exit_code() const;

  bool send_break();  // 向子进程组发送 CTRL_BREAK_EVENT
  void terminate();   // TerminateProcess 兜底

  // 退出时保留子进程：放弃管道读取，不再 join。调用后本对象不可再用。
  void abandon();

 private:
  void finish();

  struct Impl;
  Impl* impl_ = nullptr;
};

}  // namespace sc
