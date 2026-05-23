import json
import os
import threading
import sys


def _get_base_dir() -> str:
    """
    Resolve the base directory for user-writable files (settings, databases,
    generated audio).

    Strategy:
      - Frozen (PyInstaller .exe): use the folder that contains the .exe.
        sys.executable is the .exe itself, so we take its parent.
        This gives a portable layout — all data lives next to the executable.
      - Development (plain Python): use the src/core/ folder that contains
        this file, matching the existing behaviour.
    """
    if getattr(sys, "frozen", False):
        # e.g. C:/Users/you/JAM/JAM.exe  →  C:/Users/you/JAM
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_base_dir()

# ── Path constants ────────────────────────────────────────────────────────────
# All resolved relative to BASE_DIR so the app is fully portable.
SETTINGS_FILE   = os.path.join(BASE_DIR, "settings.json")
DATA_DIR        = os.path.join(BASE_DIR, "data")
JMDICT_DB       = os.path.join(DATA_DIR, "jmdict.db")
MINED_DB        = os.path.join(DATA_DIR, "mined.db")
AUDIO_DIR       = os.path.join(DATA_DIR, "audio")

# build_db.py is bundled *inside* the exe's _internal tree; expose its path so
# other modules can locate it without hardcoding PyInstaller internals.
if getattr(sys, "frozen", False):
    # PyInstaller unpacks non-Python data next to _MEIPASS for onedir builds.
    _BUNDLE_DIR = sys._MEIPASS  # type: ignore[attr-defined]
    BUILD_DB_SCRIPT = os.path.join(_BUNDLE_DIR, "data", "build_db.py")
else:
    BUILD_DB_SCRIPT = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "build_db.py"
    )

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "capture_combo":    ["shift", "a"],
    "capture_mode":     "bbox",
    "capture_width":    200,
    "capture_height":   60,

    "anki_deck":        "Test Deck",
    "anki_note_type":   "Lapis",
    "anki_misc_info":   "JAM",
    "anki_media_path":  "",   # e.g. C:/Users/you/AppData/Roaming/Anki2/User 1/collection.media
    "anki_profile":     "",   # Anki profile name (default: User 1)
}


class SettingsManager:
    def __init__(self):
        self._settings: dict = {}
        self._lock = threading.Lock()
        self._last_modified: float = 0
        self._on_change_callbacks: list = []
        self._ensure_data_dirs()
        self._load_from_disk()
        self._start_watcher()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_data_dirs(self):
        """Create data/ and data/audio/ next to the exe if they don't exist."""
        for directory in (DATA_DIR, AUDIO_DIR):
            os.makedirs(directory, exist_ok=True)

    def _load_from_disk(self):
        """Read settings.json and merge with defaults."""
        if not os.path.exists(SETTINGS_FILE):
            self._settings = DEFAULT_SETTINGS.copy()
            self._save_to_disk()
            return

        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded: dict = json.load(f)

        # Fill in any keys added since the user's file was written.
        for key, value in DEFAULT_SETTINGS.items():
            if key not in loaded:
                loaded[key] = value

        with self._lock:
            self._settings = loaded

        self._last_modified = os.path.getmtime(SETTINGS_FILE)
        print("[Settings] Loaded from disk.")

        for callback in self._on_change_callbacks:
            callback(self._settings)

    def _save_to_disk(self):
        """Persist current settings to settings.json."""
        # BASE_DIR already exists (it's the exe folder), but be safe.
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=4, ensure_ascii=False)

    def _start_watcher(self):
        """
        Background thread that polls settings.json every 2 seconds.
        Reloads automatically if the file was modified externally (e.g. user
        edited it by hand).
        """
        def watch():
            event = threading.Event()
            while True:
                event.wait(2)
                try:
                    current_mtime = os.path.getmtime(SETTINGS_FILE)
                    if current_mtime != self._last_modified:
                        print("[Settings] Change detected — reloading.")
                        self._load_from_disk()
                except FileNotFoundError:
                    pass

        threading.Thread(target=watch, daemon=True).start()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str, fallback=None):
        """Return a single setting value."""
        with self._lock:
            return self._settings.get(key, fallback)

    def set(self, key: str, value):
        """Update a setting in memory and immediately persist to disk."""
        with self._lock:
            self._settings[key] = value
        self._save_to_disk()

    def all(self) -> dict:
        """Return a copy of all current settings."""
        with self._lock:
            return self._settings.copy()

    def on_change(self, callback):
        """
        Register a callback invoked whenever settings are reloaded from disk.
        The callback receives the full settings dict as its only argument.

        Usage:
            settings.on_change(lambda s: print("Changed:", s))
        """
        self._on_change_callbacks.append(callback)