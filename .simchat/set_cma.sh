#!/bin/bash
set -e
F=/boot/extlinux/extlinux.conf
cp -a "$F" "${F}.bak.$(date +%Y%m%d%H%M)"
if grep -q '^ *APPEND.*cma=' "$F"; then
  echo "cma already present"
else
  sed -i '/^ *APPEND/s/$/ cma=4G/' "$F"
  echo "cma=4G appended"
fi
echo "=== resulting APPEND line ==="
grep '^ *APPEND' "$F"
echo "=== backup files ==="
ls -l ${F}.bak.*
