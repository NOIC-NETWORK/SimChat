#include "Compile.h"

#include "text.h"

#if defined(SC_WINDOWS)
#  include <windows.h>
#else
#  include <codecvt>
#  include <locale>
#endif

namespace sc {

std::wstring widen(std::string_view utf8) {
  if (utf8.empty()) return std::wstring();
#if defined(SC_WINDOWS)
  const int size = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()),
                                       nullptr, 0);
  if (size <= 0) return std::wstring();
  std::wstring out(static_cast<size_t>(size), L'\0');
  MultiByteToWideChar(CP_UTF8, 0, utf8.data(), static_cast<int>(utf8.size()), &out[0], size);
  return out;
#else
  std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> converter;
  return converter.from_bytes(utf8.data(), utf8.data() + utf8.size());
#endif
}

std::string narrow(const std::wstring& text) {
  if (text.empty()) return std::string();
#if defined(SC_WINDOWS)
  const int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                                       nullptr, 0, nullptr, nullptr);
  if (size <= 0) return std::string();
  std::string out(static_cast<size_t>(size), '\0');
  WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), &out[0], size,
                      nullptr, nullptr);
  return out;
#else
  std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> converter;
  return converter.to_bytes(text);
#endif
}

}  // namespace sc
