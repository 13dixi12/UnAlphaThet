from unalphathet.core.tags import TrackTags, read_tags

from .conftest import make_audio


def test_read_flac(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.flac", title="Deep", artist="Astrix", album="DJW", genre="Psy")
    t = read_tags(p)
    assert (t.title, t.artist, t.album, t.genre) == ("Deep", "Astrix", "DJW", "Psy")
    assert t.codec == "flac" and t.sample_rate == 44100 and t.bit_depth == 16
    assert 2900 <= t.duration_ms <= 3100
    assert t.audio_md5 and len(t.audio_md5) == 32
    assert t.uat_id is None


def test_read_mp3(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.mp3", title="Heart", artist="Astrix")
    t = read_tags(p)
    assert (t.title, t.artist) == ("Heart", "Astrix")
    assert t.codec == "mp3" and t.bitrate > 0 and t.audio_md5 is None


def test_read_m4a(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.m4a", title="Floorshow", artist="Surgeon")
    t = read_tags(p)
    assert (t.title, t.artist) == ("Floorshow", "Surgeon")
    assert t.codec == "aac"


def test_read_wav_without_tags(tmp_path, ffmpeg):
    p = make_audio(tmp_path / "a.wav")
    t = read_tags(p)
    assert t.title is None and t.codec == "pcm" and t.sample_rate == 44100


def test_tracktags_defaults():
    t = TrackTags()
    assert t.bpm is None and t.energy is None and t.grouping is None


import pytest  # noqa: E402

from unalphathet.core.tags import write_tags  # noqa: E402


@pytest.mark.parametrize("ext", [".flac", ".mp3", ".m4a", ".wav"])
def test_write_then_read_roundtrip(tmp_path, ffmpeg, ext):
    p = make_audio(tmp_path / f"a{ext}", title="Orig", artist="Someone")
    t = read_tags(p)
    # WAV: ffmpeg puts title/artist in the RIFF INFO chunk, which mutagen doesn't read (Phase 2);
    # we write ID3 like rekordbox does, so set them explicitly to make the roundtrip uniform.
    t.title, t.artist = "Orig", "Someone"
    t.uat_id = "0f0e0d0c-0b0a-4908-8706-050403020100"
    t.grouping = "psy/full-on;psy/night"
    t.genre = "psy"
    t.bpm = 142.0
    t.key = "8A"
    t.energy = 4
    write_tags(p, t)
    back = read_tags(p)
    assert back.uat_id == t.uat_id
    assert back.grouping == "psy/full-on;psy/night"
    assert back.genre == "psy"
    assert back.bpm == 142.0
    assert back.key == "8A"
    assert back.energy == 4
    assert back.title == "Orig" and back.artist == "Someone"


@pytest.mark.parametrize("ext", [".flac", ".mp3", ".m4a"])
def test_write_subset_and_removal(tmp_path, ffmpeg, ext):
    p = make_audio(tmp_path / f"a{ext}", title="Orig", artist="Someone", genre="Old")
    write_tags(p, TrackTags(uat_id="abc", genre=None), only=("uat_id", "genre"))
    back = read_tags(p)
    assert back.uat_id == "abc"
    assert back.genre is None
    assert back.title == "Orig"  # untouched fields survive
