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
    got = vibes.set_track_vibes(conn, t, [n.id, f.id])
    assert [v.name for v in got] == ["full-on", "night"]
    assert {v.name for v in vibes.track_vibes(conn, t)} == {"night", "full-on"}
    vibes.set_track_vibes(conn, t, [n.id])  # replaces, doesn't append
    assert [v.name for v in vibes.track_vibes(conn, t)] == ["night"]
    assert vibes.set_track_vibes(conn, t, []) == []


def test_foreign_crate_vibe_raises_and_attaches_nothing(conn, two_crates):
    """The invariant. Policy (Dixi, 2026-09-18): strict — raise, leave the track untouched."""
    psy, techno = two_crates
    t = _track(conn, psy.id, "psy/a.flac")
    n = vibes.add_vibe(conn, psy.id, "night")
    f = vibes.add_vibe(conn, psy.id, "full-on")
    hard = vibes.add_vibe(conn, techno.id, "hard")
    vibes.set_track_vibes(conn, t, [n.id])
    with pytest.raises(vibes.VibeCrateMismatch):
        vibes.set_track_vibes(conn, t, [f.id, hard.id])
    assert [v.name for v in vibes.track_vibes(conn, t)] == ["night"]  # unchanged
    with pytest.raises(vibes.VibeCrateMismatch):
        vibes.set_track_vibes(conn, t, [9999])  # unknown vibe id is also a mismatch


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
