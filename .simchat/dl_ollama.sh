#!/bin/bash
URL='https://gh-proxy.com/https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-linux-arm64.tar.zst'
curl -L --retry 20 --retry-delay 10 --retry-all-errors -o /tmp/ollama-full.tar.zst "$URL" > /tmp/ollama-dl.log 2>&1
echo "EXIT=$?" >> /tmp/ollama-dl.log
