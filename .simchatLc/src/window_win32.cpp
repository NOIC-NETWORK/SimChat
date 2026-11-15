#include "Compile.h"

#if defined(SC_WINDOWS)

#include <windows.h>
#include <shellapi.h>

#include "text.h"
#include "window.h"

#include <string>

namespace sc {
namespace {

constexpr int kStatusId = 1001;
constexpr int kUrlId = 1002;
constexpr int kLogId = 1003;
constexpr int kOpenId = 1004;
constexpr int kRestartId = 1005;
constexpr int kStopId = 1006;
constexpr int kExitId = 1007;

constexpr UINT kMsgLog = WM_APP + 1;
constexpr UINT kMsgPhase = WM_APP + 2;
constexpr UINT kMsgExit = WM_APP + 3;

const wchar_t* kClassName = L"SimChatLcWindow";
const wchar_t* kWindowTitle = L"SimChat Launcher";

struct PhasePayload {
  Phase phase;
  std::wstring detail;
};

struct WindowState {
  HWND hwnd = nullptr;
  HWND status = nullptr;
  HWND url = nullptr;
  HWND log = nullptr;
  HWND open = nullptr;
  HWND restart = nullptr;
  HWND stop = nullptr;
  HWND exit = nullptr;
  HFONT font = nullptr;
  std::wstring log_text;
  Phase phase = Phase::Locating;
  WindowCallbacks callbacks;
  bool url_clickable = false;
};

WindowState g;

const wchar_t* phase_label(Phase phase) {
  switch (phase) {
    case Phase::Locating:
      return L"定位中";
    case Phase::Probing:
      return L"检查端口";
    case Phase::Starting:
      return L"启动中";
    case Phase::Running:
      return L"运行中";
    case Phase::Stopping:
      return L"停止中";
    case Phase::Stopped:
      return L"已停止";
    case Phase::Failed:
      return L"启动失败";
  }
  return L"未知";
}

COLORREF phase_color(Phase phase) {
  switch (phase) {
    case Phase::Running:
      return RGB(46, 160, 67);
    case Phase::Failed:
      return RGB(207, 34, 46);
    case Phase::Stopped:
      return RGB(110, 110, 110);
    case Phase::Stopping:
      return RGB(200, 130, 20);
    default:
      return RGB(120, 120, 120);
  }
}

HFONT create_font(HWND hwnd) {
  UINT dpi = 96;
  HDC dc = GetDC(hwnd);
  if (dc) {
    dpi = static_cast<UINT>(GetDeviceCaps(dc, LOGPIXELSY));
    ReleaseDC(hwnd, dc);
  }
  return CreateFontW(-MulDiv(9, static_cast<int>(dpi), 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE,
                     FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                     CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Microsoft YaHei UI");
}

void apply_font(HWND control) {
  if (control && g.font) SendMessageW(control, WM_SETFONT, reinterpret_cast<WPARAM>(g.font), TRUE);
}

void apply_fonts() {
  apply_font(g.status);
  apply_font(g.url);
  apply_font(g.log);
  apply_font(g.open);
  apply_font(g.restart);
  apply_font(g.stop);
  apply_font(g.exit);
}

void layout(HWND hwnd) {
  RECT client = {};
  GetClientRect(hwnd, &client);
  const int pad = 16;
  const int status_height = 24;
  const int url_height = 22;
  const int button_height = 30;
  const int exit_width = 96;
  const int width = client.right - client.left;

  MoveWindow(g.status, pad, pad, width - 2 * pad - exit_width - 8, status_height, TRUE);
  MoveWindow(g.exit, width - pad - exit_width, pad, exit_width, status_height, TRUE);
  MoveWindow(g.url, pad, pad + status_height + 2, width - 2 * pad, url_height, TRUE);

  const int log_top = pad + status_height + url_height + 10;
  int log_height = client.bottom - (button_height + pad + 8) - log_top;
  if (log_height < 40) log_height = 40;
  MoveWindow(g.log, pad, log_top, width - 2 * pad, log_height, TRUE);

  const int button_y = log_top + log_height + 10;
  MoveWindow(g.open, pad, button_y, 100, button_height, TRUE);
  MoveWindow(g.restart, pad + 108, button_y, 84, button_height, TRUE);
  MoveWindow(g.stop, pad + 200, button_y, 84, button_height, TRUE);
}

void update_buttons() {
  const bool running = g.phase == Phase::Running;
  const bool busy = g.phase == Phase::Locating || g.phase == Phase::Probing ||
                    g.phase == Phase::Starting || g.phase == Phase::Stopping;
  EnableWindow(g.open, running);
  EnableWindow(g.restart, !busy);
  EnableWindow(g.stop, running || g.phase == Phase::Starting);
}

void append_log(const std::wstring& text) {
  if (!text.empty()) {
    if (!g.log_text.empty()) g.log_text += L"\r\n";
    g.log_text += text;
  }
  const size_t limit = 64 * 1024;
  if (g.log_text.size() > limit) {
    const size_t cut = g.log_text.size() - limit;
    const size_t newline = g.log_text.find(L'\n', cut);
    g.log_text.erase(0, newline == std::wstring::npos ? cut : newline + 1);
  }
  if (g.log) {
    SetWindowTextW(g.log, g.log_text.c_str());
    SendMessageW(g.log, EM_SETSEL, static_cast<WPARAM>(g.log_text.size()),
                 static_cast<LPARAM>(g.log_text.size()));
    SendMessageW(g.log, EM_SCROLLCARET, 0, 0);
  }
}

void apply_phase(Phase phase, const std::wstring& detail) {
  g.phase = phase;

  switch (phase) {
    case Phase::Running:
      g.url_clickable = true;
      SetWindowTextW(g.url, detail.c_str());
      break;
    case Phase::Failed:
      g.url_clickable = false;
      SetWindowTextW(g.url, L"启动失败，详见下方日志");
      append_log(detail);
      break;
    case Phase::Stopped:
      g.url_clickable = false;
      SetWindowTextW(g.url, L"服务已停止");
      break;
    case Phase::Probing:
      g.url_clickable = false;
      SetWindowTextW(g.url, L"正在检查端口占用…");
      break;
    case Phase::Starting:
      g.url_clickable = false;
      SetWindowTextW(g.url, L"等待服务通过健康检查…");
      break;
    case Phase::Stopping:
      g.url_clickable = false;
      SetWindowTextW(g.url, L"正在停止服务…");
      break;
    case Phase::Locating:
    default:
      g.url_clickable = false;
      SetWindowTextW(g.url, detail.c_str());
      break;
  }

  if (g.status) {
    const std::wstring label = std::wstring(L"● ") + phase_label(phase);
    SetWindowTextW(g.status, label.c_str());
    InvalidateRect(g.status, nullptr, TRUE);
  }
  update_buttons();
}

LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM w_param, LPARAM l_param) {
  switch (message) {
    case WM_CREATE: {
      g.hwnd = hwnd;
      g.font = create_font(hwnd);
      HINSTANCE instance =
          reinterpret_cast<HINSTANCE>(GetWindowLongPtrW(hwnd, GWLP_HINSTANCE));

      g.status = CreateWindowExW(0, L"STATIC", L"● 准备启动",
                                 WS_CHILD | WS_VISIBLE | SS_LEFT, 0, 0, 0, 0, hwnd,
                                 reinterpret_cast<HMENU>(static_cast<INT_PTR>(kStatusId)),
                                 instance, nullptr);
      g.url = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOTIFY, 0,
                              0, 0, 0, hwnd,
                              reinterpret_cast<HMENU>(static_cast<INT_PTR>(kUrlId)), instance,
                              nullptr);
      g.log = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                              WS_CHILD | WS_VISIBLE | WS_VSCROLL | ES_MULTILINE |
                                  ES_AUTOVSCROLL | ES_READONLY | WS_TABSTOP,
                              0, 0, 0, 0, hwnd,
                              reinterpret_cast<HMENU>(static_cast<INT_PTR>(kLogId)), instance,
                              nullptr);
      g.open = CreateWindowExW(0, L"BUTTON", L"打开界面",
                               WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON, 0, 0, 0, 0,
                               hwnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(kOpenId)),
                               instance, nullptr);
      g.restart = CreateWindowExW(0, L"BUTTON", L"重启",
                                  WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON, 0, 0, 0,
                                  0, hwnd,
                                  reinterpret_cast<HMENU>(static_cast<INT_PTR>(kRestartId)),
                                  instance, nullptr);
      g.stop = CreateWindowExW(0, L"BUTTON", L"停止",
                               WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON, 0, 0, 0, 0,
                               hwnd, reinterpret_cast<HMENU>(static_cast<INT_PTR>(kStopId)),
                               instance, nullptr);
      g.exit = CreateWindowExW(0, L"STATIC", L"退出码: --",
                               WS_CHILD | WS_VISIBLE | SS_RIGHT, 0, 0, 0, 0, hwnd,
                               reinterpret_cast<HMENU>(static_cast<INT_PTR>(kExitId)), instance,
                               nullptr);

      SendMessageW(g.log, EM_SETLIMITTEXT, static_cast<WPARAM>(1024 * 1024), 0);
      apply_fonts();
      layout(hwnd);
      update_buttons();
      return 0;
    }
    case WM_SIZE:
      layout(hwnd);
      return 0;
    case WM_DPICHANGED: {
      const RECT* suggested = reinterpret_cast<const RECT*>(l_param);
      SetWindowPos(hwnd, nullptr, suggested->left, suggested->top,
                   suggested->right - suggested->left, suggested->bottom - suggested->top,
                   SWP_NOZORDER | SWP_NOACTIVATE);
      if (g.font) DeleteObject(g.font);
      g.font = create_font(hwnd);
      apply_fonts();
      layout(hwnd);
      return 0;
    }
    case WM_COMMAND: {
      const int id = LOWORD(w_param);
      if (id == kOpenId || id == kUrlId) {
        if (g.callbacks.on_open) g.callbacks.on_open();
        return 0;
      }
      if (id == kRestartId) {
        if (g.callbacks.on_restart) g.callbacks.on_restart();
        return 0;
      }
      if (id == kStopId) {
        if (g.callbacks.on_stop) g.callbacks.on_stop();
        return 0;
      }
      return 0;
    }
    case WM_SETCURSOR: {
      if (LOWORD(l_param) == HTCLIENT && reinterpret_cast<HWND>(w_param) == g.url &&
          g.url_clickable) {
        SetCursor(LoadCursorW(nullptr, IDC_HAND));
        return TRUE;
      }
      break;
    }
    case WM_CTLCOLORSTATIC: {
      HDC dc = reinterpret_cast<HDC>(w_param);
      HWND control = reinterpret_cast<HWND>(l_param);
      SetBkMode(dc, TRANSPARENT);
      SetBkColor(dc, GetSysColor(COLOR_BTNFACE));
      if (control == g.status) {
        SetTextColor(dc, phase_color(g.phase));
      } else if (control == g.url) {
        SetTextColor(dc, g.url_clickable ? RGB(0, 90, 200) : GetSysColor(COLOR_GRAYTEXT));
      } else {
        SetTextColor(dc, GetSysColor(COLOR_BTNTEXT));
      }
      return reinterpret_cast<LRESULT>(GetSysColorBrush(COLOR_BTNFACE));
    }
    case WM_APP + 1: {
      auto* text = reinterpret_cast<std::wstring*>(l_param);
      if (text) {
        append_log(*text);
        delete text;
      }
      return 0;
    }
    case WM_APP + 2: {
      auto* payload = reinterpret_cast<PhasePayload*>(l_param);
      if (payload) {
        apply_phase(payload->phase, payload->detail);
        delete payload;
      }
      return 0;
    }
    case WM_APP + 3: {
      const std::wstring label = L"退出码: " + std::to_wstring(static_cast<unsigned>(w_param));
      SetWindowTextW(g.exit, label.c_str());
      return 0;
    }
    case WM_CLOSE: {
      const int choice = MessageBoxW(
          hwnd,
          L"是：停止服务并退出\n否：仅退出，服务继续运行\n取消：返回窗口",
          L"关闭 SimChat Launcher", MB_YESNOCANCEL | MB_ICONQUESTION);
      if (choice == IDCANCEL) return 0;
      ShowWindow(hwnd, SW_HIDE);
      if (g.callbacks.on_close) g.callbacks.on_close(choice == IDYES);
      DestroyWindow(hwnd);
      return 0;
    }
    case WM_DESTROY:
      PostQuitMessage(0);
      return 0;
    default:
      break;
  }
  return DefWindowProcW(hwnd, message, w_param, l_param);
}

}  // namespace

bool create_window(HINSTANCE instance, int pid) {
  SC_UNUSED(pid);

  WNDCLASSEXW window_class = {};
  window_class.cbSize = sizeof(window_class);
  window_class.lpfnWndProc = window_proc;
  window_class.hInstance = instance;
  window_class.hCursor = LoadCursorW(nullptr, IDC_ARROW);
  window_class.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
  window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_BTNFACE + 1);
  window_class.lpszClassName = kClassName;
  if (!RegisterClassExW(&window_class)) return false;

  RECT rect = {0, 0, 600, 380};
  const DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
  AdjustWindowRect(&rect, style, FALSE);
  const int width = rect.right - rect.left;
  const int height = rect.bottom - rect.top;
  const int x = (GetSystemMetrics(SM_CXSCREEN) - width) / 2;
  const int y = (GetSystemMetrics(SM_CYSCREEN) - height) / 2;

  HWND hwnd = CreateWindowExW(0, kClassName, kWindowTitle, style, x, y, width, height, nullptr,
                              nullptr, instance, nullptr);
  if (!hwnd) return false;
  ShowWindow(hwnd, SW_SHOW);
  UpdateWindow(hwnd);
  return true;
}

void set_window_callbacks(WindowCallbacks callbacks) { g.callbacks = std::move(callbacks); }

int run_message_loop() {
  MSG message = {};
  while (GetMessageW(&message, nullptr, 0, 0) > 0) {
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  return static_cast<int>(message.wParam);
}

void post_log(std::string_view utf8) {
  if (!g.hwnd) return;
  auto* text = new std::wstring(widen(utf8));
  if (!text->empty() && text->back() == L'\r') text->pop_back();
  if (!PostMessageW(g.hwnd, kMsgLog, 0, reinterpret_cast<LPARAM>(text))) delete text;
}

void post_phase(Phase phase, std::wstring detail) {
  if (!g.hwnd) return;
  auto* payload = new PhasePayload{phase, std::move(detail)};
  if (!PostMessageW(g.hwnd, kMsgPhase, 0, reinterpret_cast<LPARAM>(payload))) delete payload;
}

void post_exit_code(unsigned code) {
  if (!g.hwnd) return;
  PostMessageW(g.hwnd, kMsgExit, static_cast<WPARAM>(code), 0);
}

bool open_url(const std::wstring& url) {
  if (url.empty()) return false;
  const HINSTANCE result =
      ShellExecuteW(nullptr, L"open", url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
  return reinterpret_cast<INT_PTR>(result) > 32;
}

}  // namespace sc

#endif  // SC_WINDOWS
