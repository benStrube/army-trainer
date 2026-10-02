# Document tree (stage 3)

`army-trainer convert <ID>` writes `data/json/<ID>.json`. Every later stage reads this file to find paragraphs, tables, terms and their citations. It never goes back to the PDF.

- **Schema:** [`schemas/doc_tree.schema.json`](../schemas/doc_tree.schema.json), JSON Schema 2020-12. It is generated from `src/army_trainer/structure/models.py`.
- **Owner:** Opus. Sonnet may read and use the tree, but changes to the models or schema go through a handover to Opus (see `CLAUDE.md`).
- **Version:** `schema_version: "1.0"`.

Regenerate the schema after changing the models (a test fails if it's stale):
```
uv run python -m army_trainer.structure.schema
```

## Shape

```
DocTree
├── schema_version   "1.0"
├── pub              pub_id, title, pub_date, supersedes, proponent, distribution, source_sha256, page_count
└── divisions[]      Division (kind: preface | introduction | chapter | appendix | glossary | references | source_notes)
    └── children[]   Section | Heading | Paragraph | Table | Figure | Text | ListItem | Term | Acronym
        Section      "SECTION II – ..."   → children[] (same union)
        Heading      level 2–6            → children[] (same union)
        Paragraph    numbered "1-11."     → children[]: ListItem | Text
        ListItem     bullet, depth 0–2    → children[]: ListItem
```

Nesting follows the Markdown heading levels. Levels can skip: Appendix D goes straight from a section (`##`) to a minor heading (`####`), as the FM does. Consumers must walk `children` and must not assume levels go up one at a time.

## Fields on every node

| Field | Meaning |
|---|---|
| `type` | Node kind (the discriminator) |
| `id` | Stable, unique within the document. Use it as the slide spec's reference key |
| `cite` | What a slide footer prints after the publication ID, e.g. `para 1-11`, `table 1-2`, `figure 2-1`, `glossary, kill box`, `p. 1-3` |
| `page` | 1-based PDF page where the node starts |
| `page_label` | Page number printed on that page (`1-3`, `vii`, `Glossary-4`). Missing on unnumbered pages |

## Node types

| `type` | `id` pattern | Key fields | Notes |
|---|---|---|---|
| `division` | `ch-2`, `app-b`, `preface`, `introduction`, `glossary`, `references`, `source-notes` | `kind`, `number` ("2", "B"), `title` | `cite`: `chapter 2`, `appendix B` |
| `section` | `ch-2.sec-ii` | `number` (Roman), `title` | `cite`: `chapter 2, section II` |
| `heading` | `<parent>.<slug>` | `level`, `title` | Titles keep the PDF's capitalization (often ALL CAPS) |
| `paragraph` | `para-2-5`, `para-B-18` | `number`, `text`, `plain` | **The unit slides cite.** `text` excludes the number |
| `list_item` | `para-2-5.li1`, `para-2-5.li1.li2` | `depth`, `text`, `plain` | Inherits its paragraph's `cite` |
| `text` | `para-2-5.t1`, `ch-1.t1` | `text`, `plain` | Unnumbered text. It's a child of the paragraph it continues, or of the container when no paragraph has started (chapter introductions, quotes) |
| `table` | `table-1-2`, `table-introductory-1` | `number`, `caption`, `columns`, `rows`, `key`, `grid` | Cells are Markdown. `<br>` separates bullets in a cell. `key` is the abbreviation key printed under the table. `grid: false` means the PDF prints the table as plain text (e.g. the Table A-1 checklist): `columns`/`rows` are empty and the content follows as sibling nodes |
| `figure` | `figure-2-1` | `number`, `caption` | Caption only. Images aren't extracted (see the WP 1.2 handover) |
| `term` | `term-kill-box` | `term`, `definition`, `source`, `proponent` | `proponent: true` means this publication defines the term (`*` in the glossary). Otherwise `source` names the defining publication |
| `acronym` | `acr-fscoord` | `abbreviation`, `meaning` | From glossary section I |

`text` fields keep Markdown emphasis. In FMs, italics mark a defined term (`_Fire support_ is …`) and bold-italics mark a term this FM is the proponent for. `plain` has the emphasis removed: use it for verbatim checks, readability scores and search.

## Rules for consumers

- **Cite with `cite`**, prefixed by the publication: `FM 3-09, para 2-5`. Never make up a citation. If a node has none, use its paragraph's.
- **Verbatim checks** (WP 4.2) compare slide text against `plain` of the cited node and its children.
- **Paragraph numbers are unique** within a publication. Other IDs are unique too: a repeat gets a `-2` suffix.
- The tree only contains what's in the converted Markdown. Front matter lists, the index and blank pages are dropped by design.

## FM 3-09 (pilot) at a glance

16 divisions · 44 sections · 332 headings · 933 paragraphs · 1,381 list items · 162 unnumbered texts · 40 tables (9 gridless) · 41 figures · 251 terms (35 FM-proponent) · 146 acronyms.
