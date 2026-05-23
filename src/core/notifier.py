# Module for card preview toast notification

import tkinter as tk
import threading
import ctypes
import logging
from typing import Optional
from src.models.word import Word

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()


def _ensure_tk_root():
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root


def _create_toplevel(title: str) -> tk.Toplevel:
    root = _ensure_tk_root()
    window = tk.Toplevel(root)
    window.title(title)
    window.resizable(False, False)
    window.attributes("-topmost", True)
    window.overrideredirect(True)
    return window


def rescale(x):
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except Exception:
        return x


# ── Loading progress toast ────────────────────────────────────────────────────

class LoadingToast:
    """
    Persistent toast shown during startup.
    Displays three checklist rows (OCR, Parser, Dictionary) and ticks them off
    in real-time as each threading.Event fires. Auto-dismisses once all three
    are ready, then calls on_all_ready() on the main thread via the queue.

    Usage (from a background thread — never call Tk directly from there):
        toast = LoadingToast(main_thread_queue, on_all_ready=show_ready_toast)
        main_thread_queue.put(toast.create)   # build the window on main thread
        toast.start_watchers(ocr_event, parser_event, dict_event)
    """

    _W = rescale(320)
    _H = rescale(130)
    _PAD = rescale(14)

    # Label text for each row
    _ROWS = [
        ("ocr",    "OCR model"),
        ("parser", "Parser / tokenizer"),
        ("dict",   "Dictionary"),
    ]

    # Colours
    _BG          = "#1a1a2a"
    _BORDER      = "#333366"
    _PENDING_FG  = "#555577"
    _LOADING_FG  = "#7b9fff"
    _DONE_FG     = "#6bff6b"
    _TITLE_FG    = "#7b9fff"

    def __init__(self, main_thread_queue: "queue.Queue", ocr_event,
                 parser_event, dict_event, on_all_ready=None):
        self._queue        = main_thread_queue
        self._on_all_ready = on_all_ready
        self._root: Optional[tk.Toplevel] = None
        self._labels: dict[str, tk.Label] = {}
        self._done: dict[str, bool] = {k: False for k, _ in self._ROWS}
        # Store events at construction time so create() can both check
        # already-fired events AND start watchers for pending ones.
        self._events = {
            "ocr":    ocr_event,
            "parser": parser_event,
            "dict":   dict_event,
        }
        self.running = True

    # ── Main-thread methods (called via queue) ────────────────────────────────

    def create(self):
        """Build and show the window. Must run on the main thread."""
        self._root = _create_toplevel("JAM — Starting up")
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x  = sw - self._W - rescale(12)
        y  = sh - self._H - rescale(60)
        self._root.geometry(f"{self._W}x{self._H}+{x}+{y}")

        outer = tk.Frame(
            self._root,
            bg=self._BG,
            highlightbackground=self._BORDER,
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text="✦ JAM is starting up…",
            font=("Segoe UI", 10, "bold"),
            bg=self._BG, fg=self._TITLE_FG,
            anchor="w", padx=self._PAD, pady=rescale(8),
        ).pack(fill=tk.X)

        tk.Frame(outer, bg=self._BORDER, height=1).pack(fill=tk.X)

        rows_frame = tk.Frame(outer, bg=self._BG)
        rows_frame.pack(fill=tk.X, padx=self._PAD, pady=rescale(6))

        for key, label_text in self._ROWS:
            row = tk.Frame(rows_frame, bg=self._BG)
            row.pack(fill=tk.X, pady=rescale(2))

            # Static label
            tk.Label(
                row,
                text=label_text,
                font=("Segoe UI", 9),
                bg=self._BG, fg=self._LOADING_FG,
                anchor="w", width=rescale(22),
            ).pack(side=tk.LEFT)

            # Dynamic status label — updated by _set_status()
            status = tk.Label(
                row,
                text="loading…",
                font=("Segoe UI", 9),
                bg=self._BG, fg=self._PENDING_FG,
                anchor="e",
            )
            status.pack(side=tk.RIGHT)
            self._labels[key] = status

        # Immediately tick any subsystems that already finished before the
        # window was created (parser and dictionary are usually fast and fire
        # before the main thread gets around to building this UI).
        for key, event in self._events.items():
            if event.is_set():
                self._set_status(key, done=True)

        self._root.update_idletasks()

        # Start watcher threads only for subsystems still loading.
        # Doing this here (inside create, on the main thread) guarantees the
        # window and all label widgets exist before any watcher can post an
        # update — so status updates never arrive before the UI is ready.
        for key, event in self._events.items():
            if not event.is_set():
                threading.Thread(
                    target=self._watch,
                    args=(key, event),
                    daemon=True,
                    name=f"jam-loading-watcher-{key}",
                ).start()

    def _set_status(self, key: str, done: bool):
        """Update one row. Must run on the main thread (called via queue)."""
        lbl = self._labels.get(key)
        if lbl is None:
            return
        if done:
            lbl.config(text="✓  ready", fg=self._DONE_FG)
        else:
            lbl.config(text="loading…", fg=self._PENDING_FG)
        self._done[key] = done
        try:
            self._root.update_idletasks()
        except tk.TclError:
            pass

        if all(self._done.values()):
            # Brief pause so the user sees all three ticks, then dismiss.
            self._root.after(800, self._dismiss)

    def _dismiss(self):
        """Close the window and fire the ready callback. Main thread only."""
        self.running = False
        try:
            self._root.destroy()
        except Exception:
            pass
        if self._on_all_ready:
            self._on_all_ready()

    def pump(self):
        """Called from the main loop each cycle (like other toasts)."""
        if not self.running:
            return
        try:
            self._root.update_idletasks()
        except tk.TclError:
            self.running = False

    # ── Background watcher threads ────────────────────────────────────────────

    def _watch(self, key: str, event):
        event.wait()   # block until the subsystem signals ready
        # Post the UI update back to the main thread
        self._queue.put(lambda k=key: self._set_status(k, done=True))


# ── Active loading toast (pumped by main loop) ────────────────────────────────

_LOADING_TOAST: Optional[LoadingToast] = None


def pump_loading_toast_once():
    """Called from main loop each cycle to drive the loading progress toast."""
    global _LOADING_TOAST
    toast = _LOADING_TOAST
    if toast is None:
        return
    try:
        toast.pump()
        if not toast.running:
            _LOADING_TOAST = None
    except Exception as e:
        logging.error(f"[Notifier] Loading toast pump error: {e}")
        _LOADING_TOAST = None


def show_loading_toast(main_thread_queue, ocr_event, parser_event, dict_event,
                       on_all_ready=None):
    """
    Create and register the startup loading toast.
    Safe to call from any thread.

    Args:
        main_thread_queue:  The queue used to post tasks to the main thread.
        ocr_event:          threading.Event set when OCR model is ready.
        parser_event:       threading.Event set when parser is ready.
        dict_event:         threading.Event set when dictionary is ready.
        on_all_ready:       Optional callable invoked on the main thread when
                            all three subsystems are ready (e.g. show_ready_toast).
    """
    global _LOADING_TOAST
    toast = LoadingToast(
        main_thread_queue,
        ocr_event=ocr_event,
        parser_event=parser_event,
        dict_event=dict_event,
        on_all_ready=on_all_ready,
    )
    _LOADING_TOAST = toast
    # Post create() to the main thread queue. create() will both build the UI
    # AND start the watcher threads — guaranteeing the window exists first.
    main_thread_queue.put(toast.create)


# ── CardToast ─────────────────────────────────────────────────────────────────

class CardToast:
    WINDOW_WIDTH  = rescale(380)
    WINDOW_HEIGHT = rescale(320)
    PADDING       = rescale(16)
    MARGIN        = rescale(12)

    def __init__(self, payload: Word, settings, on_confirm, on_discard):
        self.payload    = payload
        self.settings   = settings
        self.on_confirm = on_confirm
        self.on_discard = on_discard
        self.running    = True

        self.root = _create_toplevel("JAM - Card Preview")
        self._build_ui()
        self._position_window()
        self.root.update()
        self.root.lift()
        self.root.focus_force()

    def _position_window(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - self.WINDOW_WIDTH  - self.MARGIN
        y  = sh - self.WINDOW_HEIGHT - self.MARGIN - 48
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

    def _build_ui(self):
        payload = self.payload

        surface        = payload.surface
        reading        = payload.reading
        pos            = payload.pos
        main_def       = payload.meaning
        sentence       = payload.full_sentence
        pitch_pattern  = payload.pitch_pattern
        pitch_category = payload.pitch_category
        frequency_rank = payload.frequency_rank
        jlpt_level     = payload.jlpt_level
        examples       = payload.example_sentences or []

        outer = tk.Frame(
            self.root,
            bg="#1e1e1e",
            highlightbackground="#444444",
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        p = self.PADDING

        header = tk.Frame(outer, bg="#2a2a2a")
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=f"{surface}　{reading}",
            font=("Segoe UI", 14, "bold"),
            bg="#2a2a2a", fg="#ffffff",
            anchor="w", padx=p, pady=rescale(8),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            header,
            text="✕",
            font=("Segoe UI", 10),
            bg="#2a2a2a", fg="#888888",
            bd=0, padx=rescale(8),
            cursor="hand2",
            command=self._discard,
        ).pack(side=tk.RIGHT, pady=rescale(4))

        meta_parts = []
        if pos:
            meta_parts.append(pos)
        if pitch_pattern is not None:
            cat = f" {pitch_category}" if pitch_category else ""
            meta_parts.append(f"pitch {pitch_pattern}{cat}")
        if frequency_rank:
            meta_parts.append(f"{frequency_rank}")
        if jlpt_level:
            meta_parts.append(jlpt_level)

        if meta_parts:
            tk.Label(
                outer,
                text="  ·  ".join(meta_parts),
                font=("Segoe UI", 8),
                bg="#1e1e1e", fg="#888888",
                anchor="w", padx=p, pady=rescale(4),
            ).pack(fill=tk.X)

        tk.Frame(outer, bg="#333333", height=1).pack(fill=tk.X, padx=p)

        tk.Label(
            outer,
            text=main_def or "(no definition)",
            font=("Segoe UI", 10),
            bg="#1e1e1e", fg="#dddddd",
            anchor="w",
            wraplength=self.WINDOW_WIDTH - p * 2,
            justify=tk.LEFT,
            padx=p, pady=rescale(6),
        ).pack(fill=tk.X)

        if sentence:
            tk.Label(
                outer,
                text=f"「{sentence}」",
                font=("Segoe UI", 9, "italic"),
                bg="#1e1e1e", fg="#aaaaaa",
                anchor="w",
                wraplength=self.WINDOW_WIDTH - p * 2,
                justify=tk.LEFT,
                padx=p, pady=rescale(2),
            ).pack(fill=tk.X)

        if examples:
            ex = examples[0]
            tk.Frame(outer, bg="#333333", height=1).pack(
                fill=tk.X, padx=p, pady=(rescale(6), 0)
            )
            tk.Label(
                outer,
                text=ex.get("japanese", ""),
                font=("Segoe UI", 9),
                bg="#1e1e1e", fg="#cccccc",
                anchor="w",
                wraplength=self.WINDOW_WIDTH - p * 2,
                justify=tk.LEFT,
                padx=p, pady=rescale(2),
            ).pack(fill=tk.X)
            if ex.get("english"):
                tk.Label(
                    outer,
                    text=ex["english"],
                    font=("Segoe UI", 8),
                    bg="#1e1e1e", fg="#777777",
                    anchor="w",
                    wraplength=self.WINDOW_WIDTH - p * 2,
                    justify=tk.LEFT,
                    padx=p, pady=0,
                ).pack(fill=tk.X)

        tk.Frame(outer, bg="#1e1e1e").pack(fill=tk.BOTH, expand=True)
        tk.Frame(outer, bg="#333333", height=1).pack(fill=tk.X)

        btn_row = tk.Frame(outer, bg="#1e1e1e", pady=rescale(10))
        btn_row.pack(fill=tk.X)

        tk.Button(
            btn_row,
            text="👎  Discard",
            font=("Segoe UI", 10),
            bg="#3a1a1a", fg="#ff6b6b",
            activebackground="#4a2a2a", activeforeground="#ff6b6b",
            bd=0, padx=rescale(16), pady=rescale(6),
            cursor="hand2",
            command=self._discard,
        ).pack(side=tk.LEFT, padx=(p, rescale(4)))

        tk.Button(
            btn_row,
            text="👍  Add to Anki",
            font=("Segoe UI", 10, "bold"),
            bg="#1a3a1a", fg="#6bff6b",
            activebackground="#2a4a2a", activeforeground="#6bff6b",
            bd=0, padx=rescale(16), pady=rescale(6),
            cursor="hand2",
            command=self._confirm,
        ).pack(side=tk.RIGHT, padx=(rescale(4), p))

    def _confirm(self):
        self.running = False
        cb = self.on_confirm
        self.on_confirm = None
        self._close()
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _discard(self):
        self.running = False
        cb = self.on_discard
        self.on_discard = None
        self._close()
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def pump(self):
        """Single pump iteration — called from the main loop each cycle."""
        if not self.running:
            try:
                self._close()
            except Exception:
                pass
            return
        try:
            self.root.update()
        except tk.TclError:
            self.running = False

    def show(self):
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break


# ── DuplicateToast ────────────────────────────────────────────────────────────

class DuplicateToast:
    def __init__(self, surface: str, reading: str):
        self.root    = _create_toplevel("JAM")
        self.running = True

        w, h = rescale(300), rescale(80)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{sw - w - 12}+{sh - h - 60}")

        outer = tk.Frame(
            self.root,
            bg="#2a1e00",
            highlightbackground="#665500",
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text="⚠ Already mined",
            font=("Segoe UI", 9, "bold"),
            bg="#2a1e00", fg="#ffcc44",
            pady=rescale(8),
        ).pack()

        tk.Label(
            outer,
            text=f"{surface}　{reading}",
            font=("Segoe UI", 11),
            bg="#2a1e00", fg="#ffffff",
        ).pack()

        self.root.update()
        self.root.after(3000, self._close)

    def _close(self):
        self.running = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def pump(self):
        if not self.running:
            try:
                self._close()
            except Exception:
                pass
            return
        try:
            self.root.update()
        except tk.TclError:
            self.running = False


# ── Active toasts tracked for main-loop pumping ───────────────────────────────

_ACTIVE_TOAST: Optional[CardToast]      = None
_ACTIVE_DUP:   Optional[DuplicateToast] = None


def pump_pending_toast_once():
    """Called from main loop each cycle to drive the active card toast."""
    global _ACTIVE_TOAST
    toast = _ACTIVE_TOAST
    if toast is None:
        return
    try:
        toast.pump()
        if not toast.running:
            _ACTIVE_TOAST = None
    except Exception as e:
        logging.error(f"[Notifier] Toast pump error: {e}")
        _ACTIVE_TOAST = None


def pump_pending_dup_once():
    """Called from main loop each cycle to drive the active duplicate toast."""
    global _ACTIVE_DUP
    dup = _ACTIVE_DUP
    if dup is None:
        return
    try:
        dup.pump()
        if not dup.running:
            _ACTIVE_DUP = None
    except Exception as e:
        logging.error(f"[Notifier] Dup toast pump error: {e}")
        _ACTIVE_DUP = None


# ── Public API ────────────────────────────────────────────────────────────────

def show_ready_toast(main_thread_queue):
    """Show the 'JAM is ready' toast. Safe to call from any thread."""
    logging.info("[Notifier] Posting ready toast")

    def _show():
        root = _create_toplevel("JAM")
        w, h = rescale(320), rescale(70)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{sw - w - 12}+{sh - h - 60}")

        outer = tk.Frame(
            root,
            bg="#1a1a2a",
            highlightbackground="#333366",
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text="✦ JAM is ready",
            font=("Segoe UI", 10, "bold"),
            bg="#1a1a2a", fg="#7b9fff",
            pady=rescale(6),
        ).pack()

        tk.Label(
            outer,
            text="Press your hotkey to start mining",
            font=("Segoe UI", 8),
            bg="#1a1a2a", fg="#7b9fff",
        ).pack()

        root.update()
        root.after(4000, lambda: root.destroy())

    main_thread_queue.put(_show)


def show_card_toast(payload: Word, settings, main_thread_queue, on_confirm=None, on_discard=None):
    logging.info(f"[Notifier] Posting card toast for {payload.surface}")

    def _show():
        global _ACTIVE_TOAST
        toast = CardToast(payload, settings, on_confirm, on_discard)
        _ACTIVE_TOAST = toast

    main_thread_queue.put(_show)


def show_duplicate_toast(surface: str, reading: str, main_thread_queue):
    logging.info(f"[Notifier] Posting duplicate toast: {surface} ({reading})")

    def _show():
        global _ACTIVE_DUP
        dup = DuplicateToast(surface, reading)
        _ACTIVE_DUP = dup

    main_thread_queue.put(_show)


def show_success_toast(surface: str, main_thread_queue):
    logging.info(f"[Notifier] Posting success toast for {surface}")

    def _show():
        root = _create_toplevel("JAM")
        w, h = rescale(300), rescale(60)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{sw - w - 12}+{sh - h - 60}")

        outer = tk.Frame(
            root,
            bg="#1a2a1a",
            highlightbackground="#336633",
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text=f"✓ Card added: {surface}",
            font=("Segoe UI", 10, "bold"),
            bg="#1a2a1a", fg="#6bff6b",
            pady=rescale(16),
        ).pack()

        root.update()
        root.after(2500, lambda: root.destroy())

    main_thread_queue.put(_show)