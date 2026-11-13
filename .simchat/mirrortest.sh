#!/bin/bash
PATH_TAIL='/ollama/ollama/releases/download/v0.40.14/ollama-linux-arm64.tar.zst'
for host in https://kkgithub.com https://bgithub.xyz https://ghfast.top/https://github.com https://ghproxy.net/https://github.com; do
  echo "=== $host ==="
  curl -sL --max-time 12 -o /dev/null -w 'code=%{http_code} speed=%{speed_download}B/s got=%{size_download}\n' "${host}${PATH_TAIL}" 2>&1
done
