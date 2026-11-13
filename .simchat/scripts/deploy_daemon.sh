#!/usr/bin/env bash
# SimChat 无桌面 / 服务器部署脚本（Linux systemd --user）
#
# 适用场景：
#   - 没有桌面环境、无法使用设置页「开机自启」开关的服务器；
#   - 希望由系统托管进程、而不是 SimChat 自带守护进程。
#
# 它做两件事：
#   1) 开机自启：systemctl --user enable，登录后自动启动；
#   2) 自动拉起：systemd Restart=on-failure，仅异常退出时重启。
#      主动执行 stop / 设置页「停止服务」会以 0 退出，systemd 不会复活它。
#
# 重要：桌面端请优先使用设置页里的「开机自启 / 自动拉起」。
# 两套机制同时启用会竞争同一端口；本脚本安装时会提示你移除重复项。
#
# 用法：
#   ./scripts/deploy_daemon.sh install
#   ./scripts/deploy_daemon.sh uninstall
#   ./scripts/deploy_daemon.sh start|stop|restart|status|logs
#
# 可选环境变量：
#   SIMCHAT_PYTHON  Python 解释器（默认 python3）
#   SIMCHAT_HOST    监听地址（默认 127.0.0.1）
#   SIMCHAT_PORT    监听端口（默认 5000）

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SIMCHAT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PACKAGE_PARENT="$(dirname -- "$SIMCHAT_ROOT")"

SERVICE_NAME="simchat.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/$SERVICE_NAME"

HOST="${SIMCHAT_HOST:-127.0.0.1}"
PORT="${SIMCHAT_PORT:-5000}"

# shellcheck disable=SC2016
PYTHON_BIN="${SIMCHAT_PYTHON:-$(command -v python3 || command -v python || true)}"

note() { printf '[simchat] %s\n' "$*"; }
fail() { printf '[simchat] 错误: %s\n' "$*" >&2; exit 1; }

require_systemd() {
  command -v systemctl >/dev/null 2>&1 || fail "未找到 systemctl；请改用设置页开关或 ~/.config/autostart"
  [[ -n "$PYTHON_BIN" ]] || fail "未找到 Python；请设置 SIMCHAT_PYTHON"
  [[ -f "$SIMCHAT_ROOT/web/__main__.py" ]] || fail "无法识别 SimChat 根目录: $SIMCHAT_ROOT"
}

render_unit() {
  cat <<EOF
[Unit]
Description=SimChat Web Service
Documentation=file://$PACKAGE_PARENT/README.md
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory="$SIMCHAT_ROOT"
Environment="PYTHONUNBUFFERED=1"
ExecStart="$PYTHON_BIN" "$SIMCHAT_ROOT/scripts/entry.py" web --host $HOST --port $PORT --no-browser
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillMode=mixed
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
}

check_conflicts() {
  if [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/simchat.desktop" ]]; then
    note "检测到设置页写入的 XDG 自启动项："
    note "  ${XDG_CONFIG_HOME:-$HOME/.config}/autostart/simchat.desktop"
    note "请到设置页关闭「开机自启」，避免两套机制重复启动。"
  fi
  if [[ -f "$SIMCHAT_ROOT/data/lifecycle.json" ]]; then
    note "提示：SimChat 自带的「自动拉起」适合桌面环境；"
    note "服务器上建议只用本脚本的 systemd 守护，不要同时开启两者。"
  fi
}

cmd_install() {
  require_systemd
  check_conflicts
  mkdir -p "$UNIT_DIR"
  render_unit >"$UNIT_FILE"
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE_NAME"
  note "已安装并启动 $SERVICE_NAME"
  note "  自启动: $(systemctl --user is-enabled "$SERVICE_NAME" 2>/dev/null || true)"
  note "  服务:   $HOST:$PORT"
  note "  单元:   $UNIT_FILE"
  note "如需未登录也运行，需要管理员执行: sudo loginctl enable-linger $USER"
  note "查看日志: $0 logs"
}

cmd_uninstall() {
  require_systemd
  if [[ -f "$UNIT_FILE" ]]; then
    systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload
    note "已卸载 $SERVICE_NAME（SimChat 数据未删除）"
  else
    note "未找到 $UNIT_FILE，无需卸载"
  fi
}

cmd_start() {
  require_systemd
  systemctl --user start "$SERVICE_NAME"
  note "已启动 $SERVICE_NAME"
}

cmd_stop() {
  require_systemd
  systemctl --user stop "$SERVICE_NAME"
  note "已停止 $SERVICE_NAME；systemd 不会自动拉起"
}

cmd_restart() {
  require_systemd
  systemctl --user restart "$SERVICE_NAME"
  note "已重启 $SERVICE_NAME"
}

cmd_status() {
  require_systemd
  systemctl --user status --no-pager "$SERVICE_NAME" || true
}

cmd_logs() {
  require_systemd
  journalctl --user -u "$SERVICE_NAME" -n 200 -f
}

usage() {
  cat <<EOF
SimChat systemd 部署脚本

用法:
  $0 install    安装并启用（开机自启 + 异常拉起）
  $0 uninstall  停止并移除单元
  $0 start      启动
  $0 stop       停止（不会自动拉起）
  $0 restart    重启
  $0 status     查看状态
  $0 logs       跟踪日志

当前配置:
  Python: $PYTHON_BIN
  根目录: $SIMCHAT_ROOT
  监听:   $HOST:$PORT
  单元:   $UNIT_FILE
EOF
}

case "${1:-}" in
  install)    cmd_install ;;
  uninstall)  cmd_uninstall ;;
  start)      cmd_start ;;
  stop)       cmd_stop ;;
  restart)    cmd_restart ;;
  status)     cmd_status ;;
  logs)       cmd_logs ;;
  print-unit)
    require_systemd
    render_unit
    ;;
  ""|-h|--help|help) usage ;;
  *) usage; exit 2 ;;
esac
