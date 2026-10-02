"""Rule-based QA checks (WP 4.2)."""

import json
from pathlib import Path

import pytest
from test_plan_packet_check import DOC, GLOSSARY, checklist, deck, item

from army_trainer.index.build import build_indexes
from army_trainer.plan.nodes import NodeIndex
from army_trainer.plan.spec import SlideSpec
from army_trainer.qa.rules import (
    check_acronyms,
    check_forms_dates,
    check_readability,
    check_uncited,
    coverage,
    forms_and_dates,
    run_qa,
)
from army_trainer.structure.parse import parse_markdown


@pytest.fixture(scope="module")
def tree():
    return parse_markdown(DOC + GLOSSARY)


PAD = [
    item("Check the message type and location.", ["para-1-2.li1"]),
    item("Verify the date and time.", ["para-1-2.li2"]),
    item("Record any peculiarities.", ["para-1-2.li3"]),
]


def make(*items):
    """A checklist slide (the model wants 3+ items) padded with clean, cited items."""
    return SlideSpec.model_validate(deck([checklist(*items, *PAD[len(items) :])]))


def msgs(findings, check=None):
    return [f.message for f in findings if check in (None, f.check)]


def test_forms_and_dates_are_normalized():
    forms, dates = forms_and_dates(
        "Send DA Form 2028 by 15 March 2024. See FM 3-09 and ATP 3-09.30. Marking may apply."
    )
    assert forms == {"DA FORM 2028", "FM 3-09", "ATP 3-09.30"}
    assert dates == {"15 march 2024"}  # "marking", "may" and the form number aren't dates


def test_form_numbers_and_dates_must_be_in_the_cited_text(tree):
    idx = NodeIndex(tree)
    spec = make(
        item("The FO must locate targets using DA Form 2028 by 4 May 2025.", ["para-1-1"], "must")
    )
    out = check_forms_dates(spec, idx)
    assert {f.level for f in out} == {"error"}
    assert any("DA FORM 2028" in f.message for f in out)
    assert any("4 may 2025" in f.message for f in out)
    ok = make(item("The FO must locate targets.", ["para-1-1"], "must"))
    assert check_forms_dates(ok, idx) == []


def test_cited_content_slides_pass_the_citation_rule():
    assert check_uncited(make(item("Look for the target.", ["para-1-1"]))) == []


def test_readability_flags_hard_statements_and_the_deck_average():
    hard = (
        "Synchronization of multidomain capabilities necessitates comprehensive "
        "interoperability throughout operational environments."
    )
    spec = make(
        item(hard, ["para-1-1"]), item("Check the message type and location.", ["para-1-2"])
    )
    out, stats = check_readability(spec)
    assert any("grade level" in f.message and f.where == "s02.items[0]" for f in out)
    assert stats["statements"] >= 1 and stats["over_limit"] >= 1
    easy, stats = check_readability(
        make(item("Look for the target and tell the team.", ["para-1-1"]))
    )
    assert easy == [] and stats["over_limit"] == 0


def test_readability_neutralizes_glossary_terms_and_scores_per_slide(tree):
    idx = NodeIndex(tree)
    text = "Send the message to the fire direction center (FDC) as soon as you can do it."
    spec = make(item(text, ["para-1-2"]))
    _, plain = check_readability(spec)
    out, stats = check_readability(spec, idx)
    assert stats["slides"]["s02"]["grade"] < plain["slides"]["s02"]["grade"]
    assert stats["slides"]["s02"]["raw_grade"] == plain["slides"]["s02"]["raw_grade"]
    assert stats["scored_slides"] == 1 and stats["passed"] == (stats["slide_share"] >= 0.9)


def test_readability_fails_the_deck_when_too_few_slides_are_at_level():
    hard = (
        "Synchronization of multidomain capabilities necessitates comprehensive "
        "interoperability throughout operational environments."
    )
    out, stats = check_readability(make(item(hard, ["para-1-1"])))
    assert stats["passed"] is False and stats["slides_ok"] == 0
    assert any(f.where == "s02" and "slide grade level" in f.message for f in out)
    assert any(f.where == "deck" and "FAIL" in f.message for f in out)


def test_acronym_must_be_spelled_out_where_first_used(tree):
    idx = NodeIndex(tree)
    bare = make(item("Send the message to the FDC.", ["para-1-2"]))
    assert any("FDC is used before it is spelled out" in m for m in msgs(check_acronyms(bare, idx)))
    spelled = make(item("Send the message to the fire direction center (FDC).", ["para-1-2"]))
    assert check_acronyms(spelled, idx) == []


def test_coverage_counts_cited_mandatory_requirements(tree):
    idx = NodeIndex(tree)
    spec = make(item("The FO must locate targets.", ["para-1-1"], "must"))
    findings, cov = coverage(spec, tree, build_indexes(tree), idx)
    assert cov["mandatory_requirements"] >= 2
    assert (
        0 < cov["cited"] < cov["mandatory_requirements"]
    )  # para 1-1 is cited, the sun caution isn't
    assert any("sun must never" in u["sentence"] for u in cov["uncited"])
    assert all(f.check == "coverage" for f in findings)


def test_run_qa_maps_plan_findings_to_checks(tree, tmp_path):
    slide = checklist(
        item("The FO will locate targets.", ["para-1-1"], "will"),  # source says must
        item("The FO has 30 targets.", ["para-1-1"]),  # number not in source
        *PAD[2:],
    )
    p = tmp_path / "FM-0-00.spec.json"
    p.write_text(json.dumps(deck([slide])))
    report = run_qa(p, tree, build_indexes(tree))
    assert report.by_check("directive") and report.by_check("verbatim")
    assert report.errors and not report.deck_checked
    j = report.to_json()
    assert j["errors"] == len(report.errors) and "coverage" in j


FM_SPEC = Path(__file__).parents[1] / "specs/FM-3-09.spec.json"
FM_TREE = Path(__file__).parents[1] / "data/json/FM-3-09.json"
FM_DECK = Path(__file__).parents[1] / "out/decks/FM-3-09.pptx"


@pytest.mark.skipif(
    not (FM_TREE.exists() and FM_DECK.exists()), reason="run convert, index and render first"
)
def test_fm309_deck_has_no_qa_errors():
    from army_trainer.index.build import JSON_DIR, Indexes
    from army_trainer.structure.models import DocTree

    tree = DocTree.model_validate_json(FM_TREE.read_text())
    idx = Indexes.model_validate_json((JSON_DIR / "FM-3-09.indexes.json").read_text())
    report = run_qa(FM_SPEC, tree, idx, FM_DECK)
    assert report.deck_checked
    assert not report.errors, [str(f) for f in report.errors]


FIXTURE = Path(__file__).parent / "fixtures/spec_fm309_d15.json"
#: D15 reference values (docs/decisions/readability.md), per-slide tolerance +-0.1.
D15_GRADES = {
    "s02": 8.7, "s03": 8.6, "s04": 8.2, "s05": 6.7, "s06": 9.7, "s07": 10.0, "s08": 5.0,
    "s09": 8.2, "s10": 7.2, "s11": 12.0, "s12": 9.4, "s13": 6.4, "s14": 4.7, "s15": 10.6,
    "s16": 8.7, "s17": 12.0, "s18": 9.1, "s19": 9.3, "s20": 6.9, "s21": 8.6, "s22": 12.3,
    "s23": 9.3, "s24": 6.5, "s25": 11.2, "s26": 5.1, "s27": 6.5, "s28": 7.8, "s29": 15.0,
    "s30": 14.6, "s31": 10.1, "s32": 9.0, "s33": 8.9, "s34": 9.1, "s35": 10.0,
}  # fmt: skip


@pytest.mark.skipif(not FM_TREE.exists(), reason="run convert for FM-3-09 first")
def test_readability_matches_the_d15_reference_values():
    from army_trainer.structure.models import DocTree

    idx = NodeIndex(DocTree.model_validate_json(FM_TREE.read_text()))
    spec = SlideSpec.model_validate_json(FIXTURE.read_text())
    _, stats = check_readability(spec, idx)
    assert stats["scored_slides"] == 34 and stats["slides_ok"] == 18
    assert round(stats["slide_share"], 2) == 0.53 and stats["passed"] is False
    assert abs(stats["mean_grade"] - 9.01) <= 0.1
    assert stats["raw_slides_ok"] == 3
    for sid, want in D15_GRADES.items():
        assert abs(stats["slides"][sid]["grade"] - want) <= 0.1, sid
