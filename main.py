from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app_controller import AppController
from config import Config
from widgets.main_window import MainWindow


def _pick_folders(config: Config, parent=None) -> bool:
    """Prompt the user to select library and album folders. Returns False if cancelled."""
    lib = QFileDialog.getExistingDirectory(
        parent,
        "Select Library Folder",
        config.library_path or str(Path.home()),
    )
    if not lib:
        return False
    alb = QFileDialog.getExistingDirectory(
        parent,
        "Select Album Folder",
        config.album_path or lib,
    )
    if not alb:
        return False
    config.library_path = lib
    config.album_path = alb
    config.save()
    return True


def _validate_paths(config: Config) -> bool:
    """Return True if both configured paths still exist on disk."""
    return (
        bool(config.library_path)
        and Path(config.library_path).is_dir()
        and bool(config.album_path)
        and Path(config.album_path).is_dir()
    )


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    config = Config.load()

    if not _validate_paths(config):
        if not _pick_folders(config):
            sys.exit(0)

    controller = AppController()
    window = MainWindow(controller)

    controller.library.load(config.library_path)
    controller.album.load(config.album_path)
    window.set_folder_labels(config.library_path, config.album_path)
    controller._refresh_collections()

    window.show()
    window.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
