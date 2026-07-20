import json
import os
import threading

from core.input import VK_NAMES, record_hotkey

_NAME_TO_VK: dict[str, int] = {name: vk for vk, name in VK_NAMES.items()}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE   = os.path.join(BASE_DIR, "settings.json")
DATA_DIR        = os.path.join(BASE_DIR, "data")
JMDICT_DB       = os.path.join(DATA_DIR, "jmdict.db")
MINED_DB        = os.path.join(DATA_DIR, "mined.db")
AUDIO_DIR       = os.path.join(DATA_DIR, "audio")


DEFAULT_SETTINGS = {
    "capture_combo":    ["LShift", "A"],
    "capture_mode":     "bbox",
    "record_combo":     ["RShift", "R"],   

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
        self._capture: object = None
        self._ensure_data_dirs()
        self._load_from_disk()
        self._start_watcher()
        
    def register_capture(self, capture) -> None:
        self._capture = capture
        self._push_combo_to_capture()
        print(f"[Settings] Capture Registered")
        
        
    def get_combo_vks(self) -> set[int]:
        names = self.get("capture_combo", [])
        vks = set()
        for name in names:
            vk = _NAME_TO_VK.get(name)
            if vk is not None:
                vks.add(vk)
            else:
                print(f"[Settings] Warning: unknown key name '{name}' in combo - skipped")
        return vks
    
    def set_combo_from_recording(self) -> dict:
        result = record_hotkey()
        self.set("capture_combo", sorted(result["names"]))
        print(f"[Settings] Combo saved: {result['names']}")
        self._push_combo_to_capture()
        return result

    def get_record_combo_vks(self) -> set[int]:
        names = self.get("record_combo", [])
        vks = set()
        for name in names:
            vk = _NAME_TO_VK.get(name)
            if vk is not None:
                vks.add(vk)
            else:
                print(f"[Settings] Warning: unknown key name '{name}' in record_combo - skipped")
        return vks

    def set_record_combo_from_recording(self) -> dict:
        result = record_hotkey()
        self.set("record_combo", sorted(result["names"]))
        print(f"[Settings] Record combo saved: {result['names']}")
        return result
    
    def _push_combo_to_capture(self) -> None:
        if self._capture is not None:
            vks = self.get_combo_vks()
            self._capture.set_combo(vks)
            print(f"[Settings] Hotkey pushed to capture: {self.get('capture_combo')}")

    def _ensure_data_dirs(self):
        for directory in (DATA_DIR, AUDIO_DIR):
            os.makedirs(directory, exist_ok=True)

    def _load_from_disk(self):
        if not os.path.exists(SETTINGS_FILE):
            self._settings = DEFAULT_SETTINGS.copy()
            self._save_to_disk()
            return

        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded: dict = json.load(f)

        for key, value in DEFAULT_SETTINGS.items():
            if key not in loaded:
                loaded[key] = value

        with self._lock:
            self._settings = loaded

        self._last_modified = os.path.getmtime(SETTINGS_FILE)
        print("[Settings] Loaded from disk.")

        self._push_combo_to_capture()

    def _save_to_disk(self):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._settings, f, indent=4, ensure_ascii=False)
        print("[Settings] Saved to disk.")
        
    def _start_watcher(self):
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
        with self._lock:
            return self._settings.get(key, fallback)

    def set(self, key: str, value):
        with self._lock:
            self._settings[key] = value
        self._save_to_disk()

    def all(self) -> dict:
        with self._lock:
            return self._settings.copy()