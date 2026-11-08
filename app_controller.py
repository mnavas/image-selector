from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np

import img_io
from edit_ops import EditState, apply_pipeline, apply_rotate
from file_ops import FileOps
from image_collection import (
    ImageCollection,
    ImageEntry,
    ensure_exif,
    image_dimensions,
    invalidate_dimensions,
)

if TYPE_CHECKING:
    from widgets.main_window import MainWindow


class AppController:
    # Album print-check targets: pixel aspect ratio (w/h) for the landscape
    # orientation. Either orientation passes, so the portrait inverse counts too.
    _CHECK_RATIOS = {"4r": 3 / 2, "instax": 4 / 3}
    _CHECK_TOL = 0.03   # ±3% — comfortably separates 3:2 (1.5) from 4:3 (1.333)

    def __init__(self) -> None:
        self.library = ImageCollection()
        self.album = ImageCollection()
        self.focus: Literal["library", "album"] = "library"
        self.ops = FileOps()
        self.copy_mode = False   # when True, send_to_* copies instead of moving
        self.album_check = "none"   # "none" | "4r" | "instax"
        self._window: MainWindow | None = None
        self._edit_entry: ImageEntry | None = None
        self._edit_original: np.ndarray | None = None

    def set_window(self, window: MainWindow) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def navigate(self, delta: int) -> None:
        self._active().move_cursor(delta)
        self._refresh_selection()

    def send_to_album(self) -> None:
        if self.focus != "library" or self.library.is_empty():
            return
        entry = self.library.current()
        assert entry is not None
        idx = self.library.cursor
        if self.copy_mode:
            new_path = self.ops.copy(entry.path, Path(self.album.path))
        else:
            new_path = self.ops.move(entry.path, Path(self.album.path))
        new_entry = ImageEntry(
            path=new_path,
            filename=new_path.name,
            exif_date=entry.exif_date,
            file_size=entry.file_size,
        )
        if not self.copy_mode:
            self.library.remove(idx)
        self.album.add(new_entry)
        self._refresh_collections()

    def send_to_library(self) -> None:
        if self.focus != "album" or self.album.is_empty():
            return
        entry = self.album.current()
        assert entry is not None
        idx = self.album.cursor
        if self.copy_mode:
            new_path = self.ops.copy(entry.path, Path(self.library.path))
        else:
            new_path = self.ops.move(entry.path, Path(self.library.path))
        new_entry = ImageEntry(
            path=new_path,
            filename=new_path.name,
            exif_date=entry.exif_date,
            file_size=entry.file_size,
        )
        if not self.copy_mode:
            self.album.remove(idx)
        self.library.add(new_entry)
        self._refresh_collections()

    def delete_current(self) -> None:
        active = self._active()
        if active.is_empty():
            return
        entry = active.current()
        assert entry is not None
        idx = active.cursor
        self.ops.trash(entry.path)
        active.remove(idx)
        self._refresh_collections()

    def switch_focus(self) -> None:
        self.focus = "album" if self.focus == "library" else "library"
        self._refresh_selection()

    def undo(self) -> None:
        result = self.ops.undo()
        if result is None:
            return
        kind, was_at, now_at = result
        if kind == "copy":
            self._remove_after_undo(was_at)
        else:
            self._sync_after_undo(was_at, now_at)
        self._refresh_collections()

    # ------------------------------------------------------------------
    # Edit mode
    # ------------------------------------------------------------------

    def open_edit_mode(self) -> None:
        if self._window is None:
            return
        entry = self._active().current()
        if entry is None:
            return
        img = img_io.imread(entry.path)
        if img is None:
            return
        self._edit_entry = entry
        self._edit_original = img
        self._window.show_edit_panel(entry, img)

    def close_edit_mode(self) -> None:
        if self._window is None:
            return
        self._edit_entry = None
        self._edit_original = None
        self._window.hide_edit_panel()

    def save_edit(self, state: EditState, target_path: Path) -> None:
        if self._edit_entry is None or self._edit_original is None:
            return

        import tempfile, shutil

        try:
            if not self._edit_entry.path.exists():
                raise FileNotFoundError(
                    f"{self._edit_entry.filename} no longer exists at its original location.\n"
                    "It may have been moved while the editor was open."
                )
            stat = os.stat(self._edit_entry.path)
            out = apply_pipeline(self._edit_original, state)

            # Write to a temp file in the same directory first — the original is
            # never touched until the write is confirmed successful.
            tmp_fd, tmp_name = tempfile.mkstemp(
                suffix=target_path.suffix, dir=target_path.parent
            )
            os.close(tmp_fd)
            tmp_path = Path(tmp_name)

            ok = img_io.imwrite(tmp_path, out)
            if not ok:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(f"cv2 could not encode the image (check the file extension: {target_path.suffix})")

            # Atomically move the temp file into place
            shutil.move(str(tmp_path), str(target_path))
            os.utime(target_path, (stat.st_atime, stat.st_mtime))

            active = self._active()
            if target_path == self._edit_entry.path:
                # Overwrite in-place: update file size on the existing entry
                for i, e in enumerate(active.entries):
                    if e.path == self._edit_entry.path:
                        active.entries[i].file_size = target_path.stat().st_size
                        invalidate_dimensions(active.entries[i])
                        break
            elif target_path.parent == self._edit_entry.path.parent:
                # New name in the same folder: add to the collection so it
                # appears in the strip alongside the original
                new_entry = ImageEntry(
                    path=target_path,
                    filename=target_path.name,
                    exif_date=self._edit_entry.exif_date,
                    file_size=target_path.stat().st_size,
                )
                active.add(new_entry)
            # Saved to a different folder: just written to disk, not tracked

        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            from i18n import tr
            QMessageBox.critical(
                self._window,
                tr("save_failed_title"),
                tr("save_failed_body").format(error=exc),
            )
            return

        self.close_edit_mode()
        self._refresh_collections()

    def apply_look_to_album(self, state: EditState, out_dir: Path) -> tuple[int, int, list[str]]:
        """Apply `state` to every album photo, writing edited COPIES into out_dir.

        Originals are never modified; each output is written atomically (temp file
        + move) and an output that would land on top of an original is skipped, so
        the source set is safe even if out_dir is the album folder itself. Returns
        (saved, failed, failure_messages).
        """
        import shutil
        import tempfile

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved, failed, errors = 0, 0, []
        for entry in list(self.album.entries):
            target = out_dir / entry.filename
            try:
                if target.resolve() == entry.path.resolve():
                    raise RuntimeError("would overwrite the original — skipped")
                img = img_io.imread(entry.path)
                if img is None:
                    raise RuntimeError("could not read the image")
                out = apply_pipeline(img, state)
                tmp_fd, tmp_name = tempfile.mkstemp(suffix=entry.path.suffix, dir=out_dir)
                os.close(tmp_fd)
                if not img_io.imwrite(Path(tmp_name), out):
                    Path(tmp_name).unlink(missing_ok=True)
                    raise RuntimeError("could not encode the image")
                shutil.move(tmp_name, str(target))
                saved += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{entry.filename}: {exc}")
        return saved, failed, errors

    def quick_rotate(self) -> None:
        """Rotate current image 90° CW and save in-place immediately."""
        if self._window is None:
            return
        entry = self._active().current()
        if entry is None:
            return
        img = img_io.imread(entry.path)
        if img is None:
            return

        import tempfile, shutil

        try:
            stat = os.stat(entry.path)
            rotated = apply_rotate(img, 90)

            tmp_fd, tmp_name = tempfile.mkstemp(
                suffix=entry.path.suffix, dir=entry.path.parent
            )
            os.close(tmp_fd)
            tmp_path = Path(tmp_name)

            ok = img_io.imwrite(tmp_path, rotated)
            if not ok:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(f"Could not encode the image (check the file extension: {entry.path.suffix})")

            shutil.move(str(tmp_path), str(entry.path))
            os.utime(entry.path, (stat.st_atime, stat.st_mtime))
            invalidate_dimensions(entry)
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            from i18n import tr
            QMessageBox.critical(
                self._window,
                tr("rotate_failed_title"),
                tr("rotate_failed_body").format(error=exc),
            )
            return

        self._refresh_selection()

    def set_cursor_in(self, panel: Literal["library", "album"], index: int) -> None:
        col = self.library if panel == "library" else self.album
        col.cursor = max(0, min(index, len(col.entries) - 1))
        self.focus = panel
        self._refresh_selection()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _active(self) -> ImageCollection:
        return self.library if self.focus == "library" else self.album

    def _remove_after_undo(self, path: Path) -> None:
        """Drop the entry for a copy that undo just trashed. The original never
        moved, so nothing is added back."""
        for col in (self.library, self.album):
            for i, e in enumerate(col.entries):
                if e.path == path:
                    col.entries.pop(i)
                    col.cursor = max(0, min(col.cursor, len(col.entries) - 1))
                    return

    def _sync_after_undo(self, was_at: Path, now_at: Path) -> None:
        """Update in-memory collections to reflect a file moved from was_at back to now_at."""

        def find_and_pop(col: ImageCollection, path: Path) -> ImageEntry | None:
            for i, e in enumerate(col.entries):
                if e.path == path:
                    col.entries.pop(i)
                    col.cursor = max(0, min(col.cursor, len(col.entries) - 1))
                    return e
            return None

        entry = find_and_pop(self.library, was_at) or find_and_pop(self.album, was_at)
        if entry is None:
            return
        new_entry = ImageEntry(
            path=now_at,
            filename=now_at.name,
            exif_date=entry.exif_date,
            file_size=entry.file_size,
        )
        if str(now_at.parent) == self.library.path:
            self.library.add(new_entry)
        else:
            self.album.add(new_entry)

    def _refresh_selection(self) -> None:
        """Update preview, info bar, and strip highlights — no strip rebuild."""
        if self._window is None:
            return
        active_col = self._active()
        entry = active_col.current()
        # Read EXIF lazily — only for the image currently on screen
        if entry is not None:
            ensure_exif(entry)
        self._window.preview.set_image(entry.path if entry else None)
        self._window.info_bar.update_info(entry, active_col)
        self._window.library_strip.set_selected(self.library.cursor)
        self._window.library_strip.set_focused(self.focus == "library")
        self._window.album_strip.set_selected(self.album.cursor)
        self._window.album_strip.set_focused(self.focus == "album")

    # ------------------------------------------------------------------
    # Album print check
    # ------------------------------------------------------------------

    def run_album_check(self, check_id: str) -> None:
        """Set the active album print check ("none"/"4r"/"instax") and refresh
        so failing photos get marked (or all marks clear when "none")."""
        self.album_check = check_id if check_id in self._CHECK_RATIOS else "none"
        self._refresh_collections()

    def _aspect_passes(self, w: int, h: int, ratio: float) -> bool:
        if h == 0:
            return False
        aspect = w / h
        for target in (ratio, 1.0 / ratio):
            if abs(aspect - target) <= self._CHECK_TOL * target:
                return True
        return False

    def _album_flagged_paths(self) -> set[Path]:
        """Album paths that fail the active print check. Empty when off, or when
        a file's size can't be read (we don't flag what we can't measure)."""
        if self.album_check not in self._CHECK_RATIOS:
            return set()
        ratio = self._CHECK_RATIOS[self.album_check]
        flagged: set[Path] = set()
        for entry in self.album.entries:
            dims = image_dimensions(entry)
            if dims is None:
                continue
            if not self._aspect_passes(dims[0], dims[1], ratio):
                flagged.add(entry.path)
        return flagged

    def _refresh_collections(self) -> None:
        """Rebuild both strips from scratch, then refresh selection."""
        if self._window is None:
            return
        self._window.library_strip.load(self.library)
        flagged = self._album_flagged_paths()
        self._window.album_strip.load(self.album, flagged)
        self._window.update_album_check_status(
            self.album_check, len(flagged), len(self.album.entries)
        )
        self._refresh_selection()
