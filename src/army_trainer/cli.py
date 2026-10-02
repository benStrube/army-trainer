"""Typer CLI. Stage commands are stubs until their work packages land."""

from __future__ import annotations

import typer

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
def fetch(pub: str = PUB) -> None:
    """Stage 1: download/accept a PDF, write metadata, run the Distribution A gate."""
    _stub("fetch", "0.2")


@app.command()
def convert(pub: str = PUB) -> None:
    """Stage 2-3: PDF to Markdown and JSON document tree."""
    _stub("convert", "1.2-1.3")


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
