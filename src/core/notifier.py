# Module for card preview toast notification
# Shows preview of mined card with thumbs up/down confirmation
# Runs on the main thread via the main_thread_queue system
# Stage 1 (current): text fields only - audio/image slots added later

import tkinter as tk
from tkinter import font as tkfont
import threading
import os
from src.models.word import Word
import ctypes

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
        # Get DPI for the primary monitor (96 DPI = 100% scale)
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except:
        return x

class CardToast:
    """
    Small tkinter window that slides in from the bottom-right corner.
    Shows a preview of the mined card and lets the user confirm or discard.
    """
    
    WINDOW_WIDTH    = rescale(380)
    WINDOW_HEIGHT   = rescale(320)
    PADDING         = rescale(16)
    MARGIN          = rescale(12)
    
    def __init__(self, payload: Word, settings, on_confirm, on_discard):
        """
        Args:
            payload (Word):         full pipeline payload (parser+dict+audio+image)
            settings (_type_):      SettingsManager instance
            on_confirm (_type_):    callable function - called when user clicks thumbs up
            on_discard (_type_):    callable function - called on thumbs down
        """
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
        x  = sw - self.WINDOW_WIDTH - self.MARGIN
        y  = sh - self.WINDOW_HEIGHT - self.MARGIN - 48
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

    def _build_ui(self):
        payload = self.payload
        
        surface         = payload.surface
        reading         = payload.reading
        pos             = payload.pos
        main_def        = payload.meaning
        sentence        = payload.full_sentence
        pitch_pattern   = payload.pitch_pattern
        pitch_category  = payload.pitch_category
        frequency_rank  = payload.frequency_rank
        jlpt_level      = payload.jlpt_level
        examples        = payload.example_sentences or []
        
        outer = tk.Frame(
            self.root,
            bg="#1e1e1e",
            highlightbackground="#444444",
            highlightthickness=1
        )
        outer.pack(fill=tk.BOTH, expand=True)

        p = self.PADDING
        
        header = tk.Frame(outer, bg="#2a2a2a")
        header.pack(fill=tk.X)

        word_label = tk.Label(
            header,
            text=f"{surface}　{reading}",
            font=("Segoe UI", 14, "bold"),
            bg="#2a2a2a",
            fg="#ffffff",
            anchor="w",
            padx=p,
            pady=rescale(8)
        )
        word_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        close_btn = tk.Button(
            header,
            text="✕",
            font=("Segoe UI", 10),
            bg="#2a2a2a",
            fg="#888888",
            bd=0,
            padx=rescale(8),
            cursor="hand2",
            command=self._discard
        )
        close_btn.pack(side=tk.RIGHT, pady=rescale(4))
        
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
            meta_label = tk.Label(
                outer,
                text="  ·  ".join(meta_parts),
                font=("Segoe UI", 8),
                bg="#1e1e1e",
                fg="#888888",
                anchor="w",
                padx=p,
                pady=rescale(4)
            )
            meta_label.pack(fill=tk.X)
            
        tk.Frame(outer, bg="#333333", height=1).pack(fill=tk.X, padx=p)
        
        def_label = tk.Label(
            outer,
            text=main_def or "(no definition)",
            font=("Segoe UI", 10),
            bg="#1e1e1e",
            fg="#dddddd",
            anchor="w",
            wraplength=self.WINDOW_WIDTH - p * 2,
            justify=tk.LEFT,
            padx=p,
            pady=rescale(6)
        )
        def_label.pack(fill=tk.X)
        
        if sentence:
            sent_label = tk.Label(
                outer,
                text=f"「{sentence}」",
                font=("Segoe UI", 9, "italic"),
                bg="#1e1e1e",
                fg="#aaaaaa",
                anchor="w",
                wraplength=self.WINDOW_WIDTH - p * 2,
                justify=tk.LEFT,
                padx=p,
                pady=rescale(2)
            )
            sent_label.pack(fill=tk.X)
            
        if examples:
            ex = examples[0]
            tk.Frame(outer, bg="#333333", height=1).pack(
                fill=tk.X, padx=p, pady=(rescale(6), 0)
            )
            ex_jp = tk.Label(
                outer,
                text=ex.get("japanese", ""),
                font=("Segoe UI", 9),
                bg="#1e1e1e",
                fg="#cccccc",
                anchor="w",
                wraplength=self.WINDOW_WIDTH - p * 2,
                justify=tk.LEFT,
                padx=p,
                pady=rescale(2)
            )
            ex_jp.pack(fill=tk.X)
            if ex.get("english"):
                ex_en = tk.Label(
                    outer,
                    text=ex["english"],
                    font=("Segoe UI", 8),
                    bg="#1e1e1e",
                    fg="#777777",
                    anchor="w",
                    wraplength=self.WINDOW_WIDTH - p * 2,
                    justify=tk.LEFT,
                    padx=p,
                    pady=0
                )
                ex_en.pack(fill=tk.X)
                
        tk.Frame(outer, bg="#1e1e1e").pack(fill=tk.BOTH, expand=True)

        tk.Frame(outer, bg="#333333", height=1).pack(fill=tk.X)

        btn_row = tk.Frame(outer, bg="#1e1e1e", pady=rescale(10))
        btn_row.pack(fill=tk.X)

        discard_btn = tk.Button(
            btn_row,
            text="👎  Discard",
            font=("Segoe UI", 10),
            bg="#3a1a1a",
            fg="#ff6b6b",
            activebackground="#4a2a2a",
            activeforeground="#ff6b6b",
            bd=0,
            padx=rescale(16),
            pady=rescale(6),
            cursor="hand2",
            command=self._discard
        )
        discard_btn.pack(side=tk.LEFT, padx=(p, rescale(4)))
 
        add_btn = tk.Button(
            btn_row,
            text="👍  Add to Anki",
            font=("Segoe UI", 10, "bold"),
            bg="#1a3a1a",
            fg="#6bff6b",
            activebackground="#2a4a2a",
            activeforeground="#6bff6b",
            bd=0,
            padx=rescale(16),
            pady=rescale(6),
            cursor="hand2",
            command=self._confirm
        )
        add_btn.pack(side=tk.RIGHT, padx=(rescale(4), p))
        
    def _confirm(self):
        self.running = False
        self._close()
        if self.on_confirm:
            threading.Thread(target=self.on_confirm, daemon=True).start()
    
    def _close(self):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        
    def _discard(self):
        self.running = False
        self._close()
        if self.on_discard:
            threading.Thread(target=self.on_discard, daemon=True).start()


    def show(self):
        """Blocking call - runs tkinter event loop until closed."""
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
            

class DuplicateToast:
    """
    Small warning toast shown when a word has already been mined.
    Auto-dismisses after 3 seconds.
    """
    
    def __init__(self, surface: str, reading: str):
        self.root = _create_toplevel("JAM")
        self.running = True

        self.root.title("JAM")

        w, h =  rescale(300), rescale(80)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - w - 12
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        outer = tk.Frame(
            self.root,
            bg="#2a1e00",
            highlightbackground="#665500",
            highlightthickness=1
        )
        outer.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            outer,
            text="⚠ Already mined",
            font=("Segoe UI", 9, "bold"),
            bg="#2a1e00",
            fg="#ffcc44",
            pady=rescale(8)
        ).pack()
        
        tk.Label(
            outer,
            text=f"{surface}　{reading}",
            font=("Segoe UI", 11),
            bg="#2a1e00",
            fg="#ffffff"
        ).pack()
        
        self.root.update()
        # Auto-dismiss after 3 seconds
        self.root.after(3000, self._close)
        
    def _close(self):
        self.running = False
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
    
    def show(self):
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
            
            
def show_card_toast(payload: Word, settings, main_thread_queue, on_confirm=None, on_discard=None):
    """
    Posts the card preview toast to the main thread queue.
    Non-blocking - returns immediately.

    Args:
        payload (Word):                 full pipeline payload
        settings (_type_):              SettingsManager instance
        main_thread_queue (_type_):     queue.Queue for main thread tasks
        on_confirm (_type_, optional):  callable run in background thread on thumbs up
        on_discard (_type_, optional):  callable run in background thread on thumbs down
    """
    import logging
    logging.info(f"[Notifier] Posting card toast for {payload.surface} to main queue")
    
    def _show():
        logging.debug(f"[Notifier] Creating CardToast for {payload.surface}")
        toast = CardToast(payload, settings, on_confirm, on_discard)
        logging.info(f"[Notifier] Showing CardToast for {payload.surface}")
        toast.show()

    main_thread_queue.put(_show)

def show_duplicate_toast(surface: str, reading: str, main_thread_queue):
    """
    Posts the duplicate warning toast to the main thread queue.
    Auto-dismisses after 3 seconds.

    Args:
        surface (str):              word surface form
        reading (str):              hiragana reading
        main_thread_queue (_type_): queue.Queue for main thread tasks
    """
    import logging
    logging.info(f"[Notifier] Posting duplicate toast: {surface} ({reading})")
    
    def _show():
        logging.debug(f"[Notifier] Creating DuplicateToast for {surface}")
        toast = DuplicateToast(surface, reading)
        logging.info(f"[Notifier] Showing DuplicateToast for {surface}")
        toast.show()

    main_thread_queue.put(_show)

def show_success_toast(surface: str, main_thread_queue):
    """
    Brief success notification after card is added.
    Reuses DuplicateToast structure with green styling.
    """
    import logging
    logging.info(f"[Notifier] Posting success toast for {surface}")
    
    def _show():
        logging.debug(f"[Notifier] Creating success toast for {surface}")
        root = _create_toplevel("JAM")
        w, h = rescale(300), rescale(60)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{sw - w - 12}+{sh - h - 60}")

        outer = tk.Frame(
            root,
            bg="#1a2a1a",
            highlightbackground="#336633",
            highlightthickness=1
        )
        outer.pack(fill=tk.BOTH, expand=True)     

        tk.Label(
            outer,
            text=f"✓ Card added: {surface}",
            font=("Segoe UI", 10, "bold"),
            bg="#1a2a1a",
            fg="#6bff6b",
            pady=rescale(16)
        ).pack()
        
        logging.info(f"[Notifier] Success toast displayed for {surface}")
        root.update()
        root.after(2500, lambda: (setattr(root, "_closed", True), root.destroy()))

        while True:
            try:
                root.update()
            except tk.TclError:
                break

    main_thread_queue.put(_show)