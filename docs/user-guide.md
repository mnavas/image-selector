# Image Selector — User Guide

## What is Image Selector?

Image Selector is a keyboard-driven desktop tool for sorting and editing photos. The idea is simple: you load a source folder (your Library) and a destination folder (your Album), then browse through images one by one and decide what to keep, move, or discard — all without leaving the keyboard.

---

## First Launch

On first launch you will be asked to choose two folders:

1. **Library folder** — your incoming photos (a camera card dump, a dated folder, etc.)
2. **Album folder** — the destination where selected photos go

These are remembered between sessions. You can change either folder at any time using the **Change…** buttons at the top of the window, or via **File → Change Library Folder…** / **File → Change Album Folder…**.

---

## The Triage View

The main window has four areas:

```
┌──────────────────────────────────────────────────────┐
│  Library: /path/to/library        Album: /path/to/album │
├──────────────────────────────────────────────────────┤
│                                                      │
│               [ large image preview ]                │
│                                                      │
├──────────────────────────────────────────────────────┤
│  filename  |  2025-08-07 14:32  |  5.4 MB  |  12/109 │
├──────────────────────────────────────────────────────┤
│  LIBRARY strip  │  ALBUM strip                       │
├──────────────────────────────────────────────────────┤
│ ← Prev  → Next │ ↑ To Album  ↓ To Library │ ✏ Edit ↻ Rotate ⟲ Undo 🗑 Delete │
└──────────────────────────────────────────────────────┘
```

- The **large preview** shows the currently selected image at full quality.
- The **info bar** shows the filename, EXIF date, file size, and position in the collection.
- The **thumbnail strips** show all images as filename labels. The active strip has a blue border.
- Click any filename in either strip to jump to that image.

---

## Triage Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` | Previous image in the active panel |
| `→` | Next image in the active panel |
| `↑` | Move current image from Library → Album |
| `↓` | Move current image from Album → Library |
| `Tab` | Switch focus between Library and Album panels |
| `Del` / `Backspace` | Send current image to the system trash |
| `Ctrl+Z` | Undo the last move |
| `E` | Open edit mode for the current image |
| `R` | Quick rotate 90° clockwise and save immediately |

> **Tip:** Moving an image with `↑` or `↓` never deletes it — it just changes which folder it lives in. Use `Ctrl+Z` to move it back if you change your mind. Undo only works for the most recent move.

---

## Zoom and Pan (Triage View)

| Action | Result |
|--------|--------|
| Mouse wheel up | Zoom in (×1.25 per step) |
| Mouse wheel down | Zoom out (×0.8 per step) |
| Left-drag | Pan the image when zoomed in |
| Double-click | Reset zoom to fit-window |

Zoom resets automatically when you navigate to a different image.

---

## Edit Mode

Press **`E`** or click the **✏ Edit** button to open the full-screen editor for the current image. All edits are non-destructive — the original file is not changed until you click **Save As…**.

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back  filename.jpg  ↺ Rotate L  ↻ Rotate R  Crop  Save As…  │
├───────────────────────────────────────────┬─────────────────────┤
│                                           │  ADJUSTMENTS        │
│                                           │  Brightness         │
│           [ image preview ]               │  Contrast           │
│         (zoom + pan + crop)               │  Exposure           │
│                                           │  Saturation         │
│                                           │  Shadows            │
│                                           │  Highlights         │
│                                           ├─────────────────────┤
│                                           │  FILTERS            │
│                                           │  ○ Original         │
│                                           │  ...                │
└───────────────────────────────────────────┴─────────────────────┘
```

### Edit Mode Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Esc` | Back to triage (edits discarded) |
| `Ctrl+S` | Save As |
| `Enter` | Confirm crop (when crop tool is active) |

---

## Adjustments

All sliders start at zero (no effect). Drag right to increase, left to decrease.

| Slider | Range | What it does |
|--------|-------|--------------|
| Brightness | ±100 | Shifts the overall lightness of the image |
| Contrast | ±100 | Expands or compresses the tonal range around mid-grey |
| Exposure | ±3.0 stops | Multiplies luminance by 2^stops — like changing aperture |
| Saturation | ±100 | Boosts or reduces colour intensity |
| Shadows | ±100 | Lifts or crushes the darkest parts of the image |
| Highlights | ±100 | Rolls off or boosts the brightest parts |

Click **Reset** to return all sliders to zero.

---

## Filters

Select a filter by clicking its radio button. Only one filter can be active at a time. Selecting a new filter replaces the previous one. Selecting **Original** removes all filter effects.

### Film Simulations

| Filter | Character |
|--------|-----------|
| **Original** | No filter — shows the image with only your slider adjustments |
| **Provia** | Slight S-curve, accurate and neutral colours |
| **Velvia** | Punchy contrast, boosted saturation, warm cast — great for landscapes |
| **Astia** | Lifted shadows, subdued contrast — flattering for portraits |
| **Classic Chrome** | Lifted blacks, cool cast, desaturated — documentary feel |
| **Classic Neg** | Warm shadows, cyan highlights, high contrast — cinematic |
| **Acros** | Rich black-and-white with deep blacks |
| **Eterna** | Flat, low-contrast cinematic look — good starting point for grading |
| **Sepia** | Warm brown monochrome |
| **Faded / Matte** | Lifted blacks, reduced contrast — faded Instagram look |
| **Cross Process** | Vivid colour shifts inspired by slide film in C-41 chemistry |
| **Fortia SP** | Ultra-saturated, more extreme than Velvia — vivid landscapes |
| **Neopan 1600** | High-contrast B&W, deep blacks, high-ISO character |
| **T64 (Tungsten)** | Tungsten-balanced slide film — strong cool/blue cast in daylight |
| **Pro 800Z** | Warm portrait negative, natural skin tones, lifted shadows |
| **Pro 400H** | Soft pastel portrait negative, very low contrast — natural light look |
| **Pro 160C** | Natural daylight negative, clean, slightly warm |
| **Pro 160S** | Like 160C but cooler and more neutral |
| **Superia 1600** | Warm consumer high-ISO film, pushed and contrasty |
| **Superia 400** | Warm mid-range consumer film, slight green cast |
| **Superia 100** | Clean slow consumer film, barely warm |

### Auto Adjustments

These analyse the image mathematically and apply a correction automatically. They work best as a starting point — you can fine-tune with the sliders afterwards.

| Filter | What it does |
|--------|-------------|
| **Normalize (CLAHE)** | Adaptive histogram equalisation on local regions — great for flat or hazy images |
| **Auto Levels** | Stretches each colour channel to its full range — fixes exposure and colour casts together |
| **Auto Tone** | Stretches luminance only — fixes exposure while preserving the colour balance |
| **Auto White Balance** | Grey-world correction — removes the yellow/blue cast from artificial or mixed lighting |

### Managing Visible Filters

With 20+ film simulations the list can get long. Click **⚙ Manage** at the top of the Filters section to open the filter manager.

- Every filter has a checkbox — **checked** means visible, **unchecked** means hidden.
- Use **Select All** / **Clear All** as shortcuts.
- **Original** is always visible and cannot be hidden.
- If the filter you currently have selected gets hidden, the panel automatically switches back to **Original** so nothing breaks.
- Your choices are saved and restored the next time you open the app.

---

## Crop Tool

1. Click the **Crop** button in the edit panel header.
2. A crop rectangle appears over the image. Drag the **corner or edge handles** to resize it.
3. Drag inside the rectangle to move it.
4. The crop is always locked to the **original image's aspect ratio** — you cannot change the shape.
5. Click **✓ Apply Crop** (or press `Enter`) to commit. Press `Esc` to cancel.

---

## Rotate

- **In triage view:** click **↻ Rotate** or press `R` — rotates 90° clockwise and saves to disk immediately.
- **In edit mode:** click **↺ Rotate L** or **↻ Rotate R** in the header — rotates left (CCW) or right (CW) as part of the non-destructive pipeline. The rotation is saved when you click **Save As…**.

---

## Save As

Click **Save As…** or press `Ctrl+S` in edit mode.

- The dialog opens pre-filled with the original filename and folder.
- **If you keep the same name:** the original file is overwritten with the edited version.
- **If you type a new name:** the edited image is saved as a new file alongside the original. The original is untouched and remains in the strip.
- **If you omit the extension** (e.g. type `my_edit` instead of `my_edit.jpg`): the original's extension is used automatically.
- The original file's **creation date is always preserved** on the saved file.

---

## File Safety

- Moves (`↑` / `↓`) preserve the original creation date using `os.utime`.
- Deletes go to the **system trash** (not permanently deleted). You can recover them from your file manager's Trash.
- Saves write to a **temporary file first**, then rename it into place. The original is never touched until the write succeeds. If anything goes wrong you will see an error dialog and the original is safe.

---

## Supported Formats

`.jpg` / `.jpeg` · `.png` · `.tiff` / `.tif`

HEIC (iPhone) and RAW (Nikon NEF, GoPro GPR) are planned for a future version.
