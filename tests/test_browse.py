from textual.widgets import DataTable, Tree

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import crates, playlists, vibes
from unalphathet.tui.app import UatApp
from unalphathet.tui.player import NullPlayer

CFG_KW = {"preview_start_at": 0.25}


def _scanned_app(conn, collection, player=None):
    cfg = Config(collection_root=collection, **CFG_KW)
    scan.scan(conn, collection, cfg)
    return UatApp(conn, collection, cfg, player or NullPlayer())


async def test_tree_lists_crates_vibes_playlists(conn, collection):
    app = _scanned_app(conn, collection)
    psy = crates.get_crate(conn, "psy")
    vibes.add_vibe(conn, psy.id, "night")
    playlists.add_playlist(conn, "set1")
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.screen.query_one("#nav", Tree)
        assert [str(n.label) for n in tree.root.children] == ["psy", "techno", "Playlists"]
        assert [str(n.label) for n in tree.root.children[0].children] == ["night"]
        assert [str(n.label) for n in tree.root.children[2].children] == ["set1"]


async def test_selecting_crate_fills_table(conn, collection):
    app = _scanned_app(conn, collection)
    async with app.run_test() as pilot:
        await pilot.pause()
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
    app = _scanned_app(conn, collection, player)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.press("space")  # tree still focused: priority binding must win
        await pilot.pause()
        assert player.calls and player.calls[0][0] == "load"
        assert player.calls[0][2] == 0.25
        assert player.current.name == "Astrix - Deep Jungle Walk.flac"
        await pilot.press("space")
        await pilot.pause()
        assert player.paused is True
        await pilot.press("right")
        await pilot.pause()
        assert ("seek", 10.0) in player.calls
        await pilot.press("s")
        await pilot.pause()
        assert player.current is None
