"""Assemble a deck: pattern slides on the base template, plus footers with citations, slide
numbers, speaker notes with the verbatim cited text, and overflow splitting (WP 3.2-3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from lxml import etree
from pptx import Presentation

from ..plan.check import _cited_objects
from ..plan.nodes import NodeIndex
from ..plan.spec import SlideSpec
from ..structure.models import DocTree
from . import theme as t
from .patterns import REGISTRY
from .shapes import Ctx, P
from .template import DEFAULT_PATH

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
MAX_FOOTER_CITES = 5
FOOTER_TAG = "Unofficial training aid"
NO_FOOTER = {"title"}

# pattern -> (list field, minimum items per slide) for overflow splitting
SPLITTABLE = {
    "table": ("rows", 1),
    "acronyms": ("entries", 4),
    "checklist": ("items", 3),
    "whats_new": ("items", 2),
    "key_terms": ("terms", 2),
}


@dataclass
class DeckResult:
    ctx: Ctx
    slide_count: int = 0
    splits: list[str] = field(default_factory=list)  # ids of spec slides that were split
    unsplit_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- citations


def short_cite(idx: NodeIndex, node_id: str) -> str:
    """Footer label for a node. List items and loose text cite their paragraph, not the page."""
    node = idx.get(node_id)
    if node.type in ("list_item", "text"):
        for anc in reversed(idx.by_id[node_id].ancestors):
            if anc.type == "paragraph":
                return anc.cite
    return node.cite


def slide_cites(idx: NodeIndex, slide) -> list[str]:
    ids = {c for _, obj in _cited_objects(slide, slide.id) for c in obj.cite if c in idx}
    ids |= {c for c in slide.notes.extra_sources if c in idx}
    out: list[str] = []
    for node_id in sorted(ids, key=idx.order.__getitem__):
        label = short_cite(idx, node_id)
        if label not in out:
            out.append(label)
    return out


def footer_text(short_name: str, cites: list[str], tag: str) -> str:
    """e.g. 'FM 3-09 · paras 2-17, 2-19 +3 more · table 4-1 · Unofficial training aid'."""
    paras = [c.removeprefix("para ") for c in cites if c.startswith("para ")]
    others = [c for c in cites if not c.startswith("para ")]
    parts: list[str] = []
    if paras:
        shown = paras[:MAX_FOOTER_CITES]
        more = len(paras) - len(shown)
        parts.append(
            f"{'para' if len(paras) == 1 else 'paras'} {', '.join(shown)}"
            + (f" +{more} more" if more else "")
        )
    if others:
        parts.append(
            ", ".join(others[:2]) + (f" +{len(others) - 2} more" if len(others) > 2 else "")
        )
    return " · ".join([short_name, *parts, tag])


# ---------------------------------------------------------------- notes


def notes_text(idx: NodeIndex, slide) -> str:
    lines: list[str] = []
    if slide.notes.talking_points:
        lines.append("TALKING POINTS")
        lines += [f"- {tp.text}" for tp in slide.notes.talking_points]
        lines.append("")
    ids = {c for _, obj in _cited_objects(slide, slide.id) for c in obj.cite if c in idx}
    ids |= {c for c in slide.notes.extra_sources if c in idx}
    # drop nodes whose text is already covered by a cited ancestor
    ids = {i for i in ids if not any(a.id in ids for a in idx.by_id[i].ancestors)}
    if ids:
        lines.append("SOURCE TEXT (verbatim from the publication)")
        for node_id in sorted(ids, key=idx.order.__getitem__):
            lines.append(f"[{short_cite(idx, node_id)}] {idx.text(node_id)}")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- footer placeholders


def _add_placeholder(
    slide, layout, ph_type: int, text: str, color: str, field_type: str | None = None
) -> None:
    src = next((p for p in layout.placeholders if p.placeholder_format.type == ph_type), None)
    if src is None:
        return
    pf = src.placeholder_format
    kind = "ftr" if ph_type == 15 else "sldNum"
    rpr = (
        f'<a:rPr lang="en-US" sz="{t.FOOTER_PT * 100}"><a:solidFill><a:srgbClr val="{color}"/>'
        f'</a:solidFill><a:latin typeface="{t.FONT}"/></a:rPr>'
    )
    algn = "l" if ph_type == 15 else "r"
    sid = max(int(i) for i in slide.shapes._spTree.xpath("//p:cNvPr/@id")) + 1
    if field_type:
        run = f'<a:fld id="{{{str(uuid4()).upper()}}}" type="{field_type}">{rpr}<a:t/></a:fld>'
    else:
        run = f"<a:r>{rpr}<a:t/></a:r>"
    xml = (
        f'<p:sp xmlns:p="{NS_P}" xmlns:a="{NS_A}"><p:nvSpPr>'
        f'<p:cNvPr id="{sid}" name="{src.name}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr><p:ph type="{kind}" sz="quarter" idx="{pf.idx}"/></p:nvPr></p:nvSpPr>'
        f'<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="{algn}"/>{run}</a:p>'
        "</p:txBody></p:sp>"
    )
    el = etree.fromstring(xml)
    el.find(f".//{{{NS_A}}}t").text = text  # escapes &, <, > in citations
    slide.shapes._spTree.append(el)


def add_footer(slide, layout, text: str, number: int) -> None:
    color = P.white if layout.name == "Section Header" else P.mid_gray
    _add_placeholder(slide, layout, 15, text, color)
    _add_placeholder(slide, layout, 13, str(number), color, "slidenum")


# ---------------------------------------------------------------- splitting


def _split_once(s):
    name, floor = SPLITTABLE[s.pattern]
    items = getattr(s, name)
    if len(items) < 2 * floor:
        return None
    k = (len(items) + 1) // 2
    return [s.model_copy(update={name: items[:k]}), s.model_copy(update={name: items[k:]})]


def _pieces(s, fits) -> list:
    if s.pattern not in SPLITTABLE or fits(s):
        return [s]
    halves = _split_once(s)
    if halves is None:
        return [s]
    return [p for h in halves for p in _pieces(h, fits)]


# ---------------------------------------------------------------- deck


def render_slides(
    spec: SlideSpec, out: Path, template: Path = DEFAULT_PATH, only: set[str] | None = None
) -> Ctx:
    """Pattern slides only (no footers, notes or splitting). Used for pattern samples."""
    prs = Presentation(template)
    layouts = {la.name: la for la in prs.slide_layouts}
    ctx = Ctx(short_name=spec.pub.short_name, disclaimer=spec.disclaimer)
    for s in spec.slides:
        if only and s.id not in only:
            continue
        layout_name, fn = REGISTRY[s.pattern]
        fn(prs.slides.add_slide(layouts[layout_name]), s, ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    return ctx


def render_deck(
    spec: SlideSpec, tree: DocTree, out: Path, template: Path = DEFAULT_PATH
) -> DeckResult:
    idx = NodeIndex(tree)
    prs = Presentation(template)
    layouts = {la.name: la for la in prs.slide_layouts}
    ctx = Ctx(short_name=spec.pub.short_name, disclaimer=spec.disclaimer)
    result = DeckResult(ctx)
    scratch = Presentation(template)

    def fits(s) -> bool:
        probe = Ctx(short_name=ctx.short_name, disclaimer=ctx.disclaimer)
        layout_name, fn = REGISTRY[s.pattern]
        fn(
            scratch.slides.add_slide({la.name: la for la in scratch.slide_layouts}[layout_name]),
            s,
            probe,
        )
        return not probe.warnings

    n = 0
    for s in spec.slides:
        pieces = _pieces(s, fits)
        if len(pieces) > 1:
            result.splits.append(s.id)
        for i, piece in enumerate(pieces):
            if len(pieces) > 1:
                piece = piece.model_copy(update={"title": f"{s.title} ({i + 1} of {len(pieces)})"})
            n += 1
            layout_name, fn = REGISTRY[piece.pattern]
            layout = layouts[layout_name]
            slide = prs.slides.add_slide(layout)
            before = len(ctx.warnings)
            fn(slide, piece, ctx)
            result.unsplit_warnings += [f"{s.id}: {w}" for w in ctx.warnings[before:]]
            if piece.pattern not in NO_FOOTER:
                add_footer(
                    slide,
                    layout,
                    footer_text(
                        spec.pub.short_name, slide_cites(idx, piece), "Unofficial training aid"
                    ),
                    n,
                )
            notes = notes_text(idx, piece)
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
    result.slide_count = n
    cp = prs.core_properties
    cp.title = f"{spec.pub.short_name}: {spec.pub.title} (unofficial training aid)"
    cp.author = "army-trainer"
    cp.subject = t.DISCLAIMER
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    return result
