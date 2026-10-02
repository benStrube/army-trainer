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
def plan(pub: str = PUB) -> None:
    """Stage 4: build the slide spec."""
    _stub("plan", "2.1-2.3")


@app.command()
def render(pub: str = PUB) -> None:
    """Stage 5: render the slide spec to .pptx."""
    _stub("render", "3.1-3.3")


@app.command()
def qa(pub: str = PUB) -> None:
    """Stage 6: fidelity/readability checks and review report."""
    _stub("qa", "4.1-4.3")


@app.command()
def build(pub: str = PUB) -> None:
    """Run every stage for one publication."""
    _stub("build", "5.3")


if __name__ == "__main__":
    app()
