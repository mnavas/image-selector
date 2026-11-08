"""MCP server for Image Selector — Claude Code integration.

Exposes three tools:
  get_image_info    — dimensions + thumbnail for Claude to inspect
  suggest_edits     — analyse image + user prompt → EditState JSON
  apply_and_save    — apply an EditState JSON and write the result to disk

Run standalone:
  python mcp_server.py

Register with Claude Code:
  claude mcp add image-selector -- python /path/to/image-selector/mcp_server.py
"""
from __future__ import annotations

import base64
import argparse
import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

# Edit pipeline (pure NumPy/OpenCV, no Qt)
import sys
sys.path.insert(0, str(Path(__file__).parent))

import ai_edit
import img_io
import commands
from commands import Session
from edit_ops import EditState, apply_pipeline

from mcp.server.fastmcp import FastMCP

server = FastMCP("image-selector")

# A headless session for the fine-grained command registry (the step-wise
# alternative to the coarse suggest_edits blob). get_image_info / suggest_edits /
# apply_and_save stay as higher-level, file-path helpers.
_session: dict = {"s": None}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

# Bridge mode: forward the command_* tools to a running Image Selector app.
_bridge: dict = {"client": None}
_CONTROL_INFO = Path.home() / ".cache" / "image-selector" / "control.json"


def _sess() -> Session:
    s = _session["s"]
    if s is None:
        raise RuntimeError("No image open. Call doc_open first.")
    return s


class BridgeClient:
    """JSON-lines control-protocol client for a running Image Selector app."""

    def __init__(self, host: str, port: int, token: str):
        self.host, self.port, self.token = host, port, token
        self._conn = self._f = None

    def _connect(self):
        self._conn = socket.create_connection((self.host, self.port), timeout=130)
        self._f = self._conn.makefile("rwb")

    def call(self, op: str, **kw) -> dict:
        req = {"token": self.token, "op": op, **kw}
        for attempt in (1, 2):
            try:
                if self._f is None:
                    self._connect()
                self._f.write((json.dumps(req) + "\n").encode("utf-8"))
                self._f.flush()
                line = self._f.readline()
                if not line:
                    raise ConnectionError("control server closed the connection")
                reply = json.loads(line.decode("utf-8"))
                break
            except (OSError, ValueError):
                self._f = None
                if attempt == 2:
                    raise
        if not reply.get("ok", False):
            raise RuntimeError(reply.get("error", "bridge error"))
        return reply.get("result", {})


def _load_bridge(port=None, token=None, token_file=None) -> BridgeClient:
    host = "127.0.0.1"
    if token_file:
        token = Path(token_file).expanduser().read_text().strip()
    if port is None or token is None:
        info = json.loads(_CONTROL_INFO.read_text())
        host = info.get("host", host)
        port = port if port is not None else int(info["port"])
        token = token if token is not None else info["token"]
    return BridgeClient(host, int(port), token)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_image(path: str):
    img = img_io.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def _api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Export it before starting the MCP server."
        )
    return key


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@server.tool()
def get_image_info(image_path: str) -> dict:
    """Return dimensions, file size, and a small base64 thumbnail of the image.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _read_image(image_path)
    h, w = img.shape[:2]
    file_size_kb = Path(image_path).stat().st_size // 1024
    thumbnail_b64 = ai_edit.encode_for_api(img, max_side=400)
    return {
        "width": w,
        "height": h,
        "file_size_kb": file_size_kb,
        "thumbnail_b64": thumbnail_b64,
    }


@server.tool()
def suggest_edits(image_path: str, prompt: str) -> str:
    """Analyse an image and return a suggested EditState JSON based on the prompt.

    Args:
        image_path: Absolute path to the image file.
        prompt: Natural-language description of the desired look.

    Returns:
        A JSON string with keys: brightness, contrast, exposure, saturation,
        shadows, highlights, filter_name, rotation.
    """
    b64 = ai_edit.img_path_to_b64(image_path)
    raw = ai_edit.call_api(b64, prompt, _api_key())
    state = ai_edit.parse_edit_state(raw)
    return json.dumps(state, indent=2)


@server.tool()
def apply_and_save(image_path: str, state_json: str, output_path: str) -> str:
    """Apply an EditState JSON to a full-resolution image and save the result.

    The original file is never modified. Writes atomically via a temp file.
    Original timestamps are preserved on the output file.

    Args:
        image_path: Absolute path to the source image.
        state_json: JSON string produced by suggest_edits (or hand-edited).
        output_path: Absolute path for the saved result (extension sets format).

    Returns:
        Confirmation message with the output path.
    """
    data = json.loads(state_json)
    state = EditState(
        brightness=float(data.get("brightness", 0)),
        contrast=float(data.get("contrast", 0)),
        exposure=float(data.get("exposure", 0)),
        saturation=float(data.get("saturation", 0)),
        shadows=float(data.get("shadows", 0)),
        highlights=float(data.get("highlights", 0)),
        filter_name=str(data.get("filter_name", "original")),
        rotation=int(data.get("rotation", 0)),
    )

    img = _read_image(image_path)
    stat = os.stat(image_path)
    out = apply_pipeline(img, state)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = out_path.suffix or Path(image_path).suffix
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=out_path.parent)
    os.close(tmp_fd)

    ok = img_io.imwrite(tmp_name, out)
    if not ok:
        Path(tmp_name).unlink(missing_ok=True)
        raise RuntimeError(f"Could not encode the image — check the extension: {suffix}")

    shutil.move(tmp_name, str(out_path))
    os.utime(out_path, (stat.st_atime, stat.st_mtime))

    return f"Saved: {out_path}"


# ---------------------------------------------------------------------------
# Command registry tools — fine-grained, discoverable, step-wise editing
# ---------------------------------------------------------------------------

@server.tool()
def doc_open(image_path: str) -> dict:
    """Open an image as the current editing session (for the command_* tools)."""
    img = _read_image(image_path)
    _session["s"] = Session(base=img)
    return commands.run_command(_session["s"], "doc.inspect", {})["result"]


@server.tool()
def doc_save(output_path: str) -> str:
    """Render the current session at full resolution and save it (atomically)."""
    s = _sess()
    out_path = Path(output_path)
    if out_path.suffix.lower() not in _IMAGE_EXT:
        raise ValueError(f"refusing to write a non-image extension: {out_path.suffix}")
    out = s.render(1.0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=out_path.suffix, dir=out_path.parent)
    os.close(tmp_fd)
    if not img_io.imwrite(tmp_name, out):
        Path(tmp_name).unlink(missing_ok=True)
        raise RuntimeError(f"Could not encode for extension: {out_path.suffix}")
    shutil.move(tmp_name, str(out_path))
    return f"Saved {out.shape[1]}x{out.shape[0]} to {out_path}"


@server.tool()
def command_list(filter: str | None = None, enabled_only: bool = False) -> list:
    """Discover edit commands: ids, params and current enabled state."""
    if _bridge["client"]:
        return _bridge["client"].call("command_list", filter=filter, enabled_only=enabled_only)
    return commands.command_list(_session["s"], filter=filter, enabled_only=enabled_only)


@server.tool()
def command_run(id: str, params: dict | None = None) -> dict:
    """Run one edit command by id (see command_list), e.g. adjust.apply, filter.set."""
    if _bridge["client"]:
        return _bridge["client"].call("command_run", id=id, params=params)
    return commands.run_command(_sess(), id, params)


@server.tool()
def command_batch(steps: list, stop_on_error: bool = True) -> dict:
    """Run ordered edit commands. NOT atomic: earlier successes stay applied."""
    if _bridge["client"]:
        return _bridge["client"].call("command_batch", steps=steps, stop_on_error=stop_on_error)
    return commands.run_batch(_sess(), steps, stop_on_error=stop_on_error)


@server.tool()
def doc_inspect() -> dict:
    """Return the current session's EditState, dimensions and history depth."""
    if _bridge["client"]:
        return _bridge["client"].call("doc_inspect")
    return commands.run_command(_sess(), "doc.inspect", {})["result"]


@server.tool()
def render_preview(max_side: int = 1024) -> dict:
    """Return a bounded base64 PNG of the current edited image."""
    if _bridge["client"]:
        return _bridge["client"].call("render_preview", max_side=max_side)
    return commands.run_command(_sess(), "doc.renderPreview", {"max_side": max_side})["result"]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Image Selector MCP server.")
    ap.add_argument("--bridge", action="store_true",
                    help="drive the live app's editor (reads ~/.cache/image-selector/control.json)")
    ap.add_argument("--control-port", type=int,
                    default=os.environ.get("IMAGE_SELECTOR_CONTROL_PORT"))
    ap.add_argument("--control-token", default=os.environ.get("IMAGE_SELECTOR_CONTROL_TOKEN"))
    ap.add_argument("--control-token-file",
                    default=os.environ.get("IMAGE_SELECTOR_CONTROL_TOKEN_FILE"))
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if args.bridge:
        _bridge["client"] = _load_bridge(args.control_port, args.control_token,
                                         args.control_token_file)
    server.run()


if __name__ == "__main__":
    main()
