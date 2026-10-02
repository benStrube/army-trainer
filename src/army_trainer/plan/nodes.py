"""Look up document-tree nodes by id and get the text a citation of them covers (WP 2.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..structure.models import DocTree

CONTAINERS = ("division", "section", "heading")


@dataclass(frozen=True)
class Located:
    node: object
    ancestors: tuple
    division: str  # id of the enclosing division (the node itself for a division)


class NodeIndex:
    """Every node of a tree by id, with its ancestors and the text it covers."""

    def __init__(self, tree: DocTree):
        self.tree = tree
        self.by_id: dict[str, Located] = {}
        self.order: dict[str, int] = {}  # document order, for sorting
        for d in tree.divisions:
            self._visit(d, (), d.id)
        self._text: dict[str, str] = {}

    def _visit(self, node, ancestors: tuple, division: str) -> None:
        self.by_id[node.id] = Located(node, ancestors, division)
        self.order[node.id] = len(self.order)
        for c in getattr(node, "children", None) or []:
            self._visit(c, (*ancestors, node), division)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.by_id

    def get(self, node_id: str):
        return self.by_id[node_id].node

    def division_of(self, node_id: str) -> str:
        return self.by_id[node_id].division

    def text(self, node_id: str) -> str:
        """Plain text a citation of this node covers: the node and everything under it."""
        if node_id not in self._text:
            self._text[node_id] = " ".join(t for t in _texts(self.get(node_id)) if t)
        return self._text[node_id]


def _texts(node):
    t = node.type
    if t in ("paragraph", "list_item", "text"):
        yield node.plain
    elif t in CONTAINERS:
        yield node.title
    elif t == "table":
        yield node.caption or ""
        yield " ".join(node.columns)
        yield from (" ".join(r) for r in node.rows)
        yield node.key or ""
    elif t == "figure":
        yield node.caption
    elif t == "term":
        yield f"{node.term}: {node.definition}"
    elif t == "acronym":
        yield f"{node.abbreviation}: {node.meaning}"
    for c in getattr(node, "children", None) or []:
        yield from _texts(c)


def plain_md(text: str) -> str:
    """Drop Markdown emphasis from table cells and captions."""
    return re.sub(r"(\*\*|__|\*|_)(\S(?:.*?\S)?)\1", r"\2", text)
