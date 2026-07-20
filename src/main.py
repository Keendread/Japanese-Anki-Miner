import sys
import os
import signal
import threading

SRC_DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
APP_DIR  = ROOT_DIR
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, ROOT_DIR)

from core.logger import setup_logging, log
LOG_FILE = os.path.join(APP_DIR, 'jam.log')
LOGS_DIR = os.path.join(APP_DIR, 'logs')
setup_logging(APP_DIR, LOG_FILE)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from core import ocr
from core import parser
from core import dictionary
from core import anki
from core.startup import check_dependencies, make_tray_callbacks
from core.settings import SettingsManager
from core.capture import CaptureController
from core.signals import signals
from ui.tray import TrayManager
from ui.toasts import connect_toast_signals
from ui.word_selector import connect_word_selector_signal
from ui.settings_window import connect_settings_window_signal
from core.notifier import show_loading_toast, show_ready_toast


# ── Startup ───────────────────────────────────────────────────────────────────

print("=" * 50)
print("  JAM - Japanese Anki Miner  ")
print("=" * 50)
log.startup_banner()

warnings = check_dependencies()
for w in warnings:
    print(f"[Startup] WARNING: {w}")
    log.startup_warning(w)
log.startup("Dependencies checked. Initializing...")

app = QApplication.instance() or QApplication(sys.argv)

app.setQuitOnLastWindowClosed(False)

connect_toast_signals()
connect_word_selector_signal()
connect_settings_window_signal()
signals.run_on_main_thread.connect(lambda fn: fn())

_should_exit = [False]
_tray_manager: TrayManager = None
settings = SettingsManager()
combo    = settings.get_combo_vks()
capture  = CaptureController(combo, settings)
settings.register_capture(capture)
log.settings(f"Loaded. Hotkey: {settings.get('capture_combo')}")

# Background loading threads
print("[Startup] Loading OCR model in background...")
log.task_started("OCR model load")
threading.Thread(target=ocr.get_model,        daemon=True).start()

print("[Startup] Loading parser tokenizer in background...")
threading.Thread(target=parser.get_tokenizer, daemon=True).start()

print("[Startup] Opening dictionary connection in background...")
log.task_started("Dictionary + Anki sync")
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
    log.task_started(f"Anki sync (deck: {deck})")
    anki.sync_mined_from_anki(deck)
    log.task_done("Anki sync")

threading.Thread(target=_sync_anki, daemon=True).start()

from core.audio import refresh_speaker_ids
threading.Thread(target=refresh_speaker_ids, daemon=True).start()

print(f"[Startup] Hotkey: {settings.get('capture_combo')}")
print(f"[Startup] Capture mode: {settings.get('capture_mode', 'bbox')}")
print("[Startup] Starting system tray icon...")
print("-" * 50)

capture.start()

on_show_settings, on_open_logs, on_quit_requested = make_tray_callbacks(
    settings          = settings,
    capture           = capture,
    main_thread_queue = None,
    log_file          = LOG_FILE,
    logs_dir          = LOGS_DIR,
    on_quit_flag      = _should_exit,
)

_tray_manager = TrayManager(
    on_show_settings = on_show_settings,
    on_open_logs     = on_open_logs,
    on_quit          = on_quit_requested,
)
tray_thread = threading.Thread(target=_tray_manager.run, daemon=True)
tray_thread.start()

show_loading_toast(
    None,
    ocr_event    = ocr._model_ready,
    parser_event = parser._parser_ready,
    dict_event   = dictionary._db_ready,
    on_all_ready = lambda: show_ready_toast(None),
)

print("[Startup] JAM is running in system tray.")
log.loop_started()

# ── Main event loop ─────────────────────────────────────────────────────────
def _watch_for_quit():
    import time
    while not _should_exit[0]:
        time.sleep(0.1)
    app.quit()

threading.Thread(target=_watch_for_quit, daemon=True, name="jam-quit-watcher").start()

signal.signal(signal.SIGINT, signal.SIG_DFL)
_sigint_pump = QTimer()
_sigint_pump.timeout.connect(lambda: None)
_sigint_pump.start(200)

try:
    app.exec()
except KeyboardInterrupt:
    print("\n[Shutdown] Ctrl+C detected")
    log.loop_interrupted()

# ── Cleanup ───────────────────────────────────────────────────────────────────

print("[Shutdown] Stopping capture listener...")
log.shutdown("Stopping capture listener")
capture.stop()

print("[Shutdown] Stopping system tray...")
log.shutdown("Stopping system tray")
if _tray_manager:
    _tray_manager.stop()

print("[Shutdown] Goodbye!")
log.shutdown_done()
sys.exit(0)