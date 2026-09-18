"""Read-only queries the frontends use to list tracks."""

from __future__ import annotations

import sqlite3

from unalphathet.core.models import Track, row_to_track

ORDER = "ORDER BY artist COLLATE NOCASE, title COLLATE NOCASE, rel_path"


def get_track(conn: sqlite3.Connection, track_id: str) -> Track | None:
    row = conn.execute("SELECT * FROM track WHERE id = ?", (track_id,)).fetchone()
    return row_to_track(row) if row else None


def tracks_in_crate(
    conn: sqlite3.Connection, crate_id: int, include_missing: bool = False
) -> list[Track]:
    cond = "" if include_missing else " AND state != 'missing'"
    rows = conn.execute(
        f"SELECT * FROM track WHERE crate_id = ?{cond} {ORDER}", (crate_id,)
    ).fetchall()
    return [row_to_track(r) for r in rows]


def tracks_with_vibe(conn: sqlite3.Connection, vibe_id: int) -> list[Track]:
    rows = conn.execute(
        "SELECT t.* FROM track t JOIN track_vibe tv ON tv.track_id = t.id "
        f"WHERE tv.vibe_id = ? AND t.state != 'missing' {ORDER}",
        (vibe_id,),
    ).fetchall()
    return [row_to_track(r) for r in rows]


def search(conn: sqlite3.Connection, text: str, limit: int = 200) -> list[Track]:
    like = f"%{text}%"
    rows = conn.execute(
        "SELECT * FROM track WHERE state != 'missing' AND "
        f"(title LIKE ? OR artist LIKE ? OR album LIKE ?) {ORDER} LIMIT ?",
        (like, like, like, limit),
    ).fetchall()
    return [row_to_track(r) for r in rows]
