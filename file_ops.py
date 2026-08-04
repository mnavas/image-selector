from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _UndoEntry:
    current_path: Path   # where the file is now (post-move/copy)
    original_dir: Path   # the directory it came from
    is_copy: bool = False   # True if the file was copied, not moved


class FileOps:
    def __init__(self) -> None:
        self._undo: _UndoEntry | None = None

    def move(self, src: Path, dst_dir: Path) -> Path:
        """Move src into dst_dir, preserving timestamps. Returns the new path."""
        stat = os.stat(src)
        dst = self._unique_path(dst_dir / src.name)
        shutil.move(str(src), str(dst))
        os.utime(dst, (stat.st_atime, stat.st_mtime))
        self._undo = _UndoEntry(current_path=dst, original_dir=src.parent)
        return dst

    def copy(self, src: Path, dst_dir: Path) -> Path:
        """Copy src into dst_dir, preserving timestamps. Returns the new path.
        The original stays put; undo removes the copy."""
        stat = os.stat(src)
        dst = self._unique_path(dst_dir / src.name)
        shutil.copy2(str(src), str(dst))
        os.utime(dst, (stat.st_atime, stat.st_mtime))
        self._undo = _UndoEntry(current_path=dst, original_dir=src.parent, is_copy=True)
        return dst

    def trash(self, path: Path) -> None:
        """Send path to the system trash. Clears the undo stack."""
        from send2trash import send2trash
        send2trash(str(path))
        self._undo = None

    def undo(self) -> tuple[str, Path, Path | None] | None:
        """Reverse the last move or copy.

        Returns None if there is nothing to undo, otherwise a tuple:
          ("move", was_at, now_at) — file moved back to now_at
          ("copy", was_at, None)   — the copy at was_at was trashed
        """
        if self._undo is None:
            return None
        entry = self._undo
        self._undo = None
        if entry.is_copy:
            from send2trash import send2trash
            send2trash(str(entry.current_path))
            return ("copy", entry.current_path, None)
        stat = os.stat(entry.current_path)
        dst = self._unique_path(entry.original_dir / entry.current_path.name)
        shutil.move(str(entry.current_path), str(dst))
        os.utime(dst, (stat.st_atime, stat.st_mtime))
        return ("move", entry.current_path, dst)

    def can_undo(self) -> bool:
        return self._undo is not None

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """If path already exists, append _1, _2, ... before the suffix."""
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1
