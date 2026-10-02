"""Document tree: the typed structure every later stage reads (WP 1.3, Opus-owned).

The tree mirrors how Army publications are organized and cited:

    document
      division        chapter / appendix / preface / introduction / glossary / references /
                      source notes
        section       "SECTION I – ..." (optional)
          heading     any level, nested by Markdown level
            paragraph numbered "1-11." -- the unit slides cite
              list_item   bullets, nested by depth
              text        unnumbered text that continues the paragraph
            table / figure / text
        term / acronym    glossary entries

Every node carries `id` (stable within a document), `cite` (what a slide footer prints),
and `page` / `page_label` (PDF page and the page number printed on it).
See docs/doc_tree.md and schemas/doc_tree.schema.json.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

DivisionKind = Literal[
    "preface", "introduction", "chapter", "appendix", "glossary", "references", "source_notes"
]


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable within the document, e.g. 'para-1-11', 'table-1-2'.")
    cite: str = Field(description="Citation for slide footers, e.g. 'para 1-11', 'table 1-2'.")
    page: int = Field(description="1-based PDF page where the node starts.")
    page_label: str | None = Field(
        default=None, description="Page number printed on that page, e.g. '1-3', 'vii'."
    )


class Text(_Node):
    type: Literal["text"] = "text"
    text: str = Field(description="Markdown as converted (emphasis kept).")
    plain: str = Field(description="Text with Markdown emphasis removed.")


class ListItem(_Node):
    type: Literal["list_item"] = "list_item"
    depth: int = Field(ge=0, description="0 for a top-level bullet.")
    text: str
    plain: str
    children: list[ListItem] = Field(default_factory=list)


class Paragraph(_Node):
    type: Literal["paragraph"] = "paragraph"
    number: str = Field(description="Paragraph number as printed, e.g. '1-11', 'B-18'.")
    text: str = Field(description="Markdown of the paragraph, without its number.")
    plain: str
    children: list[Annotated[ListItem | Text, Field(discriminator="type")]] = Field(
        default_factory=list
    )


class Table(_Node):
    type: Literal["table"] = "table"
    number: str | None = Field(default=None, description="'1-2', 'E-3', 'Introductory 1'.")
    caption: str | None = None
    columns: list[str] = Field(description="Header row.")
    rows: list[list[str]] = Field(description="Body rows; cells are Markdown.")
    key: str | None = Field(default=None, description="Abbreviation key printed under it.")
    grid: bool = Field(
        default=True,
        description="False when the PDF prints the table as plain text (e.g. a checklist): "
        "columns and rows are empty and the content follows as sibling text/list nodes.",
    )


class Figure(_Node):
    type: Literal["figure"] = "figure"
    number: str | None = None
    caption: str


class Term(_Node):
    type: Literal["term"] = "term"
    term: str
    definition: str
    source: str | None = Field(default=None, description="Proponent publication, e.g. 'JP 3-09'.")
    proponent: bool = Field(
        default=False, description="True when this publication is the term's proponent (*)."
    )


class Acronym(_Node):
    type: Literal["acronym"] = "acronym"
    abbreviation: str
    meaning: str


Content = Annotated[
    "Heading | Section | Paragraph | Table | Figure | Text | ListItem | Term | Acronym",
    Field(discriminator="type"),
]


class Heading(_Node):
    type: Literal["heading"] = "heading"
    level: int = Field(ge=2, le=6, description="Markdown level; levels may skip (## -> ####).")
    title: str
    children: list[Content] = Field(default_factory=list)


class Section(_Node):
    type: Literal["section"] = "section"
    number: str = Field(description="Roman numeral, e.g. 'II'.")
    title: str
    children: list[Content] = Field(default_factory=list)


class Division(_Node):
    type: Literal["division"] = "division"
    kind: DivisionKind
    number: str | None = Field(default=None, description="'2' for Chapter 2, 'B' for Appendix B.")
    title: str
    children: list[Content] = Field(default_factory=list)


class PubInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pub_id: str
    title: str | None = None
    pub_date: date | None = None
    supersedes: str | None = None
    proponent: str | None = None
    distribution: str
    source_sha256: str
    page_count: int


class DocTree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    pub: PubInfo
    divisions: list[Division]


for _m in (ListItem, Heading, Section, Division, DocTree):
    _m.model_rebuild()
