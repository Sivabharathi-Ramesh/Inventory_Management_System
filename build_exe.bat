@echo off
:: ============================================================
::  Build Launcher — Inventory Management System (AIAT Stemland)
::  Windows Batch Wrapper to compile the python files to .exe
:: ============================================================

echo ======================================
echo  AIAT Stemland Executable Builder
echo  Windows Environment Launcher
echo ======================================
echo.

:: Check if virtual environment exists and activate it
if exist "%~dp0venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call "%~dp0venv\Scripts\activate.bat"
) else (
    echo [WARNING] Virtual environment venv not found.
    echo Running with system default python if available.
    echo.
)

:: Run the python build automation script
python "%~dp0build_exe.py"

echo.
echo Build script execution finished.
pause
