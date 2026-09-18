from pathlib import Path

from unalphathet.config import default_config_path, load_config, write_default_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.collection_root == Path("~/music/dj").expanduser()
    assert cfg.write_back_tags is True
    assert cfg.preview_start_at == 0.25


def test_roundtrip(tmp_path):
    p = tmp_path / "config.toml"
    write_default_config(p, tmp_path / "coll")
    cfg = load_config(p)
    assert cfg.collection_root == tmp_path / "coll"
    assert cfg.db_path == tmp_path / "coll" / ".unalphathet" / "library.db"


def test_partial_file_keeps_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[collection]\nroot = "/x"\n[tags]\nwrite_back = false\n')
    cfg = load_config(p)
    assert cfg.collection_root == Path("/x")
    assert cfg.write_back_tags is False
    assert cfg.preview_autoplay is True


def test_default_config_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "unalphathet" / "config.toml"
