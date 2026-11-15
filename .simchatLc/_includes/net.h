#pragma once

#include <string>

namespace sc {

enum class HealthKind {
  None,      // 端口无人应答
  SimChat,   // 已有 SimChat 实例
  Other      // 端口被其他程序占用
};

struct HealthResult {
  HealthKind kind = HealthKind::None;
  int status = 0;
  std::string body;
  std::string error;
};

// GET http://host:port/api/health
HealthResult probe_health(const std::wstring& host, int port, int timeout_ms);

}  // namespace sc
