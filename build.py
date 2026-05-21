#!/usr/bin/env python3
"""
Build script for JAM (Japanese Anki Miner)
Creates a standalone Windows executable with system tray icon.

Usage:
    python build.py          # Build executable
    python build.py --clean  # Clean build artifacts
    python build.py --dev    # Build with console for debugging
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path

# Directories
ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
SPEC_FILE = ROOT_DIR / "jam.spec"

def clean():
    """Remove build artifacts."""
    print("🧹 Cleaning build artifacts...")
    for directory in [DIST_DIR, BUILD_DIR, ROOT_DIR / ".pytest_cache"]:
        if directory.exists():
            shutil.rmtree(directory)
            print(f"   Removed: {directory}")
    
    # Remove .spec cache files
    for spec_cache in ROOT_DIR.glob("*.spec"):
        if spec_cache.name in ["jam.spec"]:
            pass  # Keep our spec file
        else:
            try:
                spec_cache.unlink()
            except Exception:
                pass

def build(dev_mode=False, skip_deps=False):
    """Build the executable using PyInstaller."""
    print("🔨 Building JAM executable...")
    
    # Optionally install dependencies first
    if not skip_deps:
        print("\nEnsuring all dependencies are installed...")
        try:
            result = subprocess.run(
                [sys.executable, "install-deps.py"],
                cwd=ROOT_DIR,
                check=False
            )
            if result.returncode != 0:
                print("⚠️  Dependency installation had issues (non-fatal, continuing...)")
        except Exception as e:
            print(f"⚠️  Could not run install-deps.py: {e}")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"   PyInstaller {PyInstaller.__version__} detected ✓")
    except ImportError:
        print("   ❌ ERROR: PyInstaller not installed")
        print("   Install with: pip install pyinstaller")
        sys.exit(1)
    
    # Build command
    # Note: Don't use --onedir/--onefile with .spec file - those are spec file settings
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        str(SPEC_FILE),
    ]
    
    if dev_mode:
        cmd.insert(3, "--console")  # Show console for debugging
        print("   [DEV MODE] Console window will be shown for debugging")
    
    print(f"   Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True)
        print("✅ Build successful!")
        print(f"\n📦 Executable location:")
        exe_path = DIST_DIR / "JAM" / "JAM.exe"
        if exe_path.exists():
            print(f"   {exe_path}")
            print(f"\n🚀 To run: {exe_path}")
        else:
            print(f"   {DIST_DIR / 'JAM'}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with exit code {e.returncode}")
        return False

def create_shortcut():
    """Create a Windows shortcut (.lnk) for easy access."""
    try:
        import win32com.client
        
        exe_path = DIST_DIR / "JAM" / "JAM.exe"
        if not exe_path.exists():
            print("⚠️  Executable not found for shortcut creation")
            return
        
        desktop = Path.home() / "Desktop"
        shortcut_path = desktop / "JAM - Japanese Anki Miner.lnk"
        
        print(f"\n🔗 Creating desktop shortcut...")
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(exe_path)
        shortcut.WorkingDirectory = str(exe_path.parent)
        shortcut.IconLocation = str(exe_path)
        shortcut.save()
        
        print(f"   ✓ Shortcut created: {shortcut_path}")
    except Exception as e:
        print(f"⚠️  Shortcut creation failed (non-fatal): {e}")
        print("   You can manually create a shortcut to the executable")

def main():
    parser = argparse.ArgumentParser(description="Build JAM executable")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts first")
    parser.add_argument("--dev", action="store_true", help="Build with console for debugging")
    parser.add_argument("--no-shortcut", action="store_true", help="Skip desktop shortcut creation")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency installation check")
    args = parser.parse_args()
    
    if args.clean:
        clean()
    
    # Build
    if build(dev_mode=args.dev, skip_deps=args.skip_deps):
        if not args.no_shortcut:
            try:
                create_shortcut()
            except Exception as e:
                print(f"⚠️  Shortcut creation skipped: {e}")
        
        print("\n" + "=" * 60)
        print("Build complete! Your JAM executable is ready.")
        print("=" * 60)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
