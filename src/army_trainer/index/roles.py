"""Roles: people/positions and organizations that the publication assigns duties to.

Seeds come from the tree itself (no hand-written role list for the pilot):
  1. headings under "...PERSONNEL" and "COMMAND POSTS" style containers, matched to the
     acronym list by squashed (space-free, case-folded) text, since the PDF headings lose
     their spaces (e.g. "FIRESUPPORTCOORDINATOR");
  2. glossary acronyms whose meaning contains a role word.
Each role then gets mention counts and the sentences in which it is the grammatical
subject of a directive verb.
"""

from __future__ import annotations

import re

from ..structure.models import DocTree
from .directives import _PAT
from .walk import split_sentences, text_nodes, walk_tree

ROLE_WORDS = re.compile(
    r"\b(officer|NCO|noncommissioned|sergeant|commander|chief|coordinator|observer|"
    r"director|planner|liaison|representative|leader|operator|specialist|chief of|"
    r"staff)\b",
    re.I,
)
# Heading containers whose children name roles.
ROLE_CONTAINERS = re.compile(r"PERSONNEL|FIRE SUPPORT ELEMENT|COMMAND POSTS?", re.I)
_ORG_LAST = {
    "post",
    "center",
    "cell",
    "element",
    "elements",
    "team",
    "agencies",
    "party",
    "detachment",
    "company",
    "command",
    "group",
    "force",
    "headquarters",
    "organizations",
    "control",
}
MAX_NAME_WORDS = 8


def _kind(name: str) -> str:
    words = name.lower().split()
    if words[0] in ("commander", "chief"):
        return "position"
    return "organization" if words[-1] in _ORG_LAST else "position"


_SKIP_ABBR = {"BCT", "AO", "OA"}


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _vocabulary(tree: DocTree) -> dict[str, int]:
    """Lowercase word counts from body text, terms and acronym meanings."""
    vocab: dict[str, int] = {}
    for node, _ in walk_tree(tree):
        if node.type in ("paragraph", "list_item", "text"):
            blob = node.plain
        elif node.type == "term":
            blob = node.term
        elif node.type == "acronym":
            blob = node.meaning
        else:
            continue
        for w in re.findall(r"[a-z]+", blob.lower()):
            vocab[w] = vocab.get(w, 0) + 1
    return vocab


def segment(squashed: str, vocab: dict[str, int]) -> str | None:
    """Split a space-less heading ("firesupportofficer") into words using the vocabulary.

    Fewest words wins; ties go to the more frequent words. Returns None if no split exists.
    """
    s = squashed.lower()
    best: list[tuple[int, int, list[str]] | None] = [None] * (len(s) + 1)
    best[0] = (0, 0, [])
    for i in range(1, len(s) + 1):
        for j in range(max(0, i - 20), i):
            prev = best[j]
            w = s[j:i]
            if prev is None or w not in vocab:
                continue
            cand = (prev[0] + 1, prev[1] - min(vocab[w], 1000), [*prev[2], w])
            if best[i] is None or cand[:2] < best[i][:2]:
                best[i] = cand
    return " ".join(best[len(s)][2]) if best[len(s)] else None


def _acronym_roles(tree: DocTree) -> dict[str, dict]:
    roles: dict[str, dict] = {}
    for node, _ in walk_tree(tree):
        if node.type == "acronym" and ROLE_WORDS.search(node.meaning):
            if node.abbreviation in _SKIP_ABBR:
                continue
            roles[_squash(node.meaning)] = {
                "kind": "position",
                "name": node.meaning,
                "abbreviation": node.abbreviation,
                "source": "acronym",
                "defined_at": node.cite,
            }
    return roles


def _heading_roles(tree: DocTree, known: dict[str, dict]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    vocab = _vocabulary(tree)
    for node, path in walk_tree(tree):
        if node.type != "heading":
            continue
        if not any(a.type == "heading" and ROLE_CONTAINERS.search(a.title) for a in path):
            continue
        if node.level < 4:
            continue
        key = _squash(node.title)
        if not key or node.title.upper().startswith("OTHER "):
            continue
        match = known.get(key)
        spaced = segment(key, vocab)
        if not match and (not spaced or len(spaced.split()) > MAX_NAME_WORDS):
            continue  # unsegmentable or a catch-all heading ("Other ... personnel and duties")
        entry = {
            "name": match["name"] if match else (spaced or node.title).lower(),
            "abbreviation": match["abbreviation"] if match else None,
            "source": "heading",
            "defined_at": node.cite or f"p. {node.page_label or node.page}",
            "heading_id": node.id,
            "kind": _kind(match["name"] if match else spaced),
        }
        found[key] = entry
    return found


def extract_roles(tree: DocTree) -> list[dict]:
    from_acr = _acronym_roles(tree)
    from_head = _heading_roles(tree, from_acr)
    roles = {**from_acr, **from_head}
    # Prefer heading source where both exist but keep abbreviation from acronym.
    for key, entry in from_head.items():
        if key in from_acr:
            entry["source"] = "heading+acronym"

    texts = [(n, p) for n, p in text_nodes(tree)]
    result: list[dict] = []
    for _key, role in sorted(roles.items(), key=lambda kv: kv[1]["name"].lower()):
        # Case-insensitive name, case-sensitive abbreviation.
        name_pat = re.compile(re.escape(role["name"]), re.I)
        abbr_pat = (
            re.compile(r"(?<![A-Za-z0-9-])" + re.escape(role["abbreviation"]) + r"(?![A-Za-z0-9-])")
            if role.get("abbreviation")
            else None
        )
        mentions = 0
        duties: list[dict] = []
        cites: list[str] = []
        for node, _ in texts:
            hit = name_pat.search(node.plain) or (abbr_pat and abbr_pat.search(node.plain))
            if not hit:
                continue
            mentions += 1
            if node.cite not in cites and len(cites) < 50:
                cites.append(node.cite)
            for sentence in split_sentences(node.plain):
                sm = name_pat.search(sentence) or (abbr_pat.search(sentence) if abbr_pat else None)
                if not sm:
                    continue
                vm = _PAT.search(sentence, sm.end())
                # subject = role appears before the verb with <=60 chars between
                if vm and vm.start() - sm.end() <= 60 and len(duties) < 100:
                    duties.append(
                        {
                            "node_id": node.id,
                            "cite": node.cite,
                            "verb": vm.group(1).lower(),
                            "sentence": sentence,
                        }
                    )
        result.append(
            {
                "name": role["name"],
                "abbreviation": role.get("abbreviation"),
                "kind": role.get("kind", "position"),
                "source": role["source"],
                "defined_at": role["defined_at"],
                "mention_count": mentions,
                "cites": cites,
                "duties": duties,
            }
        )
    return result
