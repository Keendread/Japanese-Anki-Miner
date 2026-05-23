# JAM Deployment Guide

This guide explains how to prepare JAM for distribution and handle dependencies.

## Understanding Dependencies

### For End-Users (Running `.exe`)

**Question:** Do users need to install `requirements.txt`?  
**Answer:** ❌ **NO!**

When you build with PyInstaller, **all dependencies are bundled into the executable**:
- Python runtime ✓
- All pip packages ✓
- DLLs and libraries ✓
- Data files ✓

Result: **Users run `.exe` → everything works immediately**

### For Developers (Building from Source)

**Question:** Do developers need `requirements.txt`?  
**Answer:** ✅ **YES!**

Before building, install all dependencies:
```bash
pip install -r requirements.txt
```

Or let the build script do it automatically:
```bash
python build.py          # Auto-installs dependencies
python build.py --skip-deps  # Skip if already installed
```

---

## Deployment Options

### Option 1: Standalone `.exe` (Simple)

**Best for:** Users who don't want installation

**Steps:**

1. Build the executable:
   ```bash
   python build.py
   ```

2. Distribute the folder:
   ```
   dist/JAM/
   ├── JAM.exe
   ├── ... (supporting DLLs, data files)
   ```

3. Users extract and run `JAM.exe`

**Pros:**
- ✅ Ultra-simple (just an `.exe`)
- ✅ No installation needed
- ✅ Can run from USB/portable drive

**Cons:**
- ❌ Larger download (~500-800 MB)
- ❌ Folder-based, not in "Programs"

---

### Option 2: Windows Installer (Professional)

**Best for:** Professional distribution, Add/Remove Programs

**Steps:**

1. **Install NSIS:**
   ```bash
   # Option A: Download from https://nsis.sourceforge.io
   # Option B: Use Chocolatey
   choco install nsis
   ```

2. **Build JAM executable:**
   ```bash
   python build.py
   ```

3. **Create installer:**
   ```bash
   makensis jam-installer.nsi
   ```
   
   Result: `dist/JAM-Installer.exe`

4. **Users run installer:**
   - Extracts to `Program Files/JAM`
   - Creates Start Menu shortcut
   - Creates Desktop shortcut
   - Can be uninstalled via "Add/Remove Programs"

**Pros:**
- ✅ Professional appearance
- ✅ Standard Windows installation
- ✅ Uninstall support
- ✅ Can compress installer further

**Cons:**
- ❌ Requires NSIS to build
- ❌ Slightly slower first launch

---

### Option 3: Portable + Installer (Both)

**Best for:** Maximum flexibility

**Steps:**

1. Build executable:
   ```bash
   python build.py
   ```

2. Create ZIP for portable:
   ```bash
   Compress-Archive -Path dist\JAM -DestinationPath JAM-portable.zip
   ```

3. Create installer:
   ```bash
   makensis jam-installer.nsi
   ```

**Result:** Two distribution options
- `JAM-portable.zip` — Extract and run
- `JAM-Installer.exe` — Standard Windows installation

---

## Pre-Build Dependency Management

### Checking Dependencies

**Check if all requirements are installed:**

```bash
python install-deps.py --check
```

Output:
```
✅ All requirements installed!
```

Or if missing:
```
❌ Missing 3 package(s):
   - somepackage
   - anotherpackage
   - thirdpackage
```

### Installing Dependencies

**Install all requirements:**

```bash
python install-deps.py
```

**Upgrade all packages to latest:**

```bash
python install-deps.py --update
```

### Automatic Installation During Build

**Build with automatic dependency check:**

```bash
python build.py          # Auto-installs dependencies if needed
```

**Build without checking dependencies:**

```bash
python build.py --skip-deps
```

---

## Build Process Overview

```
┌─────────────────────────────────────────────────┐
│ 1. Developer runs: python build.py              │
└────────────────────┬────────────────────────────┘
                     ↓
         ┌───────────────────────┐
         │ Check requirements    │
         │ (install-deps.py)     │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │ Run PyInstaller       │
         │ (jam.spec)            │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │ Create executable     │
         │ dist/JAM/JAM.exe      │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │ Create shortcuts      │
         │ (optional)            │
         └───────────┬───────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│ 2. Distribute JAM executable                    │
│    - As-is (portable)                           │
│    - With NSIS installer                        │
│    - As ZIP archive                             │
└─────────────────────────────────────────────────┘
```

---

## Customizing Installation

### Custom Start Menu Name

Edit `jam-installer.nsi`:

```nsi
CreateDirectory "$SMPROGRAMS\My Company\JAM"
CreateShortcut "$SMPROGRAMS\My Company\JAM\JAM.lnk" ...
```

### Custom Installation Directory

Edit `jam-installer.nsi`:

```nsi
InstallDir "$APPDATA\JAM"  # User's AppData
InstallDir "$PROGRAMFILES\JAM"  # Program Files (requires admin)
```

### Add Custom Files to Installer

Edit `jam-installer.nsi`:

```nsi
File "README.md"
File "LICENSE"
File /r "docs\*.*"
```

### Compress Installer Further

Install UPX (executable compressor):

```bash
# Download from: https://upx.github.io
# Then use with PyInstaller:
pyinstaller jam.spec --upx-dir=C:\upx
```

---

## Deployment Checklist

Before releasing:

- [ ] Test executable runs on clean Windows machine
- [ ] Verify hotkeys work
- [ ] Test image selection pipeline
- [ ] Test Anki card creation
- [ ] Check first-launch dictionary build completes
- [ ] Verify system tray icon appears
- [ ] Test "View Logs" menu option
- [ ] Test uninstaller (if using NSIS)
- [ ] Create GitHub release
- [ ] Write user installation guide (see INSTALL_GUIDE.md)

---

## Size Optimization

### Typical Build Sizes

| Component | Size |
|-----------|------|
| Python runtime | 50-100 MB |
| PyTorch (OCR model) | 200-300 MB |
| Other dependencies | 50-100 MB |
| JAM code | 1-2 MB |
| **Total** | **300-500 MB** |

### To Reduce Size

1. **Remove unused dependencies:** Edit `jam.spec` `excludedimports`
2. **Use UPX compression:** Reduces by ~30-40%
3. **Remove debug symbols:** Add `strip=True` in PyInstaller
4. **Lazy-load OCR model:** Load only when needed (advanced)

---

## Troubleshooting Installer

### "makensis not found"

**Problem:** NSIS not installed or not in PATH

**Solution:**
- Install NSIS: https://nsis.sourceforge.io
- Or use Chocolatey: `choco install nsis`
- Or add NSIS to PATH manually

### Installer creates unwanted shortcuts

**Problem:** Too many/wrong shortcuts created

**Solution:** Edit `jam-installer.nsi`, comment out unwanted sections:

```nsi
; CreateShortcut "$DESKTOP\JAM.lnk" ...  ; Uncomment to enable
```

### Can't uninstall on some systems

**Problem:** Permission issues

**Solution:** Update `jam-installer.nsi`:

```nsi
RequestExecutionLevel admin  ; Require admin privileges
```

---

## GitHub Release

Recommended release structure:

```
Release: JAM v1.0

Assets:
├── JAM-v1.0-portable.zip      (dist/JAM folder zipped)
├── JAM-v1.0-installer.exe     (jam-installer.nsi built)
└── INSTALL_GUIDE.md            (user instructions)

Release Notes:
- Fixed image picker threading issues
- Added system tray support
- Bundled Japanese dictionary
```

---

## Next Steps

1. **Install NSIS** (if using installer option):
   ```bash
   choco install nsis
   ```

2. **Test build:**
   ```bash
   python build.py
   ```

3. **Test executable** on another machine

4. **Create installer:**
   ```bash
   makensis jam-installer.nsi
   ```

5. **Distribute via GitHub Releases**

---

**Questions?** Check individual guide files:
- **BUILD_GUIDE.md** — How to build from source
- **INSTALL_GUIDE.md** — How to install/run built executable
- **This file** — How to distribute built executable
