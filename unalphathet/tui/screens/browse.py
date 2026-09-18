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
    # priority=True: Tree binds space and DataTable binds left/right; playback must win anyway.
    BINDINGS = [
        Binding("space", "toggle", "Play/Pause", priority=True),
        Binding("s", "stop", "Stop", priority=True),
        Binding("left", "seek(-10)", "-10s", priority=True),
        Binding("right", "seek(10)", "+10s", priority=True),
        Binding("g", "hop", "25/50/75%", priority=True),
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

    # --- layout ---------------------------------------------------------------------
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
        self.query_one("#nav", Tree).focus()
        self.set_interval(0.5, self.refresh_status)
        self.refresh_status()

    # --- data -----------------------------------------------------------------------
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
            loaders = {
                "crate": lambda: query.tracks_in_crate(conn, ident),
                "vibe": lambda: query.tracks_with_vibe(conn, ident),
                "playlist": lambda: playlists.playlist_tracks(conn, ident),
            }
            tracks = loaders[kind]()
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
        self.refresh_status()

    # --- events ---------------------------------------------------------------------
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        self.load_tracks(event.node.data)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._highlighted = event.row_key.value if event.row_key else None

    # --- player actions -------------------------------------------------------------
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
            status.update(f"{len(self._tracks)} tracks · space: preview highlighted track")
            return
        pos, dur = player.position()
        icon = "⏸" if player.paused else "▶"
        t = next(
            (x for x in self._tracks.values() if self.app.root / x.rel_path == player.current),
            None,
        )
        label = t.display if t else player.current.name
        status.update(
            f"{icon} {label}   {int(pos) // 60}:{int(pos) % 60:02d} / "
            f"{int(dur) // 60}:{int(dur) % 60:02d}"
        )

    # --- rescan ---------------------------------------------------------------------
    def action_rescan(self) -> None:
        self.query_one("#status", Static).update("scanning…")
        self._rescan_worker()

    @work(thread=True, exclusive=True)
    def _rescan_worker(self) -> None:
        # sqlite connections are per-thread: open a fresh one for the worker
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
