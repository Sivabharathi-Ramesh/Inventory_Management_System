@echo off
:: ============================================================
::  Setup Script — Inventory Management System (AIAT Stemland)
::  Windows Setup: Installs Python 3.11, dependencies, and
::  all Python packages required to run the application.
:: ============================================================

setlocal EnableDelayedExpansion
set VENV_DIR=%~dp0venv
set PYTHON_VERSION=3.11.9
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set PYTHON_INSTALLER=%TEMP%\python_installer.exe

echo ======================================
echo  AIAT Stemland Inventory Setup
echo  Windows Environment
echo ======================================
echo.

:: ── Check Admin rights ───────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Please run this script as Administrator.
    echo Right-click setup_env_windows.bat and select "Run as administrator"
    pause
    exit /b 1
)

:: ── 1. Check if Python 3.11 is installed ─────────────────────
echo [1/6] Checking Python 3.11...
python --version 2>nul | findstr "3.11" >nul
if %errorlevel% equ 0 (
    echo   Python 3.11 already installed.
    set PYTHON_CMD=python
    goto :check_pip
)

py -3.11 --version 2>nul
if %errorlevel% equ 0 (
    echo   Python 3.11 found via py launcher.
    set PYTHON_CMD=py -3.11
    goto :check_pip
)

echo   Python 3.11 not found. Downloading installer...
echo   URL: %PYTHON_URL%
powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download Python installer.
    echo Please manually download from: https://www.python.org/downloads/release/python-3119/
    pause
    exit /b 1
)

echo   Installing Python 3.11 (this may take a minute)...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_tcltk=1 Include_pip=1
if %errorlevel% neq 0 (
    echo [ERROR] Python installation failed.
    pause
    exit /b 1
)
del "%PYTHON_INSTALLER%"

:: Refresh PATH
call refreshenv 2>nul
set PYTHON_CMD=py -3.11
echo   Python 3.11 installed successfully.

:check_pip
:: ── 2. Install Visual C++ Redistributable (needed by OpenCV) ─
echo.
echo [2/6] Checking Visual C++ Redistributable...
reg query "HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Visual C++ Redistributable already installed.
) else (
    echo   Downloading Visual C++ Redistributable...
    powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%TEMP%\vc_redist.exe'"
    "%TEMP%\vc_redist.exe" /quiet /norestart
    del "%TEMP%\vc_redist.exe"
    echo   Visual C++ Redistributable installed.
)

:: ── 3. Create virtual environment ────────────────────────────
echo.
echo [3/6] Creating Python 3.11 virtual environment...
if exist "%VENV_DIR%" (
    echo   Virtual environment already exists, skipping.
) else (
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    echo   Virtual environment created at: %VENV_DIR%
)

:: Activate venv
call "%VENV_DIR%\Scripts\activate.bat"

:: ── 4. Upgrade pip ───────────────────────────────────────────
echo.
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

:: ── 5. Install Python packages ───────────────────────────────
echo.
echo [5/6] Installing Python packages...
echo   This may take several minutes on first run...

pip install opencv-python==4.13.0.92
pip install insightface==1.0.1
pip install onnxruntime==1.26.0
pip install onnx==1.21.0
pip install faiss-cpu==1.14.2
pip install numpy==2.4.5
pip install scipy==1.17.1
pip install Pillow==12.2.0
pip install pyzbar==0.1.9
pip install pyttsx3
pip install pywin32
pip install qrcode

echo   Python packages installed.

:: ── 6. Pre-download InsightFace buffalo_sc model ─────────────
echo.
echo [6/6] Pre-downloading InsightFace buffalo_sc model...
python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_sc', providers=['CPUExecutionProvider']); app.prepare(ctx_id=0, det_size=(320,320)); print('  Model ready.')"

:: ── Create run.bat launcher ───────────────────────────────────
echo @echo off > "%~dp0run.bat"
echo call "%~dp0venv\Scripts\activate.bat" >> "%~dp0run.bat"
echo cd /d "%~dp0" >> "%~dp0run.bat"
echo python main.py >> "%~dp0run.bat"
echo pause >> "%~dp0run.bat"

echo.
echo ======================================
echo  Setup Complete!
echo ======================================
echo.
echo  To run the application:
echo    Double-click  run.bat
echo.
echo  Or manually:
echo    venv\Scripts\activate
echo    python main.py
echo.
pause
