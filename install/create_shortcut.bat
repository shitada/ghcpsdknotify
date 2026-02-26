@echo off
setlocal

:: ================================================================
::  Create desktop shortcut for AI Daily Briefing Agent
:: ================================================================

:: Resolve project root (parent of install/)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "APP_DIR=%CD%\"
popd

set "SHORTCUT_NAME=AI Daily Briefing.lnk"
set "DESKTOP=%USERPROFILE%\Desktop"
set "TARGET=%SCRIPT_DIR%start.bat"
set "ICON=%APP_DIR%assets\icon_normal.ico"

echo.
echo Creating desktop shortcut...

:: Create .lnk shortcut via PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$sc = $ws.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%'); " ^
    "$sc.TargetPath = '%TARGET%'; " ^
    "$sc.WorkingDirectory = '%APP_DIR%'; " ^
    "$sc.Description = 'Personal AI Daily Briefing Agent'; " ^
    "$sc.WindowStyle = 7; " ^
    "if (Test-Path '%ICON%') { $sc.IconLocation = '%ICON%' }; " ^
    "$sc.Save()"

if %errorlevel% equ 0 (
    echo.
    echo OK - Desktop shortcut created: %SHORTCUT_NAME%
    echo     Double-click it to launch the app.
) else (
    echo.
    echo FAILED - Could not create shortcut.
    echo          Please double-click install\start.bat directly to launch.
)

echo.
pause

endlocal
