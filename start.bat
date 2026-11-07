@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage.ps1" -Action Open
if errorlevel 1 (
  echo Startup failed. Check logs\startup.log and logs\*.stderr.log
  pause
  exit /b 1
)
