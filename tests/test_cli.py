from typer.testing import CliRunner

from army_trainer.cli import app

runner = CliRunner()


def test_help_lists_stage_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("fetch", "convert", "plan", "render", "qa", "build"):
        assert cmd in result.output


def test_stub_command_exits_nonzero():
    result = runner.invoke(app, ["render", "AR-600-20"])
    assert result.exit_code == 2
    assert "not implemented" in result.output


def test_convert_refuses_document_without_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["convert", "AR-600-20"])
    assert result.exit_code == 1
    assert "No gate record" in result.output
