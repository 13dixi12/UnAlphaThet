"""Plain dataclasses mirroring the schema. No behaviour, no I/O."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

TrackState = Literal["wanted", "inbox", "crated", "sorted", "missing"]


@dataclass(frozen=True)
class Crate:
    id: int
    name: str
    dir_name: str
    hotkey: str | None = None
    bpm_min: float | None = None
    bpm_max: float | None = None


@dataclass(frozen=True)
class Vibe:
    id: int
    crate_id: int
    name: str
    hotkey: str | None = None


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    parent_id: int | None = None


@dataclass(frozen=True)
class Track:
    id: str
    rel_path: str
    crate_id: int | None
    state: TrackState
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    duration_ms: int = 0
    bpm: float | None = None
    key: str | None = None
    energy: int | None = None
    rating: int | None = None
    codec: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    size_bytes: int = 0
    fingerprint: str | None = None
    audio_hash: str | None = None
    tags_written_at: str | None = None

    @property
    def display(self) -> str:
        return f"{self.artist or '?'} – {self.title or self.rel_path.rsplit('/', 1)[-1]}"

    @property
    def duration_str(self) -> str:
        s = self.duration_ms // 1000
        return f"{s // 60}:{s % 60:02d}"


def row_to_crate(row: sqlite3.Row) -> Crate:
    return Crate(**{k: row[k] for k in Crate.__dataclass_fields__})


def row_to_vibe(row: sqlite3.Row) -> Vibe:
    return Vibe(**{k: row[k] for k in Vibe.__dataclass_fields__})


def row_to_playlist(row: sqlite3.Row) -> Playlist:
    return Playlist(**{k: row[k] for k in Playlist.__dataclass_fields__})


def row_to_track(row: sqlite3.Row) -> Track:
    return Track(**{k: row[k] for k in Track.__dataclass_fields__})
