"""Typer CLI. Stage commands are stubs until their work packages land."""

from __future__ import annotations

from pathlib import Path

import typer

from .fetch.fetch import RAW_DIR, FetchError
from .fetch.fetch import fetch as run_fetch

app = typer.Typer(
    help="Turn public (Distribution A) Army regulations into training decks. "
    "Decks are unofficial training aids.",
    no_args_is_help=True,
)

PUB = typer.Argument(help="Publication, e.g. AR-600-20, or a local PDF path.")


def _stub(stage: str, wp: str) -> None:
    typer.echo(f"`{stage}` is not implemented yet (see WP {wp} in docs/ACTION_PLAN.md).")
    raise typer.Exit(code=2)


@app.command()
def fetch(
    pub: str = PUB,
    url: str | None = typer.Option(None, help="armypubs.army.mil PDF URL to download."),
    pdf: Path | None = typer.Option(None, help="Local PDF to ingest instead of downloading."),
) -> None:
    """Stage 1: download/accept a PDF, write metadata, run the Distribution A gate."""
    try:
        meta = run_fetch(pub, url=url, pdf_path=pdf)
    except FetchError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(
        f"{meta.pub_id}: gate passed (Distribution {meta.gate.distribution}), "
        f"{meta.page_count} pages, sha256 {meta.sha256[:12]}"
    )


@app.command()
def convert(pub: str = PUB) -> None:
    """Stages 2-3: gated PDF to clean Markdown (data/md/) and document tree (data/json/)."""
    from .convert.pipeline import MD_DIR
    from .convert.pipeline import convert as run_convert
    from .fetch.pdf import normalize_pub_id
    from .llm_guard import GateError, load_gated_metadata
    from .structure.parse import build as build_tree

    pub_id = normalize_pub_id(pub)
    try:
        meta = load_gated_metadata(pub_id, RAW_DIR)
    except GateError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    out = run_convert(meta, RAW_DIR)
    tree = build_tree(pub_id, MD_DIR)
    typer.echo(f"{pub_id}: wrote {out}, {out.with_suffix('.report.json')}, {tree}")


@app.command()
def index(pub: str = PUB) -> None:
    """Stage 3b: directives, deadlines, roles, cross-references and glossary indexes."""
    from .fetch.pdf import normalize_pub_id
    from .index.build import JSON_DIR, write_indexes

    pub_id = normalize_pub_id(pub)
    if not (JSON_DIR / f"{pub_id}.json").exists():
        typer.echo(f"error: no document tree for {pub_id}; run `convert` first.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{pub_id}: wrote {write_indexes(pub_id)}")


@app.command()
def plan(
    pub: str = PUB,
    hints: bool = typer.Option(False, "--hints", help="Write rule-based pattern hints."),
    packet: bool = typer.Option(
        False, "--packet", help="Write the planning packet to data/packets/<ID>/."
    ),
    check: bool = typer.Option(False, "--check", help="Validate a slide spec against the tree."),
    spec: Path | None = typer.Option(None, help="Spec to check (default specs/<ID>.spec.json)."),
    partial: bool = typer.Option(
        False, "--partial", help="With --check: skip deck-level checks (a chapter dry run)."
    ),
    review: bool = typer.Option(
        False, "--review", help="Print each cited statement next to its cited text."
    ),
    slides: str | None = typer.Option(None, help="With --review: slide ids, e.g. s05,s06."),
    target: int = typer.Option(34, help="With --packet: total slides to budget (25-40)."),
) -> None:
    """Stage 4: planning inputs and checks (the spec itself is written in a session, D10)."""
    import json

    from .fetch.pdf import normalize_pub_id
    from .index.build import JSON_DIR, Indexes
    from .llm_guard import GateError, load_gated_metadata
    from .structure.models import DocTree

    if not (hints or packet or check or review):
        typer.echo("error: choose --hints, --packet, --check or --review.", err=True)
        raise typer.Exit(code=2)
    pub_id = normalize_pub_id(pub)
    try:  # the session reads what these commands write: gate first (D10)
        meta = load_gated_metadata(pub_id, RAW_DIR)
    except GateError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    tree_path, index_path = JSON_DIR / f"{pub_id}.json", JSON_DIR / f"{pub_id}.indexes.json"
    if not (tree_path.exists() and index_path.exists()):
        typer.echo(f"error: run `convert` and `index` for {pub_id} first.", err=True)
        raise typer.Exit(code=1)
    tree = DocTree.model_validate_json(tree_path.read_text())
    if tree.pub.source_sha256 != meta.sha256:
        typer.echo(f"error: {tree_path} is from another PDF; re-run `convert`.", err=True)
        raise typer.Exit(code=1)

    if hints or packet:
        indexes = Indexes.model_validate_json(index_path.read_text())
    if hints:
        from .plan.classify import classify

        out = JSON_DIR / f"{pub_id}.hints.json"
        out.write_text(json.dumps([h.to_dict() for h in classify(tree, indexes)], indent=1))
        typer.echo(f"{pub_id}: wrote {out}")
    if packet:
        from .plan.packet import PACKET_DIR, build_packet

        gate_line = f"Distribution {meta.gate.distribution} ({meta.gate.reason})"
        try:
            readme = build_packet(tree, indexes, PACKET_DIR / pub_id, target, gate_line)
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2) from e
        typer.echo(f"{pub_id}: wrote {readme.parent}/ (start with README.md)")
    if check or review:
        spec_path = spec or Path("specs") / f"{pub_id}.spec.json"
        if not spec_path.exists():
            typer.echo(f"error: no spec at {spec_path}", err=True)
            raise typer.Exit(code=1)
        try:
            data = json.loads(spec_path.read_text())
        except json.JSONDecodeError as e:
            typer.echo(f"error: {spec_path} is not valid JSON: {e}", err=True)
            raise typer.Exit(code=1) from e
    if review:
        from .plan.check import review_lines

        ids = set(slides.split(",")) if slides else None
        for line in review_lines(data, tree, ids):
            typer.echo(line)
    if check:
        from .plan.check import check_spec

        findings = check_spec(data, tree, partial=partial)
        for f in findings:
            typer.echo(str(f))
        errors = sum(f.level == "error" for f in findings)
        warnings = len(findings) - errors
        n = len(data.get("slides", []))
        typer.echo(f"{spec_path}: {n} slides, {errors} error(s), {warnings} warning(s)")
        if errors:
            raise typer.Exit(code=1)


@app.command()
def render(
    pub: str = PUB,
    spec: Path | None = typer.Option(None, help="Slide spec (default specs/<ID>.spec.json)."),
    out: Path | None = typer.Option(None, help="Output .pptx (default out/decks/<ID>.pptx)."),
) -> None:
    """Stage 5: render the slide spec to .pptx (checks the spec first)."""
    import json

    from .fetch.pdf import normalize_pub_id
    from .index.build import JSON_DIR
    from .llm_guard import GateError, load_gated_metadata
    from .plan.check import check_spec
    from .plan.spec import SlideSpec
    from .render.deck import render_deck
    from .structure.models import DocTree

    pub_id = normalize_pub_id(pub)
    try:
        meta = load_gated_metadata(pub_id, RAW_DIR)
    except GateError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    tree_path = JSON_DIR / f"{pub_id}.json"
    spec_path = spec or Path("specs") / f"{pub_id}.spec.json"
    for p, hint in ((tree_path, "run `convert`"), (spec_path, "plan the deck first (WP 2.3)")):
        if not p.exists():
            typer.echo(f"error: missing {p}: {hint}.", err=True)
            raise typer.Exit(code=1)
    tree = DocTree.model_validate_json(tree_path.read_text())
    if tree.pub.source_sha256 != meta.sha256:
        typer.echo(f"error: {tree_path} is from another PDF; re-run `convert`.", err=True)
        raise typer.Exit(code=1)
    data = json.loads(spec_path.read_text())
    findings = check_spec(data, tree)
    errors = [f for f in findings if f.level == "error"]
    for f in errors:
        typer.echo(str(f), err=True)
    if errors:
        typer.echo(f"error: {len(errors)} spec error(s); fix them (`plan --check`).", err=True)
        raise typer.Exit(code=1)
    out_path = out or Path("out/decks") / f"{pub_id}.pptx"
    result = render_deck(SlideSpec.model_validate(data), tree, out_path)
    typer.echo(f"{pub_id}: wrote {out_path} ({result.slide_count} slides)")
    if result.splits:
        typer.echo(f"  split for fit: {', '.join(result.splits)}")
    if result.unsplit_warnings:
        typer.echo(f"  {len(result.unsplit_warnings)} text box(es) at minimum size may be tight:")
        for w in result.unsplit_warnings:
            typer.echo(f"    {w}")


@app.command()
def qa(
    pub: str = PUB,
    review_packet: bool = typer.Option(
        False, "--review-packet", help="Write the fidelity review packet (WP 4.1)."
    ),
    review_check: bool = typer.Option(
        False, "--review-check", help="Check specs/<ID>.review.json against the spec."
    ),
    report: bool = typer.Option(
        False, "--report", help="Also write the static review report (out/reports/<ID>/)."
    ),
    spec: Path | None = typer.Option(None, help="Spec (default specs/<ID>.spec.json)."),
) -> None:
    """Stage 6: rule-based checks (default), fidelity review packet and review check."""
    from .fetch.pdf import normalize_pub_id
    from .index.build import JSON_DIR, Indexes
    from .llm_guard import GateError, load_gated_metadata
    from .qa.review import Review, build_review_packet, check_review
    from .structure.models import DocTree

    pub_id = normalize_pub_id(pub)
    try:  # the session reads the packet: gate first (D10)
        meta = load_gated_metadata(pub_id, RAW_DIR)
    except GateError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    spec_path = spec or Path("specs") / f"{pub_id}.spec.json"
    if not spec_path.exists():
        typer.echo(f"error: no spec at {spec_path}", err=True)
        raise typer.Exit(code=1)
    if not (review_packet or review_check):
        _run_rules(pub_id, meta, spec_path, report)
        return
    if review_packet:
        tree_path, index_path = JSON_DIR / f"{pub_id}.json", JSON_DIR / f"{pub_id}.indexes.json"
        if not (tree_path.exists() and index_path.exists()):
            typer.echo(f"error: run `convert` and `index` for {pub_id} first.", err=True)
            raise typer.Exit(code=1)
        tree = DocTree.model_validate_json(tree_path.read_text())
        if tree.pub.source_sha256 != meta.sha256:
            typer.echo(f"error: {tree_path} is from another PDF; re-run `convert`.", err=True)
            raise typer.Exit(code=1)
        indexes = Indexes.model_validate_json(index_path.read_text())
        deck = Path("out/decks") / f"{pub_id}.pptx"
        out = build_review_packet(spec_path, tree, indexes, Path("data/packets") / pub_id, deck)
        typer.echo(f"{pub_id}: wrote {out}" + ("" if deck.exists() else " (no rendered deck)"))
    if review_check:
        review_path = spec_path.with_name(f"{pub_id}.review.json")
        if not review_path.exists():
            typer.echo(f"error: no review at {review_path}", err=True)
            raise typer.Exit(code=1)
        report = check_review(Review.model_validate_json(review_path.read_text()), spec_path)
        for e in report.errors:
            typer.echo(f"ERROR   {e}")
        for f in report.open_blocking:
            typer.echo(f"OPEN    {f.verdict} {f.claim}: {f.note}")
        c = report.counts
        typer.echo(
            f"{review_path}: {sum(c.values())} claims: {c['pass']} pass, {c['minor']} minor, "
            f"{c['major']} major, {c['critical']} critical; "
            + ("PASSES" if report.passes else "DOES NOT PASS")
        )
        if not report.passes:
            raise typer.Exit(code=1)


def _run_rules(pub_id: str, meta, spec_path: Path, write_report: bool = False) -> None:
    import json

    from .index.build import JSON_DIR, Indexes
    from .qa.rules import CHECKS, run_qa
    from .structure.models import DocTree

    tree_path, index_path = JSON_DIR / f"{pub_id}.json", JSON_DIR / f"{pub_id}.indexes.json"
    if not (tree_path.exists() and index_path.exists()):
        typer.echo(f"error: run `convert` and `index` for {pub_id} first.", err=True)
        raise typer.Exit(code=1)
    tree = DocTree.model_validate_json(tree_path.read_text())
    if tree.pub.source_sha256 != meta.sha256:
        typer.echo(f"error: {tree_path} is from another PDF; re-run `convert`.", err=True)
        raise typer.Exit(code=1)
    indexes = Indexes.model_validate_json(index_path.read_text())
    deck = Path("out/decks") / f"{pub_id}.pptx"
    report = run_qa(spec_path, tree, indexes, deck)
    if write_report:
        from .qa.report import build_report

        page = build_report(
            spec_path, tree, report, Path("out/reports") / pub_id, deck,
            spec_path.with_name(f"{pub_id}.review.json"),
        )  # fmt: skip
        typer.echo(f"report: {page}")
    out = Path("data/qa") / pub_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "qa.json").write_text(json.dumps(report.to_json(), indent=1), encoding="utf-8")
    for f in report.findings:
        typer.echo(str(f))
    typer.echo("")
    for name in CHECKS:
        fs = report.by_check(name)
        errs = sum(f.level == "error" for f in fs)
        typer.echo(f"  {name:12} {errs} error(s), {len(fs) - errs} warning(s)")
    r, c = report.readability, report.coverage
    typer.echo(
        f"readability (D15): {r['slides_ok']}/{r['scored_slides']} slides at grade 9 or below "
        f"({r['slide_share']:.0%}, target {r['target_share']:.0%}: "
        f"{'PASS' if r['passed'] else 'FAIL'}); neutralized statement mean {r['mean_grade']}; "
        f"coverage: {c['cited']}/{c['mandatory_requirements']} mandatory requirements cited "
        f"({c['share']:.0%})" + ("" if report.deck_checked else "; deck not rendered")
    )
    typer.echo(
        f"{pub_id}: {len(report.errors)} error(s), {len(report.warnings)} warning(s); "
        f"{out / 'qa.json'}"
    )
    if report.errors:
        raise typer.Exit(code=1)


@app.command()
def build(pub: str = PUB) -> None:
    """Run every stage for one publication."""
    _stub("build", "5.3")


if __name__ == "__main__":
    app()
