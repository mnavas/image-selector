"""Quick-edit tests — ideas mined from PhotoCraft, adapted to the culling app:
  - one-click auto corrections live in their OWN slot, independent of the film
    look (they used to share `filter_name` and were mutually exclusive)
  - Vibrance: saturation that protects already-saturated pixels
  - keyboard tone nudges coalesce into one undo step per burst
  - `0` resets to the untouched original

Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python -m pytest tests
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from edit_ops import EditState, apply_pipeline, apply_vibrance

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from app_controller import AppController
from image_collection import ImageEntry
from widgets.edit_panel import EditPanel
import commands


# ---------------------------------------------------------------------------
# Model level (no Qt)
# ---------------------------------------------------------------------------

def test_old_auto_filter_migrates_to_its_own_slot():
    # a state saved when autos lived in filter_name still renders the same
    s = EditState(filter_name="auto_tone")
    assert s.auto_correct == "auto_tone"
    assert s.filter_name == "original"


def test_is_default_accounts_for_new_fields():
    assert EditState().is_default() is True
    assert EditState(vibrance=5).is_default() is False
    assert EditState(auto_correct="auto_wb").is_default() is False


def test_auto_correction_and_film_look_stack():
    img = np.random.default_rng(0).integers(0, 256, (60, 80, 3)).astype(np.uint8)
    only_auto = apply_pipeline(img, EditState(auto_correct="auto_tone"))
    only_film = apply_pipeline(img, EditState(filter_name="velvia"))
    both = apply_pipeline(img, EditState(auto_correct="auto_tone", filter_name="velvia"))
    assert not np.array_equal(only_auto, only_film)
    # applying both differs from either alone — they are no longer exclusive
    assert not np.array_equal(both, only_auto)
    assert not np.array_equal(both, only_film)


def test_vibrance_protects_already_saturated_pixels():
    px = np.zeros((2, 1, 3), np.uint8)
    px[0, 0] = [180, 150, 120]   # low-saturation
    px[1, 0] = [255, 0, 0]       # already fully saturated
    before = cv2.cvtColor(px, cv2.COLOR_BGR2HSV)[:, :, 1].flatten().astype(int)
    after = cv2.cvtColor(apply_vibrance(px, 80), cv2.COLOR_BGR2HSV)[:, :, 1].flatten().astype(int)
    assert (after[0] - before[0]) > (after[1] - before[1])   # low-sat gains more


def test_registry_exposes_vibrance_and_auto_correct():
    base = np.full((40, 60, 3), 120, np.uint8)
    s = commands.Session(base=base)
    assert commands.run_command(s, "adjust.set", {"key": "vibrance", "value": 30})["ok"]
    assert s.state.vibrance == 30
    assert commands.run_command(s, "image.autoCorrect", {"mode": "auto_wb"})["ok"]
    assert s.state.auto_correct == "auto_wb"


# ---------------------------------------------------------------------------
# Panel level (Qt offscreen)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _panel(app, h=60, w=80):
    panel = EditPanel(AppController())
    entry = ImageEntry(path=Path("/tmp/x.png"), filename="x.png", exif_date=None, file_size=1)
    panel.load(entry, np.full((h, w, 3), 120, np.uint8))
    return panel


def test_toggle_auto_sets_state_and_button(app):
    panel = _panel(app)
    panel._toggle_auto("auto_tone")
    assert panel._state.auto_correct == "auto_tone"
    assert panel._auto_btns["auto_tone"].isChecked() is True
    panel._toggle_auto("auto_tone")                      # same key toggles off
    assert panel._state.auto_correct == "none"
    assert panel._auto_btns["auto_tone"].isChecked() is False


def test_auto_stacks_with_film_look_in_panel(app):
    panel = _panel(app)
    panel._toggle_auto("auto_tone")
    panel._on_filter_changed("velvia")
    assert panel._state.auto_correct == "auto_tone"
    assert panel._state.filter_name == "velvia"          # both held at once
    panel._toggle_auto("auto_tone")
    assert panel._state.filter_name == "velvia"          # dropping the auto keeps the look


def test_nudges_coalesce_into_one_undo_step(app):
    panel = _panel(app)
    before = len(panel._session._undo)
    panel._nudge("exposure", 3)
    panel._nudge("exposure", 3)
    panel._nudge("exposure", 3)
    assert len(panel._session._undo) - before == 1       # one burst = one step
    assert panel._state.exposure == pytest.approx(0.9)   # 3 × 0.3 stops


def test_reset_all_returns_to_original(app):
    panel = _panel(app)
    panel._toggle_auto("auto_wb")
    panel._nudge("contrast", 10)
    assert panel._state.is_default() is False
    panel._reset_all()
    assert panel._state.is_default() is True
    assert panel._auto_btns["auto_wb"].isChecked() is False


def test_copied_look_carries_vibrance_and_auto(app):
    src = _panel(app)
    src._adjustments._sliders["vibrance"].setValue(40)
    src._toggle_auto("auto_levels")
    src._copy_look()
    assert src._copied_look["vibrance"] == pytest.approx(40)
    assert src._copied_look["auto_correct"] == "auto_levels"

    dst = _panel(app)
    dst._copied_look = src._copied_look
    dst._paste_look_btn.setEnabled(True)
    dst._paste_look()
    assert dst._state.vibrance == pytest.approx(40)
    assert dst._state.auto_correct == "auto_levels"
