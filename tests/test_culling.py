"""Culling-workflow tests (image-selector edit panel):
  - edit-mode undo/redo over the Session (one step per discrete edit)
  - copy / paste "look" (adjustments + filter) across photos
  - press-and-hold before/after leaves the edit state untouched

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
from widgets.edit_panel import EditPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _panel(app, h=120, w=160):
    panel = EditPanel(AppController())
    entry = ImageEntry(path=Path("/tmp/x.png"), filename="x.png", exif_date=None, file_size=1)
    panel.load(entry, np.full((h, w, 3), 120, np.uint8))
    return panel


def test_fresh_photo_has_empty_history(app):
    panel = _panel(app)
    assert panel._undo_btn.isEnabled() is False
    assert panel._redo_btn.isEnabled() is False


def test_edit_undo_redo_one_step_per_edit(app):
    panel = _panel(app)
    panel._push_edit_history()                       # what sliderPressed does
    panel._adjustments._sliders["contrast"].setValue(40)
    assert panel._state.contrast == 40
    assert panel._undo_btn.isEnabled() is True

    panel._edit_undo()
    assert panel._state.contrast == 0
    assert panel._adjustments._sliders["contrast"].value() == 0
    assert panel._redo_btn.isEnabled() is True

    panel._edit_redo()
    assert panel._adjustments._sliders["contrast"].value() == 40


def test_copy_paste_look_across_photos(app):
    src = _panel(app)
    src._adjustments._sliders["exposure"].setValue(15)   # +1.5 stops (stored ×10)
    src._filters.set_filter("velvia")
    src._state.filter_name = "velvia"
    src._copy_look()
    assert src._copied_look["filter_name"] == "velvia"
    assert src._copied_look["exposure"] == pytest.approx(1.5)
    assert src._paste_look_btn.isEnabled() is True

    dst = _panel(app)
    dst._copied_look = src._copied_look               # same session shares this in practice
    dst._paste_look_btn.setEnabled(True)
    dst._paste_look()
    assert dst._adjustments._sliders["exposure"].value() == 15
    assert dst._state.filter_name == "velvia"


def test_paste_look_keeps_this_photos_rotation(app):
    dst = _panel(app)
    dst.apply_command("image.rotate", {"direction": "cw"})   # rotation 90, its own framing
    dst._copied_look = {"brightness": 0, "contrast": 20, "exposure": 0.0,
                        "saturation": 0, "shadows": 0, "highlights": 0,
                        "filter_name": "original"}
    dst._paste_look_btn.setEnabled(True)
    dst._paste_look()
    assert dst._state.rotation == 90                  # framing preserved, not reset by paste
    assert dst._adjustments._sliders["contrast"].value() == 20


def test_compare_does_not_mutate_state(app):
    panel = _panel(app)
    panel._adjustments._sliders["brightness"].setValue(60)
    panel._set_compare(True)
    assert panel._comparing is True
    panel._set_compare(False)
    assert panel._comparing is False
    assert panel._state.brightness == 60              # peeking never changed the edit


def _album_controller(dir_path, names=("a.png", "b.png")):
    import cv2
    from app_controller import AppController
    for n in names:
        cv2.imwrite(str(dir_path / n), np.full((40, 60, 3), 100, np.uint8))
    c = AppController()
    c.album.path = str(dir_path)
    c.album.entries = [
        ImageEntry(path=dir_path / n, filename=n, exif_date=None,
                   file_size=(dir_path / n).stat().st_size)
        for n in names
    ]
    return c


def _velvia_state():
    from edit_ops import EditState
    return EditState(brightness=0, contrast=0, exposure=1.0, saturation=0,
                     shadows=0, highlights=0, filter_name="velvia", rotation=0)


def test_batch_look_to_album_writes_copies_not_originals(tmp_path):
    c = _album_controller(tmp_path)
    original = (tmp_path / "a.png").read_bytes()
    out = tmp_path / "_edited"
    saved, failed, errors = c.apply_look_to_album(_velvia_state(), out)
    assert (saved, failed, errors) == (2, 0, [])
    assert (out / "a.png").exists() and (out / "b.png").exists()
    assert (tmp_path / "a.png").read_bytes() == original       # original untouched
    assert (out / "a.png").read_bytes() != original            # look applied


def test_batch_refuses_to_overwrite_originals(tmp_path):
    c = _album_controller(tmp_path)
    # writing into the album folder itself would clobber the sources — all skipped
    saved, failed, errors = c.apply_look_to_album(_velvia_state(), tmp_path)
    assert saved == 0 and failed == 2
    assert all("overwrite" in e for e in errors)
