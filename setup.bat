@echo off
REM One-time setup (Windows). Needs Python 3.10+: https://www.python.org/downloads/  (tick "Add python.exe to PATH" while installing)
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo.
  echo Python 3.10+ not found. Install it from https://www.python.org/downloads/
  echo While installing, tick "Add python.exe to PATH". Then double-click setup.bat again.
  pause
  exit /b 1
)
.venv\Scripts\python -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 (
  echo.
  echo Your Python is too old - version 3.10 or newer is needed.
  echo Install the latest from https://www.python.org/downloads/ then delete the .venv folder and run setup.bat again.
  pause
  exit /b 1
)

echo Installing packages (1-3 minutes)...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Package install failed - check your internet connection and run setup.bat again.
  pause
  exit /b 1
)

REM backup browser only if Google Chrome is not installed
set HAS_CHROME=0
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set HAS_CHROME=1
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set HAS_CHROME=1
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set HAS_CHROME=1
if %HAS_CHROME%==0 .venv\Scripts\python -m playwright install chromium

if not exist .env copy .env.example .env >nul

echo.
echo Install done. Starting the guided setup...
echo.
.venv\Scripts\python run.py start
pause
