"""Planning packet: everything a planning session reads to write a slide spec (WP 2.2, D10).

`army-trainer plan <ID> --packet` writes `data/packets/<ID>/`:

* `README.md`: the publication, the suggested slide budget and the deck template;
* one `<division-id>.md` per division: outline with pattern hints, requirement and deadline
  rows from the indexes, roles, terms and acronyms used there, then the **full text with node
  ids** so every statement on a slide can be cited;
* `packet.json`: the same budget and outline as data (for tools and tests).

Everything is deterministic and built from the gated document tree. No Claude API calls: the
session reads these files (D10). The playbook is `plan/prompts/planner.md`.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..index.build import Indexes
from ..structure.models import DocTree
from .classify import Hint, classify
from .nodes import NodeIndex, plain_md

PACKET_DIR = Path("data/packets")
DECK_MIN, DECK_MAX = 25, 40
DEFAULT_TARGET = 34
#: title, at_a_glance, takeaways, whats_new, key_terms, acronyms, closing
FIXED_SLIDES = (
    "title",
    "at_a_glance",
    "takeaways",
    "whats_new",
    "key_terms",
    "acronyms",
    "closing",
)
BUDGETED_KINDS = ("chapter", "appendix")


@dataclass
class DivisionBudget:
    division: str
    kind: str
    number: str | None
    title: str
    words: int
    content_slides: int = 0

    @property
    def total(self) -> int:  # chapters get a divider; appendix slides join the chapters
        return self.content_slides + (1 if self.kind == "chapter" else 0)


@dataclass
class Budget:
    target: int
    fixed: list[str] = field(default_factory=lambda: list(FIXED_SLIDES))
    divisions: list[DivisionBudget] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.fixed) + sum(d.total for d in self.divisions)


#: who or what a junior Soldier in a fires unit or maneuver platoon deals with (WP 5.1c)
_SOLDIER = re.compile(
    r"\b(observers?|FOs?|FISTs?|fire support teams?|Soldiers?|crews?|sections?|squads?|"
    r"platoons?|howitzers?|guns?|launchers?|mortars?|FDCs?|fire direction|gunners?|"
    r"section chiefs?|telescopes?|aiming circles?|GPS|radios?|filters?|vehicles?|"
    r"ammunition|rounds?|fuzes?|positions?)\b",
    re.I,
)
_STAFF = re.compile(
    r"\b(commanders?|staffs?|FSCOORD|G-\d|S-\d|boards?|working groups?|JFC|corps|division|"
    r"theater|joint force|planners?|headquarters|HQ)\b"
)


def soldier_actionable(sentence: str) -> bool:
    """Heuristic: the requirement is about people or equipment at crew/observer level and not
    mainly about commanders, staffs or echelons above brigade."""
    return bool(_SOLDIER.search(sentence)) and len(_STAFF.findall(sentence)) < 2


def plan_budget(tree: DocTree, target: int = DEFAULT_TARGET) -> Budget:
    """Split `target` slides over chapters and appendixes.

    Every chapter gets a divider and at least one content slide. Appendixes get no divider
    of their own: their slides sit with the chapter they support or after the chapters. The
    rest goes by the D'Hondt method on sqrt(word count), so long divisions get more slides
    but not proportionally more. This is a starting point: the session moves slides toward
    what junior Soldiers need and keeps the total in 25-40.
    """
    if not DECK_MIN <= target <= DECK_MAX:
        raise ValueError(f"target must be {DECK_MIN}-{DECK_MAX}, got {target}")
    idx = NodeIndex(tree)
    budget = Budget(target=target)
    for d in tree.divisions:
        if d.kind in BUDGETED_KINDS:
            words = len(idx.text(d.id).split())
            budget.divisions.append(DivisionBudget(d.id, d.kind, d.number, d.title, words))
            if d.kind == "chapter":
                budget.divisions[-1].content_slides = 1
    while budget.divisions and budget.total < target:
        best = max(budget.divisions, key=lambda b: math.sqrt(b.words) / (b.content_slides + 1))
        best.content_slides += 1
    return budget


# ---------------------------------------------------------------- rendering


def _hint_cell(h: Hint) -> str:
    return ", ".join(f"{p} {s:g}" for p, s in list(h.scores.items())[:3])


def _md_cell(s: str) -> str:
    return plain_md(s).replace("|", "/").replace("\n", " ")


def _render_node(node, out: list[str]) -> None:
    t = node.type
    if t == "division":
        out.append(f"# {node.title}  `[{node.id}]`\n")
    elif t == "section":
        out.append(f"## SECTION {node.number} – {node.title}  `[{node.id}]`\n")
    elif t == "heading":
        out.append(f"{'#' * min(node.level + 1, 6)} {node.title}  `[{node.id}]`\n")
    elif t == "paragraph":
        out.append(f"`[{node.id}]` **{node.number}.** {node.plain}\n")
    elif t == "list_item":
        out.append(f"{'  ' * node.depth}- `[{node.id}]` {node.plain}")
    elif t == "text":
        out.append(f"`[{node.id}]` {node.plain}\n")
    elif t == "table":
        label = f"Table {node.number}. " if node.number else ""
        cap = _md_cell(node.caption or "") if node.caption else ""
        cap = cap if cap.lower().startswith("table") else label + cap
        out.append(f"`[{node.id}]` **{cap.strip() or 'Table'}**\n")
        if node.grid and node.columns:
            out.append("| " + " | ".join(_md_cell(c) for c in node.columns) + " |")
            out.append("|" + " --- |" * len(node.columns))
            out.extend("| " + " | ".join(_md_cell(c) for c in r) + " |" for r in node.rows)
            out.append("")
        elif not node.grid:
            out.append("(Printed as text: the rows follow as list/text nodes.)\n")
        if node.key:
            out.append(f"Key: {_md_cell(node.key)}\n")
    elif t == "figure":
        out.append(
            f"`[{node.id}]` **{_md_cell(node.caption)}** (image not in the packet: use only "
            "what the caption and the text say)\n"
        )
    elif t == "term":
        src = f" ({node.source})" if node.source else ""
        out.append(f"- `[{node.id}]` **{node.term}**: {node.definition}{src}")
    elif t == "acronym":
        out.append(f"- `[{node.id}]` **{node.abbreviation}**: {node.meaning}")
    for c in getattr(node, "children", None) or []:
        _render_node(c, out)
    if t == "list_item" and node.depth == 0:
        out.append("")


@dataclass
class _Ctx:
    tree: DocTree
    idx: NodeIndex
    indexes: Indexes
    hints: list[Hint]
    budget: Budget
    cite_to_id: dict[str, str]


def _division_md(ctx: _Ctx, div) -> tuple[str, dict]:
    idx, ix = ctx.idx, ctx.indexes
    in_div = lambda node_id: node_id in idx and idx.division_of(node_id) == div.id  # noqa: E731
    b = next((b for b in ctx.budget.divisions if b.division == div.id), None)
    hints = [h for h in ctx.hints if (h.path[:1] or [h.node_id])[0] == div.id]
    text = idx.text(div.id)
    words = len(text.split())
    out: list[str] = [f"# Packet: {div.title}  `[{div.id}]`\n"]
    label = {"chapter": "Chapter", "appendix": "Appendix"}.get(div.kind, div.kind.title())
    num = f" {div.number}" if div.number else ""
    out.append(f"{label}{num}, {words} words, starts on page {div.page_label or div.page}.")
    if b:
        where = " + 1 divider" if b.kind == "chapter" else (
            " (no divider: place them with the chapter they support, or after the chapters)"
        )  # fmt: skip
        out.append(f"**Suggested slides:** {b.content_slides} content{where}. See README.md.\n")
    else:
        out.append("**Suggested slides:** none of its own; use it for the front/back slides.\n")

    out.append("## Outline and pattern hints\n")
    out.append("Hints are a rule-based shortlist (about 70% have the right pattern in the top "
               "3). Read the unit and decide.\n")  # fmt: skip
    out.append("| Unit | Paragraphs | Words | Hints (score) | Why (top hint) |")
    out.append("| --- | --- | --- | --- | --- |")
    for h in hints:
        paras = f"{h.paragraphs[0]}–{h.paragraphs[-1]}" if len(h.paragraphs) > 1 else (
            h.paragraphs[0] if h.paragraphs else "")  # fmt: skip
        why = "; ".join(h.reasons.get(h.primary, []))
        title = _md_cell(h.title) or "(intro text)"
        out.append(f"| {title} | {paras} | {h.words} | {_hint_cell(h)} | {why} |")
    out.append("")

    dirs = [
        d for d in ix.directives
        if in_div(d["node_id"]) and d["strength"] in ("mandatory", "prohibitive")
        and not d["possibly_historical"]
    ]  # fmt: skip
    n_soldier = sum(soldier_actionable(d["sentence"]) for d in dirs)
    out.append(
        f"## Requirements and prohibitions ({len(dirs)}; ★ {n_soldier} likely Soldier tasks)\n"
    )
    out.append("Sentences with will / must / shall / will not / must not / may not. Many FM "
               "\"must\"s are doctrine for staffs; pick those a junior Soldier acts on. Keep the "
               "verb exactly as written. ★ marks sentences about observers, crews, howitzers, "
               "fire direction, Soldiers or equipment they handle: a heuristic shortlist, not a "
               "decision.\n")  # fmt: skip
    out.extend(
        f"- {'★ ' if soldier_actionable(d['sentence']) else ''}`[{d['node_id']}]` "
        f"**{d['verb']}**: {d['sentence']}"
        for d in dirs
    )
    out.append("")

    dls = [d for d in ix.deadlines if in_div(d["node_id"]) and d["kind"] != "duration"]
    if dls:
        out.append(f"## Deadlines and time references ({len(dls)})\n")
        for d in dls:
            when = ", ".join(d["durations"] + d["time_references"] + d["markers"])
            out.append(f"- `[{d['node_id']}]` ({when}): {d['sentence']}")
        out.append("")

    roles = []
    for r in ix.roles:
        ids = [ctx.cite_to_id.get(c) for c in r.get("cites", [])]
        n = sum(1 for i in ids if i and in_div(i))
        if n:
            roles.append((n, r))
    if roles:
        out.append(f"## Roles mentioned ({len(roles)})\n")
        for n, r in sorted(roles, key=lambda x: -x[0]):
            abbr = f" ({r['abbreviation']})" if r.get("abbreviation") else ""
            out.append(f"- **{r['name']}**{abbr}: {n} paragraph(s) here")
            for duty in r.get("duties", []):
                if in_div(duty["node_id"]):
                    out.append(f"  - `[{duty['node_id']}]` {duty['sentence']}")
        out.append("")

    terms = [t for t in ix.glossary.get("inline_definitions", []) if in_div(t["node_id"])]
    if terms:
        out.append(f"## Terms defined here ({len(terms)})\n")
        for t in terms:
            gl = " (also in glossary)" if t.get("also_in_glossary") else ""
            out.append(f"- `[{t['node_id']}]` **{t['term']}**{gl}: {t['definition']}")
        out.append("")

    used = Counter()
    for a in ix.glossary.get("acronyms", []):
        n = len(re.findall(rf"(?<![\w-]){re.escape(a['abbreviation'])}(?![\w-])", text))
        if n:
            used[(a["abbreviation"], a["meaning"], a["node_id"])] = n
    if used:
        out.append(f"## Acronyms used here ({len(used)}): spell out on first use\n")
        out.extend(
            f"- {abbr} = {meaning} ×{n} `[{nid}]`" for (abbr, meaning, nid), n in used.most_common()
        )
        out.append("")

    out.append("## Full text (cite these ids)\n")
    _render_node(div, out)
    summary = {
        "division": div.id,
        "kind": div.kind,
        "title": div.title,
        "words": words,
        "units": len(hints),
        "requirements": len(dirs),
        "deadlines": len(dls),
        "roles": len(roles),
        "terms": len(terms),
        "acronyms": len(used),
    }
    return "\n".join(out).rstrip() + "\n", summary


def _readme(tree: DocTree, budget: Budget, summaries: list[dict], gate_line: str) -> str:
    p = tree.pub
    short = p.pub_id.replace("-", " ", 1)
    out = [
        f"# Planning packet: {short}, {p.title}\n",
        f"- Publication date: {p.pub_date}; supersedes: {p.supersedes or 'n/a'}",
        f"- Gate: {gate_line}",
        f"- Source SHA-256 (put in the spec's `pub.source_sha256`): `{p.source_sha256}`",
        f"- Pages: {p.page_count}",
        "",
        "Read `src/army_trainer/plan/prompts/planner.md` (the playbook) before writing the spec. "
        "Write it to `specs/<ID>.spec.json` and run `army-trainer plan <ID> --check`.\n",
        f"## Suggested slide budget: {budget.total} slides (allowed {DECK_MIN}–{DECK_MAX})\n",
        "Fixed slides: " + ", ".join(f"`{f}`" for f in budget.fixed) + ".\n",
        "| Division | Title | Words | Suggested slides (divider + content) | File |",
        "| --- | --- | --- | --- | --- |",
    ]
    for b in budget.divisions:
        sug = f"1 + {b.content_slides}" if b.kind == "chapter" else f"{b.content_slides}"
        out.append(f"| `{b.division}` | {b.title} | {b.words} | {sug} | `{b.division}.md` |")
    out += [
        "",
        "The split is by length only (D'Hondt on sqrt(words)). Move slides toward what junior "
        "Soldiers need; the playbook says how. Keep the total in range.\n",
        "## Deck template\n",
        "1. `title` 2. `at_a_glance` 3. `takeaways` 4. `whats_new` (from the Introduction) "
        "5. per chapter: `divider`, then content slides with `chapter` set (appendix slides, "
        "`chapter` = the appendix id, go with the chapter they support or after the chapters) "
        "6. optional cross-chapter slides (`chapter` null) 7. `key_terms` 8. `acronyms` "
        "9. `closing`\n",
        "## Files\n",
        "| File | Words | Units | Requirements | Deadlines | Roles | Terms | Acronyms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        out.append(
            f"| `{s['division']}.md` ({s['title']}) | {s['words']} | {s['units']} | "
            f"{s['requirements']} | {s['deadlines']} | {s['roles']} | {s['terms']} | "
            f"{s['acronyms']} |"
        )
    return "\n".join(out) + "\n"


def build_packet(
    tree: DocTree,
    indexes: Indexes,
    out_dir: Path,
    target: int = DEFAULT_TARGET,
    gate_line: str = "passed",
) -> Path:
    """Write the packet for `tree` to `out_dir` and return the README path."""
    idx = NodeIndex(tree)
    budget = plan_budget(tree, target)
    cite_to_id = {}
    for node_id, loc in idx.by_id.items():
        if loc.node.type == "paragraph":
            cite_to_id[loc.node.cite] = node_id
    ctx = _Ctx(tree, idx, indexes, classify(tree, indexes), budget, cite_to_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.md"):
        stale.unlink()
    summaries = []
    for div in tree.divisions:
        md, summary = _division_md(ctx, div)
        (out_dir / f"{div.id}.md").write_text(md, encoding="utf-8")
        summaries.append(summary)
    readme = out_dir / "README.md"
    readme.write_text(_readme(tree, budget, summaries, gate_line), encoding="utf-8")
    data = {
        "pub_id": tree.pub.pub_id,
        "source_sha256": tree.pub.source_sha256,
        "budget": {
            "target": budget.target,
            "total": budget.total,
            "fixed": budget.fixed,
            "divisions": [asdict(b) | {"total": b.total} for b in budget.divisions],
        },
        "divisions": summaries,
    }
    (out_dir / "packet.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return readme
