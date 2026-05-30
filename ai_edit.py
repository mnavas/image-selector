"""AI-assisted edit suggestions via the Anthropic API.

Pure Python — no Qt imports. Used by both EditPanel (in-app) and
mcp_server.py (headless Claude Code integration).
"""
from __future__ import annotations

import base64
import json
import re

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

EDIT_MODEL = "claude-opus-4-7"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a photo editing assistant.
The user will describe the look they want for the attached image.
Analyse the image carefully, then return ONLY a JSON object — no markdown,
no explanation, no code fences — that matches this schema exactly:

{
  "brightness":  <float, -100 to 100>,
  "contrast":    <float, -100 to 100>,
  "exposure":    <float, -3.0 to 3.0>,
  "saturation":  <float, -100 to 100>,
  "shadows":     <float, -100 to 100>,
  "highlights":  <float, -100 to 100>,
  "filter_name": <string — one of the values listed below>,
  "rotation":    <integer — one of: 0, 90, 180, 270>
}

Valid filter_name values:
  "original"     — no film simulation
  "provia"       — slight S-curve, neutral colours
  "velvia"       — punchy contrast, high saturation, warm
  "astia"        — lifted shadows, gentle contrast, natural skin
  "classic_chrome" — lifted blacks, cool, desaturated
  "classic_neg"  — warm shadows, cyan highlights, high contrast
  "acros"        — rich black-and-white
  "eterna"       — flat cinematic, muted colours
  "sepia"        — warm brown monochrome
  "faded"        — lifted blacks, reduced contrast, slightly cool
  "cross_process" — vivid cross-channel colour shifts
  "fortia_sp"    — ultra-vivid saturation, more extreme than velvia
  "neopan_1600"  — high-contrast black-and-white, deep blacks
  "t64"          — strong blue/cool cast (tungsten film in daylight)
  "pro_800z"     — warm portrait negative, lifted shadows
  "pro_400h"     — soft pastel portrait, very low contrast
  "pro_160c"     — natural daylight negative, slightly warm
  "pro_160s"     — like pro_160c but cooler and more neutral
  "superia_1600" — warm high-ISO consumer, pushed and contrasty
  "superia_400"  — warm consumer film, slight green cast
  "superia_100"  — clean slow consumer film, barely warm
  "normalize"    — adaptive histogram equalisation (CLAHE)
  "auto_levels"  — stretch each channel to full range
  "auto_tone"    — stretch luminance only
  "auto_wb"      — grey-world white balance correction

Rules:
- All numeric values must be within their stated range. Do not add fields.
- Set "rotation" to 0 unless the user explicitly asks to rotate.
- Set "filter_name" to "original" if no film simulation is needed.
- For black-and-white requests prefer "acros" or "neopan_1600" over
  setting saturation to -100.
- Base your response on both the image content AND the user's description.
- Return nothing except the JSON object.
"""

# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

_VALID_FILTERS = {
    "original", "provia", "velvia", "astia", "classic_chrome", "classic_neg",
    "acros", "eterna", "sepia", "faded", "cross_process", "fortia_sp",
    "neopan_1600", "t64", "pro_800z", "pro_400h", "pro_160c", "pro_160s",
    "superia_1600", "superia_400", "superia_100",
    "normalize", "auto_levels", "auto_tone", "auto_wb",
}


def encode_for_api(img: np.ndarray, max_side: int = 768) -> str:
    """Downscale img to max_side on its longest dimension, return base64 JPEG."""
    h, w = img.shape[:2]
    long = max(h, w)
    if long > max_side:
        scale = max_side / long
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode()


def img_path_to_b64(path: str, max_side: int = 768) -> str:
    """Read image from disk and return base64 JPEG string."""
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return encode_for_api(img, max_side)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_api(img_b64: str, user_prompt: str, api_key: str,
             model: str = EDIT_MODEL) -> str:
    """Send image + prompt to Claude, return raw response text."""
    import anthropic  # imported lazily — app starts even if package is absent

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"User request: {user_prompt}",
                    },
                ],
            }
        ],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Ollama API call
# ---------------------------------------------------------------------------

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "gemma3n"


def ollama_is_running(host: str = OLLAMA_DEFAULT_HOST) -> bool:
    """Return True if an Ollama server is reachable at host."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{host}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def call_api_ollama(img_b64: str, user_prompt: str,
                    model: str = OLLAMA_DEFAULT_MODEL,
                    host: str = OLLAMA_DEFAULT_HOST) -> str:
    """Send image + prompt to a local Ollama vision model, return raw text."""
    import json
    import urllib.request

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"User request: {user_prompt}",
                "images": [img_b64],
            },
        ],
        "stream": False,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result["message"]["content"]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_edit_state(text: str) -> dict:
    """Parse Claude's JSON response and clamp all values to valid ranges."""
    text = text.strip()
    # Strip optional markdown code fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    data = json.loads(text)  # raises json.JSONDecodeError on bad input

    def _f(key: str, lo: float, hi: float, default: float = 0.0) -> float:
        return max(lo, min(hi, float(data.get(key, default))))

    result = {
        "brightness":  _f("brightness",  -100.0, 100.0),
        "contrast":    _f("contrast",    -100.0, 100.0),
        "exposure":    _f("exposure",      -3.0,   3.0),
        "saturation":  _f("saturation",  -100.0, 100.0),
        "shadows":     _f("shadows",     -100.0, 100.0),
        "highlights":  _f("highlights",  -100.0, 100.0),
        "filter_name": data.get("filter_name", "original"),
        "rotation":    data.get("rotation", 0),
    }

    if result["filter_name"] not in _VALID_FILTERS:
        result["filter_name"] = "original"
    if result["rotation"] not in (0, 90, 180, 270):
        result["rotation"] = 0

    return result
