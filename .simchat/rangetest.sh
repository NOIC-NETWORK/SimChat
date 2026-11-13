#!/bin/bash
URL='https://gh-proxy.com/https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-linux-arm64.tar.zst'
curl -s -r 100000000-101048575 -o /tmp/rangetest.bin -D /tmp/rhdr.txt --max-time 30 "$URL"
echo '=== status line ==='
head -1 /tmp/rhdr.txt
grep -i 'content-range' /tmp/rhdr.txt
echo '=== downloaded size ==='
ls -l /tmp/rangetest.bin
