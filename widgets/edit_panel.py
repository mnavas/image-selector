from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import os

from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from edit_ops import EditState, apply_pipeline
from widgets.preview_widget import PreviewWidget, _ndarray_to_pixmap

if TYPE_CHECKING:
    from app_controller import AppController
    from image_collection import ImageEntry

_PANEL_STYLE = "background-color: #1a1a1a; color: #dddddd;"
_BTN_STYLE = (
    "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555; "
    "padding: 6px 14px; border-radius: 4px; font-size: 13px; }"
    "QPushButton:hover { background-color: #444; }"
    "QPushButton:pressed { background-color: #222; }"
)
_SMALL_BTN = (
    "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
    "padding: 3px 10px; border-radius: 3px; font-size: 12px; }"
    "QPushButton:hover { background-color: #383838; }"
    "QPushButton:pressed { background-color: #1a1a1a; }"
    "QPushButton:checked { background-color: #1e3a5f; border-color: #4a9eff; color: #fff; }"
)

_PREVIEW_LONG_SIDE = 1600


def _downscale_for_preview(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Return (downscaled_img, scale) where scale = downscaled/original."""
    h, w = img.shape[:2]
    long = max(h, w)
    if long <= _PREVIEW_LONG_SIDE:
        return img, 1.0
    scale = _PREVIEW_LONG_SIDE / long
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA), scale


# ---------------------------------------------------------------------------
# Crop overlay
# ---------------------------------------------------------------------------

_HANDLE_R = 6        # handle radius in pixels
_HANDLE_HIT = 10     # hit radius for click detection


class CropOverlay(QWidget):
    """Transparent overlay drawn on top of EditPreview for interactive cropping."""

    crop_confirmed = pyqtSignal(float, float, float, float)   # normalised x,y,w,h

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._active = False
        self._aspect: float = 1.0   # w/h of original image
        self._img_rect = QRectF()   # image rect in this widget's coords

        # Crop rect in normalised coords (0-1 of image)
        self._nx: float = 0.1
        self._ny: float = 0.1
        self._nw: float = 0.8
        self._nh: float = 0.8

        self._drag_mode: str | None = None   # "move" | "tl" | "tr" | "bl" | "br" | "t" | "b" | "l" | "r"
        self._drag_start: QPointF | None = None
        self._drag_snap: tuple | None = None  # (nx, ny, nw, nh) at drag start

    def activate(self, aspect: float, img_rect: QRectF) -> None:
        self._active = True
        self._aspect = aspect
        self._img_rect = img_rect
        # Reset to full image with correct aspect
        self._nx, self._ny, self._nw, self._nh = 0.0, 0.0, 1.0, 1.0
        self.show()
        self.update()

    def deactivate(self) -> None:
        self._active = False
        self.hide()

    def update_image_rect(self, img_rect: QRectF) -> None:
        self._img_rect = img_rect
        self.update()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _norm_to_widget(self, nx: float, ny: float) -> QPointF:
        r = self._img_rect
        return QPointF(r.x() + nx * r.width(), r.y() + ny * r.height())

    def _widget_to_norm(self, wx: float, wy: float) -> tuple[float, float]:
        r = self._img_rect
        if r.width() == 0 or r.height() == 0:
            return 0.0, 0.0
        return (wx - r.x()) / r.width(), (wy - r.y()) / r.height()

    def _crop_qrect(self) -> QRectF:
        tl = self._norm_to_widget(self._nx, self._ny)
        br = self._norm_to_widget(self._nx + self._nw, self._ny + self._nh)
        return QRectF(tl, br)

    def _handle_positions(self) -> dict[str, QPointF]:
        r = self._crop_qrect()
        cx, cy = r.center().x(), r.center().y()
        return {
            "tl": QPointF(r.left(), r.top()),
            "tr": QPointF(r.right(), r.top()),
            "bl": QPointF(r.left(), r.bottom()),
            "br": QPointF(r.right(), r.bottom()),
            "t":  QPointF(cx, r.top()),
            "b":  QPointF(cx, r.bottom()),
            "l":  QPointF(r.left(), cy),
            "r":  QPointF(r.right(), cy),
        }

    def _hit_handle(self, pos: QPointF) -> str | None:
        for name, pt in self._handle_positions().items():
            if (pos - pt).manhattanLength() <= _HANDLE_HIT:
                return name
        return None

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if not self._active:
            return
        pos = event.position()
        handle = self._hit_handle(pos)
        if handle:
            self._drag_mode = handle
        elif self._crop_qrect().contains(pos):
            self._drag_mode = "move"
        else:
            self._drag_mode = None
            return
        self._drag_start = pos
        self._drag_snap = (self._nx, self._ny, self._nw, self._nh)

    def mouseMoveEvent(self, event) -> None:
        if not self._active or self._drag_mode is None or self._drag_start is None:
            return
        pos = event.position()
        dx_n, dy_n = self._widget_to_norm(
            pos.x() - self._drag_start.x() + self._img_rect.x() + self._drag_snap[0] * self._img_rect.width(),
            pos.y() - self._drag_start.y() + self._img_rect.y() + self._drag_snap[1] * self._img_rect.height(),
        )
        snap = self._drag_snap

        if self._drag_mode == "move":
            dnx, dny = self._widget_to_norm(
                pos.x() - self._drag_start.x() + self._img_rect.x(),
                pos.y() - self._drag_start.y() + self._img_rect.y(),
            )
            nx = max(0.0, min(1.0 - snap[2], snap[0] + dnx))
            ny = max(0.0, min(1.0 - snap[3], snap[1] + dny))
            self._nx, self._ny = nx, ny
        else:
            self._resize_with_handle(pos, snap)

        self.update()

    def _resize_with_handle(self, pos: QPointF, snap: tuple) -> None:
        """Resize the crop rect from a handle drag, keeping aspect ratio locked."""
        nx0, ny0, nw0, nh0 = snap
        pw, ph = self._img_rect.width(), self._img_rect.height()
        if pw == 0 or ph == 0:
            return

        # Current mouse in normalised image coords
        mx = (pos.x() - self._img_rect.x()) / pw
        my = (pos.y() - self._img_rect.y()) / ph

        mode = self._drag_mode

        # Determine which edges are being moved
        move_left = mode in ("tl", "bl", "l")
        move_right = mode in ("tr", "br", "r")
        move_top = mode in ("tl", "tr", "t")
        move_bottom = mode in ("bl", "br", "b")

        nx, ny, nw, nh = nx0, ny0, nw0, nh0

        if move_left:
            new_nx = min(mx, nx0 + nw0 - 0.01)
            new_nw = nw0 + (nx0 - new_nx)
            nx, nw = new_nx, new_nw
        if move_right:
            new_nw = max(0.01, mx - nx0)
            nw = new_nw
        if move_top:
            new_ny = min(my, ny0 + nh0 - 0.01)
            new_nh = nh0 + (ny0 - new_ny)
            ny, nh = new_ny, new_nh
        if move_bottom:
            new_nh = max(0.01, my - ny0)
            nh = new_nh

        # Lock to original aspect ratio
        # Determine the dominant change and adjust the other dimension
        if mode in ("t", "b"):
            # Height changed — adjust width to match aspect
            nw = nh * self._aspect * (ph / pw)
            # Keep horizontally centred
            center_x = nx0 + nw0 / 2
            nx = center_x - nw / 2
        elif mode in ("l", "r"):
            nh = nw * (pw / ph) / self._aspect
            center_y = ny0 + nh0 / 2
            ny = center_y - nh / 2
        else:
            # Corner drag — use the larger delta to drive both
            delta_w = abs(nw - nw0)
            delta_h = abs(nh - nh0)
            if delta_w >= delta_h:
                nh = nw * (pw / ph) / self._aspect
                if move_top:
                    ny = (ny0 + nh0) - nh
            else:
                nw = nh * self._aspect * (ph / pw)
                if move_left:
                    nx = (nx0 + nw0) - nw

        # Clamp to image bounds
        nx = max(0.0, nx)
        ny = max(0.0, ny)
        nw = min(1.0 - nx, max(0.01, nw))
        nh = min(1.0 - ny, max(0.01, nh))

        self._nx, self._ny, self._nw, self._nh = nx, ny, nw, nh

    def mouseReleaseEvent(self, event) -> None:
        self._drag_mode = None
        self._drag_start = None

    def keyPressEvent(self, event) -> None:
        if not self._active:
            return
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.crop_confirmed.emit(self._nx, self._ny, self._nw, self._nh)
        elif event.key() == Qt.Key.Key_Escape:
            self._nx, self._ny, self._nw, self._nh = 0.0, 0.0, 1.0, 1.0
            self.deactivate()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        crop = self._crop_qrect()
        r = QRectF(self.rect())
        mask = QColor(0, 0, 0, 160)

        # Four rectangles around the crop rect — no compositing tricks needed
        painter.fillRect(QRectF(r.left(), r.top(), r.width(), crop.top() - r.top()), mask)
        painter.fillRect(QRectF(r.left(), crop.bottom(), r.width(), r.bottom() - crop.bottom()), mask)
        painter.fillRect(QRectF(r.left(), crop.top(), crop.left() - r.left(), crop.height()), mask)
        painter.fillRect(QRectF(crop.right(), crop.top(), r.right() - crop.right(), crop.height()), mask)

        # Crop border
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        painter.drawRect(crop)

        # Rule-of-thirds grid
        painter.setPen(QPen(QColor(255, 255, 255, 60), 0.8))
        for i in (1, 2):
            x = crop.x() + crop.width() * i / 3
            y = crop.y() + crop.height() * i / 3
            painter.drawLine(QPointF(x, crop.top()), QPointF(x, crop.bottom()))
            painter.drawLine(QPointF(crop.left(), y), QPointF(crop.right(), y))

        # Handles
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in self._handle_positions().values():
            painter.drawEllipse(pt, _HANDLE_R, _HANDLE_R)


# ---------------------------------------------------------------------------
# Edit preview (PreviewWidget + crop overlay child)
# ---------------------------------------------------------------------------

class EditPreview(PreviewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._crop_overlay = CropOverlay(self)
        self._crop_overlay.hide()
        self._crop_overlay.resize(self.size())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._crop_overlay.resize(self.size())
        self._crop_overlay.update_image_rect(self.image_rect())

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)
        self._crop_overlay.update_image_rect(self.image_rect())

    def set_array(self, img: np.ndarray) -> None:
        super().set_array(img)
        self._crop_overlay.update_image_rect(self.image_rect())

    def start_crop(self, aspect: float) -> None:
        self._crop_overlay.activate(aspect, self.image_rect())
        self._crop_overlay.setFocus()

    def stop_crop(self) -> None:
        self._crop_overlay.deactivate()


# ---------------------------------------------------------------------------
# Adjustments panel (6 sliders)
# ---------------------------------------------------------------------------

class AdjustmentsPanel(QWidget):
    changed = pyqtSignal()

    _SLIDERS = [
        ("Brightness", "brightness", -100, 100),
        ("Contrast",   "contrast",   -100, 100),
        ("Exposure",   "exposure",    -30,  30),   # ×0.1 → ±3.0 stops
        ("Saturation", "saturation", -100, 100),
        ("Shadows",    "shadows",    -100, 100),
        ("Highlights", "highlights", -100, 100),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._sliders: dict[str, QSlider] = {}
        self._labels: dict[str, QLabel] = {}

        for display_name, attr, lo, hi in self._SLIDERS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)

            lbl = QLabel(display_name)
            lbl.setFixedWidth(72)
            lbl.setStyleSheet("color: #aaa; font-size: 12px;")

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(lo, hi)
            slider.setValue(0)
            slider.setFixedHeight(18)
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }"
                "QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0; "
                "background: #aaa; border-radius: 6px; }"
                "QSlider::sub-page:horizontal { background: #4a9eff; border-radius: 2px; }"
            )

            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(32)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setStyleSheet("color: #888; font-size: 11px;")

            self._sliders[attr] = slider
            self._labels[attr] = val_lbl

            def _on_change(v, a=attr, vl=val_lbl, is_exp=(attr == "exposure")):
                real = v / 10.0 if is_exp else v
                vl.setText(f"{real:+.1f}" if is_exp else f"{real:+.0f}")
                self.changed.emit()

            slider.valueChanged.connect(_on_change)

            rl.addWidget(lbl)
            rl.addWidget(slider, stretch=1)
            rl.addWidget(val_lbl)
            layout.addWidget(row)

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(_SMALL_BTN)
        reset_btn.clicked.connect(self.reset)
        layout.addWidget(reset_btn)
        layout.addStretch()

    def get_values(self) -> dict[str, float]:
        values = {}
        for attr, slider in self._sliders.items():
            v = slider.value()
            values[attr] = v / 10.0 if attr == "exposure" else float(v)
        return values

    def reset(self) -> None:
        for slider in self._sliders.values():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
        for lbl in self._labels.values():
            lbl.setText("0")
        self.changed.emit()


# ---------------------------------------------------------------------------
# Filter manager dialog
# ---------------------------------------------------------------------------

class FilterManagerDialog(QDialog):
    """Checkbox dialog for showing/hiding individual filters."""

    def __init__(
        self,
        film_filters: list,
        auto_filters: list,
        hidden: set,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Manage Filters")
        self.setModal(True)
        self.setFixedWidth(320)
        self.setStyleSheet(
            "background-color: #1e1e1e; color: #ddd;"
            "QCheckBox { font-size: 14px; padding: 2px 0; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
        )

        self._checks: dict[str, QCheckBox] = {}
        _section = "color: #666; font-size: 10px; padding-top: 8px; padding-bottom: 2px;"
        _btn = (
            "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
            "padding: 4px 12px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #383838; }"
        )
        _ok = (
            "QPushButton { background-color: #1e3a5f; color: #cde; border: 1px solid #4a9eff; "
            "padding: 4px 16px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #264d7a; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(16, 12, 16, 12)

        # Film simulations section
        film_lbl = QLabel("FILM SIMULATIONS")
        film_lbl.setStyleSheet(_section)
        layout.addWidget(film_lbl)

        for key, label in film_filters:
            if key == "original":
                continue
            cb = QCheckBox(label)
            cb.setChecked(key not in hidden)
            self._checks[key] = cb
            layout.addWidget(cb)

        # Auto adjustments section
        auto_lbl = QLabel("AUTO ADJUSTMENTS")
        auto_lbl.setStyleSheet(_section)
        layout.addWidget(auto_lbl)

        for key, label in auto_filters:
            cb = QCheckBox(label)
            cb.setChecked(key not in hidden)
            self._checks[key] = cb
            layout.addWidget(cb)

        layout.addSpacing(8)

        # Convenience buttons
        convenience = QWidget()
        conv_layout = QHBoxLayout(convenience)
        conv_layout.setContentsMargins(0, 0, 0, 0)
        sel_all = QPushButton("Select All")
        sel_all.setStyleSheet(_btn)
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checks.values()])
        clr_all = QPushButton("Clear All")
        clr_all.setStyleSheet(_btn)
        clr_all.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checks.values()])
        conv_layout.addWidget(sel_all)
        conv_layout.addWidget(clr_all)
        conv_layout.addStretch()
        layout.addWidget(convenience)

        layout.addSpacing(4)

        # OK / Cancel
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_btn)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(_ok)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addWidget(btn_row)

    def get_hidden(self) -> set:
        return {key for key, cb in self._checks.items() if not cb.isChecked()}


# ---------------------------------------------------------------------------
# Filters panel (radio buttons)
# ---------------------------------------------------------------------------

class FiltersPanel(QWidget):
    changed = pyqtSignal(str)
    manage_clicked = pyqtSignal()

    _FILM_FILTERS = [
        ("original",      "Original"),
        ("provia",        "Provia"),
        ("velvia",        "Velvia"),
        ("astia",         "Astia"),
        ("classic_chrome","Classic Chrome"),
        ("classic_neg",   "Classic Neg"),
        ("acros",         "Acros"),
        ("eterna",        "Eterna"),
        ("sepia",         "Sepia"),
        ("faded",         "Faded / Matte"),
        ("cross_process", "Cross Process"),
        ("fortia_sp",     "Fortia SP"),
        ("neopan_1600",   "Neopan 1600"),
        ("t64",           "T64 (Tungsten)"),
        ("pro_800z",      "Pro 800Z"),
        ("pro_400h",      "Pro 400H"),
        ("pro_160c",      "Pro 160C"),
        ("pro_160s",      "Pro 160S"),
        ("superia_1600",  "Superia 1600"),
        ("superia_400",   "Superia 400"),
        ("superia_100",   "Superia 100"),
    ]

    _AUTO_FILTERS = [
        ("normalize",   "Normalize (CLAHE)"),
        ("auto_levels", "Auto Levels"),
        ("auto_tone",   "Auto Tone"),
        ("auto_wb",     "Auto White Balance"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        self._hidden: set = set()
        self._group = QButtonGroup(self)
        self._radios: dict[str, QRadioButton] = {}

        _rb_style = "color: #ccc; font-size: 16px;"
        _section_style = "color: #666; font-size: 10px; padding-top: 6px; padding-left: 2px;"

        # "⚙ Manage" button at top
        manage_btn = QPushButton("⚙ Manage")
        manage_btn.setStyleSheet(_SMALL_BTN)
        manage_btn.setFixedHeight(24)
        manage_btn.clicked.connect(self.manage_clicked.emit)
        layout.addWidget(manage_btn)
        layout.addSpacing(4)

        for key, label in self._FILM_FILTERS:
            rb = QRadioButton(label)
            rb.setStyleSheet(_rb_style)
            self._group.addButton(rb)
            self._radios[key] = rb
            layout.addWidget(rb)
            rb.toggled.connect(lambda checked, k=key: self.changed.emit(k) if checked else None)

        self._auto_sep = QLabel("AUTO ADJUSTMENTS")
        self._auto_sep.setStyleSheet(_section_style)
        layout.addWidget(self._auto_sep)

        for key, label in self._AUTO_FILTERS:
            rb = QRadioButton(label)
            rb.setStyleSheet(_rb_style)
            self._group.addButton(rb)
            self._radios[key] = rb
            layout.addWidget(rb)
            rb.toggled.connect(lambda checked, k=key: self.changed.emit(k) if checked else None)

        self._radios["original"].setChecked(True)
        layout.addStretch()

    def get_filter(self) -> str:
        for key, rb in self._radios.items():
            if rb.isChecked():
                return key
        return "original"

    def get_hidden(self) -> set:
        return set(self._hidden)

    def set_hidden(self, hidden: set) -> None:
        self._hidden = hidden
        current = self.get_filter()
        if current in hidden:
            self._radios["original"].blockSignals(True)
            self._radios["original"].setChecked(True)
            self._radios["original"].blockSignals(False)
            self.changed.emit("original")

        for key, rb in self._radios.items():
            rb.setVisible(key not in hidden)

        any_auto_visible = any(key not in hidden for key, _ in self._AUTO_FILTERS)
        self._auto_sep.setVisible(any_auto_visible)

    def reset(self) -> None:
        self._radios["original"].blockSignals(True)
        self._radios["original"].setChecked(True)
        self._radios["original"].blockSignals(False)
        self.changed.emit("original")


# ---------------------------------------------------------------------------
# AI worker thread
# ---------------------------------------------------------------------------

class _AiWorker(QThread):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, img: np.ndarray, prompt: str,
                 api_key: str = "",
                 ollama_model: str = "",
                 ollama_host: str = "http://localhost:11434"):
        super().__init__()
        self._img = img
        self._prompt = prompt
        self._api_key = api_key
        self._ollama_model = ollama_model
        self._ollama_host = ollama_host

    def run(self) -> None:
        try:
            import ai_edit
            b64 = ai_edit.encode_for_api(self._img)
            if self._api_key:
                raw = ai_edit.call_api(b64, self._prompt, self._api_key)
            else:
                raw = ai_edit.call_api_ollama(
                    b64, self._prompt, self._ollama_model, self._ollama_host
                )
            state = ai_edit.parse_edit_state(raw)
            self.result_ready.emit(state)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# EditPanel — the full-screen overlay
# ---------------------------------------------------------------------------

class EditPanel(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.setStyleSheet(_PANEL_STYLE)
        self.hide()

        self._entry: ImageEntry | None = None
        self._original: np.ndarray | None = None   # full-resolution BGR
        self._preview_img: np.ndarray | None = None  # downscaled for live preview
        self._preview_scale: float = 1.0
        self._state = EditState()
        self._crop_active = False

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(50)
        self._debounce.timeout.connect(self._do_update)

        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "gemma3n")
        self._ai_worker: _AiWorker | None = None
        self._ai_pre_state: dict | None = None  # snapshot taken just before AI applies

        # Detect which backend is available
        if self._api_key:
            self._ai_backend = "anthropic"
        else:
            import ai_edit as _ai
            self._ai_backend = "ollama" if _ai.ollama_is_running(self._ollama_host) else "none"

        self._build_ui()

        from config import Config
        cfg = Config.load()
        if cfg.hidden_filters:
            self._filters.set_hidden(set(cfg.hidden_filters))

    # ------------------------------------------------------------------
    # Public interface (called by AppController)
    # ------------------------------------------------------------------

    def load(self, entry: ImageEntry, original_img: np.ndarray) -> None:
        self._entry = entry
        self._original = original_img
        self._preview_img, self._preview_scale = _downscale_for_preview(original_img)
        self._state = EditState()
        self._crop_active = False

        self._adjustments.reset()
        self._filters.reset()
        self._crop_btn.setChecked(False)
        self._preview.stop_crop()
        self._filename_lbl.setText(entry.filename)
        self._ai_pre_state = None
        self._ai_status.setText("")
        self._ai_undo_btn.hide()

        self._do_update()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setStyleSheet("background-color: #222;")
        header.setFixedHeight(40)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 8, 0)

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet(_SMALL_BTN)
        back_btn.clicked.connect(self._on_back)

        self._filename_lbl = QLabel("")
        self._filename_lbl.setStyleSheet("color: #ccc; font-size: 13px;")

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setStyleSheet(_SMALL_BTN)
        self._crop_btn.toggled.connect(self._on_crop_toggled)

        self._apply_crop_btn = QPushButton("✓ Apply Crop")
        self._apply_crop_btn.setStyleSheet(
            "QPushButton { background-color: #1e4a1e; color: #8fdf8f; border: 1px solid #3a7a3a; "
            "padding: 3px 10px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #2a6a2a; }"
            "QPushButton:pressed { background-color: #163616; }"
        )
        self._apply_crop_btn.hide()
        self._apply_crop_btn.clicked.connect(self._commit_crop)

        rot_l_btn = QPushButton("↺ Rotate L")
        rot_l_btn.setStyleSheet(_SMALL_BTN)
        rot_l_btn.setToolTip("Rotate 90° counter-clockwise")
        rot_l_btn.clicked.connect(self._rotate_left)

        rot_r_btn = QPushButton("↻ Rotate R")
        rot_r_btn.setStyleSheet(_SMALL_BTN)
        rot_r_btn.setToolTip("Rotate 90° clockwise")
        rot_r_btn.clicked.connect(self._rotate_right)

        save_btn = QPushButton("Save As…")
        save_btn.setStyleSheet(_BTN_STYLE)
        save_btn.clicked.connect(self._do_save)

        hl.addWidget(back_btn)
        hl.addSpacing(12)
        hl.addWidget(self._filename_lbl)
        hl.addStretch()
        hl.addWidget(rot_l_btn)
        hl.addSpacing(4)
        hl.addWidget(rot_r_btn)
        hl.addSpacing(8)
        hl.addWidget(self._crop_btn)
        hl.addSpacing(4)
        hl.addWidget(self._apply_crop_btn)
        hl.addSpacing(8)
        hl.addWidget(save_btn)
        root.addWidget(header)

        # Main content: preview | right panel
        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self._preview = EditPreview()
        self._preview._crop_overlay.crop_confirmed.connect(self._on_crop_confirmed)
        cl.addWidget(self._preview, stretch=1)

        # Right side panel (scrollable)
        right = QWidget()
        right.setFixedWidth(240)
        right.setStyleSheet("background-color: #1e1e1e; border-left: 1px solid #333;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 8px; border: none; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        rl = QVBoxLayout(scroll_content)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        adj_box = QGroupBox("ADJUSTMENTS")
        adj_box.setStyleSheet(
            "QGroupBox { color: #777; font-size: 10px; border: none; margin-top: 8px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        adj_layout = QVBoxLayout(adj_box)
        adj_layout.setContentsMargins(0, 0, 0, 0)
        self._adjustments = AdjustmentsPanel()
        adj_layout.addWidget(self._adjustments)
        self._adjustments.changed.connect(self._on_state_changed)

        filt_box = QGroupBox("FILTERS")
        filt_box.setStyleSheet(adj_box.styleSheet())
        filt_layout = QVBoxLayout(filt_box)
        filt_layout.setContentsMargins(0, 0, 0, 0)
        self._filters = FiltersPanel()
        filt_layout.addWidget(self._filters)
        self._filters.changed.connect(self._on_filter_changed)
        self._filters.manage_clicked.connect(self._on_manage_filters)

        # AI edit section
        ai_box = QGroupBox("AI EDIT")
        ai_box.setStyleSheet(adj_box.styleSheet())
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setSpacing(6)

        self._ai_prompt = QLineEdit()
        self._ai_prompt.setPlaceholderText("describe the look you want…")
        self._ai_prompt.setStyleSheet(
            "QLineEdit { background: #2a2a2a; color: #ddd; border: 1px solid #444; "
            "border-radius: 3px; padding: 4px 6px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #4a9eff; }"
        )
        self._ai_prompt.returnPressed.connect(self._on_ai_apply)

        ai_btn_row = QWidget()
        ai_btn_layout = QHBoxLayout(ai_btn_row)
        ai_btn_layout.setContentsMargins(0, 0, 0, 0)
        ai_btn_layout.setSpacing(6)

        self._ai_btn = QPushButton("✨ Apply")
        self._ai_btn.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
            "padding: 4px 10px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #383838; color: #ddd; }"
            "QPushButton:pressed { background-color: #1a1a1a; }"
            "QPushButton:disabled { color: #555; border-color: #333; }"
        )
        self._ai_btn.clicked.connect(self._on_ai_apply)

        self._ai_undo_btn = QPushButton("↩ Undo AI")
        self._ai_undo_btn.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
            "padding: 4px 10px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #383838; color: #ddd; }"
            "QPushButton:pressed { background-color: #1a1a1a; }"
        )
        self._ai_undo_btn.clicked.connect(self._on_ai_undo)
        self._ai_undo_btn.hide()

        self._ai_status = QLabel("")
        self._ai_status.setStyleSheet("color: #666; font-size: 11px;")
        self._ai_status.setWordWrap(True)

        if self._ai_backend == "anthropic":
            backend_text = "via Claude (Anthropic)"
            backend_color = "#555"
        elif self._ai_backend == "ollama":
            backend_text = f"via Ollama ({self._ollama_model})"
            backend_color = "#555"
        else:
            backend_text = "No AI backend found — set ANTHROPIC_API_KEY or start Ollama"
            backend_color = "#664"
            self._ai_btn.setEnabled(False)
            self._ai_btn.setToolTip(backend_text)

        ai_backend_lbl = QLabel(backend_text)
        ai_backend_lbl.setStyleSheet(f"color: {backend_color}; font-size: 10px; padding-bottom: 2px;")
        ai_backend_lbl.setWordWrap(True)

        ai_btn_layout.addWidget(self._ai_btn)
        ai_btn_layout.addWidget(self._ai_undo_btn)
        ai_btn_layout.addStretch()

        ai_layout.addWidget(ai_backend_lbl)
        ai_layout.addWidget(self._ai_prompt)
        ai_layout.addWidget(ai_btn_row)
        ai_layout.addWidget(self._ai_status)

        rl.addWidget(adj_box)
        rl.addWidget(filt_box)
        rl.addWidget(ai_box)
        rl.addStretch()

        scroll.setWidget(scroll_content)
        right_layout.addWidget(scroll)

        cl.addWidget(right)
        root.addWidget(content, stretch=1)

    # ------------------------------------------------------------------
    # State change handlers
    # ------------------------------------------------------------------

    def _on_state_changed(self) -> None:
        vals = self._adjustments.get_values()
        self._state.brightness = vals["brightness"]
        self._state.contrast = vals["contrast"]
        self._state.exposure = vals["exposure"]
        self._state.saturation = vals["saturation"]
        self._state.shadows = vals["shadows"]
        self._state.highlights = vals["highlights"]
        self._debounce.start()

    def _on_filter_changed(self, name: str) -> None:
        self._state.filter_name = name
        self._debounce.start()

    def _rotate_left(self) -> None:
        self._state.rotation = (self._state.rotation - 90) % 360
        self._debounce.start()

    def _rotate_right(self) -> None:
        self._state.rotation = (self._state.rotation + 90) % 360
        self._debounce.start()

    def _on_crop_toggled(self, checked: bool) -> None:
        if checked and self._original is not None:
            h, w = self._original.shape[:2]
            self._preview.start_crop(w / h)
            self._crop_active = True
            self._apply_crop_btn.show()
        else:
            self._preview.stop_crop()
            self._crop_active = False
            self._apply_crop_btn.hide()

    def _commit_crop(self) -> None:
        """Called by the Apply Crop button — reads current overlay state and commits."""
        ol = self._preview._crop_overlay
        self._on_crop_confirmed(ol._nx, ol._ny, ol._nw, ol._nh)

    def _on_crop_confirmed(self, nx: float, ny: float, nw: float, nh: float) -> None:
        self._state.crop_rect = (nx, ny, nw, nh)
        self._crop_btn.setChecked(False)   # also hides _apply_crop_btn via toggled signal
        self._debounce.start()

    def _on_manage_filters(self) -> None:
        dlg = FilterManagerDialog(
            FiltersPanel._FILM_FILTERS,
            FiltersPanel._AUTO_FILTERS,
            self._filters.get_hidden(),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            hidden = dlg.get_hidden()
            self._filters.set_hidden(hidden)
            from config import Config
            cfg = Config.load()
            cfg.hidden_filters = list(hidden)
            cfg.save()

    def _snapshot_state(self) -> dict:
        """Capture current sliders + filter + rotation as a plain dict."""
        adj = self._adjustments
        return {
            "brightness":  adj._sliders["brightness"].value(),
            "contrast":    adj._sliders["contrast"].value(),
            "exposure":    adj._sliders["exposure"].value(),   # stored ×10
            "saturation":  adj._sliders["saturation"].value(),
            "shadows":     adj._sliders["shadows"].value(),
            "highlights":  adj._sliders["highlights"].value(),
            "filter_name": self._state.filter_name,
            "rotation":    self._state.rotation,
        }

    def _apply_state_dict(self, state: dict) -> None:
        """Push a state dict (from snapshot or AI response) into sliders + filter."""
        adj = self._adjustments
        for slider in adj._sliders.values():
            slider.blockSignals(True)

        adj._sliders["brightness"].setValue(int(state["brightness"]))
        adj._sliders["contrast"].setValue(int(state["contrast"]))
        # exposure: AI sends float stops, snapshot stores raw ×10 int — handle both
        exp_raw = state["exposure"]
        adj._sliders["exposure"].setValue(
            int(exp_raw * 10) if isinstance(exp_raw, float) and abs(exp_raw) <= 3.0
            else int(exp_raw)
        )
        adj._sliders["saturation"].setValue(int(state["saturation"]))
        adj._sliders["shadows"].setValue(int(state["shadows"]))
        adj._sliders["highlights"].setValue(int(state["highlights"]))

        for attr, lbl in adj._labels.items():
            v = adj._sliders[attr].value()
            lbl.setText(f"{v / 10.0:+.1f}" if attr == "exposure" else f"{v:+.0f}")

        for slider in adj._sliders.values():
            slider.blockSignals(False)

        fname = state.get("filter_name", "original")
        if fname in self._filters._radios:
            self._filters._radios[fname].blockSignals(True)
            self._filters._radios[fname].setChecked(True)
            self._filters._radios[fname].blockSignals(False)
        self._state.filter_name = fname
        self._state.rotation = state.get("rotation", 0)
        self._on_state_changed()

    def _on_ai_apply(self) -> None:
        if self._preview_img is None or self._ai_backend == "none":
            return
        prompt = self._ai_prompt.text().strip()
        if not prompt:
            return
        self._ai_pre_state = self._snapshot_state()   # save before overwriting
        self._ai_undo_btn.hide()
        self._ai_btn.setEnabled(False)
        self._ai_status.setStyleSheet("color: #888; font-size: 11px;")
        self._ai_status.setText("Thinking…")
        self._ai_worker = _AiWorker(
            self._preview_img, prompt,
            api_key=self._api_key,
            ollama_model=self._ollama_model,
            ollama_host=self._ollama_host,
        )
        self._ai_worker.result_ready.connect(self._on_ai_result)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_result(self, state: dict) -> None:
        self._apply_state_dict(state)
        self._ai_btn.setEnabled(True)
        self._ai_status.setStyleSheet("color: #5f5; font-size: 11px;")
        self._ai_status.setText("Applied ✓")
        self._ai_undo_btn.show()

    def _on_ai_undo(self) -> None:
        if self._ai_pre_state is None:
            return
        self._apply_state_dict(self._ai_pre_state)
        self._ai_pre_state = None
        self._ai_undo_btn.hide()
        self._ai_status.setStyleSheet("color: #888; font-size: 11px;")
        self._ai_status.setText("Undone")

    def _on_ai_error(self, message: str) -> None:
        self._ai_btn.setEnabled(True)
        self._ai_status.setStyleSheet("color: #f55; font-size: 11px;")
        self._ai_status.setText(message)
        self._ai_pre_state = None

    def _on_back(self) -> None:
        self.controller.close_edit_mode()

    # ------------------------------------------------------------------
    # Pipeline update
    # ------------------------------------------------------------------

    def _do_update(self) -> None:
        if self._preview_img is None:
            return
        out = apply_pipeline(self._preview_img, self._state)
        self._preview.set_array(out)

    # ------------------------------------------------------------------
    # Save As
    # ------------------------------------------------------------------

    def _do_save(self) -> None:
        if self._entry is None or self._original is None:
            return

        default_path = str(self._entry.path)
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            default_path,
            "Images (*.jpg *.jpeg *.png *.tiff *.tif)",
        )
        if not target:
            return

        target_path = Path(target)
        # If user omitted the extension, inherit the original's extension
        if not target_path.suffix:
            target_path = target_path.with_suffix(self._entry.path.suffix)

        # No second overwrite confirmation — the OS file dialog already asked
        self.controller.save_edit(self._state, target_path)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        mods = event.modifiers()
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._on_back()
        elif key == Qt.Key.Key_S and mods & Qt.KeyboardModifier.ControlModifier:
            self._do_save()
        else:
            super().keyPressEvent(event)
