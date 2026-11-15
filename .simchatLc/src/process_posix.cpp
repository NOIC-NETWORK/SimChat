#include "Compile.h"

#if defined(SC_POSIX)

#include "child_process.h"
#include "python.h"
#include "text.h"

#include <fcntl.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <string>
#include <thread>
#include <vector>

namespace sc {
namespace {

std::vector<std::string> split_arguments(const std::wstring& wide) {
  const std::string text = narrow(wide);
  std::vector<std::string> out;
  std::string current;
  bool in_quotes = false;
  for (const char character : text) {
    if (character == '"') {
      in_quotes = !in_quotes;
      continue;
    }
    if (!in_quotes && (character == ' ' || character == '\t')) {
      if (!current.empty()) {
        out.push_back(current);
        current.clear();
      }
      continue;
    }
    current.push_back(character);
  }
  if (!current.empty()) out.push_back(current);
  return out;
}

}  // namespace

struct Process::Impl {
  pid_t pid = -1;
  int read_fd = -1;
  std::thread reader;
  bool started = false;
  bool finished = false;
  bool leaked = false;
  unsigned exit_code = 0;
};

Process::Process() : impl_(new Impl()) {}

Process::~Process() {
  if (!impl_ || impl_->leaked) return;
  if (impl_->started && impl_->pid > 0) {
    int status = 0;
    if (waitpid(impl_->pid, &status, WNOHANG) == 0) {
      kill(impl_->pid, SIGTERM);
      waitpid(impl_->pid, &status, 0);
    }
  }
  if (impl_->reader.joinable()) impl_->reader.join();
  if (impl_->read_fd >= 0) close(impl_->read_fd);
  delete impl_;
}

bool Process::start(const SpawnOptions& options, std::string* error) {
  if (!impl_) impl_ = new Impl();
  if (impl_->reader.joinable()) impl_->reader.join();

  int fds[2] = {-1, -1};
  if (options.capture_output && pipe(fds) != 0) {
    if (error) *error = "无法创建管道";
    return false;
  }

  const std::vector<std::string> argv = split_arguments(options.args);
  std::vector<std::string> storage;
  storage.push_back(narrow(options.exe));
  storage.insert(storage.end(), argv.begin(), argv.end());
  std::vector<char*> raw;
  for (std::string& item : storage) raw.push_back(&item[0]);
  raw.push_back(nullptr);

  const pid_t pid = fork();
  if (pid < 0) {
    if (options.capture_output) {
      close(fds[0]);
      close(fds[1]);
    }
    if (error) *error = "fork 失败";
    return false;
  }

  if (pid == 0) {
    if (options.new_process_group) setpgid(0, 0);
    if (!options.cwd.empty()) {
      if (chdir(narrow(options.cwd).c_str()) != 0) _exit(127);
    }
    if (options.capture_output) {
      dup2(fds[1], STDOUT_FILENO);
      dup2(fds[1], STDERR_FILENO);
      const int devnull = open("/dev/null", O_RDONLY);
      if (devnull >= 0) {
        dup2(devnull, STDIN_FILENO);
        close(devnull);
      }
      close(fds[0]);
      close(fds[1]);
    }
    execvp(raw[0], raw.data());
    _exit(127);
  }

  if (options.capture_output) {
    close(fds[1]);
  }
  impl_->pid = pid;
  impl_->started = true;
  impl_->finished = false;
  impl_->exit_code = 0;

  if (options.capture_output) {
    impl_->read_fd = fds[0];
    auto callback = options.on_output;
    impl_->reader = std::thread([fds, callback]() {
      std::string pending;
      char buffer[8192];
      for (;;) {
        const ssize_t got = read(fds[0], buffer, sizeof(buffer));
        if (got <= 0) break;
        pending.append(buffer, static_cast<size_t>(got));
        size_t position = 0;
        while ((position = pending.find('\n')) != std::string::npos) {
          std::string line = pending.substr(0, position);
          pending.erase(0, position + 1);
          if (!line.empty() && line.back() == '\r') line.pop_back();
          if (callback) callback(line);
        }
      }
      if (!pending.empty() && callback) callback(pending);
      close(fds[0]);
    });
  }
  return true;
}

bool Process::started() const { return impl_ && impl_->started; }

bool Process::running() const {
  if (!impl_ || !impl_->started || impl_->finished) return false;
  int status = 0;
  return waitpid(impl_->pid, &status, WNOHANG) == 0;
}

void Process::finish() {
  if (!impl_ || impl_->finished) return;
  if (impl_->reader.joinable()) impl_->reader.join();
  int status = 0;
  if (impl_->pid > 0 && waitpid(impl_->pid, &status, 0) >= 0) {
    impl_->exit_code = WIFEXITED(status) ? static_cast<unsigned>(WEXITSTATUS(status))
                                        : static_cast<unsigned>(128 + WTERMSIG(status));
  }
  impl_->finished = true;
}

unsigned Process::wait() {
  if (!impl_ || !impl_->started) return 0;
  finish();
  return impl_->exit_code;
}

bool Process::wait_for(unsigned ms) {
  if (!impl_ || !impl_->started) return true;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
  while (std::chrono::steady_clock::now() < deadline) {
    if (!running()) {
      finish();
      return true;
    }
    usleep(100 * 1000);
  }
  return false;
}

unsigned Process::exit_code() const { return impl_ ? impl_->exit_code : 0; }

bool Process::send_break() {
  if (!impl_ || !impl_->started) return false;
  return kill(impl_->pid, SIGINT) == 0;
}

void Process::terminate() {
  if (impl_ && impl_->started) kill(impl_->pid, SIGKILL);
}

void Process::abandon() {
  if (!impl_) return;
  impl_->leaked = true;
  if (impl_->reader.joinable()) impl_->reader.detach();
  impl_ = nullptr;
}

}  // namespace sc

#endif  // SC_POSIX
