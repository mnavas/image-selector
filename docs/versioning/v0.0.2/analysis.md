# v0.0.2 — Implementation Analysis

## Version Scope

v0.0.2 adds the **edit mode** deferred from v0.0.1: an interactive full-screen editor accessible from the triage view. All edits are non-destructive until the user saves.

**In scope:**
- Edit mode UI (modal overlay, entered with `E` from triage)
- Zoom in/out via mouse wheel (also available in triage view)
- Crop tool with interactive drag handles
- Color adjustment tools: brightness, contrast, exposure, saturation, shadows/highlights
- Preset film simulation filters (Fujifilm-inspired)
- Normalize filter (adaptive histogram equalization via CLAHE)
- Save As dialog: original filename as default, overwrite confirmation on same name, new file on rename

**Deferred to future versions:**
- Claude Code MCP smart edit (AI-suggested edits via compressed image — see architecture note below)
- HEIC support (`pillow-heif`)
- RAW support (`rawpy`)
- Batch editing

---

## Architecture Note: Edit Pipeline Design

The edit operations will be implemented as **pure functions** that take a NumPy array and return a NumPy array. They must not be coupled to Qt widgets. This is intentional: a future MCP tool will be able to call the same functions programmatically to apply AI-suggested edits without any UI interaction.

```python
# example shape all edit ops will follow
def apply_brightness(img: np.ndarray, value: float) -> np.ndarray: ...
def apply_fuji_classic_chrome(img: np.ndarray, strength: float) -> np.ndarray: ...
```

All ops live in a new module `edit_ops.py`. The edit UI calls them; future MCP tools will call them directly.

---

## New Modules

### `edit_ops.py`
Pure OpenCV functions. No Qt imports.

| Function | Parameters | Notes |
|----------|-----------|-------|
| `apply_brightness(img, value)` | `value` ∈ [-100, 100] | additive on V channel (HSV) |
| `apply_contrast(img, value)` | `value` ∈ [-100, 100] | scale around mid-grey |
| `apply_exposure(img, stops)` | `stops` ∈ [-3.0, 3.0] | multiply by 2^stops |
| `apply_saturation(img, value)` | `value` ∈ [-100, 100] | scale S channel (HSV) |
| `apply_shadows(img, value)` | `value` ∈ [-100, 100] | tone-curve lift/crush in shadows |
| `apply_highlights(img, value)` | `value` ∈ [-100, 100] | tone-curve roll-off in highlights |
| `apply_crop(img, rect)` | `rect: QRect` | simple array slice |
| `apply_rotate(img, angle)` | `angle` ∈ {-270, -180, -90, 0, 90, 180, 270} | `cv2.rotate` |
| `apply_lut(img, lut)` | `lut: np.ndarray` shape (256, 1, 3) | applies a colour LUT per channel |
| `apply_normalize(img, clip_limit, tile_grid)` | `clip_limit=2.0`, `tile_grid=(8,8)` | CLAHE on L channel (LAB) |

### `film_luts.py`
Defines the Fujifilm-inspired LUT data as NumPy arrays. No Qt imports.

Film simulations to implement (v0.0.2):

| Name | Character |
|------|-----------|
| **Provia / Standard** | Neutral, accurate colours — baseline |
| **Velvia** | High saturation, deep shadows, punchy contrast |
| **Astia / Soft** | Subdued contrast, natural skin tones |
| **Classic Chrome** | Desaturated, faded blues/greens, lifted shadows |
| **Classic Neg** | Warm shadows, cyan highlights, high contrast |
| **Acros** | Rich black-and-white with deep blacks |
| **Normalize** | CLAHE adaptive histogram equalisation — not a film sim but lives in the same filter list |

LUTs are computed analytically (tone curves + colour matrices) at startup, not loaded from files. This keeps the project self-contained with no external assets.

### `widgets/edit_panel.py`
The edit mode widget. Displayed as a modal overlay inside `MainWindow` (replaces the triage layout while active; does not open a new window).

Layout:
```
┌───────────────────────────────────────────────────────────────┐
│  [← Back]  filename.jpg                      [Save As]  [✕]  │
├────────────────────────────────────────┬──────────────────────┤
│                                        │  ADJUSTMENTS         │
│                                        │  Brightness   [━━●━] │
│           [ image preview ]            │  Contrast     [━●━━] │
│         (zoom + crop overlay)          │  Exposure     [━━━●] │
│                                        │  Saturation   [━━●━] │
│                                        │  Shadows      [●━━━] │
│                                        │  Highlights   [━━━●] │
│                                        ├──────────────────────┤
│                                        │  FILTERS             │
│                                        │  ○ Original          │
│                                        │  ○ Provia            │
│                                        │  ○ Velvia            │
│                                        │  ○ Astia             │
│                                        │  ○ Classic Chrome    │
│                                        │  ○ Classic Neg       │
│                                        │  ○ Acros             │
│                                        │  ○ Normalize         │
└────────────────────────────────────────┴──────────────────────┘
```

---

## Zoom

Zoom is available in **both triage mode and edit mode**.

- Mouse wheel up → zoom in (×1.25 per step)
- Mouse wheel down → zoom out (×0.8 per step)
- Zoom is centred on the mouse cursor position
- Zoom range: 10 % – 800 %
- Double-click → reset to fit-to-window
- In triage mode, zoom resets automatically when navigating to a new image
- Zoom state is stored in `PreviewWidget`; no changes to the model

Implementation: `PreviewWidget` receives `wheelEvent`, adjusts a `_zoom` factor, recomputes the scaled pixmap offset so the point under the cursor stays fixed, and renders via a `QPixmap` inside a `QLabel` with a manual offset (or switch to `QPainter` in `paintEvent` for sub-pixel accuracy).

---

## Crop Tool

Crop is available only in **edit mode**.

- Activated by a "Crop" button in the edit panel toolbar
- An `CropOverlay` (transparent `QWidget` child of the preview) draws a semi-transparent dark mask + bright rectangle + drag handles at corners and mid-edges
- Dragging a handle resizes the crop rect; dragging inside the rect moves it
- Aspect ratio is always locked to the original image's W:H — the crop rectangle cannot be reshaped
- Pressing `Enter` or clicking "Apply Crop" confirms; `Esc` cancels
- After confirm, `apply_crop` is called on the in-memory image array and the overlay is hidden

---

## Edit Pipeline

All edits operate on a single **in-memory working copy** (`np.ndarray`) of the original image. The pipeline is applied in this fixed order on every slider/filter change:

```
original_array
  → apply_rotate
  → apply_crop
  → apply_exposure
  → apply_brightness
  → apply_contrast
  → apply_saturation
  → apply_shadows / apply_highlights
  → apply_lut (film filter)
  → apply_normalize (if selected)
  → display
```

Re-applying the full pipeline on each change is fast for typical JPEG sizes (< 150 ms at full resolution). If performance is an issue, downscale for preview and only apply at full res on save.

Slider changes → `EditState` dataclass is updated → pipeline re-runs → preview redraws. No partial caching in v0.0.2.

```python
@dataclass
class EditState:
    brightness: float = 0.0
    contrast: float = 0.0
    exposure: float = 0.0
    saturation: float = 0.0
    shadows: float = 0.0
    highlights: float = 0.0
    filter_name: str = "original"
    crop_rect: tuple | None = None   # (x, y, w, h) in original pixels
    rotation: int = 0                # degrees
```

---

## Save As Flow (from requirements)

1. User clicks **Save As** (or `Ctrl+S`)
2. `QFileDialog.getSaveFileName` opens, pre-filled with original filename in its original directory
3. If user keeps same name and confirms overwrite → original file is replaced; `os.utime` re-stamps creation date
4. If user picks a new name → new file is written; original creation date is copied to the new file; original is untouched
5. Edit panel closes; triage view resumes showing the (possibly renamed) file

---

## Changes to Existing Modules

| Module | Change |
|--------|--------|
| `widgets/preview_widget.py` | Add `wheelEvent` for zoom; store `_zoom` and `_pan_offset`; add `reset_zoom()`; expose `current_pixmap()` for crop overlay coordinate mapping |
| `widgets/main_window.py` | Add `E` key → open edit panel; add `R` key → rotate 90° (calls `edit_ops.apply_rotate` then saves immediately as a quick-rotate, same save-as flow) |
| `app_controller.py` | Add `open_edit_mode(entry)` and `close_edit_mode()` |

---

## Dependencies (additions)

No new pip packages required. All new features use `opencv-python` and `numpy` already installed.

---

## Decisions

1. **Crop aspect ratio** — locked to the original image's aspect ratio only. No free crop or other presets. The crop tool constrains the selection rectangle to the same W:H ratio as the source image.
2. **Fujifilm filter set** — confirmed: Provia, Velvia, Astia, Classic Chrome, Classic Neg, Acros (6 sims).
3. **Slider ranges** — confirmed: ±100 for brightness, contrast, saturation, shadows, highlights; ±3.0 stops for exposure.
4. **Normalize** — listed as a radio-button filter alongside the film sims (mutually exclusive with other filters). Selecting it replaces any active film sim.
5. **Edit mode entry** — `E` key only. No additional button in the triage action bar.
