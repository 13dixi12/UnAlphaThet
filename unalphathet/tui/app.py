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
