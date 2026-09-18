from pathlib import Path

from unalphathet.core import fs


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_is_audio():
    assert fs.is_audio(Path("x/y.FLAC"))
    assert fs.is_audio(Path("a.mp3"))
    assert not fs.is_audio(Path("cover.jpg"))
    assert not fs.is_audio(Path("notes.txt"))


def test_crate_dirs_skips_reserved_and_hidden(tmp_path):
    for d in ("psy", "techno", "inbox", "playlists", ".unalphathet"):
        (tmp_path / d).mkdir()
    _touch(tmp_path / "stray.flac")
    assert [p.name for p in fs.crate_dirs(tmp_path)] == ["psy", "techno"]


def test_iter_crate_files_recursive_sorted_audio_only(tmp_path):
    _touch(tmp_path / "psy" / "b.flac")
    _touch(tmp_path / "psy" / "sub" / "a.mp3")
    _touch(tmp_path / "psy" / "cover.jpg")
    _touch(tmp_path / "inbox" / "new.flac")
    _touch(tmp_path / "techno" / "c.wav")
    got = [(c, p.relative_to(tmp_path).as_posix()) for c, p in fs.iter_crate_files(tmp_path)]
    assert got == [("psy", "psy/b.flac"), ("psy", "psy/sub/a.mp3"), ("techno", "techno/c.wav")]


def test_rel_posix(tmp_path):
    assert fs.rel_posix(tmp_path, tmp_path / "psy" / "x.flac") == "psy/x.flac"


def test_slugify():
    assert fs.slugify("Full On!") == "full-on"
    assert fs.slugify("  Dark   Psy ") == "dark-psy"
    assert fs.slugify("drum&bass") == "drum-bass"
    assert fs.slugify("Ünïcode") == "unicode"


# --- safe_filename: fixed requirements ---

FAT_FORBIDDEN = set('\\/:*?"<>|')


def test_safe_filename_has_no_fat_forbidden_chars():
    name = fs.safe_filename('A/B: "C"', "T*it?le <x>|y", ".flac")
    assert not (set(name) & FAT_FORBIDDEN)
    assert name.endswith(".flac")


def test_safe_filename_shape():
    assert (
        fs.safe_filename("Astrix", "Deep Jungle Walk", ".flac") == "Astrix - Deep Jungle Walk.flac"
    )
    assert fs.safe_filename(None, "Untitled", ".mp3") == "Untitled.mp3"
    assert fs.safe_filename("", "Untitled", ".mp3") == "Untitled.mp3"


def test_safe_filename_length_bound():
    name = fs.safe_filename("A" * 300, "B" * 300, ".flac")
    assert len(name.encode("utf-8")) <= 200
    assert name.endswith(".flac")


def test_safe_filename_never_empty_stem():
    assert fs.safe_filename(None, "???", ".flac") != ".flac"


# --- safe_filename: Dixi's policy (2026-09-18): replace forbidden with '_', ASCII only ---


def test_safe_filename_policy_replacement_and_ascii():
    assert fs.safe_filename("AC/DC", "Ünïcode?", ".flac") == "AC_DC - Unicode_.flac"
    assert fs.safe_filename("Røyksopp", "Straße", ".mp3") == "Royksopp - Strasse.mp3"
    assert (
        fs.safe_filename("Astrix", "Deep   Jungle\tWalk", ".flac")
        == "Astrix - Deep Jungle Walk.flac"
    )


def test_safe_filename_policy_truncates_title_first():
    name = fs.safe_filename("Short Artist", "T" * 300, ".flac")
    assert name.startswith("Short Artist - TTT") and name.endswith(".flac")
    assert len(name.encode()) <= 200


def test_safe_filename_policy_no_trailing_dots_or_spaces():
    assert fs.safe_filename("A.", "B. ", ".flac") == "A. - B.flac"
