@echo off
setlocal
chcp 65001 >nul

rem Run this file from a downloaded or cloned repository on Windows.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-launcher\start-demo.ps1" %*
if errorlevel 1 (
  echo.
  echo Room Harmony failed to start. Check the error message above.
  pause
  exit /b 1
)

endlocal
