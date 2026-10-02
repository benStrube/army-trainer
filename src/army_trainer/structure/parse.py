"""Stage 3: converted Markdown -> document tree (JSON).

Reads only the Markdown written by `convert` (front matter, headings, numbered paragraphs,
captions, tables, list items, page markers). It never looks at the PDF.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..convert.blocks import plain
from . import models as M

JSON_DIR = Path("data/json")

PAGE = re.compile(r"^<!-- page (\d+)(?: \(([^)]*)\))? -->$")
HEADING = re.compile(r"^(#{1,6}) (.+)$")
DIVISION = re.compile(r"^(Chapter (\d+)|Appendix ([A-Z])): (.+)$")
SECTION = re.compile(r"^SECTION ([IVXLC]+)\s*[–-]\s*(.+)$", re.I)
PARA = re.compile(r"^\**((?:\d+|[A-Z])-\d+)\.\**\s+(.*)$", re.S)
CAPTION = re.compile(r"^\*\*((?:Introductory )?(Table|Figure) ([A-Z]?-?\d+(?:-\d+)?)\.?\s.*)\*\*$")
BULLET = re.compile(r"^( *)- (.*)$", re.S)
TERM = re.compile(r"^(\*)?\*\*(.+?)\*\*\s+—\s+(.+)$", re.S)
SOURCE = re.compile(r"\s*\(((?:JP|ADP|ADRP|FM|ATP|AR|DA PAM|TC)\s[^()]+)\)\.?$")
_ABBR_ITEM = r"[A-Z][A-Za-z0-9/-]*\s*[\u2013-]+\s*"
KEY = re.compile(rf"^(?:{_ABBR_ITEM}[^,]+,\s*)+{_ABBR_ITEM}\S.*$")  # "FA – field artillery, ..."
NAMED = {
    "preface": "preface",
    "introduction": "introduction",
    "glossary": "glossary",
    "references": "references",
    "source notes": "source_notes",
}


def slug(s: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", plain(s).lower()).strip("-")
    return s[:limit].rstrip("-") or "x"


def _split_front_matter(md: str) -> tuple[dict, str]:
    if not md.startswith("---\n"):
        raise ValueError("Markdown has no YAML front matter; was it written by `convert`?")
    _, front, body = md.split("---\n", 2)
    return yaml.safe_load(front), body


def _table(block: str) -> tuple[list[str], list[list[str]]]:
    lines = [ln for ln in block.splitlines() if ln.strip()]

    def cells(ln: str) -> list[str]:
        inner = ln.strip()[1:-1]
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", inner)]

    header = cells(lines[0])
    rows = [cells(ln) for ln in lines[2:]]
    return header, rows


class _Builder:
    def __init__(self, pub_id: str):
        self.pub_id = pub_id
        self.divisions: list[M.Division] = []
        self.stack: list[M.Division | M.Section | M.Heading] = []
        self.para: M.Paragraph | None = None
        self.items: list[M.ListItem] = []  # open list items by depth
        self.caption: tuple[str, str, str] | None = None  # (caption, kind, number)
        self.caption_where: dict = {}
        self.last_table: M.Table | None = None
        self.page, self.label = 0, None
        self.ids: dict[str, int] = {}
        self.levels: dict[int, int] = {}  # id(node) -> Markdown level, for sections/headings

    # ---------------------------------------------------------------- helpers

    def uid(self, base: str) -> str:
        n = self.ids.get(base, 0)
        self.ids[base] = n + 1
        return base if n == 0 else f"{base}-{n + 1}"

    def where(self) -> dict:
        return {"page": self.page, "page_label": self.label}

    def container(self) -> M.Division | M.Section | M.Heading:
        if not self.stack:  # text before any division: shouldn't happen with convert output
            self.open_division("Untitled", "preface", None)
        return self.stack[-1]

    def page_cite(self) -> str:
        return f"p. {self.label}" if self.label else f"PDF p. {self.page}"

    def reset_flow(self) -> None:
        self.para, self.items, self.caption, self.last_table = None, [], None, None

    # ---------------------------------------------------------------- structure

    def open_division(self, title: str, kind: str, number: str | None) -> None:
        self.reset_flow()
        did = {"chapter": f"ch-{number}", "appendix": f"app-{(number or '').lower()}"}.get(
            kind, kind.replace("_", "-")
        )
        cite = {"chapter": f"chapter {number}", "appendix": f"appendix {number}"}.get(
            kind, title.lower()
        )
        div = M.Division(
            id=self.uid(did), cite=cite, kind=kind, number=number, title=title, **self.where()
        )
        self.divisions.append(div)
        self.stack = [div]

    def heading(self, level: int, title: str) -> None:
        if level == 1:
            m = DIVISION.match(title)
            if m:
                kind = "chapter" if m.group(2) else "appendix"
                self.open_division(m.group(4), kind, m.group(2) or m.group(3))
            else:
                self.open_division(title, NAMED.get(title.lower(), "preface"), None)
            return
        self.reset_flow()
        # close anything at this level or deeper (sections count as level 2)
        while len(self.stack) > 1 and self._level(self.stack[-1]) >= level:
            self.stack.pop()
        parent = self.stack[-1]
        m = SECTION.match(title)
        if m:
            node: M.Section | M.Heading = M.Section(
                id=self.uid(f"{parent.id}.sec-{m.group(1).lower()}"),
                cite=f"{parent.cite}, section {m.group(1).upper()}",
                number=m.group(1).upper(),
                title=m.group(2).strip(),
                **self.where(),
            )
        else:
            node = M.Heading(
                id=self.uid(f"{parent.id}.{slug(title)}"),
                cite=self.page_cite(),
                level=level,
                title=title,
                **self.where(),
            )
        parent.children.append(node)
        self.stack.append(node)
        self.levels[id(node)] = level

    def _level(self, node: M.Division | M.Section | M.Heading) -> int:
        return 1 if isinstance(node, M.Division) else self.levels[id(node)]

    # ---------------------------------------------------------------- content

    def paragraph(self, number: str, text: str) -> None:
        self.items, self.caption = [], None
        p = M.Paragraph(
            id=self.uid(f"para-{number}"),
            cite=f"para {number}",
            number=number,
            text=text.strip(),
            plain=plain(text),
            **self.where(),
        )
        self.container().children.append(p)
        self.para = p

    def bullet(self, depth: int, text: str) -> None:
        depth = min(depth, len(self.items))  # no jumping more than one level deeper
        self.items = self.items[:depth]
        if depth > 0:
            parent = self.items[-1]
            siblings = parent.children
            base, cite = parent.id, parent.cite
        elif self.para is not None:
            siblings = self.para.children
            base, cite = self.para.id, self.para.cite
        else:
            siblings = self.container().children
            base, cite = self.container().id, self.page_cite()
        n = sum(isinstance(s, M.ListItem) for s in siblings) + 1
        item = M.ListItem(
            id=self.uid(f"{base}.li{n}"),
            cite=cite,
            depth=depth,
            text=text.strip(),
            plain=plain(text),
            **self.where(),
        )
        siblings.append(item)
        self.items.append(item)

    def text(self, text: str) -> None:
        self.items = []
        div = self.stack[0] if self.stack else None
        if div is not None and div.kind == "glossary" and (m := TERM.match(text)):
            self.term(m)
            return
        if self.last_table is not None and self.last_table.key is None and KEY.match(plain(text)):
            self.last_table.key = plain(text)
            return
        if self.para is not None:  # unnumbered text continuing a numbered paragraph
            siblings, base, cite = self.para.children, self.para.id, self.para.cite
        else:
            siblings, base, cite = self.container().children, self.container().id, None
        n = sum(isinstance(s, M.Text) for s in siblings) + 1
        siblings.append(
            M.Text(
                id=self.uid(f"{base}.t{n}"),
                cite=cite or self.page_cite(),
                text=text.strip(),
                plain=plain(text),
                **self.where(),
            )
        )

    def term(self, m: re.Match[str]) -> None:
        name, definition = plain(m.group(2)), m.group(3).strip()
        source = None
        if s := SOURCE.search(definition):
            source = s.group(1).strip()
            definition = definition[: s.start()].rstrip()
        self.container().children.append(
            M.Term(
                id=self.uid(f"term-{slug(name)}"),
                cite=f"glossary, {name}",
                term=name,
                definition=definition,
                source=source,
                proponent=bool(m.group(1)),
                **self.where(),
            )
        )

    def caption_line(self, caption: str, kind: str, number: str) -> None:
        if kind == "Figure":
            self.container().children.append(
                M.Figure(
                    id=self.uid(f"figure-{slug(number)}"),
                    cite=f"figure {number}",
                    number=number,
                    caption=caption,
                    **self.where(),
                )
            )
            self.caption = None
        else:
            if caption.startswith("Introductory"):
                number = f"Introductory {number}"
            self.caption = (caption, kind, number)
            self.caption_where = self.where()

    def table(self, block: str) -> None:
        header, rows = _table(block)
        div = self.stack[0] if self.stack else None
        if div is not None and div.kind == "glossary" and header[:1] == ["Acronym"]:
            for r in rows:
                if len(r) >= 2 and r[0]:
                    abbr = plain(r[0])
                    self.container().children.append(
                        M.Acronym(
                            id=self.uid(f"acr-{slug(abbr)}"),
                            cite=f"glossary, {abbr}",
                            abbreviation=abbr,
                            meaning=plain(" ".join(c for c in r[1:] if c)),
                            **self.where(),
                        )
                    )
            return
        caption, number = (self.caption[0], self.caption[2]) if self.caption else (None, None)
        t = M.Table(
            id=self.uid(f"table-{slug(number)}" if number else f"{self.container().id}.table"),
            cite=f"table {number}" if number else self.page_cite(),
            number=number,
            caption=caption,
            columns=header,
            rows=rows,
            **self.where(),
        )
        self.container().children.append(t)
        self.caption, self.last_table, self.items = None, t, []

    def flush_gridless_table(self) -> None:
        """A table caption followed by something other than a table: the PDF prints that
        table as plain text. Keep it as a gridless table node so references to it resolve."""
        if not self.caption:
            return
        caption, _, number = self.caption
        self.container().children.append(
            M.Table(
                id=self.uid(f"table-{slug(number)}"),
                cite=f"table {number}",
                number=number,
                caption=caption,
                columns=[],
                rows=[],
                grid=False,
                **self.caption_where,
            )
        )
        self.caption = None

    # ---------------------------------------------------------------- driver

    def feed(self, block: str) -> None:
        block = block.strip("\n")
        if not block.strip():
            return
        if m := PAGE.match(block.strip()):
            self.page, self.label = int(m.group(1)), m.group(2)
            return
        if block.lstrip().startswith("|"):
            self.table(block)
            return
        self.flush_gridless_table()
        self.last_table = None if not KEY.match(plain(block)) else self.last_table
        if m := HEADING.match(block):
            self.heading(len(m.group(1)), m.group(2).strip())
        elif m := CAPTION.match(block.strip()):
            self.caption_line(m.group(1), m.group(2), m.group(3))
        elif m := PARA.match(block):
            self.paragraph(m.group(1), m.group(2))
        elif m := BULLET.match(block):
            self.bullet(len(m.group(1)) // 2, m.group(2))
        else:
            self.text(block)


def parse_markdown(md: str) -> M.DocTree:
    front, body = _split_front_matter(md)
    b = _Builder(front["pub_id"])
    for block in re.split(r"\n\n+", body):
        b.feed(block)
    pub = M.PubInfo(**{k: front.get(k) for k in M.PubInfo.model_fields})
    return M.DocTree(pub=pub, divisions=b.divisions)


def build(pub_id: str, md_dir: Path, out_dir: Path = JSON_DIR) -> Path:
    tree = parse_markdown((md_dir / f"{pub_id}.md").read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{pub_id}.json"
    out.write_text(tree.model_dump_json(indent=1, exclude_none=True))
    return out
