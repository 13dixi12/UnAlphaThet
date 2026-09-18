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
