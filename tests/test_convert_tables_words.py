"""Table rebuild clean-up and word repairs (WP 5.1a), without a PDF."""

from army_trainer.convert.blocks import Block
from army_trainer.convert.tables import _clean, _distinct_cells, _styled, score
from army_trainer.convert.words import _apply, joined_word_fixes, repair_words


def test_clean_merges_two_line_header_drops_repeats_and_moves_keys():
    grid = [
        ["Operations", "", "Joint Targeting", "D3A"],
        ["Process", "", "Cycle", "D3A"],  # second header line; D3A is a merged label
        ["Continuous Assessment", "Plan", "Commander's Objectives", "Decide"],
        ["Operations Process", "", "Joint Targeting Cycle", ""],  # header repeated on page 2
        ["Continuous Assessment", "Plan", "Target Development", "Decide"],
        ["D3A – decide, detect, deliver, and assess", "", "", ""],
    ]
    rows, notes = _clean(grid)
    assert rows[0] == ["Operations Process", "", "Joint Targeting Cycle", "D3A"]
    assert len(rows) == 3 and rows[2][2] == "Target Development"
    assert notes == ["D3A – decide, detect, deliver, and assess"]


def test_clean_merges_complementary_columns_and_keeps_full_width_rows():
    grid = [
        ["Phase: II Decrease effectiveness", "", "", ""],
        ["FS Task", "(T) Target", "", "(L) Location"],
        ["EFST 1", "KE2000", "", "NAI 20"],
        ["A – alternate, AOF – azimuth of fire", "", "", ""],
        ["Notes: none", "", "", ""],
    ]
    rows, notes = _clean(grid)
    assert rows[0] == ["FS Task", "(T) Target", "(L) Location"]  # empty column dropped
    assert rows[1][0].startswith("Phase:") and rows[2] == ["EFST 1", "KE2000", "NAI 20"]
    assert notes == ["A – alternate, AOF – azimuth of fire", "Notes: none"]


def test_styled_marks_bold_italic_and_superscript():
    spans = [
        {"text": "Create", "flags": 16, "font": "Arial-Bold"},
        {"text": " advantage. ", "flags": 0, "font": "Arial"},
        {"text": "Own Observers.", "flags": 0, "font": "Arial"},
        {"text": "1", "flags": 1, "font": "Arial"},
        {"text": " term", "flags": 2, "font": "Arial-Italic"},
    ]
    assert _styled(spans) == "**Create** advantage. Own Observers.<sup>1</sup> _term_"


def test_score_rewards_recall_and_penalises_stray_tokens():
    pdf = ["own", "observers", "fa", "hq"]
    assert score(["own", "observers", "fa", "hq"], pdf) == 1.0
    assert score(["own", "fa", "hq", "companyt"], pdf) < score(["own", "fa", "hq"], pdf)
    assert list(_distinct_cells([["Decide", "a"], ["Decide", "b"]])) == ["Decide", "a", "b"]


PDF = "the high-\nexplosive round\nand the decision\nmaking process, high explosive, airburst"


def test_joined_words_are_split_only_on_pdf_line_break_evidence():
    texts = ["highexplosive and decisionmaking and airburst"] + [
        "high explosive decision making"
    ] * 3
    fixes = joined_word_fixes(texts, PDF + " airburst")
    assert fixes["highexplosive"] == "high-explosive"
    assert fixes["decisionmaking"] == "decision making"
    assert "airburst" not in fixes  # printed whole in the PDF


def test_references_and_hyphen_spaces():
    assert (
        _apply("see JP 3- 09 and table 1- 3; the S- 2", {}) == "see JP 3-09 and table 1-3; the S-2"
    )
    assert _apply("pre- mission checks for rotary- and fixed-wing", {}) == (
        "pre-mission checks for rotary- and fixed-wing"
    )
    b = Block("para", "Highexplosive rounds (ADP 3- 0)", 1)
    t = Block("table", "", 1, rows=[["a", "highexplosive"]])
    texts = [b, t, *[Block("para", "high explosive", 1)] * 3]
    assert repair_words(texts, PDF) == 2
    assert b.text == "High-explosive rounds (ADP 3-0)" and t.rows[0][1] == "high-explosive"


def test_fm309_damaged_tables_are_repaired():
    import json
    from pathlib import Path

    import pytest

    path = Path(__file__).parents[1] / "data/json/FM-3-09.json"
    if not path.exists():
        pytest.skip("run convert for FM-3-09 first")
    tables = {}

    def walk(n):
        if n.get("type") == "table":
            tables[n["id"]] = n
        for c in n.get("children") or []:
            walk(c)

    for d in json.loads(path.read_text())["divisions"]:
        walk(d)
    text = {
        k: " ".join([*t["columns"], *(c for r in t["rows"] for c in r)]) for k, t in tables.items()
    }
    assert "3. Own Observers" in tables["table-4-1"]["rows"][3][1]  # was cut off at "3. Own"
    assert tables["table-4-1"]["key"]
    assert "Companyt" not in text["table-a-4"] and "nonene" not in text["table-a-4"]
    assert "SuppressiBetty" not in text["table-a-9"] and "less than 10 minutes" in text["table-a-9"]
    assert "Cdt" not in text["table-3-7"] and "Conduct a COA briefing" in text["table-3-7"]
    assert tables["table-3-1"]["columns"][0] == "Operations Process"
    assert [r[2] for r in tables["table-3-1"]["rows"]][1] == "Target Development and Prioritization"
    assert len(tables["table-e-3"]["rows"]) == 6 and tables["table-e-3"]["key"]  # key out of rows
    assert len(tables["table-e-4"]["rows"]) == 4  # not E-5's rows
    assert "friendlyzone" not in text["table-introductory-1"]
