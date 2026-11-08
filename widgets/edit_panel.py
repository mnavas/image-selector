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
    QComboBox,
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
import commands
from i18n import tr
from widgets.agent_toast import AgentToast
from widgets.command_palette import CommandPalette, params_dialog
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
_AUTO_BTN = (
    "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
    "padding: 3px 6px; border-radius: 3px; font-size: 11px; }"
    "QPushButton:hover { background-color: #383838; }"
    "QPushButton:checked { background-color: #1e3a5f; border-color: #4a9eff; color: #fff; }"
)
_SMALL_COMBO = (
    "QComboBox { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
    "padding: 3px 8px; border-radius: 3px; font-size: 12px; }"
    "QComboBox:hover { background-color: #383838; }"
    "QComboBox QAbstractItemView { background-color: #2a2a2a; color: #ddd; "
    "selection-background-color: #1e3a5f; }"
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
        # Start with the largest centred rect that matches the target aspect.
        # aspect is the desired pixel w/h; in normalised image coords the
        # width/height ratio is aspect * (ph / pw).
        pw, ph = img_rect.width(), img_rect.height()
        if pw > 0 and ph > 0:
            ratio_norm = aspect * ph / pw
            if ratio_norm <= 1.0:
                nw, nh = ratio_norm, 1.0
            else:
                nw, nh = 1.0, 1.0 / ratio_norm
            self._nx, self._ny = (1.0 - nw) / 2, (1.0 - nh) / 2
            self._nw, self._nh = nw, nh
        else:
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
        """Return the closest handle within range, not just the first one
        whose hit-circle contains pos — with small crop rects, adjacent
        handles' hit-circles overlap, and picking "first in dict order"
        means a corner silently steals clicks aimed at a mid-edge handle.
        """
        best_name = None
        best_dist = _HANDLE_HIT
        for name, pt in self._handle_positions().items():
            dx, dy = pos.x() - pt.x(), pos.y() - pt.y()
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= best_dist:
                best_dist = dist
                best_name = name
        return best_name

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
        """Resize the crop rect from a handle drag, keeping aspect ratio locked
        to the original image. A mid-edge handle drives one axis and the other
        follows to preserve the ratio (staying centred on the fixed axis); a
        corner drag is driven by whichever axis moved most.
        """
        nx0, ny0, nw0, nh0 = snap
        pw, ph = self._img_rect.width(), self._img_rect.height()
        if pw == 0 or ph == 0:
            return

        # Current mouse in normalised image coords
        mx = (pos.x() - self._img_rect.x()) / pw
        my = (pos.y() - self._img_rect.y()) / ph

        mode = self._drag_mode
        move_left = mode in ("tl", "bl", "l")
        move_right = mode in ("tr", "br", "r")
        move_top = mode in ("tl", "tr", "t")
        move_bottom = mode in ("bl", "br", "b")

        nx, ny, nw, nh = nx0, ny0, nw0, nh0

        if move_left:
            new_nx = min(mx, nx0 + nw0 - 0.01)
            nw = (nx0 + nw0) - new_nx
            nx = new_nx
        if move_right:
            nw = max(0.01, mx - nx0)
        if move_top:
            new_ny = min(my, ny0 + nh0 - 0.01)
            nh = (ny0 + nh0) - new_ny
            ny = new_ny
        if move_bottom:
            nh = max(0.01, my - ny0)

        # Lock to original aspect ratio: adjust the passive dimension to match.
        if mode in ("t", "b"):
            # Height changed — width follows, kept horizontally centred.
            nw = nh * self._aspect * (ph / pw)
            center_x = nx0 + nw0 / 2
            nx = center_x - nw / 2
        elif mode in ("l", "r"):
            nh = nw * (pw / ph) / self._aspect
            center_y = ny0 + nh0 / 2
            ny = center_y - nh / 2
        else:
            # Corner drag — use the larger delta to drive both dimensions.
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
        # Any zoom/pan carried over from adjusting the preview would make
        # image_rect() extend past the visible widget — the crop rect is
        # computed correctly against the full image either way, but the
        # user can only see (and therefore only accurately grab) whatever
        # portion the zoom currently shows, causing every handle drag to
        # look like it's grabbing the wrong point. Always show the full
        # image, fit to the window, while cropping.
        self.reset_zoom()
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
        ("brightness", "brightness", -100, 100),
        ("contrast",   "contrast",   -100, 100),
        ("exposure",   "exposure",    -30,  30),   # ×0.1 → ±3.0 stops
        ("saturation", "saturation", -100, 100),
        ("vibrance",   "vibrance",   -100, 100),
        ("shadows",    "shadows",    -100, 100),
        ("highlights", "highlights", -100, 100),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._sliders: dict[str, QSlider] = {}
        self._labels: dict[str, QLabel] = {}

        for label_key, attr, lo, hi in self._SLIDERS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)

            lbl = QLabel(tr(label_key))
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

        reset_btn = QPushButton(tr("reset_btn"))
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
        camera_filters: list,
        film_filters: list,
        auto_filters: list,
        hidden: set,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("manage_filters_title"))
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

        # Camera profiles section
        cam_lbl = QLabel(tr("section_camera_profiles"))
        cam_lbl.setStyleSheet(_section)
        layout.addWidget(cam_lbl)

        for key, label in camera_filters:
            cb = QCheckBox(label)
            cb.setChecked(key not in hidden)
            self._checks[key] = cb
            layout.addWidget(cb)

        # Film simulations section
        film_lbl = QLabel(tr("film_simulations_title"))
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
        auto_lbl = QLabel(tr("auto_adjustments_title"))
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
        sel_all = QPushButton(tr("select_all_btn"))
        sel_all.setStyleSheet(_btn)
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checks.values()])
        clr_all = QPushButton(tr("clear_all_btn"))
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
        cancel_btn = QPushButton(tr("cancel_btn"))
        cancel_btn.setStyleSheet(_btn)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(tr("ok_btn"))
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
        ("original",      tr("filter_original")),
        ("provia",        tr("filter_provia")),
        ("velvia",        tr("filter_velvia")),
        ("astia",         tr("filter_astia")),
        ("classic_chrome",tr("filter_classic_chrome")),
        ("classic_neg",   tr("filter_classic_neg")),
        ("acros",         tr("filter_acros")),
        ("eterna",        tr("filter_eterna")),
        ("sepia",         tr("filter_sepia")),
        ("faded",         tr("filter_faded")),
        ("cross_process", tr("filter_cross_process")),
        ("fortia_sp",     tr("filter_fortia_sp")),
        ("neopan_1600",   tr("filter_neopan_1600")),
        ("t64",           tr("filter_t64")),
        ("pro_800z",      tr("filter_pro_800z")),
        ("pro_400h",      tr("filter_pro_400h")),
        ("pro_160c",      tr("filter_pro_160c")),
        ("pro_160s",      tr("filter_pro_160s")),
        ("superia_1600",  tr("filter_superia_1600")),
        ("superia_400",   tr("filter_superia_400")),
        ("superia_100",   tr("filter_superia_100")),
    ]

    _AUTO_FILTERS = [
        ("normalize",   tr("filter_normalize")),
        ("auto_levels", tr("filter_auto_levels")),
        ("auto_tone",   tr("filter_auto_tone")),
        ("auto_wb",     tr("filter_auto_wb")),
    ]

    _CAMERA_FILTERS = [
        ("standard",      tr("filter_standard")),
        ("vivid",         tr("filter_vivid")),
        ("neutral",       tr("filter_neutral")),
        ("faithful",      tr("filter_faithful")),
        ("flat",          tr("filter_flat")),
        ("landscape",     tr("filter_landscape")),
        ("portrait",      tr("filter_portrait")),
        ("monochrome",    tr("filter_monochrome")),
        ("high_contrast", tr("filter_high_contrast")),
        ("low_contrast",  tr("filter_low_contrast")),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._hidden: set = set()

        # "⚙ Manage" button at top
        manage_btn = QPushButton(tr("manage_btn"))
        manage_btn.setStyleSheet(_SMALL_BTN)
        manage_btn.setFixedHeight(24)
        manage_btn.clicked.connect(self.manage_clicked.emit)
        layout.addWidget(manage_btn)

        layout.addWidget(QLabel(tr("filter_label")))
        self._combo = QComboBox()
        self._combo.setStyleSheet(_SMALL_COMBO)
        self._combo.setToolTip(tr("tooltip_filter_combo"))
        self._combo.currentIndexChanged.connect(self._on_combo)
        layout.addWidget(self._combo)
        self._rebuild()
        layout.addStretch()

    # -- combo building ----------------------------------------------------

    def _groups(self) -> list:
        """Ordered (section_title | None, [(key,label),...]) groups."""
        return [
            (None, [("original", tr("filter_original"))]),
            (None, self._CAMERA_FILTERS),
            (None, self._FILM_FILTERS),
            # Auto corrections are no longer film looks — they live in their own
            # one-click row (self._auto_btns) and apply independently of the look.
        ]

    def _rebuild(self) -> None:
        current = self.get_filter() if self._combo.count() else "original"
        self._combo.blockSignals(True)
        self._combo.clear()
        for _title, items in self._groups():
            visible = [(k, lbl) for k, lbl in items if k not in self._hidden]
            if not visible:
                continue
            if self._combo.count() > 0:
                self._combo.insertSeparator(self._combo.count())
            for key, label in visible:
                self._combo.addItem(label, key)
        idx = self._combo.findData(current)
        self._combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo.blockSignals(False)

    def _on_combo(self, _index: int) -> None:
        key = self._combo.currentData()
        if key:
            self.changed.emit(key)

    # -- public API (unchanged signatures) ---------------------------------

    def get_filter(self) -> str:
        return self._combo.currentData() or "original"

    def get_hidden(self) -> set:
        return set(self._hidden)

    def set_hidden(self, hidden: set) -> None:
        before = self.get_filter()
        self._hidden = set(hidden)
        self._rebuild()
        if self.get_filter() != before:      # active filter was hidden → reset
            self.changed.emit(self.get_filter())

    def set_filter(self, key: str) -> None:
        """Select a filter by key WITHOUT emitting `changed` (for state restore)."""
        idx = self._combo.findData(key)
        if idx < 0:
            idx = self._combo.findData("original")
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def reset(self) -> None:
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(self._combo.findData("original"))
        self._combo.blockSignals(False)
        self.changed.emit("original")

    # -- keyboard cycling (Up/Down in edit mode) ---------------------------

    def select_next(self) -> None:
        self._step(+1)

    def select_prev(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        n = self._combo.count()
        if n == 0:
            return
        i = self._combo.currentIndex()
        for _ in range(n):                    # skip separators (itemData is None)
            i = (i + delta) % n
            if self._combo.itemData(i) is not None:
                self._combo.setCurrentIndex(i)
                return


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
    # Crop aspect presets shown in the ratio combo. Value is the desired
    # pixel w/h; None means "follow the original image's aspect ratio".
    # 4R is the standard 4×6" print (3:2); Instax Mini's image area is ~4:3.
    _CROP_RATIOS = [
        ("crop_ratio_original", None),
        ("crop_ratio_4r_land", 3 / 2),
        ("crop_ratio_4r_port", 2 / 3),
        ("crop_ratio_instax_land", 4 / 3),
        ("crop_ratio_instax_port", 3 / 4),
    ]

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
        self._session: commands.Session | None = None   # registry view over base+state
        self._crop_active = False
        self._comparing = False                          # press-and-hold before/after
        self._copied_look: dict | None = None            # copy/paste edits across photos

        # Keyboard nudges (e.g. holding ]) coalesce into ONE undo step: the first
        # nudge of a burst snapshots history; the timer closes the burst on a pause.
        self._nudge_timer = QTimer()
        self._nudge_timer.setSingleShot(True)
        self._nudge_timer.setInterval(700)

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
        self._toast = AgentToast(self)

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
        self._session = commands.Session(base=self._original, state=self._state)
        self._crop_active = False

        self._adjustments.reset()
        self._filters.reset()
        self._update_auto_buttons()
        self._crop_btn.setChecked(False)
        self._preview.stop_crop()
        self._filename_lbl.setText(entry.filename)
        self._ai_pre_state = None
        self._ai_status.setText("")
        self._ai_undo_btn.hide()
        self._comparing = False
        # The reset() calls above can emit change signals; a fresh photo starts
        # with an empty history regardless.
        self._session._undo.clear()
        self._session._redo.clear()
        self._update_history_buttons()

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

        back_btn = QPushButton(tr("back_btn"))
        back_btn.setStyleSheet(_SMALL_BTN)
        back_btn.clicked.connect(self._on_back)

        self._filename_lbl = QLabel("")
        self._filename_lbl.setStyleSheet("color: #ccc; font-size: 13px;")

        self._crop_btn = QPushButton(tr("crop_btn"))
        self._crop_btn.setCheckable(True)
        self._crop_btn.setStyleSheet(_SMALL_BTN)
        self._crop_btn.toggled.connect(self._on_crop_toggled)

        self._crop_ratio_combo = QComboBox()
        self._crop_ratio_combo.setStyleSheet(_SMALL_COMBO)
        self._crop_ratio_combo.setToolTip(tr("tooltip_crop_ratio"))
        for label_key, _ in self._CROP_RATIOS:
            self._crop_ratio_combo.addItem(tr(label_key))
        self._crop_ratio_combo.currentIndexChanged.connect(self._on_crop_ratio_changed)

        self._apply_crop_btn = QPushButton(tr("apply_crop_btn"))
        self._apply_crop_btn.setStyleSheet(
            "QPushButton { background-color: #1e4a1e; color: #8fdf8f; border: 1px solid #3a7a3a; "
            "padding: 3px 10px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #2a6a2a; }"
            "QPushButton:pressed { background-color: #163616; }"
        )
        self._apply_crop_btn.hide()
        self._apply_crop_btn.clicked.connect(self._commit_crop)

        rot_l_btn = QPushButton(tr("rotate_left_btn"))
        rot_l_btn.setStyleSheet(_SMALL_BTN)
        rot_l_btn.setToolTip(tr("tooltip_rotate_left"))
        rot_l_btn.clicked.connect(self._rotate_left)

        rot_r_btn = QPushButton(tr("rotate_right_btn"))
        rot_r_btn.setStyleSheet(_SMALL_BTN)
        rot_r_btn.setToolTip(tr("tooltip_rotate_right"))
        rot_r_btn.clicked.connect(self._rotate_right)

        # Edit-mode undo / redo (Session history: discrete edits, one per drag)
        self._undo_btn = QPushButton(tr("edit_undo_btn"))
        self._undo_btn.setStyleSheet(_SMALL_BTN)
        self._undo_btn.setToolTip(tr("tooltip_edit_undo"))
        self._undo_btn.clicked.connect(self._edit_undo)

        self._redo_btn = QPushButton(tr("edit_redo_btn"))
        self._redo_btn.setStyleSheet(_SMALL_BTN)
        self._redo_btn.setToolTip(tr("tooltip_edit_redo"))
        self._redo_btn.clicked.connect(self._edit_redo)

        # Press-and-hold "Before" — show the untouched original while held
        self._compare_btn = QPushButton(tr("compare_btn"))
        self._compare_btn.setStyleSheet(_SMALL_BTN)
        self._compare_btn.setToolTip(tr("tooltip_compare"))
        self._compare_btn.pressed.connect(lambda: self._set_compare(True))
        self._compare_btn.released.connect(lambda: self._set_compare(False))

        save_btn = QPushButton(tr("save_as_btn"))
        save_btn.setStyleSheet(_BTN_STYLE)
        save_btn.clicked.connect(self._do_save)

        hl.addWidget(back_btn)
        hl.addSpacing(12)
        hl.addWidget(self._filename_lbl)
        hl.addStretch()
        hl.addWidget(self._undo_btn)
        hl.addSpacing(2)
        hl.addWidget(self._redo_btn)
        hl.addSpacing(8)
        hl.addWidget(self._compare_btn)
        hl.addSpacing(8)
        hl.addWidget(rot_l_btn)
        hl.addSpacing(4)
        hl.addWidget(rot_r_btn)
        hl.addSpacing(8)
        hl.addWidget(self._crop_btn)
        hl.addSpacing(4)
        hl.addWidget(self._crop_ratio_combo)
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

        # One-click corrections (independent of the film look) — fast while culling.
        auto_box = QGroupBox(tr("auto_title"))
        auto_box.setStyleSheet(
            "QGroupBox { color: #777; font-size: 10px; border: none; margin-top: 8px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        auto_layout = QHBoxLayout(auto_box)
        auto_layout.setContentsMargins(8, 4, 8, 4)
        auto_layout.setSpacing(6)
        self._auto_btns: dict[str, QPushButton] = {}
        # (mode, label key, tooltip key with the hotkey)
        for mode, lbl_key, tip_key in (
            ("auto_tone",   "auto_tone_btn",   "tooltip_auto_tone"),
            ("auto_levels", "auto_levels_btn", "tooltip_auto_levels"),
            ("auto_wb",     "auto_wb_btn",     "tooltip_auto_wb"),
            ("normalize",   "auto_normalize_btn", "tooltip_auto_normalize"),
        ):
            btn = QPushButton(tr(lbl_key))
            btn.setCheckable(True)
            btn.setStyleSheet(_AUTO_BTN)
            btn.setToolTip(tr(tip_key))
            btn.clicked.connect(lambda _checked, m=mode: self._toggle_auto(m))
            self._auto_btns[mode] = btn
            auto_layout.addWidget(btn)
        auto_layout.addStretch()

        adj_box = QGroupBox(tr("adjustments_title"))
        adj_box.setStyleSheet(
            "QGroupBox { color: #777; font-size: 10px; border: none; margin-top: 8px; padding-top: 4px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
        )
        adj_layout = QVBoxLayout(adj_box)
        adj_layout.setContentsMargins(0, 0, 0, 0)
        self._adjustments = AdjustmentsPanel()
        adj_layout.addWidget(self._adjustments)
        self._adjustments.changed.connect(self._on_state_changed)
        # Snapshot state at the START of a drag so one drag = one undo step.
        for _s in self._adjustments._sliders.values():
            _s.sliderPressed.connect(self._push_edit_history)

        filt_box = QGroupBox(tr("filters_title"))
        filt_box.setStyleSheet(adj_box.styleSheet())
        filt_layout = QVBoxLayout(filt_box)
        filt_layout.setContentsMargins(0, 0, 0, 0)
        self._filters = FiltersPanel()
        filt_layout.addWidget(self._filters)
        self._filters.changed.connect(self._on_filter_changed)
        self._filters.manage_clicked.connect(self._on_manage_filters)

        # AI edit section
        ai_box = QGroupBox(tr("ai_edit_title"))
        ai_box.setStyleSheet(adj_box.styleSheet())
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setSpacing(6)

        self._ai_prompt = QLineEdit()
        self._ai_prompt.setPlaceholderText(tr("ai_prompt_placeholder"))
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

        self._ai_btn = QPushButton(tr("ai_apply_btn"))
        self._ai_btn.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
            "padding: 4px 10px; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background-color: #383838; color: #ddd; }"
            "QPushButton:pressed { background-color: #1a1a1a; }"
            "QPushButton:disabled { color: #555; border-color: #333; }"
        )
        self._ai_btn.clicked.connect(self._on_ai_apply)

        self._ai_undo_btn = QPushButton(tr("ai_undo_btn"))
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
            backend_text = tr("ai_backend_anthropic")
            backend_color = "#555"
        elif self._ai_backend == "ollama":
            backend_text = tr("ai_backend_ollama").format(model=self._ollama_model)
            backend_color = "#555"
        else:
            backend_text = tr("ai_backend_none")
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

        # Copy / paste "look" (adjustments + filter) across photos
        look_row = QWidget()
        look_layout = QHBoxLayout(look_row)
        look_layout.setContentsMargins(8, 8, 8, 0)
        look_layout.setSpacing(6)
        self._copy_look_btn = QPushButton(tr("copy_look_btn"))
        self._copy_look_btn.setStyleSheet(_SMALL_BTN)
        self._copy_look_btn.setToolTip(tr("tooltip_copy_look"))
        self._copy_look_btn.clicked.connect(self._copy_look)
        self._paste_look_btn = QPushButton(tr("paste_look_btn"))
        self._paste_look_btn.setStyleSheet(_SMALL_BTN)
        self._paste_look_btn.setToolTip(tr("tooltip_paste_look"))
        self._paste_look_btn.clicked.connect(self._paste_look)
        self._paste_look_btn.setEnabled(False)           # nothing copied yet
        self._album_look_btn = QPushButton(tr("look_batch_btn"))
        self._album_look_btn.setStyleSheet(_SMALL_BTN)
        self._album_look_btn.setToolTip(tr("tooltip_look_batch"))
        self._album_look_btn.clicked.connect(self._apply_look_to_album)
        self._album_look_btn.setEnabled(False)
        look_layout.addWidget(self._copy_look_btn)
        look_layout.addWidget(self._paste_look_btn)
        look_layout.addWidget(self._album_look_btn)
        look_layout.addStretch()

        rl.addWidget(look_row)
        rl.addWidget(auto_box)
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
        self._state.vibrance = vals["vibrance"]
        self._state.shadows = vals["shadows"]
        self._state.highlights = vals["highlights"]
        self._debounce.start()

    def _on_filter_changed(self, name: str) -> None:
        self._push_edit_history()
        self._state.filter_name = name
        self._debounce.start()

    def _rotate_left(self) -> None:
        self.apply_command("image.rotate", {"direction": "ccw"})

    def _rotate_right(self) -> None:
        self.apply_command("image.rotate", {"direction": "cw"})

    # ------------------------------------------------------------------
    # Command registry integration (shared by the GUI and the control bridge)
    # ------------------------------------------------------------------

    def registry_session(self) -> commands.Session | None:
        """The live Session the registry edits (shares this panel's base + state)."""
        if self._original is None:
            return None
        if self._session is None:
            self._session = commands.Session(base=self._original, state=self._state)
        self._session.base = self._original
        self._session.state = self._state
        return self._session

    def apply_command(self, cmd_id: str, params: dict | None = None) -> dict:
        """Run a registry command, then mirror the new state back into the widgets.

        Live slider drags still write state directly (they must not journal per
        tick); discrete actions — rotate here, plus anything an agent sends over
        the bridge — flow through the registry so there is one code path.
        """
        session = self.registry_session()
        if session is None:
            return {"ok": False, "error": "no image"}
        res = commands.run_command(session, cmd_id, params)
        if res.get("ok"):
            self._state = session.state            # pick up replacements (e.g. reset)
            self._sync_widgets_from_state()        # also re-renders via _on_state_changed
            self._update_history_buttons()
        return res

    def _sync_widgets_from_state(self) -> None:
        st = self._state
        self._apply_state_dict({
            "brightness": st.brightness, "contrast": st.contrast,
            "exposure": float(st.exposure), "saturation": st.saturation,
            "vibrance": st.vibrance, "shadows": st.shadows, "highlights": st.highlights,
            "auto_correct": st.auto_correct,
            "filter_name": st.filter_name, "rotation": st.rotation,
        })

    def note_agent_action(self, text: str) -> None:
        """Flash a toast when the agent bridge changes the live edit session."""
        self._toast.show_message(text)

    # ------------------------------------------------------------------
    # Command palette (Ctrl+K)
    # ------------------------------------------------------------------

    def _open_command_palette(self) -> None:
        session = self.registry_session()
        if session is None:
            return
        entries = commands.command_list(session)
        CommandPalette(self, entries, on_choose=self._run_palette_command).exec()

    def _run_palette_command(self, cmd_id: str) -> None:
        spec = commands.REGISTRY.get(cmd_id)
        if spec is None:
            return
        params = params_dialog(self, spec)              # {} when no params, None if cancelled
        if params is None:
            return
        self.apply_command(cmd_id, params)

    # ------------------------------------------------------------------
    # Press-and-hold before/after
    # ------------------------------------------------------------------

    def _set_compare(self, on: bool) -> None:
        """While held, show the untouched original; on release, the edited image."""
        if self._preview_img is None:
            return
        self._comparing = on
        if on:
            self._preview.set_array(self._preview_img)   # the true original (downscaled)
        else:
            self._do_update()

    # ------------------------------------------------------------------
    # Edit-mode history (undo / redo over the Session; one step per edit)
    # ------------------------------------------------------------------

    def _push_edit_history(self) -> None:
        session = self.registry_session()
        if session is not None:
            session.push_history()                       # snapshots current state, clears redo
            self._update_history_buttons()

    def _edit_undo(self) -> None:
        session = self.registry_session()
        if session is not None and session.undo():
            self._state = session.state
            self._sync_widgets_from_state()
            self._update_history_buttons()

    def _edit_redo(self) -> None:
        session = self.registry_session()
        if session is not None and session.redo():
            self._state = session.state
            self._sync_widgets_from_state()
            self._update_history_buttons()

    def _update_history_buttons(self) -> None:
        session = self._session
        self._undo_btn.setEnabled(bool(session and session._undo))
        self._redo_btn.setEnabled(bool(session and session._redo))

    # ------------------------------------------------------------------
    # One-click auto corrections (independent of the film look) + nudges
    # ------------------------------------------------------------------

    def _toggle_auto(self, mode: str) -> None:
        """Apply/clear a one-click correction via the registry (toggles if same)."""
        if self._original is None:
            return
        self.apply_command("image.autoCorrect", {"mode": mode})   # journals one step
        self._update_auto_buttons()

    def _update_auto_buttons(self) -> None:
        active = getattr(self._state, "auto_correct", "none")
        for mode, btn in getattr(self, "_auto_btns", {}).items():
            btn.setChecked(mode == active)

    def _nudge(self, attr: str, delta: int) -> None:
        """Bump one adjustment slider by `delta` slider-units (exposure is ×10)."""
        slider = self._adjustments._sliders.get(attr)
        if slider is None:
            return
        if not self._nudge_timer.isActive():
            self._push_edit_history()                    # one undo step per burst
        self._nudge_timer.start()
        new = max(slider.minimum(), min(slider.maximum(), slider.value() + delta))
        slider.setValue(new)                             # fires _on_state_changed → preview

    def _reset_all(self) -> None:
        """Back to the untouched original (keeps this photo's crop/rotation)."""
        self.apply_command("adjust.reset", {})
        self._update_auto_buttons()

    # ------------------------------------------------------------------
    # Copy / paste "look" (adjustments + filter) across photos
    # ------------------------------------------------------------------

    def _copy_look(self) -> None:
        """Remember this photo's tone adjustments and filter for pasting elsewhere.

        Framing (crop and rotation) is intentionally left out — it is specific to
        each photo, while the tonal "look" is what you want to stamp onto a set.
        """
        look = self._adjustments.get_values()            # exposure in stops (float)
        look["filter_name"] = self._state.filter_name
        look["auto_correct"] = self._state.auto_correct
        self._copied_look = look
        self._paste_look_btn.setEnabled(True)
        self._album_look_btn.setEnabled(True)
        self._toast.show_message(tr("look_copied"), icon="⧉")

    def _look_to_state(self) -> EditState:
        """Build an EditState from the copied look (tones + filter only).

        Framing is deliberately omitted — a batch applies a consistent *look*,
        not one photo's crop or rotation.
        """
        look = self._copied_look or {}
        return EditState(
            brightness=float(look.get("brightness", 0)),
            contrast=float(look.get("contrast", 0)),
            exposure=float(look.get("exposure", 0)),     # stops
            saturation=float(look.get("saturation", 0)),
            vibrance=float(look.get("vibrance", 0)),
            shadows=float(look.get("shadows", 0)),
            highlights=float(look.get("highlights", 0)),
            auto_correct=str(look.get("auto_correct", "none")),
            filter_name=str(look.get("filter_name", "original")),
            rotation=0,
        )

    def _apply_look_to_album(self) -> None:
        """Apply the copied look to every album photo, writing edited copies.

        Hard-to-undo (it writes many files), so it confirms first and never
        overwrites the originals — copies go into an `_edited` subfolder.
        """
        if self._copied_look is None:
            return
        album = self.controller.album
        n = len(album.entries)
        if not album.path or n == 0:
            QMessageBox.information(self, tr("look_batch_title"), tr("look_batch_empty"))
            return
        out_dir = Path(album.path) / "_edited"
        resp = QMessageBox.question(
            self, tr("look_batch_title"),
            tr("look_batch_confirm").format(count=n, dir=out_dir),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        state = self._look_to_state()
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            saved, failed, errors = self.controller.apply_look_to_album(state, out_dir)
        finally:
            self.unsetCursor()

        msg = tr("look_batch_done").format(saved=saved, dir=out_dir)
        if failed:
            msg += tr("look_batch_failed").format(failed=failed)
            if errors:
                msg += "\n" + "\n".join(errors[:5])
        QMessageBox.information(self, tr("look_batch_title"), msg)

    def _paste_look(self) -> None:
        if self._copied_look is None:
            return
        self._push_edit_history()                        # so paste is a single undo step
        state = dict(self._copied_look)
        state["rotation"] = self._state.rotation         # keep this photo's framing
        self._apply_state_dict(state)                    # pushes tones+filter into widgets
        self._update_history_buttons()
        self._toast.show_message(tr("look_pasted"), icon="⤷")

    def _selected_crop_aspect(self) -> float:
        """Desired crop aspect (pixel w/h) for the current combo selection."""
        _, value = self._CROP_RATIOS[self._crop_ratio_combo.currentIndex()]
        if value is not None:
            return value
        h, w = self._original.shape[:2]
        return w / h

    def _on_crop_toggled(self, checked: bool) -> None:
        if checked and self._original is not None:
            self._preview.start_crop(self._selected_crop_aspect())
            self._crop_active = True
            self._apply_crop_btn.show()
        else:
            self._preview.stop_crop()
            self._crop_active = False
            self._apply_crop_btn.hide()

    def _on_crop_ratio_changed(self, _index: int) -> None:
        # Restart the overlay with the new target ratio if we're mid-crop.
        if self._crop_active and self._original is not None:
            self._preview.start_crop(self._selected_crop_aspect())

    def _commit_crop(self) -> None:
        """Called by the Apply Crop button — reads current overlay state and commits."""
        ol = self._preview._crop_overlay
        self._on_crop_confirmed(ol._nx, ol._ny, ol._nw, ol._nh)

    def _on_crop_confirmed(self, nx: float, ny: float, nw: float, nh: float) -> None:
        self._push_edit_history()
        self._state.crop_rect = (nx, ny, nw, nh)
        self._crop_btn.setChecked(False)   # also hides _apply_crop_btn via toggled signal
        self._debounce.start()
        self._update_history_buttons()

    def _on_manage_filters(self) -> None:
        dlg = FilterManagerDialog(
            FiltersPanel._CAMERA_FILTERS,
            FiltersPanel._FILM_FILTERS,
            [],   # auto corrections are now a separate one-click row, not film looks
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
            "vibrance":    adj._sliders["vibrance"].value(),
            "shadows":     adj._sliders["shadows"].value(),
            "highlights":  adj._sliders["highlights"].value(),
            "auto_correct": self._state.auto_correct,
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
        adj._sliders["vibrance"].setValue(int(state.get("vibrance", 0)))
        adj._sliders["shadows"].setValue(int(state["shadows"]))
        adj._sliders["highlights"].setValue(int(state["highlights"]))

        for attr, lbl in adj._labels.items():
            v = adj._sliders[attr].value()
            lbl.setText(f"{v / 10.0:+.1f}" if attr == "exposure" else f"{v:+.0f}")

        for slider in adj._sliders.values():
            slider.blockSignals(False)

        fname = state.get("filter_name", "original")
        self._filters.set_filter(fname)
        self._state.filter_name = fname
        self._state.auto_correct = state.get("auto_correct", "none")
        self._state.rotation = state.get("rotation", 0)
        self._update_auto_buttons()
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
        self._ai_status.setText(tr("ai_thinking"))
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
        self._ai_status.setText(tr("ai_applied"))
        self._ai_undo_btn.show()

    def _on_ai_undo(self) -> None:
        if self._ai_pre_state is None:
            return
        self._apply_state_dict(self._ai_pre_state)
        self._ai_pre_state = None
        self._ai_undo_btn.hide()
        self._ai_status.setStyleSheet("color: #888; font-size: 11px;")
        self._ai_status.setText(tr("ai_undone"))

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
            tr("save_as_title"),
            default_path,
            tr("images_filter"),
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
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if key == Qt.Key.Key_Escape:
            self._on_back()
        elif key == Qt.Key.Key_K and ctrl:
            self._open_command_palette()
        elif key == Qt.Key.Key_S and ctrl:
            self._do_save()
        elif key == Qt.Key.Key_Z and ctrl and shift:
            self._edit_redo()
        elif key == Qt.Key.Key_Z and ctrl:
            self._edit_undo()
        elif key in (Qt.Key.Key_Y,) and ctrl:
            self._edit_redo()
        elif key == Qt.Key.Key_C and ctrl:
            self._copy_look()
        elif key == Qt.Key.Key_V and ctrl:
            self._paste_look()
        elif key == Qt.Key.Key_Backslash:
            if not event.isAutoRepeat():      # hold \ to peek at the original
                self._set_compare(True)
        elif key == Qt.Key.Key_Down:
            self._filters.select_next()   # cycle the filter dropdown, preview updates
        elif key == Qt.Key.Key_Up:
            self._filters.select_prev()
        # --- one-key auto corrections (no modifier): stack on the film look ---
        elif key == Qt.Key.Key_A and not ctrl:
            self._toggle_auto("auto_tone")
        elif key == Qt.Key.Key_L and not ctrl:
            self._toggle_auto("auto_levels")
        elif key == Qt.Key.Key_W and not ctrl:
            self._toggle_auto("auto_wb")
        elif key == Qt.Key.Key_N and not ctrl:
            self._toggle_auto("normalize")
        # --- keyboard tone nudges (hold to repeat; one undo step per burst) ---
        elif key == Qt.Key.Key_BracketLeft:
            self._nudge("exposure", -3)   # −0.3 stop
        elif key == Qt.Key.Key_BracketRight:
            self._nudge("exposure", +3)   # +0.3 stop
        elif key == Qt.Key.Key_Comma:
            self._nudge("contrast", -5)
        elif key == Qt.Key.Key_Period:
            self._nudge("contrast", +5)
        elif key == Qt.Key.Key_Minus:
            self._nudge("vibrance", -10)
        elif key == Qt.Key.Key_Equal:
            self._nudge("vibrance", +10)
        elif key == Qt.Key.Key_0:
            self._reset_all()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Backslash and not event.isAutoRepeat():
            self._set_compare(False)
        else:
            super().keyReleaseEvent(event)
