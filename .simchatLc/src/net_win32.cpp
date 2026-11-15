#include "Compile.h"

#if defined(SC_WINDOWS)

#include <windows.h>
#include <winhttp.h>

#include "net.h"

#include <string>

namespace sc {
namespace {

void close_handle(HINTERNET handle) {
  if (handle) WinHttpCloseHandle(handle);
}

}  // namespace

HealthResult probe_health(const std::wstring& host, int port, int timeout_ms) {
  HealthResult result;

  HINTERNET session = WinHttpOpen(L"SimChatLc/1.0", WINHTTP_ACCESS_TYPE_NO_PROXY,
                                  WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
  if (!session) {
    result.error = "WinHttpOpen 失败";
    return result;
  }
  WinHttpSetTimeouts(session, timeout_ms, timeout_ms, timeout_ms, timeout_ms);

  HINTERNET connection = WinHttpConnect(session, host.c_str(),
                                        static_cast<INTERNET_PORT>(port), 0);
  if (!connection) {
    result.error = "连接失败";
    close_handle(session);
    return result;
  }

  HINTERNET request =
      WinHttpOpenRequest(connection, L"GET", L"/api/health", nullptr, WINHTTP_NO_REFERER,
                         WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
  if (!request) {
    result.error = "创建请求失败";
    close_handle(connection);
    close_handle(session);
    return result;
  }

  BOOL ok = WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                               WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
  if (ok) ok = WinHttpReceiveResponse(request, nullptr);

  if (!ok) {
    result.error = "端口无人应答";
    close_handle(request);
    close_handle(connection);
    close_handle(session);
    return result;
  }

  DWORD status = 0;
  DWORD status_size = sizeof(status);
  if (WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                          WINHTTP_HEADER_NAME_BY_INDEX, &status, &status_size,
                          WINHTTP_NO_HEADER_INDEX)) {
    result.status = static_cast<int>(status);
  }

  std::string body;
  for (;;) {
    DWORD available = 0;
    if (!WinHttpQueryDataAvailable(request, &available) || available == 0) break;
    std::string chunk(available, '\0');
    DWORD read = 0;
    if (!WinHttpReadData(request, &chunk[0], available, &read) || read == 0) break;
    chunk.resize(read);
    body += chunk;
    if (body.size() > 8192) break;
  }
  result.body = body;

  if (result.status == 200 && body.find("simchat") != std::string::npos) {
    result.kind = HealthKind::SimChat;
  } else if (result.status > 0) {
    result.kind = HealthKind::Other;
  } else {
    result.kind = HealthKind::Other;  // 有应答但不是合法 HTTP，仍视为被占用
  }

  close_handle(request);
  close_handle(connection);
  close_handle(session);
  return result;
}

}  // namespace sc

#endif  // SC_WINDOWS
