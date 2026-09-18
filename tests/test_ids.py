import uuid

import pytest

from unalphathet.core import ids

from .conftest import make_audio


def test_new_track_id_is_uuid4():
    u = uuid.UUID(ids.new_track_id())
    assert u.version == 4


def test_fingerprint_same_audio_same_fp(tmp_path, ffmpeg):
    a = make_audio(tmp_path / "a.flac", seed=42)
    b = make_audio(tmp_path / "b.flac", seed=42)
    c = make_audio(tmp_path / "c.flac", seed=7)
    da, fa = ids.fingerprint(a)
    _, fb = ids.fingerprint(b)
    _, fc = ids.fingerprint(c)
    assert isinstance(fa, str) and len(fa) > 10
    assert 2.9 <= da <= 3.1
    assert fa == fb
    assert fa != fc


def test_similarity_survives_reencode_and_separates_tracks(tmp_path, ffmpeg):
    same_flac = ids.fingerprint(make_audio(tmp_path / "a.flac", seed=42))[1]
    same_mp3 = ids.fingerprint(make_audio(tmp_path / "b.mp3", seed=42))[1]
    other = ids.fingerprint(make_audio(tmp_path / "c.flac", seed=7))[1]
    assert ids.similarity(same_flac, same_mp3) > 0.9
    assert ids.similarity(same_flac, other) < 0.8
    assert ids.similarity(same_flac, same_flac) == 1.0


def test_fingerprint_error(tmp_path):
    bad = tmp_path / "x.flac"
    bad.write_bytes(b"not audio")
    with pytest.raises(ids.FingerprintError):
        ids.fingerprint(bad)


def test_audio_md5_flac_only(tmp_path, ffmpeg):
    assert len(ids.audio_md5(make_audio(tmp_path / "a.flac"))) == 32
    assert ids.audio_md5(make_audio(tmp_path / "a.mp3")) is None


def test_is_track_id():
    assert ids.is_track_id(ids.new_track_id())
    assert not ids.is_track_id(None)
    assert not ids.is_track_id("")
    assert not ids.is_track_id("not-a-uuid")
    assert not ids.is_track_id(
        "0f0e0d0c0b0a49088706050403020100"
    )  # hex without dashes: not our format
