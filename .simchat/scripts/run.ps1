#requires -Version 5.0
<#
.SYNOPSIS
    SimChat one-click launcher for Windows PowerShell
.DESCRIPTION
    Auto-detects Python >= 3.9, installs missing dependencies, and offers
    an interactive menu:
      1. Launch Web UI  (scripts\\entry.py web)
      2. MOD CLI        (scripts\\entry.py cli <command>)
      3. Quit
.EXAMPLE
    .\run.ps1
#>

$ErrorActionPreference = "Stop"

# ---------- Path resolution ----------
# 本体收在 .simchat/ 里：ScriptDir = .simchat\scripts，SimChatDir = .simchat
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$SimChatDir   = Split-Path -Parent $ScriptDir
$Entry        = Join-Path $ScriptDir "entry.py"
$Requirements = Join-Path $ScriptDir "requirements-simchat.txt"

# ---------- Colored helpers ----------
function Write-Banner($text) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   $text" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}
function Step($msg)  { Write-Host "[INFO] $msg"  -ForegroundColor Yellow }
function Ok($msg)    { Write-Host "[OK]   $msg"  -ForegroundColor Green }
function Fail($msg)  { Write-Host "[FAIL] $msg"  -ForegroundColor Red }
function Warn($msg)  { Write-Host "[WARN] $msg"  -ForegroundColor Magenta }

# ---------- 1. Locate Python ----------
Write-Banner "
                                                                                 X                  X
    SSSSSSS   IIIIIII   MMMMMMM   CCCCCCC   H     H     A      TTTTTTT             X            X
   S            I      M  M  M   C         H     H    A  A        T           XXXXXXXXXXXXXXXXXXXXXX
  SSSSSS       I      M  M  M   C         HHHHHHH   AAAAAAA      T           X   X                X
      S       I      M  M  M  C         H     H    A      A     T           X      X             X
SSSSSSS   IIIIIII   M  M  M  CCCCCCC   H     H   A         A   T           X   X        XXXXX   X                                                                
                                                                          XXXXXXXXXXXXXXXXXXXXXX           
Everything, Harnessed.

"

Step "Locating Python..."
$PyCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue),
    (Get-Command python3 -ErrorAction SilentlyContinue),
    (Get-Command py -ErrorAction SilentlyContinue)
) | Where-Object { $_ -ne $null }

$Python = $null
foreach ($c in $PyCandidates) {
    try {
        $ver = & $c.Source --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python (\d+)\.(\d+)") {
            $major, $minor = [int]$Matches[1], [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 9)) {
                $Python = $c.Source
                Ok "Python found: $ver ($Python)"
                break
            } else {
                Warn "$ver is too old (need >= 3.9), skipping"
            }
        }
    } catch { }
}

if (-not $Python) {
    Fail "No Python >= 3.9 found on PATH"
    Write-Host "  Download: https://www.python.org/downloads/"
    Write-Host "  Or via winget: winget install Python.Python.3.12"
    Read-Host "Press Enter to exit"
    exit 1
}

# ---------- 2. Package root ----------
# 切换工作目录到包根（.simchat），data/、mods/ 等相对路径以此为准；
# 包名别名由 scripts/entry.py 负责，无需再设 PYTHONPATH。
Set-Location $SimChatDir

# ---------- 3. Dependencies ----------
Step "Checking dependencies..."
$needed = @()
foreach ($pkg in @("flask", "cryptography", "requests")) {
    try {
        & $Python -c "import $pkg" 2>$null
        if ($LASTEXITCODE -ne 0) { $needed += $pkg }
    } catch { $needed += $pkg }
}

if ($needed.Count -gt 0) {
    Warn "Missing packages: $($needed -join ', ') - installing..."
    & $Python -m pip install --upgrade pip | Out-Null
    & $Python -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        Fail "pip install failed. Try manually: pip install -r $Requirements"
        Read-Host "Press Enter to exit"
        exit 1
    }
    Ok "Dependencies installed"
} else {
    Ok "All dependencies OK"
}

# ---------- 4. Menu ----------
function Show-Menu {
    Write-Host ""
    Write-Host "What do you want to do?" -ForegroundColor White
    Write-Host "  1. Launch Web UI  (http://127.0.0.1:5000)" -ForegroundColor Gray
    Write-Host "  2. MOD CLI        (init / pack / verify / publish / gen-key)" -ForegroundColor Gray
    Write-Host "  3. Quit" -ForegroundColor Gray
    Write-Host ""
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Select [1-3]"

    switch ($choice) {
        "1" {
            Write-Host ""
            Step "Starting SimChat Web UI..."
            Write-Host "  URL: http://127.0.0.1:5000"
            Write-Host "  Press Ctrl+C to stop"
            Write-Host ""
            & $Python $Entry web
        }
        "2" {
            Write-Host ""
            Step "SimChat MOD CLI - subcommands:"
            Write-Host "  init <type> <name>         Generate a MOD template" -ForegroundColor Gray
            Write-Host "  pack <dir>                 Sign + integrity + zip" -ForegroundColor Gray
            Write-Host "  verify <dir>               Local integrity + signature check" -ForegroundColor Gray
            Write-Host "  publish <dir>              Build registry entry JSON" -ForegroundColor Gray
            Write-Host "  gen-key                    Generate ed25519 keypair" -ForegroundColor Gray
            Write-Host ""
            $sub = Read-Host "Command (or blank to go back)"
            if ($sub.Trim()) {
                Write-Host ""
                & $Python $Entry cli $sub.Split()
                Write-Host ""
                Read-Host "Press Enter to continue"
            }
        }
        "3" {
            Write-Host "Bye!" -ForegroundColor Green
            exit 0
        }
        default {
            Warn "Invalid choice '$choice'"
        }
    }
}
