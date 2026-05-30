# Image Selector — Architecture & Developer Guide

## Overview

Image Selector follows a strict **MVC separation**:

- **Model** — `ImageCollection`, `ImageEntry`, `FileOps`, `Config`
- **Controller** — `AppController`
- **View** — everything under `widgets/`

The edit pipeline (`edit_ops.py`, `film_luts.py`) is intentionally **decoupled from Qt**. Every function takes a NumPy array and returns a NumPy array. This is by design: a future Claude Code MCP integration will call the same functions programmatically without any UI.

---

## Module Map

```
image_selector/
├── main.py                  Entry point — boots Qt, loads config, wires controller + window
├── config.py                JSON config persistence (~/.config/image_selector/config.json)
├── image_collection.py      ImageEntry dataclass + ImageCollection folder scanner
├── file_ops.py              Move, trash, undo — all filesystem operations
├── thumbnail_cache.py       LRU-200 OpenCV thumbnail cache (used by preview)
├── edit_ops.py              Pure image editing functions + EditState dataclass
├── film_luts.py             Film simulation functions (Fujifilm-inspired)
├── ai_edit.py               AI edit helpers — encoding, API call, response parsing (no Qt)
├── mcp_server.py            MCP server for Claude Code (get_image_info, suggest_edits, apply_and_save)
├── app_controller.py        All user actions — mediates model ↔ view
└── widgets/
    ├── main_window.py        MainWindow — layout, keyboard routing, menu
    ├── preview_widget.py     Zoomable/pannable image display (QPainter)
    ├── thumbnail_strip.py    Scrollable filename strip (QListWidget)
    ├── info_bar.py           Status bar — filename, date, size, position
    └── edit_panel.py         Full-screen edit overlay — all edit UI
```

---

## Data Flow

### Triage (startup → navigation → move)

```
main.py
  └─ Config.load()
  └─ AppController()
  └─ MainWindow(controller)
  └─ controller.library.load(path)       # scans folder, no EXIF read
  └─ controller.album.load(path)
  └─ controller._refresh_collections()
        └─ ThumbnailStrip.load(collection)   # rebuilds filename list
        └─ _refresh_selection()
              └─ ensure_exif(entry)           # EXIF read, lazy, one-time per entry
              └─ PreviewWidget.set_image(path)
              └─ InfoBar.update_info(entry)
              └─ ThumbnailStrip.set_selected(cursor)
```

### Key press → action

```
MainWindow.event()          # intercepts Tab; blocks all keys if edit panel visible
MainWindow.keyPressEvent()
  └─ controller.navigate(±1)
       └─ ImageCollection.move_cursor(delta)
       └─ _refresh_selection()   # no strip rebuild

  └─ controller.send_to_album()
       └─ FileOps.move(src, dst_dir)   # preserves timestamps, pushes undo stack
       └─ ImageCollection.remove() / .add()
       └─ _refresh_collections()       # rebuilds both strips

  └─ controller.open_edit_mode()
       └─ cv2.imread(entry.path)
       └─ MainWindow.show_edit_panel(entry, img)
            └─ EditPanel.load(entry, img)
            └─ EditPanel.setFocus()       # key capture transferred to edit panel
```

### Edit pipeline

```
slider change / filter click
  └─ EditPanel._on_state_changed()
       └─ QTimer(50ms debounce)
            └─ EditPanel._do_update()
                 └─ apply_pipeline(preview_img, state)
                      └─ apply_rotate → apply_crop → apply_exposure
                         → apply_brightness → apply_contrast
                         → apply_saturation → apply_shadows → apply_highlights
                         → film sim / auto adjustment / normalize
                 └─ EditPreview.set_array(out)   # no zoom reset
```

### Save

```
EditPanel._do_save()
  └─ QFileDialog.getSaveFileName()   # OS dialog, already handles overwrite confirmation
  └─ auto-append extension if omitted
  └─ controller.save_edit(state, target_path)
       └─ check original file still exists (guards against background moves)
       └─ apply_pipeline(original_img, state)   # full-resolution render
       └─ tempfile.mkstemp() in target directory
       └─ cv2.imwrite(tmp_path, out)
       └─ shutil.move(tmp_path → target_path)   # atomic — original safe until here
       └─ os.utime(target_path, original_timestamps)
       └─ update ImageCollection if same folder
       └─ close_edit_mode() → _refresh_collections()
```

---

## Key Classes

### `ImageCollection`

Owns a list of `ImageEntry` and a `cursor` integer. Knows nothing about Qt or files.

```python
@dataclass
class ImageEntry:
    path: Path
    filename: str
    exif_date: datetime | None   # None until ensure_exif() is called
    file_size: int
    _exif_loaded: bool = False   # sentinel: True once EXIF attempt was made
```

`load()` scans the folder synchronously but **does not read EXIF** — that would block on large folders. EXIF is read lazily in `ensure_exif(entry)`, called only for the image currently on screen.

`add()` keeps `entries` sorted by filename after insertion.

### `FileOps`

Single-level undo stack (`_undo: _UndoEntry | None`). Every `move()` overwrites the previous undo entry. `trash()` clears it. Timestamps are preserved on every operation via `os.stat` before and `os.utime` after.

`_unique_path()` handles filename conflicts by appending `_1`, `_2`, ... before the extension.

### `AppController`

The only class that touches both the model and the view. No Qt-specific code in the model; no business logic in the widgets.

Key internal methods:
- `_refresh_selection()` — updates preview, info bar, and strip highlights without rebuilding the strip list. Used for navigation (fast).
- `_refresh_collections()` — rebuilds both strips from scratch, then calls `_refresh_selection()`. Used after moves, deletes, and saves (slower, required when list content changes).

### `PreviewWidget`

Replaced `QLabel` with a `QWidget` + `QPainter` approach to support sub-pixel zoom and pan.

State: `_pixmap`, `_zoom` (float, 1.0 = fit-to-window), `_pan` (QPointF offset).

`_compute_draw_rect()` calculates the destination rectangle from these three values. `wheelEvent` adjusts `_zoom` and compensates `_pan` so the pixel under the cursor stays stationary.

`set_image(path)` resets zoom. `set_array(img)` does not (used by edit mode to preserve zoom while sliders change).

### `EditPanel`

The full-screen overlay widget. It is a child of `MainWindow.centralWidget()` and is shown/hidden over the triage layout — no second window is created.

`load(entry, img)` resets `EditState` and triggers a pipeline run.

The **50 ms debounce timer** prevents the pipeline from running on every pixel of slider movement. The timer restarts on each change; the pipeline runs only when 50 ms of silence follows.

For live preview performance, `_preview_img` is a downscaled copy (longest side ≤ 1600 px). Full-resolution rendering only happens inside `save_edit`.

The right-hand panel (adjustments + filters) is wrapped in a `QScrollArea` so all controls are reachable regardless of screen height.

### `FiltersPanel`

Holds a radio button per filter, grouped into Film Simulations and Auto Adjustments. Exposes:

- `set_hidden(hidden: set[str])` — hides the given filter keys; if the currently active filter is in `hidden`, silently resets to `"original"` and emits `changed`.
- `get_hidden() -> set[str]` — returns the current hidden set.
- `manage_clicked` signal — emitted when the user presses **⚙ Manage**.

### `FilterManagerDialog`

A modal `QDialog` opened by `EditPanel._on_manage_filters()`. Presents every filter (except Original) as a checkbox. On accept, the new hidden set is applied via `FiltersPanel.set_hidden()` and persisted to `Config.hidden_filters`.

### `CropOverlay`

A transparent `QWidget` child of `EditPreview`. Uses `WA_TranslucentBackground` to be truly transparent. Draws the dark mask as **four solid rectangles** around the crop rect (not `CompositionMode_Clear`) to avoid compositing artefacts on Linux.

Crop coordinates are stored as **normalised floats (0–1)** of the image dimensions, independent of display scale. Pixel coordinates are computed from the normalised values only at save time.

### `ai_edit.py`

Pure Python module — no Qt, no app imports. Shared between the in-app AI button and `mcp_server.py`.

Key functions:

| Function | Purpose |
|----------|---------|
| `encode_for_api(img, max_side=768)` | Downscale + JPEG encode → base64 string |
| `img_path_to_b64(path, max_side=768)` | Read from disk then encode |
| `call_api(img_b64, prompt, api_key, model)` | Send image + prompt to Claude (Anthropic), return raw text |
| `ollama_is_running(host)` | Returns `True` if Ollama is reachable at `host` (2 s timeout) |
| `call_api_ollama(img_b64, prompt, model, host)` | Send image + prompt to a local Ollama vision model, return raw text |
| `parse_edit_state(text)` | Strip fences, parse JSON, clamp all values to valid ranges |

`SYSTEM_PROMPT` is a module-level constant shared by both backends. `call_api` imports `anthropic` lazily. `call_api_ollama` uses only `urllib.request` from the stdlib — no extra dependency.

### `_AiWorker` (inside `edit_panel.py`)

A `QThread` subclass that runs the AI call off the main thread. Emits `result_ready(dict)` on success and `error(str)` on any exception. `EditPanel` disables the ✨ Apply button while the worker runs and re-enables it on either signal.

**Backend detection** happens once at `EditPanel.__init__`:
1. If `ANTHROPIC_API_KEY` is set → `_ai_backend = "anthropic"`
2. Else if `ollama_is_running(host)` → `_ai_backend = "ollama"`
3. Else → `_ai_backend = "none"` and the button is disabled

The worker receives the backend choice and calls `call_api` or `call_api_ollama` accordingly. The Ollama model and host are read from `OLLAMA_MODEL` / `OLLAMA_HOST` environment variables, defaulting to `gemma3n` and `http://localhost:11434`.

### `mcp_server.py`

Standalone MCP server built with `mcp.server.fastmcp.FastMCP`. Imports `ai_edit` and `edit_ops` directly — no Qt, no running app instance required.

| Tool | Description |
|------|-------------|
| `get_image_info(image_path)` | Returns width, height, file size, and a 400 px base64 thumbnail |
| `suggest_edits(image_path, prompt)` | Calls `ai_edit.call_api` and returns the EditState JSON string |
| `apply_and_save(image_path, state_json, output_path)` | Applies the pipeline at full resolution and saves atomically |

`apply_and_save` uses the same tempfile + `shutil.move` + `os.utime` pattern as `AppController.save_edit` — the original is never touched until the write succeeds and timestamps are always preserved.

---

## Edit Pipeline (`edit_ops.py`)

All functions signature: `(img: np.ndarray, ...) -> np.ndarray`, BGR uint8 input/output.

Fixed execution order in `apply_pipeline`:

| Step | Function | Notes |
|------|----------|-------|
| 1 | `apply_rotate` | cv2.rotate at multiples of 90° |
| 2 | `apply_crop` | array slice on normalised rect |
| 3 | `apply_exposure` | LUT: pixel × 2^stops |
| 4 | `apply_brightness` | HSV V-channel shift |
| 5 | `apply_contrast` | LUT: scale around 128 |
| 6 | `apply_saturation` | HSV S-channel scale |
| 7 | `apply_shadows` | weighted LUT, lower quarter |
| 8 | `apply_highlights` | weighted LUT, upper quarter |
| 9 | film sim / auto / normalize | mutually exclusive, from `filter_name` |

`apply_pipeline` imports `film_luts` at call time (local import) to avoid a circular dependency at module load.

### `EditState` dataclass

```python
@dataclass
class EditState:
    brightness: float = 0.0       # ±100
    contrast: float = 0.0         # ±100
    exposure: float = 0.0         # ±3.0 stops
    saturation: float = 0.0       # ±100
    shadows: float = 0.0          # ±100
    highlights: float = 0.0       # ±100
    filter_name: str = "original" # key into FILM_SIMS, or "normalize" / "auto_*"
    crop_rect: tuple | None = None # (x, y, w, h) normalised 0–1
    rotation: int = 0             # clockwise degrees: 0, 90, 180, 270
```

---

## Film Simulations (`film_luts.py`)

Each simulation is a plain function `(img: np.ndarray) -> np.ndarray`. They compose:

1. **Tone curves** via `_curve(xp, fp)` — builds a 256-entry uint8 LUT using `np.interp`
2. **Per-channel colour adjustments** via `_apply_per_channel(img, lut_b, lut_g, lut_r)`
3. **Saturation shifts** via `_scale_saturation(img, factor)` — works in HSV

`FILM_SIMS: dict[str, callable]` is the public export. `apply_pipeline` looks up `state.filter_name` in this dict.

### Available simulations (20 total)

| Key | Character |
|-----|-----------|
| `provia` | Slight S-curve, neutral colours |
| `velvia` | Strong S-curve, boosted saturation, warm cast |
| `astia` | Lifted shadows, gentle contrast, natural skin |
| `classic_chrome` | Lifted blacks, cool cast, desaturated |
| `classic_neg` | Warm shadows, cyan highlights, high contrast |
| `acros` | Rich B&W with luminosity-weighted conversion |
| `eterna` | Flat cinematic look, muted colours |
| `sepia` | Warm brown monochrome |
| `faded` | Lifted blacks, reduced contrast, slightly cool |
| `cross_process` | Vivid cross-channel shifts (slide in C-41) |
| `fortia_sp` | Ultra-vivid saturation, steeper than Velvia |
| `neopan_1600` | High-contrast B&W, deep blacks |
| `t64` | Strong blue/cool cast (tungsten film in daylight) |
| `pro_800z` | Warm portrait negative, lifted shadows |
| `pro_400h` | Soft pastel portrait, very low contrast |
| `pro_160c` | Natural daylight negative, slightly warm |
| `pro_160s` | Like 160C but cooler and more neutral |
| `superia_1600` | Warm high-ISO consumer, pushed and contrasty |
| `superia_400` | Warm consumer film, slight green cast |
| `superia_100` | Clean slow consumer film, barely warm |

Auto adjustments (`apply_auto_levels`, `apply_auto_tone`, `apply_auto_wb`) live in `edit_ops.py` rather than `film_luts.py` because they analyse the image rather than apply a fixed artistic look.

---

## Configuration

Stored at `~/.config/image_selector/config.json`:

```json
{
  "library_path": "/path/to/library",
  "album_path": "/path/to/album",
  "thumb_height": 120,
  "hidden_filters": ["fortia_sp", "t64"]
}
```

`hidden_filters` is a list of filter keys that the user has chosen to hide via the ⚙ Manage dialog. An empty list (or absent key) means all filters are visible.

`Config.load()` returns a default `Config()` on any read failure (missing file, malformed JSON). `Config.save()` creates parent directories if needed.

---

## Future: Claude Code MCP Integration

The edit pipeline was designed for this from the start. An MCP tool will:

1. Receive a compressed JPEG of the current image
2. Analyse it and return a suggested `EditState` (as JSON)
3. Call `apply_pipeline(original_img, state)` directly — no UI required
4. Return the result to the user for review/adjustment before saving

Because `edit_ops.py` has zero Qt imports, it can be imported and called from any Python context, including an MCP server process.

---

## Running in Development

```bash
cd image_selector
source .venv/bin/activate
python main.py
```

Dependencies: `PyQt6 ≥ 6.6`, `opencv-python ≥ 4.9`, `Pillow ≥ 10.0`, `send2trash ≥ 1.8`, `numpy`.

No build step required. All code is interpreted Python.
