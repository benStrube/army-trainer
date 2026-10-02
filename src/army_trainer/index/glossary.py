"""Glossary terms: formal `term` nodes plus in-text italic definitions."""

from __future__ import annotations

import re

from ..structure.models import DocTree
from .walk import text_nodes, walk_tree

# Italic phrase immediately followed by a defining verb: "_Fire support_ is ...".
_INLINE = re.compile(
    r"(?<![_\w])_(?P<term>[^_\n]{2,80}?)_\s+(?P<verb>is|are|refers? to|means|describes?)\b"
    r"(?P<rest>[^.]*\.?)"
)
_BOLD_ITALIC = re.compile(r"\*\*_([^_]+)_\*\*|_\*\*([^*]+)\*\*_")


def extract_glossary(tree: DocTree) -> dict:
    formal: list[dict] = []
    for node, _ in walk_tree(tree):
        if node.type == "term":
            formal.append(
                {
                    "term": node.term,
                    "definition": node.definition,
                    "source": node.source,
                    "proponent": node.proponent,
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                }
            )
    formal_keys = {f["term"].lower() for f in formal}

    inline: list[dict] = []
    for node, _ in text_nodes(tree):
        for m in _INLINE.finditer(node.text):
            term = re.sub(r"[*_]", "", m.group("term")).strip()
            sentence = re.sub(r"[*_]", "", m.group(0)).strip()
            inline.append(
                {
                    "term": term,
                    "definition": sentence,
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                    "also_in_glossary": term.lower() in formal_keys,
                }
            )

    acronyms = [
        {
            "abbreviation": n.abbreviation,
            "meaning": n.meaning,
            "node_id": n.id,
            "cite": n.cite,
        }
        for n, _ in walk_tree(tree)
        if n.type == "acronym"
    ]
    return {"terms": formal, "inline_definitions": inline, "acronyms": acronyms}
