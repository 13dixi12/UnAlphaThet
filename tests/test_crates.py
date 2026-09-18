import pytest

from unalphathet.library import crates


def test_add_and_list(conn, collection):
    c = crates.add_crate(conn, collection, "Drum & Bass", hotkey="4", bpm_min=170, bpm_max=180)
    assert c.dir_name == "drum-bass" and (collection / "drum-bass").is_dir()
    assert [x.name for x in crates.list_crates(conn)] == ["Drum & Bass"]
    assert crates.get_crate(conn, "drum-bass") == c


def test_add_duplicate_raises(conn, collection):
    crates.add_crate(conn, collection, "psy")
    with pytest.raises(crates.CrateExists):
        crates.add_crate(conn, collection, "psy")


def test_ensure_is_idempotent(conn, collection):
    a = crates.ensure_crate(conn, collection, "psy")
    b = crates.ensure_crate(conn, collection, "psy")
    assert a == b and (collection / "psy").is_dir()
