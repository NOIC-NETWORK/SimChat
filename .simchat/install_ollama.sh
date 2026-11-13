#!/bin/bash
set -e
echo "=== stop service ==="
systemctl stop ollama
echo "=== backup old binary ==="
cp -a /usr/local/bin/ollama /usr/local/bin/ollama.0.12.5.bak 2>/dev/null || true
echo "=== extract bin/ollama + libggml-base ==="
tar --zstd -xf /tmp/ollama-full.tar.zst -C /usr/local bin/ollama lib/ollama/libggml-base.so lib/ollama/libggml-base.so.0 lib/ollama/libggml-base.so.0.28.0
chmod 755 /usr/local/bin/ollama
echo "=== version ==="
/usr/local/bin/ollama --version
echo "=== lib check ==="
ls -l /usr/local/lib/ollama/libggml-base.so* /usr/local/bin/ollama
