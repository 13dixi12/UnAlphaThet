"""Shared fixtures. Audio fixtures are ffmpeg-generated seeded pink noise:
same seed => identical audio => identical chromaprint; sine tones give empty fingerprints."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from unalphathet.core import db

ENCODERS = {
    ".flac": ["-c:a", "flac", "-sample_fmt", "s16"],
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    ".m4a": ["-c:a", "aac", "-b:a", "128k"],
    ".wav": ["-c:a", "pcm_s16le"],
}


def make_audio(path: Path, *, seconds: float = 3, seed: int = 1, **meta: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=d={seconds}:c=pink:r=44100:a=0.5:s={seed}",
    ]
    for k, v in meta.items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd += ENCODERS[path.suffix.lower()] + [str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        pytest.skip("ffmpeg not installed")
    return exe


@pytest.fixture
def collection(tmp_path: Path, ffmpeg: str) -> Path:
    """A small collection: psy/ with two tracks (one in a subdir), techno/ with one, plus inbox/."""
    root = tmp_path / "coll"
    for sub in ("inbox", "playlists", ".unalphathet"):
        (root / sub).mkdir(parents=True)
    make_audio(
        root / "psy" / "Astrix - Deep Jungle Walk.flac",
        seed=11,
        title="Deep Jungle Walk",
        artist="Astrix",
        album="Deep Jungle Walk",
    )
    make_audio(
        root / "psy" / "albums" / "Astrix - Heart.mp3",
        seed=12,
        title="Heart",
        artist="Astrix",
        album="He.art",
    )
    make_audio(
        root / "techno" / "Surgeon - Floorshow.m4a", seed=13, title="Floorshow", artist="Surgeon"
    )
    make_audio(root / "inbox" / "unsorted.flac", seed=14, title="Unsorted", artist="Nobody")
    return root


@pytest.fixture
def conn(collection: Path):
    c = db.open_library(collection)
    yield c
    c.close()
