import pytest

from unalphathet.config import Config
from unalphathet.core import scan
from unalphathet.library import crates, query, vibes


@pytest.fixture
def scanned(conn, collection):
    scan.scan(conn, collection, Config(collection_root=collection))
    return conn


def test_tracks_in_crate_and_missing(scanned):
    psy = crates.get_crate(scanned, "psy")
    assert [t.title for t in query.tracks_in_crate(scanned, psy.id)] == [
        "Deep Jungle Walk",
        "Heart",
    ]
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
