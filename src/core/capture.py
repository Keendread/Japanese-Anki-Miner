# Module for capturing the screen relative the cursor's current position
# Feeds into ocr.py

import asyncio
import threading
import queue
import os
from datetime import datetime
from typing import Tuple, Any, Optional, List

from concurrent.futures import Future

from pynput import keyboard
from mss import mss
from PIL import Image

from core import ocr
from core import parser
from core import dictionary
from core import anki
from core import notifier
from core import audio
from core import image as image_module
from src.models.word import Word
from src.models.card import Card
from src.models.audio import AudioFile
from core.image import ImageCandidate

try:
    import win32api
    WIN32_AVAILABLE = True
except:
    WIN32_AVAILABLE = False
    import pyautogui

def get_cursor_position() -> Tuple[int, int]:
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
        cursor_x: X coordinate of cursor
        cursor_y: Y coordinate of cursor
        width: Width of region (default: 400)
        height: Height of region (default: 120)

    Returns:
        PIL Image suitable for OCR
    """
    x1 = cursor_x - width // 2
    y1 = cursor_y - height // 2
    
    with mss() as sct:
        region = {"top": y1, "left": x1, "width": width, "height": height}
        raw = sct.grab(region)
        
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

def save_capture(image: Image.Image, output_dir: str = "captures") -> str:
    """
    Saves captured image to disk for debugging/dataset collection.

    Args:
        image: PIL Image from capture_region
        output_dir: Output directory (default: "captures")

    Returns:
        Filepath where image was saved
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
    
    Args:
        timeout: Maximum seconds to wait for each component (default: 30.0)
        
    Returns:
        True if both ready within timeout, False otherwise
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
    def __init__(self, combo: set, settings: dict[str, Any], main_thread_queue: queue.Queue) -> None:
        self.combo: set = combo
        self.settings: dict[str, Any] = settings
        self.main_thread_queue: queue.Queue = main_thread_queue
        self.pressed_keys: set = set()
        self.combo_active: bool = False
        
        self._bbox_open: bool = False
        
        self.listener: keyboard.Listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        
    def _normalize(self, key: Any) -> Any:
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else key
        return key
        
    def _on_press(self, key: Any) -> None:
        self.pressed_keys.add(self._normalize(key))
        
        if self._matches_combo():
            if not self.combo_active:
                self.combo_active = True
                threading.Thread(target=self.on_trigger, daemon=True).start()
        
        # Debugging escape hotkey
        if self._normalize(key) == "q":
            self.stop()
                
    def _on_release(self, key: Any) -> None:
        self.pressed_keys.discard(self._normalize(key))
        if not self._matches_combo():
            self.combo_active = False
                
    def _matches_combo(self) -> bool:
        return all(k in self.pressed_keys for k in self.combo)
            
    def set_combo(self, new_combo: set) -> None:
        self.combo = new_combo
        
    def start(self) -> None:
        print("[Capture] Running")
        self.listener.start()
        
    def join(self) -> None:
        self.listener.join()

    def stop(self) -> None:
        print("[Capture] Stopped")
        self.listener.stop()
        
    def on_trigger(self) -> None:
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
           
    def _trigger_mouse(self) -> None:
        """Capture using fixed region around cursor"""
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
            
    def _trigger_bbox(self) -> None:
        """
        Opens fullscreen overlay for user to draw selection region.
        User can release hotkey and draw a region for capturing.
        """
        if self._bbox_open:
            print("[BBox] Overlay already open, ignoring re-trigger.")
            return

        print("[BBox] Queuing overlay...")
        self.main_thread_queue.put(self._open_bbox_on_main_thread)
        
    def _open_bbox_on_main_thread(self) -> None:
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

    def _on_bbox_capture(self, image: Image.Image) -> None:
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
        
        
    def _process(self, image: Image.Image, filepath: str) -> None:
        """
        Shared pipeline after any capture — called by both fixed and bbox modes.
        Waits for model readiness here so both modes behave identically:
        the capture always happens at the right moment, and OCR runs
        as soon as models are available.
 
        Args:
            image:    PIL Image of the capture
            filepath: path where the capture was saved (used as card context image)
        """
        # 1. Wait for both models — prints status if still loading
        if not _wait_for_ready():
            print("[Process] Models not ready in time, dropping capture.")
            return
 
        # 2. OCR
        text = ocr.extract_text(image)
        if not text:
            print("[Process] OCR returned empty string, skipping.")
            return
        print(f"[Process] OCR: {text}")
 
        # 3. Parse
        parse_result = parser.parse(text)
        if parse_result is None:
            print("[Process] Parser returned no result, skipping.")
            return
 
        word: Word = Word(
            surface = parse_result["surface"],
            dictionary_form = parse_result["dictionary_form"],
            reading = parse_result["reading"],
            pos = parse_result["pos"],
            meaning = None, # to be filled by dictionary lookup
            full_sentence = text,
            capture_path = filepath
        )
        
        # 4. Dictionary Lookup
        dict_result = dictionary.lookup(word)
        if dict_result is None:
            print("[Process] No dictionary entry found, skipping.")
            return
        # Update Word with dictionary data
        word.update_from_dictionary(dict_result)
        
        # Validate Word before creating card
        if not word.is_valid():
            print(f"[Process] Word '{word.surface}' is missing required fields.")
            return
        
        # 5. Card Assembly
        card: Card = Card.from_word(word, self.settings)
        if not card.is_valid():
            print(f"[Process] Card creation failed for '{word.surface}'.")
            return
 
        # 6. Duplicate check
        if anki.is_already_mined(
            card.source_word.dictionary_form,
            card.source_word.reading
        ):
            print(f"[Process] Already mined: {card.source_word.surface}")
            notifier.show_duplicate_toast(
                card.source_word.surface,
                card.source_word.reading,
                self.main_thread_queue
            )
            return
        
        # 7. Fetch Audio (Background/Asynchronous)
        audio_future: Future[Optional[AudioFile]] = Future()

        def _run_audio():
            try:
                result = asyncio.run(audio.fetch_audio(card.source_word))
                audio_future.set_result(result)
            except Exception as e:
                print(f"[Word] {card.source_word}")
                print(f"[Audio] Background fetch error: {e}")
                audio_future.set_result(None)

        threading.Thread(target=_run_audio, daemon=True).start()

        # 8. Fetch Image Candidates (Background/Async)
        image_future: Future[List[ImageCandidate]] = Future()
        
        def _run_image_fetch():
            try:
                candidates = asyncio.run(
                    image_module.fetch_candidates(card.source_word)
                )
                image_future.set_result(candidates)
            except Exception as e:
                print(f"[Image] Background fetch error: {e}")
                image_future.set_result([])
        
        threading.Thread(target=_run_image_fetch, daemon=True).start()
        
        # 9. Show card preview toast
        main_queue = self.main_thread_queue
        settings = self.settings

        def on_confirm():
            """
            Runs in a background thread when user clicks 'Add to Anki'.
 
            Step A — collect image candidates (wait up to 8 s).
            Step B — show ImagePicker on main thread; block until user picks.
            Step C — download + save chosen image to collection.media.
            Step D — add card to Anki.
            Step E — show success toast.
            Step F — apply audio to card once VOICEVOX finishes.
            """
            # A. Collect image candidates
            try:
                candidates: List[ImageCandidate] = image_future.result(timeout=8.0)
            except Exception:
                candidates = []
                print("[Image] Candidates not ready in time — proceeding without image.")
 
            # B. Show Image Picker
            picked_event = threading.Event()
            picked_result: List[Optional[ImageCandidate]] = [None]
 
            def on_image_selected(candidate: Optional[ImageCandidate]):
                picked_result[0] = candidate
                picked_event.set()
 
            image_module.show_image_picker(candidates, main_queue, on_image_selected)
 
            # Wait up to 60 s for the user to make a selection
            picked_event.wait(timeout=60.0)
            selected = picked_result[0]
            
            # C. Download & Save chosen image
            image_filename: Optional[str] = None
            if selected is not None:
                image_filename = image_module.save_to_media(selected, card.source_word, settings)
                if image_filename:
                    print(f"[Image] Ready for card: {image_filename}")
                else:
                    print("[Image] Save failed — card will have no image.")
                    
            # D. Add card to Anki
            success, message, note_id = anki.add_card(
                card, settings, image_filename=image_filename
            )
            
            if success:
                print(f"[Anki] {message}")
                # E. Success toast
                notifier.show_success_toast(card.source_word.surface,main_queue)
            else:
                print(f"[Anki] Failed: {message}")

            # F. Apply audio when VOICEVOX finishes (if any)
            def _apply_audio_when_ready():
                try:
                    audio_file = audio_future.result(timeout=30.0)
                except Exception:
                    audio_file = None
                
                if audio_file and note_id:
                    anki.update_card_audio(note_id, audio_file)
                else:
                    print(f"[Audio] No audio to apply to card {note_id}.")

            threading.Thread(target=_apply_audio_when_ready, daemon=True).start()

        def on_discard():
            print(f"[Process] Discarded: {card.source_word.surface}")
        
        notifier.show_card_toast(
            card.source_word,
            settings,
            main_queue,
            on_confirm=on_confirm,
            on_discard=on_discard,
        )