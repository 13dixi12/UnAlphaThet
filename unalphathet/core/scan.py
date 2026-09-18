"""Reconcile the collection directory, the files' tags and the SQLite index.

Truth model (spec §2): the file's directory is its crate; per-track facts live in the tags AND the
DB; on disagreement resolve_conflict() decides. Scan never touches inbox/."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from unalphathet.config import Config
from unalphathet.core import fs, ids
from unalphathet.core.db import transaction
from unalphathet.core.tags import TrackTags, read_tags, write_tags
from unalphathet.library import crates, vibes

COMPARED = ("title", "artist", "album", "albumartist", "genre", "bpm", "key", "energy", "grouping")


class Source(Enum):
    TAGS = "tags"
    DB = "db"


@dataclass
class ScanReport:
    added: int = 0
    updated: int = 0
    moved: int = 0
    missing: int = 0
    tag_won: int = 0
    db_won: int = 0
    errors: list[str] = field(default_factory=list)


def _mtime_iso(path: Path) -> str:
    ts = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def resolve_conflict(
    tags_written_at: str | None, file_mtime_iso: str, db_values: dict, tag_values: dict
) -> Source:
    """Who wins when the file's tags and the DB row disagree.

    Policy (Dixi, 2026-09-18): the file wins only if it was modified strictly *after* our last
    tag write. Never written by us (write_back=false, imported row), equal timestamps, or an
    older file -> the DB wins and its values are written back (with write_back=false nothing is
    written, so external edits are ignored on every scan and counted as db_won each time). A file
    mtime in the future is simply "newer" -> file wins. Timestamps are same-shape ISO-8601 UTC,
    so they compare lexically.
    """
    if tags_written_at is None:
        return Source.DB
    return Source.TAGS if file_mtime_iso > tags_written_at else Source.DB


def _comparable(t: TrackTags, codec: str) -> dict:
    """The COMPARED fields as the *file* can represent them, so lossy formats converge.

    MP4 stores BPM as an integer (`tmpo`); everything else gets two decimals (see tags._fmt).
    Without this a DB bpm of 142.5 on an .m4a would be rewritten on every scan, forever.
    """
    values = {k: getattr(t, k) for k in COMPARED}
    if values["bpm"] is not None:
        values["bpm"] = (
            round(values["bpm"]) if codec in ("aac", "alac") else round(values["bpm"], 2)
        )
    return values


def _tags_to_row(t: TrackTags) -> dict:
    return {
        "title": t.title,
        "artist": t.artist,
        "album": t.album,
        "albumartist": t.albumartist,
        "genre": t.genre,
        "bpm": t.bpm,
        "key": t.key,
        "energy": t.energy,
        "duration_ms": t.duration_ms,
        "codec": t.codec,
        "sample_rate": t.sample_rate,
        "bit_depth": t.bit_depth,
        "bitrate": t.bitrate,
    }


def _row_tags(conn: sqlite3.Connection, row: sqlite3.Row) -> TrackTags:
    return TrackTags(
        uat_id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        albumartist=row["albumartist"],
        genre=row["genre"],
        grouping=vibes.format_grouping(conn, row["id"]),
        bpm=row["bpm"],
        key=row["key"],
        energy=row["energy"],
    )


def _update_row(conn: sqlite3.Connection, track_id: str, values: dict) -> None:
    cols = ", ".join(f"{k} = ?" for k in values)
    conn.execute(f"UPDATE track SET {cols} WHERE id = ?", (*values.values(), track_id))


def _fetch(conn: sqlite3.Connection, track_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM track WHERE id = ?", (track_id,)).fetchone()


def _state_for(conn: sqlite3.Connection, track_id: str, current: str) -> str:
    if current in ("wanted", "inbox"):
        return current
    return "sorted" if vibes.track_vibes(conn, track_id) else "crated"


def _write_back(
    conn, path: Path, track_id: str, t: TrackTags, config: Config, only: list[str]
) -> None:
    """Write our id plus exactly the fields in `only` into the file; remember when we did.

    Never more than that: a file can hold things our model can't represent (repeated GENRE
    entries, a 4-decimal BPM), and rewriting a field we didn't change would flatten them.
    """
    if not config.write_back_tags:
        return
    t.uat_id = track_id
    write_tags(path, t, only=("uat_id", *only))
    _update_row(conn, track_id, {"tags_written_at": _mtime_iso(path)})


def _stamp_id(conn, path: Path, track_id: str, config: Config) -> None:
    """Put only UAT_ID into a file that lost it; every other tag is left as found."""
    if not config.write_back_tags:
        return
    write_tags(path, TrackTags(uat_id=track_id), only=("uat_id",))
    _update_row(conn, track_id, {"tags_written_at": _mtime_iso(path)})


def _reconcile_existing(
    conn,
    root: Path,
    path: Path,
    row: sqlite3.Row,
    file_tags: TrackTags,
    crate_id: int,
    config: Config,
    report: ScanReport,
) -> None:
    rel = fs.rel_posix(root, path)
    if row["rel_path"] != rel or row["crate_id"] != crate_id:
        recrated = row["crate_id"] != crate_id
        _update_row(conn, row["id"], {"rel_path": rel, "crate_id": crate_id})
        if recrated:  # vibes are crate-scoped: a track that changes crate starts with none
            conn.execute("DELETE FROM track_vibe WHERE track_id = ?", (row["id"],))
            _update_row(conn, row["id"], {"state": _state_for(conn, row["id"], "crated")})
        conn.execute(
            "INSERT INTO sort_log(track_id, action, from_path, to_path) VALUES (?, ?, ?, ?)",
            (row["id"], "recrated" if recrated else "moved", row["rel_path"], rel),
        )
        report.moved += 1
    if row["state"] == "missing":
        _update_row(conn, row["id"], {"state": _state_for(conn, row["id"], "crated")})
    row = _fetch(conn, row["id"])

    db_tags = _row_tags(conn, row)
    db_values = _comparable(db_tags, file_tags.codec)
    tag_values = _comparable(file_tags, file_tags.codec)
    if db_values == tag_values:
        return
    winner = resolve_conflict(row["tags_written_at"], _mtime_iso(path), db_values, tag_values)
    if winner is Source.TAGS:
        _update_row(conn, row["id"], _tags_to_row(file_tags))
        vibes.apply_grouping(conn, row["id"], file_tags.grouping)
        _update_row(
            conn,
            row["id"],
            {
                "state": _state_for(conn, row["id"], row["state"]),
                "tags_written_at": _mtime_iso(path),
            },
        )
        report.tag_won += 1
    else:
        changed = [k for k in COMPARED if db_values[k] != tag_values[k]]
        _write_back(conn, path, row["id"], db_tags, config, only=changed)
        report.db_won += 1
    report.updated += 1


def _find_by_fingerprint(conn, root: Path, fp: str) -> sqlite3.Row | None:
    """A DB row with this fingerprint whose file is no longer where the DB says."""
    for row in conn.execute("SELECT * FROM track WHERE fingerprint = ?", (fp,)).fetchall():
        if not (root / row["rel_path"]).exists():
            return row
    return None


def _insert_new(
    conn,
    root: Path,
    path: Path,
    file_tags: TrackTags,
    crate_id: int,
    fp: str | None,
    config: Config,
    report: ScanReport,
) -> str:
    # A file that already carries a UAT_ID unknown to this DB (lost library.db, foreign stick)
    # keeps it: re-minting would orphan every manifest and playlist that points at it.
    track_id = file_tags.uat_id if ids.is_track_id(file_tags.uat_id) else ids.new_track_id()
    values = _tags_to_row(file_tags)
    values.update(
        {
            "id": track_id,
            "rel_path": fs.rel_posix(root, path),
            "crate_id": crate_id,
            "fingerprint": fp,
            "audio_hash": file_tags.audio_md5,
            "size_bytes": path.stat().st_size,
            "state": "crated",
        }
    )
    cols = ", ".join(values)
    marks = ", ".join("?" * len(values))
    conn.execute(f"INSERT INTO track({cols}) VALUES ({marks})", tuple(values.values()))
    vibes.apply_grouping(conn, track_id, file_tags.grouping)
    _update_row(conn, track_id, {"state": _state_for(conn, track_id, "crated")})
    if file_tags.uat_id == track_id:  # already stamped: in sync as of now, nothing to write
        _update_row(conn, track_id, {"tags_written_at": _mtime_iso(path)})
    else:  # import == the file is the truth; add our id and nothing else
        _stamp_id(conn, path, track_id, config)
    conn.execute(
        "INSERT INTO sort_log(track_id, action, to_path) VALUES (?, 'added', ?)",
        (track_id, values["rel_path"]),
    )
    report.added += 1
    return track_id


def _scan_one(
    conn, root: Path, path: Path, crate_dir: str, config: Config, report: ScanReport
) -> str:
    """Reconcile one file; returns the track id it now belongs to."""
    crate = crates.ensure_crate(conn, root, crate_dir)
    file_tags = read_tags(path)
    row = _fetch(conn, file_tags.uat_id) if file_tags.uat_id else None
    if row is None:
        # Same path, no id: the file we already know that lost its UAT_ID (write_back=false, or a
        # tagger that strips unknown frames). No fingerprinting needed.
        row = conn.execute(
            "SELECT * FROM track WHERE rel_path = ?", (fs.rel_posix(root, path),)
        ).fetchone()
    fp: str | None = None
    if row is None:
        try:
            _, fp = ids.fingerprint(path)
        except ids.FingerprintError as exc:
            report.errors.append(str(exc))
        if fp:
            row = _find_by_fingerprint(conn, root, fp)
    if row is not None and file_tags.uat_id != row["id"]:  # known track, id missing: restore it
        _stamp_id(conn, path, row["id"], config)
        file_tags.uat_id = row["id"]
    if row is not None:
        _reconcile_existing(conn, root, path, row, file_tags, crate.id, config, report)
        return row["id"]
    return _insert_new(conn, root, path, file_tags, crate.id, fp, config, report)


def scan(
    conn: sqlite3.Connection,
    root: Path,
    config: Config,
    progress: Callable[[str], None] | None = None,
) -> ScanReport:
    report = ScanReport()
    seen: set[str] = set()
    for crate_dir, path in fs.iter_crate_files(root):
        if progress:
            progress(fs.rel_posix(root, path))
        try:
            with transaction(conn):  # one file == one transaction: a crash mid-scan is resumable
                seen.add(_scan_one(conn, root, path, crate_dir, config, report))
        except Exception as exc:  # one bad file must not abort the scan
            report.errors.append(f"{path}: {exc}")

    marks = ", ".join("?" * len(seen)) or "''"
    cur = conn.execute(
        "UPDATE track SET state = 'missing' "
        f"WHERE state NOT IN ('wanted','inbox','missing') AND id NOT IN ({marks})",
        tuple(seen),
    )
    report.missing = cur.rowcount
    return report
