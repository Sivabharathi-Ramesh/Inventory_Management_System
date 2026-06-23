#!/usr/bin/env python3
"""
pipeline.py — Single-file local build pipeline
Inventory Management System

Usage (Linux / Windows / macOS):
    python pipeline.py            # build both Linux + Windows → release/
    python pipeline.py --onefile  # same, but pack into one executable
    python pipeline.py linux      # Linux only
    python pipeline.py windows    # Windows only (Wine cross-compile or native)
    python pipeline.py clean      # wipe build artefacts and release/

Output layout:
    release/
    ├── linux-onedir-1.0.0/
    │   ├── InventoryManagement/   ← portable directory binary
    │   ├── DB_FILE
    │   ├── face_encodings.pkl
    │   └── README.txt
    └── windows-onedir-1.0.0/
        ├── InventoryManagement/
        │   └── InventoryManagement.exe
        ├── DB_FILE
        ├── face_encodings.pkl
        └── README.txt
"""

# ─────────────────────────────────────────────────────────────────────────────
#  Standard-library only — no third-party imports at module level
# ─────────────────────────────────────────────────────────────────────────────
import argparse
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  Project configuration  (edit these to match your project)
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME    = "InventoryManagement"
VERSION     = "1.0.0"
ENTRY_POINT = "main.py"

HERE        = Path(__file__).parent.resolve()
RELEASE_DIR = HERE / "release"
ICONS_DIR   = HERE / "icons"

# (source path, destination folder inside the bundle)
DATA_FILES = [
    (str(ICONS_DIR),                                           "icons"),
    (str(HERE / "haarcascade_frontalface_default.xml"),        "cv2/data"),
    (str(HERE / "haarcascade_eye.xml"),                        "cv2/data"),
]

# Extra PyInstaller flags applied to every build
COMMON_FLAGS = [
    "--noconfirm",
    "--collect-submodules", "PIL",
    "--collect-submodules", "cv2",
    "--hidden-import", "pyzbar.pyzbar",
    "--hidden-import", "qrcode.image.pil",
]

# Loose runtime files copied next to the executable in release/
RUNTIME_FILES = [
    "DB_FILE",
    "face_encodings.pkl",
    "haarcascade_frontalface_default.xml",
    "haarcascade_eye.xml",
]

# ─────────────────────────────────────────────────────────────────────────────
#  Logging helpers
# ─────────────────────────────────────────────────────────────────────────────

_W = 60  # banner width

def _banner(title: str):
    print("\n" + "─" * _W)
    print(f"  {title}")
    print("─" * _W)

def _ok(msg):   print(f"  [OK]   {msg}")
def _warn(msg): print(f"  [WARN] {msg}")
def _err(msg):  print(f"  [ERR]  {msg}", file=sys.stderr)
def _step(msg): print(f"  [>>]   {msg}")

def _run(cmd: list, **kwargs):
    flat = " ".join(str(c) for c in cmd)
    _step(flat)
    subprocess.run(cmd, check=True, **kwargs)

# ─────────────────────────────────────────────────────────────────────────────
#  Environment checks
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dependencies():
    """Install requirements.txt + PyInstaller into the current Python env."""
    req = HERE / "requirements.txt"
    if req.exists():
        _step("Installing requirements.txt …")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req), "--quiet"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _warn("Some packages failed to install — build may still succeed if deps are already present.")
            for line in result.stderr.splitlines():
                if line.strip():
                    _warn(f"  pip: {line.strip()}")
        else:
            _ok("Dependencies installed")
    else:
        _warn("requirements.txt not found — skipping dependency install")

    try:
        import PyInstaller as _pyi   # noqa: F401
        _ok(f"PyInstaller {_pyi.__version__}")
    except ImportError:
        _warn("PyInstaller not found — installing …")
        _run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        _ok("PyInstaller installed")

def _on_windows() -> bool:
    return platform.system().lower() == "windows"

def _on_linux() -> bool:
    return platform.system().lower() == "linux"

# ─────────────────────────────────────────────────────────────────────────────
#  PyInstaller command builder
# ─────────────────────────────────────────────────────────────────────────────

def _pyi_cmd(target_os: str, onefile: bool,
             python_exe: str = sys.executable) -> list:
    """
    Build the pyinstaller command list for the requested target OS.
    target_os : "linux" | "windows"
    python_exe: path to the Python interpreter to use (allows Wine Python)
    """
    sep = ";" if target_os == "windows" else ":"

    cmd = [python_exe, "-m", "PyInstaller"]
    cmd += COMMON_FLAGS
    cmd += ["--onefile" if onefile else "--onedir"]
    cmd += ["--windowed"]           # suppress console window for GUI apps
    cmd += [f"--name={APP_NAME}"]

    # Attach data files that actually exist on disk
    for src, dst in DATA_FILES:
        if Path(src).exists():
            cmd += ["--add-data", f"{src}{sep}{dst}"]
        else:
            _warn(f"Skipping missing data path: {src}")

    # Windows icon
    if target_os == "windows":
        ico = ICONS_DIR / "admin_icon.ico"
        if ico.exists():
            cmd += ["--icon", str(ico)]

    cmd.append(ENTRY_POINT)
    return cmd

# ─────────────────────────────────────────────────────────────────────────────
#  Output packaging helpers
# ─────────────────────────────────────────────────────────────────────────────

def _copy_runtime_files(dest: Path):
    """Copy loose runtime files next to the executable."""
    for name in RUNTIME_FILES:
        src = HERE / name
        if src.exists():
            shutil.copy2(src, dest / name)
            _ok(f"Copied {name}")

def _write_readme(dest: Path, target_os: str, onefile: bool):
    mode = "single executable" if onefile else "portable directory"
    if target_os == "windows":
        exe = f"{APP_NAME}.exe" if onefile else f"{APP_NAME}\\{APP_NAME}.exe"
        run_hint = f'Double-click "{exe}" to launch.'
    else:
        exe = APP_NAME if onefile else f"{APP_NAME}/{APP_NAME}"
        run_hint = f'Run "./{exe}" to launch.'

    text = (
        f"{APP_NAME}  v{VERSION}\n"
        f"Built : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Target: {target_os.title()}  |  Mode: {mode}\n"
        "\n"
        "HOW TO RUN\n"
        "----------\n"
        "1. Ensure DB_FILE is in this folder (same level as the executable).\n"
        "2. Ensure face_encodings.pkl is also in this folder.\n"
        f"3. {run_hint}\n"
    )
    (dest / "README.txt").write_text(text)

def _collect_dist(dest: Path, target_os: str, onefile: bool):
    """Move PyInstaller's dist/ output into the release destination folder."""
    if onefile:
        # single-file build produces dist/<APP> or dist/<APP>.exe
        candidates = [
            HERE / "dist" / f"{APP_NAME}.exe",   # Windows onefile
            HERE / "dist" / APP_NAME,             # Linux onefile
        ]
        for src in candidates:
            if src.exists():
                out = dest / src.name
                shutil.copy2(src, out)
                if target_os == "linux":
                    os.chmod(out, 0o755)
                _ok(f"Binary → {out}")
                return
        _err("onefile binary not found in dist/")
        sys.exit(1)
    else:
        # onedir build produces dist/<APP>/
        src = HERE / "dist" / APP_NAME
        if src.exists():
            out = dest / APP_NAME
            shutil.copytree(src, out, dirs_exist_ok=True)
            if target_os == "linux":
                binary = out / APP_NAME
                if binary.exists():
                    os.chmod(binary, 0o755)
            _ok(f"Directory → {out}")
        else:
            _err(f"onedir output not found: {src}")
            sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
#  Build: Linux
# ─────────────────────────────────────────────────────────────────────────────

def build_linux(onefile: bool) -> Path:
    _banner("BUILD  Linux portable binary")

    if not _on_linux():
        _warn("Current OS is not Linux — skipping native Linux build.")
        _warn("To produce a Linux binary, run this script on a Linux machine.")
        return None

    tag  = "onefile" if onefile else "onedir"
    dest = RELEASE_DIR / f"linux-{tag}-{VERSION}"
    dest.mkdir(parents=True, exist_ok=True)

    os.chdir(HERE)
    _run(_pyi_cmd("linux", onefile))
    _collect_dist(dest, "linux", onefile)
    _copy_runtime_files(dest)
    _write_readme(dest, "linux", onefile)

    # Clean PyInstaller work dirs (keep spec for reference)
    for d in ["build", "dist"]:
        p = HERE / d
        if p.exists():
            shutil.rmtree(p)

    _ok(f"Linux release ready  →  {dest}")
    return dest

# ─────────────────────────────────────────────────────────────────────────────
#  Build: Windows
# ─────────────────────────────────────────────────────────────────────────────

def build_windows(onefile: bool) -> Path:
    _banner("BUILD  Windows .exe")

    tag  = "onefile" if onefile else "onedir"
    dest = RELEASE_DIR / f"windows-{tag}-{VERSION}"
    dest.mkdir(parents=True, exist_ok=True)

    if _on_windows():
        # ── Native Windows build ──────────────────────────────────────────
        _step("Native Windows build")
        os.chdir(HERE)
        _run(_pyi_cmd("windows", onefile))
        _collect_dist(dest, "windows", onefile)
        _copy_runtime_files(dest)
        _write_readme(dest, "windows", onefile)
        for d in ["build", "dist"]:
            p = HERE / d
            if p.exists():
                shutil.rmtree(p)
        _ok(f"Windows release ready  →  {dest}")
        return dest

    # ── Linux: try Wine cross-compile ────────────────────────────────────
    wine = shutil.which("wine") or shutil.which("wine64")
    if wine:
        wine_pythons = sorted(
            Path.home().glob(".wine/drive_c/Python*/python.exe")
        )
        if wine_pythons:
            wine_python = str(wine_pythons[-1])
            _step(f"Wine cross-compile  ({wine_python})")
            os.chdir(HERE)
            _run(_pyi_cmd("windows", onefile, python_exe=wine_python))
            _collect_dist(dest, "windows", onefile)
            _copy_runtime_files(dest)
            _write_readme(dest, "windows", onefile)
            for d in ["build", "dist"]:
                p = HERE / d
                if p.exists():
                    shutil.rmtree(p)
            _ok(f"Windows release ready  →  {dest}")
            return dest
        else:
            _warn("Wine found but no Windows Python under ~/.wine/drive_c/Python*/")
            _warn("Install it with: winetricks python311")
    else:
        _warn("Wine not found (install with: sudo apt install wine)")

    # ── Docker cross-compile (tobix/pywine image) ────────────────────────
    if shutil.which("docker"):
        _ok("Docker found — attempting Windows cross-compile via tobix/pywine:3.9")
        result = _build_windows_docker(dest, onefile)
        if result:
            return dest

    # ── Fallback: write a native build script the user can run on Windows ─
    _warn("Falling back to generating a self-contained Windows build script.")
    _write_windows_build_script(dest, onefile)
    _copy_runtime_files(dest)
    _write_readme(dest, "windows", onefile)
    _ok(f"Windows launcher written  →  {dest}")
    return dest


def _build_windows_docker(dest: Path, onefile: bool) -> bool:
    """
    Cross-compile Windows .exe using tobix/pywine Docker image.
    Returns True on success, False on failure.
    """
    DOCKER_IMAGE = "tobix/pywine:3.9"
    mode_flag    = "--onefile" if onefile else "--onedir"
    sep          = ";"

    # Pull image if not present
    pull_check = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE],
        capture_output=True
    )
    if pull_check.returncode != 0:
        _step(f"Pulling Docker image {DOCKER_IMAGE} …")
        subprocess.run(["docker", "pull", DOCKER_IMAGE], check=True)

    # Build data-file args as a shell string fragment
    data_args = " ".join(
        f"--add-data '{Path(src).name}{sep}{dst}'"
        for src, dst in DATA_FILES
        if Path(src).exists()
    )

    # Install deps + run PyInstaller inside the Wine/Windows Python env
    pip_pkgs = (
        "pyinstaller Pillow numpy scipy "
        "onnxruntime onnx insightface "
        "opencv-python pyzbar qrcode faiss-cpu"
    )

    docker_script = (
        f"pip install {pip_pkgs} --quiet 2>&1 | tail -3 && "
        f"wine pyinstaller "
        f"  --noconfirm {mode_flag} --windowed "
        f"  --name={APP_NAME} "
        f"  --collect-submodules PIL "
        f"  --collect-submodules cv2 "
        f"  --hidden-import pyzbar.pyzbar "
        f"  --hidden-import qrcode.image.pil "
        f"  --icon icons/admin_icon.ico "
        f"  {data_args} "
        f"  {ENTRY_POINT}"
    )

    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{HERE}:/src",
            "-w", "/src",
            DOCKER_IMAGE,
            "bash", "-c", docker_script,
        ],
        cwd=HERE,
    )

    if result.returncode != 0:
        _warn("Docker build failed.")
        return False

    # Collect output
    _collect_dist(dest, "windows", onefile)
    _copy_runtime_files(dest)
    _write_readme(dest, "windows", onefile)

    # Clean PyInstaller work dirs
    for d in ["build", "dist"]:
        p = HERE / d
        if p.exists():
            shutil.rmtree(p)

    _ok(f"Windows release ready  →  {dest}")
    return True


def _write_windows_build_script(dest: Path, onefile: bool):
    """Generate a .bat that the user can run on a real Windows machine."""
    mode_flag = "--onefile" if onefile else "--onedir"
    tag       = "onefile" if onefile else "onedir"
    out_dir   = f"release\\windows-{tag}-{VERSION}"

    data_args = ""
    for src, dst in DATA_FILES:
        name = Path(src).name
        data_args += f'    --add-data "{name};{dst}" ^\n'

    # Build the xcopy / copy line without backslashes inside an f-string expression
    if onefile:
        copy_line = f"copy /Y dist\\{APP_NAME}.exe {out_dir}\\"
    else:
        copy_line = f"xcopy /E /I /Y dist\\{APP_NAME} {out_dir}\\{APP_NAME}"

    bat = f"""@echo off
:: ============================================================
::  {APP_NAME} — Windows Native Build Script  v{VERSION}
::  Copy your project folder to Windows, then double-click this.
:: ============================================================
setlocal

set APP={APP_NAME}
set OUT={out_dir}

echo.
echo  Building {APP_NAME} for Windows ...
echo.

:: Activate venv if present
if exist "%~dp0venv\\Scripts\\activate.bat" (
    call "%~dp0venv\\Scripts\\activate.bat"
)

:: Install dependencies from requirements.txt
if exist requirements.txt (
    echo [INFO] Installing dependencies from requirements.txt ...
    python -m pip install -r requirements.txt --quiet
)

:: Install PyInstaller
python -m pip install pyinstaller --quiet

:: Run PyInstaller
pyinstaller ^
    --noconfirm ^
    {mode_flag} ^
    --windowed ^
    --name=%APP% ^
    --icon=icons\\admin_icon.ico ^
    --collect-submodules PIL ^
    --collect-submodules cv2 ^
    --hidden-import pyzbar.pyzbar ^
    --hidden-import qrcode.image.pil ^
{data_args}    main.py

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    pause & exit /b 1
)

:: Move output to release folder
if not exist "%OUT%" mkdir "%OUT%"
{copy_line}

:: Copy runtime files
for %%F in (DB_FILE face_encodings.pkl haarcascade_frontalface_default.xml haarcascade_eye.xml) do (
    if exist "%%F" copy /Y "%%F" "%OUT%\\%%F"
)

echo.
echo  BUILD COMPLETE
echo  Output: %OUT%
echo.
pause
"""
    (dest / "build_on_windows.bat").write_text(bat)
    _ok(f"Wrote build_on_windows.bat  →  {dest}")

# ─────────────────────────────────────────────────────────────────────────────
#  Clean
# ─────────────────────────────────────────────────────────────────────────────

def clean():
    _banner("CLEAN  build artefacts + release/")
    for name in ["build", "dist", "_build_tmp", f"{APP_NAME}.spec", "release"]:
        p = HERE / name
        if p.exists():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            _ok(f"Removed {p.name}/")

# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python pipeline.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    p.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["linux", "windows", "all", "clean"],
        help="What to build (default: all)",
    )
    p.add_argument(
        "--onefile",
        action="store_true",
        help="Pack into a single self-contained executable",
    )
    p.add_argument(
        "--version",
        default=VERSION,
        metavar="X.Y.Z",
        help=f"Release version tag (default: {VERSION})",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    global VERSION
    VERSION = args.version

    width = _W
    now   = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    print("=" * width)
    print(f"  {APP_NAME}  —  Build Pipeline  v{VERSION}")
    print(f"  {now}")
    print(f"  Running on: {platform.system()} {platform.machine()}")
    print("=" * width)

    if args.target == "clean":
        clean()
        return

    _ensure_dependencies()

    built: list[str] = []

    if args.target in ("linux", "all"):
        dest = build_linux(args.onefile)
        if dest:
            built.append(str(dest))

    if args.target in ("windows", "all"):
        dest = build_windows(args.onefile)
        if dest:
            built.append(str(dest))

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * width)
    print("  PIPELINE COMPLETE")
    print()
    if built:
        for b in built:
            print(f"    [+]  {b}")
    else:
        print("    No artefacts produced for this OS.")
    print("=" * width + "\n")


if __name__ == "__main__":
    main()
