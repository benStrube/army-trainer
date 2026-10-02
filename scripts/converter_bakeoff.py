"""WP 1.1 converter bake-off on a page range of a gated PDF.

Usage (bake-off deps are not project deps):
  uv run --with pymupdf --with pymupdf4llm --with pdfplumber \
    python scripts/converter_bakeoff.py data/raw/<ID>.pdf FIRST LAST OUT_DIR

Candidates: A pymupdf4llm, B pdfplumber, C thin custom layer over PyMuPDF spans.
Scores each against ground truth taken from the PDF itself (bookmarks, plain text).
See docs/decisions/converter.md.
"""

import collections
import json
import re
import sys
import time
from pathlib import Path

import pymupdf

PDF = Path(sys.argv[1])
FIRST, LAST = int(sys.argv[2]), int(sys.argv[3])  # 1-based inclusive
OUT = Path(sys.argv[4])
OUT.mkdir(parents=True, exist_ok=True)
PAGES = list(range(FIRST - 1, LAST))
HEADER_Y, FOOTER_Y = 55, 735

doc = pymupdf.open(PDF)


# ---------------- ground truth ----------------
def body_text(pno: int) -> str:
    pg = doc[pno]
    clip = pymupdf.Rect(0, HEADER_Y, pg.rect.width, FOOTER_Y)
    return pg.get_text(clip=clip)


ref_text = "\n".join(body_text(p) for p in PAGES)
WORD = re.compile(r"[A-Za-z][A-Za-z']+")


def words(s: str) -> collections.Counter:
    s = re.sub(r"-\n", "", s)  # undo line-end hyphenation on both sides
    return collections.Counter(w.lower() for w in WORD.findall(s))


ref_words = words(ref_text)


def band_lines(pno: int) -> set[str]:
    """Running header/footer lines: text outside the body band."""
    pg = doc[pno]
    top = pg.get_text(clip=pymupdf.Rect(0, 0, pg.rect.width, HEADER_Y))
    bottom = pg.get_text(clip=pymupdf.Rect(0, FOOTER_Y, pg.rect.width, pg.rect.height))
    return {ln.strip() for ln in (top + "\n" + bottom).splitlines() if ln.strip()}


hf_lines = set().union(*(band_lines(p) for p in PAGES))
ref_paras = set(re.findall(r"^(\d+-\d+)\.\s", ref_text, re.M))
toc = [(lvl, t.strip(), p) for lvl, t, p in doc.get_toc() if FIRST <= p <= LAST and lvl >= 3]
tables_truth = sorted(
    set(m for p in PAGES for m in re.findall(r"^Table (\d+-\d+)\.", body_text(p), re.M))
)


# ---------------- candidates ----------------
def cand_pymupdf4llm() -> str:
    import pymupdf4llm

    return pymupdf4llm.to_markdown(
        str(PDF), pages=PAGES, show_progress=False, header=False, footer=False
    )


def md_table(rows) -> str:
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in rows if r]
    if not rows:
        return ""
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def cand_pdfplumber() -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(PDF) as pdf:
        for p in PAGES:
            page = pdf.pages[p]
            parts.append(page.extract_text() or "")
            for t in page.extract_tables():
                parts.append(md_table(t))
    return "\n\n".join(parts)


def cand_custom() -> str:
    """Thin rule layer: drop header/footer bands, headings from bold Times >= 12pt
    (rejoining small-caps spans), numbered paragraphs, bullets, tables via find_tables
    with continued tables merged."""
    out: list[str] = []
    last_table_id = None
    for p in PAGES:
        pg = doc[p]
        tabs = pg.find_tables().tables
        tab_rects = [pymupdf.Rect(t.bbox) for t in tabs]
        items = []  # (y, kind, payload)
        for t in tabs:
            items.append((t.bbox[1], "table", t.extract()))
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                bbox = pymupdf.Rect(ln["bbox"])
                if bbox.y1 < HEADER_Y or bbox.y0 > FOOTER_Y:
                    continue
                if any(r.intersects(bbox) for r in tab_rects):
                    continue
                spans = [s for s in ln["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in ln["spans"]).strip()
                bold_times = all("Times" in s["font"] and "Bold" in s["font"] for s in spans)
                size = max(s["size"] for s in spans)
                if bold_times and size >= 13.5:
                    kind = "h2"
                elif bold_times and size >= 11.5:
                    kind = "h3"
                elif all("Arial-Bold" in s["font"] for s in spans) and text.startswith("Table "):
                    kind = "caption"
                else:
                    kind = "text"
                items.append((bbox.y0, kind, text))
        items.sort(key=lambda x: x[0])
        for _, kind, payload in items:
            if kind == "table":
                if last_table_id and out and out[-1].startswith("|"):
                    # continuation: drop repeated header row, append body rows
                    body = md_table(payload).split("\n")[2:]
                    out[-1] += "\n" + "\n".join(body)
                else:
                    out.append(md_table(payload))
                continue
            if kind == "caption":
                m = re.match(r"Table (\d+-\d+)", payload)
                tid = m.group(1) if m else None
                if tid and tid == last_table_id and "(continued)" in payload:
                    continue
                last_table_id = tid
                out.append(f"**{payload}**")
                continue
            if kind in ("h2", "h3"):
                last_table_id = None
                out.append(("## " if kind == "h2" else "### ") + payload.title())
                continue
            if re.match(r"^\d+-\d+\.\s", payload) or payload.startswith("") or not out:
                out.append(payload)
            elif out[-1].startswith(("#", "|", "**Table")):
                out.append(payload)
            else:
                prev = out[-1]
                out[-1] = (
                    prev[:-1] + payload
                    if prev.endswith("-") and prev[-2:-1].isalpha()
                    else prev + " " + payload
                )
    return "\n\n".join(out)


CANDS = {
    "A_pymupdf4llm": cand_pymupdf4llm,
    "B_pdfplumber": cand_pdfplumber,
    "C_custom_pymupdf": cand_custom,
}


# ---------------- scoring ----------------
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def score(md: str) -> dict:
    w = words(md)
    recall = sum(min(c, w[k]) for k, c in ref_words.items()) / sum(ref_words.values())
    extra = sum(max(0, c - ref_words.get(k, 0)) for k, c in w.items()) / sum(ref_words.values())
    heading_lines = {
        norm(re.sub(r"</?mark>", "", re.sub(r"^#+\s*", "", ln)))
        for ln in md.splitlines()
        if ln.lstrip().startswith("#")
    }
    toc_hit = sum(1 for _, t, _ in toc if norm(t) in heading_lines)
    para_starts = set(re.findall(r"^\**(\d+-\d+)\.\**\s", md, re.M))
    leak = sum(1 for ln in md.splitlines() if re.sub(r"[*_#<>/]|mark", "", ln).strip() in hf_lines)
    md_tables = len(re.findall(r"(?:^\|.*\|\s*\n)(?:^\|[-:| ]+\|\s*$)", md, re.M))
    broken_hyphen = len(re.findall(r"[a-z]-\n[a-z]", md))
    return {
        "word_recall": round(recall, 4),
        "extra_words_ratio": round(extra, 4),
        "toc_headings_found": f"{toc_hit}/{len(toc)}",
        "para_numbers_at_line_start": f"{len(para_starts & ref_paras)}/{len(ref_paras)}",
        "header_footer_leak_lines": leak,
        "md_tables": md_tables,
        "tables_in_source": len(tables_truth),
        "line_end_hyphen_breaks": broken_hyphen,
    }


results = {}
for name, fn in CANDS.items():
    t0 = time.perf_counter()
    try:
        md = fn()
        dt = time.perf_counter() - t0
        (OUT / f"{name}.md").write_text(md)
        results[name] = {"seconds": round(dt, 2), **score(md)}
    except Exception as e:  # record, don't hide
        results[name] = {"error": repr(e)}
print(
    json.dumps(
        {"pages": f"{FIRST}-{LAST}", "tables_truth": tables_truth, "results": results}, indent=2
    )
)
