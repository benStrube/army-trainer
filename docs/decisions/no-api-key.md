# Decision: building without a Claude API key (D10) and the Army-style palette (D9)

- **Date:** 2026-10-02
- **Status:** Accepted
- **Owner:** Opus

## Context
The plan had the CLI call the Claude API at two points:
- Stage 4: classify sections, rewrite them in plain language, and write the slide spec.
- Stage 6: an LLM judge checks each slide against its source.

There is no API key, and the user asked whether Claude's design tools ("Claude Design", meaning the Slides and Design artifact types on claude.ai) could stand in.

## What actually needs an LLM
Only two steps need judgment:
- **Planning:** deciding what goes on each slide and writing it in plain language.
- **Fidelity review:** checking that a slide doesn't change the meaning of its source.

Everything else is deterministic code and runs without any model: fetch, gate, convert, tree, indexes, rule-based pattern hints, rendering, and rule-based QA.

## Options considered

| Option | What it is | Verdict |
|---|---|---|
| **A. A Claude Code session is the LLM** | An Opus session runs `army-trainer plan <ID> --packet`, follows a written playbook, writes the slide spec JSON, and validates it with `army-trainer plan <ID> --check`. The same applies to fidelity review. | ✅ **Chosen.** No key needed. Same model quality, and the playbook text is reused as the API prompt if a key is added later. |
| **B. Claude Slides artifact as the renderer** | A session fills a "Slides" artifact on claude.ai from the spec. The user downloads it as `.pptx`. | ➕ **Optional preview only (WP 2.4).** Fast, polished, and gives early feedback on content and look. It doesn't replace the python-pptx renderer: the export can't be repeated from the CLI, every deck needs a session, diagrams aren't guaranteed to stay editable shapes, and the deck lives on claude.ai rather than only on disk (D4). |
| **C. Claude Design System artifact** | A reusable design system on claude.ai. | Not needed. The palette lives in `render/theme.py` and the PowerPoint template. Can revisit if the user wants decks made in Claude Slides by hand. |
| **D. Wait for a key** | Pause Phase 2. | ❌ Blocks the project for no gain. |

## Decision (D10)
- **No runtime API calls for now.** The `plan` and `qa` commands prepare inputs and validate outputs. The judgment step is done by an Opus Claude Code session following a committed playbook:
  - `src/army_trainer/plan/prompts/planner.md`
  - `src/army_trainer/qa/prompts/fidelity_review.md`
- **Specs are committed:** `specs/<ID>.spec.json`, plus the fidelity review output. They're written by a session and can't be regenerated, so they must not live in gitignored `data/`.
- **The Distribution A gate still applies:** `plan --packet` uses `load_gated_metadata`, so a session never sees ungated text. D3 (sending Dist A text to the Claude API) stays valid for later.
- **Later (optional):** if a key is added, a thin API backend sends the same playbook as the prompt (new WP 6.1). Nothing else changes.
- **Batch mode** (WP 5.3) automates every deterministic stage. Planning each new publication still needs one Opus session until a key exists.

## Decision (D9): best-guess Army-style palette
The user overrode the "never guessed" branding rule: use a best guess of the Army look, lots of white, gray, black and yellow. The values come from the colors sampled from the user's army.mil screenshots (`docs/SETUP_NOTES.md`). WP 0.3 is closed as superseded. Official values replace these if the brand guide is ever obtained.

| Token | Hex | Use | Contrast |
|---|---|---|---|
| `army_black` | `#222021` | Title bars, body text, outlines | 16.2:1 on white |
| `army_gold` | `#FFCD01` | Accent rule, highlight fills, deadline markers; black text on gold | 10.8:1 with black. **Never gold text on white (1.5:1)** |
| `gold_dark` | `#8A6D00` | Gold-family text on white when needed | 4.9:1 on white |
| `olive_gray` | `#58574E` | Secondary bars, section dividers (white text) | 7.3:1 with white |
| `mid_gray` | `#6B6B6B` | Secondary text, footers, citations | 5.3:1 on white |
| `light_gray` | `#E6E6E6` | Panels, cards, table header row | black text 13.0:1 |
| `pale_gray` | `#F2F2F2` | Alternating table rows, background panels | black text 14.5:1 |
| `white` | `#FFFFFF` | Slide background (mostly white) | — |
| `do_green` | `#2E6B30` | Do / requirement marks only | 6.4:1 with white |
| `dont_red` | `#B3261E` | Don't / prohibition marks only | 6.5:1 with white |

- **Font:** Arial, which ships with Office. Headings are bold and all caps with slight letter spacing; body is regular, at least 18 pt.
- **Style:** flat rectangular shapes, no rounded corners, a black title bar with a thin gold rule underneath, mostly white slide bodies, thin outline icons.
- **No Army star, seal or wordmark** (trademark question unresolved). Every deck keeps the "Unofficial training aid — the publication is the authoritative source" disclaimer.
