"""Rule-based pattern hints for every content unit of a document (WP 2.1).

A *unit* is a division, section or heading that directly holds content (paragraphs, text,
tables, figures). For each unit the rules score every visual pattern from cheap signals in the
tree and the indexes, and return the best few with the reasons. These are **hints** for the
planning session (D10), not decisions: the session reads the unit and picks.

The scores are additive and only roughly calibrated; what matters is the ranking. See
docs/decisions/classifier-review.md for the reviewed accuracy sample.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from ..index.build import Indexes
from ..structure.models import DocTree

CONTAINERS = ("division", "section", "heading")
CONTENT = ("paragraph", "text", "table", "figure", "list_item", "term", "acronym")

TITLE_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("roles", re.compile(r"PERSONNEL|RESPONSIBILIT|DUTIES|ROLES?\b|OFFICER|SERGEANT|"
                         r"OBSERVER|COORDINATOR|CHIEF OF|COMMAND POSTS?|ELEMENT|CELL\b|"
                         r"CENTER|HEADQUARTERS|TEAM\b|COMMANDER", re.I), 3.0),
    ("process_flow", re.compile(r"PROCESS|PROCEDURE|STEPS?\b|SEQUENCE|METHOD|PLANNING|"
                                r"PREPARATION|EXECUTION|REHEARSAL|CLEARANCE|REQUEST", re.I), 2.5),
    ("cycle", re.compile(r"CYCLE|D3A|DECIDE, DETECT|TARGETING PROCESS|CONTINUOUS", re.I), 3.0),
    ("checklist", re.compile(r"PRINCIPLES?|CHARACTERISTICS|CONSIDERATIONS|TENETS|IMPERATIVES|"
                             r"FUNCTIONS|TASKS|REQUIREMENTS|COMPETENCIES|CAPABILITIES|"
                             r"FUNDAMENTALS|GUIDANCE|TRAIN", re.I), 2.5),
    ("timeline", re.compile(r"PHASES?\b|TIMELINE|TRANSITION|SCHEDUL|DAY\b|HOURS?\b", re.I), 2.5),
    ("comparison", re.compile(r"VERSUS|\bVS\b|TYPES OF|COMPARISON|DIFFERENCES", re.I), 2.0),
    ("decision_tree", re.compile(r"DECISION|DETERMIN|SELECTION|CRITERIA|AUTHORITY", re.I), 1.5),
    ("do_dont", re.compile(r"SAFETY|FRATRICIDE|DANGER CLOSE|PREVENT|AVOID", re.I), 2.0),
    ("key_terms", re.compile(r"TERMS|DEFINITIONS|GLOSSARY|ACRONYMS", re.I), 3.0),
]  # fmt: skip

ORDER_WORDS = re.compile(r"\b(first|second|third|then|next|after(?:wards)?|finally|"
                         r"once|following|subsequently|step \d|begins?|ends?)\b", re.I)  # fmt: skip
CONDITIONAL = re.compile(r"\b(if\b[^.]{3,80}\bthen\b|unless\b|whether\b|in the event|"
                         r"depending on|when [^.,]{3,60},)", re.I)  # fmt: skip
CONTRAST = re.compile(r"\b(whereas|in contrast|unlike|on the other hand|differs?|versus|"
                      r"while [a-z]+ [a-z]+ (?:is|are))\b", re.I)  # fmt: skip
# explicit prohibitions only: "restrictive" and "deny" are FM topic words, not prohibitions
NEGATIVE = re.compile(r"\b(will not|must not|may not|do not|should not|never|avoid\w*|"
                      r"prohibit\w*)\b", re.I)  # fmt: skip
SAFETY_BLOCK = re.compile(r"^(CAUTION|WARNING|DANGER)\b")
TYPES = re.compile(
    r"\b(two|three|four|five) (?:main |basic )?(types|categories|kinds|methods|forms)\b", re.I
)
ROLE_WORDS = re.compile(r"\b(responsib\w*|charges|duties|serves as|in charge|advis\w+)\b", re.I)
NUMBER_UNIT = re.compile(r"\b\d[\d,.]*\s?(?:%|percent|km|kilometers?|meters?|m\b|miles?|"
                         r"minutes?|hours?|days?|mm|rounds?|seconds?|mils?|degrees?)",
                         re.I)  # fmt: skip
ACTION_VERB = re.compile(
    r"^(Check|Verify|Determine|Compute|Enter|Record|Establish|Identify|Select|Plan|Brief)\b"
)
LOOP = re.compile(r"\b(cycle|continuous(?:ly)?|repeat\w*|iterative|loop)\b", re.I)


@dataclass
class Hint:
    node_id: str
    title: str
    path: list[str]
    cite: str
    page: int
    page_label: str | None
    words: int
    paragraphs: list[str]
    primary: str
    scores: dict[str, float]
    reasons: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _units(tree: DocTree):
    def visit(node, path):
        if node.type in CONTAINERS:
            own = [c for c in node.children if c.type in CONTENT]
            if own:
                yield node, path, own
            for c in node.children:
                if c.type in CONTAINERS:
                    yield from visit(c, (*path, node))

    for d in tree.divisions:
        yield from visit(d, ())


def _descend(nodes):
    for n in nodes:
        yield n
        yield from _descend(getattr(n, "children", None) or [])


def _text(n) -> str:
    return getattr(n, "plain", None) or getattr(n, "caption", None) or ""


def classify(tree: DocTree, indexes: Indexes) -> list[Hint]:
    by_node: dict[str, Counter] = defaultdict(Counter)
    for d in indexes.directives:
        by_node[d["node_id"]][f"dir_{d['strength']}"] += 1
    for d in indexes.deadlines:
        by_node[d["node_id"]][f"time_{d['kind']}"] += 1
    for r in indexes.roles:
        for duty in r.get("duties", []):
            by_node[duty["node_id"]]["duty"] += 1
    for d in indexes.glossary.get("inline_definitions", []):
        by_node[d["node_id"]]["definition"] += 1

    role_names: set[str] = set()  # lower-case full names
    role_abbrs: set[str] = set()  # case-sensitive abbreviations
    for r in indexes.roles:
        if len(r["name"]) >= 3:
            role_names.add(r["name"].lower())
        if r.get("abbreviation") and len(r["abbreviation"]) >= 3:
            role_abbrs.add(r["abbreviation"])

    hints: list[Hint] = []
    for unit, path, own in _units(tree):
        nodes = list(_descend(own))
        title = getattr(unit, "title", "") or ""
        text = " ".join(_text(n) for n in nodes)
        c: Counter = Counter()
        for n in nodes:
            c.update(by_node.get(n.id, {}))
        kinds = Counter(n.type for n in nodes)
        grid_tables = [n for n in own if n.type == "table" and n.grid and n.rows]
        top_items = [n for n in nodes if n.type == "list_item" and n.depth == 0]
        words = len(text.split())

        score: dict[str, float] = defaultdict(float)
        why: dict[str, list[str]] = defaultdict(list)

        def add(pattern: str, pts: float, reason: str, score=score, why=why) -> None:
            score[pattern] += pts
            why[pattern].append(reason)

        for pattern, rx, pts in TITLE_RULES:
            if rx.search(title):
                add(pattern, pts, f"title matches {pattern}")
        if grid_tables:
            add("table", 3.0 + min(len(grid_tables), 2), f"{len(grid_tables)} grid table(s)")
        if c["duty"] >= 2:
            add("roles", min(c["duty"], 5) * 0.6, f"{c['duty']} role-duty sentences")
        leads = sum(
            1
            for n in own
            if n.type == "paragraph" and n.plain.rstrip().endswith(":") and n.children
        )
        if leads:
            add("checklist", 1.5 * min(leads, 2), f"{leads} lead-in(s) ending ':' with a list")
            imperative = [n for n in top_items if ACTION_VERB.match(n.plain)]
            if len(imperative) >= 3:
                add("process_flow", 2.5, f"{len(imperative)} list items start with an action verb")
        if 3 <= len(top_items) <= 8:
            add("checklist", 2.0, f"{len(top_items)} top-level list items")
            if (n := len(ORDER_WORDS.findall(text))) >= 2:
                add("process_flow", 1.0 + 0.4 * min(n, 5), f"list + {n} order words")
        elif len(top_items) > 8:
            add("checklist", 1.0, f"{len(top_items)} list items (needs trimming)")
        per100 = max(words, 1) / 100
        if (n := len(ORDER_WORDS.findall(text))) >= 3 and n / per100 >= 1.2:
            add("process_flow", 1.0 + 0.3 * min(n, 8), f"{n} order words ({n / per100:.1f}/100w)")
        if (n := len(LOOP.findall(text))) >= 2:
            add("cycle", 0.6 * min(n, 6), f"{n} cycle/continuous words")
        if (n := c["time_deadline"] + c["time_time_reference"]) >= 1:
            add("timeline", 1.5 * min(n, 4), f"{n} deadline/time references")
        if (n := len(NEGATIVE.findall(text))) >= 2:
            add("do_dont", 0.5 * min(n, 8), f"{n} negative/prohibitive phrases")
        if c["dir_mandatory"] >= 3 and len(top_items) >= 2:
            add("checklist", 1.0, f"{c['dir_mandatory']} mandatory directives")
        # FMs define terms everywhere: only a definition-dense unit is a key-terms slide
        n_def = c["definition"] + kinds["term"]
        n_par = max(kinds["paragraph"] + kinds["text"], 1)
        if n_def >= 3 and n_def / n_par >= 0.6:
            add("key_terms", 1.0 * min(n_def, 5), f"{n_def} definitions in {n_par} paragraphs")
        elif n_def >= 1:
            add("key_idea", 1.0, f"{n_def} definition(s)")
        if (n := len(CONDITIONAL.findall(text))) >= 2 and n / per100 >= 0.8:
            add("decision_tree", 0.7 * min(n, 6), f"{n} conditional phrases")
        if (n := len(CONTRAST.findall(text))) >= 2:
            add("comparison", 0.7 * min(n, 5), f"{n} contrast phrases")
        if (n := len(NUMBER_UNIT.findall(text))) >= 2 and words < 400:
            add("big_numbers", 0.5 * min(n, 4), f"{n} numbers with units")
        if kinds["paragraph"] + kinds["text"] <= 2 and words < 220:
            add("key_idea", 1.5, "short unit")
        if (
            unit.type == "division"
            and unit.kind in ("chapter", "appendix")
            and not kinds["paragraph"]
        ):
            add("divider", 5.0, "division introduction with no numbered paragraphs")
        if any(n.type == "text" and SAFETY_BLOCK.match(n.plain) for n in nodes):
            add("do_dont", 4.0, "CAUTION/WARNING block")
        if (n := len(TYPES.findall(text))) >= 1:
            add("comparison", 2.0, "enumerates types/categories")
        low = text.lower()
        named = {nm for nm in role_names if nm in low} | {
            a for a in role_abbrs if re.search(rf"\b{re.escape(a)}\b", text)
        }
        if len(named) >= 3 or (len(named) >= 2 and ROLE_WORDS.search(text)):
            add("roles", 1.0 + 0.5 * min(len(named), 6), f"{len(named)} roles named")
        if c["dir_mandatory"] + c["dir_advisory"] >= 4 and not top_items:
            add("checklist", 1.5, "several must/should statements")
        if not score:
            add("key_idea" if words < 300 else "checklist", 0.5, "fallback")

        ranked = dict(sorted(score.items(), key=lambda kv: -kv[1])[:4])
        primary = next(iter(ranked))
        hints.append(
            Hint(
                node_id=unit.id,
                title=title,
                path=[p.id for p in path],
                cite=next((n.cite for n in own if n.type == "paragraph"), unit.cite),
                page=unit.page,
                page_label=unit.page_label,
                words=words,
                paragraphs=[n.number for n in own if n.type == "paragraph"],
                primary=primary,
                scores={k: round(v, 2) for k, v in ranked.items()},
                reasons={k: why[k] for k in ranked},
            )
        )
    return hints
