@echo off
:: ============================================================
::  Inventory Management — Windows Native Build Script
::  Run this on a Windows machine to produce InventoryManagement.exe
:: ============================================================
setlocal EnableDelayedExpansion

set APP=InventoryManagement
set VERSION=1.0.0
set RELEASE=release\windows-onedir-%VERSION%

echo.
echo  =====================================================
echo   Inventory Management  ^|  Windows Build Pipeline
echo   Version: %VERSION%
echo  =====================================================
echo.

:: ── Activate venv if present ────────────────────────────────
if exist "%~dp0venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment ...
    call "%~dp0venv\Scripts\activate.bat"
) else (
    echo [WARN] venv not found, using system Python.
)

:: ── Ensure PyInstaller ──────────────────────────────────────
python -m pip install pyinstaller --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause & exit /b 1
)

:: ── Prompt build mode ───────────────────────────────────────
echo  Select build mode:
echo    [1] Directory (onedir)  — recommended, fast startup
echo    [2] Single file (onefile)
set /p CHOICE="  Enter choice [1/2, default 1]: "
if "%CHOICE%"=="2" (
    set MODE_FLAG=--onefile
    set RELEASE=release\windows-onefile-%VERSION%
) else (
    set MODE_FLAG=--onedir
)

:: ── Run PyInstaller ─────────────────────────────────────────
echo.
echo [INFO] Running PyInstaller ...
pyinstaller ^
    --noconfirm ^
    %MODE_FLAG% ^
    --windowed ^
    --name=%APP% ^
    --icon=icons\admin_icon.ico ^
    --collect-all PIL ^
    --collect-all cv2 ^
    --collect-all numpy ^
    --collect-all qrcode ^
    --collect-all faiss ^
    --collect-all onnxruntime ^
    --collect-all onnx ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageTk ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import PIL.ImageFont ^
    --hidden-import cv2 ^
    --hidden-import numpy ^
    --hidden-import qrcode ^
    --hidden-import qrcode.image.pil ^
    --hidden-import faiss ^
    --hidden-import onnxruntime ^
    --hidden-import sqlite3 ^
    --add-data "icons;icons" ^
    --add-data "haarcascade_frontalface_default.xml;." ^
    --add-data "haarcascade_eye.xml;." ^
    main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause & exit /b 1
)

:: ── Copy to release folder ───────────────────────────────────
echo.
echo [INFO] Copying artefacts to %RELEASE% ...
if not exist "%RELEASE%" mkdir "%RELEASE%"

if "%CHOICE%"=="2" (
    copy /Y "dist\%APP%.exe" "%RELEASE%\%APP%.exe"
) else (
    xcopy /E /I /Y "dist\%APP%" "%RELEASE%\%APP%"
)

:: Copy runtime support files
for %%F in (DB_FILE face_encodings.pkl haarcascade_frontalface_default.xml haarcascade_eye.xml) do (
    if exist "%%F" copy /Y "%%F" "%RELEASE%\%%F"
)

:: Write README
echo Inventory Management System  v%VERSION% > "%RELEASE%\README.txt"
echo Target: Windows >> "%RELEASE%\README.txt"
echo. >> "%RELEASE%\README.txt"
echo HOW TO RUN >> "%RELEASE%\README.txt"
echo 1. Copy DB_FILE into this folder. >> "%RELEASE%\README.txt"
echo 2. Double-click %APP%.exe to launch. >> "%RELEASE%\README.txt"

echo.
echo  =====================================================
echo   BUILD COMPLETE
echo   Output : %RELEASE%
echo  =====================================================
echo.
pause
