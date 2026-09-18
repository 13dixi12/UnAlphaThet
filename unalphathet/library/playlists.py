"""Playlists: ordered, cross-crate. SQLite is canonical; .m3u8 files are exported for others."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from unalphathet.core.db import transaction
from unalphathet.core.fs import slugify
from unalphathet.core.models import Playlist, Track, row_to_playlist, row_to_track


class PlaylistExists(ValueError):
    pass


def list_playlists(conn: sqlite3.Connection) -> list[Playlist]:
    rows = conn.execute("SELECT * FROM playlist ORDER BY parent_id, name").fetchall()
    return [row_to_playlist(r) for r in rows]


def get_playlist(
    conn: sqlite3.Connection, name: str, parent_id: int | None = None
) -> Playlist | None:
    row = conn.execute(
        "SELECT * FROM playlist WHERE name = ? AND parent_id IS ?", (name, parent_id)
    ).fetchone()
    return row_to_playlist(row) if row else None


def add_playlist(conn: sqlite3.Connection, name: str, parent_id: int | None = None) -> Playlist:
    if get_playlist(conn, name, parent_id):
        raise PlaylistExists(name)
    conn.execute("INSERT INTO playlist(name, parent_id) VALUES (?, ?)", (name, parent_id))
    return get_playlist(conn, name, parent_id)  # type: ignore[return-value]


def add_track(conn: sqlite3.Connection, playlist_id: int, track_id: str) -> None:
    """Append; re-adding an existing track is a no-op."""
    with transaction(conn):
        nxt = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM playlist_track WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO playlist_track(playlist_id, track_id, position) "
            "VALUES (?, ?, ?)",
            (playlist_id, track_id, nxt),
        )


def remove_track(conn: sqlite3.Connection, playlist_id: int, track_id: str) -> None:
    with transaction(conn):
        conn.execute(
            "DELETE FROM playlist_track WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        rows = conn.execute(
            "SELECT track_id FROM playlist_track WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        conn.executemany(
            "UPDATE playlist_track SET position = ? WHERE playlist_id = ? AND track_id = ?",
            [(pos, playlist_id, r["track_id"]) for pos, r in enumerate(rows)],
        )


def playlist_tracks(conn: sqlite3.Connection, playlist_id: int) -> list[Track]:
    rows = conn.execute(
        "SELECT t.* FROM track t JOIN playlist_track pt ON pt.track_id = t.id "
        "WHERE pt.playlist_id = ? ORDER BY pt.position",
        (playlist_id,),
    ).fetchall()
    return [row_to_track(r) for r in rows]


def export_m3u8(conn: sqlite3.Connection, root: Path, playlist_id: int) -> Path:
    """Write <root>/playlists/<slug>.m3u8 with paths relative to that directory."""
    row = conn.execute("SELECT * FROM playlist WHERE id = ?", (playlist_id,)).fetchone()
    if row is None:
        raise ValueError(f"no playlist {playlist_id}")
    out_dir = root / "playlists"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slugify(row['name'])}.m3u8"
    lines = ["#EXTM3U"]
    for t in playlist_tracks(conn, playlist_id):
        lines.append(f"#EXTINF:{t.duration_ms // 1000},{t.artist or '?'} - {t.title or '?'}")
        lines.append(f"../{t.rel_path}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
