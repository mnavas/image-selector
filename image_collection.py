from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}


@dataclass
class ImageEntry:
    path: Path
    filename: str
    exif_date: datetime | None
    file_size: int
    _exif_loaded: bool = False  # True once we've attempted a read


def read_exif_date(path: Path) -> datetime | None:
    """Read DateTimeOriginal from EXIF without decoding the full image."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            exif_data = img._getexif()  # type: ignore[attr-defined]
        if exif_data:
            for tag_id, value in exif_data.items():
                if TAGS.get(tag_id) == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def ensure_exif(entry: ImageEntry) -> None:
    """Populate entry.exif_date on first access; no-op on subsequent calls."""
    if not entry._exif_loaded:
        entry.exif_date = read_exif_date(entry.path)
        entry._exif_loaded = True


class ImageCollection:
    def __init__(self) -> None:
        self.path: str = ""
        self.entries: list[ImageEntry] = []
        self.cursor: int = 0

    def load(self, path: str) -> None:
        self.path = path
        folder = Path(path)
        files = sorted(
            [f for f in folder.iterdir() if f.suffix.lower() in SUPPORTED_EXTS],
            key=lambda f: f.name,
        )
        self.entries = [
            ImageEntry(
                path=f,
                filename=f.name,
                exif_date=None,
                file_size=f.stat().st_size,
            )
            for f in files
        ]
        self.cursor = 0

    def current(self) -> ImageEntry | None:
        if not self.entries:
            return None
        return self.entries[self.cursor]

    def move_cursor(self, delta: int) -> None:
        if not self.entries:
            return
        self.cursor = max(0, min(len(self.entries) - 1, self.cursor + delta))

    def add(self, entry: ImageEntry) -> None:
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.filename)
        # Keep cursor pointing at the same entry after sort
        if self.entries:
            self.cursor = max(0, min(self.cursor, len(self.entries) - 1))

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.entries):
            self.entries.pop(index)
            self.cursor = max(0, min(self.cursor, len(self.entries) - 1))

    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def __len__(self) -> int:
        return len(self.entries)
