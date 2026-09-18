import shutil
import time

import pytest

from unalphathet.tui.player import MpvPlayer, NullPlayer, PlayerError

from .conftest import make_audio


def test_null_player_records_and_tracks_state(tmp_path):
    p = NullPlayer()
    p.load(tmp_path / "a.flac", start_fraction=0.25)
    assert p.current == tmp_path / "a.flac" and p.paused is False
    p.toggle()
    assert p.paused is True
    p.seek(10)
    p.seek_to(0.5)
    p.stop()
    assert p.current is None
    assert [c[0] for c in p.calls] == ["load", "toggle", "seek", "seek_to", "stop"]


@pytest.fixture
def mpv(ffmpeg):
    if not shutil.which("mpv"):
        pytest.skip("mpv not installed")
    p = MpvPlayer(extra_args=["--ao=null"])
    yield p
    p.close()


def _wait_for_duration(player, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos, dur = player.position()
        if dur > 0:
            return pos, dur
        time.sleep(0.05)
    raise AssertionError("mpv never reported a duration")


def test_mpv_load_position_toggle_seek(tmp_path, mpv):
    a = make_audio(tmp_path / "a.flac", seconds=5)
    mpv.load(a, start_fraction=0.5)
    pos, dur = _wait_for_duration(mpv)
    assert 4.9 <= dur <= 5.1
    assert pos >= 2.0  # started at 50 %
    assert mpv.paused is False
    mpv.toggle()
    assert mpv.paused is True
    mpv.seek_to(0.0)
    time.sleep(0.1)
    assert mpv.position()[0] < 1.0
    mpv.seek(2)
    time.sleep(0.1)
    assert mpv.position()[0] >= 1.5
    mpv.stop()
    assert mpv.current is None


def test_mpv_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(PlayerError):
        MpvPlayer()
