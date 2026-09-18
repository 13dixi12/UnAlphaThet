"""uat — the UnAlphaThet command line. Thin layer over unalphathet.core / .library."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from unalphathet import __version__
from unalphathet.config import Config, default_config_path, load_config, write_default_config
from unalphathet.core import db
from unalphathet.library import crates as _crates

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


def open_ctx(ctx: typer.Context) -> tuple[sqlite3.Connection, Path, Config]:
    """Open (and migrate) the library for the configured collection root."""
    state: CliState = ctx.obj
    root = state.config.collection_root
    if not root.is_dir():
        typer.echo(f"collection root {root} does not exist — run `uat init`", err=True)
        raise typer.Exit(code=1)
    return db.open_library(root), root, state.config


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


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check binaries, config, collection and database."""
    from unalphathet import doctor as _doctor

    state: CliState = ctx.obj
    checks = _doctor.check_environment(state.config, state.config_path)

    def human(cs: list[dict]) -> str:
        lines = []
        for c in cs:
            mark = "ok  " if c["ok"] else ("ERR " if c["required"] else "warn")
            lines.append(f"[{mark}] {c['name']:<11} {c['detail']}")
        return "\n".join(lines)

    emit(ctx, [c.__dict__ for c in checks], human)
    if not _doctor.all_required_ok(checks):
        raise typer.Exit(code=1)


# --- crates ---------------------------------------------------------------------------


def _parse_bpm_range(spec: str | None) -> tuple[float | None, float | None]:
    if not spec:
        return None, None
    lo, _, hi = spec.partition("-")
    return float(lo), float(hi or lo)


crate_app = typer.Typer(help="Crates (directories).")
app.add_typer(crate_app, name="crate")


def _crate_line(c: dict) -> str:
    bpm = "" if c["bpm_min"] is None else f"{c['bpm_min']:g}-{c['bpm_max']:g} bpm"
    return f"{c['hotkey'] or ' '} {c['name']:<20} {c['dir_name']:<20} {bpm}"


@crate_app.command("ls")
def crate_ls(ctx: typer.Context) -> None:
    """List crates."""
    conn, _, _ = open_ctx(ctx)
    rows = [c.__dict__ for c in _crates.list_crates(conn)]
    emit(ctx, rows, lambda cs: "\n".join(_crate_line(c) for c in cs) or "(no crates)")


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
        raise typer.Exit(code=1) from None
    emit(ctx, c.__dict__, lambda d: f"created crate {d['name']} -> {root / d['dir_name']}")
