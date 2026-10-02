"""Word repairs for text joined or split at PDF line breaks (WP 5.1a, Opus-owned).

pymupdf4llm sometimes drops what sat at a line break: the hyphen in "high-⏎explosive" or the
space in "decision⏎making" ("highexplosive", "decisionmaking"), and keeps a stray space after
a hyphen in references ("JP 3- 09"). Fixes are only made on evidence from the PDF itself:

* a joined word is split only if the PDF never prints it whole and does print its two parts
  across a line break; the hyphen comes back if the break was hyphenated, else a space;
* "JP 3- 09" -> "JP 3-09" for publication, staff-section, table and figure references;
* "pre- mission" -> "pre-mission", but suspended hyphens stay ("rotary- and fixed-wing").
"""

from __future__ import annotations

import re
from collections import Counter

from .blocks import Block

_REF = re.compile(
    r"\b(JP|FM|ATP|ADP|ADRP|TC|AR|DA Form|Table|table|Figure|figure|para(?:graph)?)"
    r" ([0-9A-Z]{1,2})- (\d)"
)
_STAFF = re.compile(r"\b([SG])- (\d)\b")  # "S- 2" -> "S-2"
_SUSPENDED = {"and", "or", "nor", "to", "through", "and/or"}
_HYPHEN_SPACE = re.compile(r"\b([a-z]+)- ([a-z][a-z/]*)\b")


def joined_word_fixes(texts: list[str], pdf_text: str) -> dict[str, str]:
    """Map each joined word in `texts` to its repair, using line breaks in `pdf_text`."""
    words = Counter(w.lower() for t in texts for w in re.findall(r"[A-Za-z]+", t))
    fixes: dict[str, str] = {}
    for w, n in words.items():
        if len(w) < 7 or n > 5:
            continue
        if re.search(rf"(?<![A-Za-z]){w}(?![A-Za-z])", pdf_text, re.I):
            continue  # the PDF prints it whole: a real word
        for i in range(2, len(w) - 2):
            a, b = w[:i], w[i:]
            if words[a] < 3 or words[b] < 3 or len(b) < 3:
                continue
            if re.search(rf"(?<![A-Za-z]){a}-[ \t]*\n[ \t]*{b}(?![A-Za-z])", pdf_text, re.I):
                fixes[w] = f"{a}-{b}"
            elif re.search(rf"(?<![A-Za-z]){a}[ \t]*\n[ \t]*{b}(?![A-Za-z])", pdf_text, re.I):
                fixes[w] = f"{a} {b}"
            if w in fixes:
                break
    return fixes


def _apply(text: str, fixes: dict[str, str]) -> str:
    text = _STAFF.sub(r"\1-\2", _REF.sub(r"\1 \2-\3", text))
    text = _HYPHEN_SPACE.sub(
        lambda m: m.group(0) if m.group(2) in _SUSPENDED else f"{m.group(1)}-{m.group(2)}", text
    )
    if fixes:

        def repl(m: re.Match[str]) -> str:
            fixed = fixes.get(m.group(0).lower())
            if not fixed:
                return m.group(0)
            return fixed[0].upper() + fixed[1:] if m.group(0)[0].isupper() else fixed

        text = re.sub(r"[A-Za-z]+", repl, text)
    return text


def repair_words(blocks: list[Block], pdf_text: str, log: list[str] | None = None) -> int:
    """Repair joined words and split references in every text block and table cell."""
    texts = [b.text for b in blocks] + [c for b in blocks for r in b.rows for c in r]
    fixes = joined_word_fixes(texts, pdf_text)
    changed = 0
    for b in blocks:
        new = _apply(b.text, fixes)
        rows = [[_apply(c, fixes) for c in r] for r in b.rows]
        if new != b.text or rows != b.rows:
            changed += 1
            b.text, b.rows = new, rows
    if log is not None:
        log.extend(f"{w} -> {f}" for w, f in sorted(fixes.items()))
    return changed
