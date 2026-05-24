# Module for capturing the screen relative the cursor's current position
# Feeds into ocr.py

import asyncio
import threading
import queue
import os
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, List, Optional, Tuple

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
from core.detector import (
    TextRegion,
    detect_regions,
    smart_crop,
    segment_screen,
    _detect_regions_canny,
)
from src.models.word import Word
from src.models.card import Card
from src.models.audio import AudioFile
from core.image import ImageCandidate
from src.ui.word_selector import WordEntry, show_word_selector

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

def capture_full_screen() -> Image.Image:
    """Captures primary monitor, downsampled to logical resolution."""
    with mss() as sct:
        raw = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    # Downsample HiDPI captures (physical 2880x1800 -> logical 1440x900)
    if img.width > 2000:
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    return img

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

def _ocr_region(image: Image.Image) -> str:
    return ocr.extract_text(image)
 
 
def _ocr_all_regions(
    full_image:  Image.Image,
    regions:     List[TextRegion],
    max_workers: int = 3,
) -> List[Tuple[TextRegion, str]]:
    """
    OCRs all detected regions concurrently via ThreadPoolExecutor.
    MangaOCR releases the GIL during PyTorch inference so threads do run
    in parallel, reducing total time from N*1s to roughly N/workers seconds.
    """
    print(f"[_ocr_all_regions] Starting OCR of {len(regions)} region(s)")
    logging.info(f"[_ocr_all_regions] Starting OCR of {len(regions)} region(s)")
    
    crops = [(region, region.crop_from(full_image, pad=2)) for region in regions]
    results: List[Tuple[TextRegion, str]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_ocr_region, crop): region for region, crop in crops}
        for future, region in futures.items():
            try:
                text = future.result(timeout=10.0)
                print(f"[_ocr_all_regions] Region OCR result: '{text}' (empty={not text or not text.strip()})")
                if text and text.strip():
                    results.append((region, text.strip()))
                    print(f"[_ocr_all_regions]   Added to results: '{text.strip()}'")
            except Exception as e:
                print(f"[OCR] Region failed: {e}")
                logging.error(f"[OCR] Region failed: {e}")

    print(f"[_ocr_all_regions] Returning {len(results)} OCR result(s)")
    return results


def _build_word_entries(
    ocr_results: List[Tuple[TextRegion, str]],
) -> List[WordEntry]:
    """
    Parses every OCR result, does dictionary lookup, and checks mined.db.
    Deduplicates by dictionary_form so the same word never appears twice.
    Returns a list ready for WordSelectorUI.
    """
    print(f"[_build_word_entries] Processing {len(ocr_results)} OCR result(s)")
    logging.info(f"[_build_word_entries] Processing {len(ocr_results)} OCR result(s)")
    for i, (_region, text) in enumerate(ocr_results):
        print(f"[_build_word_entries]   OCR {i}: '{text}'")
    
    entries: List[WordEntry] = []
    seen: set = set()

    for _region, text in ocr_results:
        # Try tokenizing the OCR text — if multiple morphemes are present,
        # expose each content morpheme as its own selectable entry so users
        # can pick multiple words from a single OCR region.
        morphemes = parser.tokenize(text)
        if not morphemes:
            # Fall back to the old single-target parse
            parse_result = parser.parse(text)
            if not parse_result:
                continue
            morpheme_list = [parse_result]
        else:
            morpheme_list = []
            for m in morphemes:
                pos = m.part_of_speech()[0]
                # Skip non-content tokens (particles, punctuation)
                if pos in ("助詞", "助動詞", "補助記号", "空白"):
                    continue
                m_dict_form = m.dictionary_form()
                m_surface = m.surface()
                m_reading = parser._kata_to_hira(m.reading_form())
                morpheme_list.append({
                    "surface": m_surface,
                    "dictionary_form": m_dict_form,
                    "reading": m_reading,
                    "pos": pos,
                    "sentence": text,
                    "sentence_furigana": parser.build_sentence_furigana(morphemes),
                })

        for parse_result in morpheme_list:
            dict_form = parse_result.get("dictionary_form", "")
            if not dict_form or dict_form in seen:
                continue
            seen.add(dict_form)

            word = Word(
                surface         = parse_result.get("surface", ""),
                dictionary_form = dict_form,
                reading         = parse_result.get("reading", ""),
                pos             = parse_result.get("pos", ""),
                meaning         = None,
                full_sentence   = parse_result.get("sentence", text),
                sentence_furigana=parse_result.get("sentence_furigana", ""),
            )

            dict_result = dictionary.lookup(word)
            if dict_result is None:
                word.meaning = "(not in dictionary)"
            else:
                word.update_from_dictionary(dict_result)
            _finalize_sentence_furigana(word)

            is_mined = anki.is_already_mined(word.dictionary_form, word.reading)

            entries.append(WordEntry(
                word=word,
                is_mined=is_mined,
                selected=not is_mined,
            ))
            print(f"[_build_word_entries]   Added entry: {word.surface} ({word.dictionary_form}), mined={is_mined}")
 
    print(f"[_build_word_entries] Returning {len(entries)} word entries")
    return entries

def _finalize_sentence_furigana(word: Word) -> None:
    """
    Ensures sentence_furigana matches whatever best_sentence() will return.
    Called after update_from_dictionary() so example_sentences is populated.
    When OCR was a bare word, best_sentence() picks Tatoeba/Jitendex — 
    we regenerate furigana for that sentence so SentenceFurigana stays in sync.
    """
    best = word.best_sentence()
    if not best:
        return
    # OCR was a real sentence — furigana already built correctly from OCR morphemes
    if best.strip() == (word.full_sentence or "").strip():
        return
    # best_sentence() chose a different source — rebuild furigana for it
    morphemes = parser.tokenize(best)
    word.sentence_furigana = parser.build_sentence_furigana(morphemes)
    
class CaptureController:
    def __init__(self, combo: set, settings: dict[str, Any],
                 main_thread_queue: queue.Queue) -> None:
        self.combo             = combo
        self.settings          = settings
        self.main_thread_queue = main_thread_queue
        self.pressed_keys: set = set()
        self.combo_active      = False
        self._bbox_open        = False
        self._last_trigger_time = 0  # Throttle rapid hotkey presses
        self._recording        = False
 
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        
    def _normalize(self, key: Any) -> Any:
        # Collapse left/right variants
        _variant_map = {
            keyboard.Key.ctrl_r:  keyboard.Key.ctrl_l,
            keyboard.Key.shift_r: keyboard.Key.shift_l,
            keyboard.Key.alt_r:   keyboard.Key.alt_l,
            keyboard.Key.alt_gr:  keyboard.Key.alt_l,
        }
        if isinstance(key, keyboard.KeyCode):
            char = key.char
            if char is not None:
                # Ctrl held maps 'a'-'z' to '\x01'-'\x1a' — convert back to letter
                if len(char) == 1 and ord(char) < 32:
                    char = chr(ord(char) + 96)  # '\x01' -> 'a', '\x02' -> 'b', etc.
                return char.lower()
            return key
        return _variant_map.get(key, key)
        
    def _on_press(self, key: Any) -> None:
        norm_key = self._normalize(key)
        self.pressed_keys.add(norm_key)
        if self._recording:
            return
        if self._matches_combo():
            if not self.combo_active:
                import time
                now = time.time()
                # Ignore if triggered less than 0.5s ago (throttle)
                if now - self._last_trigger_time < 0.5:
                    return
                self._last_trigger_time = now
                self.combo_active = True
                threading.Thread(target=self.on_trigger, daemon=True).start()
        if norm_key == "q":
            self.stop()
                
    def _on_release(self, key: Any) -> None:
        self.pressed_keys.discard(self._normalize(key))
        if not self._matches_combo():
            self.combo_active = False
                
    def _matches_combo(self) -> bool:
        return self.combo == self.pressed_keys
    
    def set_recording(self, recording: bool) -> None:
        """Call with True while settings hotkey recorder is active."""
        self._recording = recording
            
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
        mode = self.settings.get("capture_mode", "bbox")
        print(f"[Capture.on_trigger] Triggered in {mode} mode")
        logging.info(f"[Hotkey] Hotkey triggered - capture mode: {mode}")
        dispatch = {
            "mouse":  self._trigger_mouse,
            "bbox":   self._trigger_bbox,
            "screen": self._trigger_screen,
        }
        fn = dispatch.get(mode)
        if fn:
            fn()
        else:
            logging.error(f"[Hotkey] Unknown capture mode: {mode}")
            print(f"[Capture] Unknown mode '{mode}', falling back to mouse.")
            self._trigger_mouse()
           
    # ── Mouse mode (smart crop) ───────────────────────────────────────────────
 
    def _trigger_mouse(self) -> None:
        try:
            x, y   = get_cursor_position()
            width  = self.settings.get("capture_width",  400)
            height = self.settings.get("capture_height", 120)
            logging.info(f"[Mouse] Cursor at ({x}, {y})")
            print(f"[Mouse] Cursor at ({x}, {y})")

            initial = capture_region(x, y, width, height)
            logging.debug(f"[Mouse] Captured region: {initial.width}x{initial.height}")

            # Save the original capture for debugging/training — before smart crop
            filepath = save_capture(initial)
            logging.info(f"[Mouse] Capture saved to {filepath}")

            cropped, region = smart_crop(initial, width // 2, height // 2)

            if region:
                logging.info(f"[Mouse] Smart-cropped to {region.w}x{region.h}px (original {width}x{height}px)")
                print(f"[Mouse] Smart-cropped to {region.w}x{region.h}px "
                    f"(original {width}x{height}px)")
            else:
                logging.warning(f"[Mouse] No region found — using full capture.")
                print("[Mouse] No region found — using full capture.")

            self._process(cropped, filepath)

        except Exception as e:
            logging.error(f"[Mouse] Capture failed: {e}", exc_info=True)
            print(f"[Mouse] Failed: {e}")
            
    # ── BBox mode ─────────────────────────────────────────────────────────────
 
    def _trigger_bbox(self) -> None:
        print(f"[Capture._trigger_bbox] Called, _bbox_open={self._bbox_open}")
        if self._bbox_open:
            print(f"[Capture._trigger_bbox] Already open, returning")
            return
        print(f"[Capture._trigger_bbox] Queuing _open_bbox_on_main_thread")
        self.main_thread_queue.put(self._open_bbox_on_main_thread)
 
    def _open_bbox_on_main_thread(self) -> None:
        print(f"[Capture._open_bbox_on_main_thread] EXECUTING - setting _bbox_open=True")
        self._bbox_open = True
        try:
            from core.bbox import open_bbox_overlay
            print(f"[Capture._open_bbox_on_main_thread] Calling open_bbox_overlay...")
            open_bbox_overlay(self._on_bbox_capture)
            print(f"[Capture._open_bbox_on_main_thread] open_bbox_overlay returned")
        except Exception as e:
            print(f"[BBox] Overlay failed: {e}")
        finally:
            print(f"[Capture._open_bbox_on_main_thread] Setting _bbox_open=False")
            self._bbox_open = False
 
    def _on_bbox_capture(self, image: Image.Image) -> None:
        def process():
            try:
                filepath = save_capture(image)
                if not _wait_for_ready():
                    return

                regions = detect_regions(image, dilation_x=40, dilation_y=3)
                print(f"[BBox] {len(regions)} region(s) detected.")

                if not regions:
                    logging.info("[BBox] No regions detected — trying sensitive fallback #1")
                    regions = detect_regions(image, min_area=20, dilation_x=40, dilation_y=2)
                    print(f"[BBox] fallback #1: {len(regions)} region(s) detected.")

                if not regions:
                    logging.info("[BBox] Still no regions — trying fallback #2 (ultra-sensitive)")
                    regions = detect_regions(image, min_area=10, dilation_x=40, dilation_y=1)
                    print(f"[BBox] fallback #2: {len(regions)} region(s) detected.")

                if not regions:
                    logging.info("[BBox] Still no regions — trying fallback #3 (minimal threshold)")
                    regions = detect_regions(image, min_area=5, dilation_x=40, dilation_y=1)
                    print(f"[BBox] fallback #3: {len(regions)} region(s) detected.")

                if not regions:
                    logging.info("[BBox] No regions found — trying Canny edge detection fallback")
                    regions = _detect_regions_canny(image)
                    print(f"[BBox] Canny fallback: {len(regions)} region(s) detected.")

                if not regions:
                    logging.warning("[BBox] No regions found after all fallbacks — using full image as one region")
                    print("[BBox] No regions found — using full image as fallback region")
                    w, h = image.size
                    regions = [TextRegion(x=0, y=0, w=w, h=h)]

                if len(regions) <= 1:
                    if regions:
                        cropped = regions[0].crop_from(image, pad=4)
                        self._process(cropped, filepath)
                    else:
                        self._process(image, filepath)
                else:
                    self._process_multi(image, regions, filepath)
            except Exception as e:
                logging.error(f"[BBox] Post-capture failed: {e}", exc_info=True)
                print(f"[BBox] Post-capture failed: {e}")

        threading.Thread(target=process, daemon=True).start()

    # ── Screen mode ───────────────────────────────────────────────────────────
 
    def _trigger_screen(self) -> None:
        """
        Captures full screen, detects all text regions, OCRs each concurrently,
        then shows multi-word selector with mined.db filtering.
        """
        def capture():
            try:
                if not _wait_for_ready():
                    return
                print("[Screen] Capturing full screen...")
                full     = capture_full_screen()
                filepath = save_capture(full)
                print(f"[Screen] {full.width}x{full.height}px")
 
                regions = segment_screen(full)
                print(f"[Screen] {len(regions)} text region(s).")
 
                if not regions:
                    print("[Screen] No text detected.")
                    return
 
                self._process_multi(full, regions, filepath)
 
            except Exception as e:
                print(f"[Screen] Failed: {e}")
 
        threading.Thread(target=capture, daemon=True).start()
        
    # ── Single-word pipeline ──────────────────────────────────────────────────
 
    def _process(self, image: Image.Image, filepath: str) -> None:
        """OCR → Parse → Dict → Card → [audio+image bg] → Toast → Anki."""
        logging.info(f"[Pipeline] Starting single-word processing: {filepath}")
        
        if not _wait_for_ready():
            logging.warning("[Pipeline] Models not ready, aborting")
            return
 
        text = ocr.extract_text(image)
        if not text:
            logging.warning("[Pipeline] OCR extraction returned empty text")
            print("[Process] OCR empty.")
            return
        
        logging.info(f"[Pipeline] OCR extracted: {text[:100]}")
        print(f"[Process] OCR: {text}")
        # If OCR returns multiple content morphemes in a single capture,
        # offer the WordSelector so the user can pick multiple terms.
        morphemes = parser.tokenize(text)
        content_tokens = []
        if morphemes:
            for m in morphemes:
                pos = m.part_of_speech()[0]
                if pos in ("助詞", "助動詞", "補助記号", "空白"):
                    continue
                content_tokens.append(m)

        if len(content_tokens) > 1:
            # Build WordEntry list and show selector on main thread
            entries = []
            seen = set()
            for m in content_tokens:
                dict_form = m.dictionary_form()
                surface = m.surface()
                reading = parser._kata_to_hira(m.reading_form())
                if not dict_form or dict_form in seen:
                    continue
                seen.add(dict_form)

                w = Word(
                    surface=surface,
                    dictionary_form=dict_form,
                    reading=reading,
                    pos=m.part_of_speech()[0],
                    meaning=None,
                    full_sentence=text,
                    sentence_furigana=parser.build_sentence_furigana(morphemes),
                    capture_path=filepath,
                )

                dict_result = dictionary.lookup(w)
                if dict_result:
                    w.update_from_dictionary(dict_result)
                else:
                    w.meaning = "(not in dictionary)"
                _finalize_sentence_furigana(w) 

                is_mined = anki.is_already_mined(w.dictionary_form, w.reading)
                entries.append(WordEntry(word=w, is_mined=is_mined, selected=not is_mined))

            if entries:
                confirmed_event = threading.Event()
                confirmed_result = [[]]

                def _on_confirm(selected_list):
                    confirmed_result[0] = selected_list
                    confirmed_event.set()

                show_word_selector(entries, self.main_thread_queue, _on_confirm)
                confirmed_event.wait(timeout=60.0)
                selected = confirmed_result[0]
                if not selected:
                    print("[Process] No tokens selected from multi-token capture.")
                    return

                # Sequentially run card flow for each selected token
                for entry in selected:
                    entry.word.capture_path = filepath
                    card = Card.from_word(entry.word, self.settings)
                    if card.is_valid():
                        self._run_card_flow(card, self.settings, self.main_thread_queue, blocking=True)
                return

        # Default single-word parse path
        parse_result = parser.parse(text)
        if not parse_result:
            logging.warning(f"[Pipeline] Parser failed to parse: {text}")
            return

        logging.info(f"[Pipeline] Parsed: surface={parse_result.get('surface')}, "
                    f"dictionary_form={parse_result.get('dictionary_form')}")

        word = Word(
            surface=parse_result["surface"],
            dictionary_form=parse_result["dictionary_form"],
            reading=parse_result["reading"],
            pos=parse_result["pos"],
            meaning=None,
            full_sentence=text,
            sentence_furigana=parse_result.get("sentence_furigana", ""),
            capture_path=filepath,
        )
 
        dict_result = dictionary.lookup(word)
        if not dict_result:
            logging.warning(f"[Pipeline] Word not in dictionary: {word.surface}")
            print("[Process] Not in dictionary.")
            return
        
        logging.info(f"[Pipeline] Dictionary lookup succeeded for {word.surface}")
        word.update_from_dictionary(dict_result)
        _finalize_sentence_furigana(word)
        
        if not word.is_valid():
            logging.warning(f"[Pipeline] Word validation failed: {word.surface}")
            return
        
        logging.info(f"[Pipeline] Word validation passed: {word.surface}")
 
        card = Card.from_word(word, self.settings)
        if not card.is_valid():
            logging.warning(f"[Pipeline] Card validation failed for {word.surface}")
            return
        
        logging.info(f"[Pipeline] Card created successfully: {word.surface}")
 
        if anki.is_already_mined(card.source_word.dictionary_form,
                                  card.source_word.reading):
            logging.info(f"[Pipeline] Word already mined: {word.surface}")
            print(f"[Process] Already mined: {word.surface}")
            notifier.show_duplicate_toast(
                word.surface, word.reading, self.main_thread_queue)
            return
 
        logging.info(f"[Pipeline] Starting card flow for {word.surface}")
        self._run_card_flow(card, self.settings, self.main_thread_queue)
 
    # ── Multi-word pipeline ───────────────────────────────────────────────────
 
    def _process_multi(self, full_image: Image.Image,
                       regions: List[TextRegion], filepath: str) -> None:
        """
        OCR all regions → parse + dict all → filter mined.db
        → WordSelector UI (non-blocking) → callback runs card flows sequentially.
        """
        print(f"[Multi] OCR-ing {len(regions)} region(s)...")
        ocr_results = _ocr_all_regions(full_image, regions)
        print(f"[Multi] {len(ocr_results)} non-empty result(s).")
 
        if not ocr_results:
            return
 
        entries = _build_word_entries(ocr_results)
        new_count = sum(1 for e in entries if not e.is_mined)
        print(f"[Multi] {len(entries)} unique words — {new_count} new.")
 
        if new_count == 0:
            notifier.show_duplicate_toast(
                "(all words)", "already mined", self.main_thread_queue)
            return
 
        # Show word selector and handle confirmation via callback (non-blocking)
        def on_confirmed(selected: List[WordEntry]):
            """Called when user confirms or closes the selector."""
            if not selected:
                print("[Multi] Nothing selected.")
                return
            
            print(f"[Multi] Mining {len(selected)} word(s) sequentially...")
            for entry in selected:
                entry.word.capture_path = filepath
                card = Card.from_word(entry.word, self.settings)
                if card.is_valid():
                    self._run_card_flow(
                        card, self.settings, self.main_thread_queue, blocking=True
                    )
 
        show_word_selector(entries, self.main_thread_queue, on_confirmed)
 
    # ── Shared card flow (single and multi) ───────────────────────────────────
 
    def _run_card_flow(
        self,
        card:       Card,
        settings:   dict,
        main_queue: queue.Queue,
        blocking:   bool = False,
    ) -> None:
        """
        Starts background audio+image fetch, shows card toast, handles confirm.
 
        Args:
            blocking: If True, blocks until the toast is resolved.
                      Used by _process_multi so cards appear one at a time.
        """
        logging.info(f"[Flow] Showing card toast for {card.source_word.surface}")
        
        audio_future: Future[Optional[AudioFile]]     = Future()
        image_future: Future[List[ImageCandidate]]    = Future()
 
        def _run_audio():
            try:
                logging.info(f"[Flow] Starting audio fetch for {card.source_word.surface}")
                result = asyncio.run(audio.fetch_audio(card.source_word, settings=self.settings))
                if result:
                    logging.info(f"[Flow] Audio fetched successfully")
                else:
                    logging.warning(f"[Flow] Audio fetch returned None")
                audio_future.set_result(result)
            except Exception as e:
                logging.error(f"[Flow] Audio fetch failed: {e}", exc_info=True)
                print(f"[Audio] {e}")
                audio_future.set_result(None)
 
        def _run_img():
            try:
                logging.info(f"[Flow] Starting image fetch for {card.source_word.surface}")
                result = asyncio.run(image_module.fetch_candidates(card.source_word))
                logging.info(f"[Flow] Image fetch returned {len(result)} candidate(s)")
                image_future.set_result(result)
            except Exception as e:
                logging.error(f"[Flow] Image fetch failed: {e}", exc_info=True)
                print(f"[Image] {e}")
                image_future.set_result([])
 
        threading.Thread(target=_run_audio, daemon=True).start()
        threading.Thread(target=_run_img,   daemon=True).start()
 
        done_event = threading.Event()
 
        def on_confirm():
            logging.info(f"[Flow] User confirmed card for {card.source_word.surface}")
            try:
                candidates = image_future.result(timeout=8.0)
            except Exception as e:
                logging.warning(f"[Flow] Image future timeout or error: {e}")
                candidates = []
 
            picked_event  = threading.Event()
            picked_result: List[Optional[ImageCandidate]] = [None]
 
            def on_img(c):
                if c:
                    logging.info(f"[Flow] Image selected by user")
                else:
                    logging.info(f"[Flow] User skipped image selection")
                picked_result[0] = c
                picked_event.set()
 
            logging.info(f"[Flow] Showing image picker with {len(candidates)} candidates")
            image_module.show_image_picker(candidates, main_queue, on_img)
            picked_event.wait(timeout=60.0)
 
            image_filename = None
            if picked_result[0]:
                try:
                    logging.info(f"[Flow] Saving selected image")
                    image_filename = image_module.save_to_media(
                        picked_result[0], card.source_word, settings)
                    logging.info(f"[Flow] Image saved: {image_filename}")
                except Exception as e:
                    logging.error(f"[Flow] Image save failed: {e}", exc_info=True)
 
            logging.info(f"[Flow] Adding card to Anki")
            success, message, note_id = anki.add_card(
                card, settings, image_filename=image_filename)
 
            if success:
                logging.info(f"[Flow] Card added to Anki successfully: {message}")
                print(f"[Anki] {message}")
                notifier.show_success_toast(card.source_word.surface, main_queue)
            else:
                logging.error(f"[Flow] Card addition failed: {message}")
                print(f"[Anki] Failed: {message}")
 
            def _apply_audio():
                try:
                    af = audio_future.result(timeout=30.0)
                except Exception as e:
                    logging.warning(f"[Flow] Audio future timeout or error: {e}")
                    af = None
                if af and note_id:
                    try:
                        logging.info(f"[Flow] Applying audio to card note_id={note_id}")
                        anki.update_card_audio(note_id, af)
                        logging.info(f"[Flow] Audio applied successfully")
                    except Exception as e:
                        logging.error(f"[Flow] Audio application failed: {e}", exc_info=True)
 
            threading.Thread(target=_apply_audio, daemon=True).start()
            done_event.set()
 
        def on_discard():
            logging.info(f"[Flow] User discarded card: {card.source_word.surface}")
            print(f"[Flow] Discarded: {card.source_word.surface}")
            done_event.set()
 
        logging.info(f"[Flow] Posting card toast to main queue")
        notifier.show_card_toast(
            card.source_word, settings, main_queue,
            on_confirm=on_confirm, on_discard=on_discard,
        )
 
        if blocking:
            logging.info(f"[Flow] Blocking mode: waiting for card resolution")
            done_event.wait(timeout=120.0)
            logging.info(f"[Flow] Card resolution complete or timed out")