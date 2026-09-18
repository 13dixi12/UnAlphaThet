"""Vibes: tags scoped to a crate. A track only ever carries vibes of its own crate.

On disk, vibes live in the GROUPING tag as `crate_dir/vibe;crate_dir/vibe`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from unalphathet.core.db import transaction
from unalphathet.core.models import Vibe, row_to_vibe


class VibeExists(ValueError):
    pass


class VibeCrateMismatch(ValueError):
    """A vibe from another crate (or an unknown vibe) was offered to a track."""


def list_vibes(conn: sqlite3.Connection, crate_id: int) -> list[Vibe]:
    rows = conn.execute(
        "SELECT * FROM vibe WHERE crate_id = ? ORDER BY name", (crate_id,)
    ).fetchall()
    return [row_to_vibe(r) for r in rows]


def get_vibe(conn: sqlite3.Connection, crate_id: int, name: str) -> Vibe | None:
    row = conn.execute(
        "SELECT * FROM vibe WHERE crate_id = ? AND name = ?", (crate_id, name)
    ).fetchone()
    return row_to_vibe(row) if row else None


def add_vibe(conn: sqlite3.Connection, crate_id: int, name: str, hotkey: str | None = None) -> Vibe:
    if get_vibe(conn, crate_id, name):
        raise VibeExists(name)
    conn.execute(
        "INSERT INTO vibe(crate_id, name, hotkey) VALUES (?, ?, ?)", (crate_id, name, hotkey)
    )
    return get_vibe(conn, crate_id, name)  # type: ignore[return-value]


def track_vibes(conn: sqlite3.Connection, track_id: str) -> list[Vibe]:
    rows = conn.execute(
        "SELECT v.* FROM vibe v JOIN track_vibe tv ON tv.vibe_id = v.id "
        "WHERE tv.track_id = ? ORDER BY v.name",
        (track_id,),
    ).fetchall()
    return [row_to_vibe(r) for r in rows]


def set_track_vibes(conn: sqlite3.Connection, track_id: str, vibe_ids: Iterable[int]) -> list[Vibe]:
    """Replace the track's vibes with `vibe_ids`.

    Policy (Dixi, 2026-09-18): strict. Every offered vibe must belong to the track's own crate;
    otherwise VibeCrateMismatch is raised and nothing changes. Callers that expect foreign
    entries (tags edited outside the app) filter them out first — see apply_grouping().
    """
    wanted = set(vibe_ids)
    row = conn.execute("SELECT crate_id FROM track WHERE id = ?", (track_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown track {track_id}")
    crate_id = row["crate_id"]
    if wanted:
        placeholders = ", ".join("?" * len(wanted))
        ok = {
            r["id"]
            for r in conn.execute(
                f"SELECT id FROM vibe WHERE crate_id = ? AND id IN ({placeholders})",
                (crate_id, *wanted),
            ).fetchall()
        }
        if bad := wanted - ok:
            raise VibeCrateMismatch(
                f"vibes {sorted(bad)} do not belong to crate {crate_id} (track {track_id})"
            )
    with transaction(conn):
        conn.execute("DELETE FROM track_vibe WHERE track_id = ?", (track_id,))
        conn.executemany(
            "INSERT INTO track_vibe(track_id, vibe_id) VALUES (?, ?)",
            [(track_id, vid) for vid in wanted],
        )
    return track_vibes(conn, track_id)


def parse_grouping(s: str | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in (s or "").split(";"):
        part = part.strip()
        if not part or "/" not in part:
            continue
        crate, vibe = part.split("/", 1)
        if crate.strip() and vibe.strip():
            out.append((crate.strip(), vibe.strip()))
    return out


def format_grouping(conn: sqlite3.Connection, track_id: str) -> str | None:
    rows = conn.execute(
        "SELECT c.dir_name AS crate, v.name AS vibe FROM track_vibe tv "
        "JOIN vibe v ON v.id = tv.vibe_id JOIN crate c ON c.id = v.crate_id "
        "WHERE tv.track_id = ? ORDER BY v.name",
        (track_id,),
    ).fetchall()
    return ";".join(f"{r['crate']}/{r['vibe']}" for r in rows) or None


def apply_grouping(conn: sqlite3.Connection, track_id: str, grouping: str | None) -> int:
    """Set vibes from a GROUPING string. Foreign-crate entries are ignored; returns how many."""
    row = conn.execute(
        "SELECT t.crate_id, c.dir_name FROM track t JOIN crate c ON c.id = t.crate_id "
        "WHERE t.id = ?",
        (track_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"track {track_id} has no crate")
    crate_id, crate_dir = row["crate_id"], row["dir_name"]
    ids: list[int] = []
    ignored = 0
    for crate, name in parse_grouping(grouping):
        if crate != crate_dir:
            ignored += 1
            continue
        v = get_vibe(conn, crate_id, name) or add_vibe(conn, crate_id, name)
        ids.append(v.id)
    set_track_vibes(conn, track_id, ids)
    return ignored
