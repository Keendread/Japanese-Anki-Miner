import logging
import threading
from typing import Any, Optional

from PIL import Image

from core.screen import capture_full_screen, save_capture
from core.pipeline import process_multi, wait_for_ready
from core.input import is_held
from core.signals import signals


class CaptureController:
    _POLL_INTERVAL = 0.02   # 20 ms — 50 polls/s, negligible CPU

    def __init__(self, combo: set, settings: Any,
                 main_thread_queue: Optional[Any] = None) -> None:
        self.combo              = combo   # set of VK ints from input.py
        self.settings           = settings
        self.main_thread_queue  = main_thread_queue  
        self.combo_active       = False
        self._bbox_open         = False
        self._last_trigger_time = 0.0
        self._recording         = False
        self._stop_event        = threading.Event()
        self._poll_thread       = threading.Thread(
            target=self._poll_loop, daemon=True, name="JAM-hotkey-poll"
        )

    # ── Hotkey polling ────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        import time
        print("[Capture] Polling loop started (fullscreen-safe mode)")

        while not self._stop_event.is_set():
            time.sleep(self._POLL_INTERVAL)

            if self._recording or not self.combo:
                self.combo_active = False
                continue

            all_held = all(is_held(vk) for vk in self.combo)

            if all_held:
                if not self.combo_active:
                    now = time.time()
                    if now - self._last_trigger_time < 0.5:
                        continue   # throttle rapid re-triggers
                    self._last_trigger_time = now
                    self.combo_active = True
                    threading.Thread(
                        target=self.on_trigger, daemon=True, name="JAM-trigger"
                    ).start()
            else:
                self.combo_active = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_recording(self, recording: bool) -> None:
        self._recording = recording

    def set_combo(self, new_combo: set) -> None:
        self.combo = new_combo

    def start(self) -> None:
        print("[Capture] Running")
        self._stop_event.clear()
        self._poll_thread.start()

    def join(self) -> None:
        self._poll_thread.join()

    def stop(self) -> None:
        print("[Capture] Stopped")
        self._stop_event.set()

    # ── Trigger dispatch ──────────────────────────────────────────────────────

    def on_trigger(self) -> None:
        mode = self.settings.get("capture_mode", "bbox")
        print(f"[Capture] Triggered — mode: {mode}")
        logging.info(f"[Capture] Hotkey triggered, mode: {mode}")

        dispatch = {
            "bbox":   self._trigger_bbox,
            "screen": self._trigger_screen,
        }
        fn = dispatch.get(mode)
        if fn:
            fn()
        else:
            logging.error(f"[Capture] Unknown mode: {mode}")
            print(f"[Capture] Unknown mode '{mode}', falling back to bbox.")
            self._trigger_bbox()

    # ── BBox mode ─────────────────────────────────────────────────────────────

    def _trigger_bbox(self) -> None:
        if self._bbox_open:
            return
        signals.run_on_main_thread.emit(self._open_bbox_on_main_thread)

    def _open_bbox_on_main_thread(self) -> None:
        self._bbox_open = True
        try:
            from ui.capture_overlay import open_bbox_overlay
            open_bbox_overlay(self._on_bbox_capture)
        except Exception as e:
            print(f"[BBox] Overlay failed: {e}")
        finally:
            self._bbox_open = False

    def _on_bbox_capture(self, image: Image.Image) -> None:
        def process():
            try:
                filepath = save_capture(image)
                if not wait_for_ready():
                    return

                process_multi(image, filepath, self.settings, self.main_thread_queue)

            except Exception as e:
                logging.error(f"[BBox] Post-capture failed: {e}", exc_info=True)
                print(f"[BBox] Post-capture failed: {e}")

        threading.Thread(target=process, daemon=True).start()

    # ── Screen mode ───────────────────────────────────────────────────────────

    def _trigger_screen(self) -> None:
        def capture():
            try:
                if not wait_for_ready():
                    return
                print("[Screen] Capturing full screen...")
                full     = capture_full_screen()
                filepath = save_capture(full)
                print(f"[Screen] {full.width}x{full.height}px")

                process_multi(full, filepath, self.settings, self.main_thread_queue)

            except Exception as e:
                print(f"[Screen] Failed: {e}")
                logging.error(f"[Screen] Failed: {e}", exc_info=True)

        threading.Thread(target=capture, daemon=True).start()