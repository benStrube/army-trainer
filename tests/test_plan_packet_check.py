"""Planning packet, budget and `plan --check` (WP 2.2)."""

import json
from pathlib import Path

import pytest
from test_classify import DOC

from army_trainer.index.build import build_indexes
from army_trainer.plan.check import check_spec, directive_words
from army_trainer.plan.packet import DECK_MAX, DECK_MIN, build_packet, plan_budget
from army_trainer.structure.models import DocTree
from army_trainer.structure.parse import parse_markdown

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests/fixtures/spec_all_patterns.json"
FM_TREE = ROOT / "data/json/FM-3-09.json"


GLOSSARY = """
# Glossary

## SECTION I – ACRONYMS AND ABBREVIATIONS

| Acronym | Meaning |
| --- | --- |
| FDC | fire direction center |
| FM | field manual |
| FO | forward observer |
| FS | fire support |
"""


@pytest.fixture(scope="module")
def tree():
    return parse_markdown(DOC + GLOSSARY)


def item(text, cite, directive=None):
    return {"text": text, "cite": cite, "directive": directive}


def deck(slides, sha="abc", pub_id="FM-0-00"):
    """Wrap content slides with title / closing and number them."""
    slides = [
        {"pattern": "title", "title": "Test Manual"},
        *slides,
        {
            "pattern": "closing",
            "title": "Read it",
            "items": [item("Read the full manual.", ["para-1-1"])],
        },
    ]
    for i, s in enumerate(slides, 1):
        s["id"] = f"s{i:02d}"
    pub = {"pub_id": pub_id, "short_name": "FM 0-00", "title": "Test", "source_sha256": sha}
    return {"pub": pub, "slides": slides}


def checklist(*items, chapter=None):
    return {"pattern": "checklist", "title": "Checks", "chapter": chapter, "items": list(items)}


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def warnings(findings):
    return [f.message for f in findings if f.level == "warning"]


# ---------------------------------------------------------------- budget and packet


def test_budget_gives_every_chapter_a_divider_and_hits_the_target(tree):
    b = plan_budget(tree, 25)
    (ch,) = b.divisions
    assert ch.kind == "chapter" and ch.content_slides >= 1
    assert b.total == 25
    with pytest.raises(ValueError):
        plan_budget(tree, DECK_MAX + 1)


@pytest.mark.skipif(not FM_TREE.exists(), reason="run convert for FM-3-09 first")
def test_budget_on_fm309_spreads_by_length():
    t = DocTree.model_validate_json(FM_TREE.read_text())
    for target in (DECK_MIN, 34, DECK_MAX):
        b = plan_budget(t, target)
        assert b.total == target
        chapters = [d for d in b.divisions if d.kind == "chapter"]
        assert all(d.content_slides >= 1 for d in chapters)
    b = {d.division: d.content_slides for d in plan_budget(t, 34).divisions}
    assert b["ch-6"] >= b["ch-5"]  # longest chapter gets at least the shortest's share


def test_packet_has_ids_hints_requirements_and_acronyms(tree, tmp_path):
    readme = build_packet(tree, build_indexes(tree), tmp_path, target=25)
    assert "source_sha256" in readme.read_text() and "abc" in readme.read_text()
    ch = (tmp_path / "ch-1.md").read_text()
    assert "## Outline and pattern hints" in ch and "do_dont" in ch  # CAUTION hint
    assert "`[para-1-1]` **1-1.**" in ch  # full text carries citable ids
    assert "`[para-1-2.li1]`" in ch  # list items too
    assert "**must**: The FO must locate targets." in ch  # requirement rows
    assert "`[table-1-1]` **Table 1-1. Titles**" in ch and "| Corps | FSCOORD |" in ch
    data = json.loads((tmp_path / "packet.json").read_text())
    assert data["budget"]["total"] == 25 and data["source_sha256"] == "abc"


def test_packet_cli_refuses_ungated_document(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from army_trainer.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["plan", "FM-0-00", "--packet"])
    assert result.exit_code == 1 and "No gate record" in result.output


# ---------------------------------------------------------------- check


def test_directive_words_keeps_negatives_whole():
    assert directive_words("You will not fire. You MUST check. It may rain.") == [
        "will not",
        "must",
        "may",
    ]


def test_clean_partial_spec_passes(tree):
    spec = deck(
        [
            checklist(
                item("The forward observer must locate targets.", ["para-1-1"], "must"),
                item("Check the message type and location.", ["para-1-2.li1"]),
                item("Verify the date and time.", ["para-1-2.li2"]),
                chapter="ch-1",
            )
        ]
    )
    assert check_spec(spec, tree, partial=True) == []


def test_unknown_cites_and_pub_mismatch_are_errors(tree):
    spec = deck(
        [checklist(item("a", ["para-9-9"]), item("b", ["para-1-1"]), item("c", ["para-1-1"]))],
        sha="other",
    )
    errs = errors(check_spec(spec, tree, partial=True))
    assert any("unknown node 'para-9-9'" in e for e in errs)
    assert any("source_sha256" in e for e in errs)


def test_added_or_changed_directive_is_an_error(tree):
    added = item("Observers will use optics to find the azimuth.", ["para-1-3"])
    wrong = item("The FO will locate targets.", ["para-1-1"], "will")
    soft = item("The FO may want to locate targets.", ["para-1-1"])
    spec = deck([checklist(added, wrong, soft)])
    f = check_spec(spec, tree, partial=True)
    errs = errors(f)
    assert any("says 'will'" in e and "adds or changes" in e for e in errs)
    assert any("directive 'will' is not in the cited text" in e for e in errs)
    assert any("says 'may'" in w for w in warnings(f))  # may/should are warnings


def test_schema_errors_are_reported_not_raised(tree):
    spec = deck([checklist(item("a", ["para-1-1"]))])  # too few items
    errs = errors(check_spec(spec, tree, partial=True))
    assert errs and errs[0].startswith("List should have at least 3")


def test_numbers_containers_and_acronyms(tree):
    spec = deck(
        [
            checklist(
                item("There are 3 types of desert terrain.", ["para-1-4"]),  # "three" is fine
                item("There are 7 types of desert terrain.", ["para-1-4"]),
                item("Section II covers procedures.", ["ch-1.sec-ii"]),
            ),
            {
                "pattern": "acronyms",
                "title": "Acronyms",
                "entries": [
                    {"abbreviation": "XYZ", "meaning": "made up", "cite": ["para-1-1"]},
                    {"abbreviation": "FO", "meaning": "forward observer", "cite": ["para-1-1"]},
                    {"abbreviation": "FDC", "meaning": "fire direction", "cite": ["acr-fdc"]},
                    {"abbreviation": "FS", "meaning": "fire support", "cite": ["para-1-1"]},
                ],
            },
        ]
    )
    f = check_spec(spec, tree, partial=True)
    warns = warnings(f)
    assert any("['7']" in w for w in warns) and not any("['3']" in w for w in warns)
    assert any("cites a whole section" in w for w in warns)
    assert any("'XYZ' is not in the glossary" in e for e in errors(f))
    assert any("FDC meaning differs" in w for w in warns)


def test_deck_level_checks(tree):
    lists = [checklist(*(item("Verify the date.", ["para-1-2.li2"]),) * 3) for _ in range(2)]
    spec = deck(lists)
    errs = errors(check_spec(spec, tree))
    assert any("slides; the budget is 25-40" in e for e in errs)
    assert any("visual share 0%" in e for e in errs)
    assert any("at_a_glance" in e for e in errs)
    assert any("acronyms must come just before closing" in e for e in errs)


def test_chapter_slides_must_sit_under_their_divider(tree):
    s = checklist(*(item("Verify the date and time.", ["para-1-2.li2"]),) * 3, chapter="ch-1")
    spec = deck([s, {"pattern": "divider", "title": "Basics", "chapter": "ch-1"}])
    errs = errors(check_spec(spec, tree))
    assert any("ch-1 slide sits under the front divider" in e for e in errs)


@pytest.mark.skipif(not FM_TREE.exists(), reason="run convert for FM-3-09 first")
def test_all_patterns_fixture_passes_partial_check_on_fm309():
    t = DocTree.model_validate_json(FM_TREE.read_text())
    spec = json.loads(FIXTURE.read_text())
    assert check_spec(spec, t, partial=True) == []


def test_titles_cannot_carry_requirements(tree):
    s = checklist(*(item("Verify the date and time.", ["para-1-2.li2"]),) * 3)
    s["title"] = "Checks you must do"
    errs = errors(check_spec(deck([s]), tree, partial=True))
    assert any("title says 'must'" in e for e in errs)


def test_acronyms_on_slides_must_be_listed(tree):
    s = checklist(
        item("The FO must locate targets.", ["para-1-1"], "must"),
        item("Read FM 0-00 for the details.", ["para-1-1"]),  # a pub designator, not an acronym
        item("Verify the date and time.", ["para-1-2.li2"]),
    )
    warns = warnings(check_spec(deck([s]), tree))
    assert any("acronym FO is used" in w for w in warns)
    assert not any("acronym FM" in w for w in warns)


def test_review_lines_pair_statements_with_cited_text(tree):
    from army_trainer.plan.check import review_lines

    spec = deck([checklist(*(item("Verify the date and time.", ["para-1-2.li2"]),) * 3)])
    lines = list(review_lines(spec, tree, {"s02"}))
    assert lines[0].strip().startswith("=== s02 [checklist]")
    assert "* Verify the date and time." in lines[1] and "[para-1-2.li2] Verify" in lines[2]


def test_callout_needs_every_statement_under_the_label(tree):
    sun = item("The sun must never be viewed without a filter.", ["para-1-3.t2"], "must")
    sun_slide = {"pattern": "key_idea", "title": "Sun", "statement": sun, "callout": "caution"}
    assert errors(check_spec(deck([sun_slide]), tree, partial=True)) == []
    mixed = dict(sun_slide, points=[item("Observers use optics.", ["para-1-3"])])
    errs = errors(check_spec(deck([mixed]), tree, partial=True))
    assert any("isn't under a CAUTION block" in e for e in errs)
    warn_slide = dict(sun_slide, callout="warning")
    assert any("WARNING" in e for e in errors(check_spec(deck([warn_slide]), tree, partial=True)))


def test_structural_slides_take_no_callout_and_caveat_is_cited(tree):
    from pydantic import ValidationError

    from army_trainer.plan.spec import SlideSpec

    spec = deck([])
    spec["slides"][0]["callout"] = "caution"
    with pytest.raises(ValidationError, match="take no callout"):
        SlideSpec.model_validate(spec)
    nums = {
        "pattern": "big_numbers",
        "title": "Numbers",
        "stats": [{"value": "3", "label": "desert terrain types", "cite": ["para-1-4"]}] * 2,
        "caveat": item("There are 7 types.", ["para-1-4"]),
    }
    warns = warnings(check_spec(deck([nums]), tree, partial=True))
    assert any("['7']" in w for w in warns)  # the caveat is a checked claim like any item
