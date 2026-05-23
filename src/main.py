# Entry point of the application
# Wires everything together

import sys
import os
import time
import threading
import queue
import logging
from logging.handlers import RotatingFileHandler

if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
    SRC_DIR  = os.path.join(ROOT_DIR, 'src')
    APP_DIR  = ROOT_DIR                          # portable: data lives next to the exe
else:
    SRC_DIR  = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(SRC_DIR)
    APP_DIR  = ROOT_DIR
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
from core.notifier import (
    pump_pending_toast_once,
    pump_pending_dup_once,
    pump_loading_toast_once,
    show_loading_toast,
    show_ready_toast,
)
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
    try:
        import importlib.util
        data_dir = os.path.join(ROOT_DIR, "data")

        # For frozen exe, also check _internal/data (PyInstaller onedir structure)
        if getattr(sys, 'frozen', False) and not os.path.isdir(data_dir):
            internal_data = os.path.join(ROOT_DIR, "_internal", "data")
            if os.path.isdir(internal_data):
                data_dir = internal_data

        build_db_path = os.path.join(data_dir, 'build_db.py')

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
    try:
        return getattr(keyboard.Key, s)
    except AttributeError:
        return s.lower()


def update_combo(new_settings):
    new_combo = {str_to_key(k) for k in new_settings["capture_combo"]}
    capture.set_combo(new_combo)
    print(f"[Settings] Hotkey updated to {new_settings['capture_combo']}")


def on_show_settings():
    print("[Tray] Settings clicked")
    logging.info("[Main] Queueing show_settings_window task")
    try:
        show_settings_window(settings, main_thread_queue)
        logging.info("[Main] Settings window task queued successfully")
    except Exception as e:
        logging.error(f"[Main] Failed to queue settings task: {e}", exc_info=True)


def on_open_logs():
    print("[Tray] View Logs clicked")
    try:
        if os.path.isdir(LOGS_DIR):
            os.startfile(LOGS_DIR)
        elif os.path.isfile(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            open(LOG_FILE, 'a', encoding='utf-8').close()
            os.startfile(LOG_FILE)
    except Exception as e:
        print(f"[Tray] Could not open logs: {e}")
        logging.exception("Failed to open log file")


def on_quit_requested():
    global _should_exit
    print("[Tray] Quit requested")
    _should_exit = True
    capture.stop()


# ── Startup ───────────────────────────────────────────────────────────────────

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

settings = SettingsManager()
combo    = {str_to_key(k) for k in settings.get("capture_combo")}
capture  = CaptureController(combo, settings, main_thread_queue)
settings.on_change(update_combo)
logging.info(f"Settings loaded. Hotkey: {settings.get('capture_combo')}")

preload_tkinter()
logging.info("Tkinter preloaded.")

# Background loading threads
print("[Startup] Loading OCR model in background...")
logging.info("Starting background model loading...")
threading.Thread(target=ocr.get_model,        daemon=True).start()

print("[Startup] Loading parser tokenizer in background...")
threading.Thread(target=parser.get_tokenizer, daemon=True).start()

print("[Startup] Opening dictionary connection in background...")
logging.info("Starting dictionary and Anki sync...")
def _init_dictionary():
    # Small poll loop — waits for build_db to finish if it's running
    import time
    from core import dictionary
    while True:
        db_path = dictionary._get_db_path()
        if os.path.exists(db_path):
            break
        time.sleep(1.0)
    dictionary.init()

threading.Thread(target=_init_dictionary, daemon=True).start()

def _sync_anki():
    deck = settings.get("anki_deck", "Test Deck")
    logging.info(f"Syncing Anki deck: {deck}")
    anki.sync_mined_from_anki(deck)
    logging.info("Anki sync complete.")

threading.Thread(target=_sync_anki, daemon=True).start()

print(f"[Startup] Hotkey: {settings.get('capture_combo')}")
print(f"[Startup] Capture mode: {settings.get('capture_mode', 'bbox')}")
print("[Startup] Starting system tray icon...")
print("-" * 50)

capture.start()

_tray_manager = TrayManager(
    on_show_settings=on_show_settings,
    on_open_logs=on_open_logs,
    on_quit=on_quit_requested,
)
tray_thread = threading.Thread(target=_tray_manager.run, daemon=True)
tray_thread.start()

# Show the loading progress toast immediately.
# It watches the three events and auto-dismisses → fires show_ready_toast.
show_loading_toast(
    main_thread_queue,
    ocr_event    = ocr._model_ready,
    parser_event = parser._parser_ready,
    dict_event   = dictionary._db_ready,
    on_all_ready = lambda: show_ready_toast(main_thread_queue),
)

print("[Startup] JAM is running in system tray.")
logging.info("JAM startup complete. Main event loop started.")

# ── Main event loop ───────────────────────────────────────────────────────────

while not _should_exit:
    # Drain the ENTIRE task queue each iteration — not just one task.
    # Critical: if we only drain one task per cycle, toast.create can sit
    # behind other queued work and not run until OCR is already done,
    # causing the loading window to appear and instantly dismiss.
    try:
        while True:
            try:
                task = main_thread_queue.get_nowait()
                task_name = getattr(task, '__name__', str(task))
                print(f"[Main] Executing queued task: {task_name}")
                logging.debug(f"[Main] Executing task from queue: {task}")
                task()
                print(f"[Main] Task completed: {task_name}")
                logging.debug(f"[Main] Task completed successfully")
            except queue.Empty:
                break
    except KeyboardInterrupt:
        print("\n[Shutdown] Ctrl+C detected")
        logging.info("Ctrl+C detected")
        break
    except Exception as e:
        logging.exception(f"Main loop error: {e}")

# Pump all active UI components
    try:
        from ui.settings_window import _TK_ROOT
        if _TK_ROOT is not None:
            _TK_ROOT.update()
    except Exception as e:
        logging.error(f"Error pumping Tk root: {e}")
    try:
        pump_pending_window_once()
    except Exception as e:
        logging.error(f"Error pumping settings window: {e}")
    try:
        pump_loading_toast_once()
    except Exception as e:
        logging.error(f"Error pumping loading toast: {e}")
    try:
        pump_pending_toast_once()
    except Exception as e:
        logging.error(f"Error pumping card toast: {e}")
    try:
        pump_pending_dup_once()
    except Exception as e:
        logging.error(f"Error pumping dup toast: {e}")
    try:
        pump_pending_image_once()
    except Exception as e:
        logging.error(f"Error pumping image picker: {e}")

    time.sleep(0.05)

# ── Cleanup ───────────────────────────────────────────────────────────────────

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