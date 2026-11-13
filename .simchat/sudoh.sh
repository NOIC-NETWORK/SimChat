#!/bin/bash
# sudo helper - pipes password to sudo
printf '%s\n' "nvidia" | sudo -S -p '' "$@"
