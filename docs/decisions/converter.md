# Decision: PDF → Markdown converter (WP 1.1)

- **Date:** 2026-10-02
- **Status:** **Final for the pilot.** The user made FM 3-09 the pilot document (D8), so the AR re-confirmation below is no longer required. Run it when ARs are added later.
- **Owner:** Opus

## Decision

1. **Primary converter: `pymupdf4llm`** (with `header=False, footer=False`).
2. **Table cross-check/fallback: `pdfplumber`**. Use it for any table that pymupdf4llm returns malformed (see "Known gaps").
3. **Raw `PyMuPDF`** (installed with pymupdf4llm) for the signals our post-processor needs directly: PDF bookmarks (outline), span fonts/sizes, page geometry.
4. **Docling: not evaluated.** Its layout and table models download from huggingface.co, which this environment's network policy blocks. Revisit only if pymupdf4llm + pdfplumber can't meet the WP 1.2 table bar.

All WP 1.2 AR-specific cleanup (paragraph hierarchy, page-break joins, continued-table merging, glossary, Summary of Change, front matter) is built **on top of pymupdf4llm Markdown plus PyMuPDF signals**, not on a from-scratch extractor.

## Test set

| | |
|---|---|
| Document | FM 3-09 (12 Aug 2024), user-supplied; gate **passed** (Distribution A) |
| Range 1 | PDF pages 15–36: all of Chapter 1 + start of Chapter 2. 69 numbered paragraphs, 29 bookmarked headings, 5 tables (Tables 1-2, 1-3 and 1-4 continue over several pages), quote block, bullets, small-caps headings |
| Range 2 | PDF pages 35–50: Chapter 2 role descriptions. 75 paragraphs, 53 bookmarked headings (down to level 5), 1 table |
| Ground truth | Taken from the PDF itself: bookmarks (headings), body-band plain text (words, paragraph numbers), "Table N-N." captions |
| Harness | `scripts/converter_bakeoff.py` (re-runnable on any gated PDF) |

Why FM 3-09 is a fair stand-in: same Army publishing pipeline (Word → Acrobat), same `N-N.` paragraph numbering, running header/footer, multi-page "(continued)" tables, small-caps headings, bookmarks. What it **doesn't** exercise: AR-specific `a.` / `(1)` / `(a)` sub-paragraph nesting, the Summary of Change, the AR glossary layout, and AR "Responsibilities" chapter conventions.

## Results

| Metric | A: pymupdf4llm | B: pdfplumber | C: custom PyMuPDF layer |
|---|---|---|---|
| Word recall vs. body text (range 1 / range 2) | 99.8% / 100% | 100% / 100% | **73.1%** / 99.7% |
| Extra words (dupes/markup) | 6.1%¹ / 0.1% | **36.3%**² / 1.8% | 5.3% / 0.1% |
| Bookmarked headings found as headings | **29/29, 53/53** | 0/29, 0/53 | 24/29, 46/53 |
| Paragraph numbers at line start | 69/69, 75/75 | 69/69, 75/75 | 69/69, 75/75 |
| Header/footer lines leaked | **0**³ | 21 / 17 | 0 |
| Line-end hyphen breaks left | 0 | 3 / 5 | 0 |
| Seconds (22 pp / 16 pp) | 6.0 / 4.0 | 2.8 / 2.3 | 6.2 / 2.8 |

¹ Mostly `<br>` cell line breaks in tables, counted as the word "br".
² pdfplumber's page text already includes table text, so tables appear twice.
³ The harness reported 3 / 2. All of them are the real "Chapter N" / chapter-title headings, whose text matches the running header. They aren't leaks.

### What each candidate does well / badly (from reading the output)

**A: pymupdf4llm** ✅ chosen
- Headings come out at the right levels, including small-caps headings split across font sizes (`TENETS OF OPERATIONS`).
- Paragraphs are re-flowed into single lines, and line-end hyphenation is repaired.
- Keeps **italic defined terms** (`_Fire support_ is …`) and bold. This gives a free signal for the glossary and key-terms extraction.
- Header/footer suppression is built in.
- Works offline. The layout model ships in the pip wheel, so nothing is downloaded at run time.
- ❌ A paragraph that runs across a page break is split into two blocks. This is a post-processing fix in WP 1.2: join when the block ends without terminal punctuation and the next block starts in lower case.
- ❌ "(continued)" tables come out as one table per page, with the caption repeated. Post-processing merges them by caption ID.
- ❌ Some table rows split wrongly: a bullet list cell becomes its own row with an empty first cell. Post-processing merges rows with an empty first column into the row above, and checks against pdfplumber.

**B: pdfplumber**
- Best raw **table cell** fidelity: whole rows, bullets kept in the right cell, clean spacing.
- ❌ No structure at all: no headings or emphasis, header/footer left in, text duplicated with tables, hyphen breaks left. That's why it's the table cross-check, not the primary converter.

**C: thin custom layer over PyMuPDF spans**
- Fully under our control. Header/footer removal by position is trivial.
- ❌ `find_tables().extract()` drops spaces inside wide table cells ("Seeyourself seetheenemy…"). That explains the 73% recall. Fixing it means re-implementing what pymupdf4llm already does.
- ❌ The font-size heading rules missed level-4/5 headings. Many more rules would be needed to match A.
- Conclusion: use PyMuPDF for *signals*, not as the converter.

## Useful facts found along the way (for WP 1.2)

- **The PDF has a full bookmark tree (outline)** down to level 5, with page numbers. Expect ARs from armypubs to have one too. This is the best ground truth for the heading hierarchy. Use it to validate (and repair) headings rather than inferring structure from fonts alone.
- Body band on Letter pages: header text sits above y≈50 pt, footer below y≈740 pt.
- Headings are bold Times: 14 pt (section), 12 pt with 9.5 pt small caps (sub-section). Table captions are bold Arial 10 pt `Table N-N.`; continuation captions end in `(continued)`.
- Bullets come through as `•` (pymupdf4llm) or the private-use glyph `` (raw PyMuPDF).
- `pub_date` / `supersedes` parsing was already fixed against this document in WP 0.3. `title` and `proponent` are still null.

## Licensing note (action for the project owner)

`PyMuPDF` and `pymupdf4llm` are **AGPL-3.0** (or a paid Artifex commercial license). `pdfplumber` is MIT.
- Running the tool locally to make decks is fine. The decks themselves are not affected by the AGPL.
- If the tool's **code** is ever distributed to others, the AGPL requires distributing its source under the AGPL too. That matches how this repo is intended to be used (local CLI, no hosting), but it should be a conscious choice. If AGPL is ever unacceptable, the fallback is pdfplumber + pypdf (both permissive), with more custom structure code.

## Re-confirmation (optional, when ARs are added later)

When an AR PDF is available (allow `armypubs.army.mil` in the environment's network settings, or supply the PDFs):
```
uv run army-trainer fetch AR-600-20 --pdf <path>
uv run --with pymupdf --with pymupdf4llm --with pdfplumber \
  python scripts/converter_bakeoff.py data/raw/AR-600-20.pdf <first> <last> out/bakeoff
```
Pick one chapter with a table and nested `a.`/`(1)`/`(a)` sub-paragraphs. If pymupdf4llm still wins on headings and paragraph structure, mark this decision **Final**. If it doesn't, revisit. The likely alternative is Docling, which needs huggingface.co allowed.

## Outcome in WP 1.2 (full FM 3-09 conversion)

The decision held up on the whole document. WP 1.2 (`src/army_trainer/convert/`) needed these additions on top of pymupdf4llm:
- **Heading levels from PDF fonts, not pymupdf4llm.** Its `#` levels vary from page to page for the same style. `layout.py` reads the real heading styles. All bookmarked headings are found.
- **Abbreviation keys under tables** are read column by column by pymupdf4llm and come out scrambled. They're rebuilt from PyMuPDF reading-order text, but only when the abbreviations match.
- **Scrambled full-width form rows** (e.g. Table A-10) are rebuilt from PyMuPDF lines, but only when the letters match exactly, so no text is invented.
- **Table overflow:** a cell cut off at the page bottom and repeated as a paragraph is folded back into the cell.
- pdfplumber turned out not to be needed in the pipeline. It stays a dependency for manual cross-checks.
