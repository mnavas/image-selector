"""Bridge tests for Image Selector — MCP BridgeClient driving a live EditPanel.

Uses a socketpair (no TCP bind) to exercise the full path: BridgeClient <->
ControlServer._serve <-> queued GUI-thread dispatch <-> EditPanel.apply_command.
Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests
"""
import os
import socket
import sys
import threading
import time
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


def _panel_with_image(app, h=180, w=240):
    panel = EditPanel(AppController())
    entry = ImageEntry(path=Path("/tmp/x.png"), filename="x.png", exif_date=None, file_size=1)
    panel.load(entry, np.full((h, w, 3), 120, np.uint8))
    return panel


def _pump_until(app, predicate, timeout=10.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.003)


def test_bridge_drives_live_edit_panel(app):
    from control_server import ControlServer
    import mcp_server as M

    panel = _panel_with_image(app)
    srv = ControlServer(panel, autostart=False)
    sa, sb = socket.socketpair()
    threading.Thread(target=srv._serve, args=(sa,), daemon=True).start()

    client = M.BridgeClient("x", 0, srv.token)
    client._conn = sb
    client._f = sb.makefile("rwb")

    out = {}

    def drive():
        try:
            out["ping"] = client.call("ping")
            out["adjust"] = client.call("command_run", id="adjust.apply",
                                        params={"exposure": 1.5, "contrast": 40})
            out["filter"] = client.call("command_run", id="filter.set",
                                        params={"name": "velvia"})
            out["rotate"] = client.call("command_run", id="image.rotate",
                                        params={"direction": "cw"})
            out["inspect"] = client.call("doc_inspect")
            out["preview"] = client.call("render_preview", max_side=64)
        except Exception as e:                   # pragma: no cover
            out["error"] = repr(e)
        finally:
            out["done"] = True

    threading.Thread(target=drive, daemon=True).start()
    _pump_until(app, lambda: out.get("done"))

    assert "error" not in out, out.get("error")
    assert out["ping"]["hasImage"] is True
    assert out["inspect"]["state"]["filter_name"] == "velvia"
    assert out["inspect"]["state"]["rotation"] == 90
    assert out["preview"]["format"] == "png"
    # the bridge mutated the REAL panel: its live state AND sliders updated
    assert panel._state.filter_name == "velvia" and panel._state.rotation == 90
    assert panel._adjustments._sliders["exposure"].value() == 15   # stops×10
    assert panel._adjustments._sliders["contrast"].value() == 40


def test_bridge_rejects_bad_token(app):
    from control_server import ControlServer
    import mcp_server as M

    panel = _panel_with_image(app)
    srv = ControlServer(panel, autostart=False)
    sa, sb = socket.socketpair()
    threading.Thread(target=srv._serve, args=(sa,), daemon=True).start()

    client = M.BridgeClient("x", 0, "WRONG")
    client._conn = sb
    client._f = sb.makefile("rwb")
    out = {}

    def drive():
        try:
            client.call("doc_inspect")
        except RuntimeError as e:
            out["err"] = str(e)
        finally:
            out["done"] = True

    threading.Thread(target=drive, daemon=True).start()
    _pump_until(app, lambda: out.get("done"))
    assert "bad token" in out.get("err", "")
