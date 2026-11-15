#include "Compile.h"

#if defined(SC_WINDOWS)

#include <windows.h>

#include "child_process.h"
#include "python.h"
#include "text.h"

#include <string>
#include <vector>

namespace sc {
namespace {

std::vector<std::wstring> split_path_list(const std::wstring& value) {
  std::vector<std::wstring> items;
  size_t start = 0;
  while (start <= value.size()) {
    const size_t position = value.find(L';', start);
    const std::wstring item =
        value.substr(start, position == std::wstring::npos ? std::wstring::npos : position - start);
    if (!item.empty()) items.push_back(item);
    if (position == std::wstring::npos) break;
    start = position + 1;
  }
  return items;
}

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

// 扫描 PATH；跳过 WindowsApps，避免命中应用商店的 0 字节占位符。
std::wstring find_on_path(const std::wstring& name) {
  for (const std::wstring& directory : split_path_list(environment_value(L"PATH"))) {
    if (directory.find(L"WindowsApps") != std::wstring::npos) continue;
    std::wstring candidate = directory;
    if (!candidate.empty() && candidate.back() != L'\\' && candidate.back() != L'/') {
      candidate += L'\\';
    }
    candidate += name;
    if (is_file(candidate)) return candidate;
  }
  return std::wstring();
}

struct Candidate {
  std::wstring exe;
  std::vector<std::wstring> prefix;
  std::string label;
};

// 用 -c 检测版本，返回 true 时 version 形如 "3.12.4"。
bool probe_candidate(const Candidate& candidate, std::string* version, std::string* error) {
  const wchar_t* kProbe =
      L"import sys;print('%d.%d.%d' % sys.version_info[:3]);"
      L"sys.exit(0 if sys.version_info >= (3, 9) else 1)";
  std::vector<std::wstring> argv = candidate.prefix;
  argv.push_back(L"-c");
  argv.push_back(kProbe);

  SpawnOptions options;
  options.exe = candidate.exe;
  options.args = join_arguments(argv);
  options.capture_output = true;

  std::string output;
  options.on_output = [&output](std::string_view line) {
    output.append(line.data(), line.size());
    output.push_back('\n');
  };

  Process process;
  std::string start_error;
  if (!process.start(options, &start_error)) {
    if (error) *error = start_error;
    return false;
  }
  const unsigned code = process.wait();
  if (code != 0) {
    if (error) *error = candidate.label + " 无法运行或版本低于 3.9";
    return false;
  }

  std::string text = output;
  while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
  const size_t newline = text.find('\n');
  if (newline != std::string::npos) text.resize(newline);
  if (text.empty()) {
    if (error) *error = candidate.label + " 未返回版本号";
    return false;
  }
  if (version) *version = text;
  return true;
}

}  // namespace

std::wstring quote_arg(const std::wstring& arg) {
  if (arg.empty()) return L"\"\"";
  if (arg.find_first_of(L" \t\n\v\"") == std::wstring::npos) return arg;

  std::wstring out = L"\"";
  size_t index = 0;
  while (index < arg.size()) {
    size_t backslashes = 0;
    while (index < arg.size() && arg[index] == L'\\') {
      ++index;
      ++backslashes;
    }
    if (index == arg.size()) {
      out.append(backslashes * 2, L'\\');
      break;
    }
    if (arg[index] == L'"') {
      out.append(backslashes * 2 + 1, L'\\');
      out.push_back(L'"');
    } else {
      out.append(backslashes, L'\\');
      out.push_back(arg[index]);
    }
    ++index;
  }
  out.push_back(L'"');
  return out;
}

std::wstring join_arguments(const std::vector<std::wstring>& args) {
  std::wstring line;
  for (size_t index = 0; index < args.size(); ++index) {
    if (index > 0) line.push_back(L' ');
    line += quote_arg(args[index]);
  }
  return line;
}

std::optional<PythonInfo> detect_python(std::string* reason) {
  std::vector<Candidate> candidates;

  const std::wstring explicit_path = environment_value(L"SIMCHAT_PYTHON");
  if (!explicit_path.empty()) {
    candidates.push_back({explicit_path, {}, "SIMCHAT_PYTHON"});
  }
  const std::wstring py = find_on_path(L"py.exe");
  if (!py.empty()) {
    candidates.push_back({py, {L"-3"}, "py -3"});
  }
  const std::wstring python = find_on_path(L"python.exe");
  if (!python.empty()) {
    candidates.push_back({python, {}, "python"});
  }
  const std::wstring python3 = find_on_path(L"python3.exe");
  if (!python3.empty()) {
    candidates.push_back({python3, {}, "python3"});
  }

  std::string failures;
  for (const Candidate& candidate : candidates) {
    std::string version;
    std::string error;
    if (probe_candidate(candidate, &version, &error)) {
      PythonInfo info;
      info.exe = candidate.exe;
      info.prefix = candidate.prefix;
      info.version = version + " (" + candidate.label + ")";
      return info;
    }
    failures += "  - " + candidate.label + "：" + error + "\n";
  }

  if (reason) {
    *reason = "未找到可用的 Python >= 3.9。\n请安装 Python 3.10 或更高版本，"
              "或设置环境变量 SIMCHAT_PYTHON 指向解释器。\n";
    *reason += failures;
  }
  return std::nullopt;
}

}  // namespace sc

#endif  // SC_WINDOWS
