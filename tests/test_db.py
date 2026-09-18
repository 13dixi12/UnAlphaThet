import sqlite3

import pytest

from unalphathet.core import db


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_migrate_creates_schema(tmp_path):
    conn = db.connect(tmp_path / "lib.db")
    version = db.migrate(conn)
    assert version == 1
    assert {"track", "crate", "vibe", "track_vibe", "playlist", "playlist_track", "sort_log"} <= _tables(conn)


def test_migrate_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "lib.db")
    assert db.migrate(conn) == 1
    assert db.migrate(conn) == 1


def test_open_library_creates_dir(tmp_path):
    root = tmp_path / "coll"
    root.mkdir()
    conn = db.open_library(root)
    assert (root / ".unalphathet" / "library.db").exists()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_track_state_is_checked(tmp_path):
    conn = db.open_library(tmp_path)
    conn.execute("INSERT INTO crate(name, dir_name) VALUES ('psy','psy')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO track(id, rel_path, crate_id, state) VALUES ('x','psy/a.flac',1,'bogus')"
        )


def test_vibe_unique_per_crate(tmp_path):
    conn = db.open_library(tmp_path)
    conn.execute("INSERT INTO crate(name, dir_name) VALUES ('psy','psy')")
    conn.execute("INSERT INTO vibe(crate_id, name) VALUES (1,'night')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO vibe(crate_id, name) VALUES (1,'night')")


def test_transaction_rolls_back_and_nests(tmp_path):
    conn = db.open_library(tmp_path)
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            conn.execute("INSERT INTO crate(name, dir_name) VALUES ('psy','psy')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM crate").fetchone()[0] == 0
    with db.transaction(conn):
        conn.execute("INSERT INTO crate(name, dir_name) VALUES ('psy','psy')")
        with db.transaction(conn):  # nested: no second BEGIN
            conn.execute("INSERT INTO crate(name, dir_name) VALUES ('techno','techno')")
    assert conn.execute("SELECT COUNT(*) FROM crate").fetchone()[0] == 2
