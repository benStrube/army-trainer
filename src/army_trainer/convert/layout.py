"""Layout signals read straight from the PDF with PyMuPDF.

pymupdf4llm gives good body text but labels heading levels inconsistently from page to page.
Army publications use a fixed set of heading styles, so the real hierarchy comes from fonts:

    T1  Arial Bold >= 15.5 pt     chapter/appendix title, Preface, Glossary, ...
    LBL Arial Bold 12 pt          "Chapter 2" / "Appendix A" label above a T1 title
    T2  Arial Bold 12 pt          "SECTION I - ..."
    T3  Times Bold 14 pt          major heading
    T4  Times Bold 12 pt          sub-heading (often small caps: 12 pt + 9.5 pt spans)
    T5  Times Bold 11 pt          minor heading
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

HEADER_Y = 55.0  # running header sits above this (points from top, Letter page)
FOOTER_Y = 735.0  # running footer sits below this

TIERS = ("T1", "T2", "T3", "T4", "T5")
_LABEL = re.compile(r"^(Chapter \d+|Appendix [A-Z])$")
_PAGE_LABEL = re.compile(r"^(?:[A-Z]|\d+|Glossary|References|Index|Source Notes)-\d+$|^[ivxlc]+$")


@dataclass
class Heading:
    page: int  # 1-based PDF page
    tier: str
    text: str
    y: float
    label: str | None = None  # "Chapter 2" for a chapter title


@dataclass
class PageLayout:
    page: int
    label: str | None = None  # printed page number, e.g. "1-3", "vii"
    headings: list[Heading] = field(default_factory=list)


def _line_text(spans: list[dict]) -> str:
    return re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()


def _tier(spans: list[dict], text: str) -> str | None:
    fonts = [s["font"] for s in spans]
    if not all("Bold" in f for f in fonts) or any("Italic" in f for f in fonts):
        return None
    size = max(s["size"] for s in spans)
    arial = all(f.startswith(("Arial", "Helvetica")) for f in fonts)
    times = all(f.startswith(("TimesNewRoman", "Times")) for f in fonts)
    if arial and size >= 15.5:
        return "T1"
    if arial and 11.5 <= size < 12.5:
        if _LABEL.match(text):
            return "LBL"
        if text.upper().startswith("SECTION "):
            return "T2"
        return "T2+"  # second line of a wrapped section heading; dropped if orphaned
    if times and 13.5 <= size < 14.5:
        return "T3"
    if times and 11.5 <= size < 12.5:
        return "T4"
    if times and 10.5 <= size < 11.5:
        return "T5"
    return None


def scan_page(page: pymupdf.Page) -> PageLayout:
    pno = page.number + 1
    out = PageLayout(page=pno)
    lines: list[tuple[str, str, float, float]] = []  # tier, text, y0, size
    for block in page.get_text("dict")["blocks"]:
        for ln in block.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            y0, y1 = ln["bbox"][1], ln["bbox"][3]
            text = _line_text(ln["spans"])  # keep whitespace-only spans: they carry the spaces
            if y0 > FOOTER_Y and _PAGE_LABEL.match(text):
                out.label = text
            if y1 < HEADER_Y or y0 > FOOTER_Y:
                continue
            tier = _tier(spans, text)
            if tier:
                lines.append((tier, text, y0, max(s["size"] for s in spans)))
    lines.sort(key=lambda t: t[2])

    pending_label: str | None = None
    last_y = -1e9
    for tier, text, y0, size in lines:
        if tier == "LBL":
            pending_label = text
            continue
        prev = out.headings[-1] if out.headings else None
        if tier == "T2+":
            if prev and prev.tier == "T2" and 0 < y0 - last_y <= 1.6 * size:
                prev.text = f"{prev.text} {text}"
                last_y = y0
            continue
        # A heading that wraps onto a second line: same tier, directly below the last line.
        if prev and prev.tier == tier and 0 < y0 - last_y <= 1.6 * size:
            prev.text = f"{prev.text} {text}"
            last_y = y0
            continue
        h = Heading(page=pno, tier=tier, text=text, y=y0)
        if tier == "T1" and pending_label:
            h.label = pending_label
        pending_label = None
        out.headings.append(h)
        last_y = y0
    # bold run-in sentences are not headings
    out.headings = [
        h
        for h in out.headings
        if h.tier in ("T1", "T2") or (len(h.text) <= 150 and not h.text.endswith("."))
    ]
    return out


def scan(doc: pymupdf.Document) -> list[PageLayout]:
    return [scan_page(p) for p in doc]


def document_title(layouts: list[PageLayout], pages: int = 4) -> str | None:
    """Title as printed above the Contents: the first T1 heading on the opening pages that
    isn't the publication number, a distribution line, or a list heading."""
    skip = re.compile(r"^([A-Z]{2,4} \d|Contents$|Figures$|Tables$)|DISTRIBUTION", re.I)
    for pl in layouts[:pages]:
        for h in pl.headings:
            if h.tier == "T1" and not skip.search(h.text):
                return h.text
    return None
