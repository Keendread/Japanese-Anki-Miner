# DPI-aware tkinter window for selecting multiple words to mine at once.
# Appears after whole-screen or bbox capture when multiple text regions
# are detected. Already-mined words (from mined.db via anki.is_already_mined)
# are shown but grayed out with a "✓ mined" badge so the user knows
# what's new vs what they already have.
#
# Layout:
#   ┌────────────────────────────────────────────────────────┐
#   │  Select words to mine  ·  12 found  ·  3 new          │  title
#   ├────────────────────────────────────────────────────────┤
#   │  ☑  東京     とうきょう   noun   Tokyo, capital of JP  │
#   │  ☑  行く     いく         verb   to go, to move        │
#   │  ─  猫       ねこ         noun   cat            ✓mined │  grayed
#   │  ☑  食べる   たべる       verb   to eat                │
#   │  ...                                                   │  scrollable
#   ├────────────────────────────────────────────────────────┤
#   │  [Deselect All]              [Mine Selected (N)]       │  buttons
#   └────────────────────────────────────────────────────────┘
#
# Calling convention (from capture.py):
#   show_word_selector(entries, main_thread_queue, on_confirm)
#
# on_confirm receives a list[WordEntry] of the entries the user checked.
 
from __future__ import annotations
 
import ctypes
import threading
import tkinter as tk
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional
 
from src.models.word import Word

_log = logging.getLogger(__name__)
 
# ─── DPI Awareness ────────────────────────────────────────────────────────────
# Same pattern as notifier.py and image.py.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
 
 
def rescale(x: int) -> int:
    """Scales a pixel value by the system DPI (96 DPI = 100% = no scaling)."""
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except Exception:
        return x


def _ensure_tk_root():
    """Return an existing Tk root or create one (withdrawn)."""
    root = tk._default_root
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root
 
 
# ─── Entry Data Class ─────────────────────────────────────────────────────────
 
@dataclass
class WordEntry:
    """
    One row in the word selector list.
    Wraps a Word object with UI-level state (selected, is_mined).
    """
    word:      Word
    is_mined:  bool = False          # True → grayed out, checkbox disabled
    selected:  bool = True           # Default: checked (unmined words auto-selected)
 
    @property
    def display_surface(self) -> str:
        return self.word.surface or "—"
 
    @property
    def display_reading(self) -> str:
        return self.word.reading or ""
 
    @property
    def display_pos(self) -> str:
        return self.word.pos or ""
 
    @property
    def display_meaning(self) -> str:
        return self.word.meaning or "(no definition)"
 
 
# ─── Word Selector UI ─────────────────────────────────────────────────────────
 
# Layout constants (all rescaled for DPI)
_WIN_W    = rescale(580)
_ROW_H    = rescale(48)
_MAX_ROWS = 8                        # rows visible before scroll kicks in
_P        = rescale(12)              # general padding
 
 
class WordSelectorUI:
    """
    Scrollable list of detected words with checkboxes.
    Mined words are shown grayed with a badge but cannot be selected.
    Non-blocking: creates a Toplevel on the main thread and pumps via main loop.
    """
 
    def __init__(
        self,
        entries:    List[WordEntry],
        on_confirm: Callable[[List[WordEntry]], None],
    ):
        try:
            self.entries    = entries
            self.on_confirm = on_confirm
            self.running    = True
            self._ui_built  = False  # Defer UI building to first pump()

            # One BooleanVar per entry drives the checkbox state
            self._vars: List[tk.BooleanVar] = []

            # Use Toplevel attached to root to avoid multiple Tk instances
            self.root = tk.Toplevel(_ensure_tk_root())
            self.root.title("JAM — Select Words to Mine")
            self.root.resizable(False, True)
            self.root.attributes("-topmost", True)
            self.root.configure(bg="#1e1e1e")

            # Handle window close (X button) — call on_confirm with empty list
            self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

            print(f"[Selector.__init__] Toplevel created, deferring UI build to first pump()...")
            print(f"[Selector.__init__] Constructor completed successfully!")
        except Exception as e:
            print(f"[Selector.__init__] CRITICAL ERROR: {e}")
            _log.error(f"[Selector.__init__] CRITICAL ERROR: {e}", exc_info=True)
            try:
                self.root.destroy()
            except Exception:
                pass
            raise
 
    def _build_ui(self):
        new_count   = sum(1 for e in self.entries if not e.is_mined)
        total_count = len(self.entries)
        print(f"[Selector] Building UI with {total_count} total entries, {new_count} new")
        _log.info(f"[Selector] Building UI with {total_count} total entries, {new_count} new")
        for i, e in enumerate(self.entries):
            print(f"[Selector]   Entry {i}: surface={e.display_surface}, reading={e.display_reading}, mined={e.is_mined}")

        # ── Title bar ──
        title_bar = tk.Frame(self.root, bg="#2a2a2a", pady=rescale(8))
        title_bar.pack(fill=tk.X)

        tk.Label(
            title_bar,
            text="Select words to mine",
            font=("Segoe UI", 10, "bold"),
            bg="#2a2a2a", fg="#ffffff",
            padx=_P,
        ).pack(side=tk.LEFT)

        tk.Label(
            title_bar,
            text=f"{total_count} found  ·  {new_count} new",
            font=("Segoe UI", 8),
            bg="#2a2a2a", fg="#888888",
            padx=_P,
        ).pack(side=tk.RIGHT)

        # ── Scrollable list ──
        list_frame = tk.Frame(self.root, bg="#1e1e1e")
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(
            list_frame,
            bg="#1e1e1e",
            highlightthickness=0,
            height=_ROW_H * min(len(self.entries), _MAX_ROWS),
        )
        scrollbar = tk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=canvas.yview
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg="#1e1e1e")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _update_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _update_scroll)

        # Mouse-wheel scrolling
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        # Build one row per entry
        print(f"[Selector] Creating {len(self.entries)} rows...")
        for i, entry in enumerate(self.entries):
            print(f"[Selector]   Creating row {i}: {entry.display_surface}")
            try:
                var = tk.BooleanVar(value=entry.selected and not entry.is_mined)
                self._vars.append(var)
                self._build_row(inner, entry, var, i)
            except Exception as e:
                print(f"[Selector]   ERROR building row {i}: {e}")
                _log.error(f"[Selector] Error building row {i}: {e}", exc_info=True)

        # ── Divider ──
        tk.Frame(self.root, bg="#444444", height=1).pack(fill=tk.X)

        # ── Button row ──
        btn_row = tk.Frame(self.root, bg="#2a2a2a", pady=rescale(8))
        btn_row.pack(fill=tk.X)
 
        tk.Button(
            btn_row,
            text="Deselect All",
            font=("Segoe UI", 9),
            bg="#2a2a2a", fg="#aaaaaa",
            activebackground="#3a3a3a", activeforeground="#ffffff",
            bd=0, padx=rescale(12), pady=rescale(5),
            cursor="hand2",
            command=self._deselect_all,
        ).pack(side=tk.LEFT, padx=(_P, rescale(4)))
 
        tk.Button(
            btn_row,
            text="Select All New",
            font=("Segoe UI", 9),
            bg="#2a2a2a", fg="#aaaaaa",
            activebackground="#3a3a3a", activeforeground="#ffffff",
            bd=0, padx=rescale(12), pady=rescale(5),
            cursor="hand2",
            command=self._select_all_new,
        ).pack(side=tk.LEFT, padx=rescale(4))
 
        self._mine_btn = tk.Button(
            btn_row,
            text=f"Mine Selected  ({new_count})",
            font=("Segoe UI", 9, "bold"),
            bg="#1a3a1a", fg="#6bff6b",
            activebackground="#2a4a2a", activeforeground="#6bff6b",
            bd=0, padx=rescale(14), pady=rescale(5),
            cursor="hand2",
            command=self._confirm,
        )
        self._mine_btn.pack(side=tk.RIGHT, padx=(_P, _P))
 
        # Update button label whenever a checkbox changes
        for var in self._vars:
            var.trace_add("write", self._update_mine_button)
 
    def _build_row(
        self,
        parent: tk.Frame,
        entry:  WordEntry,
        var:    tk.BooleanVar,
        index:  int,
    ):
        """Builds one entry row: checkbox | surface | reading | pos | meaning | badge."""
        print(f"[Selector._build_row] Building row {index}: surface={entry.display_surface}, reading={entry.display_reading}")
        # Alternate row background for readability
        row_bg = "#1e1e1e" if index % 2 == 0 else "#252525"
        fg     = "#555555" if entry.is_mined else "#dddddd"
        sfg    = "#444444" if entry.is_mined else "#aaaaaa"   # secondary text
 
        row = tk.Frame(parent, bg=row_bg, height=_ROW_H)
        row.pack(fill=tk.X)
        row.pack_propagate(False)   # enforce fixed height
 
        # Checkbox (disabled + unchecked for mined words)
        cb = tk.Checkbutton(
            row,
            variable=var,
            bg=row_bg,
            activebackground=row_bg,
            state=tk.DISABLED if entry.is_mined else tk.NORMAL,
            cursor="hand2" if not entry.is_mined else "arrow",
        )
        cb.pack(side=tk.LEFT, padx=(rescale(8), 0))
 
        # Surface form (largest text)
        tk.Label(
            row,
            text=entry.display_surface,
            font=("Segoe UI", 11),
            bg=row_bg, fg=fg,
            width=6, anchor="w",
        ).pack(side=tk.LEFT, padx=(rescale(4), 0))
 
        # Reading
        tk.Label(
            row,
            text=entry.display_reading,
            font=("Segoe UI", 9),
            bg=row_bg, fg=sfg,
            width=10, anchor="w",
        ).pack(side=tk.LEFT, padx=rescale(4))
 
        # POS tag (small badge style)
        if entry.display_pos:
            tk.Label(
                row,
                text=entry.display_pos[:6],   # truncate long POS names
                font=("Segoe UI", 7),
                bg="#333333" if not entry.is_mined else "#2a2a2a",
                fg="#aaaaaa",
                padx=rescale(4), pady=rescale(1),
            ).pack(side=tk.LEFT, padx=rescale(2))
 
        # Meaning (fills remaining space)
        tk.Label(
            row,
            text=entry.display_meaning,
            font=("Segoe UI", 8),
            bg=row_bg, fg=sfg,
            anchor="w",
            wraplength=rescale(180),
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, padx=rescale(6), fill=tk.X, expand=True)
 
        # "✓ mined" badge on the right for already-mined words
        if entry.is_mined:
            tk.Label(
                row,
                text="✓ mined",
                font=("Segoe UI", 7, "bold"),
                bg="#1a2a1a", fg="#4a8a4a",
                padx=rescale(5), pady=rescale(2),
            ).pack(side=tk.RIGHT, padx=(_P, rescale(8)))
 
        # Click anywhere on the row (except badge) to toggle checkbox
        if not entry.is_mined:
            def _on_row_click(_e, v=var):
                print(f"[Selector._build_row] Row clicked, toggling checkbox")
                try:
                    current = v.get()
                    print(f"[Selector._build_row] Current value: {current}, setting to {not current}")
                    v.set(not current)
                    print(f"[Selector._build_row] Checkbox toggled successfully")
                except Exception as e:
                    print(f"[Selector._build_row] Error toggling checkbox: {e}")
                    _log.error(f"[Selector._build_row] Error: {e}")
            
            for widget in row.winfo_children():
                if not isinstance(widget, tk.Checkbutton):
                    widget.bind("<Button-1>", _on_row_click)
            row.bind("<Button-1>", _on_row_click)
 
    # ── Button actions ────────────────────────────────────────────────────────
 
    def _deselect_all(self):
        for var in self._vars:
            var.set(False)
 
    def _select_all_new(self):
        for var, entry in zip(self._vars, self.entries):
            if not entry.is_mined:
                var.set(True)
 
    def _update_mine_button(self, *_):
        """Keeps the 'Mine Selected (N)' label in sync with checkbox state."""
        count = sum(v.get() for v in self._vars)
        self._mine_btn.configure(text=f"Mine Selected  ({count})")
 
    def _confirm(self):
        selected = [
            entry for entry, var in zip(self.entries, self._vars)
            if var.get() and not entry.is_mined
        ]
        self.running = False
        # Prevent double-invocation
        cb = self.on_confirm
        self.on_confirm = None
        try:
            self.root.after(0, self._close)
        except Exception:
            pass
        if cb:
            cb(selected)
    
    def _on_window_close(self):
        """Handle X button close — call on_confirm with empty selection."""
        _log.info("[Selector] Window closed via X button")
        print("[Selector] Window closed via X button")
        self.running = False
        # Prevent double-invocation
        cb = self.on_confirm
        self.on_confirm = None
        try:
            self.root.after(0, self._close)
        except Exception:
            pass
        if cb:
            cb([])  # Empty selection if closed without confirming
 
    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
 
    # ── Event loop ────────────────────────────────────────────────────────────
 
    def show(self):
        """Blocking — drives tkinter manually until user confirms or closes."""
        # Deprecated: legacy blocking show. Use pump() via main loop instead.
        import time
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
            time.sleep(0.01)
        self._close()
    
    def pump(self):
        """Perform a single pump iteration; safe to call from main loop."""
        if not self.running:
            return
        try:
            # Only process if window still exists
            if not self.root.winfo_exists():
                print(f"[Selector.pump] Window no longer exists, stopping")
                self.running = False
                return
            
            # On first pump, build the UI
            if not self._ui_built:
                print(f"[Selector.pump] First pump - building UI...")
                self._build_ui()
                
                # Position window
                visible_rows = min(len(self.entries), _MAX_ROWS)
                win_h = (
                    rescale(40)                    # title bar
                    + visible_rows * _ROW_H        # row list
                    + rescale(8)                   # gap
                    + rescale(52)                  # button row
                )
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                x  = (sw - _WIN_W) // 2
                y  = (sh - win_h)  // 2
                self.root.geometry(f"{_WIN_W}x{win_h}+{x}+{y}")
                
                # Show window
                self.root.lift()
                self.root.focus_force()
                self._ui_built = True
                print(f"[Selector.pump] UI built and window shown")
            
            # Non-blocking event processing: process all pending events without blocking
            # Use update() which processes all events, unlike update_idletasks()
            self.root.update()
        except tk.TclError as e:
            print(f"[Selector.pump] TclError: {e}")
            self.running = False
        except Exception as e:
            print(f"[Selector.pump] Error: {e}")
            _log.error(f"[Selector.pump] Error: {e}", exc_info=True)
            self.running = False
 
 
# ─── Public API ───────────────────────────────────────────────────────────────
 
_ACTIVE_SELECTOR: Optional[WordSelectorUI] = None


def show_word_selector(
    entries:          List[WordEntry],
    main_thread_queue,
    on_confirm:       Callable[[List[WordEntry]], None],
):
    """
    Posts the WordSelectorUI to the main thread queue.
 
    If entries is empty (no new words detected), on_confirm([]) is called
    immediately so the caller never blocks.
 
    Args:
        entries:          List of WordEntry from the detection pipeline.
        main_thread_queue: queue.Queue owned by main.py.
        on_confirm:       Called with the list of checked WordEntry objects.
    """
    def _show():
        try:
            if not entries:
                print("[Selector] No entries to show.")
                on_confirm([])
                return
            print(f"[Selector] Creating WordSelectorUI with {len(entries)} entries...")
            ui = WordSelectorUI(entries, on_confirm=on_confirm)
            # Store active selector so main loop can pump it
            global _ACTIVE_SELECTOR
            _ACTIVE_SELECTOR = ui
            print(f"[Selector] WordSelectorUI created successfully, stored as _ACTIVE_SELECTOR")
        except Exception as e:
            print(f"[Selector._show] ERROR: {e}")
            _log.error(f"[Selector._show] ERROR: {e}", exc_info=True)
            on_confirm([])
 
    main_thread_queue.put(_show)


def pump_pending_selector_once():
    """Called from main loop to pump active word selector if any."""
    global _ACTIVE_SELECTOR
    selector = _ACTIVE_SELECTOR
    if selector is None:
        return
    try:
        selector.pump()
        if not selector.running:
            # Selector finished
            print(f"[pump_pending_selector_once] Selector finished, clearing _ACTIVE_SELECTOR")
            _ACTIVE_SELECTOR = None
    except Exception as e:
        print(f"[pump_pending_selector_once] Error: {e}")
        _log.error(f"[Selector] pump error: {e}", exc_info=True)
        try:
            selector._close()
        except Exception:
            pass
        _ACTIVE_SELECTOR = None