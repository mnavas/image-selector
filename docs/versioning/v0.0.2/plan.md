# v0.0.2 — Implementation Plan

## Prerequisites

v0.0.1 fully working. No new pip packages needed — `opencv-python` and `numpy` are already installed.

---

## Phase 1 — Image Processing Core (no UI)

All functions in this phase are pure NumPy/OpenCV — zero Qt imports. They can be tested standalone and will be reusable by the future MCP integration.

### Step 1 — `edit_ops.py`

Implement each operation as a standalone function operating on BGR `np.ndarray`:

```
apply_brightness(img, value: float) -> ndarray      # ±100, shift V in HSV
apply_contrast(img, value: float) -> ndarray        # ±100, scale around 128
apply_exposure(img, stops: float) -> ndarray        # ±3.0, multiply by 2^stops
apply_saturation(img, value: float) -> ndarray      # ±100, scale S in HSV
apply_shadows(img, value: float) -> ndarray         # ±100, tone curve lower quarter
apply_highlights(img, value: float) -> ndarray      # ±100, tone curve upper quarter
apply_crop(img, x, y, w, h) -> ndarray              # array slice
apply_rotate(img, degrees: int) -> ndarray          # cv2.rotate, multiples of 90
apply_lut(img, lut: ndarray) -> ndarray             # per-channel LUT, shape (256,1,3)
apply_normalize(img) -> ndarray                     # CLAHE on L channel in LAB
apply_pipeline(img, state: EditState) -> ndarray    # runs all ops in fixed order
```

`apply_pipeline` is the single entry point used by the UI — takes an `EditState` and returns the processed array.

### Step 2 — `film_luts.py`

Build each Fujifilm-inspired LUT analytically using tone curves and per-channel colour adjustments. Returns `dict[str, np.ndarray]` keyed by filter name.

| Sim | Technique |
|-----|-----------|
| Provia | Identity LUT (neutral baseline) |
| Velvia | Boost S +30, contrast +20, deep shadow crush |
| Astia | Reduce S −10, gentle S-curve, warm highlights |
| Classic Chrome | Desaturate blues/greens, lift shadows, cool cast |
| Classic Neg | Warm shadow tint, cyan highlight push, high contrast |
| Acros | Convert to greyscale with luminosity weights, rich blacks |

Each LUT is a `(256, 1, 3)` uint8 array applied via `cv2.LUT`. Computed once at import time and cached as module-level constants.

**Checkpoint:** write `test_edit_ops.py` — load a single test JPEG, apply each operation and filter, save outputs to `/tmp/` for visual inspection.

---

## Phase 2 — Zoom (triage + edit)

### Step 3 — Zoom in `PreviewWidget`

Extend `widgets/preview_widget.py`:

- Add `_zoom: float = 1.0` and `_pan: QPointF = QPointF(0, 0)`
- Override `wheelEvent`: adjust `_zoom` by ×1.25 (up) or ×0.8 (down), clamped to [0.1, 8.0]; keep the pixel under the cursor stationary by adjusting `_pan`
- Override `paintEvent` with `QPainter` to draw the pixmap at the computed zoom/pan offset (replaces the current `setPixmap` approach)
- Add `reset_zoom()`: sets `_zoom = 1.0`, `_pan = QPointF(0, 0)`, triggers repaint
- Double-click calls `reset_zoom()`
- `app_controller.navigate()` calls `window.preview.reset_zoom()` so zoom resets on image change

---

## Phase 3 — Edit Mode UI

### Step 4 — `EditState` dataclass

Add to `edit_ops.py` (or a separate `edit_state.py`):

```python
@dataclass
class EditState:
    brightness: float = 0.0
    contrast: float = 0.0
    exposure: float = 0.0
    saturation: float = 0.0
    shadows: float = 0.0
    highlights: float = 0.0
    filter_name: str = "original"   # "original" | "provia" | "velvia" | ...
    crop_rect: tuple | None = None   # (x, y, w, h) in original-image pixels
    rotation: int = 0

    def is_default(self) -> bool: ...   # True if no edits applied
```

### Step 5 — `widgets/edit_panel.py`

A `QWidget` that overlays the entire `MainWindow` central area. Shown/hidden by `AppController`.

Sub-widgets:
- **`EditPreview`** — subclass of `PreviewWidget`; also draws the crop overlay when crop mode is active; receives the processed `np.ndarray` from the pipeline
- **`AdjustmentsPanel`** — `QWidget` with six `QSlider` instances (one per colour op); each slider change triggers `_on_state_changed()`
- **`FiltersPanel`** — `QWidget` with `QButtonGroup` of radio buttons (Original + 6 sims + Normalize)
- **`CropOverlay`** — transparent child of `EditPreview`; draws mask + handles; emits `crop_confirmed(x, y, w, h)`
- **Header bar** — `[← Back]` label, filename, `[Save As]` button, `[✕]` close

`_on_state_changed()` flow:
```
slider / filter radio changed
  → update EditState
  → apply_pipeline(original_array, state) → processed_array
  → EditPreview.set_array(processed_array)
```

To avoid blocking the UI on large images, `apply_pipeline` runs on a downscaled copy (longest side ≤ 1600 px) for the live preview. Full resolution is used only on save.

### Step 6 — Crop overlay (`CropOverlay`)

A `QWidget` child of `EditPreview` with `setAttribute(WA_TransparentForMouseEvents, False)`.

- On `mousePressEvent`: detect if click is on a handle (8 px hit area) or inside the rect
- On `mouseMoveEvent`: resize or move the rect, constrained to original aspect ratio and image bounds
- On `mouseReleaseEvent`: emit `crop_committed(x, y, w, h)` in original-image pixel coordinates
- Draws: semi-transparent dark mask outside crop rect, bright rect border, 8 square handles, rule-of-thirds grid lines inside rect
- `Esc` → cancel crop (restore previous rect); `Enter` → confirm

---

## Phase 4 — Wiring

### Step 7 — `AppController` edit methods

```python
def open_edit_mode(self) -> None
    # loads original image array, creates EditState, shows EditPanel

def close_edit_mode(self) -> None
    # hides EditPanel, refreshes triage view

def save_edit(self, state: EditState, target_path: Path) -> None
    # apply_pipeline at full res, write file, re-stamp creation date, reload entry
```

### Step 8 — `MainWindow` keyboard additions

- `E` → `controller.open_edit_mode()` (only if an image is selected)
- `R` → quick rotate 90° CW without entering edit mode; uses `apply_rotate` + immediate save-as flow
- `Esc` in edit mode → `controller.close_edit_mode()` (cancel)
- `Ctrl+S` in edit mode → trigger save-as flow

### Step 9 — Save As flow

Implement `_save_edit_dialog(entry, state)` in `EditPanel`:

1. `QFileDialog.getSaveFileName` pre-filled with `entry.path`
2. If same path → confirm overwrite (`QMessageBox.question`)
3. Apply full-resolution pipeline → write with `cv2.imwrite`
4. `os.utime` to restore original creation date
5. If new filename → update the `ImageEntry` in the collection via controller
6. Close edit panel

---

## Phase 5 — Integration & Polish

### Step 10 — Integration testing

- Open a folder with 20+ images, enter edit mode, adjust all sliders, confirm preview updates live
- Apply each film filter, confirm visual difference in preview
- Crop, confirm aspect ratio stays locked, confirm pixel coordinates are correct
- Save As with same name, verify original date preserved (`stat -c %y`)
- Save As with new name, verify original file unchanged, new file has correct date
- Zoom in triage mode: wheel up/down, double-click reset, navigate to next image resets zoom
- Verify `R` quick-rotate works and creation date is preserved

### Step 11 — Final checks

- Test on a portrait image (W < H) — crop and zoom should still work
- Test on an empty album (no crash entering edit mode when album is empty)
- Update `README.md` — add edit mode keyboard shortcuts and feature list

---

## Deliverables

| File | Status |
|------|--------|
| `edit_ops.py` | done |
| `film_luts.py` | done |
| `widgets/edit_panel.py` | done |
| `widgets/preview_widget.py` (zoom) | done |
| `app_controller.py` (edit methods) | done |
| `widgets/main_window.py` (E, R keys) | done |
