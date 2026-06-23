@echo off
setlocal EnableDelayedExpansion

set APP=InventoryManagement
set VERSION=1.0.0
set RELEASE=release\windows-onedir-%VERSION%

:: Python 3.11 path
set PYTHON311=C:\Users\franc\AppData\Local\Programs\Python\Python311\python.exe

echo.
echo =====================================================
echo  Inventory Management ^| Windows Build Pipeline
echo  Version: %VERSION%
echo =====================================================
echo.

:: Verify Python 3.11 exists
if not exist "%PYTHON311%" (
    echo [ERROR] Python 3.11 not found:
    echo %PYTHON311%
    pause
    exit /b 1
)

:: Create venv if missing
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [INFO] Creating Python 3.11 virtual environment...
    "%PYTHON311%" -m venv "%~dp0venv"

    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate venv
echo [INFO] Activating virtual environment...
call "%~dp0venv\Scripts\activate.bat"

:: Verify version
echo.
echo [INFO] Active Python:
python --version
where python
echo.

:: Install dependencies
echo [INFO] Installing PyInstaller...
python -m pip install --upgrade pip
python -m pip install pyinstaller

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)