"""Command palette + agent toast tests (image-selector).

The palette drives the live EditPanel through its registry, so running a
param-less command (edit.undo) from the palette must mutate the panel's state and
sliders — the same path the bridge uses, minus the socket.

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
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import commands
from app_controller import AppController
from image_collection import ImageEntry
from widgets.command_palette import CommandPalette
from widgets.edit_panel import EditPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _panel(app, h=120, w=160):
    panel = EditPanel(AppController())
    entry = ImageEntry(path=Path("/tmp/x.png"), filename="x.png", exif_date=None, file_size=1)
    panel.load(entry, np.full((h, w, 3), 120, np.uint8))
    return panel


def _rows(pal):
    return [pal._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(pal._list.count())]


def test_palette_lists_session_commands(app):
    pal = CommandPalette(None, commands.command_list(_panel(app).registry_session()),
                         on_choose=lambda cid: None)
    assert "image.rotate" in _rows(pal)
    assert "filter.set" in _rows(pal)


def test_palette_runner_drives_the_panel(app):
    panel = _panel(app)
    # make an undoable change, then undo it through the palette runner (edit.undo
    # is param-less, so no modal dialog blocks the headless run)
    panel.apply_command("adjust.set", {"key": "contrast", "value": 40})
    assert panel._adjustments._sliders["contrast"].value() == 40
    panel._run_palette_command("edit.undo")
    assert panel._adjustments._sliders["contrast"].value() == 0


def test_fresh_session_reports_disabled_reason(app):
    entries = commands.command_list(commands.Session(base=np.zeros((10, 10, 3), np.uint8)))
    undo = next(e for e in entries if e["id"] == "edit.undo")
    assert undo["enabled"] is False
    assert "undo" in undo["disabledReason"].lower()


def test_agent_toast_on_panel(app):
    panel = _panel(app)
    panel.note_agent_action("Claude: Rotate")
    assert "Rotate" in panel._toast.text()
