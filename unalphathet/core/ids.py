"""Track identity: the UUID we mint, plus the content fingerprints we keep next to it."""

from __future__ import annotations

import uuid
from pathlib import Path

import acoustid
import mutagen


class FingerprintError(RuntimeError):
    pass


def new_track_id() -> str:
    return str(uuid.uuid4())


def is_track_id(value: str | None) -> bool:
    """True for a well-formed UUID string (what UAT_ID must hold)."""
    if not value:
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def fingerprint(path: Path, max_seconds: int = 120) -> tuple[float, str]:
    """Chromaprint via fpcalc. Returns (duration_seconds, compressed_fingerprint)."""
    try:
        duration, fp = acoustid.fingerprint_file(
            str(path), maxlength=max_seconds, force_fpcalc=True
        )
    except (acoustid.FingerprintGenerationError, acoustid.NoBackendError, OSError) as exc:
        raise FingerprintError(f"{path}: {exc}") from exc
    if isinstance(fp, bytes):
        fp = fp.decode("ascii")
    if not fp or len(fp) < 8:
        raise FingerprintError(f"{path}: empty fingerprint")
    return float(duration), fp


def audio_md5(path: Path) -> str | None:
    f = mutagen.File(path)
    md5 = getattr(getattr(f, "info", None), "md5_signature", None)
    return f"{md5:032x}" if md5 else None


def similarity(fp_a: str, fp_b: str) -> float:
    """0.0–1.0 bit-level agreement of two compressed chromaprints, frame-aligned from the start.

    Same recording through different encoders scores ~0.99; unrelated audio ~0.5–0.7.
    Good enough for "is this the same track?"; offset search (for trimmed intros) is Phase 2.
    """
    try:
        import chromaprint  # ctypes binding shipped with pyacoustid; needs libchromaprint
    except (ImportError, OSError) as exc:
        raise FingerprintError(f"libchromaprint unavailable: {exc}") from exc
    a, _ = chromaprint.decode_fingerprint(fp_a.encode("ascii"))
    b, _ = chromaprint.decode_fingerprint(fp_b.encode("ascii"))
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    errors = sum(((x ^ y) & 0xFFFFFFFF).bit_count() for x, y in zip(a[:n], b[:n], strict=True))
    return 1.0 - errors / (32 * n)
