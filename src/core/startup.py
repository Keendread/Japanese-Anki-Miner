import sys
import os
from core.logger import log

SRC_DIR  = os.path.dirname(os.path.abspath(__file__))  # .../src/core
CORE_DIR = SRC_DIR
SRC_DIR  = os.path.dirname(CORE_DIR)                   # .../src
ROOT_DIR = os.path.dirname(SRC_DIR)                    # .../  (project root)
APP_DIR  = ROOT_DIR

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

def make_tray_callbacks(
    settings,
    capture,
    main_thread_queue,
    log_file: str,
    logs_dir: str,
    on_quit_flag,        # a mutable container e.g. [False] so we can set it
):
    """
    Builds the three tray callback functions and returns them.
    Keeps main.py free of UI/tray logic.
    """

    def on_show_settings():
        print("[Tray] Settings clicked")
        log.settings("Queueing show_settings_window task")
        try:
            from ui.settings_window import show_settings_window
            show_settings_window(settings, main_thread_queue, capture=capture)
            log.settings("Settings window task queued successfully")
        except Exception as e:
            log.error(f"Failed to queue settings task: {e}", exc=e)

    def on_open_logs():
        print("[Tray] View Logs clicked")
        try:
            if os.path.isdir(logs_dir):
                os.startfile(logs_dir)
            elif os.path.isfile(log_file):
                os.startfile(log_file)
            else:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                open(log_file, "a", encoding="utf-8").close()
                os.startfile(log_file)
        except Exception as e:
            print(f"[Tray] Could not open logs: {e}")
            log.exception("Failed to open log file")

    def on_quit_requested():
        print("[Tray] Quit requested")
        on_quit_flag[0] = True
        capture.stop()

    return on_show_settings, on_open_logs, on_quit_requested