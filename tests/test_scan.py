import os
import time
from pathlib import Path

from unalphathet.config import Config
from unalphathet.core import fs, scan
from unalphathet.core.tags import read_tags, write_tags
from unalphathet.library import vibes

from .conftest import make_audio


def _cfg(root: Path, write_back=True) -> Config:
    return Config(collection_root=root, write_back_tags=write_back)


def _tracks(conn):
    return {r["rel_path"]: dict(r) for r in conn.execute("SELECT * FROM track").fetchall()}


def test_first_scan_adds_and_stamps_ids(conn, collection):
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.added == 3 and report.errors == []
    t = _tracks(conn)
    assert set(t) == {
        "psy/Astrix - Deep Jungle Walk.flac",
        "psy/albums/Astrix - Heart.mp3",
        "techno/Surgeon - Floorshow.m4a",
    }
    row = t["psy/Astrix - Deep Jungle Walk.flac"]
    assert row["title"] == "Deep Jungle Walk" and row["state"] == "crated"
    assert row["fingerprint"] and row["audio_hash"] and row["tags_written_at"]
    assert read_tags(collection / "psy/Astrix - Deep Jungle Walk.flac").uat_id == row["id"]
    assert not any(p.startswith("inbox/") for p in t)  # inbox is not scanned


def test_rescan_is_noop(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    report = scan.scan(conn, collection, _cfg(collection))
    assert (report.added, report.moved, report.missing, report.tag_won, report.db_won) == (
        0,
        0,
        0,
        0,
        0,
    )


def test_moved_file_keeps_id(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    before = _tracks(conn)["psy/Astrix - Deep Jungle Walk.flac"]["id"]
    src = collection / "psy/Astrix - Deep Jungle Walk.flac"
    src.rename(collection / "techno" / src.name)
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.moved == 1 and report.added == 0
    t = _tracks(conn)
    assert t["techno/Astrix - Deep Jungle Walk.flac"]["id"] == before
    assert "psy/Astrix - Deep Jungle Walk.flac" not in t


def test_moved_and_stripped_file_recovered_by_fingerprint(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    src = collection / "psy/Astrix - Deep Jungle Walk.flac"
    before = _tracks(conn)[str(src.relative_to(collection))]["id"]
    src.unlink()
    make_audio(collection / "techno" / "renamed.flac", seed=11)  # same audio, no tags, new path
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.moved == 1 and report.added == 0
    row = _tracks(conn)["techno/renamed.flac"]
    assert row["id"] == before
    assert row["title"] == "Deep Jungle Walk"  # DB won over the tagless file...
    back = read_tags(collection / "techno/renamed.flac")
    assert back.uat_id == before and back.title == "Deep Jungle Walk"  # ...and was written back


def test_deleted_file_marked_missing(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    (collection / "techno/Surgeon - Floorshow.m4a").unlink()
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.missing == 1
    assert _tracks(conn)["techno/Surgeon - Floorshow.m4a"]["state"] == "missing"


def test_external_tag_edit_wins_when_newer(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    t = read_tags(p)
    t.title = "Deep Jungle Walk (Edit)"
    t.grouping = "psy/night"
    write_tags(p, t)
    future = time.time() + 5
    os.utime(p, (future, future))
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.tag_won == 1
    row = _tracks(conn)[str(p.relative_to(collection))]
    assert row["title"] == "Deep Jungle Walk (Edit)" and row["state"] == "sorted"
    assert [v.name for v in vibes.track_vibes(conn, row["id"])] == ["night"]


def test_db_wins_when_file_not_newer(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    row = _tracks(conn)[str(p.relative_to(collection))]
    conn.execute("UPDATE track SET title = 'DB Title' WHERE id = ?", (row["id"],))
    past = time.time() - 3600
    os.utime(p, (past, past))
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.db_won == 1
    assert read_tags(p).title == "DB Title"  # written back


def test_scan_without_write_back_touches_no_files(conn, collection):
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    mtime = p.stat().st_mtime
    scan.scan(conn, collection, _cfg(collection, write_back=False))
    assert p.stat().st_mtime == mtime
    assert read_tags(p).uat_id is None
    assert _tracks(conn)[str(p.relative_to(collection))]["id"]


# --- resolve_conflict policy (Dixi, 2026-09-18) ---------------------------------------

DB = {"title": "a"}
TAGS = {"title": "b"}


def test_conflict_newer_file_tags_win():
    assert (
        scan.resolve_conflict(
            "2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z", DB, TAGS
        )
        is scan.Source.TAGS
    )


def test_conflict_older_file_db_wins():
    assert (
        scan.resolve_conflict(
            "2026-01-02T00:00:00.000000Z", "2026-01-01T00:00:00.000000Z", DB, TAGS
        )
        is scan.Source.DB
    )


def test_conflict_never_written_db_wins():
    assert scan.resolve_conflict(None, "2026-01-01T00:00:00.000000Z", DB, TAGS) is scan.Source.DB


def test_conflict_equal_timestamps_db_wins():
    ts = "2026-01-01T00:00:00.000000Z"
    assert scan.resolve_conflict(ts, ts, DB, TAGS) is scan.Source.DB


def test_conflict_future_file_still_counts_as_newer():
    assert (
        scan.resolve_conflict(
            "2026-01-01T00:00:00.000000Z", "2099-01-01T00:00:00.000000Z", DB, TAGS
        )
        is scan.Source.TAGS
    )


# --- advisor-review cases -----------------------------------------------------------


def test_cross_crate_move_drops_old_vibes(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    row = _tracks(conn)[str(p.relative_to(collection))]
    vibes.apply_grouping(conn, row["id"], "psy/night")
    scan.scan(conn, collection, _cfg(collection))  # writes grouping into the file
    assert read_tags(p).grouping == "psy/night"
    p.rename(collection / "techno" / p.name)
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.moved == 1
    moved = _tracks(conn)["techno/Astrix - Deep Jungle Walk.flac"]
    assert vibes.track_vibes(conn, moved["id"]) == []
    assert moved["state"] == "crated"
    assert read_tags(collection / "techno" / p.name).grouping is None  # stale tag stripped


def test_lost_db_keeps_ids_and_files(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    before = {k: v["id"] for k, v in _tracks(conn).items()}
    audio = [p for _, p in fs.iter_crate_files(collection)]
    mtimes = {p: p.stat().st_mtime for p in audio}
    conn.close()
    for f in (collection / ".unalphathet").glob("library.db*"):
        f.unlink()
    from unalphathet.core import db

    fresh = db.open_library(collection)
    report = scan.scan(fresh, collection, _cfg(collection))
    assert report.added == 3
    assert {k: v["id"] for k, v in _tracks(fresh).items()} == before
    assert mtimes == {p: p.stat().st_mtime for p in audio}  # nothing rewritten


def test_lossy_bpm_does_not_rewrite_forever(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "techno/Surgeon - Floorshow.m4a"
    row = _tracks(conn)[str(p.relative_to(collection))]
    conn.execute("UPDATE track SET bpm = 142.5 WHERE id = ?", (row["id"],))
    assert scan.scan(conn, collection, _cfg(collection)).db_won == 1  # written as tmpo=142
    mtime = p.stat().st_mtime
    assert scan.scan(conn, collection, _cfg(collection)).db_won == 0  # converged
    assert p.stat().st_mtime == mtime
    assert _tracks(conn)[str(p.relative_to(collection))]["bpm"] == 142.5  # DB keeps precision


def test_rescan_without_write_back_is_clean(conn, collection):
    cfg = _cfg(collection, write_back=False)
    scan.scan(conn, collection, cfg)
    report = scan.scan(conn, collection, cfg)
    assert report.errors == []
    assert (report.added, report.moved) == (0, 0)


def test_stripped_id_at_same_path_is_restamped(conn, collection):
    scan.scan(conn, collection, _cfg(collection))
    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    before = _tracks(conn)[str(p.relative_to(collection))]["id"]
    write_tags(p, scan.TrackTags(uat_id=None), only=("uat_id",))  # a tagger dropped our frame
    assert read_tags(p).uat_id is None
    report = scan.scan(conn, collection, _cfg(collection))
    assert report.errors == [] and report.moved == 0 and report.added == 0
    assert _tracks(conn)[str(p.relative_to(collection))]["id"] == before
    assert read_tags(p).uat_id == before


def test_first_scan_only_adds_the_id(conn, collection):
    """Real-file finding: multi-valued GENRE and a 4-decimal BPM must survive import untouched."""
    import mutagen

    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    f = mutagen.File(p)
    f["GENRE"] = ["Electronic", "Psytrance", "Progressive Psytrance"]
    f["BPM"] = "94.3468"
    f.save()
    scan.scan(conn, collection, _cfg(collection))
    f = mutagen.File(p)
    assert list(f["GENRE"]) == ["Electronic", "Psytrance", "Progressive Psytrance"]
    assert list(f["BPM"]) == ["94.3468"]
    assert len(f["UAT_ID"]) == 1
    row = _tracks(conn)[str(p.relative_to(collection))]
    assert row["genre"] == "Electronic" and row["bpm"] == 94.3468


def test_db_win_writes_only_changed_fields(conn, collection):
    import mutagen

    p = collection / "psy/Astrix - Deep Jungle Walk.flac"
    f = mutagen.File(p)
    f["GENRE"] = ["Electronic", "Psytrance"]
    f.save()
    scan.scan(conn, collection, _cfg(collection))
    row = _tracks(conn)[str(p.relative_to(collection))]
    conn.execute("UPDATE track SET title = 'DB Title' WHERE id = ?", (row["id"],))
    past = time.time() - 3600
    os.utime(p, (past, past))
    assert scan.scan(conn, collection, _cfg(collection)).db_won == 1
    f = mutagen.File(p)
    assert list(f["TITLE"]) == ["DB Title"]
    assert list(f["GENRE"]) == ["Electronic", "Psytrance"]  # untouched: it didn't differ
