import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "capture_combo":    ["shift", "a"],
    "capture_mode":     "bbox",
    
    "capture_width":    200,
    "capture_height":   60,
    
    "anki_deck":        "Japanese Mining",
    "anki_note_type":   "JP Mining Note",
    "anki_media_path":  "",
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
        
        thread = threading.Thread(target=watch, daemon=True)
        thread.start()

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
