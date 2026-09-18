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
