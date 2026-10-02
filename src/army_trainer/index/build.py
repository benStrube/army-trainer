"""Build all indexes for a document tree and write data/json/<ID>.indexes.json."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..structure.models import DocTree
from .crossrefs import extract_crossrefs
from .deadlines import extract_deadlines
from .directives import extract_directives
from .glossary import extract_glossary
from .roles import extract_roles

JSON_DIR = Path("data/json")
INDEX_VERSION = "1.0"


class Indexes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_version: str = INDEX_VERSION
    pub_id: str
    generated_from_sha256: str | None
    counts: dict[str, int]
    directives: list[dict]
    deadlines: list[dict]
    roles: list[dict]
    crossrefs: list[dict]
    glossary: dict


def build_indexes(tree: DocTree) -> Indexes:
    directives = extract_directives(tree)
    deadlines = extract_deadlines(tree)
    roles = extract_roles(tree)
    crossrefs = extract_crossrefs(tree)
    glossary = extract_glossary(tree)
    counts = {
        "directives": len(directives),
        "deadlines": len(deadlines),
        "roles": len(roles),
        "crossrefs": len(crossrefs),
        "terms": len(glossary["terms"]),
        "inline_definitions": len(glossary["inline_definitions"]),
        "acronyms": len(glossary["acronyms"]),
    }
    return Indexes(
        pub_id=tree.pub.pub_id,
        generated_from_sha256=tree.pub.source_sha256,
        counts=counts,
        directives=directives,
        deadlines=deadlines,
        roles=roles,
        crossrefs=crossrefs,
        glossary=glossary,
    )


def write_indexes(pub_id: str, json_dir: Path = JSON_DIR) -> Path:
    tree = DocTree.model_validate_json((json_dir / f"{pub_id}.json").read_text(encoding="utf-8"))
    out = json_dir / f"{pub_id}.indexes.json"
    out.write_text(build_indexes(tree).model_dump_json(indent=2), encoding="utf-8")
    return out
