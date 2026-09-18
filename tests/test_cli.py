from typer.testing import CliRunner

from unalphathet import __version__
from unalphathet.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_creates_config_and_collection(tmp_path):
    cfg = tmp_path / "config.toml"
    root = tmp_path / "coll"
    result = runner.invoke(app, ["--config", str(cfg), "init", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert cfg.exists()
    assert (root / "inbox").is_dir()
    assert (root / ".unalphathet").is_dir()


def test_init_json(tmp_path):
    cfg = tmp_path / "config.toml"
    result = runner.invoke(app, ["--config", str(cfg), "--json", "init", "--root", str(tmp_path / "c")])
    assert result.exit_code == 0
    import json

    assert json.loads(result.output)["collection_root"].endswith("/c")


def test_doctor_runs(tmp_path):
    result = runner.invoke(app, ["--config", str(tmp_path / "c.toml"), "--json", "doctor"])
    import json

    data = json.loads(result.output)
    assert any(c["name"] == "ffmpeg" for c in data)


def _cfg(tmp_path, root):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[collection]\nroot = "{root}"\n')
    return str(cfg)


def test_crate_add_and_ls(tmp_path):
    root = tmp_path / "coll"
    root.mkdir()
    cfg = _cfg(tmp_path, root)
    r = runner.invoke(app, ["--config", cfg, "crate", "add", "Psy", "--hotkey", "1", "--bpm", "135-150"])
    assert r.exit_code == 0, r.output
    result = runner.invoke(app, ["--config", cfg, "--json", "crate", "ls"])
    import json

    data = json.loads(result.output)
    assert data[0]["dir_name"] == "psy" and data[0]["bpm_max"] == 150.0
