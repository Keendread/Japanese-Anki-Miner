#!/usr/bin/env python3
"""
Build script for JAM (Japanese Anki Miner)
Creates a standalone Windows executable with system tray icon.

Usage:
    python build.py             # Build executable
    python build.py --clean     # Clean build artifacts then build
    python build.py --dev       # Build with console window for debugging
    python build.py --skip-deps # Skip pip dependency check
    python build.py --no-shortcut # Skip desktop shortcut creation
"""

import os
import re
import sys
import subprocess
import shutil
import argparse
from pathlib import Path

# ── Directories ───────────────────────────────────────────────────────────────
ROOT_DIR  = Path(__file__).parent
DIST_DIR  = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
SPEC_FILE = ROOT_DIR / "jam.spec"
APP_DIR   = DIST_DIR / "JAM"          # PyInstaller COLLECT output folder
EXE_PATH  = APP_DIR / "JAM.exe"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, inheriting stdout/stderr so output is visible."""
    return subprocess.run(cmd, **kwargs)


# ── Steps ─────────────────────────────────────────────────────────────────────

def clean():
    """Remove build artefacts."""
    print("🧹 Cleaning build artefacts...")
    for directory in [DIST_DIR, BUILD_DIR, ROOT_DIR / ".pytest_cache"]:
        if directory.exists():
            shutil.rmtree(directory)
            print(f"   Removed: {directory}")


def install_deps():
    """Ensure all runtime dependencies are present."""
    print("\n2. Ensuring dependencies are installed...")
    dep_script = ROOT_DIR / "install-deps.py"
    if dep_script.exists():
        result = _run([sys.executable, str(dep_script)], cwd=ROOT_DIR)
        if result.returncode != 0:
            print("⚠️  Dependency installer reported issues (continuing).")
    else:
        print("   install-deps.py not found — skipping.")


def validate_imports():
    """Quick sanity-check that key modules are importable."""
    print("\n1. Validating module imports...")
    vi = ROOT_DIR / "validate_imports.py"
    if vi.exists():
        result = _run([sys.executable, str(vi)], cwd=ROOT_DIR)
        if result.returncode != 0:
            print("⚠️  Import validation had issues (continuing).")
    else:
        print("   validate_imports.py not found — skipping.")


def patch_spec_console(enable: bool):
    """
    Toggle the console= flag inside jam.spec in-place.
    --console cannot be passed on the CLI when building from a .spec file,
    so we patch the file directly for dev builds and restore it afterwards.
    Returns the original line so the caller can restore it.
    """
    text = SPEC_FILE.read_text(encoding="utf-8")
    pattern = r"(console\s*=\s*)(True|False)"
    new_value = "True" if enable else "False"
    new_text, count = re.subn(pattern, rf"\g<1>{new_value}", text)
    if count == 0:
        print("⚠️  Could not locate 'console=' in jam.spec — dev mode not applied.")
        return text          # return original so restore is a no-op
    SPEC_FILE.write_text(new_text, encoding="utf-8")
    return text              # original content for restore


def build(dev_mode: bool = False, skip_deps: bool = False) -> bool:
    """Build the executable using PyInstaller."""
    print("🔨 Building JAM executable...\n")

    validate_imports()

    if not skip_deps:
        install_deps()
    else:
        print("\n2. Skipping dependency installation (--skip-deps).")

    # Check PyInstaller ───────────────────────────────────────────────────────
    print("\n3. Checking PyInstaller...")
    try:
        import PyInstaller
        print(f"   PyInstaller {PyInstaller.__version__} detected ✓")
    except ImportError:
        print("   ❌ ERROR: PyInstaller not installed.")
        print("   Install with: pip install pyinstaller")
        return False

    # Patch spec for dev mode (console window) ────────────────────────────────
    original_spec: str | None = None
    if dev_mode:
        print("\n   [DEV MODE] Enabling console window in jam.spec ...")
        original_spec = patch_spec_console(enable=True)

    # Run PyInstaller ─────────────────────────────────────────────────────────
    print("\n4. Running PyInstaller...")
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC_FILE)]
    print(f"   Command: {' '.join(cmd)}\n")

    try:
        result = _run(cmd, check=True)
        success = True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed (exit code {e.returncode})")
        success = False
    finally:
        # Always restore spec to non-console for normal builds
        if original_spec is not None:
            SPEC_FILE.write_text(original_spec, encoding="utf-8")
            print("\n   [DEV MODE] Restored jam.spec console=False.")

    if success:
        print("\n✅ Build successful!")
        if EXE_PATH.exists():
            print(f"\n📦 Executable: {EXE_PATH}")
        else:
            print(f"\n📦 Output folder: {APP_DIR}")

    return success


def verify_build() -> bool:
    """
    Check that the built output contains what we expect and excludes what
    should never be baked in (prebuilt DBs, source data, caches).
    """
    print("\n🔍 Verifying build contents...")

    required_files = {
        "JAM.exe": "Main executable",
        # build_db.py is a data file bundled via datas=; PyInstaller places
        # data files under _internal/ (sys._MEIPASS) in onedir builds, NOT
        # directly next to the exe.
        "_internal/data/build_db.py": "Dictionary builder (embedded in _internal)",
        # _tkinter.pyd must be present — UPX silently corrupts it on Windows.
        # If this is missing, all tkinter toasts will fail at runtime.
        "_internal/_tkinter.pyd":     "Tkinter C extension (required for toasts)",
    }

    # PyInstaller onedir: _internal/ holds the Python runtime + packages.
    # The exact sub-structure of _internal varies, so we only assert the
    # folder itself exists (not specific sub-paths like _internal/sudachipy).
    required_dirs = {
        "_internal":      "PyInstaller runtime + bundled packages",
        "_internal/data": "Bundled data folder (build_db.py lives here)",
        # Tcl/Tk data directories — collected by PyInstaller's tkinter hook.
        # Missing = UPX or hook failure; toasts will crash at runtime.
        "_internal/tcl":  "Tcl runtime data (required by tkinter)",
        "_internal/tk":   "Tk runtime data (required by tkinter)",
    }

    unwanted = {
        # These must never be baked into the _internal bundle.
        # (A data/ folder next to the exe is fine — the app creates it at runtime.)
        "_internal/data/jmdict.db": "Prebuilt dictionary — must be created at runtime",
        "_internal/data/mined.db":  "Mined-cards DB — must be created at runtime",
        "_internal/data/raw":       "Raw source data — not part of distribution",
        "_internal/data/audio":     "Audio cache — generated at runtime",
    }

    ok = True

    print("\n  Required files:")
    for rel, desc in required_files.items():
        p = APP_DIR / rel
        if p.exists():
            print(f"    ✓  {rel}  ({desc})")
        else:
            print(f"    ✗  MISSING: {rel}  ({desc})")
            ok = False

    print("\n  Required directories:")
    for rel, desc in required_dirs.items():
        p = APP_DIR / rel
        if p.is_dir():
            n = sum(1 for _ in p.rglob("*"))
            print(f"    ✓  {rel}/  ({desc})  [{n} files]")
        else:
            print(f"    ✗  MISSING: {rel}/  ({desc})")
            ok = False

    print("\n  Files that must NOT be bundled:")
    for rel, reason in unwanted.items():
        p = APP_DIR / rel
        if p.exists():
            print(f"    ⚠  FOUND (remove it): {rel}  — {reason}")
            # Warn but don't fail; developer may have stale local files.
        else:
            print(f"    ✓  Not present: {rel}")

    if ok:
        print("\n✅ Verification PASSED")
    else:
        print("\n⚠️  Verification found issues — see above")

    return ok


def create_shortcut():
    """Create a Windows .lnk shortcut on the Desktop."""
    try:
        import win32com.client
    except ImportError:
        print("\n⚠️  pywin32 not installed — skipping shortcut creation.")
        print("   Install with: pip install pywin32")
        return

    if not EXE_PATH.exists():
        print("\n⚠️  Executable not found — skipping shortcut creation.")
        return

    desktop = Path.home() / "Desktop"
    shortcut_path = desktop / "JAM - Japanese Anki Miner.lnk"

    print("\n🔗 Creating desktop shortcut...")
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(str(shortcut_path))
        sc.TargetPath       = str(EXE_PATH)
        sc.WorkingDirectory = str(EXE_PATH.parent)
        sc.IconLocation     = str(EXE_PATH)
        sc.save()
        print(f"   ✓ Shortcut: {shortcut_path}")
    except Exception as e:
        print(f"   ⚠️  Shortcut creation failed: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build JAM executable")
    parser.add_argument("--clean",       action="store_true",
                        help="Remove build artefacts before building")
    parser.add_argument("--dev",         action="store_true",
                        help="Build with a visible console window (debugging)")
    parser.add_argument("--no-shortcut", action="store_true",
                        help="Skip desktop shortcut creation")
    parser.add_argument("--skip-deps",   action="store_true",
                        help="Skip pip dependency installation check")
    args = parser.parse_args()

    if args.clean:
        clean()

    if build(dev_mode=args.dev, skip_deps=args.skip_deps):
        verify_build()

        if not args.no_shortcut:
            create_shortcut()

        print("\n" + "=" * 60)
        print("Build complete!  Your JAM executable is ready.")
        if EXE_PATH.exists():
            print(f"Location: {EXE_PATH}")
        print("=" * 60)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()