"""Deadlines, time limits and durations."""

from __future__ import annotations

import re

from ..structure.models import DocTree
from .walk import section_title, split_sentences, text_nodes

_NUM_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|"
    "forty|forty-five|sixty|ninety"
)
UNITS = r"seconds?|minutes?|hours?|days?|weeks?|months?|years?"
_DURATION = re.compile(
    rf"\b(?P<n>\d+(?:\.\d+)?(?:\s+(?:to|or|and)\s+\d+)?|(?:{_NUM_WORDS}))[-\s](?P<unit>{UNITS})\b",
    re.I,
)
_DEADLINE = re.compile(
    r"\b(no later than|not later than|at least every|at a minimum of|"
    r"not earlier than|within|every|prior to|before)\b|\b(NLT|NET)\b(?=\s+[HDLC0-9])",
    re.I,
)
_HOUR_REF = re.compile(r"\b[HDL]-(?:hour|day)\b|\b[HDL]\s?[-+]\s?\d+\b")
# "before" / "prior to" alone are too weak; require a duration or time reference with them.
_STRONG = {"no later than", "not later than", "nlt", "at least every", "net", "not earlier than"}


def extract_deadlines(tree: DocTree) -> list[dict]:
    out: list[dict] = []
    for node, path in text_nodes(tree):
        for sentence in split_sentences(node.plain):
            durations = [m.group(0) for m in _DURATION.finditer(sentence)]
            refs = [m.group(0) for m in _HOUR_REF.finditer(sentence)]
            markers = [
                (m.group(1) or m.group(2)).lower()
                for m in _DEADLINE.finditer(sentence)
                if m.group(1) or m.group(2) in ("NLT", "NET")
            ]
            strong = [m for m in markers if m in _STRONG]
            if not (durations or refs or strong):
                continue
            kind = "deadline" if strong or (durations and markers) else "duration"
            if refs and not (durations or strong):
                kind = "time_reference"
            out.append(
                {
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                    "section": section_title(path),
                    "kind": kind,
                    "durations": durations,
                    "time_references": refs,
                    "markers": markers,
                    "sentence": sentence,
                }
            )
    return out
