import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import queue
import logging

from core.settings import DEFAULT_SETTINGS

_TK_ROOT = None


def preload_tkinter():
    global _TK_ROOT
    if _TK_ROOT is None:
        _TK_ROOT = tk.Tk()
        _TK_ROOT.withdraw()
        _TK_ROOT.update()


class SettingsWindow:
    _instance = None

    @classmethod
    def show_window(cls, settings):
        logging.info("[Settings] show_window called")
        if cls._instance is not None:
            logging.info("[Settings] Existing window found, lifting to front")
            try:
                cls._instance.root.lift()
                cls._instance.root.focus_force()
                logging.info("[Settings] Window lifted successfully")
            except Exception as e:
                logging.error(f"[Settings] Failed to lift window: {e}", exc_info=True)
            return

        logging.info("[Settings] Creating new SettingsWindow instance")
        try:
            cls._instance = SettingsWindow(settings)
            logging.info("[Settings] SettingsWindow instance created")
            # Don't run a blocking show loop here; main loop will pump updates
            logging.info("[Settings] Window created and awaiting main loop pump")
        except Exception as e:
            logging.error(f"[Settings] Failed to create or show window: {e}", exc_info=True)
            cls._instance = None

    def __init__(self, settings):
        logging.info("[Settings] __init__ called")
        preload_tkinter()
        self.settings = settings
        self._event_queue = queue.Queue()  # Thread-safe queue for background thread communication
        logging.debug(f"[Settings] Creating Toplevel window from root: {_TK_ROOT}")
        self.root = tk.Toplevel(_TK_ROOT)
        self.root.title("JAM Settings")
        self.root.resizable(False, False)
        self.root.geometry("520x420")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        
        logging.info(f"[Settings] Window created: {self.root}")
        self._vars = {}
        self._build_ui()
        logging.info("[Settings] UI built")

    def _build_ui(self):
        padding = 10
        frame = ttk.Frame(self.root, padding=padding)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0
        self._add_label(frame, "Capture Hotkey:", row)
        self._vars["capture_combo"] = tk.StringVar(value=" ".join(self.settings.get("capture_combo", [])))
        self._add_entry(frame, self._vars["capture_combo"], row)
        row += 1

        self._add_label(frame, "Capture Mode:", row)
        self._vars["capture_mode"] = tk.StringVar(value=self.settings.get("capture_mode", "bbox"))
        combo = ttk.Combobox(frame, textvariable=self._vars["capture_mode"], state="readonly")
        combo["values"] = ["bbox", "mouse"]
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


def show_settings_window(settings, main_thread_queue=None):
    """Open settings window. If main_thread_queue provided, queue to main thread (safer for Tkinter)."""
    logging.info("[Settings] show_settings_window() called")
    
    def _create_window():
        try:
            logging.info("[Settings] Creating window on main thread")
            SettingsWindow.show_window(settings)
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
    """Pump a single iteration of the settings window event loop if open.
    Designed to be called from the main thread (main loop)."""
    win = SettingsWindow._instance
    if win is None:
        return
    try:
        # Handle background-thread events first
        try:
            event_type, event_data = win._event_queue.get_nowait()
            if event_type == "save_success":
                logging.info("[Settings] Save success event received")
                messagebox.showinfo("JAM Settings", "Settings saved successfully.")
                win._close()
                return
            elif event_type == "save_error":
                logging.error(f"[Settings] Save error event received: {event_data}")
                messagebox.showerror("Error saving settings", event_data)
        except queue.Empty:
            pass

        win.root.update()
    except tk.TclError:
        logging.info("[Settings] Window closed (TclError during pump)")
        try:
            win.root.destroy()
        except Exception:
            pass
        SettingsWindow._instance = None
    except Exception as e:
        logging.error(f"[Settings] Error while pumping window: {e}", exc_info=True)
