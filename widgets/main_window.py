from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QAction, QActionGroup

import commands
from PyQt6.QtWidgets import (
    QComboBox,
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
_TOGGLE_STYLE = (
    "QPushButton { background-color: #333; color: #ddd; border: 1px solid #555; "
    "padding: 6px 14px; border-radius: 4px; font-size: 13px; }"
    "QPushButton:hover { background-color: #444; }"
    "QPushButton:checked { background-color: #1e4a1e; border-color: #3a7a3a; color: #8fdf8f; }"
)
_MINI_BTN = (
    "QPushButton { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
    "padding: 2px 8px; border-radius: 3px; font-size: 11px; }"
    "QPushButton:hover { background-color: #383838; color: #ccc; }"
    "QPushButton:pressed { background-color: #1a1a1a; }"
)
_MINI_COMBO = (
    "QComboBox { background-color: #2a2a2a; color: #aaa; border: 1px solid #444; "
    "padding: 2px 6px; border-radius: 3px; font-size: 11px; }"
    "QComboBox:hover { background-color: #383838; }"
    "QComboBox QAbstractItemView { background-color: #2a2a2a; color: #ddd; "
    "selection-background-color: #1e3a5f; }"
)


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(tr("window_title"))
        self.resize(1280, 820)
        self.setStyleSheet("background-color: #111111; color: #dddddd;")

        self._editing = False
        self._build_ui()
        controller.set_window(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._control = None
        self._maybe_start_control_server()

    def _maybe_start_control_server(self):
        """Start the loopback control bridge if IMAGE_SELECTOR_CONTROL is set.

        Value "1" picks a free port; a number binds it. Port+token are written to
        ~/.cache/image-selector/control.json for `mcp_server.py --bridge`.
        """
        import os
        val = os.environ.get("IMAGE_SELECTOR_CONTROL")
        if not val:
            return
        try:
            from control_server import ControlServer
            port = int(val) if val.isdigit() else 0
            self._control = ControlServer(self._edit_panel, port=port)
            print(f"[image-selector] control server on 127.0.0.1:{self._control.port}")
        except Exception as e:
            print(f"[image-selector] control server failed to start: {e}")

    def closeEvent(self, event):
        if self._control is not None:
            self._control.close()
        super().closeEvent(event)

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
        self._editing = True
        self._edit_panel.load(entry, img)
        self._edit_panel.setGeometry(self.centralWidget().rect())
        self._edit_panel.show()
        self._edit_panel.raise_()
        self._edit_panel.activateWindow()
        self._edit_panel.setFocus(Qt.FocusReason.OtherFocusReason)

    def hide_edit_panel(self) -> None:
        self._editing = False
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
        splitter.addWidget(
            self._labeled_strip(
                tr("album_strip_title"), self.album_strip, self._build_album_check_controls()
            )
        )
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

    def _labeled_strip(
        self, title: str, strip: ThumbnailStrip, header_extra: QWidget | None = None
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QWidget()
        hb = QHBoxLayout(header)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(6)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #666; font-size: 10px; padding-left: 4px;")
        hb.addWidget(lbl)
        if header_extra is not None:
            hb.addStretch()
            hb.addWidget(header_extra)
        layout.addWidget(header)
        layout.addWidget(strip)
        return container

    def _build_album_check_controls(self) -> QWidget:
        """Print-check selector for the album: pick a target size, run the check,
        and see which one is currently applied."""
        bar = QWidget()
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(0, 0, 4, 0)
        hb.setSpacing(4)

        self._album_check_status = QLabel("")
        self._album_check_status.setStyleSheet("font-size: 10px; color: #666;")

        self._album_check_combo = QComboBox()
        self._album_check_combo.setStyleSheet(_MINI_COMBO)
        self._album_check_combo.setToolTip(tr("tooltip_album_check"))
        self._album_check_combo.addItem(tr("check_4r"), "4r")
        self._album_check_combo.addItem(tr("check_instax"), "instax")

        run_btn = QPushButton(tr("check_run_btn"))
        run_btn.setStyleSheet(_MINI_BTN)
        run_btn.setToolTip(tr("tooltip_album_check"))
        run_btn.clicked.connect(self._on_run_album_check)

        clear_btn = QPushButton(tr("check_clear_btn"))
        clear_btn.setStyleSheet(_MINI_BTN)
        clear_btn.clicked.connect(self._on_clear_album_check)

        hb.addWidget(self._album_check_status)
        hb.addWidget(self._album_check_combo)
        hb.addWidget(run_btn)
        hb.addWidget(clear_btn)
        return bar

    def _on_run_album_check(self) -> None:
        self.controller.run_album_check(self._album_check_combo.currentData())

    def _on_clear_album_check(self) -> None:
        self.controller.run_album_check("none")

    def update_album_check_status(self, check_id: str, n_fail: int, n_total: int) -> None:
        """Reflect the active album check so the user knows why cells are marked."""
        if check_id not in ("4r", "instax"):
            self._album_check_status.setText(tr("check_status_none"))
            self._album_check_status.setStyleSheet("font-size: 10px; color: #666;")
            return
        idx = self._album_check_combo.findData(check_id)
        name = self._album_check_combo.itemText(idx) if idx >= 0 else check_id
        if n_fail == 0:
            self._album_check_status.setText(tr("check_status_pass").format(name=name))
            self._album_check_status.setStyleSheet("font-size: 10px; color: #6ab86a;")
        else:
            self._album_check_status.setText(
                tr("check_status_fail").format(name=name, count=n_fail)
            )
            self._album_check_status.setStyleSheet("font-size: 10px; color: #ff6b6b;")

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

        self._copy_toggle = QPushButton(tr("btn_copy_mode"))
        self._copy_toggle.setCheckable(True)
        self._copy_toggle.setStyleSheet(_TOGGLE_STYLE)
        self._copy_toggle.setToolTip(tr("tooltip_copy_mode"))
        self._copy_toggle.setChecked(c.copy_mode)
        self._copy_toggle.toggled.connect(self._on_copy_mode_toggled)
        layout.addWidget(self._copy_toggle)

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

        self._build_edit_menus(mb)

    def _build_edit_menus(self, mb) -> None:
        """Generate edit-mode menus straight from the command registry (parity
        with image-editor's menu bar).

        The items act on the live edit session and are enabled only while a photo
        is open in Edit mode. Labels/placement come from each CommandSpec — the
        same table the palette, MCP server and bridge use — so a new command shows
        up here automatically. Running an item routes through the edit panel's
        palette runner (params dialog + apply_command).
        """
        self._edit_menu_actions: list = []               # [(QAction, spec)]
        order = ["Edit", "Image"]
        groups: dict[str, list] = {}
        for spec in commands.REGISTRY.values():
            if not spec.menu:                            # queries etc. aren't menu items
                continue
            groups.setdefault(spec.menu[0], []).append(spec)
        for name in order + [g for g in groups if g not in order]:
            specs = groups.get(name)
            if not specs:
                continue
            menu = mb.addMenu(name)
            menu.setToolTipsVisible(True)                # show disabled reasons
            for spec in specs:
                act = QAction(spec.label, self)
                act.triggered.connect(
                    lambda _checked=False, cid=spec.id: self._run_edit_command(cid))
                menu.addAction(act)
                self._edit_menu_actions.append((act, spec))
            menu.aboutToShow.connect(self._sync_edit_menu)
        self._sync_edit_menu()

    def _sync_edit_menu(self) -> None:
        panel = getattr(self, "_edit_panel", None)       # may not exist yet at build time
        session = panel.registry_session() if (self._editing and panel) else None
        for act, spec in self._edit_menu_actions:
            ok = session is not None and spec.enabled(session)
            act.setEnabled(ok)
            act.setToolTip("" if ok else (
                "open a photo in Edit mode" if session is None
                else spec.disabled_reason(session)))

    def _run_edit_command(self, cmd_id: str) -> None:
        if self._editing and getattr(self, "_edit_panel", None) is not None:
            self._edit_panel._run_palette_command(cmd_id)

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

    def _on_copy_mode_toggled(self, checked: bool) -> None:
        self.controller.copy_mode = checked
        from config import Config
        cfg = Config.load()
        cfg.copy_when_moving = checked
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
