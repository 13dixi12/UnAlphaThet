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
            Check("database", root.is_dir(), f"{db} (created on first scan)", required=False)
        )
    return checks


def all_required_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks if c.required)
