"""SQLite access. Hand-rolled migrations keyed on PRAGMA user_version.

The schema is the read contract for every frontend (spec §4). Add a new entry to
MIGRATIONS for every change; never edit an applied one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE crate (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    dir_name  TEXT NOT NULL UNIQUE,
    hotkey    TEXT,
    bpm_min   REAL,
    bpm_max   REAL
);

CREATE TABLE vibe (
    id        INTEGER PRIMARY KEY,
    crate_id  INTEGER NOT NULL REFERENCES crate(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    hotkey    TEXT,
    UNIQUE (crate_id, name)
);

CREATE TABLE track (
    id               TEXT PRIMARY KEY,              -- UUID4, also written into the file as UAT_ID
    fingerprint      TEXT,                          -- chromaprint (compressed, base64)
    audio_hash       TEXT,                          -- md5 of decoded PCM (FLAC STREAMINFO) when known
    rel_path         TEXT NOT NULL UNIQUE,          -- relative to collection root, POSIX separators
    crate_id         INTEGER REFERENCES crate(id),
    title            TEXT,
    artist           TEXT,
    album            TEXT,
    albumartist      TEXT,
    genre            TEXT,
    duration_ms      INTEGER NOT NULL DEFAULT 0,
    bpm              REAL,
    key              TEXT,
    energy           INTEGER CHECK (energy IS NULL OR energy BETWEEN 1 AND 5),
    rating           INTEGER CHECK (rating IS NULL OR rating BETWEEN 0 AND 5),
    loudness_lufs    REAL,
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    codec            TEXT NOT NULL DEFAULT '',
    sample_rate      INTEGER NOT NULL DEFAULT 0,
    bit_depth        INTEGER NOT NULL DEFAULT 0,
    bitrate          INTEGER NOT NULL DEFAULT 0,
    state            TEXT NOT NULL DEFAULT 'crated'
                     CHECK (state IN ('wanted','inbox','crated','sorted','missing')),
    deferred         INTEGER NOT NULL DEFAULT 0,
    source_url       TEXT,
    added_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    analyzed_at      TEXT,
    tags_written_at  TEXT                           -- ISO-8601 UTC of our last tag write
);
CREATE INDEX track_crate_idx ON track(crate_id);
CREATE INDEX track_fingerprint_idx ON track(fingerprint);
CREATE INDEX track_state_idx ON track(state);

CREATE TABLE track_vibe (
    track_id  TEXT NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    vibe_id   INTEGER NOT NULL REFERENCES vibe(id) ON DELETE CASCADE,
    PRIMARY KEY (track_id, vibe_id)
);

CREATE TABLE playlist (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    parent_id  INTEGER REFERENCES playlist(id) ON DELETE CASCADE,
    UNIQUE (parent_id, name)
);

CREATE TABLE playlist_track (
    playlist_id  INTEGER NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    track_id     TEXT NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE TABLE sort_log (
    id          INTEGER PRIMARY KEY,
    track_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    from_path   TEXT,
    to_path     TEXT,
    prev_state  TEXT,
    at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""

MIGRATIONS: list[str] = [SCHEMA_V1]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; we manage transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={version};\nCOMMIT;")
    return conn.execute("PRAGMA user_version").fetchone()[0]


def open_library(root: Path) -> sqlite3.Connection:
    conn = connect(root / ".unalphathet" / "library.db")
    migrate(conn)
    return conn
