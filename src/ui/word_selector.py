# src/ui/word_selector.py
#
# DPI-aware tkinter window for selecting multiple words to mine at once.
# Uses the same blocking show() pattern as CardToast in notifier.py —
# the main thread stays inside show() while the window is open, processing
# events via root.update() in a loop. No pump() or global state needed.

from __future__ import annotations

import ctypes
import tkinter as tk
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.models.word import Word

# ─── DPI Awareness ────────────────────────────────────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def rescale(x: int) -> int:
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(x * (dpi / 96.0))
    except Exception:
        return x


# ─── Entry Data Class ─────────────────────────────────────────────────────────

@dataclass
class WordEntry:
    """One row in the word selector. Wraps a Word with UI-level state."""
    word:     Word
    is_mined: bool = False   # grayed out, checkbox disabled
    selected: bool = True    # pre-checked for unmined words

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


# ─── Layout constants ─────────────────────────────────────────────────────────

_WIN_W    = rescale(580)
_ROW_H    = rescale(48)
_MAX_ROWS = 8      # visible rows before scrollbar appears
_P        = rescale(12)


# ─── Word Selector UI ─────────────────────────────────────────────────────────

class WordSelectorUI:
    """
    Scrollable word list with checkboxes.

    Lifecycle (same as CardToast):
        ui = WordSelectorUI(entries, on_confirm)
        ui.show()          # blocks main thread until user confirms / closes
        # on_confirm(selected_entries) is called before show() returns
    """

    def __init__(
        self,
        entries:    List[WordEntry],
        on_confirm: Callable[[List[WordEntry]], None],
    ):
        self.entries    = entries
        self.on_confirm = on_confirm
        self.running    = True
        self._vars: List[tk.BooleanVar] = []
        self._mine_btn: Optional[tk.Button] = None

        # Fresh Tk() — same pattern as CardToast in notifier.py
        self.root = tk.Tk()
        self.root.title("JAM — Select Words to Mine")
        self.root.resizable(False, True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._build_ui()
        self._position_window()

        self.root.update()
        self.root.lift()
        self.root.focus_force()

    # ── Event loop (blocking, same pattern as CardToast.show()) ──────────────

    def show(self):
        """
        Blocks the calling thread (main thread) until the user confirms or
        closes. Calls on_confirm before returning so the caller can act on
        the selection synchronously.
        """
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break

    # ── Layout ────────────────────────────────────────────────────────────────

    def _position_window(self):
        visible = min(len(self.entries), _MAX_ROWS)
        win_h   = rescale(40) + visible * _ROW_H + rescale(8) + rescale(52)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{_WIN_W}x{win_h}+{(sw-_WIN_W)//2}+{(sh-win_h)//2}")

    def _build_ui(self):
        new_count   = sum(1 for e in self.entries if not e.is_mined)
        total_count = len(self.entries)

        # ── Title bar ──
        title_bar = tk.Frame(self.root, bg="#2a2a2a", pady=rescale(8))
        title_bar.pack(fill=tk.X)

        tk.Label(
            title_bar,
            text="Select words to mine",
            font=("Segoe UI", 10, "bold"),
            bg="#2a2a2a", fg="#ffffff", padx=_P,
        ).pack(side=tk.LEFT)

        tk.Label(
            title_bar,
            text=f"{total_count} found  ·  {new_count} new",
            font=("Segoe UI", 8),
            bg="#2a2a2a", fg="#888888", padx=_P,
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
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg="#1e1e1e")

        # Save the canvas window ID so we can resize inner to match canvas.
        # Without this, inner has no width and fill=tk.X on each row renders 0px wide.
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        # When the canvas is resized (e.g. window resize), keep inner width in sync.
        # This is what makes fill=tk.X on rows actually fill the visible area.
        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)

        # Update scroll region whenever inner's content changes
        def _on_inner_resize(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_inner_resize)

        # Bind mousewheel to the root window so it works regardless of
        # which widget the mouse is hovering over.
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.root.bind("<MouseWheel>", _on_mousewheel)

        # Build rows
        for i, entry in enumerate(self.entries):
            var = tk.BooleanVar(value=entry.selected and not entry.is_mined)
            var.trace_add("write", self._update_mine_button)
            self._vars.append(var)
            self._build_row(inner, entry, var, i)

        # Force scroll region calculation after all rows are packed
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

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

    def _build_row(
        self,
        parent: tk.Frame,
        entry:  WordEntry,
        var:    tk.BooleanVar,
        index:  int,
    ):
        # Colour constants — match CardToast green/red in notifier.py
        _BG_SEL   = "#1a3a1a";  _FG_SEL   = "#6bff6b";  _SFG_SEL   = "#4aaa4a"
        _BG_UNSEL = "#3a1a1a";  _FG_UNSEL = "#ff6b6b";  _SFG_UNSEL = "#aa4a4a"
        _BG_MINED = "#1e2a1e";  _FG_MINED = "#4a8a4a";  _SFG_MINED = "#3a6a3a"

        row = tk.Frame(parent, height=_ROW_H)
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        # Tick — rendered as a label so we fully own the visual state.
        tick_lbl = tk.Label(row, font=("Segoe UI", 11), width=2, anchor="center",
                            cursor="arrow" if entry.is_mined else "hand2")
        tick_lbl.pack(side=tk.LEFT, padx=(rescale(8), 0))

        lbl_surface = tk.Label(row, text=entry.display_surface,
                               font=("Segoe UI", 11), width=6, anchor="w")
        lbl_surface.pack(side=tk.LEFT, padx=(rescale(4), 0))

        lbl_reading = tk.Label(row, text=entry.display_reading,
                               font=("Segoe UI", 9), width=10, anchor="w")
        lbl_reading.pack(side=tk.LEFT, padx=rescale(4))

        lbl_pos = None
        if entry.display_pos:
            lbl_pos = tk.Label(row, text=entry.display_pos[:6],
                               font=("Segoe UI", 7), fg="#aaaaaa",
                               padx=rescale(4), pady=rescale(1))
            lbl_pos.pack(side=tk.LEFT, padx=rescale(2))

        lbl_meaning = tk.Label(row, text=entry.display_meaning,
                               font=("Segoe UI", 8), anchor="w",
                               wraplength=rescale(180), justify=tk.LEFT)
        lbl_meaning.pack(side=tk.LEFT, padx=rescale(6), fill=tk.X, expand=True)

        if entry.is_mined:
            tk.Label(row, text="✓ mined", font=("Segoe UI", 7, "bold"),
                     bg="#1a2a1a", fg="#4a8a4a",
                     padx=rescale(5), pady=rescale(2),
                     ).pack(side=tk.RIGHT, padx=(_P, rescale(8)))

        def _refresh(*_):
            if entry.is_mined:
                bg, fg, sfg, tick = _BG_MINED, _FG_MINED, _SFG_MINED, "✓"
            elif var.get():
                bg, fg, sfg, tick = _BG_SEL,   _FG_SEL,   _SFG_SEL,   "☑"
            else:
                bg, fg, sfg, tick = _BG_UNSEL,  _FG_UNSEL,  _SFG_UNSEL,  "☐"
            row.configure(bg=bg)
            tick_lbl.configure(bg=bg, fg=fg,  text=tick)
            lbl_surface.configure(bg=bg, fg=fg)
            lbl_reading.configure(bg=bg, fg=sfg)
            lbl_meaning.configure(bg=bg, fg=sfg)
            if lbl_pos:
                lbl_pos.configure(bg=bg)

        _refresh()
        var.trace_add("write", _refresh)

        if not entry.is_mined:
            def _toggle(_e, v=var): v.set(not v.get())
            row.bind("<Button-1>", _toggle)
            for child in row.winfo_children():
                child.bind("<Button-1>", _toggle)

    # ── Button actions ────────────────────────────────────────────────────────

    def _deselect_all(self):
        for var in self._vars:
            var.set(False)
        self._update_mine_button()

    def _select_all_new(self):
        for var, entry in zip(self._vars, self.entries):
            if not entry.is_mined:
                var.set(True)
        self._update_mine_button()

    def _update_mine_button(self, *_):
        if self._mine_btn:
            count = sum(v.get() for v in self._vars)
            self._mine_btn.configure(text=f"Mine Selected  ({count})")

    # ── Close actions ─────────────────────────────────────────────────────────

    def _confirm(self):
        selected = [
            entry for entry, var in zip(self.entries, self._vars)
            if var.get() and not entry.is_mined
        ]
        self._finish(selected)

    def _on_window_close(self):
        """User closed the window via the X button — treat as empty selection."""
        self._finish([])

    def _finish(self, selected: List[WordEntry]):
        """
        Common exit path for confirm and close.
        Sets running=False (which exits show()'s loop), destroys the window,
        then dispatches on_confirm to a background thread.

        The callback must NOT run on the main thread: it calls
        _run_card_flow(blocking=True), which posts card toasts to the
        main_thread_queue and then blocks waiting for them to resolve.
        If it ran on the main thread the queue would never be pumped,
        the toasts would never appear, and the wait would time out.
        """
        import threading
        self.running = False
        cb = self.on_confirm
        self.on_confirm = None   # prevent double-invocation
        self._close()
        if cb:
            threading.Thread(target=cb, args=(selected,), daemon=True).start()

    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# ─── Public API ───────────────────────────────────────────────────────────────

def show_word_selector(
    entries:          List[WordEntry],
    main_thread_queue,
    on_confirm:       Callable[[List[WordEntry]], None],
):
    """
    Posts the WordSelectorUI to the main thread queue.
    Behaves identically to show_card_toast() — blocking on the main thread
    while the window is visible, returning after the user confirms or closes.

    Args:
        entries:           List of WordEntry from _build_word_entries().
        main_thread_queue: queue.Queue owned by main.py.
        on_confirm:        Called with the list of checked WordEntry objects.
                           Called with [] if the window is closed without confirming.
    """
    def _show():
        if not entries:
            print("[Selector] No entries — skipping.")
            on_confirm([])
            return
        ui = WordSelectorUI(entries, on_confirm=on_confirm)
        ui.show()   # blocks until user confirms or closes (same as CardToast)

    main_thread_queue.put(_show)