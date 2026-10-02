"""Fidelity review packet and review check (WP 4.1)."""

import json
from pathlib import Path

import pytest
from test_plan_packet_check import DOC, GLOSSARY, checklist, deck, item

from army_trainer.index.build import build_indexes
from army_trainer.plan.spec import SlideSpec
from army_trainer.qa.review import (
    Review,
    build_review_packet,
    check_review,
    claims,
    rendered,
    sha256_file,
)
from army_trainer.structure.parse import parse_markdown


@pytest.fixture(scope="module")
def tree():
    return parse_markdown(DOC + GLOSSARY)


@pytest.fixture
def spec_path(tmp_path):
    s = checklist(
        item("The FO must locate targets.", ["para-1-1"], "must"),
        item("Check the message type and location.", ["para-1-2.li1"]),
        item("Verify the date and time.", ["para-1-2.li2"]),
    )
    s["notes"] = {"talking_points": [item("Read paragraph 1-2.", ["para-1-2"])]}
    p = tmp_path / "FM-0-00.spec.json"
    p.write_text(json.dumps(deck([s])))
    return p


def test_claims_cover_items_and_notes(spec_path):
    cs = claims(SlideSpec.model_validate_json(spec_path.read_text()))
    ids = [c.id for c in cs]
    assert "s02.items[0]" in ids and "s02.notes.talking_points[0]" in ids
    c = next(c for c in cs if c.id == "s02.items[0]")
    assert c.directive == "must" and c.words == ["must"] and not c.in_notes
    assert next(c for c in cs if c.id.startswith("s02.notes")).in_notes


def test_rendered_checks_each_text_field(spec_path):
    cs = claims(SlideSpec.model_validate_json(spec_path.read_text()))
    c = next(c for c in cs if c.id == "s02.items[0]")
    assert rendered(c, "header the fo must locate targets. footer")  # deck_text() normalizes
    assert not rendered(c, "the fo should locate targets.")


def test_packet_pairs_claims_with_full_cited_text_and_requirements(tree, spec_path, tmp_path):
    out = build_review_packet(spec_path, tree, build_indexes(tree), tmp_path / "pk")
    md = out.read_text()
    assert "### `s02.items[0]`  (directive **must**)" in md
    assert "**[para-1-1]** (para 1-1) The FO is the fire support representative" in md
    assert "must: The FO must locate targets." in md  # requirement sentence row
    data = json.loads((tmp_path / "pk/review_packet.json").read_text())
    assert {d["id"] for d in data} >= {"s02.items[0]", "s02.notes.talking_points[0]"}


def _review(spec_path: Path, **kw) -> Review:
    ids = [c.id for c in claims(SlideSpec.model_validate_json(spec_path.read_text()))]
    base = {
        "pub_id": "FM-0-00",
        "source_sha256": "abc",
        "spec_sha256": sha256_file(spec_path),
        "reviewed_on": "2026-10-02",
        "reviewer": "test",
        "verdicts": {i: "pass" for i in ids},
    }
    return Review.model_validate(base | kw)


def test_clean_review_passes(spec_path):
    r = check_review(_review(spec_path), spec_path)
    assert r.passes and r.counts["pass"] == len(_review(spec_path).verdicts)


def test_stale_incomplete_or_blocking_review_fails(spec_path):
    rev = _review(spec_path)
    spec_path.write_text(spec_path.read_text() + " ")
    assert any("spec changed" in e for e in check_review(rev, spec_path).errors)

    rev = _review(spec_path)
    del rev.verdicts["s02.items[1]"]
    assert any("without a verdict" in e for e in check_review(rev, spec_path).errors)

    v = _review(spec_path).verdicts | {"s02.items[0]": "major"}
    finding = {"claim": "s02.items[0]", "verdict": "major", "category": "unsupported",
               "note": "x"}  # fmt: skip
    r = check_review(_review(spec_path, verdicts=v, findings=[finding]), spec_path)
    assert not r.errors and not r.passes and r.open_blocking[0].claim == "s02.items[0]"

    finding["status"] = "accepted"
    finding["verdict"] = "minor"
    v["s02.items[0]"] = "minor"
    assert check_review(_review(spec_path, verdicts=v, findings=[finding]), spec_path).passes

    v["s02.items[1]"] = "minor"  # non-pass with no finding
    r = check_review(_review(spec_path, verdicts=v, findings=[finding]), spec_path)
    assert any("no open or accepted finding" in e for e in r.errors)


def test_qa_review_packet_refuses_ungated(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from army_trainer.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["qa", "FM-0-00", "--review-packet"])
    assert result.exit_code == 1 and "No gate record" in result.output
