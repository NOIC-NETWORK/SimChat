#!/bin/bash
PORT=$(cat /www/server/panel/data/port.pl)
ENTRY=$(cat /www/server/panel/data/admin_path.pl)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
echo "port=$PORT entry=$ENTRY"
for p in "$ENTRY" "$ENTRY/" "$ENTRY/index" "/" "/login"; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' -A "$UA" "https://127.0.0.1:${PORT}${p}")
  echo "path=$p -> $code"
done
echo '=== first 300 bytes of entry page ==='
curl -sk -A "$UA" "https://127.0.0.1:${PORT}${ENTRY}/" | head -c 300
