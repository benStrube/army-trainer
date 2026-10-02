"""Markdown blocks and the clean-up passes that run on them.

Every pass here is a pure function over a list of `Block`s so it can be unit-tested without a
PDF. `pipeline.py` wires them together.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .layout import Heading, PageLayout

# ---------------------------------------------------------------- model


@dataclass
class Block:
    kind: str  # heading | caption | table | bullet | para | bold | mdheading
    text: str
    page: int
    level: int = 0  # headings: Markdown level
    tier: str = ""  # headings: layout tier (T1..T5)
    rows: list[list[str]] = field(default_factory=list)  # tables: header row first
    zone: str = ""  # set by assign_zones


# (first page of the table, garbled key text) -> key text in reading order, or None
LegendSource = Callable[[int, str], str | None]

CAPTION = re.compile(r"^(?:Introductory )?(Table|Figure) ([A-Z]?-?\d+(?:-\d+)?)\.?\s")
PARA_NUM = re.compile(r"^\**([A-Z]|\d+)-\d+\.\**\s")
_TAGS = re.compile(r"</?(?:mark|u)>")
_PUA_BULLET = re.compile("^[\uf06c\uf0a7\uf0b7\u2022]\\s*")
# bullet glyphs inside table cells: Symbol/Wingdings private-use points -> real bullets
_CELL_BULLETS = [
    (re.compile("[\u2022\uf06c\uf0b7]\\s*(?:<br>)?\\s*"), "\u2022 "),
    (re.compile("\uf0a7\\s*(?:<br>)?\\s*"), "\u25e6 "),
]
# pymupdf4llm drops the space after closing emphasis: "_Destroy_is" -> "_Destroy_ is"
_EMPH_SPACE = re.compile(
    r"(?<![\w*])(?:(\*\*)(?=\S)([^*|\n]+?)(?<=\S)\*\*|(_)(?=\S)([^_|\n]+?)(?<=\S)_)(?=[A-Za-z0-9])"
)
_TERMINAL = tuple('.:;?!"”’)')
_CONNECTORS = {
    "a", "an", "the", "and", "or", "nor", "but", "of", "to", "in", "on", "for", "with", "by",
    "as", "at", "from", "that", "which", "is", "are", "be", "will", "must", "may", "its", "their",
}  # fmt: skip


def norm(s: str) -> str:
    """Comparison key: letters and digits only, lower case, emphasis and tags removed."""
    return re.sub(r"[^a-z0-9]+", "", _TAGS.sub("", s).lower())


def plain(s: str) -> str:
    """Text without Markdown emphasis markers, tags, or heading hashes."""
    s = _TAGS.sub("", s)
    s = re.sub(r"^#+\s*", "", s.strip())
    return re.sub(r"\*\*|(?<!\w)_|_(?!\w)", "", s).strip()


# ---------------------------------------------------------------- parsing


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip() for c in inner.split("|")]


def fix_text(s: str) -> str:
    # bold runs that a cell line-wrap split in two: "**and**<br>** forms**" -> one run
    s = re.sub(r"\*\*[ \t]*<br>[ \t]*\*\*[ \t]*", " ", s)
    s = re.sub(r"\*\*[ \t]+\*\*[ \t]*", " ", s)
    # <br> inside cells is mostly soft wrapping; keep it only before a list bullet
    s = re.sub(r"[ \t]*<br>[ \t]*(?![\u2022\uf06c\uf0b7\uf0a7])", " ", s)
    s = _EMPH_SPACE.sub(lambda m: f"{m.group(0)} ", s)
    for pat, rep in _CELL_BULLETS:
        s = pat.sub(rep, s)
    return s


def parse_page(md: str, page: int) -> list[Block]:
    """Split one page of pymupdf4llm Markdown into typed blocks."""
    md = fix_text(_TAGS.sub("", md))
    blocks: list[Block] = []
    for chunk in re.split(r"\n\s*\n", md):
        lines = [ln.rstrip() for ln in chunk.strip("\n").splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].lstrip().startswith("|"):
            rows = [_split_row(ln) for ln in lines if not re.match(r"^\s*\|[\s:|-]+\|\s*$", ln)]
            blocks.append(Block("table", "", page, rows=rows))
            continue
        # lists come through one item per line; anything else is one paragraph
        buf: list[str] = []
        in_bullet = False
        base: int | None = None  # indent of top-level list items in this chunk
        for ln in lines:
            indent = len(ln) - len(ln.lstrip())
            s = _PUA_BULLET.sub("- ", ln.strip())
            if s.startswith("- ") and PARA_NUM.match(s[2:]):
                s = s[2:]  # a numbered paragraph that leads into a list, not a list item
                base = None
            if s.startswith(("#", "- ")):
                if buf:
                    blocks.append(Block("para", " ".join(buf), page))
                    buf = []
                kind = "mdheading" if s.startswith("#") else "bullet"
                if kind == "bullet":
                    base = indent if base is None else min(base, indent)
                    depth = min(2, max(0, (indent - base) // 2))
                    s = "  " * depth + s
                blocks.append(Block(kind, s, page))
                in_bullet = kind == "bullet"
            elif PARA_NUM.match(s):
                if buf:
                    blocks.append(Block("para", " ".join(buf), page))
                buf = [s]
                in_bullet = False
            elif in_bullet:
                blocks[-1].text += " " + s  # wrapped list item
            else:
                buf.append(s)
        if buf:
            text = " ".join(buf)
            kind = "bold" if re.fullmatch(r"\*\*[^*]+\*\*", text.strip()) else "para"
            blocks.append(Block(kind, text, page))
    for b in blocks:
        if b.kind in ("bold", "mdheading", "para") and CAPTION.match(plain(b.text)):
            b.kind, b.text = "caption", plain(b.text)
    return blocks


# ---------------------------------------------------------------- headings


def _heading_text(h: Heading) -> str:
    return f"{h.label}: {h.text}" if h.label else h.text


def resolve_headings(blocks: list[Block], layout: PageLayout) -> list[str]:
    """Replace pymupdf4llm's heading guesses with the PDF's real headings.

    Returns the texts of real headings that could not be placed (for the report)."""
    labels = {norm(h.label) for h in layout.headings if h.label}
    todo = list(layout.headings)
    out: list[Block] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind in ("mdheading", "bold", "para") and norm(b.text) in labels:
            i += 1  # "Chapter 2" label line; folded into the title heading
            continue
        matched = False
        if b.kind == "table" and b.rows and todo:
            first = norm("".join(b.rows[0]))
            h = next((h for h in todo[:3] if norm(h.text) == first), None)
            if h:
                out.append(Block("heading", _heading_text(h), b.page, tier=h.tier))
                todo.remove(h)
                b.rows = b.rows[1:]
                if b.rows:
                    out.append(b)
                i += 1
                continue
        if b.kind in ("mdheading", "bold", "para") and todo:
            key = norm(b.text)
            for h in todo[:3]:
                target = norm(h.text)
                # the heading may be split over two Markdown lines
                span, acc = 1, key
                while acc != target and target.startswith(acc) and i + span < len(blocks):
                    acc += norm(blocks[i + span].text)
                    span += 1
                if acc == target:
                    out.append(Block("heading", _heading_text(h), b.page, tier=h.tier))
                    todo.remove(h)
                    i += span
                    matched = True
                    break
        if matched:
            continue
        if b.kind == "mdheading":
            b.kind, b.text = "bold", f"**{plain(b.text)}**"
        out.append(b)
        i += 1
    blocks[:] = out
    return [h.text for h in todo]


ZONE_DROP = re.compile(r"^(Contents|Figures|Tables)$", re.I)
ZONE_KEEP = re.compile(
    r"^(Preface|Introduction|Chapter \d+|Appendix [A-Z]|Source Notes|Glossary|References)", re.I
)


def assign_zones(blocks: list[Block]) -> list[Block]:
    """Tag blocks with their T1 zone and drop front matter lists, the index, and anything
    before the Preface. Then set Markdown heading levels per zone from the tiers present."""
    zone = ""
    kept: list[Block] = []
    for b in blocks:
        if b.kind == "heading" and b.tier == "T1":
            title = b.text
            if re.match(r"^Index$", title, re.I):
                break  # index and the authentication page after it
            if ZONE_DROP.match(title):
                zone = ""
            elif ZONE_KEEP.match(title):
                zone = title.split(":")[0]
            else:
                zone = zone if zone else ""
        if not zone:
            continue
        b.zone = zone
        kept.append(b)

    by_zone: dict[str, set[str]] = {}
    for b in kept:
        if b.kind == "heading" and b.tier != "T1":
            by_zone.setdefault(b.zone, set()).add(b.tier)
    for b in kept:
        if b.kind == "heading":
            tiers = sorted(by_zone.get(b.zone, set()))
            b.level = 1 if b.tier == "T1" else 2 + tiers.index(b.tier)
    return kept


# ---------------------------------------------------------------- tables


def _caption_id(text: str) -> str | None:
    m = CAPTION.match(text)
    return f"{m.group(1)} {m.group(2)}" if m else None


def merge_continued_tables(blocks: list[Block]) -> int:
    """Join "(continued)" table parts into the first part. Returns the number of merges."""
    out: list[Block] = []
    merges = 0
    last_table: Block | None = None
    last_id: str | None = None
    pending_continue = False
    for b in blocks:
        if b.kind == "caption":
            cid = _caption_id(b.text)
            if cid and cid == last_id and "(continued)" in b.text:
                pending_continue = last_table is not None
                continue
            last_id, last_table, pending_continue = cid, None, False
        elif b.kind == "table":
            if pending_continue and last_table is not None:
                rows = b.rows
                if rows and [norm(c) for c in rows[0]] == [norm(c) for c in last_table.rows[0]]:
                    rows = rows[1:]
                last_table.rows.extend(rows)
                merges += 1
                pending_continue = False
                continue
            if last_id and last_id.startswith("Table") and last_table is None:
                last_table = b
        elif b.kind == "heading":
            last_id, last_table, pending_continue = None, None, False
        out.append(b)
    blocks[:] = out
    return merges


def _word_split(a: str, b: str) -> bool:
    """True when cell `a` ends mid-word and cell `b` carries on the same word."""
    a, b = plain(a), plain(b)
    return bool(a and b and a[-1].islower() and b[0].islower())


# "ACM – airspace coordinating measure, C2 – command and control" (an abbreviation key)
_LEGEND = re.compile(r"(?:[A-Z][A-Za-z0-9/]+\s*[–-]\s*[^,]+,\s*)+[A-Z][A-Za-z0-9/]+\s*[–-]\s*\S.*")


_ABBR = re.compile(r"\b([A-Z][A-Z0-9/]+)\s*[–-]\s*(?=[a-zA-Z])")


def legend_abbreviations(text: str) -> set[str]:
    return set(_ABBR.findall(text))


def _tidy_cell(c: str) -> str:
    """Merge per-word emphasis ("_Direct_ _Support_" -> "_Direct Support_")."""
    c = re.sub(r"(?<=\w)_ _(?=\w)", " ", c)
    return re.sub(r"\s{2,}", " ", c).strip()


def repair_table(t: Block, legend_source: LegendSource | None = None) -> tuple[Block | None, int]:
    """Fix common pymupdf4llm table faults in place. Returns (legend paragraph or None,
    number of rows repaired).

    * a full-width row (title or legend) split across columns mid-word -> one cell
    * a body row with an empty first cell -> continuation of the row above
    * a final legend row (``ACM – airspace ..., C2 – ...``) -> paragraph after the table
    """
    fixes = 0
    rows = t.rows
    width = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([""] * (width - len(r)))

    for r in rows:
        filled = [k for k, c in enumerate(r) if c]
        if len(filled) > 1 and any(
            _word_split(r[a], r[b]) for a, b in zip(filled, filled[1:], strict=False)
        ):
            joined = "".join(r[k] for k in filled)
            r[:] = [joined] + [""] * (width - 1)
            fixes += 1

    legend: Block | None = None
    if len(rows) > 2:
        joined = plain("".join(c for c in rows[-1] if c))
        if _LEGEND.fullmatch(joined):
            # pymupdf4llm reads a multi-line key column by column; prefer the PDF's own
            # reading order when it carries exactly the same abbreviations
            better = legend_source(t.page, joined) if legend_source else None
            legend = Block("note", better or joined, t.page)
            rows.pop()
            fixes += 1

    body: list[list[str]] = [rows[0]] if rows else []
    for r in rows[1:]:
        if len(body) > 1 and not r[0] and any(r[1:]):
            prev = body[-1]
            for k in range(1, width):
                if r[k]:
                    prev[k] = f"{prev[k]}<br>{r[k]}" if prev[k] else r[k]
            fixes += 1
        else:
            body.append(r)
    # drop columns that are empty in every row
    keep = [k for k in range(width) if any(r[k] for r in body)]
    t.rows = [[_tidy_cell(r[k]) for k in keep] for r in body]
    if t.rows:  # Markdown already bolds the header row; per-word emphasis there is noise
        t.rows[0] = [plain(c) for c in t.rows[0]]
    return legend, fixes


def absorb_table_overflow(blocks: list[Block]) -> int:
    """pymupdf4llm sometimes cuts the last cell of a table short at the page bottom and then
    repeats the whole cell as a paragraph after the table. Put the full text back in the cell
    and drop the duplicate."""
    fixes = 0
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if b.kind == "para" and prev is not None and prev.kind == "table" and prev.rows:
            key = norm(b.text)
            for k, cell in enumerate(prev.rows[-1]):
                ck = norm(cell)
                if len(ck) >= 40 and key.startswith(ck[: max(40, len(ck) - 10)]):
                    if len(key) >= len(ck):
                        prev.rows[-1][k] = b.text
                    fixes += 1
                    break
            else:
                out.append(b)
            continue
        out.append(b)
    blocks[:] = out
    return fixes


def repair_tables(blocks: list[Block], legend_source: LegendSource | None = None) -> int:
    out: list[Block] = []
    fixes = 0
    for b in blocks:
        out.append(b)
        if b.kind == "table" and b.rows:
            legend, n = repair_table(b, legend_source)
            fixes += n
            if legend:
                legend.zone = b.zone
                out.append(legend)
    blocks[:] = out
    return fixes


def render_table(t: Block) -> str:
    rows = t.rows
    width = max(len(r) for r in rows)
    esc = [[c.replace("|", "\\|") for c in r] + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(esc[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in esc[1:]]
    return "\n".join(lines)


# ---------------------------------------------------------------- page-break joins


def _ends_open(text: str) -> bool:
    s = plain(text).rstrip()
    if not s or s.endswith(_TERMINAL) or _LEGEND.fullmatch(s):
        return False
    last = re.findall(r"[A-Za-z]+$", s)
    return (
        s.endswith(("-", ",", "–"))
        or (bool(last) and last[0].lower() in _CONNECTORS)
        or s[-1].isalnum()
    )


def _starts_continuation(text: str) -> bool:
    s = plain(text)
    if not s or PARA_NUM.match(text) or CAPTION.match(s):
        return False
    return s[0].islower() or s[0].isdigit() or s[0] in '(“"'


def join_page_breaks(blocks: list[Block], log: list[tuple[str, str]] | None = None) -> int:
    """Re-join paragraphs and list items that a page break split in two.

    `log`, if given, collects (end of first part, start of second part) for review."""
    joins = 0
    i = 0
    while i < len(blocks) - 1:
        a = blocks[i]
        if a.kind not in ("para", "bullet") or not _ends_open(a.text):
            i += 1
            continue
        # the continuation is the first paragraph on a later page, possibly after a
        # table or caption that the layout placed at the top of that page
        j = i + 1
        while j < len(blocks) and j <= i + 4 and blocks[j].kind in ("table", "caption"):
            j += 1
        if j >= len(blocks):
            break
        b = blocks[j]
        later_page = b.page > a.page
        tail = plain(a.text).rstrip()
        strong = (
            tail.endswith(("-", ","))
            or tail.split()[-1].lower() in _CONNECTORS
            # body paragraphs (and sentence-length list items) end in punctuation;
            # a bare word means the page break cut them
            or (tail[-1].islower() and (a.kind == "para" or len(tail.split()) >= 8))
        )
        if (
            later_page
            and b.kind == "para"
            and (_starts_continuation(b.text) or (strong and not PARA_NUM.match(b.text)))
        ):
            if log is not None:
                log.append((a.text[-60:], b.text[:60]))
            sep = "" if tail.endswith("-") else " "
            a.text = a.text.rstrip() + sep + b.text.lstrip()
            del blocks[j]
            joins += 1
            continue
        i += 1
    return joins


# ---------------------------------------------------------------- glossary


def format_glossary(blocks: list[Block]) -> int:
    """Glossary: one acronym table, and ``**term** — definition`` lines for terms."""
    out: list[Block] = []
    terms = 0
    acronyms: Block | None = None
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.zone != "Glossary":
            out.append(b)
            i += 1
            continue
        if b.kind == "heading":
            acronyms = None
        if b.kind == "table":
            if acronyms is None:
                acronyms = Block("table", "", b.page, rows=[["Acronym", "Meaning"]], zone=b.zone)
                out.append(acronyms)
            acronyms.rows.extend(r for r in b.rows if any(r))
            i += 1
            continue
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if b.kind == "bold" and nxt is not None and nxt.kind == "para":
            out.append(Block("para", f"{b.text.strip()} — {nxt.text.strip()}", b.page, zone=b.zone))
            terms += 1
            i += 2
            continue
        out.append(b)
        i += 1
    blocks[:] = out
    return terms


# ---------------------------------------------------------------- output


def render(blocks: list[Block], page_labels: dict[int, str | None]) -> str:
    parts: list[str] = []
    page = None
    for b in blocks:
        if b.page != page:
            page = b.page
            label = page_labels.get(page)
            parts.append(f"<!-- page {page}" + (f" ({label})" if label else "") + " -->")
        if b.kind == "heading":
            parts.append("#" * b.level + " " + b.text)
        elif b.kind == "caption":
            parts.append(f"**{b.text}**")
        elif b.kind == "table":
            if b.rows:
                parts.append(render_table(b))
        else:
            parts.append(b.text)
    return "\n\n".join(parts) + "\n"
