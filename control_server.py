"""Loopback control server for Image Selector — the *bridge* to the live app.

Same design as image-editor/control_server.py: the running app hosts a JSON-lines
server on 127.0.0.1 so an MCP process (mcp_server.py --bridge) can drive the edit
session the user has open. Requests are marshalled onto the Qt GUI thread, so the
EditPanel's widgets and the EditState are only ever touched on the main thread.

The target is the live `EditPanel` (base image + EditState). Commands run through
`panel.apply_command`, which also mirrors the new state back into the sliders.
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

import commands

INFO_PATH = Path.home() / ".cache" / "image-selector" / "control.json"


def _describe_run(cmd_id: str, res: dict) -> str:
    """One-line human summary of a command result, for the agent toast."""
    spec = commands.REGISTRY.get(cmd_id)
    label = spec.label if spec else cmd_id
    if res.get("ok"):
        return f"Claude: {label}"
    return f"Claude: {label} failed — {res.get('error', '')}"


class _Call:
    __slots__ = ("req", "result", "done")

    def __init__(self, req: dict):
        self.req = req
        self.result: dict | None = None
        self.done = threading.Event()


class ControlServer(QObject):
    _dispatch = pyqtSignal(object)

    def __init__(self, panel, host: str = "127.0.0.1", port: int = 0,
                 token: str | None = None, *, autostart: bool = True):
        super().__init__()
        self.panel = panel                       # the live EditPanel
        self.token = token or secrets.token_hex(16)
        self._dispatch.connect(self._run_on_gui)
        self._sock = None
        self.host, self.port = host, port
        self._closed = False
        if autostart:
            self.start(host, port)

    def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(8)
        self.host, self.port = self._sock.getsockname()
        threading.Thread(target=self._accept_loop, name="control-accept", daemon=True).start()
        self._write_info()
        return self.port

    def _write_info(self):
        try:
            INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
            INFO_PATH.write_text(json.dumps(
                {"host": self.host, "port": self.port, "token": self.token}))
            INFO_PATH.chmod(0o600)
        except OSError:
            pass

    def close(self):
        self._closed = True
        try:
            self._sock.close()
        except (OSError, AttributeError):
            pass
        try:
            if INFO_PATH.exists():
                INFO_PATH.unlink()
        except OSError:
            pass

    def _accept_loop(self):
        while not self._closed:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,),
                             name="control-conn", daemon=True).start()

    def _serve(self, conn: socket.socket):
        with conn, conn.makefile("rwb") as f:
            for raw in f:
                try:
                    req = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._write(f, {"ok": False, "error": "invalid JSON"})
                    continue
                if not secrets.compare_digest(str(req.get("token", "")), self.token):
                    self._write(f, {"ok": False, "error": "bad token"})
                    continue
                call = _Call(req)
                self._dispatch.emit(call)
                if not call.done.wait(timeout=120):
                    self._write(f, {"ok": False, "error": "engine timeout"})
                    continue
                self._write(f, call.result)

    @staticmethod
    def _write(f, obj: dict):
        f.write((json.dumps(obj) + "\n").encode("utf-8"))
        f.flush()

    def _run_on_gui(self, call: _Call):
        try:
            call.result = self._handle(call.req)
        except Exception as e:
            call.result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        finally:
            call.done.set()

    def _handle(self, req: dict) -> dict:
        op = req.get("op")
        session = self.panel.registry_session()

        if op == "ping":
            return {"ok": True, "result": {"app": "image-selector",
                                           "hasImage": session is not None}}
        if op == "command_list":
            return {"ok": True, "result": commands.command_list(
                session, filter=req.get("filter"), enabled_only=bool(req.get("enabled_only")))}
        if session is None:
            return {"ok": False, "error": "no image open in the editor"}
        if op == "doc_inspect":
            return {"ok": True, "result": commands.run_command(session, "doc.inspect", {})["result"]}
        if op == "render_preview":
            return {"ok": True, "result": commands.run_command(
                session, "doc.renderPreview", {"max_side": req.get("max_side", 1024)})["result"]}
        if op == "command_run":
            # through the panel so sliders + preview update on the GUI thread
            res = self.panel.apply_command(req.get("id", ""), req.get("params"))
            self._notify(_describe_run(req.get("id", ""), res))
            return {"ok": True, "result": res}
        if op == "command_batch":
            results, completed = [], 0
            for step in req.get("steps", []):
                res = self.panel.apply_command(step.get("id", ""), step.get("params"))
                results.append(res)
                if res.get("ok"):
                    completed += 1
                elif req.get("stop_on_error", True):
                    break
            total = len(req.get("steps", []))
            self._notify(f"Claude ran {completed}/{total} commands")
            return {"ok": True, "result": {"completed": completed,
                                           "total": total, "results": results}}
        return {"ok": False, "error": f"unknown op: {op}"}

    def _notify(self, text: str) -> None:
        """Surface agent activity in the editor, if the panel supports it."""
        note = getattr(self.panel, "note_agent_action", None)
        if callable(note):
            note(text)
