#!/usr/bin/env bash
# ============================================================================
#  SimChat launcher for HarmonyOS PC (with Linux sub-environment)
#
#  Strategy (3-layer auto-detection):
#    Layer 1: HarmonyOS PC + Fusion Dev Engine (openEuler Linux)
#             -> run python3 + pip directly inside the Linux sub-env (RECOMMENDED)
#    Layer 2: HarmonyOS PC + PC Software Engine (Windows compat layer)
#             -> use Windows Python if present
#    Layer 3: CodeArts IDE only (no pip)
#             -> print setup instructions for Layer 1
#
#  Prerequisites for Layer 1:
#    - HarmonyOS PC with HarmonyOS 6.1+
#    - Fusion Dev Engine installed and started
#      (search "Fusion Dev Engine" in AppGallery, install and launch)
#    - Project dir added to shared folders -> /mnt/linux_share/<name>
# ============================================================================

set -euo pipefail

# ---------- Colored helpers (pure ASCII markers, no Unicode) ----------
if [ -t 1 ]; then
    C_BOLD="\033[1m"; C_RED="\033[31m"; C_GREEN="\033[32m"
    C_YELLOW="\033[33m"; C_CYAN="\033[36m"; C_BLUE="\033[34m"; C_RESET="\033[0m"
else
    C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_BLUE=""; C_RESET=""
fi

banner()  { echo -e "\n${C_CYAN}============================================${C_RESET}"; echo -e "${C_CYAN}   $*${C_RESET}"; echo -e "${C_CYAN}============================================${C_RESET}\n"; }
step()    { echo -e "${C_YELLOW}[INFO]${C_RESET}  $*"; }
ok()      { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
fail()    { echo -e "${C_RED}[FAIL]${C_RESET}  $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
info()    { echo -e "${C_BLUE}[HARMONY]${C_RESET} $*"; }

banner "SimChat Launcher - HarmonyOS PC Adapter"

# ---------- Host detection ----------
step "Probing host environment..."
IS_HARMONY=false
if [ -f /system/bin/harmony ] || [ -f /etc/harmony-version ] || command -v hdc &>/dev/null; then
    IS_HARMONY=true
    ok "HarmonyOS host detected"
elif command -v getprop &>/dev/null && getprop ro.build.version.release &>/dev/null; then
    IS_HARMONY=true
    ok "HarmonyOS (device) detected via getprop"
else
    info "Not running natively on HarmonyOS"
    info "(This script is safe to run from macOS/Linux too)"
fi

# ---------- Path resolution ----------
# Inside the Fusion Dev Engine, the HarmonyOS-side shared folder is
# mounted at /mnt/linux_share/<folder-name>. Prefer that, fall back to cwd.
resolve_project_root() {
    # Common locations inside Fusion Dev Engine
    for candidate in \
        /mnt/linux_share/LMBrewer \
        /mnt/linux_share/lmbrewer \
        /mnt/linux_share/simchat \
        "$(pwd)"; do
        if [ -d "$candidate/simchat" ] || [ -d "$candidate/cli" ]; then
            echo "$candidate"
            return 0
        fi
    done
    pwd
}

PROJECT_ROOT="$(resolve_project_root)"
SIMCHAT_DIR="$PROJECT_ROOT/simchat"
REQUIREMENTS="$SIMCHAT_DIR/scripts/requirements-simchat.txt"

step "Project root: $PROJECT_ROOT"

# ---------- Layer 1: Fusion Dev Engine (openEuler) ----------
detect_layer1() {
    # If hdc is available, the user can deploy SimChat to a device too
    if command -v hdc &>/dev/null; then
        info "hdc detected - you can deploy SimChat to a HarmonyOS device"
    fi
    # Detect openEuler-compatible Linux env (python3 + dnf/yum)
    if command -v python3 &>/dev/null && (command -v dnf &>/dev/null || command -v yum &>/dev/null); then
        PYTHON="python3"
        ok "Layer 1 available: Linux sub-environment with $($PYTHON --version 2>&1)"
        return 0
    fi
    return 1
}

# ---------- Layer 2: PC Software Engine (Windows Python) ----------
detect_layer2() {
    # HarmonyOS PC Software Engine exposes Windows filesystem in some paths.
    # Unlikely to hit this inside bash, but keep the logic.
    if command -v python.exe &>/dev/null; then
        PYTHON="python.exe"
        ok "Layer 2 available: Windows Python via PC Software Engine"
        return 0
    fi
    return 1
}

# ---------- Layer 3: CodeArts IDE bundled Python (no pip) ----------
detect_layer3() {
    if command -v python &>/dev/null && ! command -v pip &>/dev/null; then
        ok "Layer 3 available: CodeArts IDE bundled Python (no pip)"
        return 0
    fi
    return 1
}

PYTHON=""
LAYER=0

if detect_layer1; then LAYER=1
elif detect_layer2; then LAYER=2
elif detect_layer3; then LAYER=3
fi

if [ "$LAYER" -eq 0 ]; then
    fail "No usable Python environment found"
    echo ""
    echo "  ${C_BOLD}Install one of the following (priority top-down):${C_RESET}"
    echo ""
    echo "  ${C_GREEN}[1] RECOMMENDED${C_RESET}  Fusion Dev Engine (openEuler Linux)"
    echo "     - Search for 'Fusion Dev Engine' in HarmonyOS AppGallery, install and launch"
    echo "     - Settings -> File Sharing -> add your project folder"
    echo "     - The shared dir will appear at /mnt/linux_share/<folder-name> inside Linux"
    echo "     - Then re-run this script from there"
    echo ""
    echo "  ${C_BLUE}[2] ALTERNATIVE${C_RESET}  PC Software Engine + Git Bash"
    echo "     - Run Windows Python + Git Bash on HarmonyOS PC via compat layer"
    echo "     - Then run this script inside Git Bash"
    echo ""
    echo "  ${C_YELLOW}[3] EXPERIMENTAL${C_RESET}  CodeArts IDE"
    echo "     - CodeArts IDE has built-in Python but currently no pip support"
    echo "     - Not suitable for SimChat yet"
    exit 1
fi

# ---------- Dependency install ----------
echo ""
step "Installing dependencies..."
NEED_PIP=true
if [ "$LAYER" -eq 3 ]; then
    # CodeArts has no pip - skip and remind user to get Fusion Dev Engine
    warn "CodeArts IDE Python does not support pip yet"
    warn "Skipping auto-install. Please use Fusion Dev Engine (Layer 1) instead."
    NEED_PIP=false
fi

if $NEED_PIP; then
    # openEuler may not have pip preinstalled - try dnf/yum first
    if ! $PYTHON -m pip --version &>/dev/null; then
        step "pip not found - installing via dnf/yum..."
        if command -v dnf &>/dev/null; then
            sudo dnf install -y python3-pip || true
        elif command -v yum &>/dev/null; then
            sudo yum install -y python3-pip || true
        fi
    fi
    $PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true
    if $PYTHON -m pip install -r "$REQUIREMENTS"; then
        ok "Dependencies installed"
    else
        warn "pip install failed - trying --user flag..."
        $PYTHON -m pip install --user -r "$REQUIREMENTS" \
            && ok "Dependencies installed (user-local)" \
            || { fail "pip install failed. Check network / DNS settings"; exit 1; }
    fi
fi

# ---------- Launch menu ----------
echo ""
info "Running via Layer $LAYER ($PYTHON)"

show_menu() {
    echo ""
    echo -e "${C_BOLD}SimChat on HarmonyOS - What do you want to do?${C_RESET}"
    echo "  1. Start Web UI          http://127.0.0.1:5000"
    echo "  2. Start Web UI (debug)  with --debug flag"
    echo "  3. MOD CLI toolchain     init / pack / verify / publish / gen-key"
    echo "  4. Quit"
    echo ""
}

cd "$PROJECT_ROOT"

while true; do
    show_menu
    read -rp "Select [1-4]: " choice
    case "$choice" in
        1)
            echo
            step "Starting SimChat Web UI..."
            echo "  URL:  http://127.0.0.1:5000"
            if [ "$LAYER" -eq 1 ]; then
                echo "  Fusion Dev Engine LAN IP: run 'ip addr' and find 192.168.x.x"
                echo "  Then open http://<that-IP>:5000 from the HarmonyOS browser"
            fi
            echo "  Stop: Ctrl+C"
            echo
            $PYTHON -m simchat.web
            ;;
        2)
            echo
            step "Starting SimChat Web UI (debug mode)..."
            echo "  URL:  http://127.0.0.1:5000"
            echo "  Stop: Ctrl+C"
            echo
            $PYTHON -m simchat.web --debug
            ;;
        3)
            echo
            step "MOD CLI - subcommands:"
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
                $PYTHON -m simchat.cli $sub
                echo
                read -rp "Press Enter to continue... " _
            fi
            ;;
        4)
            echo "Bye!"
            exit 0
            ;;
        *)
            warn "Invalid choice '$choice'"
            ;;
    esac
done
