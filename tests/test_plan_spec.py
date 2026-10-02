"""Slide spec models (WP 2.1): validation rules, schema sync, the all-patterns fixture."""

import copy
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from army_trainer.plan.schema import SCHEMA_PATH, schema_json
from army_trainer.plan.spec import DISCLAIMER, PATTERNS, VISUAL_PATTERNS, SlideSpec

FIXTURE = Path(__file__).parent / "fixtures" / "spec_all_patterns.json"


@pytest.fixture
def spec() -> dict:
    return json.loads(FIXTURE.read_text())


def slide(spec, pattern):
    return next(s for s in spec["slides"] if s["pattern"] == pattern)


def test_fixture_covers_every_pattern_and_validates(spec):
    m = SlideSpec.model_validate(spec)
    assert {s.pattern for s in m.slides} == set(PATTERNS)
    assert m.disclaimer == DISCLAIMER and m.audience == "junior Soldiers"
    assert "para-2-19" in m.cited_ids() and "table-2-1" in m.cited_ids()
    assert VISUAL_PATTERNS <= set(PATTERNS)


def test_schema_file_in_sync_and_fixture_matches_it(spec):
    assert SCHEMA_PATH.read_text() == schema_json(), (
        "schemas/slide_spec.schema.json is stale: run `uv run python -m army_trainer.plan.schema`"
    )
    jsonschema.validate(spec, json.loads(SCHEMA_PATH.read_text()))


def invalid(spec, mutate, match):
    s = copy.deepcopy(spec)
    mutate(s)
    with pytest.raises(ValidationError, match=match):
        SlideSpec.model_validate(s)


def test_every_item_needs_a_citation(spec):
    invalid(spec, lambda s: slide(s, "checklist")["items"][0].update(cite=[]), "at least 1")


def test_directive_must_appear_in_item_text(spec):
    def soften(s):
        item = slide(s, "do_dont")["dont"][0]
        item["text"] = "Avoid viewing the sun through the telescope without a filter."

    invalid(spec, soften, "directive 'must' must appear")


def renumber(s):
    for k, sl in enumerate(s["slides"], 1):
        sl["id"] = f"s{k:02d}"


def test_deck_must_open_with_title_and_close_with_closing(spec):
    invalid(spec, lambda s: (s["slides"].reverse(), renumber(s)), "first slide must be the title")
    invalid(spec, lambda s: s["slides"].pop(), "last slide must be the closing")


def test_slide_ids_run_in_order(spec):
    invalid(spec, lambda s: s["slides"][1].update(id="s07"), "slide ids must run")


def test_disclaimer_and_audience_are_fixed(spec):
    invalid(spec, lambda s: s.update(disclaimer="Official guidance."), "disclaimer")
    invalid(spec, lambda s: s.update(audience="staff officers"), "audience")


def test_decision_tree_must_be_a_tree(spec):
    invalid(spec, lambda s: slide(s, "decision_tree")["nodes"][0].update(no=None), "yes and no")
    invalid(spec, lambda s: slide(s, "decision_tree")["nodes"][0].update(no="o1"), "cycle or")
    invalid(spec, lambda s: slide(s, "decision_tree")["nodes"][1].update(yes="q1"), "cannot branch")


def test_roles_parents_must_exist(spec):
    invalid(spec, lambda s: slide(s, "roles")["roles"][0].update(parent="xo"), "unknown parent")


def test_table_rows_match_columns_and_stay_short(spec):
    invalid(spec, lambda s: slide(s, "table")["rows"][0]["cells"].pop(), "one cell per column")
    invalid(
        spec, lambda s: slide(s, "table")["rows"][0]["cells"].__setitem__(1, "x" * 81), "too long"
    )


def test_budgets_limit_items_and_text_length(spec):
    def too_many(s):
        items = slide(s, "checklist")["items"]
        items.extend(copy.deepcopy(items[:4]))  # 8 > 7

    invalid(spec, too_many, "at most 7")
    invalid(spec, lambda s: slide(s, "checklist")["items"][0].update(text="x" * 161), "160")


def test_unknown_fields_and_patterns_are_rejected(spec):
    invalid(spec, lambda s: slide(s, "checklist").update(color="#FFCD01"), "Extra inputs")
    invalid(spec, lambda s: slide(s, "checklist").update(pattern="word_cloud"), "word_cloud")
