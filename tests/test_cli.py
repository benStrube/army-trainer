from typer.testing import CliRunner

from army_trainer.cli import app

runner = CliRunner()


def test_help_lists_stage_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("fetch", "convert", "plan", "render", "qa", "build"):
        assert cmd in result.output


def test_stub_command_exits_nonzero():
    result = runner.invoke(app, ["plan", "AR-600-20"])
    assert result.exit_code == 2
    assert "not implemented" in result.output
