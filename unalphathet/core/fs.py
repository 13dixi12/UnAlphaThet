"""Collection filesystem conventions: what is a crate, what is audio, how files are named."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

AUDIO_EXTS: frozenset[str] = frozenset(
    {".flac", ".mp3", ".m4a", ".wav", ".aiff", ".aif", ".ogg", ".opus"}
)
RESERVED_DIRS: frozenset[str] = frozenset({"inbox", "playlists"})


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def crate_dirs(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in RESERVED_DIRS
    )


def iter_crate_files(root: Path) -> Iterator[tuple[str, Path]]:
    for crate in crate_dirs(root):
        for path in sorted(crate.rglob("*")):
            if path.is_file() and is_audio(path):
                yield crate.name, path


def rel_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# Letters NFKD can't decompose into ASCII. Everything else non-ASCII is dropped.
_TRANSLIT = str.maketrans(
    {
        "ß": "ss", "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O", "œ": "oe", "Œ": "OE",
        "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D",
        "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
    }
)


def asciify(text: str) -> str:
    text = text.translate(_TRANSLIT)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", asciify(name).lower()).strip("-")


MAX_FILENAME_BYTES = 200  # leaves room under FAT32's 255 after a PIONEER/... prefix
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MIN_TITLE = 24  # when truncating, the title always keeps at least this many chars


def _clean(part: str) -> str:
    part = re.sub(r"\s+", " ", asciify(part)).strip()  # collapse before control chars become '_'
    return _FORBIDDEN.sub("_", part)


def safe_filename(artist: str | None, title: str, ext: str) -> str:
    """`Artist - Title<ext>` that is safe on FAT32/exFAT and every CDJ.

    Policy (Dixi, 2026-09-18): forbidden characters become '_', everything is transliterated
    to ASCII (oldest decks show garbage for UTF-8), whitespace collapses, trailing dots/spaces
    go, and over-long names lose title characters first so the artist stays recognisable.
    """
    artist_c = _clean(artist or "")
    # FAT32 silently drops trailing dots/spaces from a name; only the end of the stem matters
    title_c = _clean(title).rstrip(". ") or "untitled"
    budget = MAX_FILENAME_BYTES - len(ext)
    sep = " - " if artist_c else ""
    overflow = len(artist_c) + len(sep) + len(title_c) - budget
    if overflow > 0:
        cut_title = min(overflow, max(len(title_c) - _MIN_TITLE, 0))
        title_c = title_c[: len(title_c) - cut_title].rstrip(". ") or "untitled"
        overflow -= cut_title
        if overflow > 0:
            artist_c = artist_c[: max(len(artist_c) - overflow, 0)].rstrip(". ")
            sep = " - " if artist_c else ""
    return f"{artist_c}{sep}{title_c}{ext}"
