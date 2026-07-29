"""Unicode-safe image read/write.

cv2.imread / cv2.imwrite build on fopen() with the given path encoded via the
current codepage on Windows, so any non-ASCII filename (accented letters, ñ,
CJK, ...) fails silently — imread returns None, imwrite returns False, no
exception. Route through numpy + imdecode/imencode instead, which take a
byte buffer and never touch the OS path-encoding layer.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path) -> np.ndarray | None:
    """Unicode-safe replacement for cv2.imread (color, BGR)."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite(path, img: np.ndarray) -> bool:
    """Unicode-safe replacement for cv2.imwrite."""
    path = Path(path)
    ext = path.suffix
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    buf.tofile(str(path))
    return True
