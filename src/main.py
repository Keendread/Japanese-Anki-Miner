# Entry point of the applications
# Wires everything together

import sys
import os
import time
import threading
import queue

SRC_DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
 
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, ROOT_DIR)

from core.settings import SettingsManager
from core.capture import CaptureController
from core import ocr
from core import parser
from core import dictionary
from core import anki
from pynput import keyboard

main_thread_queue = queue.Queue()

def check_dependencies():
    """
    Checks all required components before starting.
    Exits with a clear message if something unrecoverable is missing.
    Returns a list of non-fatal warnings.
    """
    warnings = []
 
    # 1. Check sudachidict_full is installed
    try:
        import importlib
        importlib.import_module("sudachidict_full")
    except ModuleNotFoundError:
        print("[Startup] ERROR: sudachidict_full is not installed.")
        print("          Run: pip install sudachidict_full")
        sys.exit(1)
 
    # 2. Check AnkiConnect is reachable (non-fatal)
    try:
        import urllib.request
        import json as _json
        req = urllib.request.Request(
            "http://localhost:8765",
            data=_json.dumps({"action": "version", "version": 6}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = _json.loads(resp.read())
            if result.get("result"):
                print(f"[Startup] AnkiConnect v{result['result']} detected.")
            else:
                warnings.append("AnkiConnect responded but returned no version.")
    except Exception:
        warnings.append(
            "AnkiConnect not reachable on port 8765. "
            "Start Anki and install the AnkiConnect addon to enable card creation."
        )
 
    # 3. Check dictionary DB — trigger build if missing or outdated
    # build_db.py lives in data/ which is at ROOT_DIR/data/build_db.py
    try:
        data_dir = os.path.join(ROOT_DIR, "data")
        sys.path.insert(0, data_dir)
        import build_db
        if build_db.needs_build():
            print("[Startup] Dictionary database missing or outdated — building now.")
            print("[Startup] This only happens once and may take a few minutes.")
            build_db.run_with_progress()
        else:
            print("[Startup] Dictionary database OK.")
    except Exception as e:
        warnings.append(f"Dictionary DB check failed: {e}")
 
    return warnings

def str_to_key(s: str):
    """
    Converts a settings string like 'shift' to keyboard.Key.shift,
    or leaves single characters like 'a' as is. """
    try:
        return getattr(keyboard.Key, s)
    except AttributeError:
        return s.lower()
    
def update_combo(new_settings):
    new_combo = {str_to_key(k) for k in new_settings["capture_combo"]}
    capture.set_combo(new_combo)
    print(f"[Settings] Hotkey updated to {new_settings['capture_combo']}")

# STARTUP

print("=" * 50)
print("  JAM - Japanese Anki Miner  ")
print("=" * 50)

warnings = check_dependencies()
for w in warnings:
    print(f"[Startup] WARNING: {w}")
    
# Load settings
settings = SettingsManager()
combo = {str_to_key(k) for k in settings.get("capture_combo")}
capture = CaptureController(combo, settings, main_thread_queue)
settings.on_change(update_combo)

# Background threads
print("[Startup] Loading OCR model in background...")
threading.Thread(target=ocr.get_model,        daemon=True).start()
 
print("[Startup] Loading parser tokenizer in background...")
threading.Thread(target=parser.get_tokenizer, daemon=True).start()

print("[Startup] Opening dictionary connection in background...")
threading.Thread(target=dictionary.init,      daemon=True).start()

# Sync existing Anki cards into mined.db (non-blocking, non-fatal)
def _sync_anki():
    deck = settings.get("anki_deck", "Test Deck")
    anki.sync_mined_from_anki(deck)
    
threading.Thread(target=_sync_anki, daemon=True).start()

 
print(f"[Startup] Hotkey: {settings.get('capture_combo')}")
print(f"[Startup] Capture mode: {settings.get('capture_mode', 'bbox')}")
print("[Startup] Press Ctrl+C or Q to quit.")
print("-" * 50)

capture.start()

while True:
    try:
        task = main_thread_queue.get_nowait()
        task()
    except queue.Empty:
        pass
    except KeyboardInterrupt:
        break
    time.sleep(0.05)
 