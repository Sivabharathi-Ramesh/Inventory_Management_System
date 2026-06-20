# ============================================================
#  Setup Script — Inventory Management System (AIAT Stemland)
#  PowerShell version for Windows
#  Run with: Right-click → "Run with PowerShell" (as Admin)
# ============================================================

$ErrorActionPreference = "Stop"
$VENV_DIR = Join-Path $PSScriptRoot "venv"
$PYTHON_VERSION = "3.11.9"
$PYTHON_URL = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-amd64.exe"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host " AIAT Stemland Inventory Setup" -ForegroundColor Cyan
Write-Host " Windows Environment (PowerShell)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# ── Check Admin ──────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] Please run as Administrator." -ForegroundColor Red
    Write-Host "Right-click the script and select 'Run as Administrator'" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# ── 1. Python 3.11 ───────────────────────────────────────────
Write-Host "`n[1/6] Checking Python 3.11..." -ForegroundColor Green
$pythonCmd = $null

try {
    $ver = & py -3.11 --version 2>&1
    if ($ver -match "3\.11") { $pythonCmd = "py -3.11" }
} catch {}

if (-not $pythonCmd) {
    try {
        $ver = & python --version 2>&1
        if ($ver -match "3\.11") { $pythonCmd = "python" }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "  Python 3.11 not found. Downloading..." -ForegroundColor Yellow
    $installer = "$env:TEMP\python_installer.exe"
    Invoke-WebRequest -Uri $PYTHON_URL -OutFile $installer -UseBasicParsing
    Write-Host "  Installing Python 3.11..."
    Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_tcltk=1 Include_pip=1" -Wait
    Remove-Item $installer
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    $pythonCmd = "py -3.11"
    Write-Host "  Python 3.11 installed." -ForegroundColor Green
} else {
    Write-Host "  Python 3.11 found: $pythonCmd" -ForegroundColor Green
}

# ── 2. Visual C++ Redistributable ────────────────────────────
Write-Host "`n[2/6] Checking Visual C++ Redistributable..." -ForegroundColor Green
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
if (Test-Path $vcKey) {
    Write-Host "  Already installed." -ForegroundColor Green
} else {
    Write-Host "  Downloading Visual C++ Redistributable..."
    $vcInstaller = "$env:TEMP\vc_redist.exe"
    Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile $vcInstaller -UseBasicParsing
    Start-Process -FilePath $vcInstaller -ArgumentList "/quiet /norestart" -Wait
    Remove-Item $vcInstaller
    Write-Host "  Visual C++ Redistributable installed." -ForegroundColor Green
}

# ── 3. Virtual environment ────────────────────────────────────
Write-Host "`n[3/6] Creating virtual environment..." -ForegroundColor Green
if (Test-Path $VENV_DIR) {
    Write-Host "  Virtual environment already exists, skipping." -ForegroundColor Yellow
} else {
    Invoke-Expression "$pythonCmd -m venv `"$VENV_DIR`""
    Write-Host "  Virtual environment created at: $VENV_DIR" -ForegroundColor Green
}

# Activate
$activateScript = Join-Path $VENV_DIR "Scripts\Activate.ps1"
& $activateScript

# ── 4. Upgrade pip ───────────────────────────────────────────
Write-Host "`n[4/6] Upgrading pip..." -ForegroundColor Green
pip install --upgrade pip setuptools wheel

# ── 5. Install packages ───────────────────────────────────────
Write-Host "`n[5/6] Installing Python packages..." -ForegroundColor Green
Write-Host "  This may take several minutes on first run..." -ForegroundColor Yellow

$packages = @(
    "opencv-python==4.13.0.92",
    "insightface==1.0.1",
    "onnxruntime==1.26.0",
    "onnx==1.21.0",
    "faiss-cpu==1.14.2",
    "numpy==2.4.5",
    "scipy==1.17.1",
    "Pillow==12.2.0",
    "pyzbar==0.1.9",
    "pyttsx3",
    "pywin32"
)

foreach ($pkg in $packages) {
    Write-Host "  Installing $pkg..."
    pip install $pkg
}

Write-Host "  All packages installed." -ForegroundColor Green

# ── 6. Pre-download InsightFace model ────────────────────────
Write-Host "`n[6/6] Pre-downloading InsightFace buffalo_sc model..." -ForegroundColor Green
python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_sc', providers=['CPUExecutionProvider']); app.prepare(ctx_id=0, det_size=(320,320)); print('  Model ready.')"

# ── Create run.bat ────────────────────────────────────────────
$runBat = Join-Path $PSScriptRoot "run.bat"
@"
@echo off
call "%~dp0venv\Scripts\activate.bat"
cd /d "%~dp0"
python main.py
pause
"@ | Set-Content $runBat

Write-Host "`n======================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " To run the application:" -ForegroundColor White
Write-Host "   Double-click  run.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host " Or from PowerShell:" -ForegroundColor White
Write-Host "   .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "   python main.py" -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to exit"
