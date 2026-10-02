"""Rebuild damaged tables from the PDF's own ruling lines (WP 5.1a, Opus-owned).

pymupdf4llm flattens tables with merged cells, rotated labels or a key printed inside the
border badly: header rows are glued together, a merged label is cut into fragments ("ment"),
key lines become table rows, the last cell overflows into a junk row. PyMuPDF's
`page.find_tables()` follows the ruling lines instead, so it knows which cells are merged.

For each table block this module rebuilds the table from `find_tables()` and keeps the rebuild
only when it matches the words the PDF prints inside the table border clearly better (word
recall up, stray tokens down). Well-formed tables are left as they were.

Merged cells: a cell that spans several rows is either a label for all of them ("Decide",
"Plan": one line of text) or a column with no row rules of its own whose lines belong to
different rows (the Joint Targeting Cycle column of table 3-1). A one-band cell is repeated in
every row it spans; a multi-band cell is split by the vertical position of each line.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import pymupdf

from .blocks import Block, fix_text, norm

#: minimum score gain before a rebuild replaces pymupdf4llm's table
MIN_GAIN = 0.02
_BULLET = re.compile("^[•▪−–]")
_LEGEND_ROW = re.compile(r"^(?:Note[s]?\b|[A-Z][A-Za-z0-9/]*(?:\s[A-Z][a-z]+)?\s*[–-]{1,2}\s*\S)")


@dataclass
class Rebuilt:
    rows: list[list[str]]  # header first
    notes: list[str]  # key and note lines printed inside the table border
    bbox: tuple[float, float, float, float]


def _tokens(s: str) -> list[str]:
    return [t for t in (norm(w) for w in re.split(r"[\s/|]+|<br>", s)) if t]


def _lines(page: pymupdf.Page, rect: pymupdf.Rect) -> list[tuple[float, str]]:
    """Text lines inside `rect` as (vertical centre, text), top to bottom. Rotated lines (a
    vertical "Continuous Assessment" label) keep PyMuPDF's reading order along the line."""
    out = []
    for block in page.get_text("dict", clip=rect)["blocks"]:
        for line in block.get("lines", []):
            x0, y0, x1, y1 = line["bbox"]
            if not rect.contains(pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                continue
            text = _styled(line["spans"])
            if text:
                out.append(((y0 + y1) / 2, text))
    out.sort(key=lambda t: t[0])
    return out


def _styled(spans: list[dict]) -> str:
    """Join spans, marking bold runs with ** and italic runs with _ (as pymupdf4llm does)."""
    runs: list[list] = []  # [bold, italic, superscript, text]
    for sp in spans:
        bold = bool(sp["flags"] & 16) or "Bold" in sp["font"]
        italic = bool(sp["flags"] & 2) or "Italic" in sp["font"]
        sup = bool(sp["flags"] & 1)  # footnote markers: "Own Observers.<sup>1</sup>"
        if not sp["text"].strip():
            bold, italic, sup = runs[-1][:3] if runs else (False, False, False)
        if runs and runs[-1][:3] == [bold, italic, sup]:
            runs[-1][3] += sp["text"]
        else:
            runs.append([bold, italic, sup, sp["text"]])
    out = ""
    for bold, italic, sup, text in runs:
        core = text.strip()
        if not core:
            out += text
            continue
        lead, trail = text[: len(text) - len(text.lstrip())], text[len(text.rstrip()) :]
        if sup:
            out += lead + f"<sup>{core}</sup>" + trail
            continue
        if italic:
            core = f"_{core}_"
        if bold:
            core = f"**{core}**"
        out += lead + core + trail
    return re.sub(r"\s+", " ", out).strip()


def _join(lines: list[str]) -> str:
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if _BULLET.match(ln) and out:
            out += "<br>" + ln
        elif out.endswith("-") and not out.endswith(" -") and ln[:1].islower():
            out += ln
        else:
            out += (" " if out else "") + ln
    return fix_text(re.sub(r"\s+", " ", out).strip())


def _grid(page: pymupdf.Page, table) -> list[list[str]]:
    rows = table.rows
    n, m = len(rows), max(len(r.cells) for r in rows)
    grid = [[""] * m for _ in range(n)]
    # a row's band runs from its top to the next row's top (merged cells stretch row.bbox)
    tops = [r.bbox[1] for r in rows] + [table.bbox[3]]
    bands = [(tops[k], tops[k + 1]) for k in range(n)]
    for i, r in enumerate(rows):
        for j, cell in enumerate(r.cells):
            if cell is None:
                continue
            rect = pymupdf.Rect(cell)
            span = [
                k for k in range(i, n) if bands[k][0] < rect.y1 - 1 and bands[k][1] > rect.y0 + 1
            ]
            lines = _lines(page, rect)
            if not lines:
                continue
            by_band: dict[int, list[str]] = {}
            for y, text in lines:
                k = next((k for k in span if bands[k][0] - 1 <= y <= bands[k][1] + 1), span[0])
                by_band.setdefault(k, []).append(text)
            if len(span) > 1 and len(by_band) == 1:  # a label for every row it spans
                text = _join(next(iter(by_band.values())))
                for k in span:
                    grid[k][j] = text
            else:
                for k, ls in by_band.items():
                    grid[k][j] = _join(ls)
    return grid


def _complementary(a: list[str], b: list[str]) -> bool:
    return all(not (x and y) for x, y in zip(a, b, strict=True))


def _clean(grid: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    # drop empty columns; merge neighbours that never both hold text (a header spanning two)
    cols = [list(c) for c in zip(*grid, strict=True) if any(c)]
    k = 0
    while k + 1 < len(cols):
        if _complementary(cols[k], cols[k + 1]) and any(cols[k]) and any(cols[k + 1]):
            cols[k] = [x or y for x, y in zip(cols[k], cols[k + 1], strict=True)]
            del cols[k + 1]
        else:
            k += 1
    rows = [list(r) for r in zip(*cols, strict=True)] if cols else []
    # drop exact duplicate consecutive rows (a repeated label row)
    rows = [r for i, r in enumerate(rows) if any(r) and (i == 0 or r != rows[i - 1])]
    # key and note lines inside the border: single-cell rows at the bottom
    notes: list[str] = []
    while rows and sum(bool(c) for c in rows[-1]) == 1 and _LEGEND_ROW.match(rows[-1][0] or "x"):
        notes.insert(0, rows.pop()[0])
    if not rows:
        return rows, notes
    # header: first row with two or more filled cells; full-width rows above it stay as rows
    h = next((i for i, r in enumerate(rows) if sum(bool(c) for c in r) >= 2), 0)
    header, pre, body = rows[h], rows[:h], rows[h + 1 :]
    filled = {j for j, c in enumerate(header) if c}
    while body:  # a header printed on two lines: "Operations" / "Process"
        nxt = body[0]
        nf = {j for j, c in enumerate(nxt) if c and c != header[j]}  # not a repeated label
        if nf and nf <= filled and len(nf) < len(filled):
            header = [
                f"{a} {b}".strip() if b and b != a else a for a, b in zip(header, nxt, strict=True)
            ]
            body = body[1:]
        else:
            break

    def repeats_header(r: list[str]) -> bool:
        return any(r) and all(not c or c in h for c, h in zip(r, header, strict=True))

    body = [r for r in body if not repeats_header(r)]
    return [header, *pre, *body], notes


def rebuild(page: pymupdf.Page, table) -> Rebuilt:
    rows, notes = _clean(_grid(page, table))
    return Rebuilt(rows, notes, tuple(table.bbox))


def _distinct_cells(rows: list[list[str]]):
    """Cells, skipping a label repeated down its column (a merged cell filled in)."""
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            if c and not (i and j < len(rows[i - 1]) and rows[i - 1][j] == c):
                yield c


def score(text_tokens: list[str], pdf_tokens: list[str]) -> float:
    """Word recall against the PDF minus the share of tokens the PDF doesn't print there."""
    if not pdf_tokens or not text_tokens:
        return 0.0
    pdf, got = Counter(pdf_tokens), Counter(text_tokens)
    recall = sum((pdf & got).values()) / sum(pdf.values())
    stray = sum((got - pdf).values()) / sum(got.values())
    return recall - stray


def rebuild_tables(blocks: list[Block], doc: pymupdf.Document, log: list[str] | None = None) -> int:
    """Replace damaged table blocks with rebuilds from the PDF. Returns the number replaced."""
    found: dict[int, list] = {}
    out: list[Block] = []
    replaced = 0
    for b in blocks:
        out.append(b)
        if b.kind != "table" or not b.rows:
            continue
        if b.page not in found:
            page = doc[b.page - 1]
            found[b.page] = [(page, t) for t in page.find_tables().tables]
        old_tokens = _tokens(" ".join(c for r in b.rows for c in r))
        # the PDF table this block came from: the best word overlap on its page
        cands = []
        for page, t in found[b.page]:
            pdf_tokens = _tokens(" ".join(w[4] for w in page.get_text("words", clip=t.bbox)))
            a, p = set(old_tokens), set(pdf_tokens)
            cands.append((len(a & p) / max(len(a | p), 1), page, t, pdf_tokens))
        best = None
        if cands:
            jaccard, page, t, pdf_tokens = max(cands, key=lambda c: c[0])
            new = rebuild(page, t) if jaccard >= 0.4 else None
            if new and len(new.rows) >= 2 and max(len(r) for r in new.rows) >= 2:
                new_tokens = _tokens(" ".join([*_distinct_cells(new.rows), *new.notes]))
                gain = score(new_tokens, pdf_tokens) - score(old_tokens, pdf_tokens)
                if gain >= MIN_GAIN:
                    best = (gain, new)
        if best:
            gain, new = best
            b.rows = new.rows
            out.extend(Block("note", n, b.page, zone=b.zone) for n in new.notes)
            replaced += 1
            if log is not None:
                log.append(f"page {b.page}: table rebuilt from PDF rulings (score +{gain:.2f})")
    # pymupdf4llm may already have put a key line after the table as a paragraph
    deduped: list[Block] = []
    for b in out:
        if b.kind in ("note", "para") and any(
            p.kind in ("note", "para") and norm(p.text) == norm(b.text) for p in deduped[-3:]
        ):
            continue
        deduped.append(b)
    blocks[:] = deduped
    return replaced
