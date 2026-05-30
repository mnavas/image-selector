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
import json
import os
import shutil
import tempfile
from pathlib import Path

import cv2

# Edit pipeline (pure NumPy/OpenCV, no Qt)
import sys
sys.path.insert(0, str(Path(__file__).parent))

from edit_ops import EditState, apply_pipeline
import ai_edit

from mcp.server.fastmcp import FastMCP

server = FastMCP("image-selector")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_image(path: str):
    img = cv2.imread(path)
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

    ok = cv2.imwrite(tmp_name, out)
    if not ok:
        Path(tmp_name).unlink(missing_ok=True)
        raise RuntimeError(f"cv2.imwrite failed — check the extension: {suffix}")

    shutil.move(tmp_name, str(out_path))
    os.utime(out_path, (stat.st_atime, stat.st_mtime))

    return f"Saved: {out_path}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server.run()
