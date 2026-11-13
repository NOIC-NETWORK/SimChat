#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
cd /tmp
printf 'y\nyes\ny\n' | bash /tmp/bt_install.sh > /tmp/bt-install.log 2>&1
echo "EXIT=$?" >> /tmp/bt-install.log
