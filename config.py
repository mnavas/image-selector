from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "image_selector" / "config.json"


@dataclass
class Config:
    library_path: str = ""
    album_path: str = ""
    thumb_height: int = 120
    hidden_filters: list = field(default_factory=list)

    @staticmethod
    def load() -> "Config":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                return Config(
                    library_path=data.get("library_path", ""),
                    album_path=data.get("album_path", ""),
                    thumb_height=data.get("thumb_height", 120),
                    hidden_filters=data.get("hidden_filters", []),
                )
            except Exception:
                pass
        return Config()

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "library_path": self.library_path,
                    "album_path": self.album_path,
                    "thumb_height": self.thumb_height,
                    "hidden_filters": self.hidden_filters,
                },
                indent=2,
            )
        )
