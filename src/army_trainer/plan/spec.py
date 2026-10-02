"""Slide spec: what goes on every slide of a deck (WP 2.1, Opus-owned).

An Opus session writes a spec (D10); the renderer (Phase 3) draws it; QA (Phase 4) checks it
against the document tree. The spec holds *what* to say and *which pattern* to use, never
layout coordinates or colors (those are the renderer's, from the D9 palette).

Fidelity is built in:
* every piece of slide text that makes a claim carries `cite`: one or more document-tree node
  ids (e.g. "para-2-5"); `plan --check` verifies they exist;
* `directive` records the exact directive verb (will / must / will not / may ...) when an item
  states a requirement, so QA can confirm it wasn't softened;
* the renderer pulls verbatim source text for speaker notes from the cited nodes, so the spec
  never copies source text it could get wrong.

See docs/slide_spec.md and schemas/slide_spec.schema.json.
"""

from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

SPEC_VERSION = "1.1"  # 1.1 (WP 5.1d): optional `callout` and big-number `caveat`
DISCLAIMER = (
    "Unofficial training aid. Not an official Army product. "
    "The publication is the authoritative source; read it before acting."
)

NodeId = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9][\w.\-]*$",
        description="Document-tree node id, e.g. 'para-2-5', 'table-1-2', 'term-kill-box'.",
    ),
]
Cites = Annotated[list[NodeId], Field(min_length=1, description="Tree nodes this text rests on.")]
Directive = Literal[
    "will", "will not", "must", "must not", "shall", "may", "may not", "should", "should not"
]
Key = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=40)]


def _s(max_length: int, description: str = "") -> object:
    return Field(min_length=1, max_length=max_length, description=description)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- building blocks


class Item(_M):
    """One cited statement: a bullet, a card line, a checklist entry."""

    text: str = _s(160, "Plain language for junior Soldiers (~8th grade).")
    cite: Cites
    directive: Directive | None = Field(
        default=None,
        description="Exact directive verb when the item states a requirement; it must appear "
        "in `text` and in the cited source.",
    )

    @model_validator(mode="after")
    def _directive_in_text(self) -> Item:
        if self.directive and self.directive not in self.text.lower():
            raise ValueError(f"directive {self.directive!r} must appear in the item text")
        return self


class Stat(_M):
    value: str = _s(12, "Short number or term shown large, e.g. '4', '3 km', 'D3A'.")
    label: str = _s(60)
    cite: Cites


class Step(_M):
    label: str = _s(40, "A few words, verb first where possible.")
    detail: str | None = Field(default=None, max_length=140)
    cite: Cites


class Event(_M):
    when: str = _s(24, "As written in the source, e.g. 'H-6', 'within 24 hours', 'Phase II'.")
    label: str = _s(60)
    detail: str | None = Field(default=None, max_length=140)
    cite: Cites


class Role(_M):
    key: Key
    name: str = _s(50, "Role name as written in the publication.")
    abbreviation: str | None = Field(default=None, max_length=12)
    duties: list[Item] = Field(min_length=1, max_length=3)
    parent: Key | None = Field(default=None, description="`key` of the role above (hierarchy).")


class Row(_M):
    cells: list[str] = Field(min_length=2, max_length=4)
    cite: Cites


class Column(_M):
    heading: str = _s(40)
    points: list[Item] = Field(min_length=1, max_length=4)


class DecisionNode(_M):
    key: Key
    kind: Literal["question", "outcome"]
    text: str = _s(90)
    yes: Key | None = None
    no: Key | None = None
    cite: Cites


class TermCard(_M):
    term: str = _s(40)
    definition: str = _s(200, "Plain-language definition; the official one goes in notes.")
    cite: Cites


class AcronymEntry(_M):
    abbreviation: str = _s(16)
    meaning: str = _s(80)
    cite: Cites


class Notes(_M):
    """Speaker notes. The renderer appends the verbatim text of every cited node."""

    talking_points: list[Item] = Field(default_factory=list, max_length=5)
    extra_sources: list[NodeId] = Field(
        default_factory=list, description="More nodes whose verbatim text goes in the notes."
    )


# ---------------------------------------------------------------- slides


Callout = Literal["caution", "warning"]


class _Slide(_M):
    id: str = Field(pattern=r"^s\d{2,3}$", description="'s01', 's02', ... in deck order.")
    title: str = _s(70)
    chapter: NodeId | None = Field(
        default=None, description="Division id this slide belongs to, e.g. 'ch-2'."
    )
    notes: Notes = Field(default_factory=Notes)
    callout: Callout | None = Field(
        default=None,
        description="The publication prints this content as a CAUTION or WARNING block: the "
        "renderer labels the slide with that word. Only for content under such a label "
        "(`plan --check` verifies a cited node sits right under it).",
    )

    @model_validator(mode="after")
    def _no_structural_callout(self) -> _Slide:
        if self.callout and type(self).model_fields["pattern"].default in STRUCTURAL_PATTERNS:
            raise ValueError("title, divider, acronyms and closing slides take no callout")
        return self


class TitleSlide(_Slide):
    pattern: Literal["title"] = "title"
    subtitle: str | None = Field(default=None, max_length=120)


class AtAGlanceSlide(_Slide):
    """Purpose, who it applies to, and 2-4 headline facts."""

    pattern: Literal["at_a_glance"] = "at_a_glance"
    purpose: Item
    applies_to: Item
    stats: list[Stat] = Field(default_factory=list, max_length=4)


class TakeawaysSlide(_Slide):
    """'What this means for you': the 3-5 most important points for a junior Soldier."""

    pattern: Literal["takeaways"] = "takeaways"
    items: list[Item] = Field(min_length=3, max_length=5)


class WhatsNewSlide(_Slide):
    pattern: Literal["whats_new"] = "whats_new"
    items: list[Item] = Field(min_length=2, max_length=6)


class DividerSlide(_Slide):
    pattern: Literal["divider"] = "divider"
    number: str | None = Field(default=None, max_length=4, description="'2', 'B'.")
    blurb: Item | None = None


class KeyIdeaSlide(_Slide):
    """One big statement (often a definition) with up to three supporting points."""

    pattern: Literal["key_idea"] = "key_idea"
    statement: Item
    points: list[Item] = Field(default_factory=list, max_length=3)


class ProcessFlowSlide(_Slide):
    pattern: Literal["process_flow"] = "process_flow"
    steps: list[Step] = Field(min_length=3, max_length=7)


class CycleSlide(_Slide):
    """Steps that repeat in a loop, e.g. decide - detect - deliver - assess."""

    pattern: Literal["cycle"] = "cycle"
    steps: list[Step] = Field(min_length=3, max_length=6)
    center_label: str | None = Field(default=None, max_length=30)


class RolesSlide(_Slide):
    pattern: Literal["roles"] = "roles"
    layout: Literal["cards", "hierarchy"] = "cards"
    roles: list[Role] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def _parents(self) -> RolesSlide:
        keys = [r.key for r in self.roles]
        if len(keys) != len(set(keys)):
            raise ValueError("role keys must be unique")
        bad = [r.parent for r in self.roles if r.parent and r.parent not in keys]
        if bad:
            raise ValueError(f"unknown parent role(s): {bad}")
        return self


class TimelineSlide(_Slide):
    pattern: Literal["timeline"] = "timeline"
    events: list[Event] = Field(min_length=3, max_length=7)


class ChecklistSlide(_Slide):
    pattern: Literal["checklist"] = "checklist"
    items: list[Item] = Field(min_length=3, max_length=7)


class DoDontSlide(_Slide):
    pattern: Literal["do_dont"] = "do_dont"
    do: list[Item] = Field(min_length=1, max_length=4)
    dont: list[Item] = Field(min_length=1, max_length=4)


class TableSlide(_Slide):
    """A source table cut down to what a junior Soldier needs (split rather than cram)."""

    pattern: Literal["table"] = "table"
    source_table: NodeId | None = None
    columns: list[str] = Field(min_length=2, max_length=4)
    rows: list[Row] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _widths(self) -> TableSlide:
        if any(len(r.cells) != len(self.columns) for r in self.rows):
            raise ValueError("every row needs one cell per column")
        if any(len(c) > 30 for c in self.columns) or any(
            len(c) > 80 for r in self.rows for c in r.cells
        ):
            raise ValueError("table text too long: headers <= 30 chars, cells <= 80")
        return self


class BigNumbersSlide(_Slide):
    pattern: Literal["big_numbers"] = "big_numbers"
    stats: list[Stat] = Field(min_length=2, max_length=4)
    caveat: Item | None = Field(
        default=None,
        description="One cited line drawn under the numbers when they could be misread "
        "(e.g. 'Don't confuse these with minimum safe distances').",
    )


class ComparisonSlide(_Slide):
    pattern: Literal["comparison"] = "comparison"
    columns: list[Column] = Field(min_length=2, max_length=3)


class DecisionTreeSlide(_Slide):
    pattern: Literal["decision_tree"] = "decision_tree"
    root: Key
    nodes: list[DecisionNode] = Field(min_length=3, max_length=9)

    @model_validator(mode="after")
    def _tree(self) -> DecisionTreeSlide:
        by_key = {n.key: n for n in self.nodes}
        if len(by_key) != len(self.nodes) or self.root not in by_key:
            raise ValueError("node keys must be unique and include the root")
        for n in self.nodes:
            if n.kind == "question" and not (n.yes in by_key and n.no in by_key):
                raise ValueError(f"question {n.key!r} needs yes and no branches that exist")
            if n.kind == "outcome" and (n.yes or n.no):
                raise ValueError(f"outcome {n.key!r} cannot branch")
        seen, stack = set(), [self.root]
        while stack:  # every node reachable, no cycles
            k = stack.pop()
            if k in seen:
                raise ValueError("decision tree has a cycle or a shared branch")
            seen.add(k)
            stack += [c for c in (by_key[k].yes, by_key[k].no) if c]
        if seen != set(by_key):
            raise ValueError("some decision nodes are unreachable from the root")
        return self


class KeyTermsSlide(_Slide):
    pattern: Literal["key_terms"] = "key_terms"
    terms: list[TermCard] = Field(min_length=2, max_length=6)


class AcronymsSlide(_Slide):
    pattern: Literal["acronyms"] = "acronyms"
    entries: list[AcronymEntry] = Field(min_length=4, max_length=24)


class ClosingSlide(_Slide):
    """'Read the full text': where to go next. The renderer repeats the disclaimer."""

    pattern: Literal["closing"] = "closing"
    items: list[Item] = Field(min_length=1, max_length=4)


Slide = Annotated[
    TitleSlide
    | AtAGlanceSlide
    | TakeawaysSlide
    | WhatsNewSlide
    | DividerSlide
    | KeyIdeaSlide
    | ProcessFlowSlide
    | CycleSlide
    | RolesSlide
    | TimelineSlide
    | ChecklistSlide
    | DoDontSlide
    | TableSlide
    | BigNumbersSlide
    | ComparisonSlide
    | DecisionTreeSlide
    | KeyTermsSlide
    | AcronymsSlide
    | ClosingSlide,
    Field(discriminator="pattern"),
]

SLIDE_TYPES: tuple[type[_Slide], ...] = get_args(get_args(Slide)[0])
PATTERNS: tuple[str, ...] = tuple(t.model_fields["pattern"].default for t in SLIDE_TYPES)
#: Patterns that draw a picture rather than a list (scope §8: >= 60% of content slides).
VISUAL_PATTERNS = frozenset(
    {
        "process_flow", "cycle", "roles", "timeline", "do_dont", "table", "big_numbers",
        "comparison", "decision_tree", "key_terms", "key_idea", "at_a_glance",
    }
)  # fmt: skip
STRUCTURAL_PATTERNS = frozenset({"title", "divider", "acronyms", "closing"})


class PubRef(_M):
    pub_id: str = Field(description="e.g. 'FM-3-09'")
    short_name: str = Field(description="As printed in footers, e.g. 'FM 3-09'.")
    title: str
    pub_date: str | None = None
    source_sha256: str = Field(description="Ties the spec to the exact PDF the tree came from.")


class SlideSpec(_M):
    spec_version: Literal["1.0", "1.1"] = SPEC_VERSION
    pub: PubRef
    audience: Literal["junior Soldiers"] = "junior Soldiers"
    disclaimer: Literal[DISCLAIMER] = DISCLAIMER  # type: ignore[valid-type]
    slides: list[Slide] = Field(min_length=3, max_length=60)

    @model_validator(mode="after")
    def _deck_shape(self) -> SlideSpec:
        ids = [s.id for s in self.slides]
        expected = [f"s{i:02d}" for i in range(1, len(ids) + 1)]
        if ids != expected:
            raise ValueError(f"slide ids must run s01, s02, ... in order; got {ids[:5]}...")
        if self.slides[0].pattern != "title":
            raise ValueError("the first slide must be the title slide")
        if self.slides[-1].pattern != "closing":
            raise ValueError("the last slide must be the closing slide")
        return self

    def cited_ids(self) -> set[str]:
        """Every node id the spec cites (for `plan --check`)."""
        out: set[str] = set()

        def visit(v: object) -> None:
            if isinstance(v, BaseModel):
                for name, val in v:
                    if name in ("cite", "extra_sources") and isinstance(val, list):
                        out.update(val)
                    elif name == "source_table" and isinstance(val, str):
                        out.add(val)
                    else:
                        visit(val)
            elif isinstance(v, list):
                for x in v:
                    visit(x)

        visit(self)
        return out
