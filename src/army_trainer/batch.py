"""Batch mode (WP 5.3): run the deterministic stages over a list of publications, and check
whether the PDFs we hold have been revised.

Planning stays one Opus session per publication (D10). So a publication with no committed spec
stops after `index` with the planning packet written and the status "needs planning"; `render`
and `qa` run only where `specs/<ID>.spec.json` exists and was planned from the PDF we hold.

Every input goes through the Distribution A gate (`fetch.fetch`) and every later stage loads its
metadata through `llm_guard.load_gated_metadata`. Nothing here bypasses either. One publication
failing never stops the others.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .fetch import pdf as pdfmod
from .fetch.fetch import FetchError, download
from .fetch.fetch import fetch as run_fetch
from .fetch.models import PubMetadata
from .llm_guard import GateError, load_gated_metadata

STAGES = ("fetch", "convert", "index", "plan", "render", "qa")


@dataclass(frozen=True)
class Dirs:
    """Where each stage reads and writes (defaults are the project layout)."""

    raw: Path = Path("data/raw")
    md: Path = Path("data/md")
    json: Path = Path("data/json")
    packets: Path = Path("data/packets")
    qa: Path = Path("data/qa")
    batch: Path = Path("data/batch")
    inbox: Path = Path("data/inbox")
    specs: Path = Path("specs")
    decks: Path = Path("out/decks")


@dataclass(frozen=True)
class Entry:
    pub_id: str
    pdf: Path | None = None  # a local PDF to ingest
    url: str | None = None  # an armypubs.army.mil PDF URL


def _split_line(line: str) -> tuple[str, str | None]:
    """Split ``ID [source]``. The ID may contain spaces ("FM 3-09"), so the source starts at the
    first word that looks like a URL or a path (http..., a slash, or a .pdf ending)."""
    words = line.split()
    for i, w in enumerate(words):
        if i and (re.match(r"https?://", w) or "/" in w or "\\" in w or w.lower().endswith(".pdf")):
            return " ".join(words[:i]), " ".join(words[i:])
    return line, None


def parse_list(text: str) -> list[Entry]:
    """One publication per line: ``ID``, ``ID path/to.pdf`` or ``ID https://armypubs...pdf``.
    Blank lines and ``#`` comments are ignored. Duplicate IDs are an error."""
    out: list[Entry] = []
    seen: set[str] = set()
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pub_id_raw, src = _split_line(line)
        pub_id = pdfmod.normalize_pub_id(pub_id_raw)
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]*", pub_id):
            raise ValueError(f"line {n}: {pub_id_raw!r} is not a publication ID")
        if pub_id in seen:
            raise ValueError(f"line {n}: {pub_id} is listed twice")
        seen.add(pub_id)
        if src and re.match(r"https?://", src):
            out.append(Entry(pub_id, url=src))
        elif src:
            out.append(Entry(pub_id, pdf=Path(src)))
        else:
            out.append(Entry(pub_id))
    return out


# ---------------------------------------------------------------- results


@dataclass
class PubResult:
    pub_id: str
    #: ok | needs_planning | rejected | no_input | failed
    status: str = "ok"
    message: str = ""
    steps: dict[str, str] = field(default_factory=dict)
    pages: int | None = None

    @property
    def is_error(self) -> bool:
        return self.status in ("rejected", "no_input", "failed")


@dataclass
class BatchReport:
    results: list[PubResult] = field(default_factory=list)

    @property
    def errors(self) -> list[PubResult]:
        return [r for r in self.results if r.is_error]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def to_json(self) -> dict:
        return {"counts": self.counts(), "results": [asdict(r) for r in self.results]}

    def table(self) -> str:
        rows = [("publication", "status", *STAGES, "note")]
        for r in self.results:
            rows.append((r.pub_id, r.status, *(r.steps.get(s, "-") for s in STAGES), r.message))
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
        lines = []
        for row in rows:
            cells = [c.ljust(w) for c, w in zip(row[:-1], widths, strict=True)]
            lines.append("  ".join(cells) + ("  " + row[-1] if row[-1] else ""))
        return "\n".join(lines)


# ---------------------------------------------------------------- one publication


def _load_meta(pub_id: str, dirs: Dirs) -> PubMetadata | None:
    p = dirs.raw / f"{pub_id}.meta.json"
    return PubMetadata.model_validate_json(p.read_text()) if p.exists() else None


def _fetch_step(e: Entry, dirs: Dirs, force: bool) -> str:
    """Bring the PDF in through the gate. Returns the step note; raises FetchError."""
    have = _load_meta(e.pub_id, dirs)
    have_pdf = (dirs.raw / f"{e.pub_id}.pdf").exists()
    src = e.pdf
    if src is None and e.url is None:
        inbox = dirs.inbox / f"{e.pub_id}.pdf"
        if inbox.exists():
            src = inbox
        elif have and have_pdf and have.gate.status == "pass":
            return "skipped (already fetched)"
        else:
            raise FileNotFoundError(
                f"no input: put {e.pub_id}.pdf in {dirs.inbox}/, or give a path or URL in the list"
            )
    if src is not None:
        if not src.exists():
            raise FileNotFoundError(f"no input: {src} does not exist")
        if (
            have
            and have_pdf
            and not force
            and have.gate.status == "pass"
            and have.sha256 == pdfmod.sha256_file(src)
        ):
            return "skipped (same PDF)"
        run_fetch(e.pub_id, pdf_path=src, raw_dir=dirs.raw)
        return "done"
    if have and have_pdf and not force and have.gate.status == "pass":
        return "skipped (already fetched)"
    run_fetch(e.pub_id, url=e.url, raw_dir=dirs.raw)
    return "done"


def process(  # noqa: PLR0911, PLR0912, PLR0915
    e: Entry,
    dirs: Dirs = Dirs(),
    stages: tuple[str, ...] = STAGES,
    force: bool = False,
    target: int = 34,
) -> PubResult:
    """Run the requested stages for one publication; never raises for a per-publication problem."""
    from .convert.pipeline import convert as run_convert
    from .index.build import Indexes, write_indexes
    from .structure.models import DocTree
    from .structure.parse import build as build_tree

    res = PubResult(e.pub_id)
    want = set(stages)

    def mark(stage: str, note: str) -> None:
        res.steps[stage] = note

    try:
        if "fetch" in want:
            try:
                mark("fetch", _fetch_step(e, dirs, force))
            except FileNotFoundError as ex:
                res.status, res.message = "no_input", str(ex)
                mark("fetch", "no input")
                return res
            except FetchError as ex:
                rejected = "gate rejected" in str(ex)
                res.status = "rejected" if rejected else "failed"
                res.message = str(ex)
                mark("fetch", "REJECTED" if rejected else "failed")
                return res
        try:  # every later stage needs a passing gate record
            meta = load_gated_metadata(e.pub_id, dirs.raw)
        except GateError as ex:
            res.status, res.message = "rejected", str(ex)
            return res
        res.pages = meta.page_count
        tree_path = dirs.json / f"{e.pub_id}.json"
        index_path = dirs.json / f"{e.pub_id}.indexes.json"

        def tree_current() -> bool:
            if not (tree_path.exists() and (dirs.md / f"{e.pub_id}.md").exists()):
                return False
            return (
                DocTree.model_validate_json(tree_path.read_text()).pub.source_sha256 == meta.sha256
            )

        if "convert" in want:
            if tree_current() and not force:
                mark("convert", "skipped (up to date)")
            else:
                run_convert(meta, dirs.raw, dirs.md)
                build_tree(e.pub_id, dirs.md, dirs.json)
                mark("convert", "done")
        if "index" in want:
            if not tree_path.exists():
                res.status, res.message = "failed", "no document tree: run convert first"
                mark("index", "failed")
                return res
            if (
                index_path.exists()
                and not force
                and index_path.stat().st_mtime >= tree_path.stat().st_mtime
            ):
                mark("index", "skipped (up to date)")
            else:
                write_indexes(e.pub_id, dirs.json)
                mark("index", "done")
        if not (want & {"plan", "render", "qa"}):
            return res
        if not (tree_path.exists() and index_path.exists()):
            res.status, res.message = "failed", "run convert and index first"
            return res
        tree = DocTree.model_validate_json(tree_path.read_text())
        if tree.pub.source_sha256 != meta.sha256:
            res.status, res.message = "failed", "document tree is from another PDF; run convert"
            return res
        indexes = Indexes.model_validate_json(index_path.read_text())

        spec_path = dirs.specs / f"{e.pub_id}.spec.json"
        spec_data = json.loads(spec_path.read_text()) if spec_path.exists() else None
        stale = spec_data is not None and (
            spec_data.get("pub", {}).get("source_sha256") != meta.sha256
        )
        if spec_data is None or stale:
            # no spec for this PDF: a person plans it. Write the packet and stop.
            from .plan.packet import build_packet

            gate_line = f"Distribution {meta.gate.distribution} ({meta.gate.reason})"
            try:
                readme = build_packet(tree, indexes, dirs.packets / e.pub_id, target, gate_line)
                mark("plan", "packet written")
                res.message = f"packet: {readme.parent}/"
            except ValueError as ex:
                mark("plan", "failed")
                res.status, res.message = "failed", f"planning packet: {ex}"
                return res
            res.status = "needs_planning"
            res.message += (
                " (spec is for an older revision of the PDF)" if stale else " (no committed spec)"
            )
            return res
        from .plan.check import check_spec

        if "plan" in want:
            findings = check_spec(spec_data, tree)
            errs = [f for f in findings if f.level == "error"]
            if errs:
                mark("plan", f"{len(errs)} spec error(s)")
                res.status, res.message = "failed", f"spec check: {errs[0]}"
                return res
            mark("plan", "spec ok")
        deck = dirs.decks / f"{e.pub_id}.pptx"
        if "render" in want:
            from .plan.spec import SlideSpec
            from .render.deck import render_deck

            result = render_deck(SlideSpec.model_validate(spec_data), tree, deck)
            mark("render", f"{result.slide_count} slides")
        if "qa" in want:
            from .qa.rules import run_qa

            report = run_qa(spec_path, tree, indexes, deck)
            out = dirs.qa / e.pub_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "qa.json").write_text(json.dumps(report.to_json(), indent=1), encoding="utf-8")
            mark("qa", f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
            if report.errors:
                res.status, res.message = "failed", f"qa: {report.errors[0]}"
    except Exception as ex:  # one bad publication must not stop the batch
        res.status = "failed"
        res.message = f"{type(ex).__name__}: {ex}"
    return res


def run_batch(
    entries: list[Entry],
    dirs: Dirs = Dirs(),
    stages: tuple[str, ...] = STAGES,
    force: bool = False,
    target: int = 34,
    progress: Callable[[str], None] | None = None,
) -> BatchReport:
    report = BatchReport()
    for e in entries:
        if progress:
            progress(f"{e.pub_id} ...")
        report.results.append(process(e, dirs, stages, force, target))
    dirs.batch.mkdir(parents=True, exist_ok=True)
    (dirs.batch / "report.json").write_text(json.dumps(report.to_json(), indent=1))
    return report


# ---------------------------------------------------------------- check-updates


@dataclass
class UpdateResult:
    pub_id: str
    #: unchanged | changed | rejected | unreachable | no_source
    status: str
    message: str = ""
    held_date: str | None = None
    new_date: str | None = None
    spec_stale: bool = False

    @property
    def is_error(self) -> bool:
        return self.status in ("rejected", "unreachable")


def _source_for(e: Entry, meta: PubMetadata | None, dirs: Dirs) -> tuple[Path | None, str | None]:
    if e.pdf:
        return e.pdf, None
    if e.url:
        return None, e.url
    candidate = dirs.inbox / f"{e.pub_id}.pdf"
    if candidate.exists():
        return candidate, None
    if meta and meta.source_url:
        return None, meta.source_url
    return None, None


def check_one(
    e: Entry,
    dirs: Dirs = Dirs(),
    fetcher: Callable[[str, Path], None] = download,
) -> UpdateResult:
    """Compare the PDF we hold with the current one (downloaded, or a local candidate).

    Read-only for the project: the candidate is checked in a temp folder, through the same
    Distribution A gate, and never replaces what is in data/raw. To adopt it, re-run `fetch`.
    """
    from .fetch.fetch import ingest

    meta = _load_meta(e.pub_id, dirs)
    if meta is None:
        return UpdateResult(e.pub_id, "no_source", "not fetched yet: nothing to compare")
    held = str(meta.pub_date) if meta.pub_date else None
    src, url = _source_for(e, meta, dirs)
    if src is None and url is None:
        return UpdateResult(
            e.pub_id, "no_source", f"no URL on record; put a newer PDF at {dirs.inbox}/", held
        )
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        try:
            if url:
                src = tmpdir / "candidate.pdf"
                fetcher(url, src)
            assert src is not None
            cand = ingest(src, e.pub_id, source_url=url, raw_dir=tmpdir / "raw")
        except FetchError as ex:
            return UpdateResult(e.pub_id, "unreachable", str(ex), held)
        except Exception as ex:  # unreadable or corrupt PDF
            return UpdateResult(e.pub_id, "unreachable", f"{type(ex).__name__}: {ex}", held)
    new = str(cand.pub_date) if cand.pub_date else None
    if cand.gate.status != "pass":
        return UpdateResult(
            e.pub_id, "rejected", f"candidate fails the Distribution A gate: {cand.gate.reason}",
            held, new,
        )  # fmt: skip
    if cand.sha256 == meta.sha256:
        return UpdateResult(e.pub_id, "unchanged", "same PDF", held, new)
    spec_path = dirs.specs / f"{e.pub_id}.spec.json"
    spec_stale = False
    if spec_path.exists():
        spec_stale = json.loads(spec_path.read_text()).get("pub", {}).get("source_sha256") != (
            cand.sha256
        )
    if cand.pub_date and meta.pub_date and cand.pub_date > meta.pub_date:
        why = f"newer: {held} -> {new}"
    elif cand.pub_date and meta.pub_date and cand.pub_date < meta.pub_date:
        why = f"older than the one held ({new} < {held}); check the source"
    else:
        why = "different file with the same or unknown date (a change or reprint)"
    if cand.supersedes:
        why += f"; supersedes {cand.supersedes}"
    if spec_stale:
        why += "; the committed spec was planned from the old PDF and needs re-planning"
    return UpdateResult(e.pub_id, "changed", why, held, new, spec_stale)


def known_entries(dirs: Dirs) -> list[Entry]:
    """Every publication with a metadata record in data/raw."""
    return [
        Entry(p.name.removesuffix(".meta.json"))
        for p in sorted(dirs.raw.glob("*.meta.json"))
        if not p.name.startswith(".")
    ]


def check_updates(
    entries: list[Entry] | None = None,
    dirs: Dirs = Dirs(),
    fetcher: Callable[[str, Path], None] = download,
) -> list[UpdateResult]:
    return [check_one(e, dirs, fetcher) for e in (entries or known_entries(dirs))]
