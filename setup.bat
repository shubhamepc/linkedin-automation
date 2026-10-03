@echo off
REM One-time setup (Windows). Python 3.10+ chahiye: https://www.python.org/downloads/  (install karte waqt "Add to PATH" tick karna)
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Python 3.10+ nahi mila. Install karo: https://www.python.org/downloads/
  pause
  exit /b 1
)

.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
REM Chrome na ho to backup browser
.venv\Scripts\python -m playwright install chromium
if not exist .env copy .env.example .env >nul

echo.
echo Setup done. Ab guided setup shuru ho raha hai...
echo.
.venv\Scripts\python run.py start
pause
