# Entry point of the application
# Wires everything together

import sys
import os
import time
import threading
import queue
import webbrowser
import subprocess
import logging
import importlib.util
from logging.handlers import RotatingFileHandler

if getattr(sys, 'frozen', False):
    # When bundled by PyInstaller, use the executable directory for resource paths.
    ROOT_DIR = os.path.dirname(sys.executable)
    SRC_DIR = os.path.join(ROOT_DIR, 'src')
    APP_DIR = os.path.join(os.path.expanduser('~'), '.jam')
else:
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(SRC_DIR)
    APP_DIR = ROOT_DIR
    sys.path.insert(0, SRC_DIR)
    sys.path.insert(0, ROOT_DIR)

LOG_FILE = os.path.join(APP_DIR, 'jam.log')
LOGS_DIR = os.path.join(APP_DIR, 'logs')

os.makedirs(APP_DIR, exist_ok=True)

handler = RotatingFileHandler(LOG_FILE, maxBytes=5_242_880, backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[handler])
logging.getLogger('manga_ocr').setLevel(logging.ERROR)

from core.settings import SettingsManager
from core.capture import CaptureController
from core import ocr
from core import parser
from core import dictionary
from core import anki
from ui.tray import TrayManager
from ui.settings_window import preload_tkinter, show_settings_window, pump_pending_window_once
from core.image import pump_pending_image_once
from ui.word_selector import pump_pending_selector_once
from pynput import keyboard

main_thread_queue = queue.Queue()
_should_exit = False
_tray_manager: TrayManager = None

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
        
        # For frozen exe, also check _internal/data (PyInstaller onedir structure)
        if getattr(sys, 'frozen', False) and not os.path.isdir(data_dir):
            internal_data = os.path.join(ROOT_DIR, "_internal", "data")
            if os.path.isdir(internal_data):
                data_dir = internal_data
        
        build_db_path = os.path.join(data_dir, 'build_db.py')
        
        # Load build_db as a module from file path (works even if not in sys.path)
        if os.path.isfile(build_db_path):
            spec = importlib.util.spec_from_file_location("build_db", build_db_path)
            build_db = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build_db)
            
            if build_db.needs_build():
                print("[Startup] Dictionary database missing or outdated — building now.")
                print("[Startup] This only happens once and may take a few minutes.")
                build_db.run_with_progress()
            else:
                print("[Startup] Dictionary database OK.")
        else:
            raise FileNotFoundError(f"build_db.py not found at {build_db_path}")
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

def on_show_settings():
    """Called when 'Settings' is clicked in tray menu."""
    print("[Tray] Settings clicked")
    logging.info("[Main] Queueing show_settings_window task")
    try:
        # Pass main_thread_queue to show_settings_window so it can use it for thread-safe Tkinter operations
        show_settings_window(settings, main_thread_queue)
        logging.info("[Main] Settings window task queued successfully")
    except Exception as e:
        logging.error(f"[Main] Failed to queue settings task: {e}", exc_info=True)

def on_open_logs():
    """Called when 'View Logs' is clicked in tray menu."""
    print("[Tray] View Logs clicked")
    log_file = LOG_FILE
    logs_dir = LOGS_DIR
    
    try:
        if os.path.isdir(logs_dir):
            os.startfile(logs_dir)
        elif os.path.isfile(log_file):
            os.startfile(log_file)
        else:
            # Create the log file if it doesn't yet exist so the user can open it
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            open(log_file, 'a', encoding='utf-8').close()
            os.startfile(log_file)
    except Exception as e:
        print(f"[Tray] Could not open logs: {e}")
        logging.exception("Failed to open log file")

def on_quit_requested():
    """Called when 'Exit' is clicked in tray menu."""
    global _should_exit
    print("[Tray] Quit requested")
    _should_exit = True
    capture.stop()


def _notify_when_ready():
    max_wait = 120.0
    ocr_ready = ocr._model_ready.wait(timeout=max_wait)
    parser_ready = parser._parser_ready.wait(timeout=max_wait)
    dict_ready = dictionary._db_ready.wait(timeout=max_wait)

    if ocr_ready and parser_ready and dict_ready:
        message = "OCR, parser, and dictionary are ready."
    else:
        missing = []
        if not ocr_ready:
            missing.append("OCR")
        if not parser_ready:
            missing.append("parser")
        if not dict_ready:
            missing.append("dictionary")
        message = "Ready with issues: " + ", ".join(missing)

    if _tray_manager:
        _tray_manager.notify("JAM startup", message)

# STARTUP

print("=" * 50)
print("  JAM - Japanese Anki Miner  ")
print("=" * 50)
logging.info("=" * 50)
logging.info("JAM - Japanese Anki Miner Startup")
logging.info("=" * 50)

warnings = check_dependencies()
for w in warnings:
    print(f"[Startup] WARNING: {w}")
    logging.warning(w)

logging.info("Dependencies checked. Initializing...")

# Load settings
settings = SettingsManager()
combo = {str_to_key(k) for k in settings.get("capture_combo")}
capture = CaptureController(combo, settings, main_thread_queue)
settings.on_change(update_combo)
logging.info(f"Settings loaded. Hotkey: {settings.get('capture_combo')}")

# Preload Tkinter now so the settings window opens faster later
preload_tkinter()
logging.info("Tkinter preloaded.")

# Background threads
print("[Startup] Loading OCR model in background...")
logging.info("Starting background model loading...")
threading.Thread(target=ocr.get_model,        daemon=True).start()
 
print("[Startup] Loading parser tokenizer in background...")
threading.Thread(target=parser.get_tokenizer, daemon=True).start()

print("[Startup] Opening dictionary connection in background...")
logging.info("Starting dictionary and Anki sync...")
threading.Thread(target=dictionary.init,      daemon=True).start()

# Sync existing Anki cards into mined.db (non-blocking, non-fatal)
def _sync_anki():
    deck = settings.get("anki_deck", "Test Deck")
    logging.info(f"Syncing Anki deck: {deck}")
    anki.sync_mined_from_anki(deck)
    logging.info("Anki sync complete.")
    
threading.Thread(target=_sync_anki, daemon=True).start()

# Start capture listener
print(f"[Startup] Hotkey: {settings.get('capture_combo')}")
print(f"[Startup] Capture mode: {settings.get('capture_mode', 'bbox')}")
print("[Startup] Starting system tray icon...")
print("-" * 50)

capture.start()

# Start system tray in a background thread
_tray_manager = TrayManager(
    on_show_settings=on_show_settings,
    on_open_logs=on_open_logs,
    on_quit=on_quit_requested,
)
tray_thread = threading.Thread(target=_tray_manager.run, daemon=True)
tray_thread.start()

threading.Thread(target=_notify_when_ready, daemon=True).start()
print("[Startup] JAM is running in system tray.")
logging.info("JAM startup complete. Main event loop started.")

# Main event loop
while not _should_exit:
    try:
        task = main_thread_queue.get_nowait()
        task_name = getattr(task, '__name__', str(task))
        print(f"[Main] Executing queued task: {task_name}")
        logging.debug(f"[Main] Executing task from queue: {task}")
        task()
        print(f"[Main] Task completed: {task_name}")
        logging.debug(f"[Main] Task completed successfully")
    except queue.Empty:
        pass
    except KeyboardInterrupt:
        print("\n[Shutdown] Ctrl+C detected")
        logging.info("Ctrl+C detected")
        break
    except Exception as e:
        logging.exception(f"Main loop error: {e}")
    # Pump settings window (if open) so Tk events are processed without blocking
    try:
        pump_pending_window_once()
    except Exception as e:
        logging.error(f"Error pumping settings window: {e}")
    try:
        pump_pending_image_once()
    except Exception as e:
        logging.error(f"Error pumping image picker: {e}")
    try:
        # Debug: check selector state
        from ui.word_selector import _ACTIVE_SELECTOR
        if _ACTIVE_SELECTOR is not None:
            print(f"[Main] Pumping selector (ui_built={_ACTIVE_SELECTOR._ui_built})")
        pump_pending_selector_once()
    except Exception as e:
        logging.error(f"Error pumping selector: {e}")
    time.sleep(0.05)

# Cleanup
print("[Shutdown] Stopping capture listener...")
logging.info("Shutdown: stopping capture listener")
capture.stop()

print("[Shutdown] Stopping system tray...")
logging.info("Shutdown: stopping tray")
if _tray_manager:
    _tray_manager.stop()

print("[Shutdown] Goodbye!")
logging.info("JAM shutdown complete.")
sys.exit(0)