"""Shared helpers: walk the tree, split sentences."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..structure.models import DocTree

TEXT_TYPES = ("paragraph", "list_item", "text")
_ABBREV = re.compile(
    r"\b(?:e\.g|i\.e|etc|vs|no|fig|para|gen|col|lt|maj|capt|sgt|dr|u\.s|approx|ch|figs)\.$", re.I
)


def walk(node, path: tuple = ()) -> Iterator[tuple]:
    """Yield (node, ancestors) depth-first."""
    yield node, path
    for child in getattr(node, "children", None) or []:
        yield from walk(child, (*path, node))


def walk_tree(tree: DocTree) -> Iterator[tuple]:
    for d in tree.divisions:
        yield from walk(d)


def text_nodes(tree: DocTree) -> Iterator[tuple]:
    """Paragraphs, list items and unnumbered texts, each with ancestors."""
    for node, path in walk_tree(tree):
        if node.type in TEXT_TYPES:
            yield node, path


def section_title(path: tuple) -> str | None:
    """Nearest enclosing heading/section/division title."""
    for anc in reversed(path):
        title = getattr(anc, "title", None)
        if title:
            return title
    return None


def split_sentences(text: str) -> list[str]:
    """Split after . ? ! before a capital, digit or quote; skip common abbreviations."""
    parts: list[str] = []
    start = 0
    for m in re.finditer(r"[.?!][\"')\]”’]*\s+(?=[A-Z0-9\"“(])", text):
        end = m.end()
        candidate = text[start : m.start() + 1].rstrip()
        if _ABBREV.search(candidate) or re.search(r"\b[A-Z]\.$", candidate):
            continue
        parts.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts
