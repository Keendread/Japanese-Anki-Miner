# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for JAM (Japanese Anki Miner)
# Build with: pyinstaller jam.spec

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Project root directory
ROOT_DIR = os.path.dirname(os.path.abspath(SPEC))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
DATA_DIR = os.path.join(ROOT_DIR, 'data')

# Collect data files for sudachipy and other dependencies
datas = []

# Add data files from packages that need them
datas += collect_data_files('sudachipy')
datas += collect_data_files('manga_ocr')

# Add project-specific data (dictionary, etc.)
if os.path.isdir(DATA_DIR):
    datas.append((DATA_DIR, 'data'))

# Hidden imports for packages that aren't automatically detected
hiddenimports = [
    'sudachipy',
    'sudachidict_full',
    'manga_ocr',
    'PIL',
    'pystray',
    'pynput',
    'aiohttp',
    'lxml',
]

a = Analysis(
    ['src/main.py'],
    pathex=[ROOT_DIR],
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
