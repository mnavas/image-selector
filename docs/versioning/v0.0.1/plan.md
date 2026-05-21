# v0.0.1 — Implementation Plan

## Prerequisites

```bash
cd image_selector
python -m venv .venv && source .venv/bin/activate
pip install PyQt6 opencv-python Pillow send2trash
```

---

## Phase 1 — Foundation (no UI)

Build and unit-test the data and filesystem layer independently of Qt.

### Step 1 — Project scaffold
- Create directory structure as defined in `analysis.md`
- Create `requirements.txt`
- Create empty `__init__.py` files

### Step 2 — `config.py`
- `Config` dataclass with `library_path`, `album_path`, `thumb_height`
- `Config.load()` — reads `~/.config/image_selector/config.json`; fills defaults if missing
- `Config.save()` — writes back to disk

### Step 3 — `image_collection.py`
- `ImageEntry` dataclass: `path`, `filename`, `exif_date`, `file_size`
- `ImageCollection.load(path)` — scans folder for `jpg|jpeg|png|tiff` files, sorts by filename, reads EXIF date via Pillow
- `ImageCollection.current()`, `move_cursor(delta)`, `add(entry)`, `remove(index)`

### Step 4 — `file_ops.py`
- `FileOps.move(src, dst_dir)` — `shutil.move`, restore timestamps with `os.utime`, push to undo stack
- `FileOps.trash(path)` — `send2trash`
- `FileOps.undo()` — reverses last move; clears stack entry

**Checkpoint:** write a short `test_ops.py` script that loads a temp folder, moves a file, checks timestamps, trashes a file, and undoes a move.

---

## Phase 2 — Core Widgets

Build each widget in isolation; each should be runnable as `python -m widgets.<name>` with dummy data for visual verification.

### Step 5 — `thumbnail_cache.py`
- LRU dict capped at 200 entries
- `get(path, height)` — decode with `cv2.imread`, resize with `cv2.resize`, convert BGR→RGB, wrap in `QImage`, return `QPixmap`
- Handle decode failure (return a grey placeholder pixmap)

### Step 6 — `widgets/preview_widget.py`
- `QLabel` subclass, `setAlignment(Qt.AlignCenter)`
- `set_image(path)` — loads via `ThumbnailCache` at display size; on `resizeEvent` re-scales the cached original
- Displays a grey placeholder when no image is set

### Step 7 — `widgets/thumbnail_strip.py`
- `QScrollArea` → `QWidget` → `QHBoxLayout` of `ThumbnailCell` (`QLabel` subclass)
- `ThumbnailCell` emits `clicked(index)` signal
- `ThumbnailStrip.load(collection)` — clears and rebuilds all cells
- `ThumbnailStrip.set_selected(index)` — highlights cell, calls `ensureWidgetVisible`
- `ThumbnailStrip.set_focused(bool)` — changes container border color

### Step 8 — `widgets/info_bar.py`
- Single `QLabel`
- `update(entry, collection)` — formats `"filename  |  date  |  size  |  n / total"`

---

## Phase 3 — Controller + Main Window

### Step 9 — `app_controller.py`
- Holds `library: ImageCollection`, `album: ImageCollection`, `focus`, `ops: FileOps`
- Implements all actions: `navigate`, `send_to_album`, `send_to_library`, `delete_current`, `switch_focus`, `undo`
- `refresh_ui()` pushes current state to all widgets via direct method calls (no signals needed at this scale)

### Step 10 — `widgets/main_window.py`
- `QMainWindow` with `QVBoxLayout`: `PreviewWidget` → `InfoBar` → `QSplitter(LibraryStrip | AlbumStrip)` → `ActionBar`
- `ActionBar`: five `QPushButton` instances wired to controller methods
- `keyPressEvent` maps Qt key codes to controller methods:
  - `Qt.Key_Left/Right` → `navigate`
  - `Qt.Key_Up` → `send_to_album`
  - `Qt.Key_Down` → `send_to_library`
  - `Qt.Key_Delete` → `delete_current`
  - `Qt.Key_Tab` → `switch_focus`
  - `Ctrl+Z` → `undo`

### Step 11 — Session setup dialog + folder change buttons
- On first launch (or if paths are missing from config): `QFileDialog.getExistingDirectory` for Library, then for Album
- No in-app folder creation; user picks any existing folder via `QFileDialog.getExistingDirectory`
- Paths written to `Config.save()` immediately
- Folder label row contains a small "Change…" `QPushButton` next to each label; clicking either opens `QFileDialog.getExistingDirectory`, reloads the collection, and persists the new path — usable at any time without restarting

### Step 12 — `main.py`
- `QApplication` init
- Load `Config`; show setup dialog if paths are empty or missing
- Instantiate `AppController` + `MainWindow`
- `sys.exit(app.exec())`

---

## Phase 4 — Integration & Polish

### Step 13 — Wire everything together
- Run end-to-end: open real photo folder, navigate, move, delete, undo
- Verify timestamps are preserved after move (check with `stat` in terminal)
- Verify focus switching and thumbnail scroll-to-selected work correctly

### Step 14 — Thumbnail lazy loading
- On strip load, render only the thumbnails currently in the visible viewport
- Connect `QScrollArea.horizontalScrollBar().valueChanged` to trigger rendering of newly visible cells
- Queue off-screen cells with `QTimer.singleShot(0, ...)` to avoid blocking the UI on large card dumps

### Step 15 — Final checks
- Test with both Nikon sequential filenames (`DSC_0001.JPG`) and GoPro (`GH010001.MP4` excluded, `GH010001.JPG` included)
- Test empty album folder (no crash on `current()`)
- Test single-image folder (no crash on navigation at boundaries)
- Update `README.md` with install and run instructions

---

## Deliverables

| File | Status |
|------|--------|
| `requirements.txt` | done |
| `config.py` | done |
| `image_collection.py` | done |
| `file_ops.py` | done |
| `thumbnail_cache.py` | done |
| `widgets/__init__.py` | done |
| `widgets/preview_widget.py` | done |
| `widgets/thumbnail_strip.py` | done |
| `widgets/info_bar.py` | done |
| `widgets/main_window.py` | done |
| `app_controller.py` | done |
| `main.py` | done |
