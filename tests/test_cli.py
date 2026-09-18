from typer.testing import CliRunner

from unalphathet import __version__
from unalphathet.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
