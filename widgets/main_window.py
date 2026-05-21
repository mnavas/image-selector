from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from image_collection import ImageEntry
from widgets.edit_panel import EditPanel
from widgets.info_bar import InfoBar
from widgets.preview_widget import PreviewWidget
from widgets.thumbnail_strip import ThumbnailStrip

if TYPE_CHECKING:
    from app_controller import AppController

_BTN_STYLE = (
    "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555; "
    "padding: 6px 14px; border-radius: 4px; font-size: 13px; }"
    "QPushButton:hover { background-color: #444; }"
    "QPushButton:pressed { background-color: #222; }"
    "QPushButton:disabled { color: #555; }"
)


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Image Selector")
        self.resize(1280, 820)
        self.setStyleSheet("background-color: #111111; color: #dddddd;")

        self._build_ui()
        controller.set_window(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Public interface used by AppController
    # ------------------------------------------------------------------

    def set_folder_labels(self, library_path: str, album_path: str) -> None:
        self._lib_label.setText(f"Library: {library_path}")
        self._alb_label.setText(f"Album: {album_path}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def show_edit_panel(self, entry: ImageEntry, img: np.ndarray) -> None:
        self._edit_panel.load(entry, img)
        self._edit_panel.setGeometry(self.centralWidget().rect())
        self._edit_panel.show()
        self._edit_panel.raise_()
        self._edit_panel.activateWindow()
        self._edit_panel.setFocus(Qt.FocusReason.OtherFocusReason)

    def hide_edit_panel(self) -> None:
        self._edit_panel.hide()
        self.setFocus()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_edit_panel") and self._edit_panel.isVisible():
            self._edit_panel.setGeometry(self.centralWidget().rect())

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Menu bar
        self._build_menu()

        # Folder label row
        folder_row = QWidget()
        fl = QHBoxLayout(folder_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)

        _lbl_style = "color: #888888; font-size: 11px;"
        _chg_style = (
            "QPushButton { background-color: #2a2a2a; color: #888; border: 1px solid #444; "
            "padding: 2px 8px; border-radius: 3px; font-size: 11px; }"
            "QPushButton:hover { background-color: #383838; color: #ccc; }"
            "QPushButton:pressed { background-color: #1a1a1a; }"
        )

        self._lib_label = QLabel("Library: —")
        self._lib_label.setStyleSheet(_lbl_style)
        lib_btn = QPushButton("Change…")
        lib_btn.setStyleSheet(_chg_style)
        lib_btn.setToolTip("Select a different library folder")
        lib_btn.clicked.connect(self._on_change_library)

        self._alb_label = QLabel("Album: —")
        self._alb_label.setStyleSheet(_lbl_style)
        alb_btn = QPushButton("Change…")
        alb_btn.setStyleSheet(_chg_style)
        alb_btn.setToolTip("Select a different album folder")
        alb_btn.clicked.connect(self._on_change_album)

        fl.addWidget(self._lib_label)
        fl.addWidget(lib_btn)
        fl.addStretch()
        fl.addWidget(self._alb_label)
        fl.addWidget(alb_btn)
        root.addWidget(folder_row)

        # Large preview
        self.preview = PreviewWidget()
        self.preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.preview, stretch=1)

        # Info bar
        self.info_bar = InfoBar()
        root.addWidget(self.info_bar)

        # Thumbnail strips
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.library_strip = ThumbnailStrip()
        self.album_strip = ThumbnailStrip()
        splitter.addWidget(self._labeled_strip("LIBRARY", self.library_strip))
        splitter.addWidget(self._labeled_strip("ALBUM", self.album_strip))
        splitter.setSizes([640, 640])
        root.addWidget(splitter)

        # Action bar
        root.addWidget(self._build_action_bar())

        # Wire thumbnail click signals
        self.library_strip.cell_clicked.connect(
            lambda idx: self.controller.set_cursor_in("library", idx)
        )
        self.album_strip.cell_clicked.connect(
            lambda idx: self.controller.set_cursor_in("album", idx)
        )

        # Edit panel — overlays the entire central widget
        self._edit_panel = EditPanel(self.controller, parent=central)
        self._edit_panel.hide()

    def _labeled_strip(self, title: str, strip: ThumbnailStrip) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #666; font-size: 10px; padding-left: 4px;")
        layout.addWidget(lbl)
        layout.addWidget(strip)
        return container

    def _build_action_bar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)

        def btn(label: str, slot, tooltip: str = "") -> QPushButton:
            b = QPushButton(label)
            b.setStyleSheet(_BTN_STYLE)
            b.clicked.connect(slot)
            if tooltip:
                b.setToolTip(tooltip)
            return b

        c = self.controller
        layout.addWidget(btn("← Prev", lambda: c.navigate(-1), "Left arrow"))
        layout.addWidget(btn("→ Next", lambda: c.navigate(+1), "Right arrow"))
        layout.addStretch()
        layout.addWidget(btn("↑ To Album", c.send_to_album, "Up arrow — move to album"))
        layout.addWidget(btn("↓ To Library", c.send_to_library, "Down arrow — move to library"))
        layout.addStretch()
        layout.addWidget(btn("✏ Edit", c.open_edit_mode, "E — open edit mode"))
        layout.addWidget(btn("↻ Rotate", c.quick_rotate, "R — rotate 90° clockwise"))
        layout.addWidget(btn("⟲ Undo", c.undo, "Ctrl+Z"))
        layout.addWidget(btn("🗑 Delete", c.delete_current, "Del — send to trash"))
        return row

    def _build_menu(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("File")

        change_lib = file_menu.addAction("Change Library Folder…")
        change_lib.triggered.connect(self._on_change_library)

        change_alb = file_menu.addAction("Change Album Folder…")
        change_alb.triggered.connect(self._on_change_album)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _on_change_library(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Library Folder", self.controller.library.path or ""
        )
        if not path:
            return
        self.controller.library.load(path)
        self._lib_label.setText(f"Library: {path}")
        self.controller._refresh_collections()
        self._persist_paths()

    def _on_change_album(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Album Folder", self.controller.album.path or ""
        )
        if not path:
            return
        self.controller.album.load(path)
        self._alb_label.setText(f"Album: {path}")
        self.controller._refresh_collections()
        self._persist_paths()

    def _persist_paths(self) -> None:
        from config import Config
        cfg = Config.load()
        cfg.library_path = self.controller.library.path
        cfg.album_path = self.controller.album.path
        cfg.save()

    # ------------------------------------------------------------------
    # Keyboard handling
    # ------------------------------------------------------------------

    def event(self, event: QEvent) -> bool:
        # While edit mode is open, swallow all key events so triage actions
        # can't fire in the background.
        if event.type() == QEvent.Type.KeyPress:
            if self._edit_panel.isVisible():
                self._edit_panel.setFocus()
                self._edit_panel.keyPressEvent(event)  # type: ignore[arg-type]
                return True
            from PyQt6.QtGui import QKeyEvent
            ke: QKeyEvent = event  # type: ignore[assignment]
            if ke.key() == Qt.Key.Key_Tab:
                self.controller.switch_focus()
                return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        c = self.controller

        if key == Qt.Key.Key_Left:
            c.navigate(-1)
        elif key == Qt.Key.Key_Right:
            c.navigate(+1)
        elif key == Qt.Key.Key_Up:
            c.send_to_album()
        elif key == Qt.Key.Key_Down:
            c.send_to_library()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            c.delete_current()
        elif key == Qt.Key.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
            c.undo()
        elif key == Qt.Key.Key_E:
            c.open_edit_mode()
        elif key == Qt.Key.Key_R:
            c.quick_rotate()
        else:
            super().keyPressEvent(event)
