from typer.testing import CliRunner

from army_trainer.cli import app

runner = CliRunner()


def test_help_lists_stage_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("fetch", "convert", "plan", "render", "qa", "build", "batch", "check-updates"):
        assert cmd in result.output


def test_build_without_an_input_pdf_fails_and_says_where_to_put_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["build", "AR-600-20"])
    assert result.exit_code == 1
    assert "no_input" in result.output and "data/inbox" in result.output


def test_render_refuses_document_without_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["render", "AR-600-20"])
    assert result.exit_code == 1


def test_convert_refuses_document_without_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["convert", "AR-600-20"])
    assert result.exit_code == 1
    assert "No gate record" in result.output


def test_qa_refuses_document_without_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["qa", "AR-600-20"])
    assert result.exit_code == 1
