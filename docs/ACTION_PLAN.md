# Action Plan — Two-Model Build

This plan breaks the phases in [PROJECT_SCOPE.md](PROJECT_SCOPE.md) §6 into **work packages (WPs)** and assigns each one to a model tier:

- **Sonnet** builds well-specified code: scaffolding, the CLI, rendering, rule-based checks, tests, batch tooling.
- **Opus** handles the parts that need judgment and set quality for everything downstream: the PDF cleanup rules, the document tree design, the slide planner, the prompts sent to Claude, and the fidelity judge.

The stop and handover rules are in [`CLAUDE.md`](../CLAUDE.md). This file is the single source of truth for **status**. Update the Status column at every handover.

**Stop column:**
- 🛑 **STOP**: hard stop. Write a handover, push, and end the session. These sit at model switches and phase ends.
- ➡️ **continue**: write a short handover entry, then you may continue into the next WP in the same session (same model).

Status values: `todo` · `in progress` · `done` · `blocked`

## Work packages

### Phase 0 — Setup
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 0.1 | Scaffold: `uv` project, `src/army_trainer/` package layout (§5 of scope), Typer CLI with stub commands, pytest, ruff, GitHub Actions CI, `.gitignore` for `data/` and `out/` | Sonnet | `uv run army-trainer --help` works; CI green; tests run | ➡️ continue | done |
| 0.2 | Fetch stage + **Distribution A gate**: download/accept PDF, metadata JSON (title, date, proponent, distribution, SHA-256, source URL), gate that rejects anything not Distribution A; API-client guard that refuses ungated docs | Sonnet | Pilot PDFs (AR 600-20, AR 670-1, AR 623-3) in `data/raw/` with metadata; gate unit tests including a rejection case | ➡️ continue | done (pilot changed to FM 3-09 per D8; gated from the user-supplied PDF) |
| 0.3 | Branding research subtask (see `docs/SETUP_NOTES.md`): pull brand rules and examples from several army.mil sites | Sonnet | Every checklist item in `SETUP_NOTES.md` filled in with source URL + date, or marked "not found" with what was searched | 🛑 **STOP** → Opus | blocked (army.mil unreachable; see SETUP_NOTES) |

### Phase 1 — Convert
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 1.1 | Converter bake-off: Docling vs. pymupdf4llm (pdfplumber for tables) on one AR 600-20 chapter; record the decision and why | Opus | Decision + comparison written to `docs/decisions/converter.md` | ➡️ continue | done (final for the FM 3-09 pilot, D7/D8) |
| 1.2 | AR post-processing: headers/footers, paragraph numbering + hierarchy, hyphen/page-break joins, tables, figures, glossary, Summary of Change, YAML front matter | Opus | FM 3-09 pilot converts; spot-check ≥ 98% paragraph-structure accuracy; tables intact; golden tests in `tests/` | ➡️ continue | done |
| 1.3 | Document tree: Pydantic models + `schemas/doc_tree.schema.json`, MD → JSON | Opus | FM 3-09 produces a valid tree; schema documented | 🛑 **STOP** → Sonnet | todo |
| 1.4 | Indexes from the tree: directive sentences (will/must/will not/may), deadlines/time limits, roles, cross-refs, glossary terms | Sonnet | Index outputs for FM 3-09; unit tests per extractor | 🛑 **STOP** → Opus | todo |

### Phase 2 — Plan
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 2.1 | Slide spec: Pydantic models + `schemas/slide_spec.schema.json` covering every visual pattern and the deck structure template; rule-based pattern classifier | Opus | Schema committed; rules classify pilot sections with a reviewed accuracy sample | ➡️ continue | todo |
| 2.2 | Claude API planner: choose the runtime model(s), write the prompts (pattern classification, junior-Soldier plain-language rewrite, fidelity rules), prompt caching of the regulation text, slide budget (25–40) enforcement | Opus | Runtime model choice recorded in `docs/decisions/runtime-models.md`; prompts in `src/army_trainer/plan/prompts/`; dry run on one pilot | ➡️ continue | todo |
| 2.3 | Generate and hand-review the slide spec for FM 3-09; tune prompts | Opus | Valid spec for FM 3-09 in `data/specs/`; every item cited; review notes in handover | 🛑 **STOP** → Sonnet | todo |

### Phase 3 — Render
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 3.1 | Theme + `templates/base.pptx` from the branding findings (`SETUP_NOTES.md`); `render/theme.py` | Sonnet | Template opens in PowerPoint/LibreOffice; colors/fonts match findings; contrast checked | ➡️ continue | todo |
| 3.2 | Pattern renderers (native shapes): process flow, roles, timeline, checklist, do/don't, restyled table, title, at-a-glance, what-this-means-for-you | Sonnet | One sample slide per pattern rendered from a fixture spec; thumbnails via LibreOffice | ➡️ continue | todo |
| 3.3 | Deck assembly: deck structure template, footers with citations, speaker notes with verbatim source text, overflow splitting, disclaimer slide | Sonnet | Full `.pptx` for FM 3-09 in `out/decks/` | 🛑 **STOP** → Opus | todo |

### Phase 4 — QA
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 4.1 | LLM fidelity judge: prompt + scoring rubric comparing each slide to its cited text | Opus | Judge prompt committed; run on the FM 3-09 deck; false-positive/negative notes | 🛑 **STOP** → Sonnet | todo |
| 4.2 | Rule-based checks: citation, verbatim (numbers/dates/forms), directive-word, readability (`textstat`), acronym, coverage report | Sonnet | `army-trainer qa` runs all checks; tests for each | ➡️ continue | todo |
| 4.3 | Local review report: thumbnails ↔ cited source side by side, all flags | Sonnet | Static report generated per deck | 🛑 **STOP** → Opus | todo |
| 4.4 | Pilot review: assess the FM 3-09 deck against MVP success criteria (§8 of scope); list fixes by WP; recommend on open question Q1 (per-chapter decks) | Opus | Review written to a handover; fix list assigned to models in this file | 🛑 **STOP** → user | todo |

### Phase 5 — Scale
| WP | Work | Model | Exit criteria | Stop | Status |
|---|---|---|---|---|---|
| 5.1 | Fixes from WP 4.4 (split by model as assigned there) | per 4.4 | Fix list closed | 🛑 **STOP** | todo |
| 5.2 | Remaining patterns: decision tree, comparison, term cards | Sonnet | Samples + tests | ➡️ continue | todo |
| 5.3 | Batch mode over a list of ARs; `check-updates` revision detection | Sonnet | Batch run on ≥ 5 regs; update check tested | 🛑 **STOP** → user | todo |

## Escalation (Sonnet → Opus)

A Sonnet session stops and hands over to Opus, even mid-WP, when:
- it has tried **two different approaches** to the same problem and both failed, or
- the work would require changing the **doc tree schema, slide spec schema, Claude prompts, or fidelity rules** (these are Opus-owned), or
- conversion output is wrong in a way that isn't an obvious bug (layout/structure judgment calls).

Opus may hand back to Sonnet at any point by writing a handover with a well-specified task.
