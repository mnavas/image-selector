"""Command-registry tests for Image Selector. Run: .venv/bin/python -m pytest tests"""
import base64
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import commands
from commands import Session


def _session(h=64, w=96):
    rng = np.random.default_rng(0)
    return Session(base=rng.integers(0, 256, (h, w, 3), dtype=np.uint8))


def test_command_list_self_describing():
    s = _session()
    ids = {c["id"] for c in commands.command_list(s)}
    assert {"doc.inspect", "adjust.apply", "filter.set", "image.rotate", "edit.undo"} <= ids
    for c in commands.command_list(s):
        assert "params" in c and "enabled" in c and "journal" in c


def test_enabled_reflects_state():
    s = _session()
    by_id = {c["id"]: c for c in commands.command_list(s)}
    assert by_id["edit.undo"]["enabled"] is False
    assert by_id["image.clearCrop"]["enabled"] is False
    assert by_id["adjust.reset"]["enabled"] is False     # state is default
    commands.run_command(s, "adjust.set", {"key": "contrast", "value": 30})
    by_id = {c["id"]: c for c in commands.command_list(s)}
    assert by_id["edit.undo"]["enabled"] is True
    assert by_id["adjust.reset"]["enabled"] is True


def test_adjust_apply_changes_render():
    s = _session()
    before = s.render(1.0).copy()
    res = commands.run_command(s, "adjust.apply", {"exposure": 1.0, "contrast": 40})
    assert res["ok"] and set(res["result"]["applied"]) == {"exposure", "contrast"}
    assert not np.array_equal(before, s.render(1.0))


def test_adjust_apply_rejects_unknown():
    s = _session()
    res = commands.run_command(s, "adjust.apply", {"clarity": 10})
    assert not res["ok"] and "unknown" in res["error"]


def test_filter_set_and_validation():
    s = _session()
    assert commands.run_command(s, "filter.set", {"name": "velvia"})["ok"]
    assert s.state.filter_name == "velvia"
    assert not commands.run_command(s, "filter.set", {"name": "nope"})["ok"]


def test_undo_redo_roundtrip():
    s = _session()
    commands.run_command(s, "adjust.set", {"key": "brightness", "value": 20})
    assert s.state.brightness == 20
    assert commands.run_command(s, "edit.undo", {})["result"]["undone"] is True
    assert s.state.brightness == 0
    assert commands.run_command(s, "edit.redo", {})["result"]["redone"] is True
    assert s.state.brightness == 20


def test_rotate_and_crop():
    s = _session()
    commands.run_command(s, "image.rotate", {"direction": "cw"})
    assert s.state.rotation == 90
    commands.run_command(s, "image.setCrop", {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5})
    assert s.state.crop_rect == (0.1, 0.1, 0.5, 0.5)
    commands.run_command(s, "image.clearCrop", {})
    assert s.state.crop_rect is None


def test_reset_keeps_framing():
    s = _session()
    commands.run_command(s, "image.rotate", {"direction": "cw"})
    commands.run_command(s, "adjust.apply", {"saturation": 50})
    commands.run_command(s, "adjust.reset", {})
    assert s.state.saturation == 0 and s.state.rotation == 90   # tones reset, rotation kept


def test_render_preview_png():
    s = _session(h=400, w=600)
    res = commands.run_command(s, "doc.renderPreview", {"max_side": 128})
    assert res["ok"] and res["result"]["format"] == "png"
    assert max(res["result"]["width"], res["result"]["height"]) == 128
    assert len(base64.b64decode(res["result"]["base64"])) > 0


def test_batch_not_atomic():
    s = _session()
    rep = commands.run_batch(s, [
        {"id": "adjust.set", "params": {"key": "exposure", "value": 0.5}},
        {"id": "adjust.set", "params": {"key": "bogus", "value": 1}},
        {"id": "adjust.set", "params": {"key": "contrast", "value": 20}},
    ], stop_on_error=True)
    assert rep["completed"] == 1 and s.state.exposure == 0.5 and s.state.contrast == 0
