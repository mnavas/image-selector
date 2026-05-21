from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class EditState:
    brightness: float = 0.0    # ±100
    contrast: float = 0.0      # ±100
    exposure: float = 0.0      # ±3.0 stops
    saturation: float = 0.0    # ±100
    shadows: float = 0.0       # ±100
    highlights: float = 0.0    # ±100
    filter_name: str = "original"
    crop_rect: tuple | None = None   # (x, y, w, h) normalised 0-1 of post-rotate image
    rotation: int = 0                # clockwise degrees: 0, 90, 180, 270

    def is_default(self) -> bool:
        return (
            self.brightness == 0.0
            and self.contrast == 0.0
            and self.exposure == 0.0
            and self.saturation == 0.0
            and self.shadows == 0.0
            and self.highlights == 0.0
            and self.filter_name == "original"
            and self.crop_rect is None
            and self.rotation == 0
        )


# ---------------------------------------------------------------------------
# LUT helpers
# ---------------------------------------------------------------------------

def _make_lut(fn) -> np.ndarray:
    """Build a 256-entry uint8 LUT from a mapping function int->float."""
    t = np.arange(256, dtype=np.float32)
    out = np.clip(fn(t), 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------
# Individual operations — all operate on BGR uint8 ndarray
# ---------------------------------------------------------------------------

def apply_brightness(img: np.ndarray, value: float) -> np.ndarray:
    """Shift V channel in HSV. value ∈ [-100, 100]."""
    if value == 0.0:
        return img
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
    shift = int(value * 255 / 100)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] + shift, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def apply_contrast(img: np.ndarray, value: float) -> np.ndarray:
    """Scale pixel values around 128. value ∈ [-100, 100]."""
    if value == 0.0:
        return img
    factor = (value + 100) / 100.0   # 0 → 0, 100 → 1 (no change), 200 → 2
    lut = _make_lut(lambda t: (t - 128) * factor + 128)
    return cv2.LUT(img, lut)


def apply_exposure(img: np.ndarray, stops: float) -> np.ndarray:
    """Multiply luminance by 2^stops. stops ∈ [-3.0, 3.0]."""
    if stops == 0.0:
        return img
    scale = 2.0 ** stops
    lut = _make_lut(lambda t: t * scale)
    return cv2.LUT(img, lut)


def apply_saturation(img: np.ndarray, value: float) -> np.ndarray:
    """Scale S channel in HSV. value ∈ [-100, 100]."""
    if value == 0.0:
        return img
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    factor = 1.0 + value / 100.0
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * factor, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def apply_shadows(img: np.ndarray, value: float) -> np.ndarray:
    """Lift or crush the lower quarter of the tone curve. value ∈ [-100, 100]."""
    if value == 0.0:
        return img
    shift = value * 0.5   # max ±50 output units
    # Weight peaks at 0 (pure black) and tapers to 0 at 192
    lut = _make_lut(lambda t: t + shift * np.clip(1.0 - t / 192.0, 0, 1) ** 2)
    return cv2.LUT(img, lut)


def apply_highlights(img: np.ndarray, value: float) -> np.ndarray:
    """Roll-off or boost the upper quarter of the tone curve. value ∈ [-100, 100]."""
    if value == 0.0:
        return img
    shift = value * 0.5   # max ±50 output units
    # Weight peaks at 255 (pure white) and tapers to 0 at 64
    lut = _make_lut(lambda t: t + shift * np.clip((t - 64) / 191.0, 0, 1) ** 2)
    return cv2.LUT(img, lut)


def apply_crop(img: np.ndarray, x: float, y: float, w: float, h: float) -> np.ndarray:
    """Crop using normalised coordinates (0-1). Returns sliced array."""
    ih, iw = img.shape[:2]
    x0 = max(0, int(x * iw))
    y0 = max(0, int(y * ih))
    x1 = min(iw, int((x + w) * iw))
    y1 = min(ih, int((y + h) * ih))
    if x1 <= x0 or y1 <= y0:
        return img
    return img[y0:y1, x0:x1]


def apply_rotate(img: np.ndarray, degrees: int) -> np.ndarray:
    """Rotate clockwise by 0, 90, 180, or 270 degrees."""
    degrees = degrees % 360
    if degrees == 0:
        return img
    if degrees == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def apply_normalize(img: np.ndarray) -> np.ndarray:
    """CLAHE on the L channel in LAB colour space."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_auto_levels(img: np.ndarray, clip: float = 0.5) -> np.ndarray:
    """Stretch each BGR channel to its 0.5–99.5 percentile range.

    Fixes both exposure and colour casts by treating each channel independently.
    `clip` is the percentage of pixels clipped at each end (0.5 = 0.5%).
    """
    out = np.empty_like(img)
    for i in range(3):
        ch = img[:, :, i].astype(np.float32)
        lo = np.percentile(ch, clip)
        hi = np.percentile(ch, 100.0 - clip)
        if hi <= lo:
            out[:, :, i] = img[:, :, i]
            continue
        stretched = (ch - lo) * 255.0 / (hi - lo)
        out[:, :, i] = np.clip(stretched, 0, 255).astype(np.uint8)
    return out


def apply_auto_tone(img: np.ndarray, clip: float = 0.5) -> np.ndarray:
    """Stretch luminance to its percentile range without shifting colours.

    Converts to LAB, stretches the L channel only, then converts back.
    Exposure is corrected while the colour balance is preserved.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    l = lab[:, :, 0]
    lo = np.percentile(l, clip)
    hi = np.percentile(l, 100.0 - clip)
    if hi > lo:
        lab[:, :, 0] = np.clip((l - lo) * 255.0 / (hi - lo), 0, 255)
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)


def apply_auto_wb(img: np.ndarray) -> np.ndarray:
    """Grey-world white balance: scale each channel so its mean equals the overall mean.

    Removes colour casts caused by artificial or mixed lighting.
    """
    img_f = img.astype(np.float32)
    mean_b = img_f[:, :, 0].mean()
    mean_g = img_f[:, :, 1].mean()
    mean_r = img_f[:, :, 2].mean()
    overall = (mean_b + mean_g + mean_r) / 3.0
    if mean_b > 0:
        img_f[:, :, 0] = np.clip(img_f[:, :, 0] * overall / mean_b, 0, 255)
    if mean_g > 0:
        img_f[:, :, 1] = np.clip(img_f[:, :, 1] * overall / mean_g, 0, 255)
    if mean_r > 0:
        img_f[:, :, 2] = np.clip(img_f[:, :, 2] * overall / mean_r, 0, 255)
    return img_f.astype(np.uint8)


def apply_lut(img: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Apply a per-channel colour LUT. lut shape: (256, 1, 3) or (256,) uint8."""
    return cv2.LUT(img, lut)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def apply_pipeline(img: np.ndarray, state: EditState) -> np.ndarray:
    """Apply all edits in fixed order. img is the unmodified original (BGR)."""
    from film_luts import FILM_SIMS  # local import avoids circular dependency

    out = apply_rotate(img, state.rotation)

    if state.crop_rect is not None:
        x, y, w, h = state.crop_rect
        out = apply_crop(out, x, y, w, h)

    out = apply_exposure(out, state.exposure)
    out = apply_brightness(out, state.brightness)
    out = apply_contrast(out, state.contrast)
    out = apply_saturation(out, state.saturation)
    out = apply_shadows(out, state.shadows)
    out = apply_highlights(out, state.highlights)

    if state.filter_name == "normalize":
        out = apply_normalize(out)
    elif state.filter_name == "auto_levels":
        out = apply_auto_levels(out)
    elif state.filter_name == "auto_tone":
        out = apply_auto_tone(out)
    elif state.filter_name == "auto_wb":
        out = apply_auto_wb(out)
    elif state.filter_name in FILM_SIMS:
        out = FILM_SIMS[state.filter_name](out)

    return out
