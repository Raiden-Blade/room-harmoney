@echo off
setlocal
chcp 65001 >nul

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0demo-launcher\stop-demo.ps1"
if errorlevel 1 (
  echo.
  echo Room Harmony failed to stop. Check the error message above.
  pause
  exit /b 1
)

endlocal
