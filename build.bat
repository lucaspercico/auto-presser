@echo off
setlocal
cd /d "%~dp0"

echo Gerando icone...
python tools\make_icon.py
if errorlevel 1 (
  echo Falha ao gerar icone.
  exit /b 1
)

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
  --icon assets\icon.ico ^
  --add-data "assets\icon.ico;assets" ^
  --add-data "assets\icon.png;assets" ^
  --add-data "assets\icon_64.png;assets" ^
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
