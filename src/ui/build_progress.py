from __future__ import annotations
import sys
import threading

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar,
)
from PySide6.QtCore import Qt, Signal


class BuildProgressWindow(QWidget):
    _step_signal  = Signal(str, float)
    _close_signal = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JAM — Building Dictionary Database")
        self.setFixedSize(500, 140)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self._step_signal.connect(self._apply_step)
        self._close_signal.connect(self.close)

        # Center on the primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.x() + (screen.width()  - self.width())  // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        title = QLabel("Building dictionary database (first run only)")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self._step_label = QLabel("Starting...")
        self._step_label.setStyleSheet("color: #555555; font-size: 11px;")
        layout.addWidget(self._step_label)

        layout.addSpacing(8)

        bar_row = QVBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(True)
        bar_row.addWidget(self._progress)
        layout.addLayout(bar_row)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

    def set_step(self, text: str, pct: float) -> None:
        self._step_signal.emit(text, pct)

    def _apply_step(self, text: str, pct: float) -> None:
        self._step_label.setText(text)
        self._progress.setValue(int(pct))

    def close_when_done(self) -> None:
        self._close_signal.emit()


def run_with_progress_ui(build_fn) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    win = BuildProgressWindow()
    win.show()

    def _run_build():
        try:
            build_fn(win)
        finally:
            win.close_when_done()

    build_thread = threading.Thread(target=_run_build, daemon=True)
    build_thread.start()

    app.exec()
    build_thread.join()