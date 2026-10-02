"""Cross-references: internal (table/figure/chapter/paragraph) and external publications."""

from __future__ import annotations

import re

from ..structure.models import DocTree
from .walk import section_title, text_nodes

_PUB_TYPES = (
    r"ADP|ADRP|ATP|FM|JP|TC|AR|DA\s+Pam|DAFI|AFI|ATTP|GTA|MCRP|MCTP|MCWP|NTTP|CJCSI|DODD|DODI"
    r"|STP|TM"
)
# e.g. "ATP 3-09.50", "JP 1, Volume 2", "ATP 3- 09" (PDF spacing noise)
EXTERNAL = re.compile(
    rf"\b(?P<type>{_PUB_TYPES})\s+(?P<num>\d{{1,3}}\s?-\s?\d{{1,3}}(?:\.\d+)*|\d{{1,3}})"
    rf"(?P<vol>,\s*Volume\s+\w+|,\s*vol\s+\w+)?",
    re.I,
)
INTERNAL = re.compile(
    r"\b(?P<kind>table|figure|chapter|appendix|paragraph|para|section)s?\s+"
    r"(?P<ref>[A-Z]?-?\d+(?:-\d+)*(?:\.\d+)?|[A-Z](?![a-z]))",
    re.I,
)
_SEE = re.compile(r"\b(see|refer to|according to|as described in)\b", re.I)
_KIND_NORM = {"para": "paragraph"}


def _norm_pub(m: re.Match) -> str:
    num = re.sub(r"\s+", "", m.group("num"))
    vol = m.group("vol")
    out = f"{re.sub(r'\s+', ' ', m.group('type').upper().replace('DA PAM', 'DA Pam'))} {num}"
    if vol:
        out += ", Volume " + vol.split()[-1]
    return out


def extract_crossrefs(tree: DocTree) -> list[dict]:
    """One row per reference. `target_exists` is checked for internal tables/figures/paragraphs."""
    table_nums = set()
    fig_nums = set()
    para_nums = set()
    from .walk import walk_tree

    for node, _ in walk_tree(tree):
        if node.type == "table" and node.number:
            table_nums.add(node.number)
        elif node.type == "figure" and node.number:
            fig_nums.add(node.number)
        elif node.type == "paragraph":
            para_nums.add(node.number)

    out: list[dict] = []
    for node, path in text_nodes(tree):
        text = node.plain
        spans: list[tuple[int, int]] = []
        for m in EXTERNAL.finditer(text):
            spans.append(m.span())
            out.append(
                {
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                    "section": section_title(path),
                    "scope": "external",
                    "kind": "publication",
                    "target": _norm_pub(m),
                    "raw": m.group(0),
                    "see": bool(_SEE.search(text[max(0, m.start() - 12) : m.start()])),
                    "target_exists": None,
                }
            )
        for m in INTERNAL.finditer(text):
            if any(s <= m.start() < e for s, e in spans):
                continue
            kind = _KIND_NORM.get(m.group("kind").lower(), m.group("kind").lower())
            ref = m.group("ref")
            if kind == "paragraph" and not re.search(r"\d", ref):
                continue
            exists = None
            if kind == "table":
                exists = ref in table_nums
            elif kind == "figure":
                exists = ref in fig_nums
            elif kind == "paragraph":
                exists = ref in para_nums
            out.append(
                {
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                    "section": section_title(path),
                    "scope": "internal",
                    "kind": kind,
                    "target": f"{kind} {ref}",
                    "raw": m.group(0),
                    "see": bool(_SEE.search(text[max(0, m.start() - 12) : m.start()])),
                    "target_exists": exists,
                }
            )
    return out
