from __future__ import annotations
import sys
from typing import Callable

from PIL import Image
from mss import mss

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore    import Qt, QRect, QPoint, QEventLoop
from PySide6.QtGui     import QPainter, QColor, QPen, QCursor


# ── Overlay window ─────────────────────────────────────────────────────────────

class _BBoxOverlay(QWidget):
    def __init__(self, callback: Callable[[Image.Image], None]) -> None:
        super().__init__()
        self._callback  = callback
        self._origin    = QPoint()
        self._selection = QRect()
        self._dragging  = False

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool                             
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(QCursor(Qt.CrossCursor))

        # Cover the entire virtual desktop (all monitors)
        screen = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(screen)
        self.showFullScreen()

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))

        if not self._selection.isNull():
            # Cut out (un-dim) the selected region so user sees content beneath
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self._selection, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw selection border
            pen = QPen(QColor(100, 200, 255), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(self._selection)

    # ── Mouse events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._origin    = event.position().toPoint()
            self._selection = QRect()
            self._dragging  = True

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._selection = QRect(
                self._origin, event.position().toPoint()
            ).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging  = False
            self.hide()                         
            self._capture_and_callback()
            self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:        
            self.close()

    # ── Capture ────────────────────────────────────────────────────────────────

    def _capture_and_callback(self) -> None:
        rect = self._selection
        if rect.width() < 4 or rect.height() < 4:
            return                              # too small, ignore

        dpr = QApplication.primaryScreen().devicePixelRatio()
        region = {
            "left":   int(rect.x()      * dpr),
            "top":    int(rect.y()      * dpr),
            "width":  int(rect.width()  * dpr),
            "height": int(rect.height() * dpr),
        }

        with mss() as sct:
            raw = sct.grab(region)

        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self._callback(image)


# ── Public API ───────────────────────────────────────────────────────────────

def open_bbox_overlay(callback: Callable[[Image.Image], None]) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = _BBoxOverlay(callback)

    loop = QEventLoop()
    overlay.destroyed.connect(loop.quit)
    overlay.show()
    loop.exec()