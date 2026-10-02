# Slide spec (stage 4 output)

The slide spec says what goes on every slide of a deck and which visual pattern draws it.
- **Who writes it:** an Opus session following the planning playbook (D10, WP 2.2–2.3).
- **Who reads it:** the renderer (Phase 3) and QA (Phase 4).
- **Where it lives:** `specs/<ID>.spec.json`, committed.
- **Schema:** [`schemas/slide_spec.schema.json`](../schemas/slide_spec.schema.json), generated from `src/army_trainer/plan/spec.py`.
- **Owner:** Opus. Sonnet uses it but doesn't change it (`CLAUDE.md`).
- **Example:** [`tests/fixtures/spec_all_patterns.json`](../tests/fixtures/spec_all_patterns.json) is a 19-slide deck that uses every pattern once, with real FM 3-09 citations. Use it as the render fixture in WP 3.2.

Regenerate the schema after changing the models (a test fails if it's stale):
```
uv run python -m army_trainer.plan.schema
```

## What the spec holds, and what it doesn't
- **Holds:** slide order, pattern, title, plain-language text, and **citations** (document-tree node IDs).
- **Doesn't hold:** positions, sizes, colors or fonts (the renderer decides those from the D9 palette), or source text. The renderer pulls the verbatim text of every cited node into the speaker notes, so the spec never copies source text it could get wrong.

## Fidelity rules built into the models
| Rule | Enforced by |
|---|---|
| Every statement carries `cite` (≥ 1 node ID) | Model (`min_length=1`). `plan --check` (WP 2.2) verifies the IDs exist in the tree |
| A requirement records its exact `directive` (`will`, `must`, `will not`, `may`, `should` …) and that word appears in the slide text | Model validator. QA (WP 4.2) checks the same word is in the cited source |
| Disclaimer text and audience are fixed | `Literal` fields: `disclaimer`, `audience: "junior Soldiers"` |
| Deck starts with `title` and ends with `closing`; IDs run `s01, s02, …` | Deck validator |
| Text budgets (see the table) keep slides readable | Field limits |
| No unknown fields | `extra="forbid"` everywhere |

The 25–40 slide budget, the ≥ 60% visual-slide target and the deck template order are **checked by `plan --check`**, not by the schema. The schema only bounds a deck at 3–60 slides. See "Planning packet and check" below.

## Deck template (one deck per publication, D2)
1. `title`: renders the disclaimer
2. `at_a_glance`: purpose, who it applies to, 2–4 headline numbers
3. `takeaways`: "What this means for you" (3–5)
4. `whats_new`: from the Introduction / Summary of Change
5. Per chapter: `divider` → content slides (one or more patterns per chapter). Appendixes get no divider: their slides (`chapter` = the appendix id) sit with the chapter they support, or after the chapters
6. Optional cross-chapter slides: `timeline` (deadlines), `do_dont` (prohibitions)
7. `key_terms`, then `acronyms`
8. `closing`: "Read the full text", which repeats the disclaimer

## Patterns

Every slide has `id`, `pattern`, `title` (≤ 70 characters), optional `chapter` (division node ID) and `notes` (`talking_points[]` of cited items, and `extra_sources[]` whose text goes into the notes).

`Item` = `{text ≤ 160, cite[], directive?}`. `Stat` = `{value ≤ 12, label ≤ 60, cite[]}`. `Step` = `{label ≤ 40, detail? ≤ 140, cite[]}`.

| Pattern | Use when the source… | Fields (limits) | Draw as |
|---|---|---|---|
| `title` | always first | `subtitle?` | Black title band, gold rule, disclaimer |
| `at_a_glance` | always second | `purpose: Item`, `applies_to: Item`, `stats: Stat[0–4]` | Big-number tiles + two lines |
| `takeaways` | the most important points for a junior Soldier | `items: Item[3–5]` | Numbered cards |
| `whats_new` | lists changes from the last edition | `items: Item[2–6]` | Highlight list |
| `divider` | starts a chapter | `number?`, `blurb?: Item` | Olive-gray band, large number |
| `key_idea` | one main statement (often a definition) | `statement: Item`, `points: Item[0–3]` | Hero statement + small supports |
| `process_flow` | ordered steps or phases | `steps: Step[3–7]` | Chevrons / arrows |
| `cycle` | steps that repeat (e.g. D3A) | `steps: Step[3–6]`, `center_label?` | Ring of steps |
| `roles` | who does what | `layout: cards\|hierarchy`, `roles: Role[2–6]` (`key`, `name`, `abbreviation?`, `duties: Item[1–3]`, `parent?`) | Cards or org chart |
| `timeline` | times, deadlines, phases on a time axis | `events: {when ≤ 24, label ≤ 60, detail?, cite}[3–7]` | Horizontal timeline, gold markers |
| `checklist` | a set of requirements or considerations | `items: Item[3–7]` | Check icons |
| `do_dont` | prohibitions and their positive counterparts | `do: Item[1–4]`, `dont: Item[1–4]` | Two columns, green / red marks |
| `table` | a source table (cut down) | `source_table?`, `columns[2–4] ≤ 30`, `rows: {cells ≤ 80, cite}[1–6]` | Banded table (split rather than cram) |
| `big_numbers` | a few distances, counts or limits matter | `stats: Stat[2–4]` | Large number tiles |
| `comparison` | two or three things side by side | `columns: {heading ≤ 40, points: Item[1–4]}[2–3]` | Side-by-side columns |
| `decision_tree` | if/then conditions | `root`, `nodes: {key, kind: question\|outcome, text ≤ 90, yes?, no?, cite}[3–9]`; must form a tree | Yes/no flowchart |
| `key_terms` | definitions to learn | `terms: {term ≤ 40, definition ≤ 200, cite}[2–6]` | Definition cards |
| `acronyms` | always near the end | `entries: {abbreviation ≤ 16, meaning ≤ 80, cite}[4–24]` | Two-column list |
| `closing` | always last | `items: Item[1–4]` | Pointer to the publication + disclaimer |

`VISUAL_PATTERNS` (in `spec.py`) lists the patterns that count as "visual" for the ≥ 60% target. `checklist`, `takeaways` and `whats_new` count as lists.

## Rule-based pattern hints (`plan --hints`)
`uv run army-trainer plan <ID> --hints` writes `data/json/<ID>.hints.json`. It gives one entry per content unit (a division, section or heading that holds paragraphs): the top patterns with scores and the reasons. They are **hints for the planning session, not decisions**. On a blind-labelled review sample the best pattern was in the top 3 about 70% of the time, and top-1 was exact only about 45–60% of the time (see `docs/decisions/classifier-review.md`).

## Planning packet and check (WP 2.2, D10/D11)
The playbook the planning session follows is [`src/army_trainer/plan/prompts/planner.md`](../src/army_trainer/plan/prompts/planner.md).

`uv run army-trainer plan <ID> --packet [--target 34]` runs the Distribution A gate, then writes `data/packets/<ID>/`:
- `README.md`: publication, SHA-256 for the spec, suggested budget per chapter/appendix, deck template, file list.
- `<division-id>.md` for every division: outline with pattern hints, requirement and prohibition rows (`mandatory`/`prohibitive`, not historical), deadlines, roles with duties, terms defined there, acronyms used there, then the **full text with node ids** (`` `[para-2-19]` ``) to cite.
- `packet.json`: budget and per-division counts as data.

The budget is by length only: every chapter gets a divider and one content slide, then the rest goes by D'Hondt on sqrt(words). The session moves slides toward what junior Soldiers need.

`uv run army-trainer plan <ID> --check [--spec PATH] [--partial]` validates `specs/<ID>.spec.json` (exit 1 on any error). `--partial` skips the whole-deck checks for a chapter dry run.

| Errors | Warnings |
|---|---|
| Schema / model validation | `may` / `should` in slide text but not in the cited text |
| `pub_id` or `source_sha256` doesn't match the tree | A number in slide text that isn't in the cited text (digits or one…twelve; "chapter 2"-style references ignored) |
| A cite, `chapter`, `source_table` or `extra_sources` id not in the tree | A cite of a whole heading/section/division (except divider blurbs) |
| An item's `directive` isn't in its cited text | An acronym's meaning differs from the glossary; a key term found nowhere |
| Slide text says will / must / shall / will not / must not / may not / should not and the cited text doesn't | An acronym used on a slide but missing from the `acronyms` slide (publication designators like "FM 3-09" don't count) |
| A slide title contains one of those words (titles aren't cited) | A chapter with no divider |
| An acronym entry not in the glossary | |
| Whole deck: 25–40 slides; ≥ 60% of non-structural slides visual; `title`, `at_a_glance`, `takeaways` (slide 3 or 4), …, `key_terms`, `acronyms`, `closing` order; dividers in document order; a chapter's slides under its own divider | |

`uv run army-trainer plan <ID> --review [--slides s05,s06]` prints every cited statement next to the text of the nodes it cites, for the self-review.

What the check can't see: a reworded requirement with **no** directive word ("Never look at the sun" for "must never be viewed"), meaning changes, and outside knowledge. The session's self-review and the fidelity review (WP 4.1) cover those.
