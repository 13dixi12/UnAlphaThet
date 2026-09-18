"""Read and write the tag fields UnAlphaThet cares about, across FLAC/Ogg (Vorbis comments),
MP3/WAV/AIFF (ID3) and M4A (MP4 atoms). Everything else in the file is left untouched.

Custom fields: UAT_ID (track UUID), UAT_ENERGY (1-5). Vibes ride in GROUPING as
`crate/vibe;crate/vibe` (see library.vibes.format_grouping)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen._vorbis import VCommentDict
from mutagen.id3 import ID3, TALB, TBPM, TCON, TIT1, TIT2, TKEY, TPE1, TPE2, TXXX
from mutagen.mp4 import MP4, MP4FreeForm


@dataclass
class TrackTags:
    uat_id: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    grouping: str | None = None
    bpm: float | None = None
    key: str | None = None
    energy: int | None = None
    # stream info (read-only)
    duration_ms: int = 0
    codec: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    audio_md5: str | None = None


WRITABLE = (
    "uat_id", "title", "artist", "album", "albumartist", "genre", "grouping", "bpm", "key", "energy",
)

# field -> tag key per family
VORBIS_KEYS = {
    "uat_id": "UAT_ID", "title": "TITLE", "artist": "ARTIST", "album": "ALBUM",
    "albumartist": "ALBUMARTIST", "genre": "GENRE", "grouping": "GROUPING",
    "bpm": "BPM", "key": "INITIALKEY", "energy": "UAT_ENERGY",
}
ID3_FRAMES = {  # field -> frame class (TXXX handled separately)
    "title": TIT2, "artist": TPE1, "album": TALB, "albumartist": TPE2,
    "genre": TCON, "grouping": TIT1, "bpm": TBPM, "key": TKEY,
}
ID3_TXXX = {"uat_id": "UAT_ID", "energy": "UAT_ENERGY"}
MP4_KEYS = {
    "title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "albumartist": "aART",
    "genre": "\xa9gen", "grouping": "\xa9grp",
}
MP4_FREEFORM = {
    "uat_id": "----:com.apple.iTunes:UAT_ID",
    "energy": "----:com.apple.iTunes:UAT_ENERGY",
    "key": "----:com.apple.iTunes:initialkey",
}


def _first(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        if not value:
            return None
        value = value[0]
    if isinstance(value, MP4FreeForm):
        return bytes(value).decode("utf-8", "replace")
    if hasattr(value, "text"):  # ID3 frame
        value = value.text[0] if value.text else None
    return None if value is None else str(value)


def _to_float(s) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_int(s) -> int | None:
    f = _to_float(s)
    return int(f) if f is not None else None


def _codec_name(f: mutagen.FileType) -> str:
    name = type(f).__name__.lower()
    if name == "mp4":
        return "alac" if getattr(f.info, "codec", "") == "alac" else "aac"
    if name in ("wave", "aiff"):
        return "pcm"
    if name == "oggvorbis":
        return "vorbis"
    if name == "oggopus":
        return "opus"
    return name  # flac, mp3


def _stream_info(f: mutagen.FileType, t: TrackTags) -> None:
    info = f.info
    t.duration_ms = round(getattr(info, "length", 0) * 1000)
    t.codec = _codec_name(f)
    t.sample_rate = int(getattr(info, "sample_rate", 0) or 0)
    t.bit_depth = int(getattr(info, "bits_per_sample", 0) or 0)
    t.bitrate = int(getattr(info, "bitrate", 0) or 0)
    md5 = getattr(info, "md5_signature", None)
    if md5:
        t.audio_md5 = f"{md5:032x}"


def read_tags(path: Path) -> TrackTags:
    f = mutagen.File(path)
    if f is None:
        raise ValueError(f"unsupported audio file: {path}")
    t = TrackTags()
    _stream_info(f, t)
    tags = f.tags
    if tags is None:
        return t
    if isinstance(tags, VCommentDict):
        for field, k in VORBIS_KEYS.items():
            setattr(t, field, _first(tags.get(k)))
    elif isinstance(tags, ID3):
        for field, frame in ID3_FRAMES.items():
            setattr(t, field, _first(tags.get(frame.__name__)))
        for field, desc in ID3_TXXX.items():
            setattr(t, field, _first(tags.get(f"TXXX:{desc}")))
    elif isinstance(f, MP4):
        for field, k in MP4_KEYS.items():
            setattr(t, field, _first(tags.get(k)))
        for field, k in MP4_FREEFORM.items():
            setattr(t, field, _first(tags.get(k)))
        t.bpm = _first(tags.get("tmpo"))  # type: ignore[assignment]
    t.bpm = _to_float(t.bpm)
    t.energy = _to_int(t.energy)
    return t
