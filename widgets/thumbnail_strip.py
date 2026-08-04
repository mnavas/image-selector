from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
)

from image_collection import ImageCollection

_CELL_W = 150
_CELL_H = 44

# Custom item data role: True when the cell failed the album print check.
_FAIL_ROLE = Qt.ItemDataRole.UserRole + 1


def _truncate(filename: str) -> str:
    if len(filename) > 20:
        return filename[:9] + "…" + filename[-9:]
    return filename


class _CellDelegate(QStyledItemDelegate):
    """Paints each cell so a failed print-check cell gets a red border and red
    name, while selection/hover keep their usual blue/grey look."""

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        failed = bool(index.data(_FAIL_ROLE))

        # Background
        if selected:
            bg = QColor("#1e3050")
        elif hovered:
            bg = QColor("#333333")
        else:
            bg = QColor("#2a2a2a")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 2, 2)

        # Border — red mark wins over the selection border
        if failed:
            pen = QPen(QColor("#ff4d4d"))
            pen.setWidthF(2.0)
        elif selected:
            pen = QPen(QColor("#4a9eff"))
            pen.setWidthF(1.0)
        else:
            pen = None
        if pen is not None:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 2, 2)

        # Name
        if failed:
            text_color = QColor("#ff6b6b")
        elif selected:
            text_color = QColor("#ffffff")
        else:
            text_color = QColor("#cccccc")
        painter.setPen(text_color)
        painter.drawText(
            option.rect,
            Qt.AlignmentFlag.AlignCenter,
            index.data(Qt.ItemDataRole.DisplayRole),
        )
        painter.restore()


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
        self.setMouseTracking(True)   # so hover state reaches the delegate

        font = QFont()
        font.setPixelSize(11)
        self.setFont(font)
        self.setItemDelegate(_CellDelegate(self))

        # Never steal keyboard focus — all key handling lives in MainWindow
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._updating = False
        # itemClicked fires on every mouse click, even if the row is already selected.
        # currentRowChanged would miss clicks on the already-current row (e.g. first item
        # after load), so we use itemClicked exclusively.
        self.itemClicked.connect(self._on_item_clicked)
        self.set_focused(False)

    def load(self, collection: ImageCollection, flagged: set | None = None) -> None:
        """Rebuild the strip. `flagged` is a set of paths that failed the album
        print check and should be marked red; None/empty marks nothing."""
        flagged = flagged or set()
        self._updating = True
        self.clear()
        for entry in collection.entries:
            item = QListWidgetItem(_truncate(entry.filename))
            item.setToolTip(entry.filename)
            item.setSizeHint(QSize(_CELL_W, _CELL_H))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(_FAIL_ROLE, entry.path in flagged)
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
        # Only the frame is styled here; cells are drawn by _CellDelegate.
        self.setStyleSheet(
            f"QListWidget {{ background-color: #1a1a1a; border: 2px solid {border}; "
            f"outline: none; }}"
        )

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if not self._updating:
            index = self.row(item)
            if index >= 0:
                self.cell_clicked.emit(index)
