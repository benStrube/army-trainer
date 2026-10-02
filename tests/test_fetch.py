import json

import pytest
from pdfutil import make_pdf
from typer.testing import CliRunner

from army_trainer.cli import app
from army_trainer.fetch.fetch import FetchError, download, fetch
from army_trainer.fetch.models import PubMetadata
from army_trainer.llm_guard import GateError, load_gated_metadata, require_gate_pass

FRONT_A = "Headquarters Department of the Army Washington DC 24 July 2020 DISTRIBUTION RESTRICTION: Approved for public release; distribution is unlimited."
FRONT_B = "Headquarters Department of the Army DISTRIBUTION STATEMENT B: Distribution authorized to US Government agencies only"


def test_ingest_passing_pdf(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", [FRONT_A, "page two"])
    raw = tmp_path / "raw"
    meta = fetch("AR 600–20", pdf_path=src, raw_dir=raw)
    assert meta.pub_id == "AR-600-20"
    assert meta.page_count == 2
    assert str(meta.pub_date) == "2020-07-24"
    assert len(meta.sha256) == 64
    assert (raw / "AR-600-20.pdf").exists()
    saved = json.loads((raw / "AR-600-20.meta.json").read_text())
    assert saved["gate"]["status"] == "pass"
    assert load_gated_metadata("AR-600-20", raw).pub_id == "AR-600-20"


def test_rejected_pdf_not_kept_and_guard_refuses(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", [FRONT_B])
    raw = tmp_path / "raw"
    with pytest.raises(FetchError, match="gate rejected"):
        fetch("AR-1-1", pdf_path=src, raw_dir=raw)
    assert not (raw / "AR-1-1.pdf").exists()
    with pytest.raises(GateError):
        load_gated_metadata("AR-1-1", raw)


def test_guard_refuses_missing_record(tmp_path):
    with pytest.raises(GateError, match="No gate record"):
        load_gated_metadata("AR-9-9", tmp_path)


def test_guard_refuses_failed_record(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", [FRONT_B])
    from army_trainer.fetch.fetch import ingest

    meta = ingest(src, "AR-1-1", raw_dir=tmp_path / "raw")
    assert isinstance(meta, PubMetadata)
    with pytest.raises(GateError):
        require_gate_pass(meta)


def test_download_refuses_other_hosts(tmp_path):
    with pytest.raises(FetchError, match="only armypubs"):
        download("https://example.com/x.pdf", tmp_path / "x")


def test_requires_exactly_one_source(tmp_path):
    with pytest.raises(FetchError):
        fetch("AR-1-1", raw_dir=tmp_path)


def test_cli_fetch_rejection_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = make_pdf(tmp_path / "in.pdf", [FRONT_B])
    r = CliRunner().invoke(app, ["fetch", "AR-1-1", "--pdf", str(src)])
    assert r.exit_code == 1


def test_pub_date_prefers_hq_block_over_superseded_date():
    from datetime import date

    from army_trainer.fetch.pdf import parse_pub_date, parse_supersedes

    text = (
        "This publication supersedes FM 3-09, dated 30 April 2020.\n"
        "Headquarters Department of the Army Washington, DC, 12 August 2024"
    )
    assert parse_pub_date(text) == date(2024, 8, 12)
    assert parse_supersedes(text) == "FM 3-09, dated 30 April 2020"
