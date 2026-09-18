# UnAlphaThet Phase 0+1 — Bootstrap, Library Core, Browse TUI — Implementation Plan

> **Status: executed 2026-09-18 on branch `phase-0-1`.** Deviations from the plan as written: the three (Dixi) slots were decided by Dixi in conversation and implemented by Claire; `ids.similarity()` replaced the bogus fingerprint-prefix test; `db.transaction()` was added for nested transactions; three scan bugs found in review were fixed (cross-crate vibe leak, UUID re-minting on lost DB, lossy-BPM rewrite loop); playback bindings got `priority=True`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working `uat` CLI + Textual browse screen over a real collection directory: crates, crate-scoped vibes, playlists, UUID-stamped tracks, tag read/write-back, a reconciling scan, and mpv preview — the foundation every later phase builds on.

**Architecture:** `unalphathet.core` (config, db, models, fs, tags, ids, scan) and `unalphathet.library` (crates, vibes, playlists, query) form a UI-free service layer over SQLite + file tags. `cli.py` (Typer) and `tui/` (Textual) are thin consumers of that layer; both are given an open `sqlite3.Connection`, the collection root and a `Config`. Preview playback sits behind a `Player` protocol with an mpv JSON-IPC implementation and a `NullPlayer` for tests.

**Tech Stack:** Python 3.13 (uv-managed), Typer, Textual 8, mutagen, pyacoustid (`fpcalc`), sqlite3 (stdlib, WAL), tomllib (stdlib), pytest + pytest-asyncio, ruff. External binaries: ffmpeg/ffprobe (fixtures, doctor), fpcalc, mpv.

**Spec:** `docs/superpowers/specs/2026-09-18-unalphathet-design.md`

## Global Constraints

- Python `>=3.13`; project pinned to 3.13 via `.python-version`; never 3.14 (audio wheels lag).
- Package name `unalphathet`, CLI entry point `uat`, flat layout (`unalphathet/` at repo root, not `src/`).
- Config: `~/.config/unalphathet/config.toml` (respect `$XDG_CONFIG_HOME`); default collection root `~/music/dj`; DB at `<root>/.unalphathet/library.db`.
- Reserved top-level dirs in the collection: `inbox/`, `playlists/`, any dot-dir. Every other top-level dir is a crate.
- Track PK = UUID4 string written into the file as `UAT_ID` (Vorbis comment / ID3 `TXXX:UAT_ID` / MP4 `----:com.apple.iTunes:UAT_ID`). Path is never identity.
- Vibes are crate-scoped. A track only ever carries vibes of its own crate. Grouping tag format: `crate_dir/vibe;crate_dir/vibe`.
- Conflict rule on scan: file mtime newer than DB `tags_written_at` **and** values differ → tag wins; else DB wins.
- Service layer (`core/`, `library/`) must not import `textual`, `typer`, or `rich`.
- Every CLI command supports `--json` (global flag) and exits non-zero on failure.
- Tests never require an audio device: mpv runs with `--ao=null`; fixtures are ffmpeg-generated seeded pink noise (sine tones give empty chromaprints).
- Commit after every task with a conventional-commit message ending in `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Learning mode:** steps marked **(Dixi)** are written by Dixi. Claire prepares the file, signature, docstring and tests for the fixed requirements; Dixi writes the body and adds tests for the judgment calls she makes.

---

## File structure

```
pyproject.toml                       project metadata, deps, pytest/ruff config
.python-version                      3.13
.gitignore
unalphathet/__init__.py              __version__
unalphathet/config.py                Config dataclass, load_config, write_default_config, default_config_path
unalphathet/core/__init__.py
unalphathet/core/db.py               connect, migrate (PRAGMA user_version), open_library, SCHEMA_V1
unalphathet/core/models.py           Track, Crate, Vibe, Playlist dataclasses, TrackState, row_to_* helpers
unalphathet/core/fs.py               AUDIO_EXTS, is_audio, crate_dirs, iter_crate_files, slugify, safe_filename
unalphathet/core/tags.py             TrackTags, read_tags, write_tags (vorbis / id3 / mp4 dispatch)
unalphathet/core/ids.py              new_track_id, fingerprint, audio_md5
unalphathet/core/scan.py             ScanReport, Source, resolve_conflict, scan
unalphathet/library/__init__.py
unalphathet/library/crates.py        list_crates, get_crate, ensure_crate, add_crate
unalphathet/library/vibes.py         list_vibes, add_vibe, set_track_vibes, track_vibes, parse_grouping, format_grouping
unalphathet/library/playlists.py     list_playlists, add_playlist, add_track, remove_track, playlist_tracks, export_m3u8
unalphathet/library/query.py         get_track, tracks_in_crate, tracks_with_vibe, search
unalphathet/cli.py                   Typer app: init, doctor, scan, ls, tui, crate {ls,add}, vibe {ls,add}, playlist {ls,add,add-track,export}
unalphathet/doctor.py                check_environment -> list[Check]  (used by cli doctor; no typer import)
unalphathet/tui/__init__.py
unalphathet/tui/player.py            Player protocol, NullPlayer, MpvPlayer
unalphathet/tui/app.py               UatApp
unalphathet/tui/screens/__init__.py
unalphathet/tui/screens/browse.py    BrowseScreen (Tree | DataTable | status bar)
tests/conftest.py                    make_audio (ffmpeg seeded noise), collection fixture, db fixture
tests/test_*.py                      one per module
```

---

### Task 1: Project bootstrap

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `unalphathet/__init__.py`, `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `unalphathet.__version__: str`; `unalphathet.cli.app: typer.Typer`; `uat --version`.

- [x] **Step 1: Write project files**

`.python-version`:
```
3.13
```

`pyproject.toml`:
```toml
[project]
name = "unalphathet"
version = "0.1.0"
description = "rekordbox-free DJ library, inbox sorter and stick manager (TUI)"
readme = "README.md"
license = "MIT"
requires-python = ">=3.13,<3.14"
dependencies = [
    "textual>=8,<9",
    "typer>=0.27",
    "mutagen>=1.48",
    "pyacoustid>=1.3",
]

[project.scripts]
uat = "unalphathet.cli:app"

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=1.0",
    "ruff>=0.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["unalphathet"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
unsaved file*
```

`README.md`:
```markdown
# UnAlphaThet

rekordbox-free DJ library, inbox sorter and stick manager. Terminal UI. See `docs/superpowers/specs/`.

    uv sync
    uv run uat --help
```

`unalphathet/__init__.py`:
```python
__version__ = "0.1.0"
```

- [x] **Step 2: Write the failing CLI test**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner

from unalphathet import __version__
from unalphathet.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
```

- [x] **Step 3: Sync env and run test to verify it fails**

Run: `cd /workspace/UnAlphaThet && uv sync && uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'unalphathet.cli'`

- [x] **Step 4: Write minimal CLI**

`unalphathet/cli.py`:
```python
"""uat — the UnAlphaThet command line. Thin layer over unalphathet.core / .library."""

from __future__ import annotations

import typer

from unalphathet import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"uat {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    """UnAlphaThet: rekordbox-free DJ library."""
```

- [x] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore README.md uv.lock unalphathet tests
git commit -m "chore: bootstrap uv project, uat entry point

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Config loading and `uat init`

**Files:**
- Create: `unalphathet/config.py`, `tests/test_config.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `Config(collection_root: Path, write_back_tags: bool = True, preview_autoplay: bool = True, preview_start_at: float = 0.25, mpv_args: tuple[str, ...] = ())`
  - `default_config_path() -> Path`
  - `load_config(path: Path | None = None) -> Config` — missing file → defaults.
  - `write_default_config(path: Path, collection_root: Path) -> None`
  - `Config.db_path -> Path` (`<root>/.unalphathet/library.db`)
  - CLI global options `--config PATH` and `--json`, stored in `ctx.obj = CliState(config, json)`.

- [x] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
from pathlib import Path

from unalphathet.config import Config, default_config_path, load_config, write_default_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.collection_root == Path("~/music/dj").expanduser()
    assert cfg.write_back_tags is True
    assert cfg.preview_start_at == 0.25


def test_roundtrip(tmp_path):
    p = tmp_path / "config.toml"
    write_default_config(p, tmp_path / "coll")
    cfg = load_config(p)
    assert cfg.collection_root == tmp_path / "coll"
    assert cfg.db_path == tmp_path / "coll" / ".unalphathet" / "library.db"


def test_partial_file_keeps_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[collection]\nroot = "/x"\n[tags]\nwrite_back = false\n')
    cfg = load_config(p)
    assert cfg.collection_root == Path("/x")
    assert cfg.write_back_tags is False
    assert cfg.preview_autoplay is True


def test_default_config_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "unalphathet" / "config.toml"
```

Append to `tests/test_cli.py`:
```python
def test_init_creates_config_and_collection(tmp_path):
    cfg = tmp_path / "config.toml"
    root = tmp_path / "coll"
    result = runner.invoke(app, ["--config", str(cfg), "init", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert cfg.exists()
    assert (root / "inbox").is_dir()
    assert (root / ".unalphathet").is_dir()


def test_init_json(tmp_path):
    cfg = tmp_path / "config.toml"
    result = runner.invoke(
        app, ["--config", str(cfg), "--json", "init", "--root", str(tmp_path / "c")]
    )
    assert result.exit_code == 0
    import json

    assert json.loads(result.output)["collection_root"].endswith("/c")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.config`, `init` unknown command)

- [x] **Step 3: Implement config**

`unalphathet/config.py`:
```python
"""User configuration. TOML in, frozen dataclass out. Missing file == defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path("~/music/dj")


@dataclass(frozen=True)
class Config:
    collection_root: Path
    write_back_tags: bool = True
    preview_autoplay: bool = True
    preview_start_at: float = 0.25
    mpv_args: tuple[str, ...] = ()

    @property
    def db_path(self) -> Path:
        return self.collection_root / ".unalphathet" / "library.db"


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unalphathet" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    data: dict = {}
    if path.exists():
        data = tomllib.loads(path.read_text())
    coll = data.get("collection", {})
    tags = data.get("tags", {})
    preview = data.get("preview", {})
    return Config(
        collection_root=Path(coll.get("root", str(DEFAULT_ROOT))).expanduser(),
        write_back_tags=bool(tags.get("write_back", True)),
        preview_autoplay=bool(preview.get("autoplay", True)),
        preview_start_at=float(preview.get("start_at", 0.25)),
        mpv_args=tuple(preview.get("mpv_args", [])),
    )


def write_default_config(path: Path, collection_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# UnAlphaThet configuration\n"
        "[collection]\n"
        f'root = "{collection_root}"\n\n'
        "[tags]\n"
        "write_back = true   # write vibes/bpm/key/id into the audio files\n\n"
        "[preview]\n"
        "autoplay = true\n"
        "start_at = 0.25     # fraction of the track to start previewing from\n"
        'mpv_args = []       # e.g. ["--ao=pipewire"]\n'
    )
```

- [x] **Step 4: Add CLI state, `--config`, `--json`, `init`**

Replace `unalphathet/cli.py` with:
```python
"""uat — the UnAlphaThet command line. Thin layer over unalphathet.core / .library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import typer

from unalphathet import __version__
from unalphathet.config import Config, default_config_path, load_config, write_default_config

app = typer.Typer(no_args_is_help=True, add_completion=False)


@dataclass
class CliState:
    config_path: Path
    config: Config
    json: bool


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"uat {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    """UnAlphaThet: rekordbox-free DJ library."""
    path = config or default_config_path()
    ctx.obj = CliState(config_path=path, config=load_config(path), json=as_json)


def emit(ctx: typer.Context, data: Any, human: Callable[[Any], str]) -> None:
    """Print `data` as JSON if --json, else via `human`."""
    state: CliState = ctx.obj
    typer.echo(json.dumps(data, default=str) if state.json else human(data))


@app.command()
def init(
    ctx: typer.Context,
    root: Path | None = typer.Option(None, "--root", help="Collection root directory."),
) -> None:
    """Create the config file and the collection skeleton (inbox/, .unalphathet/)."""
    state: CliState = ctx.obj
    root = (root or state.config.collection_root).expanduser().resolve()
    if not state.config_path.exists():
        write_default_config(state.config_path, root)
    for sub in ("inbox", ".unalphathet", "playlists"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    emit(
        ctx,
        {"config_path": str(state.config_path), "collection_root": str(root)},
        lambda d: f"config: {d['config_path']}\ncollection: {d['collection_root']}",
    )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py tests/test_cli.py -v`
Expected: PASS (6 tests)

- [x] **Step 6: Commit**

```bash
git add unalphathet/config.py unalphathet/cli.py tests/test_config.py tests/test_cli.py
git commit -m "feat: config loading and uat init

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Database schema, migrations, models

**Files:**
- Create: `unalphathet/core/__init__.py`, `unalphathet/core/db.py`, `unalphathet/core/models.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `db.connect(path: Path) -> sqlite3.Connection` (WAL, foreign_keys ON, `sqlite3.Row` factory)
  - `db.migrate(conn) -> int` (returns new `user_version`; idempotent)
  - `db.open_library(root: Path) -> sqlite3.Connection` (creates `<root>/.unalphathet/`, connects, migrates)
  - `models.TrackState = Literal["wanted", "inbox", "crated", "sorted", "missing"]`
  - `models.Track`, `models.Crate`, `models.Vibe`, `models.Playlist` dataclasses; `models.row_to_track(row) -> Track` etc.

- [x] **Step 1: Write failing tests**

`tests/test_db.py`:
```python
import sqlite3

from unalphathet.core import db


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_migrate_creates_schema(tmp_path):
    conn = db.connect(tmp_path / "lib.db")
    version = db.migrate(conn)
    assert version == 1
    assert {
        "track",
        "crate",
        "vibe",
        "track_vibe",
        "playlist",
        "playlist_track",
        "sort_log",
    } <= _tables(conn)


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
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO track(id, rel_path, crate_id, state) VALUES ('x','psy/a.flac',1,'bogus')"
        )


def test_vibe_unique_per_crate(tmp_path):
    conn = db.open_library(tmp_path)
    conn.execute("INSERT INTO crate(name, dir_name) VALUES ('psy','psy')")
    conn.execute("INSERT INTO vibe(crate_id, name) VALUES (1,'night')")
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO vibe(crate_id, name) VALUES (1,'night')")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'unalphathet.core'`

- [x] **Step 3: Implement db and models**

`unalphathet/core/__init__.py`: empty file.

`unalphathet/core/db.py`:
```python
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
        conn.execute("BEGIN")
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version={version}")
        conn.execute("COMMIT")
    return conn.execute("PRAGMA user_version").fetchone()[0]


def open_library(root: Path) -> sqlite3.Connection:
    conn = connect(root / ".unalphathet" / "library.db")
    migrate(conn)
    return conn
```

Note: `executescript` issues a COMMIT before running, so wrap carefully — the `BEGIN`/`COMMIT` pair above is fine because `executescript` commits any pending transaction first and the script itself is then atomic per statement; the PRAGMA write after it is what we care about landing. If a migration half-fails you'll see it in tests immediately.

`unalphathet/core/models.py`:
```python
"""Plain dataclasses mirroring the schema. No behaviour, no I/O."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

TrackState = Literal["wanted", "inbox", "crated", "sorted", "missing"]


@dataclass(frozen=True)
class Crate:
    id: int
    name: str
    dir_name: str
    hotkey: str | None = None
    bpm_min: float | None = None
    bpm_max: float | None = None


@dataclass(frozen=True)
class Vibe:
    id: int
    crate_id: int
    name: str
    hotkey: str | None = None


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    parent_id: int | None = None


@dataclass(frozen=True)
class Track:
    id: str
    rel_path: str
    crate_id: int | None
    state: TrackState
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    duration_ms: int = 0
    bpm: float | None = None
    key: str | None = None
    energy: int | None = None
    rating: int | None = None
    codec: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    size_bytes: int = 0
    fingerprint: str | None = None
    audio_hash: str | None = None
    tags_written_at: str | None = None

    @property
    def display(self) -> str:
        return f"{self.artist or '?'} – {self.title or self.rel_path.rsplit('/', 1)[-1]}"

    @property
    def duration_str(self) -> str:
        s = self.duration_ms // 1000
        return f"{s // 60}:{s % 60:02d}"


def row_to_crate(row: sqlite3.Row) -> Crate:
    return Crate(**{k: row[k] for k in Crate.__dataclass_fields__})


def row_to_vibe(row: sqlite3.Row) -> Vibe:
    return Vibe(**{k: row[k] for k in Vibe.__dataclass_fields__})


def row_to_playlist(row: sqlite3.Row) -> Playlist:
    return Playlist(**{k: row[k] for k in Playlist.__dataclass_fields__})


def row_to_track(row: sqlite3.Row) -> Track:
    return Track(**{k: row[k] for k in Track.__dataclass_fields__})
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Commit**

```bash
git add unalphathet/core tests/test_db.py
git commit -m "feat(core): sqlite schema v1, migrations, model dataclasses

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `uat doctor`

**Files:**
- Create: `unalphathet/doctor.py`, `tests/test_doctor.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `doctor.Check(name: str, ok: bool, detail: str, required: bool)`; `doctor.check_environment(config: Config, config_path: Path) -> list[Check]`; `doctor.all_required_ok(checks) -> bool`.

- [x] **Step 1: Write failing tests**

`tests/test_doctor.py`:
```python
from pathlib import Path

from unalphathet import doctor
from unalphathet.config import Config


def test_missing_binary_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    checks = doctor.check_environment(Config(collection_root=tmp_path), tmp_path / "c.toml")
    by_name = {c.name: c for c in checks}
    assert by_name["ffmpeg"].ok is False and by_name["ffmpeg"].required is True
    assert by_name["mpv"].ok is False and by_name["mpv"].required is False
    assert doctor.all_required_ok(checks) is False


def test_all_good(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text("")
    root = tmp_path / "coll"
    (root / ".unalphathet").mkdir(parents=True)
    checks = doctor.check_environment(Config(collection_root=root), cfg_path)
    assert doctor.all_required_ok(checks)
    assert {c.name for c in checks} >= {
        "python",
        "ffmpeg",
        "ffprobe",
        "fpcalc",
        "mpv",
        "config",
        "collection",
        "database",
    }
```

Append to `tests/test_cli.py`:
```python
def test_doctor_runs(tmp_path):
    result = runner.invoke(app, ["--config", str(tmp_path / "c.toml"), "--json", "doctor"])
    import json

    data = json.loads(result.output)
    assert any(c["name"] == "ffmpeg" for c in data)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_doctor.py tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.doctor`)

- [x] **Step 3: Implement doctor**

`unalphathet/doctor.py`:
```python
"""Environment checks for `uat doctor`. No UI imports; the CLI renders the result."""

from __future__ import annotations

import shutil
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from unalphathet.config import Config

BINARIES: list[tuple[str, bool]] = [
    ("ffmpeg", True),
    ("ffprobe", True),
    ("fpcalc", True),
    ("mpv", False),
]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def check_environment(config: Config, config_path: Path) -> list[Check]:
    checks: list[Check] = []
    v = sys.version_info
    checks.append(Check("python", v >= (3, 13), f"{v.major}.{v.minor}.{v.micro}"))
    for name, required in BINARIES:
        path = shutil.which(name)
        checks.append(Check(name, path is not None, path or "not found in PATH", required))
    checks.append(Check("config", config_path.exists(), str(config_path), required=False))
    root = config.collection_root
    checks.append(Check("collection", root.is_dir(), str(root)))
    db = config.db_path
    if db.exists():
        try:
            conn = sqlite3.connect(db)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            conn.close()
            checks.append(Check("database", True, f"{db} (schema v{version})"))
        except sqlite3.Error as exc:  # corrupt or locked
            checks.append(Check("database", False, f"{db}: {exc}"))
    else:
        checks.append(
            Check(
                "database", root.is_dir(), f"{db} (will be created on first scan)", required=False
            )
        )
    return checks


def all_required_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks if c.required)
```

Add to `unalphathet/cli.py` (after `init`):
```python
@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check binaries, config, collection and database."""
    from unalphathet import doctor as _doctor

    state: CliState = ctx.obj
    checks = _doctor.check_environment(state.config, state.config_path)

    def human(cs: list[_doctor.Check]) -> str:
        lines = []
        for c in cs:
            mark = "ok " if c.ok else ("ERR" if c.required else "warn")
            lines.append(f"[{mark}] {c.name:<11} {c.detail}")
        return "\n".join(lines)

    emit(ctx, [c.__dict__ for c in checks], human)
    if not _doctor.all_required_ok(checks):
        raise typer.Exit(code=1)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_doctor.py tests/test_cli.py -v`
Expected: PASS

- [x] **Step 5: Run it for real and commit**

Run: `uv run uat --config /tmp/uat-test.toml doctor` — expect ok for ffmpeg/ffprobe/fpcalc/mpv, ERR for collection (doesn't exist yet). Exit code 1 is correct here.

```bash
git add unalphathet/doctor.py unalphathet/cli.py tests/test_doctor.py tests/test_cli.py
git commit -m "feat: uat doctor environment checks

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Filesystem helpers

**Files:**
- Create: `unalphathet/core/fs.py`, `tests/test_fs.py`

**Interfaces:**
- Produces:
  - `AUDIO_EXTS: frozenset[str]` = `{".flac", ".mp3", ".m4a", ".wav", ".aiff", ".aif", ".ogg", ".opus"}`
  - `RESERVED_DIRS: frozenset[str]` = `{"inbox", "playlists"}`
  - `is_audio(path: Path) -> bool`
  - `crate_dirs(root: Path) -> list[Path]` — sorted top-level dirs, excluding reserved and dot-dirs
  - `iter_crate_files(root: Path) -> Iterator[tuple[str, Path]]` — `(crate_dir_name, absolute file path)`, recursive, sorted, audio only
  - `rel_posix(root: Path, path: Path) -> str`
  - `slugify(name: str) -> str` — `"Full On!"` → `"full-on"`
  - `safe_filename(artist: str | None, title: str, ext: str) -> str` **(Dixi)**

- [x] **Step 1: Write failing tests for the fixed behaviour**

`tests/test_fs.py`:
```python
from pathlib import Path

from unalphathet.core import fs


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_is_audio():
    assert fs.is_audio(Path("x/y.FLAC"))
    assert fs.is_audio(Path("a.mp3"))
    assert not fs.is_audio(Path("cover.jpg"))
    assert not fs.is_audio(Path("notes.txt"))


def test_crate_dirs_skips_reserved_and_hidden(tmp_path):
    for d in ("psy", "techno", "inbox", "playlists", ".unalphathet"):
        (tmp_path / d).mkdir()
    _touch(tmp_path / "stray.flac")
    assert [p.name for p in fs.crate_dirs(tmp_path)] == ["psy", "techno"]


def test_iter_crate_files_recursive_sorted_audio_only(tmp_path):
    _touch(tmp_path / "psy" / "b.flac")
    _touch(tmp_path / "psy" / "sub" / "a.mp3")
    _touch(tmp_path / "psy" / "cover.jpg")
    _touch(tmp_path / "inbox" / "new.flac")
    _touch(tmp_path / "techno" / "c.wav")
    got = [(c, p.relative_to(tmp_path).as_posix()) for c, p in fs.iter_crate_files(tmp_path)]
    assert got == [("psy", "psy/b.flac"), ("psy", "psy/sub/a.mp3"), ("techno", "techno/c.wav")]


def test_rel_posix(tmp_path):
    assert fs.rel_posix(tmp_path, tmp_path / "psy" / "x.flac") == "psy/x.flac"


def test_slugify():
    assert fs.slugify("Full On!") == "full-on"
    assert fs.slugify("  Dark   Psy ") == "dark-psy"
    assert fs.slugify("drum&bass") == "drum-bass"
    assert fs.slugify("Ünïcode") == "unicode"


# --- safe_filename: fixed requirements (Dixi adds tests for her own choices) ---

FAT_FORBIDDEN = set('\\/:*?"<>|')


def test_safe_filename_has_no_fat_forbidden_chars():
    name = fs.safe_filename('A/B: "C"', "T*it?le <x>|y", ".flac")
    assert not (set(name) & FAT_FORBIDDEN)
    assert name.endswith(".flac")


def test_safe_filename_shape():
    assert (
        fs.safe_filename("Astrix", "Deep Jungle Walk", ".flac") == "Astrix - Deep Jungle Walk.flac"
    )
    assert fs.safe_filename(None, "Untitled", ".mp3") == "Untitled.mp3"
    assert fs.safe_filename("", "Untitled", ".mp3") == "Untitled.mp3"


def test_safe_filename_length_bound():
    name = fs.safe_filename("A" * 300, "B" * 300, ".flac")
    assert len(name.encode("utf-8")) <= 200
    assert name.endswith(".flac")


def test_safe_filename_never_empty_stem():
    assert fs.safe_filename(None, "???", ".flac") != ".flac"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fs.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.core.fs`)

- [x] **Step 3: Implement everything except `safe_filename`**

`unalphathet/core/fs.py`:
```python
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


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


MAX_FILENAME_BYTES = 200  # leaves room for FAT32's 255-byte limit after a PIONEER/ prefix


def safe_filename(artist: str | None, title: str, ext: str) -> str:
    """Build `Artist - Title<ext>` that is safe on FAT32/exFAT and every CDJ.

    Requirements (tested in tests/test_fs.py):
      * none of  \\ / : * ? " < > |  in the result
      * `ext` (with its dot) is preserved verbatim at the end
      * artist None/empty -> just `Title<ext>`
      * result is at most MAX_FILENAME_BYTES bytes in UTF-8, ext included
      * the stem is never empty (fall back to something sensible)

    Your calls (add a test for each): what to replace forbidden chars with (drop? '_'? '-'?),
    whether to collapse runs of whitespace, whether to keep non-ASCII (CDJs render UTF-8 fine;
    some very old ones show garbage), how to truncate (cut the title first? both evenly?).
    """
    raise NotImplementedError  # TODO(Dixi)
```

- [x] **Step 4 (Dixi): Implement `safe_filename`**

Context: this function names every file that ever lands in a crate or on a stick. It is the one place where "what does a track look like on the CDJ screen" is decided, because folder-browse sticks show filenames. Roughly 8–12 lines. Run `uv run pytest tests/test_fs.py -v` until the fixed tests pass, then add at least two tests for choices you made (replacement char, unicode policy, truncation).

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_fs.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add unalphathet/core/fs.py tests/test_fs.py
git commit -m "feat(core): collection filesystem helpers and FAT-safe filenames

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Audio fixtures and tag reading

**Files:**
- Create: `tests/conftest.py`, `unalphathet/core/tags.py`, `tests/test_tags.py`

**Interfaces:**
- Produces:
  - `conftest.make_audio(path: Path, *, seconds: float = 3, seed: int = 1, **meta: str) -> Path` — ffmpeg seeded pink noise, encoder by extension (`.flac`, `.mp3`, `.m4a`, `.wav`), `-metadata` from `meta`.
  - `tags.TrackTags` dataclass (fields below).
  - `tags.read_tags(path: Path) -> TrackTags`
  - Fixture `ffmpeg` skips tests when ffmpeg is missing.

- [x] **Step 1: Write conftest**

`tests/conftest.py`:
```python
"""Shared fixtures. Audio fixtures are ffmpeg-generated seeded pink noise:
same seed => identical audio => identical chromaprint; sine tones give empty fingerprints."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from unalphathet.core import db

ENCODERS = {
    ".flac": ["-c:a", "flac"],
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
```

- [x] **Step 2: Write failing tag-reading tests**

`tests/test_tags.py`:
```python
from unalphathet.core.tags import TrackTags, read_tags

from .conftest import make_audio


def test_read_flac(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.flac", title="Deep", artist="Astrix", album="DJW", genre="Psy")
    t = read_tags(p)
    assert (t.title, t.artist, t.album, t.genre) == ("Deep", "Astrix", "DJW", "Psy")
    assert t.codec == "flac" and t.sample_rate == 44100 and t.bit_depth == 16
    assert 2900 <= t.duration_ms <= 3100
    assert t.audio_md5 and len(t.audio_md5) == 32
    assert t.uat_id is None


def test_read_mp3(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.mp3", title="Heart", artist="Astrix")
    t = read_tags(p)
    assert (t.title, t.artist) == ("Heart", "Astrix")
    assert t.codec == "mp3" and t.bitrate > 0 and t.audio_md5 is None


def test_read_m4a(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.m4a", title="Floorshow", artist="Surgeon")
    t = read_tags(p)
    assert (t.title, t.artist) == ("Floorshow", "Surgeon")
    assert t.codec == "aac"


def test_read_wav_without_tags(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.wav")
    t = read_tags(p)
    assert t.title is None and t.codec == "pcm" and t.sample_rate == 44100


def test_tracktags_defaults():
    t = TrackTags()
    assert t.bpm is None and t.energy is None and t.grouping is None
```

- [x] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_tags.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.core.tags`)

- [x] **Step 4: Implement TrackTags and read_tags**

`unalphathet/core/tags.py`:
```python
"""Read and write the tag fields UnAlphaThet cares about, across FLAC/Ogg (Vorbis comments),
MP3/WAV/AIFF (ID3) and M4A (MP4 atoms). Everything else in the file is left untouched.

Custom fields: UAT_ID (track UUID), UAT_ENERGY (1-5). Vibes ride in GROUPING as
`crate/vibe;crate/vibe` (see library.vibes.format_grouping)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import mutagen
from mutagen._vorbis import VCommentDict
from mutagen.id3 import ID3, TALB, TBPM, TCON, TIT1, TIT2, TKEY, TPE1, TPE2, TXXX
from mutagen.mp4 import MP4, MP4FreeForm


@dataclass
class TrackTags:
    uat_id: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    albumartist: str | None = None
    genre: str | None = None
    grouping: str | None = None
    bpm: float | None = None
    key: str | None = None
    energy: int | None = None
    # stream info (read-only)
    duration_ms: int = 0
    codec: str = ""
    sample_rate: int = 0
    bit_depth: int = 0
    bitrate: int = 0
    audio_md5: str | None = None


WRITABLE = (
    "uat_id",
    "title",
    "artist",
    "album",
    "albumartist",
    "genre",
    "grouping",
    "bpm",
    "key",
    "energy",
)

# field -> tag key per family
VORBIS_KEYS = {
    "uat_id": "UAT_ID",
    "title": "TITLE",
    "artist": "ARTIST",
    "album": "ALBUM",
    "albumartist": "ALBUMARTIST",
    "genre": "GENRE",
    "grouping": "GROUPING",
    "bpm": "BPM",
    "key": "INITIALKEY",
    "energy": "UAT_ENERGY",
}
ID3_FRAMES = {  # field -> frame class (TXXX handled separately)
    "title": TIT2,
    "artist": TPE1,
    "album": TALB,
    "albumartist": TPE2,
    "genre": TCON,
    "grouping": TIT1,
    "bpm": TBPM,
    "key": TKEY,
}
ID3_TXXX = {"uat_id": "UAT_ID", "energy": "UAT_ENERGY"}
MP4_KEYS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "albumartist": "aART",
    "genre": "\xa9gen",
    "grouping": "\xa9grp",
}
MP4_FREEFORM = {
    "uat_id": "----:com.apple.iTunes:UAT_ID",
    "energy": "----:com.apple.iTunes:UAT_ENERGY",
    "key": "----:com.apple.iTunes:initialkey",
}


def _first(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    if isinstance(value, MP4FreeForm):
        return bytes(value).decode("utf-8", "replace")
    if hasattr(value, "text"):  # ID3 frame
        value = value.text[0] if value.text else None
    return None if value is None else str(value)


def _to_float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def _to_int(s: str | None) -> int | None:
    f = _to_float(s)
    return int(f) if f is not None else None


def _codec_name(f: mutagen.FileType) -> str:
    name = type(f).__name__.lower()
    if name == "mp4":
        c = getattr(f.info, "codec", "")
        return "alac" if c == "alac" else "aac"
    if name in ("wave", "aiff"):
        return "pcm"
    if name == "oggvorbis":
        return "vorbis"
    if name == "oggopus":
        return "opus"
    return name  # flac, mp3


def _stream_info(f: mutagen.FileType, t: TrackTags) -> None:
    info = f.info
    t.duration_ms = int(round(getattr(info, "length", 0) * 1000))
    t.codec = _codec_name(f)
    t.sample_rate = int(getattr(info, "sample_rate", 0) or 0)
    t.bit_depth = int(getattr(info, "bits_per_sample", 0) or 0)
    t.bitrate = int(getattr(info, "bitrate", 0) or 0)
    md5 = getattr(info, "md5_signature", None)
    if md5:
        t.audio_md5 = f"{md5:032x}"


def read_tags(path: Path) -> TrackTags:
    f = mutagen.File(path)
    if f is None:
        raise ValueError(f"unsupported audio file: {path}")
    t = TrackTags()
    _stream_info(f, t)
    tags = f.tags
    if tags is None:
        return t
    if isinstance(tags, VCommentDict):
        for field, k in VORBIS_KEYS.items():
            setattr(t, field, _first(tags.get(k)))
    elif isinstance(tags, ID3):
        for field, frame in ID3_FRAMES.items():
            setattr(t, field, _first(tags.get(frame.__name__)))
        for field, desc in ID3_TXXX.items():
            setattr(t, field, _first(tags.get(f"TXXX:{desc}")))
    elif isinstance(f, MP4):
        for field, k in MP4_KEYS.items():
            setattr(t, field, _first(tags.get(k)))
        for field, k in MP4_FREEFORM.items():
            setattr(t, field, _first(tags.get(k)))
        t.bpm = _first(tags.get("tmpo"))
    t.bpm = _to_float(t.bpm)  # type: ignore[arg-type]
    t.energy = _to_int(t.energy)  # type: ignore[arg-type]
    return t
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tags.py -v`
Expected: PASS (5 tests)

- [x] **Step 6: Commit**

```bash
git add tests/conftest.py unalphathet/core/tags.py tests/test_tags.py
git commit -m "feat(core): tag reading across flac/mp3/m4a/wav, ffmpeg test fixtures

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Tag writing

**Files:**
- Modify: `unalphathet/core/tags.py`, `tests/test_tags.py`

**Interfaces:**
- Produces: `tags.write_tags(path: Path, tags: TrackTags, only: Iterable[str] | None = None) -> None` — writes the `WRITABLE` fields (or the subset `only`); `None` values remove the tag. Preserves everything else in the file.

- [x] **Step 1: Write failing tests**

Append to `tests/test_tags.py`:
```python
import pytest

from unalphathet.core.tags import write_tags


@pytest.mark.parametrize("ext", [".flac", ".mp3", ".m4a", ".wav"])
def test_write_then_read_roundtrip(tmp_path, ffmpeg, ext):
    p = make_audio(tmp_path / f"a{ext}", title="Orig", artist="Someone")
    t = read_tags(p)
    t.uat_id = "0f0e0d0c-0b0a-4908-8706-050403020100"
    t.grouping = "psy/full-on;psy/night"
    t.genre = "psy"
    t.bpm = 142.0
    t.key = "8A"
    t.energy = 4
    write_tags(p, t)
    back = read_tags(p)
    assert back.uat_id == t.uat_id
    assert back.grouping == "psy/full-on;psy/night"
    assert back.genre == "psy"
    assert back.bpm == 142.0
    assert back.key == "8A"
    assert back.energy == 4
    assert back.title == "Orig" and back.artist == "Someone"  # untouched fields survive


def test_write_subset_and_removal(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.flac", title="Orig", artist="Someone", genre="Old")
    write_tags(p, TrackTags(uat_id="abc", genre=None), only=("uat_id", "genre"))
    back = read_tags(p)
    assert back.uat_id == "abc"
    assert back.genre is None
    assert back.title == "Orig"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tags.py -v`
Expected: FAIL (`ImportError: cannot import name 'write_tags'`)

- [x] **Step 3: Implement write_tags**

Append to `unalphathet/core/tags.py`:
```python
def _fmt(field: str, value) -> str:
    if field == "bpm":
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def write_tags(path: Path, t: TrackTags, only=None) -> None:
    f = mutagen.File(path)
    if f is None:
        raise ValueError(f"unsupported audio file: {path}")
    if f.tags is None:
        f.add_tags()
    tags = f.tags
    fields_to_write = tuple(only) if only is not None else WRITABLE

    if isinstance(tags, VCommentDict):
        for field in fields_to_write:
            k, v = VORBIS_KEYS[field], getattr(t, field)
            if v is None:
                tags.pop(k, None)
            else:
                tags[k] = _fmt(field, v)
    elif isinstance(tags, ID3):
        for field in fields_to_write:
            v = getattr(t, field)
            if field in ID3_TXXX:
                key = f"TXXX:{ID3_TXXX[field]}"
                tags.delall(key)
                if v is not None:
                    tags.add(TXXX(encoding=3, desc=ID3_TXXX[field], text=[_fmt(field, v)]))
            else:
                frame = ID3_FRAMES[field]
                tags.delall(frame.__name__)
                if v is not None:
                    tags.add(frame(encoding=3, text=[_fmt(field, v)]))
    elif isinstance(f, MP4):
        for field in fields_to_write:
            v = getattr(t, field)
            if field == "bpm":
                if v is None:
                    tags.pop("tmpo", None)
                else:
                    tags["tmpo"] = [int(round(v))]
            elif field in MP4_FREEFORM:
                k = MP4_FREEFORM[field]
                if v is None:
                    tags.pop(k, None)
                else:
                    tags[k] = [MP4FreeForm(_fmt(field, v).encode("utf-8"))]
            else:
                k = MP4_KEYS[field]
                if v is None:
                    tags.pop(k, None)
                else:
                    tags[k] = [_fmt(field, v)]
    else:
        raise ValueError(f"don't know how to write tags for {path}")
    f.save()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tags.py -v`
Expected: PASS. If the `.wav` roundtrip fails on `add_tags`, mutagen's `WAVE` needs `f.add_tags()` before `f.tags` is an `ID3` — the code above does that; if it still fails, print `type(f.tags)` and adjust the isinstance branch.

- [x] **Step 5: Commit**

```bash
git add unalphathet/core/tags.py tests/test_tags.py
git commit -m "feat(core): tag write-back incl. UAT_ID, grouping, bpm, key, energy

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Track identity helpers

**Files:**
- Create: `unalphathet/core/ids.py`, `tests/test_ids.py`

**Interfaces:**
- Produces:
  - `ids.new_track_id() -> str` (UUID4 string)
  - `ids.fingerprint(path: Path, max_seconds: int = 120) -> tuple[float, str]` — `(duration_seconds, chromaprint)` via `fpcalc`; raises `ids.FingerprintError` on failure.
  - `ids.audio_md5(path: Path) -> str | None` — FLAC STREAMINFO md5 only (others `None`).

- [x] **Step 1: Write failing tests**

`tests/test_ids.py`:
```python
import uuid

import pytest

from unalphathet.core import ids

from .conftest import make_audio


def test_new_track_id_is_uuid4():
    u = uuid.UUID(ids.new_track_id())
    assert u.version == 4


def test_fingerprint_same_audio_same_fp(tmp_path, ffmpeg):
    a = make_audio(tmp_path / "a.flac", seed=42)
    b = make_audio(tmp_path / "b.flac", seed=42)
    c = make_audio(tmp_path / "c.flac", seed=7)
    da, fa = ids.fingerprint(a)
    _, fb = ids.fingerprint(b)
    _, fc = ids.fingerprint(c)
    assert isinstance(fa, str) and len(fa) > 10
    assert 2.9 <= da <= 3.1
    assert fa == fb
    assert fa != fc


def test_fingerprint_survives_reencode(tmp_path, ffmpeg):
    a = make_audio(tmp_path / "a.flac", seed=42)
    b = make_audio(tmp_path / "b.mp3", seed=42)
    assert (
        ids.fingerprint(a)[1][:8] == ids.fingerprint(b)[1][:8]
    )  # header/leading bits match; full compare is Phase 2


def test_fingerprint_error(tmp_path):
    bad = tmp_path / "x.flac"
    bad.write_bytes(b"not audio")
    with pytest.raises(ids.FingerprintError):
        ids.fingerprint(bad)


def test_audio_md5_flac_only(tmp_path, ffmpeg):
    assert len(ids.audio_md5(make_audio(tmp_path / "a.flac"))) == 32
    assert ids.audio_md5(make_audio(tmp_path / "a.mp3")) is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ids.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.core.ids`)

- [x] **Step 3: Implement ids**

`unalphathet/core/ids.py`:
```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ids.py -v`
Expected: PASS. If `test_fingerprint_survives_reencode` fails on the 8-char prefix, relax it to the first 4 chars — the point is only that the two are *related*; real similarity scoring lands in Phase 2.

- [x] **Step 5: Commit**

```bash
git add unalphathet/core/ids.py tests/test_ids.py
git commit -m "feat(core): uuid, chromaprint and audio-md5 identity helpers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Crates

**Files:**
- Create: `unalphathet/library/__init__.py`, `unalphathet/library/crates.py`, `tests/test_crates.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `crates.list_crates(conn) -> list[Crate]`
  - `crates.get_crate(conn, dir_name: str) -> Crate | None`
  - `crates.ensure_crate(conn, root: Path, dir_name: str) -> Crate` — insert-or-get, mkdir
  - `crates.add_crate(conn, root: Path, name: str, hotkey=None, bpm_min=None, bpm_max=None) -> Crate` — `dir_name = slugify(name)`, mkdir, raises `CrateExists`
  - CLI: `uat crate ls`, `uat crate add NAME [--hotkey K] [--bpm MIN-MAX]`
  - CLI helper `open_ctx(ctx) -> tuple[sqlite3.Connection, Path, Config]` for later commands

- [x] **Step 1: Write failing tests**

`tests/test_crates.py`:
```python
import pytest

from unalphathet.library import crates


def test_add_and_list(conn, collection):
    c = crates.add_crate(conn, collection, "Drum & Bass", hotkey="4", bpm_min=170, bpm_max=180)
    assert c.dir_name == "drum-bass" and (collection / "drum-bass").is_dir()
    assert [x.name for x in crates.list_crates(conn)] == ["Drum & Bass"]
    assert crates.get_crate(conn, "drum-bass") == c


def test_add_duplicate_raises(conn, collection):
    crates.add_crate(conn, collection, "psy")
    with pytest.raises(crates.CrateExists):
        crates.add_crate(conn, collection, "psy")


def test_ensure_is_idempotent(conn, collection):
    a = crates.ensure_crate(conn, collection, "psy")
    b = crates.ensure_crate(conn, collection, "psy")
    assert a == b and (collection / "psy").is_dir()
```

Append to `tests/test_cli.py`:
```python
def _cfg(tmp_path, root):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[collection]\nroot = "{root}"\n')
    return str(cfg)


def test_crate_add_and_ls(tmp_path):
    root = tmp_path / "coll"
    root.mkdir()
    cfg = _cfg(tmp_path, root)
    assert (
        runner.invoke(
            app, ["--config", cfg, "crate", "add", "Psy", "--hotkey", "1", "--bpm", "135-150"]
        ).exit_code
        == 0
    )
    result = runner.invoke(app, ["--config", cfg, "--json", "crate", "ls"])
    import json

    data = json.loads(result.output)
    assert data[0]["dir_name"] == "psy" and data[0]["bpm_max"] == 150.0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_crates.py tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.library`)

- [x] **Step 3: Implement crates + CLI**

`unalphathet/library/__init__.py`: empty.

`unalphathet/library/crates.py`:
```python
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
```

Add to `unalphathet/cli.py` — imports at top:
```python
import sqlite3

from unalphathet.core import db
from unalphathet.library import crates as _crates
```
and, after `emit`:
```python
def open_ctx(ctx: typer.Context) -> tuple[sqlite3.Connection, Path, Config]:
    """Open (and migrate) the library for the configured collection root."""
    state: CliState = ctx.obj
    root = state.config.collection_root
    if not root.is_dir():
        typer.echo(f"collection root {root} does not exist — run `uat init`", err=True)
        raise typer.Exit(code=1)
    return db.open_library(root), root, state.config


def _parse_bpm_range(spec: str | None) -> tuple[float | None, float | None]:
    if not spec:
        return None, None
    lo, _, hi = spec.partition("-")
    return float(lo), float(hi or lo)


crate_app = typer.Typer(help="Crates (directories).")
app.add_typer(crate_app, name="crate")


@crate_app.command("ls")
def crate_ls(ctx: typer.Context) -> None:
    """List crates."""
    conn, _, _ = open_ctx(ctx)
    rows = [c.__dict__ for c in _crates.list_crates(conn)]
    emit(
        ctx,
        rows,
        lambda cs: (
            "\n".join(
                f"{c['hotkey'] or ' '} {c['name']:<20} {c['dir_name']:<20} "
                f"{'' if c['bpm_min'] is None else f'{c["bpm_min"]:g}-{c["bpm_max"]:g} bpm'}"
                for c in cs
            )
            or "(no crates)"
        ),
    )


@crate_app.command("add")
def crate_add(
    ctx: typer.Context,
    name: str,
    hotkey: str | None = typer.Option(None, "--hotkey"),
    bpm: str | None = typer.Option(None, "--bpm", help="Range like 135-150."),
) -> None:
    """Create a crate directory and register it."""
    conn, root, _ = open_ctx(ctx)
    lo, hi = _parse_bpm_range(bpm)
    try:
        c = _crates.add_crate(conn, root, name, hotkey=hotkey, bpm_min=lo, bpm_max=hi)
    except _crates.CrateExists as exc:
        typer.echo(f"crate already exists: {exc}", err=True)
        raise typer.Exit(code=1)
    emit(ctx, c.__dict__, lambda d: f"created crate {d['name']} -> {root / d['dir_name']}")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_crates.py tests/test_cli.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add unalphathet/library unalphathet/cli.py tests/test_crates.py tests/test_cli.py
git commit -m "feat(library): crates + uat crate ls/add

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Vibes (crate-scoped tags) and the GROUPING format

**Files:**
- Create: `unalphathet/library/vibes.py`, `tests/test_vibes.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `vibes.list_vibes(conn, crate_id: int) -> list[Vibe]`
  - `vibes.add_vibe(conn, crate_id: int, name: str, hotkey: str | None = None) -> Vibe` (raises `VibeExists`)
  - `vibes.track_vibes(conn, track_id: str) -> list[Vibe]`
  - `vibes.set_track_vibes(conn, track_id: str, vibe_ids: Iterable[int]) -> list[Vibe]` **(Dixi)** — replaces the track's vibes; the invariant (only vibes of the track's own crate) is enforced here.
  - `vibes.parse_grouping(s: str | None) -> list[tuple[str, str]]` — `"psy/full-on;psy/night"` → `[("psy","full-on"),("psy","night")]`
  - `vibes.format_grouping(conn, track_id: str) -> str | None`
  - `vibes.apply_grouping(conn, track_id: str, grouping: str | None) -> int` — resolves names to vibe ids within the track's crate (creating vibes as needed), calls `set_track_vibes`; returns number of *ignored* foreign-crate entries.
  - CLI: `uat vibe ls CRATE`, `uat vibe add CRATE NAME [--hotkey K]`

- [x] **Step 1: Write failing tests (fixed requirements)**

`tests/test_vibes.py`:
```python
import pytest

from unalphathet.core.ids import new_track_id
from unalphathet.library import crates, vibes


def _track(conn, crate_id, rel):
    tid = new_track_id()
    conn.execute(
        "INSERT INTO track(id, rel_path, crate_id, state) VALUES (?,?,?,'crated')",
        (tid, rel, crate_id),
    )
    return tid


@pytest.fixture
def two_crates(conn, collection):
    psy = crates.ensure_crate(conn, collection, "psy")
    techno = crates.ensure_crate(conn, collection, "techno")
    return psy, techno


def test_add_and_list(conn, two_crates):
    psy, _ = two_crates
    n = vibes.add_vibe(conn, psy.id, "night", hotkey="n")
    vibes.add_vibe(conn, psy.id, "full-on")
    assert [v.name for v in vibes.list_vibes(conn, psy.id)] == ["full-on", "night"]
    assert n.hotkey == "n"
    with pytest.raises(vibes.VibeExists):
        vibes.add_vibe(conn, psy.id, "night")


def test_set_track_vibes_same_crate(conn, two_crates):
    psy, _ = two_crates
    t = _track(conn, psy.id, "psy/a.flac")
    n = vibes.add_vibe(conn, psy.id, "night")
    f = vibes.add_vibe(conn, psy.id, "full-on")
    vibes.set_track_vibes(conn, t, [n.id, f.id])
    assert {v.name for v in vibes.track_vibes(conn, t)} == {"night", "full-on"}
    vibes.set_track_vibes(conn, t, [n.id])  # replaces, doesn't append
    assert [v.name for v in vibes.track_vibes(conn, t)] == ["night"]


def test_foreign_crate_vibe_never_attached(conn, two_crates):
    """The invariant. HOW it's signalled (exception? report?) is Dixi's call — add a test for it."""
    psy, techno = two_crates
    t = _track(conn, psy.id, "psy/a.flac")
    n = vibes.add_vibe(conn, psy.id, "night")
    hard = vibes.add_vibe(conn, techno.id, "hard")
    try:
        vibes.set_track_vibes(conn, t, [n.id, hard.id])
    except vibes.VibeCrateMismatch:
        pass
    assert all(v.crate_id == psy.id for v in vibes.track_vibes(conn, t))


def test_parse_and_format_grouping(conn, two_crates):
    psy, _ = two_crates
    assert vibes.parse_grouping("psy/full-on;psy/night") == [("psy", "full-on"), ("psy", "night")]
    assert vibes.parse_grouping(" psy/night ; ;") == [("psy", "night")]
    assert vibes.parse_grouping(None) == []
    t = _track(conn, psy.id, "psy/a.flac")
    assert vibes.format_grouping(conn, t) is None
    ignored = vibes.apply_grouping(conn, t, "psy/night;techno/hard;psy/full-on")
    assert ignored == 1
    assert vibes.format_grouping(conn, t) == "psy/full-on;psy/night"
    assert [v.name for v in vibes.list_vibes(conn, psy.id)] == ["full-on", "night"]  # auto-created
```

Append to `tests/test_cli.py`:
```python
def test_vibe_add_and_ls(tmp_path):
    root = tmp_path / "coll"
    root.mkdir()
    cfg = _cfg(tmp_path, root)
    runner.invoke(app, ["--config", cfg, "crate", "add", "psy"])
    assert (
        runner.invoke(
            app, ["--config", cfg, "vibe", "add", "psy", "night", "--hotkey", "n"]
        ).exit_code
        == 0
    )
    result = runner.invoke(app, ["--config", cfg, "--json", "vibe", "ls", "psy"])
    import json

    assert json.loads(result.output)[0]["name"] == "night"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_vibes.py tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.library.vibes`)

- [x] **Step 3: Implement everything except `set_track_vibes`**

`unalphathet/library/vibes.py`:
```python
"""Vibes: tags scoped to a crate. A track only ever carries vibes of its own crate.

On disk, vibes live in the GROUPING tag as `crate_dir/vibe;crate_dir/vibe`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from unalphathet.core.models import Vibe, row_to_vibe


class VibeExists(ValueError):
    pass


class VibeCrateMismatch(ValueError):
    """A vibe from another crate was offered to a track."""


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
    """Replace the track's vibes with `vibe_ids`, enforcing the crate invariant.

    Fixed requirements (tests/test_vibes.py): the result contains only vibes whose crate_id equals
    the track's crate_id; it *replaces* (previous vibes not in `vibe_ids` are removed); returns the
    vibes now attached, sorted by name.

    Your call: what happens when a foreign-crate vibe is in `vibe_ids`? Options: raise
    VibeCrateMismatch and attach nothing (strict, transactional); silently drop the foreign ones;
    drop them but report (return type would change). Think about who calls this: the tagging screen
    (user typed a hotkey — can't be foreign, hotkeys are per crate) and apply_grouping() below (tags
    edited outside the app — foreign entries are expected and should not abort a scan). Add a test
    for the behaviour you pick. Use `conn.execute("BEGIN")` / `COMMIT` if you go transactional.
    """
    raise NotImplementedError  # TODO(Dixi)


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
    """Set a track's vibes from a GROUPING string. Foreign-crate entries are ignored; returns how many."""
    row = conn.execute(
        "SELECT t.crate_id, c.dir_name FROM track t JOIN crate c ON c.id = t.crate_id WHERE t.id = ?",
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
```

- [x] **Step 4 (Dixi): Implement `set_track_vibes`**

Context: this is *the* invariant of the whole data model — "a file can be psy/full-on and psy/night but never also metal/death". Everything that attaches vibes goes through here. Roughly 8–12 lines: look up the track's `crate_id`, look up the offered vibes' `crate_id`s, decide what to do with mismatches, `DELETE FROM track_vibe WHERE track_id=?`, insert the survivors, return `track_vibes(conn, track_id)`. Then add a test for your mismatch behaviour to `tests/test_vibes.py`.

- [x] **Step 5: Add CLI commands**

Add to `unalphathet/cli.py`:
```python
from unalphathet.library import vibes as _vibes

vibe_app = typer.Typer(help="Vibes (crate-scoped tags).")
app.add_typer(vibe_app, name="vibe")


def _crate_or_die(conn, dir_name: str):
    c = _crates.get_crate(conn, dir_name)
    if c is None:
        typer.echo(f"no such crate: {dir_name}", err=True)
        raise typer.Exit(code=1)
    return c


@vibe_app.command("ls")
def vibe_ls(ctx: typer.Context, crate: str) -> None:
    """List vibes of a crate."""
    conn, _, _ = open_ctx(ctx)
    c = _crate_or_die(conn, crate)
    rows = [v.__dict__ for v in _vibes.list_vibes(conn, c.id)]
    emit(
        ctx,
        rows,
        lambda vs: "\n".join(f"{v['hotkey'] or ' '} {v['name']}" for v in vs) or "(no vibes)",
    )


@vibe_app.command("add")
def vibe_add(
    ctx: typer.Context, crate: str, name: str, hotkey: str | None = typer.Option(None, "--hotkey")
) -> None:
    """Add a vibe to a crate."""
    conn, _, _ = open_ctx(ctx)
    c = _crate_or_die(conn, crate)
    try:
        v = _vibes.add_vibe(conn, c.id, name, hotkey=hotkey)
    except _vibes.VibeExists:
        typer.echo(f"vibe already exists: {crate}/{name}", err=True)
        raise typer.Exit(code=1)
    emit(ctx, v.__dict__, lambda d: f"added {crate}/{d['name']}")
```

- [x] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_vibes.py tests/test_cli.py -v`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add unalphathet/library/vibes.py unalphathet/cli.py tests/test_vibes.py tests/test_cli.py
git commit -m "feat(library): crate-scoped vibes, GROUPING format, uat vibe ls/add

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Scan — reconcile filesystem, tags and DB

**Files:**
- Create: `unalphathet/core/scan.py`, `tests/test_scan.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `fs.iter_crate_files`, `fs.rel_posix`, `tags.read_tags/write_tags`, `ids.*`, `crates.ensure_crate`, `vibes.apply_grouping/format_grouping`.
- Produces:
  - `scan.ScanReport(added: int, updated: int, moved: int, missing: int, tag_won: int, db_won: int, errors: list[str])`
  - `scan.Source` enum `TAGS | DB`
  - `scan.resolve_conflict(tags_written_at: str | None, file_mtime_iso: str, db_values: dict, tag_values: dict) -> Source` **(Dixi)**
  - `scan.scan(conn, root: Path, config: Config, progress: Callable[[str], None] | None = None) -> ScanReport`
  - CLI: `uat scan`

Compared fields (DB ↔ tags): `title, artist, album, albumartist, genre, bpm, key, energy` plus `grouping` (DB side via `format_grouping`).

- [x] **Step 1: Write failing tests**

`tests/test_scan.py`:
```python
import os
import time
from pathlib import Path

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.core.tags import read_tags, write_tags
from unalphathet.library import vibes

from .conftest import make_audio


def _cfg(root: Path, write_back=True) -> Config:
    return Config(collection_root=root, write_back_tags=write_back)


def _tracks(conn):
    return {r["rel_path"]: dict(r) for r in conn.execute("SELECT * FROM track").fetchall()}


def test_first_scan_adds_and_stamps_ids(conn, collection):
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.added == 3 and report.errors == []
    t = _tracks(conn)
    assert set(t) == {
        "psy/Astrix - Deep Jungle Walk.flac",
        "psy/albums/Astrix - Heart.mp3",
        "techno/Surgeon - Floorshow.m4a",
    }
    row = t["psy/Astrix - Deep Jungle Walk.flac"]
    assert row["title"] == "Deep Jungle Walk" and row["state"] == "crated"
    assert row["fingerprint"] and row["audio_hash"] and row["tags_written_at"]
    assert read_tags(collection / "psy/Astrix - Deep Jungle Walk.flac").uat_id == row["id"]
    # inbox is not scanned
    assert not any(p.startswith("inbox/") for p in t)


def test_rescan_is_noop(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    report = scan.scan(conn, collection, _cfg(collection))
    assert (report.added, report.moved, report.missing, report.tag_won) == (0, 0, 0, 0)


def test_moved_file_keeps_id(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    before = _tracks(conn)["psy/Astrix - Deep Jungle Walk.flac"]["id"]
    src = collection / "psy/Astrix - Deep Jungle Walk.flac"
    dst = collection / "techno" / src.name
    src.rename(dst)
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.moved == 1 and report.added == 0
    t = _tracks(conn)
    assert t["techno/Astrix - Deep Jungle Walk.flac"]["id"] == before
    assert "psy/Astrix - Deep Jungle Walk.flac" not in t


def test_moved_and_stripped_file_recovered_by_fingerprint(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    src = collection / "psy/Astrix - Deep Jungle Walk.flac"
    before = _tracks(conn)[str(src.relative_to(collection))]["id"]
    # regenerate identical audio with no tags at a new path (== tags stripped + moved)
    src.unlink()
    make_audio(collection / "techno" / "renamed.flac", seed=11)
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.moved == 1 and report.added == 0
    assert _tracks(conn)["techno/renamed.flac"]["id"] == before
    assert read_tags(collection / "techno/renamed.flac").uat_id == before


def test_deleted_file_marked_missing(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    (collection / "techno/Surgeon - Floorshow.m4a").unlink()
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.missing == 1
    assert _tracks(conn)["techno/Surgeon - Floorshow.m4a"]["state"] == "missing"


def test_external_tag_edit_wins_when_newer(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    time.sleep(0.05)
    t = read_tags(p)
    t.title = "Deep Jungle Walk (Edit)"
    t.grouping = "psy/night"
    write_tags(p, t)
    future = time.time() + 5
    os.utime(p, (future, future))
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.tag_won == 1
    row = _tracks(conn)[str(p.relative_to(collection))]
    assert row["title"] == "Deep Jungle Walk (Edit)" and row["state"] == "sorted"
    assert [v.name for v in vibes.track_vibes(conn, row["id"])] == ["night"]


def test_db_wins_when_file_not_newer(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    row = _tracks(conn)[str(p.relative_to(collection))]
    conn.execute("UPDATE track SET title = 'DB Title' WHERE id = ?", (row["id"],))
    past = time.time() - 3600
    os.utime(p, (past, past))
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.db_won == 1
    assert read_tags(p).title == "DB Title"  # written back


def test_scan_without_write_back_touches_no_files(conn, collection):
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    mtime = p.stat().st_mtime
    scan.scan(conn, collection, _cfg(collection, write_back=False))
    assert p.stat().st_mtime == mtime
    assert read_tags(p).uat_id is None
    assert _tracks(conn)[str(p.relative_to(collection))]["id"]
```

Append to `tests/test_cli.py`:
```python
def test_scan_cli(collection):
    cfg = _cfg(collection.parent, collection)
    result = runner.invoke(app, ["--config", cfg, "--json", "scan"])
    assert result.exit_code == 0, result.output
    import json

    assert json.loads(result.output)["added"] == 3
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scan.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.core.scan`)

- [x] **Step 3: Implement scan (all but `resolve_conflict`)**

`unalphathet/core/scan.py`:
```python
"""Reconcile the collection directory, the files' tags and the SQLite index.

Truth model (spec §2): the file's directory is its crate; per-track facts live in the tags AND the
DB; on disagreement the newer side wins (resolve_conflict). Scan never touches inbox/."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from unalphathet.config import Config
from unalphathet.core import fs, ids
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


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def resolve_conflict(
    tags_written_at: str | None, file_mtime_iso: str, db_values: dict, tag_values: dict
) -> Source:
    """Decide who wins when the file's tags and the DB row disagree.

    Spec rule: file mtime newer than `tags_written_at` (our last write) AND values differ -> TAGS
    wins (someone edited the file outside the app); otherwise DB wins and we re-write the tags.
    Both timestamps are ISO-8601 UTC strings of the same shape, so they compare lexically.

    Fixed by tests: newer file -> TAGS; older file -> DB.
    Your calls (add a test each): `tags_written_at is None` (we never wrote this file — e.g. scan
    ran with write_back=false, or the row came from a stick manifest): trust the file or the DB?
    Equal timestamps (same-second edits, FAT32's 2-second mtime resolution on a stick)?
    A file whose mtime is in the future (clock skew)?
    """
    raise NotImplementedError  # TODO(Dixi)


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


def _state_for(conn: sqlite3.Connection, track_id: str, current: str) -> str:
    if current in ("wanted", "inbox"):
        return current
    return "sorted" if vibes.track_vibes(conn, track_id) else "crated"


def _write_back(conn, path: Path, track_id: str, t: TrackTags, config: Config) -> None:
    if not config.write_back_tags:
        return
    t.uat_id = track_id
    write_tags(path, t)
    conn.execute("UPDATE track SET tags_written_at = ? WHERE id = ?", (_mtime_iso(path), track_id))


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
        _update_row(conn, row["id"], {"rel_path": rel, "crate_id": crate_id})
        conn.execute(
            "INSERT INTO sort_log(track_id, action, from_path, to_path) VALUES (?, 'moved', ?, ?)",
            (row["id"], row["rel_path"], rel),
        )
        report.moved += 1
        row = conn.execute("SELECT * FROM track WHERE id = ?", (row["id"],)).fetchone()
    if row["state"] == "missing":
        _update_row(conn, row["id"], {"state": "crated"})
        row = conn.execute("SELECT * FROM track WHERE id = ?", (row["id"],)).fetchone()

    db_tags = _row_tags(conn, row)
    db_values = {k: getattr(db_tags, k) for k in COMPARED}
    tag_values = {k: getattr(file_tags, k) for k in COMPARED}
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
        _write_back(conn, path, row["id"], db_tags, config)
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
) -> None:
    track_id = ids.new_track_id()
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
    conn.execute(
        f"INSERT INTO track({cols}) VALUES ({', '.join('?' * len(values))})", tuple(values.values())
    )
    vibes.apply_grouping(conn, track_id, file_tags.grouping)
    _update_row(conn, track_id, {"state": _state_for(conn, track_id, "crated")})
    _write_back(conn, path, track_id, file_tags, config)
    conn.execute(
        "INSERT INTO sort_log(track_id, action, to_path) VALUES (?, 'added', ?)",
        (track_id, values["rel_path"]),
    )
    report.added += 1


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
            crate = crates.ensure_crate(conn, root, crate_dir)
            file_tags = read_tags(path)
            conn.execute("BEGIN")
            row = None
            if file_tags.uat_id:
                row = conn.execute(
                    "SELECT * FROM track WHERE id = ?", (file_tags.uat_id,)
                ).fetchone()
            fp: str | None = None
            if row is None:
                try:
                    _, fp = ids.fingerprint(path)
                except ids.FingerprintError as exc:
                    report.errors.append(str(exc))
                if fp:
                    row = _find_by_fingerprint(conn, root, fp)
                    if row is not None:  # moved + stripped: re-stamp
                        _write_back(conn, path, row["id"], file_tags, config)
                        file_tags.uat_id = row["id"]
            if row is not None:
                _reconcile_existing(conn, root, path, row, file_tags, crate.id, config, report)
                seen.add(row["id"])
            else:
                _insert_new(conn, root, path, file_tags, crate.id, fp, config, report)
                seen.add(
                    file_tags.uat_id
                    or conn.execute(
                        "SELECT id FROM track WHERE rel_path = ?", (fs.rel_posix(root, path),)
                    ).fetchone()["id"]
                )
            conn.execute("COMMIT")
        except Exception as exc:  # one bad file must not abort the scan
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            report.errors.append(f"{path}: {exc}")

    placeholders = ", ".join("?" * len(seen)) or "''"
    cur = conn.execute(
        f"UPDATE track SET state = 'missing' WHERE state NOT IN ('wanted','inbox','missing') "
        f"AND id NOT IN ({placeholders})",
        tuple(seen),
    )
    report.missing = cur.rowcount
    return report
```

Note on `_write_back` for the *re-stamp* case: it writes the file's own tags back plus the UUID, so a stripped file gets its UUID and nothing else changes; the subsequent `_reconcile_existing` then applies the conflict rule normally (the DB will win because we just wrote the file — `tags_written_at` == mtime).

- [x] **Step 4 (Dixi): Implement `resolve_conflict`**

Context: this is the truth model's tie-breaker (spec §2), and it decides whether an edit you made in another tagger silently gets overwritten. The body is ~5 lines for the spec rule; the interesting part is the three edge cases in the docstring. Pick, implement, add a test each to `tests/test_scan.py` (you can call `resolve_conflict` directly with dicts — no files needed).

- [x] **Step 5: Add `uat scan`**

Add to `unalphathet/cli.py`:
```python
from unalphathet.core import scan as _scan


@app.command()
def scan(ctx: typer.Context) -> None:
    """Reconcile crate directories, file tags and the database."""
    conn, root, config = open_ctx(ctx)
    state: CliState = ctx.obj
    progress = None if state.json else (lambda rel: typer.echo(f"  {rel}", err=True))
    report = _scan.scan(conn, root, config, progress=progress)
    emit(
        ctx,
        report.__dict__,
        lambda r: (
            f"added {r['added']}  updated {r['updated']}  moved {r['moved']}  missing {r['missing']}  "
            f"(tags won {r['tag_won']}, db won {r['db_won']})"
            + ("".join(f"\n  ! {e}" for e in r["errors"]))
        ),
    )
    if report.errors:
        raise typer.Exit(code=2)
```

- [x] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_scan.py tests/test_cli.py -v`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add unalphathet/core/scan.py unalphathet/cli.py tests/test_scan.py tests/test_cli.py
git commit -m "feat(core): reconciling scan with uuid stamping, fingerprint recovery, conflict rule

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Playlists and M3U8 export

**Files:**
- Create: `unalphathet/library/playlists.py`, `tests/test_playlists.py`
- Modify: `unalphathet/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `playlists.list_playlists(conn) -> list[Playlist]`
  - `playlists.get_playlist(conn, name: str, parent_id=None) -> Playlist | None`
  - `playlists.add_playlist(conn, name: str, parent_id: int | None = None) -> Playlist` (raises `PlaylistExists`)
  - `playlists.add_track(conn, playlist_id: int, track_id: str) -> None` — appends; re-adding is a no-op
  - `playlists.remove_track(conn, playlist_id: int, track_id: str) -> None` — renumbers positions
  - `playlists.playlist_tracks(conn, playlist_id: int) -> list[Track]` — ordered
  - `playlists.export_m3u8(conn, root: Path, playlist_id: int) -> Path` — `<root>/playlists/<slug>.m3u8`, paths relative to `playlists/`, `#EXTINF` lines
  - CLI: `uat playlist ls|add NAME|add-track NAME TRACK_ID|export NAME`

- [x] **Step 1: Write failing tests**

`tests/test_playlists.py`:
```python
import pytest

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import playlists


@pytest.fixture
def scanned(conn, collection):
    scan.scan(conn, collection, Config(collection_root=collection))
    ids = [r["id"] for r in conn.execute("SELECT id FROM track ORDER BY rel_path").fetchall()]
    return ids


def test_add_list_and_order(conn, scanned):
    p = playlists.add_playlist(conn, "jungle set")
    assert [x.name for x in playlists.list_playlists(conn)] == ["jungle set"]
    playlists.add_track(conn, p.id, scanned[2])
    playlists.add_track(conn, p.id, scanned[0])
    playlists.add_track(conn, p.id, scanned[0])  # no-op
    assert [t.id for t in playlists.playlist_tracks(conn, p.id)] == [scanned[2], scanned[0]]
    playlists.remove_track(conn, p.id, scanned[2])
    assert [t.id for t in playlists.playlist_tracks(conn, p.id)] == [scanned[0]]
    pos = conn.execute(
        "SELECT position FROM playlist_track WHERE playlist_id = ?", (p.id,)
    ).fetchone()[0]
    assert pos == 0
    with pytest.raises(playlists.PlaylistExists):
        playlists.add_playlist(conn, "jungle set")


def test_export_m3u8(conn, collection, scanned):
    p = playlists.add_playlist(conn, "Jungle Set!")
    playlists.add_track(conn, p.id, scanned[0])
    out = playlists.export_m3u8(conn, collection, p.id)
    assert out == collection / "playlists" / "jungle-set.m3u8"
    lines = out.read_text().splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1].startswith("#EXTINF:3,Astrix - Deep Jungle Walk")
    assert lines[2] == "../psy/Astrix - Deep Jungle Walk.flac"
```

Append to `tests/test_cli.py`:
```python
def test_playlist_cli(collection):
    cfg = _cfg(collection.parent, collection)
    runner.invoke(app, ["--config", cfg, "scan"])
    import json

    tracks = json.loads(runner.invoke(app, ["--config", cfg, "--json", "ls", "psy"]).output)
    assert runner.invoke(app, ["--config", cfg, "playlist", "add", "set1"]).exit_code == 0
    assert (
        runner.invoke(
            app, ["--config", cfg, "playlist", "add-track", "set1", tracks[0]["id"]]
        ).exit_code
        == 0
    )
    result = runner.invoke(app, ["--config", cfg, "--json", "playlist", "export", "set1"])
    assert result.exit_code == 0 and (collection / "playlists" / "set1.m3u8").exists()
```
(`uat ls` is added in Task 13; run this test after that task.)

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_playlists.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.library.playlists`)

- [x] **Step 3: Implement playlists + CLI**

`unalphathet/library/playlists.py`:
```python
"""Playlists: ordered, cross-crate. SQLite is canonical; .m3u8 files are exported for other software."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
    nxt = conn.execute(
        "SELECT COALESCE(MAX(position) + 1, 0) FROM playlist_track WHERE playlist_id = ?",
        (playlist_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO playlist_track(playlist_id, track_id, position) VALUES (?, ?, ?)",
        (playlist_id, track_id, nxt),
    )


def remove_track(conn: sqlite3.Connection, playlist_id: int, track_id: str) -> None:
    conn.execute("BEGIN")
    conn.execute(
        "DELETE FROM playlist_track WHERE playlist_id = ? AND track_id = ?", (playlist_id, track_id)
    )
    rows = conn.execute(
        "SELECT track_id FROM playlist_track WHERE playlist_id = ? ORDER BY position",
        (playlist_id,),
    ).fetchall()
    for pos, r in enumerate(rows):
        conn.execute(
            "UPDATE playlist_track SET position = ? WHERE playlist_id = ? AND track_id = ?",
            (pos, playlist_id, r["track_id"]),
        )
    conn.execute("COMMIT")


def playlist_tracks(conn: sqlite3.Connection, playlist_id: int) -> list[Track]:
    rows = conn.execute(
        "SELECT t.* FROM track t JOIN playlist_track pt ON pt.track_id = t.id "
        "WHERE pt.playlist_id = ? ORDER BY pt.position",
        (playlist_id,),
    ).fetchall()
    return [row_to_track(r) for r in rows]


def export_m3u8(conn: sqlite3.Connection, root: Path, playlist_id: int) -> Path:
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
```

Add to `unalphathet/cli.py`:
```python
from unalphathet.library import playlists as _playlists

playlist_app = typer.Typer(help="Playlists (cross-crate, ordered).")
app.add_typer(playlist_app, name="playlist")


def _playlist_or_die(conn, name: str):
    p = _playlists.get_playlist(conn, name)
    if p is None:
        typer.echo(f"no such playlist: {name}", err=True)
        raise typer.Exit(code=1)
    return p


@playlist_app.command("ls")
def playlist_ls(ctx: typer.Context) -> None:
    """List playlists."""
    conn, _, _ = open_ctx(ctx)
    rows = [p.__dict__ for p in _playlists.list_playlists(conn)]
    emit(ctx, rows, lambda ps: "\n".join(p["name"] for p in ps) or "(no playlists)")


@playlist_app.command("add")
def playlist_add(ctx: typer.Context, name: str) -> None:
    """Create a playlist."""
    conn, _, _ = open_ctx(ctx)
    try:
        p = _playlists.add_playlist(conn, name)
    except _playlists.PlaylistExists:
        typer.echo(f"playlist already exists: {name}", err=True)
        raise typer.Exit(code=1)
    emit(ctx, p.__dict__, lambda d: f"created playlist {d['name']}")


@playlist_app.command("add-track")
def playlist_add_track(ctx: typer.Context, name: str, track_id: str) -> None:
    """Append a track (by id) to a playlist."""
    conn, _, _ = open_ctx(ctx)
    p = _playlist_or_die(conn, name)
    _playlists.add_track(conn, p.id, track_id)
    emit(
        ctx,
        {"playlist": p.name, "track_id": track_id},
        lambda d: f"added {d['track_id']} to {d['playlist']}",
    )


@playlist_app.command("export")
def playlist_export(ctx: typer.Context, name: str) -> None:
    """Write playlists/<name>.m3u8."""
    conn, root, _ = open_ctx(ctx)
    p = _playlist_or_die(conn, name)
    out = _playlists.export_m3u8(conn, root, p.id)
    emit(ctx, {"path": str(out)}, lambda d: d["path"])
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_playlists.py -v`
Expected: PASS (the CLI test waits for Task 13)

- [x] **Step 5: Commit**

```bash
git add unalphathet/library/playlists.py unalphathet/cli.py tests/test_playlists.py tests/test_cli.py
git commit -m "feat(library): playlists with m3u8 export, uat playlist commands

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: Query helpers and `uat ls`

**Files:**
- Create: `unalphathet/library/query.py`, `tests/test_query.py`
- Modify: `unalphathet/cli.py`

**Interfaces:**
- Produces:
  - `query.get_track(conn, track_id: str) -> Track | None`
  - `query.tracks_in_crate(conn, crate_id: int, include_missing: bool = False) -> list[Track]` — ordered by artist, title
  - `query.tracks_with_vibe(conn, vibe_id: int) -> list[Track]`
  - `query.search(conn, text: str, limit: int = 200) -> list[Track]` — case-insensitive substring over title/artist/album
  - CLI: `uat ls CRATE[/VIBE]`

- [x] **Step 1: Write failing tests**

`tests/test_query.py`:
```python
import pytest

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import crates, query, vibes


@pytest.fixture
def scanned(conn, collection):
    scan.scan(conn, collection, Config(collection_root=collection))
    return conn


def test_tracks_in_crate_and_missing(scanned, collection):
    psy = crates.get_crate(scanned, "psy")
    ts = query.tracks_in_crate(scanned, psy.id)
    assert [t.title for t in ts] == ["Deep Jungle Walk", "Heart"]
    scanned.execute("UPDATE track SET state='missing' WHERE title='Heart'")
    assert [t.title for t in query.tracks_in_crate(scanned, psy.id)] == ["Deep Jungle Walk"]
    assert len(query.tracks_in_crate(scanned, psy.id, include_missing=True)) == 2


def test_tracks_with_vibe(scanned):
    psy = crates.get_crate(scanned, "psy")
    night = vibes.add_vibe(scanned, psy.id, "night")
    t = query.tracks_in_crate(scanned, psy.id)[0]
    vibes.set_track_vibes(scanned, t.id, [night.id])
    assert [x.id for x in query.tracks_with_vibe(scanned, night.id)] == [t.id]


def test_search(scanned):
    assert [t.title for t in query.search(scanned, "astrix")] == ["Deep Jungle Walk", "Heart"]
    assert [t.title for t in query.search(scanned, "FLOOR")] == ["Floorshow"]
    assert query.search(scanned, "zzz") == []


def test_get_track(scanned):
    t = query.search(scanned, "Heart")[0]
    assert query.get_track(scanned, t.id) == t
    assert query.get_track(scanned, "nope") is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_query.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.library.query`)

- [x] **Step 3: Implement query + `uat ls`**

`unalphathet/library/query.py`:
```python
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
        f"SELECT t.* FROM track t JOIN track_vibe tv ON tv.track_id = t.id "
        f"WHERE tv.vibe_id = ? AND t.state != 'missing' {ORDER}",
        (vibe_id,),
    ).fetchall()
    return [row_to_track(r) for r in rows]


def search(conn: sqlite3.Connection, text: str, limit: int = 200) -> list[Track]:
    like = f"%{text}%"
    rows = conn.execute(
        f"SELECT * FROM track WHERE state != 'missing' AND "
        f"(title LIKE ? OR artist LIKE ? OR album LIKE ?) {ORDER} LIMIT ?",
        (like, like, like, limit),
    ).fetchall()
    return [row_to_track(r) for r in rows]
```

Add to `unalphathet/cli.py`:
```python
from unalphathet.library import query as _query


@app.command("ls")
def ls(ctx: typer.Context, where: str = typer.Argument(..., help="CRATE or CRATE/VIBE")) -> None:
    """List tracks in a crate or a crate/vibe."""
    conn, _, _ = open_ctx(ctx)
    crate_name, _, vibe_name = where.partition("/")
    c = _crate_or_die(conn, crate_name)
    if vibe_name:
        v = _vibes.get_vibe(conn, c.id, vibe_name)
        if v is None:
            typer.echo(f"no such vibe: {where}", err=True)
            raise typer.Exit(code=1)
        tracks = _query.tracks_with_vibe(conn, v.id)
    else:
        tracks = _query.tracks_in_crate(conn, c.id)
    emit(
        ctx,
        [t.__dict__ for t in tracks],
        lambda ts: (
            "\n".join(
                f"{t['id'][:8]}  {(t['artist'] or '?')[:24]:<24} {(t['title'] or '?')[:40]:<40} "
                f"{'' if t['bpm'] is None else f'{t["bpm"]:g}':>6} {t['key'] or '':<3} {t['codec']}"
                for t in ts
            )
            or "(no tracks)"
        ),
    )
```

- [x] **Step 4: Run all tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS, including `test_playlist_cli` from Task 12.

- [x] **Step 5: Commit**

```bash
git add unalphathet/library/query.py unalphathet/cli.py tests/test_query.py
git commit -m "feat(library): track queries and uat ls

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 14: Player interface — NullPlayer and MpvPlayer

**Files:**
- Create: `unalphathet/tui/__init__.py`, `unalphathet/tui/player.py`, `tests/test_player.py`

**Interfaces:**
- Produces:
  - `player.Player` Protocol: `load(path: Path, start_fraction: float = 0.0) -> None`, `toggle() -> None`, `seek(seconds: float) -> None` (relative), `seek_to(fraction: float) -> None`, `position() -> tuple[float, float]` (`(pos_s, duration_s)`), `paused -> bool`, `current -> Path | None`, `stop() -> None`, `close() -> None`
  - `player.NullPlayer` — in-memory; records `calls: list[tuple]`
  - `player.MpvPlayer(extra_args: Sequence[str] = ())` — spawns `mpv --idle=yes --no-video --input-ipc-server=<tmp>/mpv.sock --really-quiet <extra_args>`; JSON IPC over a unix socket; raises `PlayerError` if mpv is missing.

- [x] **Step 1: Write failing tests**

`tests/test_player.py`:
```python
import shutil
import time

import pytest

from unalphathet.tui.player import MpvPlayer, NullPlayer, PlayerError

from .conftest import make_audio


def test_null_player_records_and_tracks_state(tmp_path):
    p = NullPlayer()
    p.load(tmp_path / "a.flac", start_fraction=0.25)
    assert p.current == tmp_path / "a.flac" and p.paused is False
    p.toggle()
    assert p.paused is True
    p.seek(10)
    p.seek_to(0.5)
    p.stop()
    assert p.current is None
    assert [c[0] for c in p.calls] == ["load", "toggle", "seek", "seek_to", "stop"]


@pytest.fixture
def mpv(ffmpeg):
    if not shutil.which("mpv"):
        pytest.skip("mpv not installed")
    p = MpvPlayer(extra_args=["--ao=null"])
    yield p
    p.close()


def test_mpv_load_position_toggle_seek(tmp_path, mpv):
    a = make_audio(tmp_path / "a.flac", seconds=5)
    mpv.load(a, start_fraction=0.5)
    deadline = time.time() + 3
    while time.time() < deadline:
        pos, dur = mpv.position()
        if dur > 0:
            break
        time.sleep(0.05)
    assert 4.9 <= dur <= 5.1
    assert pos >= 2.0  # started at 50 %
    assert mpv.paused is False
    mpv.toggle()
    assert mpv.paused is True
    mpv.seek_to(0.0)
    time.sleep(0.1)
    assert mpv.position()[0] < 1.0
    mpv.seek(2)
    time.sleep(0.1)
    assert mpv.position()[0] >= 1.5
    mpv.stop()
    assert mpv.current is None


def test_mpv_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(PlayerError):
        MpvPlayer()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_player.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.tui`)

- [x] **Step 3: Implement the players**

`unalphathet/tui/__init__.py`: empty.

`unalphathet/tui/player.py`:
```python
"""Preview playback behind a small Protocol so the TUI (and a future GTK app) never talk to mpv directly."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class PlayerError(RuntimeError):
    pass


class Player(Protocol):
    @property
    def current(self) -> Path | None: ...
    @property
    def paused(self) -> bool: ...
    def load(self, path: Path, start_fraction: float = 0.0) -> None: ...
    def toggle(self) -> None: ...
    def seek(self, seconds: float) -> None: ...
    def seek_to(self, fraction: float) -> None: ...
    def position(self) -> tuple[float, float]: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class NullPlayer:
    """Does nothing, remembers everything. For tests and `--no-audio`."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._current: Path | None = None
        self._paused = False

    @property
    def current(self) -> Path | None:
        return self._current

    @property
    def paused(self) -> bool:
        return self._paused

    def load(self, path: Path, start_fraction: float = 0.0) -> None:
        self.calls.append(("load", path, start_fraction))
        self._current, self._paused = path, False

    def toggle(self) -> None:
        self.calls.append(("toggle",))
        self._paused = not self._paused

    def seek(self, seconds: float) -> None:
        self.calls.append(("seek", seconds))

    def seek_to(self, fraction: float) -> None:
        self.calls.append(("seek_to", fraction))

    def position(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def stop(self) -> None:
        self.calls.append(("stop",))
        self._current = None

    def close(self) -> None:
        self.stop()


class MpvPlayer:
    """mpv in idle mode, driven over its JSON IPC socket."""

    def __init__(self, extra_args: Sequence[str] = ()) -> None:
        exe = shutil.which("mpv")
        if not exe:
            raise PlayerError("mpv not found in PATH")
        self._dir = tempfile.mkdtemp(prefix="uat-mpv-")
        self._sock_path = os.path.join(self._dir, "mpv.sock")
        self._proc = subprocess.Popen(
            [
                exe,
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                "--really-quiet",
                f"--input-ipc-server={self._sock_path}",
                *extra_args,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + 5
        while True:
            try:
                self._sock.connect(self._sock_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.time() > deadline or self._proc.poll() is not None:
                    raise PlayerError("mpv did not open its IPC socket")
                time.sleep(0.02)
        self._sock.settimeout(2.0)
        self._buf = b""
        self._req = 0
        self._current: Path | None = None

    # --- IPC plumbing -------------------------------------------------------------
    def _send(self, *command) -> dict:
        self._req += 1
        rid = self._req
        self._sock.sendall(
            json.dumps({"command": list(command), "request_id": rid}).encode() + b"\n"
        )
        while True:
            while b"\n" not in self._buf:
                chunk = self._sock.recv(65536)
                if not chunk:
                    raise PlayerError("mpv closed the IPC socket")
                self._buf += chunk
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("request_id") == rid:
                if msg.get("error") not in (None, "success"):
                    raise PlayerError(f"mpv: {msg['error']} for {command}")
                return msg
            # else: an event or someone else's reply; drop it

    def _get(self, prop: str, default=None):
        try:
            return self._send("get_property", prop).get("data", default)
        except PlayerError:
            return default

    # --- Player -------------------------------------------------------------------
    @property
    def current(self) -> Path | None:
        return self._current

    @property
    def paused(self) -> bool:
        return bool(self._get("pause", False))

    def load(self, path: Path, start_fraction: float = 0.0) -> None:
        start = f"start={max(0.0, min(start_fraction, 0.99)) * 100:.1f}%"
        self._send("loadfile", str(path), "replace", -1, start)
        self._send("set_property", "pause", False)
        self._current = path

    def toggle(self) -> None:
        self._send("cycle", "pause")

    def seek(self, seconds: float) -> None:
        self._send("seek", seconds, "relative")

    def seek_to(self, fraction: float) -> None:
        self._send("seek", max(0.0, min(fraction, 1.0)) * 100, "absolute-percent")

    def position(self) -> tuple[float, float]:
        return float(self._get("time-pos", 0.0) or 0.0), float(self._get("duration", 0.0) or 0.0)

    def stop(self) -> None:
        try:
            self._send("stop")
        except PlayerError:
            pass
        self._current = None

    def close(self) -> None:
        try:
            self._send("quit")
        except (PlayerError, OSError):
            pass
        try:
            self._sock.close()
        finally:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            shutil.rmtree(self._dir, ignore_errors=True)
```

Note the `loadfile` signature: mpv ≥ 0.38 takes `loadfile <url> [<flags> [<index> [<options>]]]`; older builds took `loadfile <url> [<flags> [<options>]]`. If `test_mpv_load_position_toggle_seek` errors with "invalid parameter", drop the `-1` argument. Check with `mpv --version`.

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_player.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add unalphathet/tui tests/test_player.py
git commit -m "feat(tui): Player protocol with mpv JSON-IPC and null implementations

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Browse screen and `uat tui`

**Files:**
- Create: `unalphathet/tui/app.py`, `unalphathet/tui/screens/__init__.py`, `unalphathet/tui/screens/browse.py`, `tests/test_browse.py`
- Modify: `unalphathet/cli.py`

**Interfaces:**
- Consumes: `crates.list_crates`, `vibes.list_vibes`, `playlists.list_playlists/playlist_tracks`, `query.*`, `Player`.
- Produces:
  - `app.UatApp(conn, root: Path, config: Config, player: Player)`; `App.run()` for real use
  - `browse.BrowseScreen` with: `Tree` (`#nav`, node data = `("crate", id) | ("vibe", id) | ("playlist", id)`), `DataTable` (`#tracks`, row key = track id, columns Artist/Title/BPM/Key/Len/Fmt), `Static` (`#status`).
  - Keys: `space` play/pause (loads highlighted track at `config.preview_start_at` if nothing loaded), `left`/`right` ±10 s, `g` hop 25→50→75 %, `s` stop, `q` quit, `r` rescan (runs `scan.scan` in a worker thread, then reloads).
  - CLI: `uat tui [--no-audio]`

- [x] **Step 1: Write failing tests**

`tests/test_browse.py`:
```python
from textual.widgets import DataTable, Tree

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import crates, playlists, vibes
from unalphathet.tui.app import UatApp
from unalphathet.tui.player import NullPlayer


def _app(conn, collection, player=None):
    cfg = Config(collection_root=collection, preview_start_at=0.25)
    scan.scan(conn, collection, cfg)
    return UatApp(conn, collection, cfg, player or NullPlayer())


async def test_tree_lists_crates_vibes_playlists(conn, collection):
    psy = crates.get_crate(conn, "psy")
    vibes.add_vibe(conn, psy.id, "night")
    playlists.add_playlist(conn, "set1")
    app = _app(conn, collection)
    async with app.run_test() as pilot:
        tree = app.screen.query_one("#nav", Tree)
        labels = [str(n.label) for n in tree.root.children]
        assert labels == ["psy", "techno", "Playlists"]
        psy_node = tree.root.children[0]
        assert [str(n.label) for n in psy_node.children] == ["night"]
        assert [str(n.label) for n in tree.root.children[2].children] == ["set1"]
        await pilot.pause()


async def test_selecting_crate_fills_table(conn, collection):
    app = _app(conn, collection)
    async with app.run_test() as pilot:
        table = app.screen.query_one("#tracks", DataTable)
        assert table.row_count == 0
        await pilot.press("down", "enter")  # first crate: psy
        await pilot.pause()
        assert table.row_count == 2
        await pilot.press("down", "enter")  # techno
        await pilot.pause()
        assert table.row_count == 1


async def test_space_loads_highlighted_track_then_toggles(conn, collection):
    player = NullPlayer()
    app = _app(conn, collection, player)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.press("tab")  # focus the table
        await pilot.press("space")
        await pilot.pause()
        assert player.calls and player.calls[0][0] == "load"
        assert player.calls[0][2] == 0.25
        assert player.current.name == "Astrix - Deep Jungle Walk.flac"
        await pilot.press("space")
        await pilot.pause()
        assert player.paused is True
        await pilot.press("s")
        await pilot.pause()
        assert player.current is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_browse.py -v`
Expected: FAIL (`ModuleNotFoundError: unalphathet.tui.app`)

- [x] **Step 3: Implement the app and browse screen**

`unalphathet/tui/screens/__init__.py`: empty.

`unalphathet/tui/screens/browse.py`:
```python
"""Browse screen: crate/vibe/playlist tree on the left, tracks on the right, player bar below."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static, Tree

from unalphathet.core import scan
from unalphathet.core.models import Track
from unalphathet.library import crates, playlists, query, vibes

NodeData = tuple[str, int] | None  # ("crate"|"vibe"|"playlist", id)
HOPS = (0.25, 0.5, 0.75)


class BrowseScreen(Screen):
    BINDINGS = [
        Binding("space", "toggle", "Play/Pause"),
        Binding("s", "stop", "Stop"),
        Binding("left", "seek(-10)", "-10s"),
        Binding("right", "seek(10)", "+10s"),
        Binding("g", "hop", "25/50/75%"),
        Binding("r", "rescan", "Rescan"),
        Binding("q", "app.quit", "Quit"),
    ]
    DEFAULT_CSS = """
    BrowseScreen Horizontal { height: 1fr; }
    #nav { width: 32; border-right: solid $primary; }
    #tracks { width: 1fr; }
    #status { height: 1; background: $panel; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._tracks: dict[str, Track] = {}
        self._highlighted: str | None = None
        self._hop = 0

    # --- layout -------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Tree("Collection", id="nav")
            yield DataTable(id="tracks", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tracks", DataTable)
        table.add_columns("Artist", "Title", "BPM", "Key", "Len", "Fmt")
        self.reload_tree()
        self.set_interval(0.5, self.refresh_status)

    # --- data ---------------------------------------------------------------------
    def reload_tree(self) -> None:
        conn = self.app.conn
        tree = self.query_one("#nav", Tree)
        tree.clear()
        tree.root.expand()
        for c in crates.list_crates(conn):
            node = tree.root.add(c.dir_name, data=("crate", c.id))
            for v in vibes.list_vibes(conn, c.id):
                node.add_leaf(v.name, data=("vibe", v.id))
        pl = tree.root.add("Playlists", data=None)
        for p in playlists.list_playlists(conn):
            pl.add_leaf(p.name, data=("playlist", p.id))

    def load_tracks(self, data: NodeData) -> None:
        conn = self.app.conn
        if data is None:
            tracks: list[Track] = []
        else:
            kind, ident = data
            tracks = {
                "crate": lambda: query.tracks_in_crate(conn, ident),
                "vibe": lambda: query.tracks_with_vibe(conn, ident),
                "playlist": lambda: playlists.playlist_tracks(conn, ident),
            }[kind]()
        table = self.query_one("#tracks", DataTable)
        table.clear()
        self._tracks = {t.id: t for t in tracks}
        self._highlighted = tracks[0].id if tracks else None
        for t in tracks:
            table.add_row(
                t.artist or "?",
                t.title or "?",
                "" if t.bpm is None else f"{t.bpm:g}",
                t.key or "",
                t.duration_str,
                t.codec,
                key=t.id,
            )

    # --- events -------------------------------------------------------------------
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        self.load_tracks(event.node.data)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._highlighted = event.row_key.value if event.row_key else None

    # --- player actions -----------------------------------------------------------
    def _highlighted_path(self) -> Path | None:
        t = self._tracks.get(self._highlighted or "")
        return self.app.root / t.rel_path if t else None

    def action_toggle(self) -> None:
        player = self.app.player
        if player.current is None:
            path = self._highlighted_path()
            if path is None:
                return
            self._hop = 0
            player.load(path, start_fraction=self.app.config.preview_start_at)
        else:
            player.toggle()
        self.refresh_status()

    def action_stop(self) -> None:
        self.app.player.stop()
        self.refresh_status()

    def action_seek(self, seconds: float) -> None:
        if self.app.player.current is not None:
            self.app.player.seek(seconds)

    def action_hop(self) -> None:
        if self.app.player.current is not None:
            self._hop = (self._hop + 1) % len(HOPS)
            self.app.player.seek_to(HOPS[self._hop])

    def refresh_status(self) -> None:
        player = self.app.player
        status = self.query_one("#status", Static)
        if player.current is None:
            status.update(f"{len(self._tracks)} tracks · space: preview highlighted")
            return
        pos, dur = player.position()
        icon = "⏸" if player.paused else "▶"
        t = next(
            (x for x in self._tracks.values() if self.app.root / x.rel_path == player.current), None
        )
        label = t.display if t else player.current.name
        status.update(
            f"{icon} {label}   {int(pos) // 60}:{int(pos) % 60:02d} / {int(dur) // 60}:{int(dur) % 60:02d}"
        )

    # --- rescan -------------------------------------------------------------------
    def action_rescan(self) -> None:
        self.query_one("#status", Static).update("scanning…")
        self._rescan_worker()

    @work(thread=True, exclusive=True)
    def _rescan_worker(self) -> None:
        # sqlite connections are per-thread by default; open a fresh one for the worker
        from unalphathet.core import db

        conn = db.open_library(self.app.root)
        try:
            report = scan.scan(conn, self.app.root, self.app.config)
        finally:
            conn.close()
        self.app.call_from_thread(self._after_rescan, report)

    def _after_rescan(self, report: scan.ScanReport) -> None:
        self.reload_tree()
        self.query_one("#status", Static).update(
            f"scan: +{report.added} moved {report.moved} missing {report.missing} "
            f"errors {len(report.errors)}"
        )
```

`unalphathet/tui/app.py`:
```python
"""The Textual application. Holds the shared connection, root, config and player."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import App

from unalphathet.config import Config
from unalphathet.tui.player import Player
from unalphathet.tui.screens.browse import BrowseScreen


class UatApp(App[None]):
    TITLE = "UnAlphaThet"

    def __init__(
        self, conn: sqlite3.Connection, root: Path, config: Config, player: Player
    ) -> None:
        super().__init__()
        self.conn = conn
        self.root = root
        self.config = config
        self.player = player

    def on_mount(self) -> None:
        self.push_screen(BrowseScreen())

    async def on_unmount(self) -> None:
        self.player.close()
```

Add to `unalphathet/cli.py`:
```python
@app.command()
def tui(
    ctx: typer.Context,
    no_audio: bool = typer.Option(False, "--no-audio", help="Disable preview playback."),
) -> None:
    """Open the browse screen."""
    from unalphathet.tui.app import UatApp
    from unalphathet.tui.player import MpvPlayer, NullPlayer, PlayerError

    conn, root, config = open_ctx(ctx)
    player = NullPlayer()
    if not no_audio:
        try:
            player = MpvPlayer(extra_args=config.mpv_args)
        except PlayerError as exc:
            typer.echo(f"preview disabled: {exc}", err=True)
    UatApp(conn, root, config, player).run()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_browse.py -v`
Expected: PASS. If `test_selecting_crate_fills_table` gets 0 rows: the Tree needs focus for `down`/`enter` — add `self.query_one("#nav", Tree).focus()` at the end of `on_mount`. If `tab` in the third test doesn't reach the table, replace it with `app.screen.query_one("#tracks", DataTable).focus()` in the test.

- [x] **Step 5: Try it for real**

```bash
uv run uat --config /tmp/uat-dev.toml init --root /tmp/uat-coll
uv run python -c "
from pathlib import Path; from tests.conftest import make_audio
make_audio(Path('/tmp/uat-coll/psy/Astrix - Deep Jungle Walk.flac'), seed=11, title='Deep Jungle Walk', artist='Astrix')
make_audio(Path('/tmp/uat-coll/techno/Surgeon - Floorshow.flac'), seed=13, title='Floorshow', artist='Surgeon')
"
uv run uat --config /tmp/uat-dev.toml scan
uv run uat --config /tmp/uat-dev.toml tui --no-audio     # inside the container: no audio device
```
Navigate: `down`, `enter`, `tab`, `space`, `q`. In the container mpv has no output device; on the host (after the pipewire socket is mounted) drop `--no-audio`.

- [x] **Step 6: Lint, full test run, commit**

```bash
uv run ruff check . && uv run ruff format --check . || uv run ruff format .
uv run pytest -q
git add unalphathet/tui unalphathet/cli.py tests/test_browse.py
git commit -m "feat(tui): browse screen with tree, track table, preview bar and uat tui

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage (Phase 0 + 1 only):**
- Bootstrap: uv, pyproject, deps, config loader, schema + migrations, `uat scan`, `uat doctor` — Tasks 1–4, 11. ✔
- Crates/vibes/playlists CRUD — Tasks 9, 10, 12. ✔
- Ids + fingerprinting — Task 8; stamping + recovery — Task 11. ✔
- Tag read/write-back — Tasks 6, 7; conflict rule — Task 11. ✔
- Browse screen + mpv preview behind `Player` — Tasks 14, 15. ✔
- `--json` on every command — `emit()` in Task 2, used everywhere. ✔
- Service layer free of UI imports — `core/`, `library/`, `doctor.py` import neither typer nor textual. ✔
- Not in this plan (by design): inbox pipeline, sorter screens, sticks, analysis, Pioneer export, m3u8 auto-regeneration on playlist change (explicit `export` command for now — the sorter phase wires the automatic regenerate).

**Placeholders:** the only `NotImplementedError` bodies are the three **(Dixi)** slots (`safe_filename`, `set_track_vibes`, `resolve_conflict`); each has fixed tests and a docstring listing the open choices.

**Type consistency:** `Config.preview_start_at` (Task 2) used by browse (Task 15); `TrackTags` field names (Task 6) used by scan (Task 11); `vibes.get_vibe` (Task 10) used by `uat ls` (Task 13); `ScanReport` fields (Task 11) rendered by CLI and TUI; `Player` methods (Task 14) called by browse (Task 15); node data tuples `("crate"|"vibe"|"playlist", id)` consistent between `reload_tree` and `load_tracks`.
