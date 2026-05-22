# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for JAM (Japanese Anki Miner)
# Build with: pyinstaller jam.spec
#
# Features to include:
# - All src/ modules (core, models, ui, main.py)
# - build_db.py for dictionary database creation
# - External package data files (sudachipy, manga_ocr)

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Project directories
ROOT_DIR = os.path.dirname(os.path.abspath(SPEC))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
DATA_DIR = os.path.join(ROOT_DIR, 'data')

print("[PyInstaller] Building JAM from spec...")
print(f"[PyInstaller] ROOT_DIR: {ROOT_DIR}")
print(f"[PyInstaller] SRC_DIR: {SRC_DIR}")
print(f"[PyInstaller] DATA_DIR: {DATA_DIR}")

# ============================================================================
# DATA FILES
# ============================================================================
datas = []

# 1. Collect external package data files (required for functionality)
print("[PyInstaller] Collecting external package data files...")
sudachi_data = collect_data_files('sudachipy')
manga_ocr_data = collect_data_files('manga_ocr')
datas += sudachi_data
datas += manga_ocr_data
print(f"[PyInstaller] - sudachipy data files: {len(sudachi_data)} entries")
print(f"[PyInstaller] - manga_ocr data files: {len(manga_ocr_data)} entries")

# 2. Include only build_db.py from data/ folder (NOT prebuilt databases or cached audio)
# We explicitly exclude: jmdict.db, mined.db, audio/, raw/, __pycache__
print("[PyInstaller] Adding data folder files...")
build_db_py = os.path.join(DATA_DIR, 'build_db.py')
data_init_py = os.path.join(DATA_DIR, '__init__.py')

if os.path.isfile(build_db_py):
    # Add the data directory itself to ensure folder structure is created
    # PyInstaller will copy all files from DATA_DIR to the 'data' folder in the bundle
    datas.append((DATA_DIR, 'data'))
    print(f"[PyInstaller] - Added: data/ folder with build_db.py and __init__.py")
else:
    print(f"[PyInstaller] WARNING: build_db.py not found at {build_db_py}")
    print(f"[PyInstaller] WARNING: data folder will not be included in bundle")

# Note: PyInstaller will include everything in DATA_DIR, but files are only in source repo if they:
# - Are part of the version control (.git tracked)
# - Actually exist in data/ directory
# The following DO NOT exist in the source (intentionally):
# - jmdict.db (built on first run)
# - mined.db (created at runtime)
# - audio/ (not part of distribution - VOICEVOX generates on-demand)
# - raw/ (raw source files, not needed in distribution)

# ============================================================================
# HIDDEN IMPORTS
# ============================================================================
# Packages not automatically detected by PyInstaller's module scanner
print("[PyInstaller] Setting up hidden imports...")

hiddenimports = [
    # External packages that need to be explicitly included
    'sudachipy',
    'sudachidict_full',
    'manga_ocr',
    'PIL',
    'pystray',
    'pynput',
    'aiohttp',
    'lxml',
    'cv2',                # opencv-python for text region detection
    
    # JAM internal modules (to ensure they're all included)
    'core.anki',
    'core.audio',
    'core.bbox',
    'core.capture',
    'core.detector',      # Multi-word region detection
    'core.dictionary',
    'core.image',
    'core.notifier',
    'core.ocr',
    'core.parser',
    'core.settings',
    'models.audio',
    'models.card',
    'models.word',
    'ui.settings_window',
    'ui.tray',
    'ui.word_selector',   # Multi-word selection UI
]

# pynput loads backend modules dynamically, so include its submodules
print("[PyInstaller] Collecting pynput submodules...")
pynput_subs = collect_submodules('pynput')
pynput_kb_subs = collect_submodules('pynput.keyboard')
pynput_mouse_subs = collect_submodules('pynput.mouse')
hiddenimports += pynput_subs + pynput_kb_subs + pynput_mouse_subs
print(f"[PyInstaller] - Added {len(pynput_subs)} pynput submodules")

# ============================================================================
# ANALYSIS
# ============================================================================
print("[PyInstaller] Starting PyInstaller Analysis...")
a = Analysis(
    ['src/main.py'],  # Entry point
    pathex=[ROOT_DIR, SRC_DIR],  # Python path for imports
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludedimports=[],
    win_private_assemblies=False,
    win_no_prefer_redirects=False,
    cipher=block_cipher,
    noarchive=False,
)

print("[PyInstaller] Analysis complete")
print(f"[PyInstaller] - Pure Python modules: {len(a.pure)}")
print(f"[PyInstaller] - Binaries: {len(a.binaries)}")
print(f"[PyInstaller] - Data files: {len(a.datas)}")

# ============================================================================
# PACKAGING
# ============================================================================
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JAM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (runs as system tray app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: Add path to .ico file if available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JAM',
)

print("[PyInstaller] Spec file complete")
