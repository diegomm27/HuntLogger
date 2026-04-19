@echo off
REM Build a single-file Windows executable for HuntLogger.
REM Requires: Python 3.10+ with the project's requirements installed, plus pyinstaller.

setlocal
pushd %~dp0

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name HuntLogger ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import windows_capture ^
    --hidden-import cv2 ^
    --hidden-import numpy ^
    run.py

echo.
echo Build complete. Executable is in dist\HuntLogger.exe
popd
endlocal
