# Decision D15: how the deck's reading level is measured (WP 5.1b)

- **Date:** 2026-10-02
- **Status:** Accepted
- **Owner:** Opus. Sonnet implements it in WP 5.1e.

## Context
MVP criterion §8.4 says "≥ 90% of slides at or below ~grade 9 reading level", but the method was never defined. WP 4.2 measured each claim's fields joined together with raw Flesch-Kincaid (FK) and reported a deck mean of 10.8. WP 4.4 found two problems with that:
- FK counts syllables, so the doctrinal terms a Soldier must learn push the grade up. "Fire support coordination measure" is 11 syllables. With those terms counted as one word, the share of statements at grade 9 or below roughly doubles (30% → 57%).
- §8 is stated **per slide**, but the check reported per statement and as a deck mean.

## Decision
Reading level is measured **per slide** with FK grade (`textstat.flesch_kincaid_grade`), on **neutralized** text:

1. **Statements:** every text field drawn on a slide, measured separately as the renderer draws it. Each text field (`Item.text`, a `Step`'s `label` and `detail`, a table cell …) is one statement.
   - **Excluded:** speaker notes, and the `title`, `acronyms` and `closing` slides. Their text is fixed (disclaimer), a list of expansions, or pointers to other publications.
   - **Short text:** a statement with fewer than **8 words** (`[A-Za-z']+`) has no stable grade and is skipped.
2. **Neutralizing:** before scoring, replace with the single word `term`, case-insensitive and longest first, and only as whole words:
   - every **glossary term** (`term` nodes in the publication's tree)
   - every **acronym meaning** (`acronym.meaning`)
   - every **acronym abbreviation** (case-sensitive)

   Nothing else is neutralized: no hand-made word lists. Sentence length is untouched, because a term still counts as one word.
3. **Slide grade:** the mean of its statements' grades. A slide with no scored statement is not scored.
4. **Deck result (the §8 number):** the share of scored slides whose grade is **≤ 9.0**. **Pass at ≥ 90%.**
5. **Reported alongside, not graded:**
   - the raw (un-neutralized) slide grades
   - the deck mean of neutralized statement grades
   - every statement above grade **12** (a warning, as now)
   - every slide above **9.0** (a warning)

### Why this is fair, not lenient
- Only terms the publication itself defines are neutralized, and the deck has to teach them anyway: on the key terms slide, by spelling out acronyms, and through the playbook's §4 plain-language rules.
- Long sentences and long ordinary words still count fully.
- On today's deck the measure gives **53%** of slides at grade 9 or below, not 90%, so the criterion still drives the WP 5.1c rewrite.

## Reference values (for the WP 5.1e tests)
Computed on `specs/FM-3-09.spec.json` at commit `748ea0b` (WP 5.1a tree), using the `textstat` version locked in `uv.lock`. The tolerance for per-slide grades is ±0.1.

| Measure | Value |
|---|---|
| Glossary terms + acronym meanings (neutralized phrases) | 341 phrases, 146 abbreviations |
| Scored slides | 34 |
| Slides ≤ 9.0 | **18 (53%)** — §8 target ≥ 90% |
| Deck mean (neutralized statements) | 9.01 |
| Raw FK slides ≤ 9.0 (for contrast) | 3 of 34 |

Per-slide neutralized grades:

| s02 8.7 | s03 8.6 | s04 8.2 | s05 6.7 | s06 9.7 | s07 10.0 | s08 5.0 | s09 8.2 | s10 7.2 |
|---|---|---|---|---|---|---|---|---|
| **s11 12.0** | s12 9.4 | s13 6.4 | s14 4.7 | s15 10.6 | s16 8.7 | **s17 12.0** | s18 9.1 | s19 9.3 |
| s20 6.9 | s21 8.6 | **s22 12.3** | s23 9.3 | s24 6.5 | s25 11.2 | s26 5.1 | s27 6.5 | s28 7.8 |
| **s29 15.0** | **s30 14.6** | s31 10.1 | s32 9.0 | s33 8.9 | s34 9.1 | s35 10.0 | | |

These values go stale as soon as WP 5.1c edits the spec. A copy of today's spec is saved as `tests/fixtures/spec_fm309_d15.json`; pin the test to it, not to the live spec. The test needs the FM 3-09 tree (skip when `data/` is absent).

## Consequences
- **WP 5.1e (Sonnet)** implements this in `qa/rules.py`:
  - per-slide grading
  - neutralizing from the tree
  - the §8 percentage and pass/fail in `qa` output and `qa.json`
  - the raw grades alongside
  - a test pinned to the reference values above, using a fixture copy of the spec
- **WP 5.1c (Opus)** rewrites the spec until ≥ 90% of slides pass. The worst slides now are s29, s30, s22, s11, s17 and s25. Dividers count: s22 and s30 are divider blurbs.
- The planner playbook (§4) names this measure as the target.
