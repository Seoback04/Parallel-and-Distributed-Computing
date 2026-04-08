@echo off
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip
python -m pip install pyinstaller -r requirements.txt

pyinstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name JobBotV2 ^
  app_gui.py

if errorlevel 1 (
  echo.
  echo EXE build failed.
  pause
  exit /b 1
)

echo.
echo Build complete.
echo EXE path: dist\JobBotV2.exe
pause
