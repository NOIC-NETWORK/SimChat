#pragma once

#include <string>
#include <string_view>

namespace sc {

// UTF-8 → UTF-16；非法字节最多替换，不抛异常。
std::wstring widen(std::string_view utf8);

// UTF-16 → UTF-8。
std::string narrow(const std::wstring& text);

}  // namespace sc
