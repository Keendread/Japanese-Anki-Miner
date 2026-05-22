#!/usr/bin/env python3
"""
Verify and debug the built JAM executable.
Run this after building to check if all required files are present.

Usage:
    python verify_build.py              # Check dist/JAM/ folder
    python verify_build.py --details    # Show detailed file listing
"""

import os
import sys
from pathlib import Path
import argparse

ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist" / "JAM"

# Define what SHOULD be in the build
REQUIREMENTS = {
    "EXECUTABLES": {
        "JAM.exe": "Main application executable",
    },
    "DIRECTORIES": {
        "_internal": "PyInstaller bundled dependencies",
        "data": "Application data folder",
    },
    "DATA_FILES": {
        "data/build_db.py": "Dictionary database builder (MUST HAVE)",
    },
    "NESTED_DIRECTORIES": {
        "_internal/sudachipy": "Sudachi NLP support",
        "_internal/manga_ocr": "Manga OCR model data",
    },
}

# Files that should NOT be present
UNWANTED = {
    "data/jmdict.db": "Prebuilt dictionary - should be generated on first run",
    "data/mined.db": "Mined cards database - should be created at runtime",
    "data/audio": "Cached audio files - VOICEVOX generates on-demand",
    "data/raw": "Raw source files - not needed in distribution",
    "data/__pycache__": "Python cache files - not needed",
}

def check_file(path, description, critical=False):
    """Check if a file exists."""
    if path.exists():
        size = path.stat().st_size
        size_str = f"{size:,} bytes" if size < 1024*1024 else f"{size/(1024*1024):.2f} MB"
        symbol = "✓" if not critical else "✓"
        print(f"  {symbol} {path.name:30} {size_str:20} ({description})")
        return True
    else:
        symbol = "✗" if critical else "⚠"
        print(f"  {symbol} {path.name:30} {'MISSING':20} ({description})")
        return False

def check_directory(path, description, critical=False):
    """Check if a directory exists and count files."""
    if path.exists() and path.is_dir():
        file_count = len(list(path.rglob('*')))
        symbol = "✓"
        print(f"  {symbol} {path.name:30} {file_count:5} files  ({description})")
        return True
    else:
        symbol = "✗" if critical else "⚠"
        print(f"  {symbol} {path.name:30} {'MISSING':20} ({description})")
        return False

def verify_build():
    """Main verification logic."""
    print("=" * 80)
    print("JAM Build Verification")
    print("=" * 80)
    print(f"\nBuild location: {DIST_DIR}")
    
    if not DIST_DIR.exists():
        print(f"\n❌ ERROR: Build directory not found: {DIST_DIR}")
        print("   Run: python build.py")
        return False
    
    all_ok = True
    
    # Check executables
    print("\n📦 CHECKING EXECUTABLES:")
    for exe_name, desc in REQUIREMENTS["EXECUTABLES"].items():
        exe_path = DIST_DIR / exe_name
        if not check_file(exe_path, desc, critical=True):
            all_ok = False
    
    # Check main directories
    print("\n📁 CHECKING MAIN DIRECTORIES:")
    for dir_name, desc in REQUIREMENTS["DIRECTORIES"].items():
        dir_path = DIST_DIR / dir_name
        if not check_directory(dir_path, desc, critical=True):
            all_ok = False
    
    # Check data files
    print("\n📄 CHECKING DATA FILES:")
    for file_path_str, desc in REQUIREMENTS["DATA_FILES"].items():
        file_path = DIST_DIR / file_path_str
        if file_path.is_dir():
            if not check_directory(file_path, desc, critical=False):
                all_ok = False
        else:
            if not check_file(file_path, desc, critical=True):
                all_ok = False
    
    # Check nested critical directories
    print("\n🔍 CHECKING NESTED DEPENDENCIES:")
    for dir_path_str, desc in REQUIREMENTS["NESTED_DIRECTORIES"].items():
        dir_path = DIST_DIR / dir_path_str
        if not check_directory(dir_path, desc, critical=False):
            all_ok = False
    
    # Check for unwanted files
    print("\n⚠️  CHECKING FOR UNWANTED FILES:")
    unwanted_found = False
    for unwanted_path_str, reason in UNWANTED.items():
        unwanted_path = DIST_DIR / unwanted_path_str
        if unwanted_path.exists():
            print(f"  ⚠ FOUND (should be removed): {unwanted_path_str}")
            print(f"      Reason: {reason}")
            unwanted_found = True
        else:
            print(f"  ✓ Not present: {unwanted_path_str}")
    
    # Summary
    print("\n" + "=" * 80)
    if all_ok and not unwanted_found:
        print("✅ BUILD VERIFICATION PASSED")
        print("\n   All required files are present and correctly structured.")
        print("   The executable is ready to run.")
    else:
        print("⚠️  BUILD VERIFICATION ISSUES DETECTED")
        if not all_ok:
            print("   - Some critical files are missing")
        if unwanted_found:
            print("   - Some unwanted files are present (should be removed for smaller bundle)")
    print("=" * 80)
    
    return all_ok and not unwanted_found

def show_detailed_listing():
    """Show detailed file listing of the build."""
    print("\n" + "=" * 80)
    print("DETAILED BUILD CONTENTS")
    print("=" * 80)
    
    def print_tree(path, prefix="", max_depth=3, current_depth=0, max_files=15):
        if current_depth >= max_depth:
            return
        
        if not path.exists():
            return
        
        try:
            items = sorted(path.iterdir())
        except PermissionError:
            print(f"{prefix}[Permission Denied]")
            return
        
        # Group directories and files
        dirs = [item for item in items if item.is_dir()]
        files = [item for item in items if item.is_file()]
        
        # Show directories first
        for i, dir_item in enumerate(dirs):
            is_last = (i == len(dirs) - 1) and len(files) == 0
            print(f"{prefix}{'└── ' if is_last else '├── '}{dir_item.name}/")
            next_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(dir_item, next_prefix, max_depth, current_depth + 1, max_files)
        
        # Show files (limit display)
        for i, file_item in enumerate(files[:max_files]):
            is_last = (i == len(files) - 1)
            size = file_item.stat().st_size
            size_str = f"{size:,}" if size < 1024 else f"{size//1024}K"
            print(f"{prefix}{'└── ' if is_last else '├── '}{file_item.name:40} ({size_str})")
        
        if len(files) > max_files:
            print(f"{prefix}... and {len(files) - max_files} more files")
    
    if DIST_DIR.exists():
        print(f"\n{DIST_DIR.name}/")
        print_tree(DIST_DIR)
    else:
        print(f"Build directory not found: {DIST_DIR}")
    
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Verify JAM build")
    parser.add_argument("--details", action="store_true", help="Show detailed file listing")
    parser.add_argument("--fix-unwanted", action="store_true", help="Remove unwanted files")
    args = parser.parse_args()
    
    if args.details:
        show_detailed_listing()
    
    success = verify_build()
    
    if args.fix_unwanted and (DIST_DIR / "data" / "jmdict.db").exists():
        print("\n🧹 Removing unwanted files...")
        for unwanted_path_str in UNWANTED.keys():
            unwanted_path = DIST_DIR / unwanted_path_str
            if unwanted_path.exists():
                if unwanted_path.is_file():
                    unwanted_path.unlink()
                    print(f"   Removed: {unwanted_path_str}")
                elif unwanted_path.is_dir():
                    import shutil
                    shutil.rmtree(unwanted_path)
                    print(f"   Removed: {unwanted_path_str}/")
        print("\n✓ Cleanup complete")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
