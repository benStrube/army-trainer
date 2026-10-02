"""Document tree (WP 1.3): Markdown -> typed tree, schema kept in sync."""

import json
from pathlib import Path

import jsonschema
import pytest

from army_trainer.structure import models as M
from army_trainer.structure.parse import parse_markdown
from army_trainer.structure.schema import SCHEMA_PATH, schema_json

FRONT = """---
pub_id: FM-0-00
title: Test Manual
pub_date: '2024-08-12'
distribution: A — approved for public release; distribution is unlimited
source_sha256: abc
page_count: 10
---

"""

GOLDEN = Path(__file__).parent / "golden" / "FM-3-09_p15-21.md"


def walk(node):
    yield node
    for ch in getattr(node, "children", []):
        yield from walk(ch)


def nodes(tree):
    return [n for d in tree.divisions for n in walk(d)]


def by_id(tree):
    return {n.id: n for n in nodes(tree)}


SAMPLE = (
    FRONT
    + """<!-- page 35 (2-1) -->

# Chapter 2: The Fire Support System

As discussed in chapter 1, FS is a system.

## SECTION I – COMMAND AND CONTROL

2-1. The elements of the FS system _deliver fires_.

### FIRE SUPPORT PERSONNEL

2-5. The FSCOORD must ensure the following:

- First duty.

  - A sub-point.

- Second duty.

These duties continue at every echelon.

**Table 2-1. Fire support titles**

| Echelon | Title |
| --- | --- |
| Corps | FSCOORD (FAB CDR) |

<!-- page 36 (2-2) -->

FAB – field artillery brigade, CDR – commander

**Figure 2-1. Example of target area of interest**

## SECTION II – TARGET ACQUISITION

2-40. Target acquisition text.

# Glossary

## SECTION I – ACRONYMS AND ABBREVIATIONS

| Acronym | Meaning |
| --- | --- |
| **FA** | field artillery |

## SECTION II – TERMS

**air interdiction** — Air operations to perform interdiction. (JP 3-03)

***priority of fires** — The commander's guidance for fires.
"""
)


def test_sample_structure_and_citations():
    tree = parse_markdown(SAMPLE)
    ids = by_id(tree)
    ch2 = tree.divisions[0]
    assert (ch2.id, ch2.kind, ch2.number, ch2.cite) == ("ch-2", "chapter", "2", "chapter 2")
    assert [c.type for c in ch2.children] == ["text", "section", "section"]

    sec = ids["ch-2.sec-i"]
    assert sec.title == "COMMAND AND CONTROL" and sec.cite == "chapter 2, section I"
    assert [c.id for c in sec.children] == ["para-2-1", "ch-2.sec-i.fire-support-personnel"]

    p = ids["para-2-5"]
    assert (p.cite, p.page, p.page_label) == ("para 2-5", 35, "2-1")
    assert [c.id for c in p.children] == ["para-2-5.li1", "para-2-5.li2", "para-2-5.t1"]
    assert ids["para-2-5.li1"].children[0].text == "A sub-point."
    assert ids["para-2-5.t1"].cite == "para 2-5"  # unnumbered text continues the paragraph
    assert ids["para-2-1"].plain == "The elements of the FS system deliver fires."

    t = ids["table-2-1"]
    assert (t.columns, t.rows) == (["Echelon", "Title"], [["Corps", "FSCOORD (FAB CDR)"]])
    assert t.key == "FAB – field artillery brigade, CDR – commander"
    assert ids["figure-2-1"].page_label == "2-2"
    # a section at the same level closes the previous one, including its headings
    assert ids["ch-2.sec-ii"].children[0].id == "para-2-40"


def test_glossary_terms_and_acronyms():
    tree = parse_markdown(SAMPLE)
    ids = by_id(tree)
    assert ids["acr-fa"].meaning == "field artillery"
    ai = ids["term-air-interdiction"]
    assert (ai.definition, ai.source, ai.proponent) == (
        "Air operations to perform interdiction.",
        "JP 3-03",
        False,
    )
    pof = ids["term-priority-of-fires"]
    assert pof.proponent and pof.source is None


def test_golden_excerpt_tree():
    tree = parse_markdown(GOLDEN.read_text())
    paras = [n for n in nodes(tree) if n.type == "paragraph"]
    assert [p.number for p in paras] == [f"1-{i}" for i in range(1, len(paras) + 1)]
    ids = by_id(tree)
    assert ids["table-1-2"].caption.startswith("Table 1-2.")
    # three PDF pages, one table: the nine imperatives of operations, in order
    firsts = [r[0].split(".")[0].strip("* ") for r in ids["table-1-2"].rows]
    assert len(firsts) == 9
    assert firsts[0] == "See yourself, see the enemy, and understand the OE"
    assert firsts[-1] == "Understand and manage the effects of operations on units and leaders"
    assert all(n.page >= 15 for n in nodes(tree))


def test_ids_are_unique_and_output_matches_committed_schema():
    tree = parse_markdown(GOLDEN.read_text())
    all_ids = [n.id for n in nodes(tree)]
    assert len(all_ids) == len(set(all_ids))
    assert SCHEMA_PATH.read_text() == schema_json(), (
        "schemas/doc_tree.schema.json is stale: run `uv run python -m army_trainer.structure.schema`"
    )
    data = json.loads(tree.model_dump_json(exclude_none=True))
    jsonschema.validate(data, json.loads(SCHEMA_PATH.read_text()))
    assert M.DocTree.model_validate(data) == tree


def test_rejects_markdown_without_front_matter():
    with pytest.raises(ValueError, match="front matter"):
        parse_markdown("# Chapter 1: X\n")
