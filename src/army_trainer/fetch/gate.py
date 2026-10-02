"""Distribution A gate. Fail closed: anything not clearly Distribution A is rejected."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .models import GateResult

_DIST_A = re.compile(
    r"approved\s+for\s+public\s+release\s*;?\s*distribution\s+(?:is\s+)?unlimited", re.I
)
# "DISTRIBUTION RESTRICTION: ..." / "Distribution Statement B" through F, plus X.
_DIST_OTHER = re.compile(r"distribution\s+(?:statement\s+)?([B-FX])\b", re.I)
_RESTRICTED_MARKINGS = re.compile(
    r"\b(CUI|CONTROLLED\s+UNCLASSIFIED|FOR\s+OFFICIAL\s+USE\s+ONLY|FOUO|"
    r"CONFIDENTIAL|SECRET|NOFORN)\b"
)
_LIMITED = re.compile(
    r"(distribution\s+(?:is\s+)?(?:authorized|limited|restricted)\s+to|"
    r"not\s+approved\s+for\s+public\s+release)",
    re.I,
)


def _fail(distribution: str | None, reason: str, evidence: str | None = None) -> GateResult:
    return GateResult(
        status="fail",
        distribution=distribution,
        reason=reason,
        evidence=evidence,
        checked_at=datetime.now(UTC),
    )


def check_distribution(front_matter_text: str) -> GateResult:
    """Inspect text from the first pages of a PDF and decide whether it is Distribution A.

    Any restricted marking or other distribution statement fails the gate even if
    Distribution A language also appears, and a missing statement also fails.
    """
    text = " ".join(front_matter_text.split())

    if m := _RESTRICTED_MARKINGS.search(text):
        return _fail(m.group(1).upper(), f"Restricted marking found: {m.group(1)}", m.group(0))
    if m := _DIST_OTHER.search(text):
        letter = m.group(1).upper()
        return _fail(letter, f"Distribution Statement {letter} found", m.group(0))
    if m := _LIMITED.search(text):
        return _fail(None, "Limited-distribution language found", m.group(0))
    if m := _DIST_A.search(text):
        return GateResult(
            status="pass",
            distribution="A",
            reason="Distribution A statement found",
            evidence=m.group(0),
            checked_at=datetime.now(UTC),
        )
    return _fail(None, "No distribution statement found; refusing by default")
