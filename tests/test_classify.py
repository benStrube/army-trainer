"""Rule-based pattern hints (WP 2.1) on a small synthetic document."""

from army_trainer.index.build import build_indexes
from army_trainer.plan.classify import classify
from army_trainer.structure.parse import parse_markdown

DOC = """---
pub_id: FM-0-00
title: Test Manual
pub_date: '2024-08-12'
distribution: A — approved for public release; distribution is unlimited
source_sha256: abc
page_count: 10
---

<!-- page 1 (1-1) -->

# Chapter 1: Basics

This chapter has two sections. Section I covers people. Section II covers procedures.

## SECTION I – PEOPLE

### FORWARD OBSERVER

1-1. The FO is the fire support representative for the platoon. The FO must locate targets.

## SECTION II – PROCEDURES

### VERIFYING MESSAGES

1-2. When the FDC receives a message, check it as follows:

- Check the message type and location entries.

- Verify the date and time.

- Record any peculiarities.

### SAFETY WITH OPTICS

1-3. Observers use optics to find the azimuth.

CAUTION

The sun must never be viewed through the telescope without a filter.

### TERRAIN

1-4. There are three types of desert terrain: mountainous, rocky plateau, and sandy desert.

**Table 1-1. Titles**

| Echelon | Title |
| --- | --- |
| Corps | FSCOORD |
| Division | FSCOORD |
"""


def hints():
    tree = parse_markdown(DOC)
    return {h.node_id: h for h in classify(tree, build_indexes(tree))}


def test_chapter_intro_is_a_divider():
    assert hints()["ch-1"].primary == "divider"


def test_role_heading_suggests_roles():
    assert hints()["ch-1.sec-i.forward-observer"].primary == "roles"


def test_lead_in_with_action_verbs_suggests_process_or_checklist():
    h = hints()["ch-1.sec-ii.verifying-messages"]
    assert set(list(h.scores)[:2]) == {"process_flow", "checklist"}
    assert any("action verb" in r for r in h.reasons["process_flow"])


def test_caution_block_suggests_do_dont():
    assert hints()["ch-1.sec-ii.safety-with-optics"].primary == "do_dont"


def test_types_and_tables():
    h = hints()["ch-1.sec-ii.terrain"]
    assert {"table", "comparison"} <= set(h.scores)
    assert h.primary == "table"
    assert h.paragraphs == ["1-4"] and h.cite == "para 1-4"
