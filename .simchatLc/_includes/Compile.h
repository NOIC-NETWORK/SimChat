#pragma once

// 编译期收敛：平台与编译器的差异只允许出现在这里。

#if defined(_WIN32)
#  ifndef _WIN32_WINNT
#    define _WIN32_WINNT 0x0601
#  endif
#  ifndef WINVER
#    define WINVER 0x0601
#  endif
#  define SC_WINDOWS 1
#elif defined(__unix__) || defined(__APPLE__)
#  define SC_POSIX 1
#else
#  error "simchatLc: unsupported platform"
#endif

#if defined(_MSC_VER)
#  define SC_MSVC 1
#  include <process.h>
#elif defined(__MINGW32__)
#  define SC_MINGW 1
#endif

#ifndef NOMINMAX
#  define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
#endif

#define SC_COUNTOF(a) (sizeof(a) / sizeof((a)[0]))
#define SC_UNUSED(x) ((void)(x))
