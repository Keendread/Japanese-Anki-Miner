import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import queue
import logging
import ctypes

from core.settings import DEFAULT_SETTINGS

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

_TK_ROOT = None

def rescale(x):
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except Exception:
        return x

def preload_tkinter():
    global _TK_ROOT
    if _TK_ROOT is None:
        _TK_ROOT = tk.Tk()
        _TK_ROOT.withdraw()
        _TK_ROOT.update()


class SettingsWindow:
    _instance = None

    @classmethod
    def show_window(cls, settings, capture=None):
        logging.info("[Settings] show_window called")
        if cls._instance is not None:
            logging.info("[Settings] Existing window found, lifting to front")
            try:
                cls._instance.root.lift()
                cls._instance.root.focus_force()
            except Exception as e:
                logging.error(f"[Settings] Failed to lift window: {e}", exc_info=True)
            return

        logging.info("[Settings] Creating new SettingsWindow instance")
        try:
            cls._instance = SettingsWindow(settings, capture=capture)
            logging.info("[Settings] SettingsWindow instance created")
            # Don't run a blocking show loop here; main loop will pump updates
            logging.info("[Settings] Window created and awaiting main loop pump")
        except Exception as e:
            logging.error(f"[Settings] Failed to create or show window: {e}", exc_info=True)
            cls._instance = None

    def __init__(self, settings, capture=None):
        logging.info("[Settings] __init__ called")
        preload_tkinter()
        self.settings = settings
        self._capture = capture
        self._event_queue = queue.Queue()  # Thread-safe queue for background thread communication
        logging.debug(f"[Settings] Creating Toplevel window from root: {_TK_ROOT}")
        self.root = tk.Toplevel(_TK_ROOT)
        self.root.title("JAM Settings")
        self.root.resizable(True, True)
        w = rescale(520)
        h = rescale(420)
        self.root.geometry(f"{w}x{h}")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._currently_held = set()
        
        logging.info(f"[Settings] Window created: {self.root}")
        self._vars = {}
        self._build_ui()
        logging.info("[Settings] UI built")

    def _build_ui(self):
        padding = 10
        
        # ── Scrollable container ──────────────────────────────────────────────
        container = tk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = ttk.Frame(canvas, padding=padding)
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<MouseWheel>", _on_mousewheel)
        frame.bind("<MouseWheel>", _on_mousewheel)

        # ── Settings rows ──────────────────────────
        row = 0
        self._add_label(frame, "Capture Hotkey:", row)
        self._vars["capture_combo"] = tk.StringVar(value=" ".join(self.settings.get("capture_combo", [])))
        
        # Hotkey recorder button
        self._hotkey_btn = ttk.Button(
            frame,
            text=self._vars["capture_combo"].get() or "Click to set hotkey",
            command=self._start_hotkey_recording,
        )
        self._hotkey_btn.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(0, padding), pady=4)
        self._recording_hotkey = False
        self._recorded_keys = []
        row += 1

        self._add_label(frame, "Capture Mode:", row)
        self._vars["capture_mode"] = tk.StringVar(value=self.settings.get("capture_mode", "bbox"))
        combo = ttk.Combobox(frame, textvariable=self._vars["capture_mode"], state="readonly")
        combo["values"] = ["bbox", "mouse", "screen"]
        combo.grid(row=row, column=1, sticky="ew", padx=(0, padding), pady=4)
        row += 1

        self._add_label(frame, "Capture Width:", row)
        self._vars["capture_width"] = tk.StringVar(value=str(self.settings.get("capture_width", 200)))
        self._add_entry(frame, self._vars["capture_width"], row)
        row += 1

        self._add_label(frame, "Capture Height:", row)
        self._vars["capture_height"] = tk.StringVar(value=str(self.settings.get("capture_height", 60)))
        self._add_entry(frame, self._vars["capture_height"], row)
        row += 1

        self._add_separator(frame, row)
        row += 1
        
        self._add_label(frame, "VOICEVOX Voice:", row)
        # Build display names: "Zundamon (ずんだもん)"
        from core.audio import VOICEVOX_SPEAKERS
        self._speaker_options = VOICEVOX_SPEAKERS
        speaker_display = [
            f"{s['english']} ({s['japanese']})" for s in self._speaker_options
        ]
        current_id = self.settings.get("voicevox_speaker_id", 3)
        current_idx = next(
            (i for i, s in enumerate(self._speaker_options) if s["id"] == current_id),
            0
        )
        self._vars["voicevox_speaker_id"] = tk.StringVar(
            value=speaker_display[current_idx]
        )
        voice_combo = ttk.Combobox(
            frame,
            textvariable=self._vars["voicevox_speaker_id"],
            values=speaker_display,
            state="readonly",
            width=30,
        )
        voice_combo.grid(row=row, column=1, sticky="ew", padx=(0, padding), pady=4)

        preview_btn = ttk.Button(
            frame,
            text="▶ Preview",
            command=self._preview_voice,
        )
        preview_btn.grid(row=row, column=2, sticky="ew", padx=(0, padding), pady=4)
        row += 1
        
        self._add_separator(frame, row)
        row += 1

        self._add_label(frame, "Anki Deck:", row)
        self._vars["anki_deck"] = tk.StringVar(value=self.settings.get("anki_deck", DEFAULT_SETTINGS["anki_deck"]))
        self._add_entry(frame, self._vars["anki_deck"], row)
        row += 1

        self._add_label(frame, "Anki Note Type:", row)
        self._vars["anki_note_type"] = tk.StringVar(value=self.settings.get("anki_note_type", DEFAULT_SETTINGS["anki_note_type"]))
        self._add_entry(frame, self._vars["anki_note_type"], row)
        row += 1

        self._add_label(frame, "Anki Media Path:", row)
        self._vars["anki_media_path"] = tk.StringVar(value=self.settings.get("anki_media_path", DEFAULT_SETTINGS["anki_media_path"]))
        self._add_entry(frame, self._vars["anki_media_path"], row)
        browse = ttk.Button(frame, text="Browse", command=self._browse_media_path)
        browse.grid(row=row, column=2, sticky="ew", padx=(0, padding), pady=4)
        row += 1

        self._add_label(frame, "Anki Misc Info:", row)
        self._vars["anki_misc_info"] = tk.StringVar(value=self.settings.get("anki_misc_info", DEFAULT_SETTINGS["anki_misc_info"]))
        self._add_entry(frame, self._vars["anki_misc_info"], row)
        row += 1

        self._add_label(frame, "Anki Profile:", row)
        self._vars["anki_profile"] = tk.StringVar(value=self.settings.get("anki_profile", DEFAULT_SETTINGS["anki_profile"]))
        self._add_entry(frame, self._vars["anki_profile"], row)
        row += 1

        self._add_separator(frame, row)
        row += 1

        note = tk.Label(
            frame,
            text="Enter hotkey parts separated by spaces, e.g. shift a or ctrl alt c.",
            wraplength=480,
            justify=tk.LEFT,
            foreground="#555555"
        )
        note.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        save_btn = ttk.Button(button_frame, text="Save", command=self._save)
        save_btn.grid(row=0, column=0, sticky="ew", padx=3)
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self._close)
        cancel_btn.grid(row=0, column=1, sticky="ew", padx=3)
        reset_btn = ttk.Button(button_frame, text="Reset Defaults", command=self._reset_defaults)
        reset_btn.grid(row=0, column=2, sticky="ew", padx=3)

        frame.columnconfigure(1, weight=1)

    def _add_label(self, parent, text, row):
        label = ttk.Label(parent, text=text)
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)

    def _add_entry(self, parent, var, row, placeholder=None):
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=4)
        if placeholder and not var.get():
            entry.insert(0, placeholder)

    def _add_separator(self, parent, row):
        sep = ttk.Separator(parent, orient=tk.HORIZONTAL)
        sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)

    def _browse_media_path(self):
        directory = filedialog.askdirectory(
            title="Select Anki media folder",
            initialdir=self._vars["anki_media_path"].get() or os.path.expanduser("~"),
        )
        if directory:
            self._vars["anki_media_path"].set(directory)

    def _parse_capture_combo(self, raw_value):
        parts = [part.strip() for part in raw_value.replace(",", " ").split() if part.strip()]
        if not parts:
            raise ValueError("Capture hotkey cannot be empty")
        return parts

    def _save(self):
        """Validate settings and spawn background thread to save (avoid blocking main thread)."""
        try:
            combo = self._parse_capture_combo(self._vars["capture_combo"].get())
            mode = self._vars["capture_mode"].get()
            width = int(self._vars["capture_width"].get())
            height = int(self._vars["capture_height"].get())
            if width <= 0 or height <= 0:
                raise ValueError("Width and height must be positive")

            selected_voice = self._vars["voicevox_speaker_id"].get()
            from core.audio import VOICEVOX_SPEAKERS
            speaker = next(
                (s for s in VOICEVOX_SPEAKERS
                 if f"{s['english']} ({s['japanese']})" == selected_voice),
                None
            )

            updated = {
                "capture_combo": combo,
                "capture_mode": mode,
                "capture_width": width,
                "capture_height": height,
                "anki_deck": self._vars["anki_deck"].get().strip(),
                "anki_note_type": self._vars["anki_note_type"].get().strip(),
                "anki_misc_info": self._vars["anki_misc_info"].get().strip(),
                "anki_media_path": self._vars["anki_media_path"].get().strip(),
                "anki_profile": self._vars["anki_profile"].get().strip(),
                "voicevox_speaker_id": speaker["id"] if speaker else 3,
            }

            # Spawn background thread to save settings (don't block main thread on I/O)
            def save_in_background():
                logging.info("[Settings] Background save thread started")
                try:
                    for key, value in updated.items():
                        self.settings.set(key, value)
                    logging.info("[Settings] Settings saved successfully")
                    # Signal success via queue (show() loop will handle it)
                    self._event_queue.put(("save_success", None))
                except Exception as e:
                    logging.error(f"[Settings] Background save failed: {e}", exc_info=True)
                    # Signal error via queue
                    self._event_queue.put(("save_error", str(e)))

            threading.Thread(target=save_in_background, daemon=True).start()
            
        except ValueError as exc:
            logging.error(f"[Settings] Validation failed: {exc}")
            messagebox.showerror("Invalid settings", str(exc))
        except Exception as exc:
            logging.error(f"[Settings] Save failed: {exc}", exc_info=True)
            messagebox.showerror("Error saving settings", str(exc))

    def _reset_defaults(self):
        for key, value in DEFAULT_SETTINGS.items():
            if key in self._vars:
                self._vars[key].set(str(value) if not isinstance(value, list) else " ".join(value))
        # Sync the hotkey button text to the reset value
        default_combo = DEFAULT_SETTINGS.get("capture_combo", [])
        combo_str = " ".join(default_combo) if isinstance(default_combo, list) else str(default_combo)
        self._hotkey_btn.config(text=combo_str or "Click to set hotkey")

    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        finally:
            SettingsWindow._instance = None

    def show(self):
        """Deprecated: legacy blocking loop. Use `pump()` from main loop instead."""
        logging.warning("[Settings] show() called directly — this is deprecated. Use main loop pump.")
        # Provide a simple fallback: pump until window closes
        import time
        try:
            while SettingsWindow._instance is self:
                self.pump()
                time.sleep(0.05)
        except Exception:
            pass
        
    def _start_hotkey_recording(self):
        if self._recording_hotkey:
            return
        self._recording_hotkey = True
        self._recorded_keys = []
        self._currently_held = set()
        if self._capture:
            self._capture.set_recording(True)
        self._hotkey_btn.config(text="Press keys… (Esc to cancel)")
        self.root.bind("<KeyPress>", self._on_hotkey_keypress)
        self.root.bind("<KeyRelease>", self._on_hotkey_keyrelease)
        self.root.focus_set()

    def _on_hotkey_keypress(self, event):
        if not self._recording_hotkey:
            return

        # Esc cancels immediately
        if event.keysym == "Escape":
            self._stop_hotkey_recording(cancelled=True)
            return

        key = self._tkkey_to_pynput(event)
        if key is None:
            return

        self._currently_held.add(key)

        # Build ordered combo: modifiers first, then regular keys
        modifier_keys = {"shift", "ctrl", "alt", "cmd", "caps_lock"}
        modifiers = [k for k in self._recorded_keys if k in modifier_keys]
        non_modifiers = [k for k in self._recorded_keys if k not in modifier_keys]

        if key not in self._recorded_keys:
            if key in modifier_keys:
                modifiers.append(key)
            else:
                non_modifiers.append(key)

        self._recorded_keys = modifiers + non_modifiers
        self._hotkey_btn.config(text=" + ".join(self._recorded_keys) + "…")

    def _on_hotkey_keyrelease(self, event):
        if not self._recording_hotkey:
            return

        key = self._tkkey_to_pynput(event)
        if key:
            self._currently_held.discard(key)

        # Only finalize when ALL keys have been released and we have a valid combo
        modifier_keys = {"shift", "ctrl", "alt", "cmd", "caps_lock"}
        has_non_modifier = any(k not in modifier_keys for k in self._recorded_keys)

        if len(self._currently_held) == 0 and self._recorded_keys and has_non_modifier:
            self._stop_hotkey_recording(cancelled=False)

    def _stop_hotkey_recording(self, cancelled=False):
        self._recording_hotkey = False
        self.root.unbind("<KeyPress>")
        self.root.unbind("<KeyRelease>")
        if self._capture:
            self._capture.set_recording(False)
        if cancelled or not self._recorded_keys:
            self._hotkey_btn.config(
                text=self._vars["capture_combo"].get() or "Click to set hotkey"
            )
        else:
            combo_str = " ".join(self._recorded_keys)
            self._vars["capture_combo"].set(combo_str)
            self._hotkey_btn.config(text=combo_str)
        self._recorded_keys = []
        self._currently_held = set()
        
    def _tkkey_to_pynput(self, event) -> str:
            """Convert a Tkinter key event to a pynput-compatible string."""
            special_map = {
                "shift":        "shift",
                "shift_l":      "shift",
                "shift_r":      "shift",
                "control":      "ctrl",
                "control_l":    "ctrl",
                "control_r":    "ctrl",
                "alt":          "alt",
                "alt_l":        "alt",
                "alt_r":        "alt",
                "super":        "cmd",
                "super_l":      "cmd",
                "super_r":      "cmd",
                "caps_lock":    "caps_lock",
                "tab":          "tab",
                "return":       "enter",
                "space":        "space",
                "backspace":    "backspace",
                "delete":       "delete",
                "home":         "home",
                "end":          "end",
                "prior":        "page_up",
                "next":         "page_down",
                "up":           "up",
                "down":         "down",
                "left":         "left",
                "right":        "right",
                "f1":  "f1",  "f2":  "f2",  "f3":  "f3",  "f4":  "f4",
                "f5":  "f5",  "f6":  "f6",  "f7":  "f7",  "f8":  "f8",
                "f9":  "f9",  "f10": "f10", "f11": "f11", "f12": "f12",
            }
            sym = event.keysym.lower()
            if sym in special_map:
                return special_map[sym]

            # Use keysym directly for single letter/digit keys — this works even
            # when Ctrl is held and event.char becomes a control character like \x03
            if len(sym) == 1 and sym.isalnum():
                return sym

            # Fallback: printable char from event.char
            if event.char and len(event.char) == 1 and event.char.isprintable():
                return event.char.lower()

            return None
        
    def _preview_voice(self):
        """Play a short preview of the selected voice."""
        selected = self._vars["voicevox_speaker_id"].get()
        speaker = next(
            (s for s in self._speaker_options
             if f"{s['english']} ({s['japanese']})" == selected),
            None
        )
        if speaker is None:
            return

        import asyncio, threading, io
        speaker_id = speaker["id"]

        def _play():
            try:
                from core.audio import preview_speaker
                import asyncio
                audio_bytes = asyncio.run(preview_speaker(speaker_id))
                if audio_bytes is None:
                    print("[Settings] Preview failed — is VOICEVOX running?")
                    return
                # Play using winsound (Windows built-in, no extra deps)
                import winsound, tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_bytes)
                    tmp_path = f.name
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
                os.unlink(tmp_path)
            except Exception as e:
                print(f"[Settings] Voice preview error: {e}")

        threading.Thread(target=_play, daemon=True).start()


def show_settings_window(settings, main_thread_queue=None, capture=None):
    """Open settings window. If main_thread_queue provided, queue to main thread (safer for Tkinter)."""
    logging.info("[Settings] show_settings_window() called")
    
    def _create_window():
        try:
            logging.info("[Settings] Creating window on main thread")
            SettingsWindow.show_window(settings, capture=capture)
            logging.info("[Settings] Window creation completed")
        except Exception as e:
            logging.error(f"[Settings] Failed to create window: {e}", exc_info=True)
    
    # If main_thread_queue is available, use it to ensure window creation on main thread
    if main_thread_queue is not None:
        logging.info("[Settings] Queueing window creation to main thread")
        main_thread_queue.put(_create_window)
    else:
        # Fallback: spawn background thread (less safe but works if no queue available)
        logging.warning("[Settings] No main_thread_queue provided, spawning background thread")
        thread = threading.Thread(target=_create_window, daemon=True)
        thread.start()


def pump_pending_window_once():
    win = SettingsWindow._instance
    if win is None:
        return
    try:
        try:
            event_type, event_data = win._event_queue.get_nowait()
            if event_type == "save_success":
                logging.info("[Settings] Save success event received")
                messagebox.showinfo("JAM Settings", "Settings saved successfully.", parent=win.root)
                win._close()
                return
            elif event_type == "save_error":
                logging.error(f"[Settings] Save error event received: {event_data}")
                messagebox.showerror("Error saving settings", event_data, parent=win.root)
        except queue.Empty:
            pass
    except tk.TclError:
        logging.info("[Settings] Window closed (TclError during pump)")
        try:
            win.root.destroy()
        except Exception:
            pass
        SettingsWindow._instance = None
    except Exception as e:
        logging.error(f"[Settings] Error while pumping window: {e}", exc_info=True)
