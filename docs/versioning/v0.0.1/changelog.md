# Changelog — v0.0.1

## Status: implemented

---

## Fixed

### Performance — folder load freeze
- `image_collection.load()` no longer reads EXIF for every file on load. Loading a folder is now instant regardless of size.
- EXIF date is read lazily via `ensure_exif(entry)` — only once, only when that image is actually displayed. Result is cached on the entry.
- `ThumbnailStrip` rewritten as a `QListWidget` (horizontal flow, no wrapping). Replaces the broken `QScrollArea` + manual `QHBoxLayout` approach that had two root causes: (1) the container widget never had an explicit height set so it rendered as 0px tall, and (2) `deleteLater()` on old cells was deferred while new cells were inserted in the same event tick, causing Qt object confusion. `QListWidget` handles sizing, selection highlight, scrolling, and item reuse natively. Uses `_updating` flag to block `currentRowChanged` signal when selection is set programmatically, preventing a feedback loop with the controller.

---

## Added

### Core data layer
- `config.py` — `Config` dataclass; reads/writes `~/.config/image_selector/config.json`; fills defaults when missing; persists library path, album path, and thumbnail height.
- `image_collection.py` — `ImageEntry` dataclass and `ImageCollection` class; loads a folder's images sorted by filename; reads EXIF `DateTimeOriginal` via Pillow at load time; supports `add`, `remove`, `move_cursor`, `current`.
- `file_ops.py` — `FileOps` class; `move` preserves `atime`/`mtime` via `os.utime`; handles filename conflicts by appending `_1`, `_2`, ...; `trash` delegates to `send2trash`; single-slot in-memory undo stack; clears undo on trash.

### Image processing
- `thumbnail_cache.py` — LRU `ThumbnailCache` capped at 200 entries; decodes with `cv2.imread`, resizes with `cv2.INTER_AREA`, converts BGR→RGB, wraps in `QImage`/`QPixmap`; returns grey placeholder on decode failure.

### Widgets
- `widgets/preview_widget.py` — `PreviewWidget` (`QLabel` subclass); loads full image via OpenCV; scales to available space preserving aspect ratio on every `resizeEvent`; dark `#1a1a1a` background.
- `widgets/info_bar.py` — `InfoBar` (`QLabel`); displays `filename | EXIF date | size MB | n / total`; updates on every selection change.
- `widgets/thumbnail_strip.py` — `ThumbnailStrip` (`QScrollArea`); lazy loads visible cells on scroll (defers off-screen rendering via `QTimer.singleShot`); highlights selected cell with blue border; highlights focused panel with blue container border; auto-scrolls to keep selected cell visible.

### Application
- `widgets/main_window.py` (folder row) — added a small **"Change…"** `QPushButton` next to both the Library and Album folder labels; clicking either opens `QFileDialog.getExistingDirectory` pre-seeded with the current path, reloads the collection, updates the label, and persists the new path to config — available at any time without restarting. Buttons are also mirrored in **File → Change Library Folder…** / **File → Change Album Folder…**.
- `app_controller.py` — `AppController`; owns both `ImageCollection` instances and `FileOps`; separates `_refresh_selection` (no strip rebuild, used for navigation) from `_refresh_collections` (full strip reload, used after moves/deletes); handles undo by syncing in-memory collections after filesystem reversal.
- `widgets/main_window.py` — `MainWindow` (`QMainWindow`); dark Fusion theme; large preview + info bar + splitter with two labeled thumbnail strips + action button row; menu bar with "Change Library Folder…" / "Change Album Folder…"; intercepts `Tab` via `event()` override to prevent Qt from routing it as focus-change; keyboard shortcuts: `←/→` navigate, `↑` to album, `↓` to library, `Del/Backspace` trash, `Tab` switch panel focus, `Ctrl+Z` undo.
- `main.py` — entry point; validates configured paths on startup; prompts folder selection dialogs if paths are missing or no longer exist; loads both collections and calls initial `_refresh_collections`.

---

## Technical decisions recorded in this version

- **Lazy thumbnail loading** — cells are rendered only when within two viewport-widths of the current scroll position.
- **No in-app album folder creation** — user selects any existing folder via standard `QFileDialog`.
- **Undo in-memory only** — undo stack is cleared on app exit.
- **Filename conflict handling** — `file_ops._unique_path` appends `_1`, `_2`, ... to avoid silent overwrites on move.
- **Separate refresh paths** — `navigate` skips strip rebuild for performance; only move/delete/undo triggers `_refresh_collections`.

---

## Deferred to v0.0.2

- Edit mode: crop/straighten, brightness/contrast, preset filters, rotate 90°
- HEIC support (`pillow-heif`)
- RAW support (`rawpy` for Nikon NEF / GoPro GPR)
