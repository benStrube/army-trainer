# Army Trainer — Project Scope

**Goal:** Turn publicly released Army regulations (PDF) into clean Markdown, then into colorful, diagram-heavy PowerPoint decks that make dense regulatory text easier to absorb — without changing what the regulation actually says.

---

## 0. Decisions Log

| # | Decision | Date |
|---|---|---|
| D1 | **Audience:** general Army, with a focus on **junior Soldiers** (E-1 to E-4). Plain language, Soldier-centric framing. | 2026-10-02 |
| D2 | **Deck size:** **one deck per regulation** for now. Per-chapter decks remain an open question (§9). | 2026-10-02 |
| D3 | **LLM use:** Distribution A regulation text **may be sent to the Claude API**. The distribution gate (Stage 1) must pass before any API call. | 2026-10-02 |
| D4 | **Hosting / delivery:** **no hosting.** The tool runs locally as a CLI and produces `.pptx` files for **manual distribution**. | 2026-10-02 |

## 1. Problem & Outcome

Army Regulations (ARs) are long (often 100+ pages), text-dense, and built from nested paragraph numbering (`3–4a(2)(b)`), large tables, and cross-references. Junior Soldiers rarely read a regulation cover to cover, but they are expected to follow it. They need the *shape* of a regulation — what applies to me, what I must and must not do, which steps happen in what order, what the deadlines are, and who I go to for help — in plain language, before (and as a guide into) the full text.

**Outcome:** a pipeline where you drop in a regulation number (e.g. `AR 600-20`) and get:

1. `ar-600-20.md` — faithful, structured Markdown of the full regulation
2. `ar-600-20.json` — a document tree (chapters → paragraphs → subparagraphs, tables, figures) used by later stages
3. `ar-600-20.pptx` — a visual deck: flowcharts, timelines, responsibility charts, checklists, callouts — every slide cited back to its paragraph number, with source text in the speaker notes

## 2. Scope

### In scope
- Public regulations only: documents on [armypubs.army.mil](https://armypubs.army.mil) marked **Distribution Statement A — approved for public release; distribution is unlimited**. Start with ARs; DA Pams are a natural follow-on (same format).
- Text-based PDFs (all modern ARs are born-digital; no OCR needed for MVP).
- PDF → Markdown + JSON document tree.
- Automated "visual pattern" detection and slide generation.
- `.pptx` output that is editable in PowerPoint / Google Slides / Keynote, produced locally for manual distribution (email, shared drive, unit training).
- Re-running when a regulation is revised (Summary of Change awareness).

### Out of scope (for now)
- Anything CAC-restricted, CUI, FOUO, or marked with a Distribution Statement other than A. The pipeline should **refuse** these, not just skip them (see §7).
- Scanned/legacy PDFs requiring OCR.
- Field Manuals / ATPs (different structure — later phase).
- Interactive e-learning, quizzes, LMS integration (possible Phase 6).
- Hosting of any kind — no web app, server, or online viewer (D4).
- Official endorsement or Army branding (see §7 — decks are labeled unofficial training aids).

### Audience & writing style (D1)
Decks target **general Army, focused on junior Soldiers**. This drives the planning and rendering stages:
- **Plain language:** target roughly an 8th-grade reading level on slides (measured, see §3 Stage 6). Short sentences, active voice.
- **Soldier-centric framing:** lead with "What this means for you", "What you must do", "What you must not do", "Who to go to". Turn "Commanders will ensure Soldiers…" into what the Soldier experiences, while keeping the citation.
- **Acronyms:** spell out on first use in every deck; an acronym slide at the end. Never assume staff knowledge (e.g. "DCS, G–1" becomes "Army personnel staff (DCS, G-1)" or is omitted if irrelevant to a junior Soldier).
- **Prioritization:** content that applies to the individual Soldier is always included. Staff/HQ-level responsibilities (e.g. Army Staff, ACOM duties) are summarized on a single "Who's responsible" overview slide rather than detailed.
- **Directive words kept exact:** `will`/`must`/`will not`/`may` are never softened, even when simplifying.

## 3. Architecture

```
 ┌───────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────┐   ┌────────┐
 │ 1. Fetch  │──▶│ 2. Convert │──▶│ 3. Structure│──▶│ 4. Plan      │──▶│ 5. Render │──▶│ 6. QA  │
 │  PDF +    │   │ PDF → MD   │   │ MD → JSON   │   │ slide spec   │   │ spec →    │   │fidelity│
 │  metadata │   │ (clean)    │   │ doc tree    │   │ (LLM-assist) │   │ .pptx     │   │+ review│
 └───────────┘   └────────────┘   └─────────────┘   └──────────────┘   └───────────┘   └────────┘
   data/raw/       data/md/         data/json/        data/specs/        out/decks/
```

Every stage writes an artifact to disk, so any stage can be re-run, diffed, and hand-edited independently. The whole pipeline runs locally from a CLI; the only external call is the Claude API (Stages 4 and 6). The **slide spec** (stage 4) is the key seam: it's a human-readable JSON/YAML file that says "slide 7 is a 5-step flowchart built from para 4–3a–e". You can edit it by hand before rendering.

### Stage 1 — Fetch
- Input: publication number (`AR 670-1`) or a local PDF path.
- Download the PDF from armypubs, capture metadata: title, pub date, proponent, distribution statement, supersedes, page count, SHA-256.
- Respectful scraping: rate limit, cache, User-Agent identifying the tool. Prefer manual download for MVP; automate later.
- **Gate:** parse the first pages for the distribution statement; reject unless it's Distribution A. The gate result is recorded in the metadata, and the Claude API client refuses to send any document without a passing gate record (D3).

### Stage 2 — PDF → Markdown
Army regs have a very consistent layout, which makes this tractable.

| Tool | Strength | Weakness | Role |
|---|---|---|---|
| **Docling** (IBM) | Best table structure recovery, layout model, reading order | Heavier install, slower | **Primary converter** |
| **PyMuPDF / pymupdf4llm** | Fast, exact text + font info (bold, size) | Tables weaker | Font/heading signals, fallback |
| pdfplumber | Fine-grained table cells | Manual tuning | Fallback for tricky tables |
| Marker | Good general MD output | Less control | Benchmark only |

**AR-specific post-processing (custom code — this is where the real work is):**
- Strip running headers/footers (`AR 600–20 • 24 July 2020`, page numbers).
- Normalize en-dashes in paragraph numbers (`1–1` → `1-1`) while preserving the original for citation.
- Rebuild paragraph hierarchy: `Chapter 3` → `3–4. Title` → `a.` → `(1)` → `(a)`, mapped to Markdown headings / nested lists.
- Re-join words hyphenated across lines and paragraphs split across pages.
- Tables → GitHub-flavored Markdown tables (fall back to HTML for merged cells).
- Figures → extract image + caption; keep reference.
- Recognize standard sections: Summary of Change, Contents, Chapters, Appendixes (A = References), Glossary (abbreviations + terms).
- YAML front matter with the stage-1 metadata.

### Stage 3 — Document tree (JSON)
A typed tree the planner can reason over:
```json
{ "id": "3-4.a.(2)", "type": "subparagraph", "title": null,
  "text": "...", "page": 21, "refs": ["AR 27-10", "para 2-1"],
  "children": [...] }
```
Plus extracted indexes: glossary terms, cross-references, tables, every "must / will / may not" sentence (directive language), dates/time limits ("within 30 days"), and role names ("commanders", "the DCS, G–1").

### Stage 4 — Slide planning (the "make it visual" brain)
Each section is classified into a **visual pattern**. Rules first (cheap, deterministic), LLM (Claude) where the rules can't decide.

| Content signal in the text | Visual pattern | Rendered as |
|---|---|---|
| Ordered steps, "will then", "upon completion" | **Process flow** | Chevron/arrow flowchart |
| "The Commander will… The S1 will…" (Responsibilities chapter) | **Roles & responsibilities** | Org-chart cards or RACI matrix |
| Conditions / eligibility / "if… then… unless" | **Decision tree** | Yes/No flowchart |
| Deadlines, "within N days", effective dates | **Timeline** | Horizontal timeline with markers |
| Lists of requirements | **Checklist** | Icon checklist / cards |
| Prohibitions ("will not", "prohibited") | **Do / Don't** | Two-column green/red |
| Numeric thresholds, limits, ratios | **Big-number callout** | Large stat tiles |
| Category comparisons (e.g. by rank, component) | **Comparison** | Side-by-side columns / styled table |
| Existing tables | **Restyled table** | Banded, color-coded, split if > ~8 rows |
| Glossary / key terms | **Term cards** | Definition cards |
| Summary of Change | **"What's new"** | Highlight slide at the front |

Output: a **slide spec** per deck, validated against a JSON Schema:
```yaml
- slide: 7
  pattern: process_flow
  title: "Filing an Equal Opportunity Complaint"
  steps:
    - { label: "Soldier files DA Form 7279", cite: "6-3a" }
    - { label: "Commander notified within 3 days", cite: "6-3b" }
  notes_source: ["6-3a", "6-3b", "6-3c"]
```

**Deck structure template** (one deck per regulation, D2):
1. Title + "unofficial training aid" disclaimer
2. Regulation at a glance (purpose, who it applies to, date — big-number tiles)
3. **What this means for you** — the 3–5 most important takeaways for a junior Soldier
4. What's new (Summary of Change)
5. Who's responsible / who to go to (one overview slide)
6. One section per chapter: divider slide → visual slides (chapters with little Soldier-level content get a single summary slide)
7. Key deadlines timeline (aggregated across the whole reg)
8. Do / Don't summary (aggregated prohibitions)
9. Key terms & acronyms
10. References & "read the full text" pointer

**Slide budget:** because it's one deck per regulation, the planner enforces a target of **~25–40 slides** regardless of regulation length. It prioritizes Soldier-applicable content and pushes detail into speaker notes rather than adding slides. Whether long regulations (e.g. AR 350-1) should instead get per-chapter decks is an open question (§9).

**Fidelity rules for the LLM step (non-negotiable):**
- It may only **summarize, restructure, and shorten** — never add requirements.
- Every bullet/step/node carries a `cite` paragraph ID that must exist in the tree.
- Directive verbs are preserved (`will` ≠ `should` ≠ `may`).
- Numbers, dates, form numbers, and role names are copied verbatim (checked in stage 6).

### Stage 5 — Rendering
- **python-pptx** with a custom master template (`templates/base.pptx`).
- Diagrams drawn as **native PowerPoint shapes** (chevrons, rounded rectangles, connectors) where possible — they stay editable and recolorable. A small layout library per pattern: `process_flow.py`, `timeline.py`, `org_chart.py`, `decision_tree.py`, etc.
- Complex graphs (big decision trees, cross-reference maps) via **Graphviz/Mermaid → SVG/PNG** inserted as images (not editable, but auto-laid-out).
- Icons from an open-licensed set (e.g. Lucide / Material Symbols) rendered to PNG/SVG.
- Speaker notes: full verbatim source text of the cited paragraphs + citation, so a briefer always has the authoritative wording.
- Footer on every slide: `AR 600-20 (24 Jul 2020) · para 6-3` .
- Overflow handling: auto-split slides that exceed text/node budgets (e.g. ≤ 6 bullets, ≤ 7 flow steps, ≤ 40 words per box).

**Design system**
- Palette: high-contrast, colorblind-safe categorical palette (6–8 colors) with semantic colors fixed across all decks — e.g. responsibilities = blue, deadlines = amber, prohibitions = red, requirements = green, definitions = purple.
- Neutral/"tactical" base (charcoal, sand, olive) so it feels on-theme without copying official Army branding.
- 16:9, one big idea per slide, ≥ 18 pt body text.

### Stage 6 — QA & review
Automated:
- **Citation check:** every cited paragraph exists.
- **Verbatim check:** every number, date, form number (`DA Form 4856`), and pub reference on a slide appears in the cited source text.
- **Directive check:** "will/must/will not" in source isn't softened on the slide.
- **Coverage report:** % of paragraphs represented somewhere, and 100% of directive sentences that apply to individual Soldiers.
- **Readability check:** reading-grade score per slide (e.g. Flesch-Kincaid via `textstat`); flag slides above ~grade 9 and undefined acronyms.
- **LLM-as-judge pass:** second model call compares each slide to its cited text and flags distortions.
- Render thumbnails (LibreOffice headless → PNG) to catch overflow/overlap.

Human:
- Review the spec + thumbnails before distribution. The `qa` command writes a local review report (slide thumbnail ↔ cited source text side by side, plus all flags) as a static HTML/PDF file opened on your own machine — nothing hosted (D4).
- Final output is the reviewed `.pptx` (optionally also a PDF export via LibreOffice for people without PowerPoint), ready to hand out manually.

## 4. Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12, `uv` for env/deps |
| PDF | Docling, PyMuPDF, pdfplumber |
| Data models | Pydantic (tree + slide spec schemas) |
| LLM | Claude API (classification, summarization, judging); prompt caching on the regulation text |
| Slides | python-pptx; Graphviz / Mermaid CLI for complex diagrams |
| Preview | LibreOffice headless → PDF/PNG |
| CLI | Typer, run locally: `army-trainer fetch|convert|plan|render|qa|build AR-600-20` |
| Readability | `textstat` |
| Delivery | Local files in `out/decks/` for manual distribution; no hosting |
| Tests | pytest; golden-file tests on 3 reference regs |
| CI | GitHub Actions (lint, tests, build a sample deck as an artifact) |

## 5. Proposed Repo Layout

```
army-trainer/
├── src/army_trainer/
│   ├── fetch/          # armypubs download + metadata + distribution gate
│   ├── convert/        # PDF → MD (docling wrapper + AR post-processors)
│   ├── structure/      # MD → JSON tree, indexes (glossary, deadlines, roles)
│   ├── plan/           # rules + LLM classifier → slide spec
│   ├── render/
│   │   ├── patterns/   # process_flow.py, timeline.py, org_chart.py, ...
│   │   └── theme.py    # palette, fonts, sizes
│   ├── qa/             # citation/verbatim/coverage checks, LLM judge
│   └── cli.py
├── templates/base.pptx
├── schemas/            # slide_spec.schema.json, doc_tree.schema.json
├── data/{raw,md,json,specs}/   # gitignored except fixtures
├── out/decks/
├── tests/fixtures/     # small excerpts of public ARs
└── docs/
```

## 6. Phased Plan

| Phase | Deliverable | Est. effort* |
|---|---|---|
| **0. Setup** | Repo, tooling, CI, pick 3 pilot regs, download PDFs | 2–3 days |
| **1. Convert** | High-quality MD + JSON tree for the 3 pilots; golden tests | 1.5–2 weeks |
| **2. Plan** | Rule-based + LLM pattern classifier; slide spec schema; specs for pilots | 1.5–2 weeks |
| **3. Render** | Theme + 6 core patterns (process, roles, timeline, checklist, do/don't, table) + title/at-a-glance; first full decks | 2 weeks |
| **4. QA** | Automated fidelity + readability checks, coverage report, thumbnails, local review report | 1–1.5 weeks |
| **5. Scale** | Remaining patterns (decision tree, comparison, term cards), batch mode over a list of ARs, revision diffing | 2 weeks |
| **6. Stretch** | DA Pams/FMs, quiz/flashcard generation from the same tree, per-chapter decks (if §9 Q1 says yes), Google Slides export | open |

\*Single developer with AI assistance; **MVP = Phases 0–3 ≈ 5–7 weeks**.

**Suggested pilot regulations** (all public, varied structure):
- **AR 600-20** *Army Command Policy* — responsibilities, EO/SHARP complaint processes (great for flowcharts)
- **AR 670-1** *Wear and Appearance of Army Uniforms and Insignia* — rules, do/don't, tables
- **AR 623-3** *Evaluation Reporting System* — timelines, rater chains, deadlines
- *(alt)* **AR 350-1** *Army Training and Leader Development* — very long; stress test

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Misrepresenting the regulation** (oversimplification, hallucination) | Citations on everything, verbatim checks, LLM judge, human approval, verbatim text in notes, disclaimer slide: *"Unofficial training aid. The regulation is the authoritative source."* |
| **Restricted material slipping in** | Distribution-statement gate; reject on CUI/FOUO/"Distribution B–F" markings; never fetch behind CAC login; log provenance (URL, hash, date) |
| **Stale content** (regs revised, rapid action revisions) | Store pub date + hash; `check-updates` command compares against armypubs; deck footer shows reg date |
| **Branding / endorsement concerns** | No Army star logo, seals, or "official" styling; Army trademarks require licensing for some uses — keep a neutral theme |
| **Table/layout extraction errors** | Docling + pdfplumber fallback; golden tests; flag low-confidence tables for manual review |
| **Visual clutter / bad auto-layout** | Hard budgets per pattern, auto-splitting, thumbnail review |
| **LLM cost** | Rules first; prompt caching of the full reg text; batch API for large runs. Rough order: low single-digit dollars per regulation |

## 8. Success Criteria (MVP)
- 3 pilot regs converted with ≥ 98% paragraph-structure accuracy (spot-checked) and all tables intact.
- Each pilot deck: ≥ 60% of content slides are diagrams/visuals (not bullet lists).
- 100% of slide claims carry a valid citation; 0 verbatim-check failures on numbers/dates/forms.
- Each pilot deck is 25–40 slides, with ≥ 90% of slides at or below ~grade 9 reading level and no undefined acronyms.
- A junior Soldier unfamiliar with the reg can answer 8/10 basic "what do I have to do" questions about it after a 15-minute deck walkthrough (simple usability test).

## 9. Open Questions
Resolved questions are recorded in §0 (D1–D4).

1. **Per-chapter decks** — keep one deck per regulation (D2), or also produce per-chapter decks for long regulations (e.g. AR 350-1)? Revisit after the pilots show whether the 25–40 slide budget loses too much.
2. **Branding** — neutral theme, or a unit-specific template you're allowed to use?
3. **PDF copies** — should every run also export a PDF of the deck for people without PowerPoint, or `.pptx` only?

## 10. Immediate Next Steps
1. Settle the branding question (§9 Q2) before Phase 3; Q1 and Q3 can wait until the pilots are done.
2. Phase 0: scaffold the Python package, CLI skeleton, CI.
3. Download the 3 pilot PDFs and run Docling vs. pymupdf4llm side by side on one chapter to lock in the converter.
