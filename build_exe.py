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
        "pyinstaller",
        "--noconfirm",
        mode_flag,
        "--windowed",  # Hide terminal console when app is running
        "--name=InventoryManagement",
        "--collect-submodules", "PIL",
        "--add-data", f"icons{sep}icons",
        "main.py"
    ]

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
