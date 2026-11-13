#!/bin/bash
echo "=== autostart ==="
systemctl is-enabled ollama
ls -l /etc/init.d/bt 2>/dev/null | head -2
echo "=== cleanup ==="
rm -f /tmp/ollama-0.12.5.tgz /tmp/ollama-0.12.5-part.tgz /tmp/ollama-test.tgz /tmp/rangetest.bin /tmp/rhdr.txt /tmp/mirrortest.sh /tmp/bt_install_run.sh 2>/dev/null
echo done
echo "=== disk ==="
df -h / | tail -1
echo "=== final ollama ==="
ollama --version 2>/dev/null
