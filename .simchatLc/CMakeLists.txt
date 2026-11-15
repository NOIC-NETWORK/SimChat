cmake_minimum_required(VERSION 3.20)
project(simchatLc LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(WIN32)
  add_executable(simchatLc WIN32
    launcher.cpp
    src/text.cpp
    src/process_win32.cpp
    src/python_win32.cpp
    src/net_win32.cpp
    src/window_win32.cpp
    resources/launcher.rc)
  target_include_directories(simchatLc PRIVATE _includes)
  target_compile_definitions(simchatLc PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
  target_link_libraries(simchatLc PRIVATE
    winhttp comctl32 user32 shell32 ole32)
  if(MSVC)
    target_compile_options(simchatLc PRIVATE /utf-8 /W4)
    # manifest 已由 resources/launcher.rc 嵌入，禁止链接器再生成一份（否则 CVT1100 资源重复）
    target_link_options(simchatLc PRIVATE /MANIFEST:NO)
    # 静态链接 CRT：目标机器不需要装 VC++ 运行库
    set_property(TARGET simchatLc PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  else()
    # MinGW 必须加 -municode，否则 WIN32 子系统下 wWinMain 不会被调用
    target_link_options(simchatLc PRIVATE -municode)
  endif()
else()
  add_executable(simchatLc
    launcher.cpp
    src/text.cpp
    src/process_posix.cpp)
  target_include_directories(simchatLc PRIVATE _includes)
endif()

set_target_properties(simchatLc PROPERTIES
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
  OUTPUT_NAME "simchatLc")
