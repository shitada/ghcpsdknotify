@echo off
setlocal EnableDelayedExpansion

:: ================================================================
::  Personal AI Daily Briefing Agent - One-click launcher
::
::  Double-click this file to:
::    1. Install uv (Python package manager)
::    2. Install Python 3.12+ (via uv)
::    3. Install gh CLI (via winget)
::    4. Install dependencies
::    5. Launch the application
:: ================================================================

set "PYTHONUTF8=1"
:: Resolve project root (parent of install/)
set "APP_DIR=%~dp0.."
pushd "%APP_DIR%"
set "APP_DIR=%CD%\"
popd
cd /d "%APP_DIR%"

title AI Daily Briefing Agent

echo.
echo ==============================================================
echo   Personal AI Daily Briefing Agent - Setup
echo ==============================================================
echo.

:: ---- Step 1: Check / install uv ----
echo [1/4] Checking uv (Python package manager)...

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo       uv not found. Installing...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" 2>nul
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install uv.
        echo         Please install manually: https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    :: Update PATH (uv installs to %USERPROFILE%\.local\bin)
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

    :: Verify
    where uv >nul 2>&1
    if !errorlevel! neq 0 (
        :: Fallback: try AppData path
        if exist "%LOCALAPPDATA%\uv\uv.exe" (
            set "PATH=%LOCALAPPDATA%\uv;%PATH%"
        ) else (
            echo [ERROR] uv was installed but not found in PATH.
            echo         Please restart your terminal and re-run start.bat.
            pause
            exit /b 1
        )
    )
    echo       uv installed successfully.
) else (
    echo       OK - uv found.
)

:: ---- Step 2: Check Python (managed by uv) ----
echo [2/4] Checking Python...

uv python find ">=3.12" >nul 2>&1
if %errorlevel% neq 0 (
    echo       Python 3.12+ not found. Installing...
    uv python install 3.12
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install Python.
        pause
        exit /b 1
    )
    echo       Python 3.12 installed successfully.
) else (
    echo       OK - Python 3.12+ found.
)

:: ---- Step 3: Check gh CLI ----
echo [3/4] Checking GitHub CLI (gh)...

where gh >nul 2>&1
if %errorlevel% neq 0 (
    echo       gh CLI not found. Attempting to install...

    where winget >nul 2>&1
    if !errorlevel! equ 0 (
        echo       Installing GitHub CLI via winget...
        winget install GitHub.cli --accept-package-agreements --accept-source-agreements -s winget
        if !errorlevel! neq 0 (
            echo [WARN] winget installation failed.
            echo        Please download from: https://cli.github.com
        ) else (
            echo       GitHub CLI installed successfully.
            :: Update PATH
            set "PATH=C:\Program Files\GitHub CLI;C:\Program Files (x86)\GitHub CLI;%PATH%"
        )
    ) else (
        echo [WARN] winget not available.
        echo        Please install GitHub CLI manually: https://cli.github.com
    )
) else (
    echo       OK - gh CLI found.
)

:: ---- Step 4: Sync dependencies and launch ----
echo [4/4] Syncing dependencies and launching...
echo.

uv sync --quiet 2>nul
if %errorlevel% neq 0 (
    echo       Dependency sync error. Retrying...
    uv sync
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo --------------------------------------------------------------
echo  Starting application...
echo  (This window will close when the app exits)
echo --------------------------------------------------------------
echo.

uv run python -m app.main

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code: %errorlevel%
    echo         Log file: %APP_DIR%logs\app.log
    pause
    exit /b %errorlevel%
)

endlocal
