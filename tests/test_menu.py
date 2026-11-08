"""Registry-generated edit menu bar (image-selector main window).

The Edit/Image menus are generated from the command registry and are enabled
only while a photo is open in Edit mode; running an item routes through the edit
panel's palette runner.

Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python -m pytest tests
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from app_controller import AppController
from image_collection import ImageEntry
from widgets.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _win(app):
    return MainWindow(AppController())


def _open(win):
    win.show_edit_panel(
        ImageEntry(path=Path("/tmp/x.png"), filename="x.png", exif_date=None, file_size=1),
        np.full((120, 160, 3), 120, np.uint8))


def test_registry_menus_exist(app):
    win = _win(app)
    titles = [a.menu().title() for a in win.menuBar().actions() if a.menu()]
    assert "Edit" in titles and "Image" in titles
    ids = {spec.id for _a, spec in win._edit_menu_actions}
    assert {"image.rotate", "filter.set", "edit.undo"} <= ids


def test_menu_disabled_until_editing(app):
    win = _win(app)
    win._sync_edit_menu()
    states = {s.id: a.isEnabled() for a, s in win._edit_menu_actions}
    assert states["image.rotate"] is False              # not editing yet

    _open(win)
    win._sync_edit_menu()
    states = {s.id: a.isEnabled() for a, s in win._edit_menu_actions}
    assert states["image.rotate"] is True
    assert states["edit.undo"] is False                 # fresh session: nothing to undo
    assert states["image.clearCrop"] is False           # no crop set

    win.hide_edit_panel()
    win._sync_edit_menu()
    assert {s.id: a.isEnabled() for a, s in win._edit_menu_actions}["image.rotate"] is False


def test_menu_item_routes_to_edit_panel(app):
    win = _win(app)
    _open(win)
    win._edit_panel.apply_command("adjust.set", {"key": "contrast", "value": 30})
    assert win._edit_panel._state.contrast == 30
    win._run_edit_command("edit.undo")                  # param-less -> runs immediately
    assert win._edit_panel._state.contrast == 0
