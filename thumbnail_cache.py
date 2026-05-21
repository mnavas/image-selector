from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import cv2
from PyQt6.QtGui import QImage, QPixmap

_MAX_ENTRIES = 200


class ThumbnailCache:
    def __init__(self) -> None:
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()

    def get(self, path: Path, height: int) -> QPixmap:
        key = (str(path), height)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pixmap = self._load(path, height)
        self._cache[key] = pixmap
        if len(self._cache) > _MAX_ENTRIES:
            self._cache.popitem(last=False)
        return pixmap

    def invalidate(self, path: Path) -> None:
        keys = [k for k in self._cache if k[0] == str(path)]
        for k in keys:
            del self._cache[k]

    def _load(self, path: Path, height: int) -> QPixmap:
        img = cv2.imread(str(path))
        if img is None:
            return self._placeholder(height)
        h, w = img.shape[:2]
        new_w = max(1, int(w * height / h))
        resized = cv2.resize(img, (new_w, height), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        h2, w2 = rgb.shape[:2]
        qimg = QImage(rgb.data, w2, h2, w2 * 3, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg)

    @staticmethod
    def _placeholder(height: int) -> QPixmap:
        w = max(1, int(height * 1.5))
        px = QPixmap(w, height)
        px.fill()
        return px
