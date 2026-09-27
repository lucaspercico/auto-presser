@echo off
setlocal
cd /d "%~dp0"

echo Instalando dependencias de build...
python -m pip install -r requirements.txt pyinstaller -q

echo.
echo Gerando AutoPresser.exe (sem console)...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name AutoPresser ^
  --collect-all customtkinter ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  auto_keyboard_presser.py

if errorlevel 1 (
  echo Build falhou.
  exit /b 1
)

echo.
echo Pronto: dist\AutoPresser.exe
endlocal
