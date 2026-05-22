import json
import os
import threading
import sys

# When packaged as a frozen executable (PyInstaller/etc.), the application
# bundle location is not writable. Use a user-writable config directory
# (e.g. %USERPROFILE%\.jam) for settings when frozen.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(os.path.expanduser("~"), ".jam")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "capture_combo":    ["shift", "a"],
    "capture_mode":     "bbox",
    "capture_width":    200,
    "capture_height":   60,
    
    "anki_deck":        "Test Deck",
    "anki_note_type":   "Lapis",
    "anki_misc_info":   "JAM",
    "anki_media_path":  "", # e.g. C:/Users/user/AppData/Roaming/Anki2/User 1/collection.media
    "anki_profile":     "", # anki profile name (default = User 1)
}

class SettingsManager:
    def __init__(self):
        self._settings = {}
        self._lock = threading.Lock()
        self._last_modified = 0
        self._on_change_callbacks = []
        self._load_from_disk()
        self._start_watcher()

    def _load_from_disk(self):
        """Reads settings.json and merges with defaults."""
        if not os.path.exists(SETTINGS_FILE):
            self._settings = DEFAULT_SETTINGS.copy()
            self._save_to_disk()
            return
        
        with open (SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

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
        # Ensure the target directory exists (fixes bundled exe paths)
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        except Exception:
            # If for some reason the bundle location is not writable (frozen exe),
            # fall back to a user-writable config location.
            if getattr(sys, "frozen", False):
                user_dir = os.path.join(os.path.expanduser("~"), ".jam")
                try:
                    os.makedirs(user_dir, exist_ok=True)
                    fallback = os.path.join(user_dir, "settings.json")
                    with open(fallback, "w", encoding="utf-8") as f:
                        json.dump(self._settings, f, indent=4, ensure_ascii=False)
                    return
                except Exception:
                    pass
            raise

        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=4, ensure_ascii=False)

    def _start_watcher(self):
        """
        Background thread that polls settings.json every 2 seconds.
        If the file was modified, reloads automatically.
        """
        def watch():
            while True:
                threading.Event().wait(2)
                try:
                    current_modified = os.path.getmtime(SETTINGS_FILE)
                    if current_modified != self._last_modified:
                        print("[Settings] Change detected - reloading.")
                        self._load_from_disk()
                except FileNotFoundError:
                    pass
        
        threading.Thread(target=watch, daemon=True).start()

    def get(self, key: str, fallback=None):
        """Get a single setting value."""
        with self._lock:
            return self._settings.get(key, fallback)

    def set(self, key: str, value):
        """Update a setting in memory and immediately persist to disk"""
        with self._lock:
            self._settings[key] = value
        self._save_to_disk()

    def all(self) -> dict:
        """Returns a copy of all current settings"""
        with self._lock:
            return self._settings.copy()

    def on_change(self, callback):
        """
        Register a function to be called when settings are reloaded.
        Callback receives the full new settings dict as its argument

        Args:
            callback (function): Function to be called
            
        Usage:
            settings.on_change(lambda s: print("Settings changed:", s))
        """
        self._on_change_callbacks.append(callback)
