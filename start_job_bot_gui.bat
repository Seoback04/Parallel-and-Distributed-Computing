@echo off
setlocal
cd /d "%~dp0"

python app_gui.py

if errorlevel 1 (
  echo.
  echo Failed to start Job Bot GUI.
  echo Make sure Python and dependencies are installed.
  pause
)
