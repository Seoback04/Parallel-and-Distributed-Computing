@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install dependencies. Please check internet connection and Python setup.
  pause
  exit /b 1
)

start "" pythonw app_gui.py
