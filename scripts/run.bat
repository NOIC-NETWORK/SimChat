@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  SimChat one-click launcher for Windows CMD
REM  Entry:  Web UI | MOD CLI
REM  Req:    Python >= 3.9
REM ============================================================

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

for %%P in ("%SCRIPT_DIR%\..")  do set "SIMCHAT_DIR=%%~fP"
for %%P in ("%SIMCHAT_DIR%\..") do set "PROJECT_ROOT=%%~fP"
set "REQUIREMENTS=%SCRIPT_DIR%\requirements-simchat.txt"

echo.
echo ========================================
echo    SimChat Launcher - Windows CMD
echo ========================================
echo.

REM ---------- 1. Locate Python ----------
echo [INFO] Locating Python...
set "PYTHON="

where python >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python') do (
        set "PYTHON=%%i"
        goto :found_python
    )
)
where py >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where py') do (
        set "PYTHON=%%i -3"
        goto :found_python
    )
)
where python3 >nul 2>&1
if %errorlevel%==0 (
    for /f "delims=" %%i in ('where python3') do (
        set "PYTHON=%%i"
        goto :found_python
    )
)

:no_python
echo [FAIL] No Python found on PATH (need >= 3.9)
echo   Download: https://www.python.org/downloads/
echo   Or:       winget install Python.Python.3.12
pause
exit /b 1

:found_python
%PYTHON% --version >nul 2>&1
if %errorlevel% neq 0 goto :no_python

for /f "tokens=*" %%v in ('%PYTHON% --version 2^>^&1') do echo [OK]   %%v

REM ---------- 2. Project root ----------
cd /d "%PROJECT_ROOT%"

REM ---------- 3. Dependencies ----------
echo.
echo [INFO] Checking dependencies...
set "NEED_INSTALL=0"

for %%P in (flask cryptography requests) do (
    %PYTHON% -c "import %%P" >nul 2>&1
    if !errorlevel! neq 0 (
        set "NEED_INSTALL=1"
        echo [WARN] Missing: %%P
    )
)

if "!NEED_INSTALL!"=="1" (
    echo [INFO] Installing dependencies...
    %PYTHON% -m pip install --upgrade pip >nul 2>&1
    %PYTHON% -m pip install -r "%REQUIREMENTS%"
    if !errorlevel! neq 0 (
        echo [FAIL] pip install failed. Try: pip install -r "%REQUIREMENTS%"
        pause
        exit /b 1
    )
)
echo [OK]   All dependencies ready

REM ---------- 4. Menu ----------
:menu
echo.
echo What do you want to do?
echo   1. Launch Web UI  ^(http://127.0.0.1:5000^)
echo   2. MOD CLI        ^(init / pack / verify / publish / gen-key^)
echo   3. Quit
echo.
set /p "CHOICE=Select [1-3]: "

if "%CHOICE%"=="1" goto :web
if "%CHOICE%"=="2" goto :cli
if "%CHOICE%"=="3" goto :bye

echo [WARN] Invalid choice "%CHOICE%"
goto :menu

:web
echo.
echo [INFO] Starting SimChat Web UI...
echo   URL:  http://127.0.0.1:5000
echo   Stop: Ctrl+C
echo.
%PYTHON% -m simchat.web
goto :menu

:cli
echo.
echo [INFO] SimChat MOD CLI - subcommands:
echo   init ^<type^> ^<name^>     Generate a MOD template
echo   pack ^<dir^>             Sign + integrity + zip
echo   verify ^<dir^>           Local integrity + signature check
echo   publish ^<dir^>          Build registry entry JSON
echo   gen-key                 Generate ed25519 keypair
echo.
set /p "SUB=Command (blank to go back): "
if "%SUB%"=="" goto :menu
echo.
%PYTHON% -m simchat.cli %SUB%
echo.
pause
goto :menu

:bye
echo Bye!
endlocal
exit /b 0
