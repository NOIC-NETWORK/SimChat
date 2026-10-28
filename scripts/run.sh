#!/usr/bin/env bash
# ============================================================================
#  SimChat one-click launcher for Linux / macOS / WSL
#  Entry:  Web UI | MOD CLI
#  Req:    Python >= 3.9
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIMCHAT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$SIMCHAT_DIR")"
REQUIREMENTS="$SCRIPT_DIR/requirements-simchat.txt"

# ---------- Colored helpers ----------
if [ -t 1 ]; then
    C_BOLD="\033[1m"; C_RED="\033[31m"; C_GREEN="\033[32m"
    C_YELLOW="\033[33m"; C_CYAN="\033[36m"; C_RESET="\033[0m"
else
    C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_RESET=""
fi

banner()  { echo -e "\n${C_CYAN}========================================${C_RESET}"; echo -e "${C_CYAN}   $*${C_RESET}"; echo -e "${C_CYAN}========================================${C_RESET}\n"; }
step()    { echo -e "${C_YELLOW}[INFO]${C_RESET}  $*"; }
ok()      { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
fail()    { echo -e "${C_RED}[FAIL]${C_RESET}  $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }

banner "SimChat Launcher - Unix (bash)"

# ---------- 1. Locate Python ----------
step "Locating Python >= 3.9..."
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            ok "Python found: $($PYTHON --version 2>&1)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "No Python >= 3.9 found on PATH"
    echo "  macOS:   brew install python@3.12"
    echo "  Debian:  sudo apt install python3 python3-pip"
    echo "  Fedora:  sudo dnf install python3 python3-pip"
    exit 1
fi

# ---------- 2. Project root ----------
cd "$PROJECT_ROOT"

# ---------- 3. Dependencies ----------
step "Checking dependencies..."
NEED_INSTALL=0
for pkg in flask cryptography requests; do
    if ! "$PYTHON" -c "import $pkg" &>/dev/null; then
        warn "Missing: $pkg"
        NEED_INSTALL=1
    fi
done

if [ "$NEED_INSTALL" -eq 1 ]; then
    step "Installing dependencies..."
    "$PYTHON" -m pip install --upgrade pip >/dev/null 2>&1 || true
    if "$PYTHON" -m pip install -r "$REQUIREMENTS"; then
        ok "Dependencies installed"
    else
        warn "pip install failed - trying with --user flag..."
        "$PYTHON" -m pip install --user -r "$REQUIREMENTS"
        ok "Dependencies installed (user-local)"
    fi
else
    ok "All dependencies ready"
fi

# ---------- 4. Menu ----------
show_menu() {
    echo
    echo -e "${C_BOLD}What do you want to do?${C_RESET}"
    echo "  1. Launch Web UI  (http://127.0.0.1:5000)"
    echo "  2. MOD CLI        (init / pack / verify / publish / gen-key)"
    echo "  3. Quit"
    echo
}

while true; do
    show_menu
    read -rp "Select [1-3]: " choice
    case "$choice" in
        1)
            echo
            step "Starting SimChat Web UI..."
            echo "  URL:  http://127.0.0.1:5000"
            echo "  Stop: Ctrl+C"
            echo
            "$PYTHON" -m simchat.web
            ;;
        2)
            echo
            step "SimChat MOD CLI - subcommands:"
            echo "  init <type> <name>     Generate a MOD template"
            echo "  pack <dir>             Sign + integrity + zip"
            echo "  verify <dir>           Local integrity + signature check"
            echo "  publish <dir>          Build registry entry JSON"
            echo "  gen-key                Generate ed25519 keypair"
            echo
            read -rp "Command (blank to go back): " sub
            if [ -n "$sub" ]; then
                echo
                # shellcheck disable=SC2086
                "$PYTHON" -m simchat.cli $sub
                echo
                read -rp "Press Enter to continue... " _
            fi
            ;;
        3)
            echo "Bye!"
            exit 0
            ;;
        *)
            warn "Invalid choice '$choice'"
            ;;
    esac
done
