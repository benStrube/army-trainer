"""Metadata and gate-result models written next to each raw PDF."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

GateStatus = Literal["pass", "fail"]


class GateResult(BaseModel):
    status: GateStatus
    distribution: str | None = Field(
        default=None, description="Statement found, e.g. 'A', 'B'-'F', 'CUI', or None."
    )
    reason: str
    evidence: str | None = Field(default=None, description="Matched text from the PDF.")
    checked_at: datetime


class PubMetadata(BaseModel):
    pub_id: str = Field(description="Normalized, e.g. 'AR-600-20'.")
    title: str | None = None
    pub_date: date | None = None
    proponent: str | None = None
    supersedes: str | None = None
    page_count: int
    sha256: str
    source_url: str | None = Field(default=None, description="None for local files.")
    source_path: str | None = None
    fetched_at: datetime
    gate: GateResult
