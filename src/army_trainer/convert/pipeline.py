"""Stage 2: gated PDF -> clean Markdown with YAML front matter.

pymupdf4llm supplies body text, emphasis and tables; PyMuPDF layout signals supply the heading
hierarchy and printed page numbers. See docs/decisions/converter.md.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf
import pymupdf4llm
import yaml

from ..fetch.models import PubMetadata
from ..llm_guard import require_gate_pass
from . import blocks as B
from .layout import document_title, scan

MD_DIR = Path("data/md")


@dataclass
class ConversionReport:
    pub_id: str
    pages_converted: int = 0
    headings: int = 0
    headings_unplaced: list[str] = field(default_factory=list)
    numbered_paragraphs: int = 0
    tables: int = 0
    continued_tables_merged: int = 0
    table_rows_repaired: int = 0
    table_overflow_absorbed: int = 0
    table_rows_rebuilt: int = 0
    rebuilt_log: list[tuple[int, str]] = field(default_factory=list)
    table_rows_scrambled_pages: list[int] = field(default_factory=list)
    page_break_joins: int = 0
    join_log: list[tuple[str, str]] = field(default_factory=list)
    glossary_terms: int = 0


def _proponent(text: str) -> str | None:
    m = re.search(r"The proponent of (?:this publication|[A-Z]{2,4} [\d.-]+) is ([^.]+)\.", text)
    return " ".join(m.group(1).split()) if m else None


def legend_from_pdf(doc: pymupdf.Document) -> B.LegendSource:
    """Find an abbreviation key in the PDF's reading-order text with the same abbreviations."""

    def find(page: int, garbled: str) -> str | None:
        want = B.legend_abbreviations(garbled)
        for pno in range(page - 1, min(page + 4, len(doc))):
            lines = [ln.strip() for ln in doc[pno].get_text().splitlines()]
            for i, ln in enumerate(lines):
                if not B._LEGEND.match(ln) and not B._ABBR.match(ln):
                    continue
                run: list[str] = []
                for nxt in lines[i:]:
                    if not B._ABBR.search(nxt):
                        break
                    run.append(nxt)
                text = re.sub(r"\s+", " ", " ".join(run)).strip()
                have = B.legend_abbreviations(text)
                if want and want <= have and len(have) <= len(want) + 1:
                    return text
        return None

    return find


def _letters(s: str) -> Counter[str]:
    return Counter(c for c in B.plain(s).lower() if c.isalnum())


def _known(word: str, vocab: set[str]) -> bool:
    """In the page vocabulary, or two vocabulary words run together ("becomesproponent")."""
    return word in vocab or any(
        word[:k] in vocab and word[k:] in vocab for k in range(3, len(word) - 2)
    )


def ungarble_tables(
    blocks: list[B.Block], doc: pymupdf.Document, log: list[tuple[int, str]] | None = None
) -> tuple[int, list[int]]:
    """pymupdf4llm can interleave the columns of a full-width form row ("Purpos Priority
    Allocati..."). Detect rows whose words don't exist on the page, then rebuild them from the
    PDF's reading-order lines -- only when the letters match exactly, so nothing is invented.

    Returns (rows rebuilt, pages with scrambled rows that could not be rebuilt)."""
    fixed, failed = 0, []
    for t in (b for b in blocks if b.kind == "table"):
        pages = range(t.page - 1, min(t.page + 3, len(doc)))
        lines = [
            ln.strip()
            for p in pages
            for ln in doc[p].get_text(clip=pymupdf.Rect(0, 55, 612, 735)).splitlines()
            if ln.strip()
        ]
        vocab = {w.lower() for ln in lines for w in re.findall(r"[A-Za-z]{3,}", ln)}
        width = max(len(r) for r in t.rows)
        for row in t.rows:
            words = re.findall(r"[A-Za-z]{3,}", B.plain(" ".join(row)))
            unknown = [w for w in words if not _known(w.lower(), vocab)]
            if len(words) < 4 or len(unknown) / len(words) < 0.15:
                continue
            want = _letters("".join(row))
            size = sum(want.values())
            for i in range(len(lines)):
                acc: Counter[str] = Counter()
                for j in range(i, len(lines)):
                    acc += _letters(lines[j])
                    if sum(acc.values()) >= size:
                        break
                if acc == want:
                    if log is not None:
                        log.append((t.page, " | ".join(row)[:90]))
                    row[:] = ["<br>".join(lines[i : j + 1])] + [""] * (width - 1)
                    fixed += 1
                    break
            else:
                failed.append(t.page)
    return fixed, sorted(set(failed))


def page_markdown(pdf: Path, pages: list[int] | None = None) -> list[tuple[int, str]]:
    """(1-based page, Markdown) for each page, running headers/footers removed."""
    chunks = pymupdf4llm.to_markdown(
        str(pdf), pages=pages, page_chunks=True, header=False, footer=False, show_progress=False
    )
    return [(c["metadata"]["page_number"], c["text"]) for c in chunks]


def convert_pdf(
    pdf: Path, meta: PubMetadata, pages: list[int] | None = None
) -> tuple[str, ConversionReport]:
    """Convert a gated PDF. `pages` (0-based) limits the run, e.g. for tests."""
    require_gate_pass(meta)
    doc = pymupdf.open(pdf)
    layouts = scan(doc)
    report = ConversionReport(pub_id=meta.pub_id)

    blocks: list[B.Block] = []
    for pno, md in page_markdown(pdf, pages):
        page_blocks = B.parse_page(md, pno)
        report.headings_unplaced += B.resolve_headings(page_blocks, layouts[pno - 1])
        blocks += page_blocks
        report.pages_converted += 1

    if pages is None:
        blocks = B.assign_zones(blocks)
    else:  # a page range has no zone-opening titles to go on; keep everything
        blocks = _excerpt(blocks)

    report.table_overflow_absorbed = B.absorb_table_overflow(blocks)
    report.continued_tables_merged = B.merge_continued_tables(blocks)
    report.page_break_joins = B.join_page_breaks(blocks, report.join_log)
    report.table_rows_rebuilt, report.table_rows_scrambled_pages = ungarble_tables(
        blocks, doc, report.rebuilt_log
    )
    report.table_rows_repaired = B.repair_tables(blocks, legend_from_pdf(doc))
    report.glossary_terms = B.format_glossary(blocks)

    report.headings = sum(b.kind == "heading" for b in blocks)
    report.tables = sum(b.kind == "table" for b in blocks)
    report.numbered_paragraphs = sum(bool(B.PARA_NUM.match(b.text)) for b in blocks)

    front_text = "\n".join(doc[i].get_text() for i in range(min(12, len(doc))))
    front = {
        "pub_id": meta.pub_id,
        "title": meta.title or document_title(layouts),
        "pub_date": meta.pub_date.isoformat() if meta.pub_date else None,
        "supersedes": meta.supersedes,
        "proponent": meta.proponent or _proponent(front_text),
        "distribution": "A — approved for public release; distribution is unlimited",
        "source_sha256": meta.sha256,
        "page_count": meta.page_count,
        "converter": {
            "pymupdf4llm": importlib.metadata.version("pymupdf4llm"),
            "pymupdf": importlib.metadata.version("pymupdf"),
        },
    }
    if pages is not None:
        front["excerpt_pages"] = [p + 1 for p in pages]
    labels = {pl.page: pl.label for pl in layouts}
    body = B.render(blocks, labels)
    header = "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n"
    return header + body, report


def _excerpt(blocks: list[B.Block]) -> list[B.Block]:
    """Heading levels for a page range that starts mid-chapter."""
    for b in blocks:
        b.zone = "Excerpt"
    tiers = sorted({b.tier for b in blocks if b.kind == "heading" and b.tier != "T1"})
    for b in blocks:
        if b.kind == "heading":
            b.level = 1 if b.tier == "T1" else 2 + tiers.index(b.tier)
    return blocks


def convert(meta: PubMetadata, raw_dir: Path, out_dir: Path = MD_DIR) -> Path:
    pdf = raw_dir / f"{meta.pub_id}.pdf"
    md, report = convert_pdf(pdf, meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{meta.pub_id}.md"
    out.write_text(md)
    (out_dir / f"{meta.pub_id}.report.json").write_text(json.dumps(asdict(report), indent=2))
    return out
