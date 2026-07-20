from __future__ import annotations
import threading
from typing import Optional

from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtCore    import Qt, QTimer, Signal
from PySide6.QtGui     import QScreen
from PySide6.QtWidgets import QApplication

from src.models.word import Word


# ── Shared helpers ──────────────────────────────────────────────────────────

_active_widgets: list[QWidget] = []


def _track(widget: QWidget) -> None:
    _active_widgets.append(widget)
    widget.destroyed.connect(lambda: _active_widgets.remove(widget) if widget in _active_widgets else None)


def _bottom_right_geometry(width: int, height: int, margin: int = 12, lift: int = 60) -> tuple[int, int]:
    screen = QApplication.primaryScreen().availableGeometry()
    x = screen.x() + screen.width()  - width  - margin
    y = screen.y() + screen.height() - height - lift
    return x, y


def _frameless(widget: QWidget) -> None:
    widget.setWindowFlags(
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    )


class _PlainToast(QWidget):
    def __init__(self, title: str, subtitle: str = "", *,
                 bg: str, border: str, fg: str,
                 width: int = 320, height: int = 70,
                 dismiss_ms: int = 4000) -> None:
        super().__init__()
        _frameless(self)
        self.setFixedSize(width, height)
        self.move(*_bottom_right_geometry(width, height))

        self.setStyleSheet(f"""
            QWidget#toastRoot {{
                background-color: {bg};
                border: 1px solid {border};
            }}
            QLabel {{ background: transparent; color: {fg}; }}
        """)

        root = QFrame(self)
        root.setObjectName("toastRoot")
        root.setGeometry(0, 0, width, height)

        layout = QVBoxLayout(root)
        layout.setAlignment(Qt.AlignCenter)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet("font-size: 10px;")
            sub_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(sub_lbl)

        _track(self)
        self.show()
        QTimer.singleShot(dismiss_ms, self.close)


# ── LoadingToast ─────────────────────────────────────────────────────────────

class LoadingToast(QWidget):
    _W, _H, _PAD = 320, 130, 14
    _ROWS = [("ocr", "OCR model"), ("parser", "Parser / tokenizer"), ("dict", "Dictionary")]

    _BG, _BORDER      = "#1a1a2a", "#333366"
    _PENDING_FG       = "#555577"
    _LOADING_FG       = "#7b9fff"
    _DONE_FG          = "#6bff6b"
    _TITLE_FG         = "#7b9fff"

    _key_ready = Signal(str)

    def __init__(self, ocr_event, parser_event, dict_event, on_all_ready=None) -> None:
        super().__init__()
        self._on_all_ready = on_all_ready
        self._labels: dict[str, QLabel] = {}
        self._done = {
            "ocr":    ocr_event.is_set(),
            "parser": parser_event.is_set(),
            "dict":   dict_event.is_set(),
        }
        self._events = {"ocr": ocr_event, "parser": parser_event, "dict": dict_event}

        self._key_ready.connect(self._on_key_ready)

        _frameless(self)
        self.setFixedSize(self._W, self._H)
        self.move(*_bottom_right_geometry(self._W, self._H))
        self.setStyleSheet(f"""
            QWidget#toastRoot {{ background-color: {self._BG}; border: 1px solid {self._BORDER}; }}
            QLabel {{ background: transparent; }}
        """)

        root = QFrame(self)
        root.setObjectName("toastRoot")
        root.setGeometry(0, 0, self._W, self._H)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(self._PAD, 8, self._PAD, 8)

        title = QLabel("✦ JAM is starting up…")
        title.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {self._TITLE_FG};")
        layout.addWidget(title)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {self._BORDER};")
        layout.addWidget(divider)

        for key, label_text in self._ROWS:
            row = QHBoxLayout()
            name_lbl = QLabel(label_text)
            name_lbl.setStyleSheet(f"font-size: 11px; color: {self._LOADING_FG};")
            status_lbl = QLabel("loading…")
            status_lbl.setStyleSheet(f"font-size: 11px; color: {self._PENDING_FG};")
            status_lbl.setAlignment(Qt.AlignRight)
            row.addWidget(name_lbl)
            row.addWidget(status_lbl)
            layout.addLayout(row)
            self._labels[key] = status_lbl

        for key, done in self._done.items():
            if done:
                self._labels[key].setText("✓  ready")
                self._labels[key].setStyleSheet(f"font-size: 11px; color: {self._DONE_FG};")

        _track(self)
        self.show()

        if all(self._done.values()):
            QTimer.singleShot(800, self._dismiss)
            return

        for key, event in self._events.items():
            if not self._done[key]:
                threading.Thread(target=self._watch, args=(key, event), daemon=True,
                                  name=f"jam-loading-watcher-{key}").start()

    def _watch(self, key: str, event) -> None:
        event.wait()
        self._key_ready.emit(key)

    def _on_key_ready(self, key: str) -> None:
        self._set_status(key, True)

    def _set_status(self, key: str, done: bool) -> None:
        lbl = self._labels.get(key)
        if lbl is None:
            return
        if done:
            lbl.setText("✓  ready")
            lbl.setStyleSheet(f"font-size: 11px; color: {self._DONE_FG};")
        else:
            lbl.setText("loading…")
            lbl.setStyleSheet(f"font-size: 11px; color: {self._PENDING_FG};")
        self._done[key] = done

        if all(self._done.values()):
            QTimer.singleShot(800, self._dismiss)

    def _dismiss(self) -> None:
        self.close()
        if self._on_all_ready:
            self._on_all_ready()


# ── CardToast ────────────────────────────────────────────────────────────────

class CardToast(QWidget):
    _W, _H, _PAD = 380, 320, 16

    def __init__(self, word: Word, settings, on_confirm, on_discard) -> None:
        super().__init__()
        self._on_confirm = on_confirm
        self._on_discard = on_discard

        _frameless(self)
        self.setFixedSize(self._W, self._H)
        # Positioned higher than the standard toast row since this card is taller
        self.move(*_bottom_right_geometry(self._W, self._H, lift=self._H + 60))

        self.setStyleSheet("""
            QWidget#toastRoot { background-color: #1e1e1e; border: 1px solid #444444; }
            QLabel { background: transparent; }
        """)

        root = QFrame(self)
        root.setObjectName("toastRoot")
        root.setGeometry(0, 0, self._W, self._H)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setStyleSheet("background-color: #2a2a2a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(self._PAD, 8, 8, 8)

        title = QLabel(f"{word.surface}　{word.reading}")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
        header_layout.addWidget(title, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888888; border: none; font-size: 12px; }
            QPushButton:hover { color: #ffffff; }
        """)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self._discard)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)

        # ── Metadata row ──
        meta_parts = []
        if word.pos:
            meta_parts.append(word.pos)
        if word.pitch_pattern is not None:
            cat = f" {word.pitch_category}" if word.pitch_category else ""
            meta_parts.append(f"pitch {word.pitch_pattern}{cat}")
        if word.frequency_rank:
            meta_parts.append(str(word.frequency_rank))
        if word.jlpt_level:
            meta_parts.append(str(word.jlpt_level))

        if meta_parts:
            meta_lbl = QLabel("  ·  ".join(meta_parts))
            meta_lbl.setStyleSheet("font-size: 10px; color: #888888;")
            meta_lbl.setContentsMargins(self._PAD, 4, self._PAD, 4)
            layout.addWidget(meta_lbl)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #333333;")
        layout.addWidget(divider)

        # ── Definition ──
        def_lbl = QLabel(word.meaning or "(no definition)")
        def_lbl.setWordWrap(True)
        def_lbl.setStyleSheet("font-size: 12px; color: #dddddd;")
        def_lbl.setContentsMargins(self._PAD, 6, self._PAD, 6)
        layout.addWidget(def_lbl)

        # ── Sentence + translation ──
        if word.example_sentences:
            sentence    = word.example_sentences[0].get("japanese", "")
            sentence_en = word.example_sentences[0].get("english", "")
        else:
            sentence    = word.full_sentence
            sentence_en = word.sentence_translation

        if sentence:
            sent_lbl = QLabel(f"「{sentence}」")
            sent_lbl.setWordWrap(True)
            sent_lbl.setStyleSheet("font-size: 11px; font-style: italic; color: #aaaaaa;")
            sent_lbl.setContentsMargins(self._PAD, 2, self._PAD, 2)
            layout.addWidget(sent_lbl)

            if sentence_en:
                en_lbl = QLabel(sentence_en)
                en_lbl.setWordWrap(True)
                en_lbl.setStyleSheet("font-size: 10px; color: #666666;")
                en_lbl.setContentsMargins(self._PAD, 0, self._PAD, 0)
                layout.addWidget(en_lbl)

        layout.addStretch(1)

        divider2 = QFrame()
        divider2.setFixedHeight(1)
        divider2.setStyleSheet("background-color: #333333;")
        layout.addWidget(divider2)

        # ── Buttons ──
        btn_row = QFrame()
        btn_row.setStyleSheet("background-color: #1e1e1e;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(self._PAD, 10, self._PAD, 10)

        discard_btn = QPushButton("👎  Discard")
        discard_btn.setCursor(Qt.PointingHandCursor)
        discard_btn.setStyleSheet("""
            QPushButton { background-color: #3a1a1a; color: #ff6b6b; border: none;
                          padding: 6px 16px; font-size: 11px; }
            QPushButton:hover { background-color: #4a2a2a; }
        """)
        discard_btn.clicked.connect(self._discard)
        btn_layout.addWidget(discard_btn)

        confirm_btn = QPushButton("👍  Add to Anki")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setStyleSheet("""
            QPushButton { background-color: #1a3a1a; color: #6bff6b; border: none;
                          padding: 6px 16px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #2a4a2a; }
        """)
        confirm_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(confirm_btn)

        layout.addWidget(btn_row)

        _track(self)
        self.show()
        self.raise_()
        self.activateWindow()

    def _confirm(self) -> None:
        cb = self._on_confirm
        self._on_confirm = None
        self.close()
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _discard(self) -> None:
        cb = self._on_discard
        self._on_discard = None
        self.close()
        if cb:
            threading.Thread(target=cb, daemon=True).start()


# ── DuplicateToast ───────────────────────────────────────────────────────────

def _make_duplicate_toast(surface: str, reading: str) -> _PlainToast:
    toast = _PlainToast(
        "⚠ Already mined", f"{surface}　{reading}",
        bg="#2a1e00", border="#665500", fg="#ffcc44",
        width=300, height=80, dismiss_ms=3000,
    )
    return toast


# ── Signal handlers (connected once, at startup) ──────────────────────────────

def _on_show_loading(ocr_event, parser_event, dict_event, on_all_ready) -> None:
    LoadingToast(ocr_event, parser_event, dict_event, on_all_ready)


def _on_show_ready() -> None:
    _PlainToast(
        "✦ JAM is ready", "Press your hotkey to start mining",
        bg="#1a1a2a", border="#333366", fg="#7b9fff",
        width=320, height=70, dismiss_ms=4000,
    )


def _on_show_card(word, settings, on_confirm, on_discard) -> None:
    CardToast(word, settings, on_confirm, on_discard)


def _on_show_success(surface: str) -> None:
    _PlainToast(
        f"✓ Card added: {surface}", "",
        bg="#1a2a1a", border="#336633", fg="#6bff6b",
        width=300, height=60, dismiss_ms=2500,
    )


def _on_show_duplicate(surface: str, reading: str) -> None:
    _make_duplicate_toast(surface, reading)


def connect_toast_signals() -> None:
    from core.signals import signals
    signals.show_loading.connect(_on_show_loading)
    signals.show_ready.connect(_on_show_ready)
    signals.show_card.connect(_on_show_card)
    signals.show_success.connect(_on_show_success)
    signals.show_duplicate.connect(_on_show_duplicate)