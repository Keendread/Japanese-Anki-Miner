# Entry point of the applications
# Wires everything together

import sys
import os
import time
import threading
import queue

sys.path.insert(0, os.path.dirname(__file__))

from core.settings import SettingsManager
from core.capture import CaptureController
from core import ocr
from core import parser
from pynput import keyboard

main_thread_queue = queue.Queue()

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

# Load settings
settings = SettingsManager()
combo = {str_to_key(k) for k in settings.get("capture_combo")}
capture = CaptureController(combo, settings, main_thread_queue)
settings.on_change(update_combo)

threading.Thread(target=ocr.get_model, daemon=True).start()
threading.Thread(target=parser.get_tokenizer, daemon=True).start()

print(f"JAM running - hotkey: {settings.get('capture_combo')}")
print("Press Ctrl+C to quit.")

capture.start()

while True:
    try:
        task = main_thread_queue.get_nowait()
        task()
    except queue.Empty:
        pass
    time.sleep(0.05)