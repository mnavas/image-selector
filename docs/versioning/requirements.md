# Image Selector — Requirements

## Overview

A desktop image triage and light-editing tool. The user loads a source folder (library) and an album folder, browses images with the keyboard, moves images between folders, and applies quick edits. File creation dates are always preserved.

---

## Technology Stack

- **Language**: Python 3
- **Image processing**: OpenCV (`cv2`)
- **GUI framework**: PyQt6 (or PySide6) — required for responsive keyboard handling and custom widgets
- **Metadata / date preservation**: `os.utime` + `piexif` or `Pillow` for EXIF reading

---

## Session Setup

On launch the user selects:
1. **Library folder** — the incoming source folder (e.g. `DCIM/100NIKON`). All image files in the folder are loaded; sub-folders are not traversed.
2. **Album folder** — either an existing folder or a new one created via a dialog. The app remembers the last used paths between sessions (stored in a local config file).

Images are sorted by **filename** (camera sequential order) within each folder.

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  [ Library: DCIM/100NIKON ]    [ Album: Hiking_2025 ]   │  ← folder labels / change buttons
├─────────────────────────────────────────────────────────┤
│                                                         │
│                  [ LARGE PREVIEW ]                      │  ← active image, fills available space
│                                                         │
│  filename.jpg  |  2024-07-15 10:32  |  3.4 MB  |  4/87 │  ← info bar
├──────────────────────────┬──────────────────────────────┤
│ LIBRARY (focused*)       │ ALBUM                        │
│ [th][th][th][th][th] ... │ [th][th][th][th][th] ...     │  ← scrollable thumbnail strips
│        ↑ selected        │                              │
├──────────────────────────┴──────────────────────────────┤
│  [← Prev]  [→ Next]  [↑ To Album]  [🗑 Delete]  [Edit] │  ← action bar
└─────────────────────────────────────────────────────────┘
```

- The **large preview** always shows the image currently selected in either strip.
- Clicking a thumbnail in either strip focuses that panel and selects that image.
- The **focused panel** is highlighted with a colored border.
- The **info bar** shows filename, EXIF creation date, file size, and current position (n/total).

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` | Previous image in focused panel |
| `→` | Next image in focused panel |
| `↑` | Move current image from **Library → Album** |
| `↓` | Move current image from **Album → Library** |
| `Del` / `Supr` | Send current image to system trash |
| `Tab` | Switch focus between Library and Album panels |
| `E` | Open edit mode for current image |
| `Esc` | Close edit mode / cancel |
| `Ctrl+Z` | Undo last move (not available after delete) |

---

## File Operations

### Move (Library ↔ Album)
- File is physically moved to the destination folder.
- Original **file creation date and modification date are preserved** (`os.utime`).
- EXIF `DateTimeOriginal` is never modified.
- After the move, the cursor advances to the next image in the source panel.

### Delete
- File is sent to the **system trash** (use `send2trash` library) — not permanently deleted.
- Creation date is irrelevant since the file is not modified.
- Cursor advances to the next image.

### Undo last move
- A single-level undo moves the file back and restores the previous cursor position.

---

## Editing

All edits are **temporary** until explicitly saved — the original file is never touched during the editing session.

### Available operations (all accessible from Edit mode)

| Operation | Details |
|-----------|---------|
| **Rotate 90°** | Clockwise / counter-clockwise. Available directly from main view via `R` key. |
| **Crop / Straighten** | Draw crop rectangle with mouse. Free-angle straighten slider (±15°). |
| **Brightness / Contrast / Exposure** | Three sliders with live preview. |
| **Preset color filters** | One-click presets: Original, B&W, Warm, Cool, Vivid, Fade. Implemented via OpenCV LUTs. |

### Edit workflow
1. Press `E` to enter edit mode — full-screen view with editing controls on the right panel.
2. All changes are **previewed live** via OpenCV on an in-memory copy; the original file is untouched.
3. **Save** (`Ctrl+S` or Save button) — opens a **Save As** dialog pre-filled with the original filename.
   - If the user keeps the same filename and confirms the overwrite prompt, the file is replaced and the original creation date is re-stamped.
   - If the user enters a different filename, the edited copy is saved as a new file (original creation date is copied to the new file); the original remains unchanged.
4. **Cancel** (`Esc`) — discards all in-memory changes and exits edit mode without touching any file.

---

## Image Support

Supported formats: `JPEG`, `PNG`, `TIFF`, `HEIC` (read-only via `pillow-heif`), `RAW` formats via optional `rawpy` (Nikon NEF, GoPro GPR).

---

## Configuration

Stored in `~/.config/image_selector/config.json`:
- Last used library path
- Last used album path
- Thumbnail strip height (default: 120 px)
- Preferred filter preset

---

## Out of Scope (v1)

- Face detection or AI tagging
- Video files
- Cloud sync or remote folders
- Batch editing across multiple images at once
- Rating / star system
