import pytest

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import playlists


@pytest.fixture
def scanned(conn, collection):
    scan.scan(conn, collection, Config(collection_root=collection))
    return [r["id"] for r in conn.execute("SELECT id FROM track ORDER BY rel_path").fetchall()]


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
