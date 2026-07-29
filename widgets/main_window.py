from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import i18n
from i18n import tr
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
        self.setWindowTitle(tr("window_title"))
        self.resize(1280, 820)
        self.setStyleSheet("background-color: #111111; color: #dddddd;")

        self._build_ui()
        controller.set_window(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Public interface used by AppController
    # ------------------------------------------------------------------

    def set_folder_labels(self, library_path: str, album_path: str) -> None:
        self._lib_label.setText(tr("library_label").format(path=library_path))
        self._alb_label.setText(tr("album_label").format(path=album_path))

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

        self._lib_label = QLabel(tr("library_label").format(path="—"))
        self._lib_label.setStyleSheet(_lbl_style)
        lib_btn = QPushButton(tr("change_btn"))
        lib_btn.setStyleSheet(_chg_style)
        lib_btn.setToolTip(tr("tooltip_change_library"))
        lib_btn.clicked.connect(self._on_change_library)

        self._alb_label = QLabel(tr("album_label").format(path="—"))
        self._alb_label.setStyleSheet(_lbl_style)
        alb_btn = QPushButton(tr("change_btn"))
        alb_btn.setStyleSheet(_chg_style)
        alb_btn.setToolTip(tr("tooltip_change_album"))
        alb_btn.clicked.connect(self._on_change_album)

        lang_btn = QPushButton(f"🌐 {tr(f'lang_{i18n.get_language()}')}")
        lang_btn.setStyleSheet(_chg_style)
        lang_btn.setToolTip(tr("menu_language"))
        lang_btn.clicked.connect(self._show_language_menu)

        fl.addWidget(self._lib_label)
        fl.addWidget(lib_btn)
        fl.addStretch()
        fl.addWidget(self._alb_label)
        fl.addWidget(alb_btn)
        fl.addSpacing(12)
        fl.addWidget(lang_btn)
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
        splitter.addWidget(self._labeled_strip(tr("library_strip_title"), self.library_strip))
        splitter.addWidget(self._labeled_strip(tr("album_strip_title"), self.album_strip))
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
        layout.addWidget(btn(tr("btn_prev"), lambda: c.navigate(-1), tr("tooltip_left_arrow")))
        layout.addWidget(btn(tr("btn_next"), lambda: c.navigate(+1), tr("tooltip_right_arrow")))
        layout.addStretch()
        layout.addWidget(btn(tr("btn_to_album"), c.send_to_album, tr("tooltip_to_album")))
        layout.addWidget(btn(tr("btn_to_library"), c.send_to_library, tr("tooltip_to_library")))
        layout.addStretch()
        layout.addWidget(btn(tr("btn_edit"), c.open_edit_mode, tr("tooltip_edit")))
        layout.addWidget(btn(tr("btn_rotate"), c.quick_rotate, tr("tooltip_rotate")))
        layout.addWidget(btn(tr("btn_undo"), c.undo, tr("tooltip_undo")))
        layout.addWidget(btn(tr("btn_delete"), c.delete_current, tr("tooltip_delete")))
        return row

    def _build_menu(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu(tr("menu_file"))

        change_lib = file_menu.addAction(tr("menu_change_library"))
        change_lib.triggered.connect(self._on_change_library)

        change_alb = file_menu.addAction(tr("menu_change_album"))
        change_alb.triggered.connect(self._on_change_album)

        lang_menu = file_menu.addMenu(tr("menu_language"))
        self._populate_language_menu(lang_menu)

    def _populate_language_menu(self, menu) -> None:
        group = QActionGroup(self)
        group.setExclusive(True)
        current = i18n.get_language()
        for code in i18n.available_languages():
            action = menu.addAction(tr(f"lang_{code}"))
            action.setCheckable(True)
            action.setChecked(code == current)
            group.addAction(action)
            action.triggered.connect(lambda checked, c=code: self._on_change_language(c))

    def _show_language_menu(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        self._populate_language_menu(menu)
        sender = self.sender()
        pos = sender.mapToGlobal(sender.rect().bottomLeft())
        menu.exec(pos)

    def _on_change_language(self, code: str) -> None:
        if code == i18n.get_language():
            return
        from config import Config
        cfg = Config.load()
        cfg.language = code
        cfg.save()
        QMessageBox.information(
            self,
            tr("menu_language"),
            tr("restart_required"),
        )

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _on_change_library(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, tr("select_library_folder"), self.controller.library.path or ""
        )
        if not path:
            return
        self.controller.library.load(path)
        self._lib_label.setText(tr("library_label").format(path=path))
        self.controller._refresh_collections()
        self._persist_paths()

    def _on_change_album(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, tr("select_album_folder"), self.controller.album.path or ""
        )
        if not path:
            return
        self.controller.album.load(path)
        self._alb_label.setText(tr("album_label").format(path=path))
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
