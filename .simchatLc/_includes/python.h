#pragma once

#include <optional>
#include <string>
#include <vector>

namespace sc {

struct PythonInfo {
  std::wstring exe;                  // python.exe / py.exe 绝对路径
  std::vector<std::wstring> prefix;  // {"-3"} 之类，放在 entry.py 之前
  std::string version;               // "3.12.4"
};

// 依次尝试 SIMCHAT_PYTHON → py -3 → python → python3，全部要求 >= 3.9。
// 找不到返回 nullopt，reason 中写入可直接展示给用户的失败原因。
std::optional<PythonInfo> detect_python(std::string* reason);

// Windows 命令行引号转义。
std::wstring quote_arg(const std::wstring& arg);

// 每个参数单独转义后用空格拼接。
std::wstring join_arguments(const std::vector<std::wstring>& args);

}  // namespace sc
