"""Directive sentences: will / will not / must / must not / may / may not / should."""

from __future__ import annotations

import re

from ..structure.models import DocTree
from .walk import section_title, split_sentences, text_nodes

# Longest alternatives first so "will not" wins over "will".
_PAT = re.compile(
    r"\b(will not|must not|may not|should not|shall not|will|must|may|should|shall)\b", re.I
)
# Verbs after "may" that make it a permission/definition of capability. We keep all; the
# strength field lets consumers filter.
STRENGTH = {
    "must": "mandatory",
    "must not": "mandatory",
    "will": "mandatory",
    "will not": "mandatory",
    "shall": "mandatory",
    "shall not": "mandatory",
    "should": "advisory",
    "should not": "advisory",
    "may": "permissive",
    "may not": "prohibitive",
}
# FM/ATP convention: "will" in descriptive prose often predicts future events rather than
# directing. We can't judge that mechanically; flag the obvious future-narrative cases.
_HISTORICAL = re.compile(r"\b(1[89]\d\d|20[01]\d)\b")


def extract_directives(tree: DocTree) -> list[dict]:
    out: list[dict] = []
    for node, path in text_nodes(tree):
        for sentence in split_sentences(node.plain):
            verbs = [m.group(1).lower() for m in _PAT.finditer(sentence)]
            if not verbs:
                continue
            out.append(
                {
                    "node_id": node.id,
                    "cite": node.cite,
                    "page": node.page,
                    "section": section_title(path),
                    "verb": verbs[0],
                    "verbs": verbs,
                    "strength": STRENGTH[verbs[0]],
                    "sentence": sentence,
                    "possibly_historical": bool(_HISTORICAL.search(sentence)),
                }
            )
    return out
