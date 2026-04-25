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
            
            text = ocr.extract_text(image)
            if not text:
                print("[Mouse] No text found.")
                return
            print(f"OCR result: {text}")
            
            word_data = parser.parse(text)
            if not word_data:
                print("[Mouse] Could not parse text.")
                return

        except Exception as e:
            print(f"Capture failed: {e}")
            
    def _trigger_bbox(self):
        """
        Opens a fullscreen transparent overlay.
        User can release the hotkey and draw a region for apturing.
        """
        if self._bbox_open:
            print("[BBox] Overlay already open, ignoring re-trigger.")
            return

        self._bbox_open = True
        print("[BBox] Queing task...")
        self.main_thread_queue.put(self._open_bbox_on_main_thread)
        print("[BBox] Task queued.")
        
    def _open_bbox_on_main_thread(self):
        print("[BBox] Main thread received task, opening overlay...")
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
        def process():
            try:
                filepath = save_capture(image)
                print(f"[BBox] Saved: {filepath}")

                text = ocr.extract_text(image)
                if not text:
                    print("[BBox] No text found.")
                    return
                print(f"[BBox] OCR result: {text}")
                
                word_data = parser.parse(text)
                if not word_data:
                    print("[BBox] Could not parse text.")
                    return
                
            except Exception as e:
                print(f"[BBox] Post-capture failed: {e}")
        
        threading.Thread(target=process, daemon=True).start()