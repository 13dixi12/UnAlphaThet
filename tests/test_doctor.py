from unalphathet import doctor
from unalphathet.config import Config


def test_missing_binary_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    checks = doctor.check_environment(Config(collection_root=tmp_path), tmp_path / "c.toml")
    by_name = {c.name: c for c in checks}
    assert by_name["ffmpeg"].ok is False and by_name["ffmpeg"].required is True
    assert by_name["mpv"].ok is False and by_name["mpv"].required is False
    assert doctor.all_required_ok(checks) is False


def test_all_good(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text("")
    root = tmp_path / "coll"
    (root / ".unalphathet").mkdir(parents=True)
    checks = doctor.check_environment(Config(collection_root=root), cfg_path)
    assert doctor.all_required_ok(checks)
    assert {c.name for c in checks} >= {
        "python",
        "ffmpeg",
        "ffprobe",
        "fpcalc",
        "mpv",
        "config",
        "collection",
        "database",
    }
