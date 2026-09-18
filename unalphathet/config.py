"""User configuration. TOML in, frozen dataclass out. Missing file == defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path("~/music/dj")


@dataclass(frozen=True)
class Config:
    collection_root: Path
    write_back_tags: bool = True
    preview_autoplay: bool = True
    preview_start_at: float = 0.25
    mpv_args: tuple[str, ...] = ()

    @property
    def db_path(self) -> Path:
        return self.collection_root / ".unalphathet" / "library.db"


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unalphathet" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    data: dict = {}
    if path.exists():
        data = tomllib.loads(path.read_text())
    coll = data.get("collection", {})
    tags = data.get("tags", {})
    preview = data.get("preview", {})
    return Config(
        collection_root=Path(coll.get("root", str(DEFAULT_ROOT))).expanduser(),
        write_back_tags=bool(tags.get("write_back", True)),
        preview_autoplay=bool(preview.get("autoplay", True)),
        preview_start_at=float(preview.get("start_at", 0.25)),
        mpv_args=tuple(preview.get("mpv_args", [])),
    )


def write_default_config(path: Path, collection_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# UnAlphaThet configuration\n"
        "[collection]\n"
        f'root = "{collection_root}"\n\n'
        "[tags]\n"
        "write_back = true   # write vibes/bpm/key/id into the audio files\n\n"
        "[preview]\n"
        "autoplay = true\n"
        "start_at = 0.25     # fraction of the track to start previewing from\n"
        'mpv_args = []       # e.g. ["--ao=pipewire"]\n'
    )
