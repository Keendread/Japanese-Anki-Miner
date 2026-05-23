#!/usr/bin/env python3
"""
Pre-build validation script.
Tests that all required modules can be imported before building.

Usage:
    python validate_imports.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"

# Add src to path
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

# Modules to verify
CORE_MODULES = [
    "core.anki",
    "core.audio",
    "core.bbox",
    "core.capture",
    "core.dictionary",
    "core.image",
    "core.notifier",
    "core.ocr",
    "core.parser",
    "core.settings",
]

MODEL_MODULES = [
    "models.audio",
    "models.card",
    "models.word",
]

UI_MODULES = [
    "ui.settings_window",
    "ui.tray",
]

EXTERNAL_MODULES = [
    "sudachipy",
    "sudachidict_full",
    "manga_ocr",
    "PIL",
    "pystray",
    "pynput",
    "aiohttp",
    "lxml",
]

def test_import(module_name):
    """Test if a module can be imported."""
    try:
        __import__(module_name)
        return True, None
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 80)
    print("JAM Pre-Build Validation")
    print("=" * 80)
    
    all_ok = True
    
    # Test core modules
    print("\n📦 Testing Core Modules:")
    for module in CORE_MODULES:
        ok, error = test_import(module)
        symbol = "✓" if ok else "✗"
        status = "OK" if ok else f"FAILED: {error}"
        print(f"  {symbol} {module:40} {status}")
        if not ok:
            all_ok = False
    
    # Test model modules
    print("\n🏗️  Testing Model Modules:")
    for module in MODEL_MODULES:
        ok, error = test_import(module)
        symbol = "✓" if ok else "✗"
        status = "OK" if ok else f"FAILED: {error}"
        print(f"  {symbol} {module:40} {status}")
        if not ok:
            all_ok = False
    
    # Test UI modules
    print("\n🖥️  Testing UI Modules:")
    for module in UI_MODULES:
        ok, error = test_import(module)
        symbol = "✓" if ok else "✗"
        status = "OK" if ok else f"FAILED: {error}"
        print(f"  {symbol} {module:40} {status}")
        if not ok:
            all_ok = False
    
    # Test external modules (non-critical)
    print("\n🌐 Testing External Modules:")
    for module in EXTERNAL_MODULES:
        ok, error = test_import(module)
        symbol = "✓" if ok else "⚠"
        status = "OK" if ok else f"NOT INSTALLED: {error}"
        print(f"  {symbol} {module:40} {status}")
    
    # Test main.py
    print("\n🚀 Testing Main Entry Point:")
    main_file = SRC_DIR / "main.py"
    if main_file.exists():
        print(f"  ✓ main.py found at {main_file}")
    else:
        print(f"  ✗ main.py NOT FOUND at {main_file}")
        all_ok = False
    
    # Summary
    print("\n" + "=" * 80)
    if all_ok:
        print("✅ All critical modules are importable - ready to build!")
    else:
        print("❌ Some modules failed to import - fix errors before building")
    print("=" * 80)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
