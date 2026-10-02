"""Stage 1: accept a local PDF or download from armypubs, record metadata, run the gate."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import pdf
from .gate import check_distribution
from .models import PubMetadata

USER_AGENT = "army-trainer/0.1 (local training-aid tool; Distribution A only)"
ALLOWED_HOSTS = {"armypubs.army.mil", "www.armypubs.army.mil"}
RAW_DIR = Path("data/raw")


class FetchError(RuntimeError):
    pass


def download(url: str, dest: Path) -> None:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise FetchError(f"Refusing to download from {host!r}; only armypubs.army.mil is allowed.")
    try:
        with httpx.stream(
            "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60
        ) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as e:
        dest.unlink(missing_ok=True)
        raise FetchError(f"Download failed for {url}: {e}") from e


def ingest(
    pdf_path: Path,
    pub_id: str,
    source_url: str | None = None,
    raw_dir: Path = RAW_DIR,
) -> PubMetadata:
    """Run the gate on `pdf_path`; write metadata always, keep the PDF only if the gate passes."""
    pub_id = pdf.normalize_pub_id(pub_id)
    front, pages = pdf.read_front(pdf_path)
    gate = check_distribution(front)
    meta = PubMetadata(
        pub_id=pub_id,
        title=None,
        pub_date=pdf.parse_pub_date(front),
        supersedes=pdf.parse_supersedes(front),
        page_count=pages,
        sha256=pdf.sha256_file(pdf_path),
        source_url=source_url,
        source_path=None if source_url else str(pdf_path),
        fetched_at=datetime.now(UTC),
        gate=gate,
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{pub_id}.meta.json").write_text(meta.model_dump_json(indent=2))
    if gate.status == "pass":
        shutil.copyfile(pdf_path, raw_dir / f"{pub_id}.pdf")
    return meta


def fetch(
    pub: str, url: str | None = None, pdf_path: Path | None = None, raw_dir: Path = RAW_DIR
) -> PubMetadata:
    """Fetch by URL or ingest a local PDF. Raises FetchError if the gate rejects it."""
    if (url is None) == (pdf_path is None):
        raise FetchError("Provide exactly one of a URL or a local PDF path.")
    tmp: Path | None = None
    try:
        if url:
            raw_dir.mkdir(parents=True, exist_ok=True)
            tmp = raw_dir / f".{pdf.normalize_pub_id(pub)}.download"
            download(url, tmp)
            pdf_path = tmp
        assert pdf_path is not None
        meta = ingest(pdf_path, pub, source_url=url, raw_dir=raw_dir)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    if meta.gate.status != "pass":
        raise FetchError(f"Distribution A gate rejected {meta.pub_id}: {meta.gate.reason}")
    return meta
