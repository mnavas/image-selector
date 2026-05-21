from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import cv2
import numpy as np

from edit_ops import EditState, apply_pipeline, apply_rotate
from file_ops import FileOps
from image_collection import ImageCollection, ImageEntry, ensure_exif

if TYPE_CHECKING:
    from widgets.main_window import MainWindow


class AppController:
    def __init__(self) -> None:
        self.library = ImageCollection()
        self.album = ImageCollection()
        self.focus: Literal["library", "album"] = "library"
        self.ops = FileOps()
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
        new_path = self.ops.move(entry.path, Path(self.album.path))
        new_entry = ImageEntry(
            path=new_path,
            filename=new_path.name,
            exif_date=entry.exif_date,
            file_size=entry.file_size,
        )
        self.library.remove(idx)
        self.album.add(new_entry)
        self._refresh_collections()

    def send_to_library(self) -> None:
        if self.focus != "album" or self.album.is_empty():
            return
        entry = self.album.current()
        assert entry is not None
        idx = self.album.cursor
        new_path = self.ops.move(entry.path, Path(self.library.path))
        new_entry = ImageEntry(
            path=new_path,
            filename=new_path.name,
            exif_date=entry.exif_date,
            file_size=entry.file_size,
        )
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
        was_at, now_at = result
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
        img = cv2.imread(str(entry.path))
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

            ok = cv2.imwrite(str(tmp_path), out)
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
            QMessageBox.critical(
                self._window,
                "Save failed",
                f"Could not save image:\n{exc}",
            )
            return

        self.close_edit_mode()
        self._refresh_collections()

    def quick_rotate(self) -> None:
        """Rotate current image 90° CW and save in-place immediately."""
        if self._window is None:
            return
        entry = self._active().current()
        if entry is None:
            return
        img = cv2.imread(str(entry.path))
        if img is None:
            return
        stat = os.stat(entry.path)
        rotated = apply_rotate(img, 90)
        cv2.imwrite(str(entry.path), rotated)
        os.utime(entry.path, (stat.st_atime, stat.st_mtime))
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

    def _refresh_collections(self) -> None:
        """Rebuild both strips from scratch, then refresh selection."""
        if self._window is None:
            return
        self._window.library_strip.load(self.library)
        self._window.album_strip.load(self.album)
        self._refresh_selection()
