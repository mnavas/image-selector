from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from image_collection import ImageCollection

_CELL_W = 150
_CELL_H = 44


def _truncate(filename: str) -> str:
    if len(filename) > 20:
        return filename[:9] + "…" + filename[-9:]
    return filename


class ThumbnailStrip(QListWidget):
    cell_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setFixedHeight(_CELL_H + 24)   # cell + scrollbar room
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Fixed)
        self.setSpacing(2)
        self.setUniformItemSizes(True)

        # Never steal keyboard focus — all key handling lives in MainWindow
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._updating = False
        # itemClicked fires on every mouse click, even if the row is already selected.
        # currentRowChanged would miss clicks on the already-current row (e.g. first item
        # after load), so we use itemClicked exclusively.
        self.itemClicked.connect(self._on_item_clicked)
        self.set_focused(False)

    def load(self, collection: ImageCollection) -> None:
        self._updating = True
        self.clear()
        for entry in collection.entries:
            item = QListWidgetItem(_truncate(entry.filename))
            item.setToolTip(entry.filename)
            item.setSizeHint(QSize(_CELL_W, _CELL_H))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.addItem(item)
        self._updating = False

    def set_selected(self, index: int) -> None:
        self._updating = True
        self.setCurrentRow(index)
        item = self.item(index)
        if item:
            self.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
        self._updating = False

    def set_focused(self, focused: bool) -> None:
        border = "#4a9eff" if focused else "#444444"
        self.setStyleSheet(
            f"QListWidget {{ background-color: #1a1a1a; border: 2px solid {border}; "
            f"outline: none; }}"
            "QListWidget::item { color: #cccccc; background-color: #2a2a2a; "
            "border-radius: 2px; margin: 1px; font-size: 10px; }"
            "QListWidget::item:selected { background-color: #1e3050; "
            "border: 1px solid #4a9eff; color: #ffffff; }"
            "QListWidget::item:hover:!selected { background-color: #333333; }"
        )

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if not self._updating:
            index = self.row(item)
            if index >= 0:
                self.cell_clicked.emit(index)
