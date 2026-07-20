from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
    QScrollArea, QApplication,
)
from PySide6.QtCore import Qt, QTimer

from src.models.word import Word
from core.signals import signals


# ─── Entry Data Class (unchanged — no UI dependency) ───────────────────────────

@dataclass
class WordEntry:
    word:     Word
    is_mined: bool = False
    selected: bool = True

    block_index:       int = 0
    block_text:        str = ""
    block_translation: str = ""

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

_WIN_W    = 600
_ROW_H    = 44
_MAX_ROWS = 10
_P        = 12

_BG_SEL,   _FG_SEL,   _SFG_SEL   = "#1a3a1a", "#6bff6b", "#4aaa4a"
_BG_UNSEL, _FG_UNSEL, _SFG_UNSEL = "#3a1a1a", "#ff6b6b", "#aa4a4a"
_BG_MINED, _FG_MINED, _SFG_MINED = "#1e2a1e", "#4a8a4a", "#3a6a3a"


# ─── Row widget ─────────────────────────────────────────────────────────────

class _WordRow(QFrame):
    def __init__(self, entry: WordEntry, on_toggle: Callable[[], None]) -> None:
        super().__init__()
        self.entry      = entry
        self._on_toggle = on_toggle
        self.setFixedHeight(_ROW_H)
        self.setCursor(Qt.ArrowCursor if entry.is_mined else Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)

        self._tick = QLabel()
        self._tick.setFixedWidth(24)
        self._tick.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._tick)

        self._surface = QLabel(entry.display_surface)
        self._surface.setFixedWidth(60)
        layout.addWidget(self._surface)

        self._reading = QLabel(entry.display_reading)
        self._reading.setFixedWidth(90)
        layout.addWidget(self._reading)

        if entry.display_pos:
            self._pos = QLabel(entry.display_pos[:6])
            self._pos.setStyleSheet("font-size: 9px; color: #aaaaaa; padding: 1px 4px;")
            layout.addWidget(self._pos)
        else:
            self._pos = None

        self._meaning = QLabel(entry.display_meaning)
        self._meaning.setWordWrap(True)
        layout.addWidget(self._meaning, stretch=1)

        if entry.is_mined:
            mined_lbl = QLabel("✓ mined")
            mined_lbl.setStyleSheet(
                "font-size: 9px; font-weight: bold; background-color: #1a2a1a; "
                "color: #4a8a4a; padding: 2px 5px;"
            )
            layout.addWidget(mined_lbl)

        self._refresh()

    def _refresh(self) -> None:
        if self.entry.is_mined:
            bg, fg, sfg, tick = _BG_MINED, _FG_MINED, _SFG_MINED, "✓"
        elif self.entry.selected:
            bg, fg, sfg, tick = _BG_SEL, _FG_SEL, _SFG_SEL, "☑"
        else:
            bg, fg, sfg, tick = _BG_UNSEL, _FG_UNSEL, _SFG_UNSEL, "☐"

        self.setStyleSheet(f"_WordRow {{ background-color: {bg}; }}")
        self._tick.setStyleSheet(f"color: {fg}; background: transparent; font-size: 13px;")
        self._tick.setText(tick)
        self._surface.setStyleSheet(f"color: {fg}; background: transparent; font-size: 13px;")
        self._reading.setStyleSheet(f"color: {sfg}; background: transparent; font-size: 11px;")
        self._meaning.setStyleSheet(f"color: {sfg}; background: transparent; font-size: 10px;")

    def mousePressEvent(self, event) -> None:
        if not self.entry.is_mined and event.button() == Qt.LeftButton:
            self.entry.selected = not self.entry.selected
            self._refresh()
            self._on_toggle()
        super().mousePressEvent(event)


# ─── Group header (per-block, with audio source toggle) ───────────────────────

class _GroupHeader(QFrame):
    def __init__(self, entries: List[WordEntry], on_recording_state_change,
                 on_activated) -> None:
        super().__init__()
        self.entries = entries               # all entries sharing this block_index
        self._on_recording_state_change = on_recording_state_change
        self._on_activated = on_activated
        self._active = False
        first = entries[0]

        self.setCursor(Qt.PointingHandCursor)
        self._apply_container_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_P, 8, _P, 6)
        layout.setSpacing(2)

        text_row = QHBoxLayout()
        block_lbl = QLabel(first.block_text or "(no text)")
        block_lbl.setWordWrap(True)
        block_lbl.setStyleSheet("font-size: 12px; color: #dddddd; font-style: italic;")
        text_row.addWidget(block_lbl, stretch=1)
        layout.addLayout(text_row)

        if first.block_translation:
            trans_lbl = QLabel(first.block_translation)
            trans_lbl.setWordWrap(True)
            trans_lbl.setStyleSheet("font-size: 10px; color: #888888;")
            layout.addWidget(trans_lbl)

        control_row = QHBoxLayout()

        self._record_btn = QPushButton("● Record Sentence Audio")
        self._record_btn.setCursor(Qt.PointingHandCursor)
        self._apply_idle_style()
        self._record_btn.clicked.connect(self._toggle_recording)
        control_row.addWidget(self._record_btn)

        self._source_lbl = QLabel("Source: VOICEVOX (default)")
        self._source_lbl.setStyleSheet("font-size: 9px; color: #7799ff;")
        control_row.addWidget(self._source_lbl, stretch=1)

        self._hotkey_hint = QLabel("")
        self._hotkey_hint.setStyleSheet("font-size: 9px; color: #666666;")
        control_row.addWidget(self._hotkey_hint)

        layout.addLayout(control_row)

    def set_hotkey_hint(self, text: str) -> None:
        self._hotkey_hint.setText(text)

    def _apply_idle_style(self) -> None:
        self._record_btn.setText("● Record Sentence Audio")
        self._record_btn.setEnabled(True)
        self._record_btn.setStyleSheet("""
            QPushButton { background-color: #3a1a1a; color: #ff8888; border: none;
                          padding: 4px 10px; font-size: 9px; font-weight: bold; }
            QPushButton:hover { background-color: #4a2424; }
        """)

    def _apply_recording_style(self) -> None:
        self._record_btn.setText("⏹ Stop Recording")
        self._record_btn.setStyleSheet("""
            QPushButton { background-color: #4a1a1a; color: #ffaaaa; border: none;
                          padding: 4px 10px; font-size: 9px; font-weight: bold; }
            QPushButton:hover { background-color: #5a2424; }
        """)

    def _apply_container_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                "background-color: #202030; border-left: 3px solid #7799ff;"
            )
        else:
            self.setStyleSheet(
                "background-color: #202030; border-left: 3px solid transparent;"
            )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_container_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on_activated(self)
        super().mousePressEvent(event)

    def set_disabled_while_other_group_records(self, disabled: bool) -> None:
        """Called on every OTHER group's header while one group is actively recording."""
        self._record_btn.setEnabled(not disabled)

    def toggle_recording(self) -> None:
        self._toggle_recording()

    def _toggle_recording(self) -> None:
        from core import audio_recorder

        if not audio_recorder.is_recording():
            ok, error_msg = audio_recorder.start_recording()
            if not ok:
                self._source_lbl.setText(f"⚠ {error_msg or 'Could not start recording'}")
                self._source_lbl.setStyleSheet("font-size: 9px; color: #ff8888;")
                return
            self._apply_recording_style()
            self._source_lbl.setText("● Recording… replay the line now")
            self._on_recording_state_change(self, recording=True)
        else:
            temp_path = audio_recorder.stop_recording()
            self._apply_idle_style()

            if temp_path is None:
                self._source_lbl.setText("⚠ No audio captured — still using VOICEVOX")
                self._on_recording_state_change(self, recording=False)
                return

            committed_filename = audio_recorder.commit_shared_recording(temp_path)

            if committed_filename is None:
                self._source_lbl.setText("⚠ Failed to save recording — still using VOICEVOX")
                self._source_lbl.setStyleSheet("font-size: 9px; color: #ff8888;")
                self._on_recording_state_change(self, recording=False)
                return

            for entry in self.entries:
                entry.word.sentence_audio = committed_filename

            self._source_lbl.setText("✓ Source: Recorded")
            self._source_lbl.setStyleSheet("font-size: 9px; color: #6bff6b;")
            self._on_recording_state_change(self, recording=False)


# ─── Word Selector Window ─────────────────────────────────────────────────────

class WordSelectorWindow(QWidget):
    def __init__(self, entries: List[WordEntry],
                 on_confirm: Callable[[List[WordEntry]], None],
                 settings=None) -> None:
        super().__init__()
        self.entries      = entries
        self._on_confirm  = on_confirm
        self.settings     = settings
        self._rows: List[_WordRow] = []
        self._headers: List[_GroupHeader] = []
        self._recording_header: Optional[_GroupHeader] = None
        self._active_header: Optional[_GroupHeader] = None

        self.setWindowTitle("JAM — Select Words to Mine")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #1e1e1e;")

        self._build_ui()
        self._position_window()
        self._setup_record_hotkey()
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Global record hotkey ─────────────────────────────────────────────────
    def _setup_record_hotkey(self) -> None:
        self._record_combo_vks: set = set()
        self._hotkey_was_down = False

        if self.settings is not None:
            try:
                self._record_combo_vks = self.settings.get_record_combo_vks()
            except Exception as e:
                print(f"[Selector] Couldn't read record_combo: {e}")

        combo_names = self.settings.get("record_combo", []) if self.settings else []
        hint = f"⌨ {' + '.join(combo_names)}" if combo_names else ""
        for header in self._headers:
            header.set_hotkey_hint(hint)

        if not self._record_combo_vks:
            return   # no combo configured — button-only, no polling needed

        self._hotkey_timer = QTimer(self)
        self._hotkey_timer.setInterval(20)   # matches CaptureController's poll rate
        self._hotkey_timer.timeout.connect(self._poll_record_hotkey)
        self._hotkey_timer.start()

    def _poll_record_hotkey(self) -> None:
        from core.input import is_held

        all_held = all(is_held(vk) for vk in self._record_combo_vks)

        if all_held and not self._hotkey_was_down:
            self._hotkey_was_down = True
            self._trigger_record_hotkey()
        elif not all_held:
            self._hotkey_was_down = False

    def _trigger_record_hotkey(self) -> None:
        if self._recording_header is not None:
            self._recording_header.toggle_recording()
        elif self._active_header is not None:
            self._active_header.toggle_recording()

    # ── Group targeting ──────────────────────────────────────────────────────

    def _on_group_activated(self, header: "_GroupHeader") -> None:
        if header is self._active_header:
            return
        if self._active_header is not None:
            self._active_header.set_active(False)
        self._active_header = header
        header.set_active(True)

    # ── Grouping ──────────────────────────────────────────────────────────────

    def _grouped_entries(self) -> List[List[WordEntry]]:
        groups: dict[int, List[WordEntry]] = {}
        order: List[int] = []
        for entry in self.entries:
            if entry.block_index not in groups:
                groups[entry.block_index] = []
                order.append(entry.block_index)
            groups[entry.block_index].append(entry)
        return [groups[i] for i in order]

    def _on_recording_state_change(self, active_header: _GroupHeader, recording: bool) -> None:
        self._recording_header = active_header if recording else None
        for header in self._headers:
            if header is not active_header:
                header.set_disabled_while_other_group_records(recording)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _position_window(self) -> None:
        visible_rows = min(len(self.entries), _MAX_ROWS)
        group_count  = len(self._grouped_entries())
        win_h = 40 + group_count * 54 + visible_rows * _ROW_H + 8 + 52
        win_h = min(win_h, 700)
        screen = QApplication.primaryScreen().availableGeometry()
        self.setFixedSize(_WIN_W, win_h)
        self.move(
            screen.x() + (screen.width()  - _WIN_W) // 2,
            screen.y() + (screen.height() - win_h)  // 2,
        )

    def _build_ui(self) -> None:
        new_count   = sum(1 for e in self.entries if not e.is_mined)
        total_count = len(self.entries)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Title bar ──
        title_bar = QFrame()
        title_bar.setStyleSheet("background-color: #2a2a2a;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(_P, 8, _P, 8)

        title = QLabel("Select words to mine")
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffffff;")
        tb_layout.addWidget(title, stretch=1)

        count_lbl = QLabel(f"{total_count} found  ·  {new_count} new")
        count_lbl.setStyleSheet("font-size: 9px; color: #888888;")
        tb_layout.addWidget(count_lbl)

        layout.addWidget(title_bar)

        # ── Scrollable, grouped list ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: #1e1e1e;")

        inner = QWidget()
        inner.setStyleSheet("background-color: #1e1e1e;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        for group in self._grouped_entries():
            header = _GroupHeader(
                group,
                on_recording_state_change=self._on_recording_state_change,
                on_activated=self._on_group_activated,
            )
            self._headers.append(header)
            inner_layout.addWidget(header)

            for entry in group:
                row = _WordRow(entry, on_toggle=self._update_mine_button)
                inner_layout.addWidget(row)
                self._rows.append(row)

            group_divider = QFrame()
            group_divider.setFixedHeight(1)
            group_divider.setStyleSheet("background-color: #333333;")
            inner_layout.addWidget(group_divider)

        if self._headers:
            self._on_group_activated(self._headers[0])

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #444444;")
        layout.addWidget(divider)

        # ── Button row ──
        btn_row = QFrame()
        btn_row.setStyleSheet("background-color: #2a2a2a;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(_P, 8, _P, 8)

        deselect_btn = QPushButton("Deselect All")
        deselect_btn.setCursor(Qt.PointingHandCursor)
        deselect_btn.setStyleSheet(self._secondary_btn_style())
        deselect_btn.clicked.connect(self._deselect_all)
        btn_layout.addWidget(deselect_btn)

        select_new_btn = QPushButton("Select All New")
        select_new_btn.setCursor(Qt.PointingHandCursor)
        select_new_btn.setStyleSheet(self._secondary_btn_style())
        select_new_btn.clicked.connect(self._select_all_new)
        btn_layout.addWidget(select_new_btn)

        btn_layout.addStretch(1)

        self._mine_btn = QPushButton(f"Mine Selected  ({new_count})")
        self._mine_btn.setCursor(Qt.PointingHandCursor)
        self._mine_btn.setStyleSheet("""
            QPushButton { background-color: #1a3a1a; color: #6bff6b; border: none;
                          padding: 5px 14px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #2a4a2a; }
        """)
        self._mine_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(self._mine_btn)

        layout.addWidget(btn_row)

    @staticmethod
    def _secondary_btn_style() -> str:
        return """
            QPushButton { background-color: #2a2a2a; color: #aaaaaa; border: none;
                          padding: 5px 12px; font-size: 10px; }
            QPushButton:hover { background-color: #3a3a3a; color: #ffffff; }
        """

    # ── Button actions ────────────────────────────────────────────────────────

    def _deselect_all(self) -> None:
        for row in self._rows:
            if not row.entry.is_mined:
                row.entry.selected = False
                row._refresh()
        self._update_mine_button()

    def _select_all_new(self) -> None:
        for row in self._rows:
            if not row.entry.is_mined:
                row.entry.selected = True
                row._refresh()
        self._update_mine_button()

    def _update_mine_button(self) -> None:
        count = sum(1 for e in self.entries if e.selected and not e.is_mined)
        self._mine_btn.setText(f"Mine Selected  ({count})")

    # ── Close actions ─────────────────────────────────────────────────────────

    def _confirm(self) -> None:
        selected = [e for e in self.entries if e.selected and not e.is_mined]
        self._finish(selected)

    def closeEvent(self, event) -> None:
        if hasattr(self, "_hotkey_timer"):
            self._hotkey_timer.stop()

        from core import audio_recorder
        if audio_recorder.is_recording():
            audio_recorder.cancel_recording()
        if self._on_confirm is not None:
            self._finish([])
        event.accept()

    def _finish(self, selected: List[WordEntry]) -> None:
        cb = self._on_confirm
        self._on_confirm = None   # prevent double-invocation (confirm + closeEvent)
        self.close()
        if cb:
            threading.Thread(target=cb, args=(selected,), daemon=True).start()


# ─── Public API ───────────────────────────────────────────────────────────────

def show_word_selector(
    entries:    List[WordEntry],
    main_thread_queue,   # unused, kept for call-site compatibility
    on_confirm: Callable[[List[WordEntry]], None],
    settings=None,       # needed for the sentence-audio record hotkey
) -> None:
    if not entries:
        print("[Selector] No entries — skipping.")
        on_confirm([])
        return
    signals.show_word_selector.emit(entries, on_confirm, settings)


def _on_show_word_selector(entries, on_confirm, settings) -> None:
    WordSelectorWindow(entries, on_confirm, settings)


def connect_word_selector_signal() -> None:
    signals.show_word_selector.connect(_on_show_word_selector)