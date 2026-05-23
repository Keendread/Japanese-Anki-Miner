#!/usr/bin/env python3
"""
Pre-build dependency installer for JAM

Ensures all requirements are installed before building the executable.
Run this once before building, or let build.py run it automatically.

Usage:
    python install-deps.py              # Install all requirements
    python install-deps.py --check      # Check (don't install)
    python install-deps.py --update     # Upgrade all packages
"""

import sys
import subprocess
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).parent
REQUIREMENTS = ROOT_DIR / "requirements.txt"

def check_requirements(verbose=True):
    """Check if all requirements are installed."""
    try:
        import pkg_resources
        
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = []
        
        with open(REQUIREMENTS) as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Extract package name (before ==, >=, etc.)
                pkg_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].strip()
                pkg_key = pkg_name.replace('-', '_').lower()
                
                if pkg_key not in installed and pkg_name.lower() not in installed:
                    missing.append(pkg_name)
        
        if missing:
            if verbose:
                print(f"❌ Missing {len(missing)} package(s):")
                for pkg in missing:
                    print(f"   - {pkg}")
            return False, missing
        else:
            if verbose:
                print("✅ All requirements installed!")
            return True, []
    
    except Exception as e:
        print(f"⚠️  Error checking requirements: {e}")
        return None, None

def install_requirements(upgrade=False):
    """Install requirements using pip."""
    print(f"📦 Installing dependencies from {REQUIREMENTS}...")
    
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    
    if upgrade:
        cmd.append("--upgrade")
        print("   (upgrading to latest versions)")
    
    try:
        result = subprocess.run(cmd, check=True)
        print("✅ Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed with exit code {e.returncode}")
        print("   Try running: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Manage JAM dependencies")
    parser.add_argument("--check", action="store_true", help="Check without installing")
    parser.add_argument("--update", action="store_true", help="Upgrade all packages")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()
    
    if not REQUIREMENTS.exists():
        print(f"❌ ERROR: {REQUIREMENTS} not found!")
        sys.exit(1)
    
    if args.check:
        # Check only
        ok, missing = check_requirements(verbose=not args.quiet)
        sys.exit(0 if ok else 1)
    else:
        # Check first
        ok, missing = check_requirements(verbose=not args.quiet)
        
        if ok and not args.update:
            return True
        
        # Install if needed or requested
        success = install_requirements(upgrade=args.update)
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
