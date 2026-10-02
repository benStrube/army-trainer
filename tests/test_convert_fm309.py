"""Integration tests on the FM 3-09 pilot (user-supplied, Distribution A).

Skipped when the PDF is not in the checkout. The full-document test takes about a minute;
run it with RUN_SLOW=1. Refresh the golden excerpt with UPDATE_GOLDEN=1 after an intended change.
"""

import os
import re
from pathlib import Path

import pymupdf
import pytest

from army_trainer.convert.pipeline import convert_pdf
from army_trainer.fetch.fetch import ingest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [ROOT / "data/raw/FM-3-09.pdf", *sorted(ROOT.glob("FM 3-09*.pdf"))]
PDF = next((p for p in CANDIDATES if p.exists()), None)
GOLDEN = Path(__file__).parent / "golden" / "FM-3-09_p15-21.md"

pytestmark = pytest.mark.skipif(PDF is None, reason="FM 3-09 PDF not present")


@pytest.fixture(scope="module")
def gated(tmp_path_factory):
    """Run the real Distribution A gate first; conversion refuses ungated documents."""
    raw = tmp_path_factory.mktemp("raw")
    meta = ingest(PDF, "FM-3-09", raw_dir=raw)
    assert meta.gate.status == "pass"
    return raw / "FM-3-09.pdf", meta


def test_excerpt_matches_golden(gated):
    pdf, meta = gated
    md, report = convert_pdf(pdf, meta, pages=list(range(14, 21)))
    if os.environ.get("UPDATE_GOLDEN") or not GOLDEN.exists():
        GOLDEN.write_text(md)
    assert md == GOLDEN.read_text()
    assert report.headings_unplaced == []


def test_excerpt_structure(gated):
    pdf, meta = gated
    md, report = convert_pdf(pdf, meta, pages=list(range(14, 21)))
    assert "# Chapter 1: Foundations of Fire Support and the Role of the Field Artillery" in md
    assert "### TENETS OF OPERATIONS" in md
    ids = re.findall(r"^(1-\d+)\. ", md, re.M)
    assert ids == [f"1-{n}" for n in range(1, len(ids) + 1)]  # every paragraph, in order
    assert "12 August 2024" not in md.split("---", 2)[2]  # running footer removed
    # Table 1-2 spans three pages: one caption, one table
    assert md.count("**Table 1-2.") == 1 and report.continued_tables_merged >= 1
    # page-break join: "importance in any" + "confrontation"
    assert "of paramount importance in any confrontation with a threat actor" in md


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="set RUN_SLOW=1 (about 1 minute)")
def test_full_document_against_pdf_ground_truth(gated):
    pdf, meta = gated
    md, report = convert_pdf(pdf, meta)
    doc = pymupdf.open(pdf)

    def n(s):
        return re.sub(r"[^a-z0-9]+", "", s.lower())

    headings = {
        n(re.sub(r"^(Chapter \d+|Appendix [A-Z]): ", "", m))
        for m in re.findall(r"^#+ (.*)$", md, re.M)
    }
    toc = [t for t in doc.get_toc() if 9 <= t[2] < 279]
    missing = [
        t for t in toc if n(t[1]) not in headings and not re.match(r"^(Chapter|Appendix) ", t[1])
    ]
    assert missing == []

    ids = re.findall(r"^\**([1-6A-E])-(\d+)\.\**\s", md, re.M)
    order = "123456ABCDE"
    keys = [(order.index(a), int(b)) for a, b in ids]
    assert keys == sorted(keys) and len(set(keys)) == len(keys) == 933

    body = md.split("---", 2)[2]
    assert not re.search(r"^\W*(12 August 2024|FM 3-09)\W*$", body, re.M)
    assert not re.search("[-�]", body)
    assert report.glossary_terms > 240
