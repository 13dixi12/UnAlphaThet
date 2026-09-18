"""Crates: one directory under the collection root == one crate."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from unalphathet.core.fs import slugify
from unalphathet.core.models import Crate, row_to_crate


class CrateExists(ValueError):
    pass


def list_crates(conn: sqlite3.Connection) -> list[Crate]:
    rows = conn.execute("SELECT * FROM crate ORDER BY name").fetchall()
    return [row_to_crate(r) for r in rows]


def get_crate(conn: sqlite3.Connection, dir_name: str) -> Crate | None:
    row = conn.execute("SELECT * FROM crate WHERE dir_name = ?", (dir_name,)).fetchone()
    return row_to_crate(row) if row else None


def ensure_crate(conn: sqlite3.Connection, root: Path, dir_name: str) -> Crate:
    existing = get_crate(conn, dir_name)
    if existing:
        return existing
    (root / dir_name).mkdir(parents=True, exist_ok=True)
    conn.execute("INSERT INTO crate(name, dir_name) VALUES (?, ?)", (dir_name, dir_name))
    return get_crate(conn, dir_name)  # type: ignore[return-value]


def add_crate(
    conn: sqlite3.Connection,
    root: Path,
    name: str,
    hotkey: str | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
) -> Crate:
    dir_name = slugify(name)
    if not dir_name:
        raise ValueError(f"crate name {name!r} produces an empty directory name")
    if get_crate(conn, dir_name):
        raise CrateExists(dir_name)
    (root / dir_name).mkdir(parents=True, exist_ok=True)
    conn.execute(
        "INSERT INTO crate(name, dir_name, hotkey, bpm_min, bpm_max) VALUES (?, ?, ?, ?, ?)",
        (name, dir_name, hotkey, bpm_min, bpm_max),
    )
    return get_crate(conn, dir_name)  # type: ignore[return-value]
