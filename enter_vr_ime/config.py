from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    osc_host: str = "127.0.0.1"
    osc_port: int = 9000
    notify_sound: bool = False
    overlay_width_m: float = 1.15
    overlay_y_m: float = -0.34
    overlay_z_m: float = -1.0
    capture_fps: int = 20
    window_width_px: int = 1100
    window_height_px: int = 390
    max_characters: int = 144


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "EnterVRIME"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> AppConfig:
    path = app_data_dir() / "config.json"
    config = AppConfig()
    if path.exists():
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            allowed = set(asdict(config))
            config = AppConfig(**{key: value for key, value in values.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            pass

    config.osc_port = max(1, min(65535, int(config.osc_port)))
    config.capture_fps = max(5, min(30, int(config.capture_fps)))
    config.max_characters = max(1, min(144, int(config.max_characters)))
    save_config(config)
    return config


def save_config(config: AppConfig) -> None:
    path = app_data_dir() / "config.json"
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
