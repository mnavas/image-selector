from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget


def _ndarray_to_pixmap(img: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qi = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qi)


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setStyleSheet("background-color: #1a1a1a;")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0
        self._pan: QPointF = QPointF(0.0, 0.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, path: Path | None) -> None:
        if path is None:
            self._pixmap = None
            self.reset_zoom()
            self.update()
            return
        img = cv2.imread(str(path))
        if img is None:
            self._pixmap = None
            self.reset_zoom()
            self.update()
            return
        self._pixmap = _ndarray_to_pixmap(img)
        self.reset_zoom()
        self.update()

    def set_array(self, img: np.ndarray) -> None:
        """Set image from a numpy BGR array without resetting zoom."""
        self._pixmap = _ndarray_to_pixmap(img)
        self.update()

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    def image_rect(self) -> QRectF:
        """Return the rectangle (in widget coords) where the image is drawn."""
        if self._pixmap is None:
            return QRectF()
        return self._compute_draw_rect()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pixmap is None:
            return
        rect = self._compute_draw_rect()
        painter.drawPixmap(rect.toRect(), self._pixmap)

    def _compute_draw_rect(self) -> QRectF:
        """Compute the destination rectangle for the pixmap given current zoom/pan."""
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()

        fit_scale = min(ww / pw, wh / ph)
        draw_w = pw * fit_scale * self._zoom
        draw_h = ph * fit_scale * self._zoom

        cx = (ww - draw_w) / 2 + self._pan.x()
        cy = (wh - draw_h) / 2 + self._pan.y()

        return QRectF(cx, cy, draw_w, draw_h)

    # ------------------------------------------------------------------
    # Zoom / Pan events
    # ------------------------------------------------------------------

    def wheelEvent(self, event) -> None:
        if self._pixmap is None:
            return
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = max(0.1, min(8.0, self._zoom * factor))
        if new_zoom == self._zoom:
            return

        pos = QPointF(event.position())
        rect = self._compute_draw_rect()
        rx = (pos.x() - rect.x()) / rect.width()
        ry = (pos.y() - rect.y()) / rect.height()

        self._zoom = new_zoom

        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        fit_scale = min(ww / pw, wh / ph)
        draw_w = pw * fit_scale * self._zoom
        draw_h = ph * fit_scale * self._zoom
        new_x = pos.x() - rx * draw_w
        new_y = pos.y() - ry * draw_h
        self._pan = QPointF(
            new_x - (ww - draw_w) / 2,
            new_y - (wh - draw_h) / 2,
        )
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset_zoom()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_pan = QPointF(self._pan)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag_start"):
            delta = event.position() - self._drag_start
            self._pan = self._drag_pan + delta
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if hasattr(self, "_drag_start"):
            del self._drag_start
