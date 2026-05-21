# v0.0.2 — Changelog

## New Files

### `edit_ops.py`
Pure OpenCV/NumPy image editing functions. No Qt imports — designed to be callable by a future Claude Code MCP tool.

- `EditState` dataclass — holds all edit parameters (brightness, contrast, exposure, saturation, shadows, highlights, filter_name, crop_rect, rotation)
- `apply_brightness(img, value)` — shift V channel in HSV; ±100
- `apply_contrast(img, value)` — LUT scale around 128; ±100
- `apply_exposure(img, stops)` — LUT multiply by 2^stops; ±3.0
- `apply_saturation(img, value)` — scale S channel in HSV; ±100
- `apply_shadows(img, value)` — weighted tone-curve lift/crush in lower quarter; ±100
- `apply_highlights(img, value)` — weighted tone-curve roll-off in upper quarter; ±100
- `apply_crop(img, x, y, w, h)` — normalised 0-1 coordinates, array slice
- `apply_rotate(img, degrees)` — cv2.rotate for 0/90/180/270°
- `apply_normalize(img)` — CLAHE on L channel in LAB
- `apply_pipeline(img, state)` — applies all ops in fixed order: rotate → crop → exposure → brightness → contrast → saturation → shadows → highlights → film filter / normalize

### `film_luts.py`
Fujifilm-inspired film simulations computed analytically via `np.interp` tone curves. No external asset files.

| Key | Character |
|-----|-----------|
| `provia` | Slight S-curve, neutral colours |
| `velvia` | Punchy contrast, +35% saturation, warm cast |
| `astia` | Lifted shadows, gentle curve, −12% saturation |
| `classic_chrome` | Lifted blacks, cool cast, −28% saturation |
| `classic_neg` | Warm shadows, cyan highlights, +15% saturation |
| `acros` | Black-and-white with rich blacks via tone curve |

`FILM_SIMS` dict is the public export; `apply_pipeline` imports it lazily.

### `widgets/edit_panel.py`
Full-screen edit mode overlay widget.

- **`CropOverlay`** — transparent `QWidget` drawn over `EditPreview`; normalised coordinate system; 8 drag handles (corners + mid-edges); aspect-ratio-locked resize; rule-of-thirds grid; dark mask outside crop rect; `crop_confirmed` signal emits normalised x,y,w,h
- **`EditPreview`** — `PreviewWidget` subclass; hosts `CropOverlay` child; passes updated `image_rect()` to overlay on resize/zoom/set_array
- **`AdjustmentsPanel`** — 6 `QSlider` instances with labels and live value display; Reset button; emits `changed` signal
- **`FiltersPanel`** — `QButtonGroup` with 8 `QRadioButton` instances (Original + 6 sims + Normalize); emits `changed(str)` signal
- **`EditPanel`** — main container; header bar with Back/Crop/Save As; 50 ms debounce timer on slider/filter changes; downscales image to max 1600px longest side for live preview; applies full-resolution pipeline on save; `Ctrl+S` / `Esc` keyboard shortcuts

---

## Modified Files

### `widgets/preview_widget.py`
Rewritten from `QLabel` subclass to `QWidget` with `QPainter`-based rendering.

- `_zoom` (float, 1.0) and `_pan` (QPointF) state
- `wheelEvent` — zoom ×1.25 / ×0.8 per step, clamped [0.1, 8.0], cursor-centred via pan adjustment
- `mouseDoubleClickEvent` — `reset_zoom()`
- `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent` — left-drag pan
- `set_array(img)` — update from numpy array without zoom reset (used by edit mode)
- `reset_zoom()` — called by `set_image()` and on image navigation
- `image_rect() -> QRectF` — returns draw rectangle in widget coords (used by `CropOverlay`)

### `app_controller.py`
Added edit mode methods:

- `open_edit_mode()` — reads image with `cv2.imread`, calls `window.show_edit_panel(entry, img)`
- `close_edit_mode()` — calls `window.hide_edit_panel()`, clears `_edit_entry` / `_edit_original`
- `save_edit(state, target_path)` — applies full-resolution pipeline, writes file, restores timestamps with `os.utime`, updates collection entry if renamed, then calls `close_edit_mode()` + `_refresh_collections()`
- `quick_rotate()` — reads image, applies `apply_rotate(img, 90)`, writes in-place, restores timestamps, calls `_refresh_selection()`

### `widgets/main_window.py`
- Added `EditPanel` as a child of `centralWidget`, hidden by default
- `show_edit_panel(entry, img)` — sizes panel to `centralWidget().rect()`, shows and raises
- `hide_edit_panel()` — hides panel, restores focus to `MainWindow`
- `resizeEvent` — resizes `_edit_panel` to match central widget if visible
- `keyPressEvent` additions: `E` → `open_edit_mode()`, `R` → `quick_rotate()`

### `README.md`
- Features section updated for v0.0.2
- Keyboard shortcuts split into triage / edit mode sections
- Project structure updated with new files
- Roadmap updated

---

## Design Decisions

1. **Crop in normalised coordinates** — the overlay works in 0-1 fractions of the image, independent of display scale. Pixel coordinates are derived at save time from the full-resolution array dimensions.
2. **50 ms debounce** — prevents pipeline re-rendering on every slider pixel of movement while keeping latency imperceptible.
3. **Preview downscaling at 1600px** — pipeline runs at ~4× lower resolution for the live preview; full resolution used only on `save_edit`.
4. **`film_luts.py` functions, not arrays** — simulations are functions (not pre-baked LUTs) so they can compose tone curves and HSV operations in sequence without a fixed LUT indirection overhead.
5. **`apply_pipeline` imports `film_luts` lazily** — avoids a circular import; `edit_ops.py` has no module-level dependency on `film_luts.py`.
