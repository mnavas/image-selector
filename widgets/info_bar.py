from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from image_collection import ImageCollection, ImageEntry


class InfoBar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: #2a2a2a; color: #cccccc; padding: 4px; font-size: 12px;"
        )
        self.setText("No image")

    def update_info(
        self, entry: ImageEntry | None, collection: ImageCollection
    ) -> None:
        if entry is None or collection.is_empty():
            self.setText("No images")
            return
        date_str = (
            entry.exif_date.strftime("%Y-%m-%d %H:%M")
            if entry.exif_date
            else "No date"
        )
        size_mb = entry.file_size / (1024 * 1024)
        position = f"{collection.cursor + 1} / {len(collection.entries)}"
        self.setText(
            f"{entry.filename}  |  {date_str}  |  {size_mb:.1f} MB  |  {position}"
        )
