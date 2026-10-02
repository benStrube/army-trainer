"""Read the front of an AR PDF: text for the gate plus best-effort metadata."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

FRONT_PAGES = 3

_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "January February March April May June July August September October November December"
        ).split(),
        start=1,
    )
}
_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b")
_SUPERSEDES = re.compile(r"This\s+(?:major\s+)?revision\s+(?:\w+\s+)*?supersedes\s+([^.]+)\.", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_front(path: Path, pages: int = FRONT_PAGES) -> tuple[str, int]:
    """Return (text of the first `pages` pages, total page count)."""
    reader = PdfReader(str(path))
    n = min(pages, len(reader.pages))
    text = "\n".join((reader.pages[i].extract_text() or "") for i in range(n))
    return text, len(reader.pages)


def parse_pub_date(text: str) -> date | None:
    if m := _DATE.search(text):
        return date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
    return None


def parse_supersedes(text: str) -> str | None:
    if m := _SUPERSEDES.search(" ".join(text.split())):
        return m.group(1).strip()
    return None


def normalize_pub_id(raw: str) -> str:
    """'AR 600–20', 'ar_600-20' -> 'AR-600-20'."""
    s = raw.upper().replace("–", "-").replace("—", "-")
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", s)
