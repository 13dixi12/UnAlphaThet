"""uat — the UnAlphaThet command line. Thin layer over unalphathet.core / .library."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
