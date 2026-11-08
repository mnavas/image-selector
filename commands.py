"""Command registry for Image Selector — same pattern as image-editor's core.

One self-describing table of commands drives the GUI, the CLI and the MCP server,
so adding an edit once exposes it everywhere — and an agent discovers it via
`command_list` instead of us hand-writing a prompt. Modelled on PhotoCraft
(ArtCraft's Rust editor): "every action is a command".

Image Selector's edit model is a single destructive pipeline over an `EditState`
(not a layer document), so a command targets a `Session` = base image + EditState,
with its own undo/redo. The three entry points match image-editor and PhotoCraft:
`command_list`, `run_command`, `run_batch`.
"""
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field, fields
from typing import Any, Callable

import cv2
import numpy as np

from edit_ops import EditState, apply_pipeline

# The scalar slider fields of EditState (all clamp ranges are enforced by the ops).
ADJUST_FIELDS = ["brightness", "contrast", "exposure", "saturation", "vibrance",
                 "shadows", "highlights"]

# Valid filter_name values: "original" plus every film / camera simulation.
# One-click corrections (auto tone/levels/wb/normalize) are NOT film looks — they
# live in their own `auto_correct` slot and have their own command below.
def _filter_names() -> list[str]:
    from film_luts import FILM_SIMS
    return ["original", *FILM_SIMS]


# ---------------------------------------------------------------------------
# Session — the thing a command edits (base image + EditState + history)
# ---------------------------------------------------------------------------

@dataclass
class Session:
    base: np.ndarray                                    # immutable original, BGR uint8
    state: EditState = field(default_factory=EditState)
    _undo: list = field(default_factory=list, repr=False)
    _redo: list = field(default_factory=list, repr=False)

    def render(self, scale: float = 1.0) -> np.ndarray:
        img = self.base
        if scale != 1.0:
            h, w = img.shape[:2]
            img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                             interpolation=cv2.INTER_AREA)
        return apply_pipeline(img, self.state)

    def proxy_scale(self, max_side: int) -> float:
        long = max(self.base.shape[:2])
        return 1.0 if long <= max_side else max_side / long

    def push_history(self):
        self._undo.append(copy.copy(self.state))        # EditState fields are all immutable
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.copy(self.state))
        self.state = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.copy(self.state))
        self.state = self._redo.pop()
        return True


# ---------------------------------------------------------------------------
# Spec + registry (identical shape to image-editor/core/commands.py)
# ---------------------------------------------------------------------------

@dataclass
class CommandSpec:
    id: str
    label: str
    run: Callable[[Session, dict], Any]
    params: dict = field(default_factory=dict)
    menu: tuple = ()
    shortcut: str = ""
    enabled: Callable[[Session], bool] = lambda s: True
    disabled_reason: Callable[[Session], str] = lambda s: ""
    journal: bool = False
    query: bool = False


REGISTRY: dict[str, CommandSpec] = {}


def register(spec: CommandSpec) -> CommandSpec:
    if spec.id in REGISTRY:
        raise ValueError(f"duplicate command id: {spec.id}")
    REGISTRY[spec.id] = spec
    return spec


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def command_list(session: Session | None, filter: str | None = None,
                 enabled_only: bool = False) -> list[dict]:
    out = []
    for spec in REGISTRY.values():
        if filter and filter not in spec.id and filter not in spec.label.lower():
            continue
        ok = session is not None and spec.enabled(session)
        if enabled_only and not ok:
            continue
        out.append({
            "id": spec.id, "label": spec.label, "menu": list(spec.menu),
            "shortcut": spec.shortcut, "params": spec.params, "enabled": ok,
            "disabledReason": "" if ok else (
                "no image" if session is None else spec.disabled_reason(session)),
            "journal": spec.journal, "query": spec.query,
        })
    return out


def run_command(session: Session, id: str, params: dict | None = None) -> dict:
    spec = REGISTRY.get(id)
    if spec is None:
        return {"id": id, "ok": False, "error": f"unknown command: {id}"}
    if session is None:
        return {"id": id, "ok": False, "error": "no image"}
    if not spec.enabled(session):
        return {"id": id, "ok": False, "error": spec.disabled_reason(session) or "disabled"}
    try:
        return {"id": id, "ok": True, "result": spec.run(session, params or {})}
    except Exception as e:
        return {"id": id, "ok": False, "error": f"{type(e).__name__}: {e}"}


def run_batch(session: Session, steps: list[dict], stop_on_error: bool = True) -> dict:
    results, completed = [], 0
    for step in steps:
        res = run_command(session, step.get("id", ""), step.get("params"))
        results.append(res)
        if res["ok"]:
            completed += 1
        elif stop_on_error:
            break
    return {"completed": completed, "total": len(steps), "results": results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num(params: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"`{key}` must be a number")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _run_inspect(s: Session, _p: dict) -> dict:
    h, w = s.base.shape[:2]
    st = s.state
    return {
        "size": {"width": int(w), "height": int(h)},
        "state": {f.name: getattr(st, f.name) for f in fields(st)},
        "isDefault": st.is_default(),
        "history": {"undo": len(s._undo), "redo": len(s._redo)},
    }


register(CommandSpec(id="doc.inspect", label="Inspect", query=True, run=_run_inspect))


def _run_preview(s: Session, p: dict) -> dict:
    max_side = max(16, min(int(p.get("max_side", 1024)), 2048))
    img = s.render(s.proxy_scale(max_side))
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encode failed")
    h, w = img.shape[:2]
    return {"format": "png", "width": int(w), "height": int(h),
            "base64": base64.b64encode(buf.tobytes()).decode("ascii")}


register(CommandSpec(
    id="doc.renderPreview", label="Render Preview", query=True, run=_run_preview,
    params={"max_side": {"type": "int", "default": 1024, "max": 2048}}))


register(CommandSpec(
    id="edit.undo", label="Undo", menu=("Edit",), shortcut="Ctrl+Z",
    enabled=lambda s: len(s._undo) > 0, disabled_reason=lambda s: "nothing to undo",
    run=lambda s, _p: {"undone": s.undo()}))

register(CommandSpec(
    id="edit.redo", label="Redo", menu=("Edit",), shortcut="Ctrl+Shift+Z",
    enabled=lambda s: len(s._redo) > 0, disabled_reason=lambda s: "nothing to redo",
    run=lambda s, _p: {"redone": s.redo()}))


def _run_adjust_set(s: Session, p: dict) -> dict:
    key = str(p.get("key", ""))
    if key not in ADJUST_FIELDS:
        raise ValueError(f"unknown adjustment `{key}`; one of: {', '.join(ADJUST_FIELDS)}")
    s.push_history()
    setattr(s.state, key, _num(p, "value"))
    return {key: getattr(s.state, key)}


register(CommandSpec(
    id="adjust.set", label="Set Adjustment", menu=("Image", "Adjust"), journal=True,
    run=_run_adjust_set,
    params={"key": {"type": "enum", "values": ADJUST_FIELDS},
            "value": {"type": "float", "doc": "absolute slider value"}}))


def _run_adjust_apply(s: Session, p: dict) -> dict:
    unknown = [k for k in p if k not in ADJUST_FIELDS]
    if unknown:
        raise ValueError(f"unknown adjustment(s): {', '.join(unknown)}")
    if not any(k in p for k in ADJUST_FIELDS):
        raise ValueError("no adjustments given")
    s.push_history()
    applied = {}
    for k in ADJUST_FIELDS:
        if k in p:
            setattr(s.state, k, _num(p, k))
            applied[k] = getattr(s.state, k)
    return {"applied": applied}


register(CommandSpec(
    id="adjust.apply", label="Apply Adjustments", menu=("Image", "Adjust"), journal=True,
    run=_run_adjust_apply,
    params={k: {"type": "float", "doc": "absolute value; omit to leave unchanged"}
            for k in ADJUST_FIELDS}))


def _run_adjust_reset(s: Session, _p: dict) -> dict:
    s.push_history()
    keep_geom = (s.state.crop_rect, s.state.rotation)
    s.state = EditState()
    s.state.crop_rect, s.state.rotation = keep_geom     # tones reset, framing kept
    return {"reset": True}


register(CommandSpec(
    id="adjust.reset", label="Reset Adjustments", menu=("Image", "Adjust"), journal=True,
    enabled=lambda s: not s.state.is_default(), disabled_reason=lambda s: "already default",
    run=_run_adjust_reset))


def _run_filter(s: Session, p: dict) -> dict:
    name = str(p.get("name", "original"))
    if name not in _filter_names():
        raise ValueError(f"unknown filter `{name}`")
    s.push_history()
    s.state.filter_name = name
    return {"filter_name": name}


register(CommandSpec(
    id="filter.set", label="Set Film Look", menu=("Image", "Film"), journal=True,
    run=_run_filter, params={"name": {"type": "enum", "values_fn": "filters"}}))


def _run_auto_correct(s: Session, p: dict) -> dict:
    from edit_ops import AUTO_CORRECTIONS
    mode = str(p.get("mode", "none"))
    if mode not in AUTO_CORRECTIONS:
        raise ValueError(f"unknown correction `{mode}`; one of: {', '.join(AUTO_CORRECTIONS)}")
    s.push_history()
    # pressing the same correction again toggles it off — fast A/B while culling
    s.state.auto_correct = "none" if s.state.auto_correct == mode else mode
    return {"auto_correct": s.state.auto_correct}


register(CommandSpec(
    id="image.autoCorrect", label="Auto Correct", menu=("Image", "Auto"), journal=True,
    run=_run_auto_correct,
    params={"mode": {"type": "enum",
                     "values": ["auto_tone", "auto_levels", "auto_wb", "normalize", "none"],
                     "default": "auto_tone",
                     "doc": "one-click correction, independent of the film look; "
                            "re-sending the current one turns it off"}}))


def _run_rotate(s: Session, p: dict) -> dict:
    direction = str(p.get("direction", "cw")).lower()
    if direction not in ("cw", "ccw"):
        raise ValueError("`direction` must be 'cw' or 'ccw'")
    s.push_history()
    s.state.rotation = (s.state.rotation + (90 if direction == "cw" else 270)) % 360
    return {"rotation": s.state.rotation}


register(CommandSpec(
    id="image.rotate", label="Rotate", menu=("Image", "Rotate"), journal=True,
    run=_run_rotate,
    params={"direction": {"type": "enum", "values": ["cw", "ccw"], "default": "cw"}}))


def _run_set_crop(s: Session, p: dict) -> dict:
    x, y, w, h = (_num(p, "x"), _num(p, "y"), _num(p, "w"), _num(p, "h"))
    if w <= 0 or h <= 0:
        raise ValueError("`w` and `h` must be > 0")
    s.push_history()
    s.state.crop_rect = (x, y, w, h)
    return {"crop": s.state.crop_rect}


register(CommandSpec(
    id="image.setCrop", label="Crop", menu=("Image", "Crop"), journal=True,
    run=_run_set_crop,
    params={k: {"type": "float", "doc": "normalised 0..1, post-rotation"}
            for k in ("x", "y", "w", "h")}))


def _run_clear_crop(s: Session, _p: dict) -> dict:
    s.push_history()
    s.state.crop_rect = None
    return {"crop": None}


register(CommandSpec(
    id="image.clearCrop", label="Clear Crop", menu=("Image",), journal=True,
    enabled=lambda s: s.state.crop_rect is not None, disabled_reason=lambda s: "no crop",
    run=_run_clear_crop))
