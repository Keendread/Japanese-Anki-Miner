# Module for capturing the screen relative the cursor's current position
# Feeds into ocr.py

import threading
import queue
import os
from datetime import datetime

from pynput import keyboard
from mss import mss
from PIL import Image

from core import ocr
from core import parser
from core import dictionary
from core import anki
from core import notifier

try:
    import win32api
    WIN32_AVAILABLE = True
except:
    WIN32_AVAILABLE = False
    import pyautogui

def get_cursor_position() -> tuple[int, int]:
    """Returns current (x, y) screen position of mouse cursor"""
    if WIN32_AVAILABLE:
        return win32api.GetCursorPos()
    else:
        pos = pyautogui.position()
        return (pos.x, pos.y)

def capture_region(cursor_x: int, cursor_y: int,
                   width: int = 400, height: int = 120) -> Image.Image:
    """
    Captures rectangular region centered on the cursor

    Args:
        cursor_x (int): x coord of mouse
        cursor_y (int): y coord of mouse
        width (int, optional): width of region. Defaults to 400.
        height (int, optional): height of region. Defaults to 120.

    Returns:
        Image.Image: Image used for OCR
    """
    x1 = cursor_x - width // 2
    y1 = cursor_y - height // 2
    
    with mss() as sct:
        region = {"top": y1, "left": x1, "width": width, "height": height}
        raw = sct.grab(region)
        
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

def save_capture(image: Image.Image, output_dir: str = "captures") -> str:
    """
    Saves captured image to disk for debugging / dataset colletion.
    Returns the saved file path.

    Args:
        image (Image.Image): Image captured by capture_region function
        output_dir (str, optional): Set output directory. Defaults to "captures".

    Returns:
        str: The filepath where the image is saved
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    filepath = os.path.join(output_dir, filename)
    image.save(filepath)
    return filepath
    
def _wait_for_ready(timeout: float = 30.0) -> bool:
    """
    Waits for both OCR model and parser tokenizer to finish loading.
    Prints status if either is still loading when called.
    Returns True if both are ready within timeout, False otherwise.
 
    Args:
        timeout: Maximum seconds to wait for each component
    """
    ocr_ready    = ocr._model_ready.is_set()
    parser_ready = parser._parser_ready.is_set()
 
    if not ocr_ready or not parser_ready:
        ocr_status    = "✓" if ocr_ready    else "..."
        parser_status = "✓" if parser_ready else "..."
        print(f"[JAM] Models still loading (OCR: {ocr_status}  Parser: {parser_status}) — waiting...")
 
    if not ocr._model_ready.wait(timeout=timeout):
        print("[JAM] Timed out waiting for OCR model.")
        return False
 
    if not parser._parser_ready.wait(timeout=timeout):
        print("[JAM] Timed out waiting for parser.")
        return False
 
    return True
    
class CaptureController:
    def __init__(self, combo, settings, main_thread_queue: queue.Queue):
        self.combo = combo
        self.settings = settings
        self.main_thread_queue = main_thread_queue
        self.pressed_keys = set()
        self.combo_active = False
        
        self._bbox_open = False
        
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        
    def _normalize(self, key):
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else key
        return key
        
    def _on_press(self, key):
        self.pressed_keys.add(self._normalize(key))
        
        if self._matches_combo():
            if not self.combo_active:
                self.combo_active = True
                threading.Thread(target=self.on_trigger, daemon=True).start()
        
        # Debugging escape hotkey
        if self._normalize(key) == "q":
            self.stop()
                
    def _on_release(self, key):
        self.pressed_keys.discard(self._normalize(key))
        if not self._matches_combo():
            self.combo_active = False
                
    def _matches_combo(self):
        return all(k in self.pressed_keys for k in self.combo)
            
    def set_combo(self, new_combo: set):
        self.combo = new_combo
        
    def start(self):
        print("[Capture] Running")
        self.listener.start()
        
    def join(self):
        self.listener.join()

    def stop(self):
        print("[Capture] Stopped")
        self.listener.stop()
        
    def on_trigger(self):
        """
        Called in a background thread when hotkey fires.
        Routes to mouse or bbox capture based on capture_mode setting.
        """
        mode = self.settings.get("capture_mode", "bbox")
        
        if mode == "mouse":
            self._trigger_mouse()
        elif mode == "bbox":
            self._trigger_bbox()
        else:
            print(f"[Capture] Unknown capture_mode '{mode}', falling back to mouse.")
            self._trigger_mouse()
           
    def _trigger_mouse(self):
        """Mouse mode"""
        try:
            x, y = get_cursor_position()
            print(f"[Mouse] Cursor at ({x}, {y})")

            width = self.settings.get("capture_width", 200)
            height = self.settings.get("capture_height", 60)
            
            image = capture_region(x, y, width, height)
            filepath = save_capture(image)
            print(f"Saved: {filepath}")
            
            self._process(image, filepath)

        except Exception as e:
            print(f"[Mouse] Capture failed: {e}")
            
    def _trigger_bbox(self):
        """
        Opens a fullscreen transparent overlay.
        User can release the hotkey and draw a region for apturing.
        """
        if self._bbox_open:
            print("[BBox] Overlay already open, ignoring re-trigger.")
            return

        print("[BBox] Queuing overlay...")
        self.main_thread_queue.put(self._open_bbox_on_main_thread)
        
    def _open_bbox_on_main_thread(self):
        """Opens tkinter overlay. Must be called from main thread via queue."""
        self._bbox_open = True
        try:
            from core.bbox import open_bbox_overlay
            open_bbox_overlay(self._on_bbox_capture)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[BBox] Overlay failed: {e}")
        finally:
            self._bbox_open = False

    def _on_bbox_capture(self, image: Image.Image):
        """
        Callback from bbox overlay after user draws selection.
        Offloads to background thread so main thread stays free.
        """
        def process():
            try:
                filepath = save_capture(image)
                print(f"[BBox] Saved: {filepath}")
                self._process(image, filepath)
            except Exception as e:
                print(f"[BBox] Post-capture failed: {e}")
 
        threading.Thread(target=process, daemon=True).start()
        
        
    def _process(self, image: Image.Image, filepath: str):
        """
        Shared pipeline after any capture — called by both fixed and bbox modes.
        Waits for model readiness here so both modes behave identically:
        the capture always happens at the right moment, and OCR runs
        as soon as models are available.
 
        Args:
            image:    PIL Image of the capture
            filepath: path where the capture was saved (used as card context image)
        """
        # Wait for both models — prints status if still loading
        if not _wait_for_ready():
            print("[Process] Models not ready in time, dropping capture.")
            return
 
        # OCR
        text = ocr.extract_text(image)
        if not text:
            print("[Process] OCR returned empty string, skipping.")
            return
        print(f"[Process] OCR: {text}")
 
        # Parse
        parse_result = parser.parse(text)
        if parse_result is None:
            print("[Process] Parser returned no result, skipping.")
            return
 
        parse_result["capture_path"] = filepath
        
        # Dictionary Lookup
        dict_result = dictionary.lookup(parse_result)
        if dict_result is None:
            print("[Process] No dictionary entry found, skipping.")
            return
 
        # Merge parse + dictionary results into one payload
        payload = {**parse_result, **dict_result}
 
        # Duplicate check
        if anki.is_already_mined(
            payload["dictionary_form"],
            payload["reading"]
        ):
            print(f"[Process] Already mined: {payload['surface']}")
            notifier.show_duplicate_toast(
                payload["surface"],
                payload["reading"],
                self.main_thread_queue
            )
            return
        
        # Show card preview toast
        settings = self.settings

        def on_confirm():
            success, message, note_id = anki.add_card(payload, settings)
            if success:
                print(f"[Anki] {message}")
                notifier.show_success_toast(
                    payload["surface"],
                    self.main_thread_queue
                )
            else:
                print(f"[Anki] Failed: {message}")

        def on_discard():
            print(f"[Process] Discarded: {payload['surface']}")
        
        notifier.show_card_toast(
            payload,
            settings,
            self.main_thread_queue,
            on_confirm=on_confirm,
            on_discard=on_discard
        )
 
        # TODO: audio.py + image.py