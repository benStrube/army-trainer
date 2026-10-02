"""Index extractors (WP 1.4): one group of tests per extractor, on a synthetic tree."""

import json

from army_trainer.index.build import build_indexes, write_indexes
from army_trainer.index.crossrefs import extract_crossrefs
from army_trainer.index.deadlines import extract_deadlines
from army_trainer.index.directives import extract_directives
from army_trainer.index.glossary import extract_glossary
from army_trainer.index.roles import extract_roles, segment
from army_trainer.index.walk import split_sentences
from army_trainer.structure.parse import parse_markdown

FRONT = """---
pub_id: FM-0-00
title: Test Manual
pub_date: '2024-08-12'
distribution: A — approved for public release; distribution is unlimited
source_sha256: abc
page_count: 10
---

"""

MD = (
    FRONT
    + """<!-- page 5 (1-1) -->

# Chapter 1: Basics

## FIRE SUPPORT PERSONNEL

#### FIRESUPPORTOFFICER

1-1. The FSO will advise the commander. The FSO must not delay a mission. Leaders may
adjust the plan (see ATP 3-09.50 and table 1-1). See figure 9-9 and paragraph 1-2.

- Report within 30 minutes of contact.
- The team should rehearse.

1-2. The FSCOORD updates the plan no later than H-6, and every 2 hours (FM 3-0). Units
will not fire without clearance; JP 3-09, Volume 2 applies.

_Fire support_ is the collective use of indirect fires.

**Table 1-1. Roles**

| Role | Duty |
|---|---|
| FSO | Advises |

# Glossary

## SECTION I – ACRONYMS AND ABBREVIATIONS

| Acronym | Meaning |
| --- | --- |
| **FSO** | fire support officer |
| **FSCOORD** | fire support coordinator |
"""
)


def tree():
    return parse_markdown(MD)


def test_split_sentences_keeps_abbreviations_together():
    s = split_sentences("Dr. Smith went to Fig. 2. Then he left. The U.S. Army won.")
    assert s[0].startswith("Dr. Smith went to Fig. 2.")
    assert len(s) == 3


def test_directives_keep_exact_verbs_and_cite():
    d = extract_directives(tree())
    by_verb = {x["verb"]: x for x in d}
    assert {"will", "must not", "may", "should", "will not", "must"} & set(by_verb) >= {
        "will",
        "must not",
        "may",
        "should",
        "will not",
    }
    assert by_verb["will"]["cite"] == "para 1-1"
    assert by_verb["will"]["strength"] == "mandatory"
    assert by_verb["may"]["strength"] == "permissive"
    assert by_verb["should"]["strength"] == "advisory"
    assert "will not fire" in by_verb["will not"]["sentence"]
    # "must not" is one verb, not "must" + something else
    assert "must" not in [x["verb"] for x in d if "must not delay" in x["sentence"]]


def test_deadlines_find_durations_and_hour_references():
    rows = extract_deadlines(tree())
    kinds = {r["kind"] for r in rows}
    assert "deadline" in kinds
    joined = " ".join(r["sentence"] for r in rows)
    assert "within 30 minutes" in joined.lower()
    h6 = next(r for r in rows if "H-6" in r["time_references"])
    assert "no later than" in h6["markers"]
    assert "every" in h6["markers"] and "2 hours" in h6["durations"]


def test_deadlines_net_is_not_the_noun():
    from army_trainer.structure.parse import parse_markdown as pm

    t = pm(FRONT + "<!-- page 1 (1-1) -->\n\n# Chapter 1: X\n\n1-1. Use the maneuver net.\n")
    assert extract_deadlines(t) == []


def test_crossrefs_internal_external_and_existence():
    rows = extract_crossrefs(tree())
    ext = {r["target"] for r in rows if r["scope"] == "external"}
    assert {"ATP 3-09.50", "FM 3-0", "JP 3-09, Volume 2"} <= ext
    internal = {r["target"]: r for r in rows if r["scope"] == "internal"}
    assert internal["table 1-1"]["target_exists"] is True
    assert internal["figure 9-9"]["target_exists"] is False
    assert internal["paragraph 1-2"]["target_exists"] is True
    assert next(r for r in rows if r["target"] == "ATP 3-09.50")["cite"] == "para 1-1"


def test_segment_squashed_headings():
    vocab = {"fire": 9, "support": 9, "officer": 9, "fires": 1}
    assert segment("FIRESUPPORTOFFICER", vocab) == "fire support officer"
    assert segment("zzz", vocab) is None


def test_roles_from_heading_and_acronym():
    roles = {r["name"]: r for r in extract_roles(tree())}
    fso = roles["fire support officer"]
    assert fso["abbreviation"] == "FSO"
    assert fso["kind"] == "position"
    assert fso["source"] == "heading+acronym"
    assert fso["mention_count"] == 1
    assert any(d["verb"] == "will" for d in fso["duties"])


def test_glossary_inline_definitions():
    g = extract_glossary(tree())
    assert any(i["term"] == "Fire support" and i["cite"] for i in g["inline_definitions"])
    assert {a["abbreviation"] for a in g["acronyms"]} >= {"FSO", "FSCOORD"}


def test_build_and_write_roundtrip(tmp_path):
    t = tree()
    idx = build_indexes(t)
    assert idx.pub_id == "FM-0-00"
    assert idx.counts["directives"] == len(idx.directives)
    (tmp_path / "FM-0-00.json").write_text(t.model_dump_json(), encoding="utf-8")
    out = write_indexes("FM-0-00", tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["counts"] == idx.counts
    # every entry is citable
    for key in ("directives", "deadlines", "crossrefs"):
        assert all(e["cite"] and e["node_id"] for e in data[key])
