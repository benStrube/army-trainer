"""`plan --check`: validate a slide spec against the document tree (WP 2.2).

Errors fail the check; warnings are for the session to look at. The check is deterministic
and makes no API calls. QA (Phase 4) repeats the fidelity checks on the rendered deck.

Errors:
* the spec doesn't validate against the models (schema, text budgets, deck shape);
* `pub.pub_id` / `pub.source_sha256` don't match the tree;
* a cited node id (or `chapter`, `source_table`, `extra_sources`) isn't in the tree;
* an item's `directive` isn't in the text of any node it cites;
* slide text uses will / must / shall / will not / must not / may not / should not but none
  of its cited nodes does (an added or strengthened requirement);
* an acronym entry isn't in the glossary;
* deck level (skipped with `partial`): 25-40 slides, >= 60% visual content slides, and the
  deck template order (docs/slide_spec.md).

Warnings: `may` / `should` in slide text but not in the source, numbers in slide text not in
the cited source, citations of whole headings or divisions, acronym meanings that differ from
the glossary, key terms not found in the glossary or an inline definition, chapters with no
slides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from ..structure.models import DocTree
from .nodes import CONTAINERS, NodeIndex
from .packet import DECK_MAX, DECK_MIN
from .spec import STRUCTURAL_PATTERNS, VISUAL_PATTERNS, SlideSpec

VISUAL_TARGET = 0.6
#: Directive phrases, longest first so "will not" is matched before "will".
DIRECTIVES = (
    "will not", "must not", "may not", "should not", "shall", "will", "must", "may", "should",
)  # fmt: skip
STRICT = {"will not", "must not", "may not", "should not", "shall", "will", "must"}
_DIRECTIVE_RX = re.compile(r"\b(" + "|".join(d.replace(" ", r"\s+") for d in DIRECTIVES) + r")\b")
_NUMBER_RX = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?")
TEXT_FIELDS = ("text", "label", "detail", "when", "value", "definition", "meaning", "cells")


@dataclass
class Finding:
    level: str  # "error" | "warning"
    where: str  # "s05", "s05.items[2]", "deck"
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


def directive_words(text: str) -> list[str]:
    """Directive phrases in `text` (lower-cased, "will not" kept whole)."""
    return [re.sub(r"\s+", " ", m) for m in _DIRECTIVE_RX.findall(text.lower())]


def _has_word(text: str, phrase: str) -> bool:
    return phrase in directive_words(text)


_NUMBER_WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


_REF_RX = re.compile(r"\b(?:chapter|appendix|section|table|figure|para(?:graph)?)\s+[\w-]+", re.I)


def _numbers(text: str) -> set[str]:
    """Numbers in `text`, with number words (one ... twelve) as digits. References such as
    "chapter 2" or "table 3-1" are not numbers to verify."""
    text = _REF_RX.sub(" ", text)
    out = {n.replace(",", "") for n in _NUMBER_RX.findall(text)}
    words = set(re.findall(r"[a-z]+", text.lower()))
    return out | {str(i) for i, w in enumerate(_NUMBER_WORDS) if w in words}


def _cited_objects(obj, path: str):
    """Yield (path, model) for every model in the spec that carries `cite`."""
    if isinstance(obj, BaseModel):
        if "cite" in type(obj).model_fields:
            yield path, obj
        for name, val in obj:
            if isinstance(val, BaseModel | list):
                yield from _cited_objects(val, f"{path}.{name}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _cited_objects(v, f"{path}[{i}]")


def _slide_text(obj: BaseModel) -> str:
    parts = []
    for name in TEXT_FIELDS:
        v = getattr(obj, name, None)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(x for x in v if isinstance(x, str))
    return " ".join(parts)


def check_spec(data: dict, tree: DocTree, partial: bool = False) -> list[Finding]:
    """Return every finding for a spec (as parsed JSON). `partial` skips deck-level checks."""
    f: list[Finding] = []
    err = lambda w, m: f.append(Finding("error", w, m))  # noqa: E731
    warn = lambda w, m: f.append(Finding("warning", w, m))  # noqa: E731
    try:
        spec = SlideSpec.model_validate(data)
    except ValidationError as e:
        for x in e.errors():
            loc = ".".join(str(p) for p in x["loc"])
            err(f"schema {loc}", x["msg"])
        return f

    idx = NodeIndex(tree)
    if spec.pub.pub_id != tree.pub.pub_id:
        err("pub", f"pub_id {spec.pub.pub_id!r} != tree {tree.pub.pub_id!r}")
    if spec.pub.source_sha256 != tree.pub.source_sha256:
        err("pub", "source_sha256 doesn't match the tree: the spec was planned on another PDF")

    acronyms = {}
    terms = set()
    for loc in idx.by_id.values():
        n = loc.node
        if n.type == "acronym":
            acronyms[n.abbreviation] = n
        elif n.type == "term":
            terms.add(n.term.lower())

    for s in spec.slides:
        sid = s.id
        if strict := [w for w in directive_words(s.title) if w in STRICT]:
            err(sid, f"title says {strict[0]!r}: titles aren't cited, keep requirements in items")
        if s.chapter is not None:
            if s.chapter not in idx:
                err(sid, f"chapter {s.chapter!r} is not in the tree")
            elif idx.get(s.chapter).type != "division":
                err(sid, f"chapter {s.chapter!r} is not a division id")
        for ref in [*s.notes.extra_sources, *([s.source_table] if s.pattern == "table" else [])]:
            if ref and ref not in idx:
                err(sid, f"unknown node {ref!r}")
        if s.pattern == "table" and s.source_table and s.source_table in idx:
            if idx.get(s.source_table).type != "table":
                err(sid, f"source_table {s.source_table!r} is not a table")

        for path, obj in _cited_objects(s, sid):
            where = path.replace(f"{sid}.", f"{sid} ", 1) if path != sid else sid
            missing = [c for c in obj.cite if c not in idx]
            for c in missing:
                err(where, f"cites unknown node {c!r}")
            known = [c for c in obj.cite if c in idx]
            if not known:
                continue
            if s.pattern != "divider":
                for c in known:
                    if idx.get(c).type in CONTAINERS:
                        warn(where, f"cites a whole {idx.get(c).type} ({c}); cite paragraphs")
            source = " ".join(idx.text(c) for c in known)
            text = _slide_text(obj)
            directive = getattr(obj, "directive", None)
            if directive and not _has_word(source, directive):
                err(where, f"directive {directive!r} is not in the cited text ({', '.join(known)})")
            for w in dict.fromkeys(directive_words(text)):
                if w == directive or _has_word(source, w):
                    continue
                msg = f"slide text says {w!r} but the cited text doesn't"
                if w in STRICT:
                    err(where, msg + " (adds or changes a requirement)")
                else:
                    warn(where, msg)
            extra = _numbers(text) - _numbers(source)
            if extra:
                warn(where, f"number(s) {sorted(extra)} not in the cited text")
            if s.pattern == "acronyms":
                a = acronyms.get(obj.abbreviation)
                if a is None:
                    err(where, f"acronym {obj.abbreviation!r} is not in the glossary")
                elif a.meaning.lower() != obj.meaning.lower():
                    warn(where, f"{obj.abbreviation} meaning differs from glossary: {a.meaning!r}")
            if s.pattern == "key_terms" and obj.term.lower() not in terms:
                if not any(obj.term.lower() in idx.text(c).lower() for c in known):
                    warn(where, f"term {obj.term!r} not in the glossary or the cited text")

    listed = {e.abbreviation for s in spec.slides if s.pattern == "acronyms" for e in s.entries}
    if listed or not partial:
        _acronym_coverage(spec, acronyms, listed, warn)
    if not partial:
        _deck_checks(spec, tree, idx, err, warn)
    return f


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, BaseModel):
        for name, val in obj:
            if name not in ("cite", "extra_sources", "source_table", "chapter", "id", "key"):
                yield from _strings(val)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _acronym_coverage(spec: SlideSpec, acronyms: dict, listed: set[str], warn) -> None:
    """Every glossary acronym that appears on a slide should be on the acronyms slide."""
    used: dict[str, str] = {}
    for s in spec.slides:
        if s.pattern == "acronyms":
            continue
        text = " ".join(_strings(s))
        for abbr in acronyms:
            if len(abbr) >= 2 and abbr not in used:
                if re.search(rf"(?<![\w-]){re.escape(abbr)}(?![\w-])(?!\s+\d)", text):
                    used[abbr] = s.id
    for abbr, sid in used.items():
        if abbr not in listed:
            warn(sid, f"acronym {abbr} is used but not on the acronyms slide")


def _deck_checks(spec: SlideSpec, tree: DocTree, idx: NodeIndex, err, warn) -> None:
    slides = spec.slides
    n = len(slides)
    if not DECK_MIN <= n <= DECK_MAX:
        err("deck", f"{n} slides; the budget is {DECK_MIN}-{DECK_MAX}")
    content = [s for s in slides if s.pattern not in STRUCTURAL_PATTERNS]
    visual = [s for s in content if s.pattern in VISUAL_PATTERNS]
    share = len(visual) / len(content) if content else 0.0
    if share < VISUAL_TARGET:
        err("deck", f"visual share {share:.0%} ({len(visual)}/{len(content)}) < 60%")

    pats = [s.pattern for s in slides]
    if n > 1 and pats[1] != "at_a_glance":
        err("s02", "slide 2 must be at_a_glance")
    if "takeaways" not in pats[2:4]:
        err("deck", "takeaways must be slide 3 (or 4)")
    if n > 2 and pats[-2] != "acronyms":
        err("deck", "acronyms must come just before closing")
    for p in ("title", "at_a_glance", "takeaways", "whats_new", "key_terms", "acronyms", "closing"):
        if pats.count(p) > 1:
            err("deck", f"more than one {p} slide")
    if "key_terms" in pats and pats.index("key_terms") != n - 3:
        err("deck", "key_terms must come just before acronyms")

    order = {d.id: i for i, d in enumerate(tree.divisions)}
    current: str | None = None
    seen: list[str] = []
    for s in slides:
        if s.pattern == "divider":
            if not s.chapter or s.chapter not in order:
                err(s.id, "a divider needs `chapter` set to a division id")
                continue
            if s.chapter in seen:
                err(s.id, f"second divider for {s.chapter}")
            elif seen and order[s.chapter] < order[seen[-1]]:
                err(s.id, f"divider for {s.chapter} is out of document order")
            seen.append(s.chapter)
            current = s.chapter
        elif s.chapter in order and s.pattern not in STRUCTURAL_PATTERNS:
            kind = tree.divisions[order[s.chapter]].kind
            if s.chapter == current:
                continue
            if kind == "chapter" or current is None:  # appendix slides may join any chapter
                err(s.id, f"{s.chapter} slide sits under the {current or 'front'} divider")
    first_div = pats.index("divider") if "divider" in pats else None
    if first_div is not None and first_div > 4:
        err("deck", "front slides after whats_new: put them in a chapter or after the chapters")
    for d in tree.divisions:
        if d.kind == "chapter" and d.id not in seen:
            warn("deck", f"no divider/slides for {d.id} ({d.title})")
