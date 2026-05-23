# Building JAM into an Executable

This guide explains how to turn the Python application into a standalone Windows executable that runs in the system tray.

## Architecture Overview

**JAM** uses three key technologies:

1. **pystray** — Creates and manages the system tray icon
2. **PyInstaller** — Bundles Python code into a standalone `.exe`
3. **Pillow** — Renders the tray icon image

### How it Works

```
User Right-Clicks Tray Icon
         ↓
    pystray Menu (rendered by Pillow)
    ├─ Settings
    ├─ View Logs
    └─ Exit
         ↓
    Main thread queue processes callbacks
         ↓
   Application continues/exits
```

## Prerequisites

Before building, ensure:

1. **Python 3.8+** installed
2. **All dependencies installed:**
   ```bash
   pip install -r requirements.txt
   ```

3. **PyInstaller installed:**
   ```bash
   pip install pyinstaller
   ```

4. (Optional) **pywin32 post-install:**
   ```bash
   python Scripts/pywin32_postinstall.py -install
   ```
   (Required for Windows-specific features)

## Building the Executable

### Quick Build (Recommended)

From the project root:

```bash
python build.py
```

This will:
- ✅ Check and install all dependencies from `requirements.txt` (if needed)
- ✅ Clean previous build artifacts
- ✅ Build the executable using PyInstaller
- ✅ Create a desktop shortcut (optional)
- ✅ Place the `.exe` in `dist/JAM/JAM.exe`

### Build Options

```bash
# Clean only (remove dist/, build/ folders)
python build.py --clean

# Build with console window (for debugging)
python build.py --dev

# Build without checking dependencies (if already installed)
python build.py --skip-deps

# Build without creating desktop shortcut
python build.py --no-shortcut

# Clean + build + debug console
python build.py --clean --dev
```

### Managing Dependencies Manually

If you prefer to manage dependencies separately:

```bash
# Check if all requirements are installed
python install-deps.py --check

# Install all requirements
python install-deps.py

# Upgrade all packages to latest versions
python install-deps.py --update
```

### Manual Build (Advanced)

If you prefer direct PyInstaller control:

```bash
pyinstaller jam.spec
```

### Two-Step Manual Build

If you want explicit control:

```bash
# Step 1: Ensure all dependencies are installed
python install-deps.py

# Step 2: Build with PyInstaller
pyinstaller jam.spec
```

## Understanding the Built Executable

### Does the `.exe` Need `requirements.txt`?

**Question:** Do users need to install dependencies when they get the `.exe`?  
**Answer:** ❌ **No!**

When PyInstaller builds the executable, it **bundles everything inside**:
- ✅ Python runtime
- ✅ All pip packages (pystray, Pillow, etc.)
- ✅ Supporting DLLs and libraries
- ✅ Data files (dictionaries, models)

**Result:** Users just run `JAM.exe` → everything works immediately

### What About Developers?

**Question:** Do developers need to install dependencies before building?  
**Answer:** ✅ **Yes!**

The build script automatically handles this, but you can also do it manually:

```bash
pip install -r requirements.txt
```

The **`install-deps.py` script** helps with dependency management:
- Validates which packages are installed
- Installs missing dependencies
- Upgrades all packages (optional)

For details, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

### `jam.spec` (PyInstaller Specification)

Defines how PyInstaller bundles your app:

```python
Analysis(
    ['src/main.py'],           # Entry point
    datas=datas,               # Data files (dictionaries, models)
    hiddenimports=hiddenimports,  # Packages to bundle
)

EXE(
    console=False,             # No console window (system tray)
    icon=None,                 # TODO: Add path to .ico file
)
```

### `build.py` (Build Automation)

Wrapper script that:
- Validates dependencies
- Runs PyInstaller with correct arguments
- Creates desktop shortcuts
- Reports build status

## Testing the Executable

After building:

1. **Locate the executable:**
   ```
   dist/JAM/JAM.exe
   ```

2. **Run it:**
   - Double-click from File Explorer, OR
   - Use the desktop shortcut (if created), OR
   - Run from terminal:
     ```bash
     dist\JAM\JAM.exe
     ```

3. **Verify system tray icon appears:**
   - Look for the "JAM" icon in Windows system tray (bottom right)
   - Right-click for menu options

## Troubleshooting

### Build Fails: "Module not found"

**Problem:** PyInstaller can't find a dependency

**Solution:** Add to `jam.spec` `hiddenimports` list:
```python
hiddenimports = [
    'your_module_name',
    ...
]
```

### No Console Window (but need debugging)

**Problem:** Can't see error messages

**Solution:** Build with console:
```bash
python build.py --dev
```

### Executable runs but no tray icon appears

**Problem:** pystray might not be starting properly

**Solution:** 
1. Check `console=False` in spec file
2. Verify pystray is installed: `pip list | grep pystray`
3. Run with console to see errors: `python build.py --dev`

### Executable is huge (500+ MB)

**Problem:** Including unnecessary libraries

**Solution:** Review `jam.spec` `excludedimports` and remove packages like:
- Dev tools (pytest, sphinx, etc.)
- Unused model files
- Debug packages

### "Tcl_AsyncDelete" or threading errors

**Problem:** tkinter + threading issues

**Solution:** Ensure all changes from previous sessions are applied:
- Check `src/core/image.py` for proper thread cleanup
- Verify `_close()` method waits for background threads

## Advanced Customization

### Custom Icon

To use a custom tray icon:

1. **Create/prepare `.ico` file** (use online converters for `.png` → `.ico`)

2. **Update `jam.spec`:**
   ```python
   exe = EXE(
       ...
       icon='path/to/icon.ico',
   )
   ```

3. **Update `src/ui/tray.py`:**
   ```python
   def _create_icon(self) -> Image.Image:
       # Load from file instead of generating
       return Image.open('path/to/icon.png')
   ```

### One-File vs One-Dir

Current setup: **`--onedir`** (executable in folder)

To use single-file executable (slower startup, simpler distribution):

1. Change in `jam.spec`:
   ```python
   --onefile
   ```

2. Rebuild:
   ```bash
   python build.py --clean
   ```

### Digital Signing (Optional)

For trusted distribution, digitally sign the executable:

```bash
signtool sign /f certificate.pfx /p password dist\JAM\JAM.exe
```

## Distribution

To share the executable:

### Option 1: Folder Distribution
```bash
# Compress the entire dist/JAM folder
Compress-Archive -Path dist\JAM -DestinationPath JAM-v1.0.zip

# Users extract and run JAM.exe
```

### Option 2: Installer
Use NSIS or similar to create an `.msi` installer:
```bash
# Example: Create MSI with WiX or Inno Setup
```

### Option 3: Auto-Update
- Host on GitHub Releases
- Use `py2exe` or similar for auto-update capability

## Key Dependencies Explained

| Package | Purpose | Notes |
|---------|---------|-------|
| **pystray** | System tray icon | Doesn't work in WSL, must be Windows |
| **PyInstaller** | Bundle → .exe | Only needed for building |
| **Pillow** | Icon rendering | Dependency of pystray |
| **pynput** | Hotkey listener | Runs globally (outside window) |
| **manga-ocr** | OCR large model | ~500MB, included in executable |
| **sudachipy** | Japanese parsing | Included with dictionary |

## What Happens When Built

```
Source Files:
  src/main.py
  src/core/*.py
  src/ui/tray.py
  src/models/*.py
         ↓
PyInstaller Analysis:
  • Traces all imports
  • Collects data files (dictionaries, models)
  • Bundles dependencies
         ↓
.exe Creation:
  • Embeds Python runtime
  • Includes all dependencies
  • Single executable file
         ↓
Result:
  dist/JAM/JAM.exe  (with supporting DLLs)
```

## First Launch

On first launch, the app will:

1. Check dependencies (dictionary, AnkiConnect, etc.)
2. Build dictionary database (if missing) — **may take 5-10 minutes**
3. Load OCR model in background
4. Start listening for hotkeys
5. Appear in system tray

User will see nothing in first launch (app runs minimized to tray).

## Next Steps

- [ ] Update `jam.spec` with custom `.ico` icon path
- [ ] Test built executable thoroughly
- [ ] Create GitHub Release with `.exe`
- [ ] Write user installation guide
- [ ] Set up auto-update mechanism (optional)

---

**Questions?** Check `build.py --help` or see inline comments in `jam.spec`.
