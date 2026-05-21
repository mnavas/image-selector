# v0.0.1 — Implementation Analysis

## Version Scope

v0.0.1 delivers the **core triage workflow** only. Editing features are deferred to v0.0.2.

**In scope:**
- Session setup (folder selection, config persistence)
- Main window layout: large preview + two thumbnail strips
- Keyboard navigation (←/→/↑/↓/Tab/Del/Ctrl+Z)
- Move images Library ↔ Album (preserve creation date)
- Delete to system trash
- Single-level undo for moves
- Info bar (filename, date, size, position)
- Folder change buttons — visible "Change…" button next to each folder label, callable at any time

**Deferred to v0.0.2:**
- Edit mode (crop, filters, brightness/contrast, rotate)
- HEIC and RAW format support (`pillow-heif`, `rawpy`)

---

## Architecture

The app follows a simple **MVC** pattern suited to a single-window PyQt6 desktop app.

```
┌──────────────────────────────────────────────────────┐
│  MainWindow (QMainWindow)                            │
│  ├── PreviewWidget       (QLabel, scaled pixmap)     │
│  ├── InfoBar             (QLabel row)                │
│  ├── ThumbnailStrip ×2   (QScrollArea + QHBoxLayout) │
│  └── ActionBar           (QPushButton row)           │
├──────────────────────────────────────────────────────┤
│  AppController                                       │
│  ├── ImageCollection ×2  (Library, Album)            │
│  ├── FileOps             (move, trash, undo stack)   │
│  └── Config              (JSON read/write)           │
└──────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### `main.py`
Entry point. Instantiates `QApplication`, loads `Config`, shows `MainWindow`.

### `config.py` — `Config`
Reads/writes `~/.config/image_selector/config.json`.

Fields:
```json
{
  "library_path": "/path/to/DCIM/100NIKON",
  "album_path":   "/path/to/Albums/Hiking_2025",
  "thumb_height": 120
}
```

### `image_collection.py` — `ImageCollection`
Represents one folder's image list.

```python
class ImageCollection:
    path: str
    entries: list[ImageEntry]   # sorted by filename
    cursor: int                 # currently selected index

    def load(path: str)
    def current() -> ImageEntry
    def move_cursor(delta: int)
```

```python
@dataclass
class ImageEntry:
    path: Path
    filename: str
    exif_date: datetime | None   # DateTimeOriginal from EXIF
    file_size: int               # bytes
```

EXIF date is read once at load time using `Pillow` (fast, no full decode needed).

### `file_ops.py` — `FileOps`
All filesystem mutations. Keeps a single-slot undo stack.

```python
class FileOps:
    def move(src: Path, dst_dir: Path) -> Path
        # shutil.move, then os.utime to restore timestamps
    def trash(path: Path)
        # send2trash.send2trash
    def undo() -> tuple[Path, Path] | None
        # reverses the last move only
```

Timestamps are captured with `os.stat` before the move and restored with `os.utime` after.

### `thumbnail_cache.py` — `ThumbnailCache`
Lazy, LRU-bounded thumbnail generator (max 200 entries).

```python
class ThumbnailCache:
    def get(path: Path, height: int) -> QPixmap
        # returns cached pixmap or generates via cv2.imread + resize
```

OpenCV (`cv2.imread` + `cv2.resize`) is used here as specified. Result is converted to `QPixmap` via `QImage`.

### `widgets/main_window.py` — `MainWindow`
Top-level `QMainWindow`. Owns the layout and routes keyboard events to `AppController`.

Key signals wired:
- `keyPressEvent` → controller actions
- Thumbnail click → `set_focus(panel)` + `set_cursor(index)`
- Button clicks → same controller actions as keyboard

### `widgets/preview_widget.py` — `PreviewWidget`
`QLabel` subclass. Scales the current `QPixmap` to fill available space while preserving aspect ratio (`Qt.KeepAspectRatio`). Reacts to window resize.

### `widgets/thumbnail_strip.py` — `ThumbnailStrip`
`QScrollArea` containing a horizontal `QWidget` with a `QHBoxLayout` of `ThumbnailCell` items.

- Selected cell is highlighted with a colored border.
- On cursor change, auto-scrolls to keep selected cell visible (`ensureWidgetVisible`).
- Focused panel gets a distinct border color on the strip container.

### `widgets/info_bar.py` — `InfoBar`
Single `QLabel` row. Updated on every cursor change. Displays:
`filename  |  YYYY-MM-DD HH:MM  |  X.X MB  |  n / total`

### `app_controller.py` — `AppController`
Mediates between widgets and model. Holds references to both `ImageCollection` instances and `FileOps`. Exposes one method per user action; each method mutates state and calls `refresh_ui()`.

```python
class AppController:
    library: ImageCollection
    album:   ImageCollection
    focus:   Literal["library", "album"]
    ops:     FileOps

    def navigate(delta: int)      # ←/→
    def send_to_album()           # ↑
    def send_to_library()         # ↓
    def delete_current()          # Del
    def switch_focus()            # Tab
    def undo()                    # Ctrl+Z
    def refresh_ui()              # pushes state to all widgets
```

---

## Data Flow: Move Image (↑ Library → Album)

```
User presses ↑
  → MainWindow.keyPressEvent
  → AppController.send_to_album()
      → capture: entry = library.current()
      → FileOps.move(entry.path, album.path)
          → shutil.move()
          → os.utime() restores timestamps
          → push to undo stack
      → library.remove(cursor)      # remove entry from list
      → album.add(new_entry)        # insert into sorted position
      → library.move_cursor(+0)     # stay at same index (now next image)
  → AppController.refresh_ui()
      → PreviewWidget.set_image(library.current())
      → LibraryStrip.update(library)
      → AlbumStrip.update(album)
      → InfoBar.update(library.current(), library)
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `PyQt6` | ≥ 6.6 | GUI framework |
| `opencv-python` | ≥ 4.9 | Thumbnail generation, image decode |
| `Pillow` | ≥ 10.0 | EXIF date reading (`_getexif`) |
| `send2trash` | ≥ 1.8 | Cross-platform trash |

All installable via `pip`. No system dependencies beyond standard Python 3.11+.

---

## Project Structure

```
image_selector/
├── main.py
├── app_controller.py
├── config.py
├── image_collection.py
├── file_ops.py
├── thumbnail_cache.py
├── widgets/
│   ├── __init__.py
│   ├── main_window.py
│   ├── preview_widget.py
│   ├── thumbnail_strip.py
│   └── info_bar.py
├── requirements.txt
└── docs/
    ├── requirements.md
    └── versioning/
        └── v0.0.1/
            └── analysis.md
```

---

## Implementation Tasks

| # | Task | Notes |
|---|------|-------|
| 1 | `Config` — read/write JSON, defaults | |
| 2 | `ImageEntry` + `ImageCollection.load` | EXIF date via Pillow |
| 3 | `FileOps.move` + timestamp preservation | Test on Linux & macOS |
| 4 | `FileOps.trash` | `send2trash` |
| 5 | `FileOps.undo` | Single-slot stack |
| 6 | `ThumbnailCache` with LRU | OpenCV decode + QPixmap convert |
| 7 | `PreviewWidget` — scaled display + resize | |
| 8 | `ThumbnailStrip` — render, select, scroll | |
| 9 | `InfoBar` — format and display | |
| 10 | `MainWindow` — layout assembly + keyboard events | |
| 11 | `AppController` — wire all actions | |
| 12 | Session setup dialog (folder picker) | Qt file dialog |
| 13 | `main.py` — bootstrap + config load | |
| 14 | `requirements.txt` + smoke test | |

---

## Decisions

1. **Thumbnail loading** — lazy on scroll. Visible thumbnails load immediately; off-screen ones are queued via `QTimer.singleShot(0, ...)` as the strip scrolls. No progress bar needed.
2. **Album folder creation** — standard `QFileDialog.getExistingDirectory`. No in-app subfolder creation; the user creates folders in the OS file manager beforehand.
3. **Undo across sessions** — in-memory only. Closing the app clears the undo stack. Acceptable for v0.0.1.
