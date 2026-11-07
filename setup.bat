@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 (
  echo Python 3.11+ is required. Install Python first.
  pause
  exit /b 1
)
echo [2/2] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your connection.
  pause
  exit /b 1
)
echo Setup completed. Please install FFmpeg separately if missing.
pause
