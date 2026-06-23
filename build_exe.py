#!/usr/bin/env python3
"""
Build script for packaging the Inventory Management System into a standalone executable.
Must be run on Windows to generate a Windows .exe file.
"""
import os
import sys
import subprocess
import shutil


def main():
    # Ensure working directory is the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir:
        os.chdir(script_dir)

    print("==================================================")
    print("  Inventory Management System — Executable Builder")
    print("==================================================")


    # 1. Verify OS (warn if not Windows)
    if os.name != 'nt':
        print("\n[WARNING] You are running this script on a non-Windows OS.")
        print("PyInstaller can only compile a Windows '.exe' when run on Windows.")
        print("Continuing will produce a binary for your current operating system.")
        print("Press Enter to continue, or Ctrl+C to cancel...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nBuild cancelled.")
            sys.exit(0)


    # 2. Check/Install PyInstaller
    try:
        import PyInstaller
        print(f"✓ PyInstaller found (v{PyInstaller.__version__})")
    except ImportError:
        print("PyInstaller not found. Installing it in the virtual environment...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("✓ PyInstaller installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install PyInstaller: {e}")
            sys.exit(1)


    # Clean up previous build/dist folders and spec files to avoid caching issues
    print("\nCleaning up previous build artifacts to ensure a fresh compile...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"✓ Removed old '{folder}' directory.")
            except Exception as e:
                print(f"[WARNING] Could not remove '{folder}' directory: {e}")
    
    spec_file = "InventoryManagement.spec"
    if os.path.exists(spec_file):
        try:
            os.remove(spec_file)
            print(f"✓ Removed old '{spec_file}'.")
        except Exception as e:
            print(f"[WARNING] Could not remove '{spec_file}': {e}")


    # 3. Mode selection
    print("\nSelect packaging mode:")
    print("  [1] Directory Mode (Recommended) — Instant startup, folder with files")
    print("  [2] Single File Mode — Takes 5-15 seconds to start up on every run")
    choice = input("Enter choice [1/2, default: 1]: ").strip()


    if choice == '2':
        mode_flag = "--onefile"
        mode_name = "Single File"
    else:
        mode_flag = "--onedir"
        mode_name = "Directory"


    print(f"\nBuilding in {mode_name} mode...")


    # 4. Configure PyInstaller arguments
    # Path separator for --add-data: ';' on Windows, ':' on Unix
    sep = ';' if os.name == 'nt' else ':'


    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",  # Clean PyInstaller cache before building
        "--noconfirm",
        mode_flag,
        "--windowed",  # Hide terminal console when app is running
        "--name=InventoryManagement",

        # --- Local module resolution ---
        "--paths", ".",
        "--collect-submodules", "ui",
        "--collect-submodules", "core",
        "--collect-submodules", "db",
        "--collect-submodules", "utils",

        # --- Bundle all third-party packages that PyInstaller misses ---
        "--collect-all", "PIL",
        "--collect-all", "cv2",
        "--collect-all", "numpy",
        "--collect-all", "qrcode",
        "--collect-all", "faiss",
        "--collect-all", "onnx",
        "--collect-all", "onnxruntime",
        "--collect-all", "insightface",


        # Hidden imports that PyInstaller's static analysis can miss
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "qrcode",
        "--hidden-import", "qrcode.image.pil",
        "--hidden-import", "faiss",
        "--hidden-import", "faiss_cpu",
        "--hidden-import", "onnx",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "insightface",
        "--hidden-import", "sqlite3",


        # Bundle data files
        "--add-data", f"icons{sep}icons",
        "--add-data", f"haarcascade_frontalface_default.xml{sep}.",
        "--add-data", f"haarcascade_eye.xml{sep}.",


        "main.py"
    ]


    # Include face_encodings.pkl if it exists
    if os.path.exists("face_encodings.pkl"):
        cmd.extend(["--add-data", f"face_encodings.pkl{sep}."])


    print(f"\nRunning command:\n  {' '.join(cmd)}\n")


    try:
        subprocess.run(cmd, check=True)
        print("\n==================================================")
        print("✓ BUILD SUCCESSFUL!")
        print("==================================================")


        # 5. Explain next steps
        dist_path = os.path.abspath(os.path.join("dist", "InventoryManagement"))
        if choice == '2':
            exe_file = os.path.abspath(os.path.join("dist", "InventoryManagement.exe"))
            print(f"Standalone executable is located at:\n  {exe_file}")
            print("\n[IMPORTANT] To run the application:")
            print("1. Copy your 'DB_FILE' into the same directory as the 'InventoryManagement.exe'.")
            print("2. Double-click 'InventoryManagement.exe' to launch.")
        else:
            print(f"Application directory is located at:\n  {dist_path}")
            print("\n[IMPORTANT] To run the application:")
            print(f"1. Copy your 'DB_FILE' into the folder: {dist_path}")
            print(f"2. Run the 'InventoryManagement.exe' executable inside that folder.")


    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] PyInstaller build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
