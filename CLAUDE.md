# CLAUDE.md

Guidance for Claude sessions working in this repo. Read this first, every session.

## What this project is
A local CLI that turns **public (Distribution A) Army publications** (regulations and field manuals; the current pilot is FM 3-09, see D8) in PDF form into structured Markdown/JSON and then into **visual, diagram-heavy PowerPoint decks for junior Soldiers**. Decks are made locally and distributed by hand.

Key docs:
- `docs/PROJECT_SCOPE.md`: architecture, decisions log (§0, D1–D6), risks, open questions
- `docs/ACTION_PLAN.md`: work packages, **model assignments**, stop points, **current status**
- `docs/SETUP_NOTES.md`: branding research (feeds the slide template)
- `docs/handovers/`: handover notes between sessions (newest file = where to resume)

## Start-of-session procedure
1. Read `docs/ACTION_PLAN.md` and find the first WP that is not `done`.
2. Read the newest handover note in `docs/handovers/` (by filename date).
3. **Check the model assignment.** Work out which model tier you are (Opus or Sonnet) from your environment/system information; if you can't tell, ask the user.
   - If the WP is assigned to your tier: mark it `in progress` and start.
   - If it is assigned to the other tier: **don't start it.** Tell the user which model the WP needs and give them the kickoff prompt from the latest handover. Exception: the user explicitly tells you to proceed anyway. Then note that in the handover.
4. Confirm the WP's exit criteria before writing code.

## Model assignments (summary; the full table is in `docs/ACTION_PLAN.md`)
| Model | Owns |
|---|---|
| **Opus** | Converter choice + AR PDF cleanup rules (1.1–1.2), doc tree schema (1.3), slide spec schema + classifier (2.1), Claude API prompts and runtime model choice (2.2), pilot spec review (2.3), LLM fidelity judge (4.1), pilot deck review (4.4) |
| **Sonnet** | Scaffold/CLI/CI (0.1), fetch + Distribution A gate (0.2), branding research (0.3), index extractors (1.4), theme/template/renderers/deck assembly (3.1–3.3), rule-based QA + review report (4.2–4.3), extra patterns + batch mode (5.2–5.3) |

Opus-owned artifacts: `schemas/*.json`, `src/army_trainer/plan/prompts/`, fidelity rules, the QA judge prompt. Sonnet may *use* them but must hand over to Opus rather than change them.

## Stop and handover procedure
**When to stop:**
- At the end of any WP marked 🛑 **STOP** in `docs/ACTION_PLAN.md` (model switches and phase ends). This is a hard stop. Don't start the next WP.
- At the end of a WP marked ➡️ **continue**: write the handover, then you may continue to the next WP **only if it's assigned to your tier**.
- **Escalation (Sonnet):** two failed approaches to the same problem, or the work needs a change to an Opus-owned artifact. Stop mid-WP and hand over to Opus.
- The context is getting long enough that quality could slip. Hand over at a clean point rather than pushing on.
- The user says stop.

**How to hand over (all steps, in order):**
1. Get the code to a clean state: tests and lint pass, or failures are written up in the handover.
2. Copy `docs/handovers/TEMPLATE.md` to `docs/handovers/YYYY-MM-DD-WP<x.y>-<slug>.md` and fill in every section. Be honest about what's not done.
3. Update the Status column in `docs/ACTION_PLAN.md` (`done`, `in progress`, or `blocked`).
4. Record any new decisions in `docs/PROJECT_SCOPE.md` §0 (or `docs/decisions/`).
5. Commit and push to the working branch.
6. Tell the user, briefly: what finished, what's next, **which model the next WP needs**, and the kickoff prompt from the handover.
7. **Stop.** Don't start the next WP after a 🛑 STOP.

## Non-negotiable rules
- **Distribution A only.** Never fetch, process, or send to the Claude API any document that hasn't passed the Distribution A gate. Never handle CUI/FOUO/CAC-restricted material.
- **Fidelity over polish.** Slides may summarize, restructure, and simplify. They may never add requirements or change meaning. Every slide item carries a paragraph citation that exists in the doc tree.
- **Never soften directive words:** `will` / `must` / `will not` / `may` stay as written. Numbers, dates, form numbers, and role names are copied exactly.
- **Audience is junior Soldiers:** plain language (~8th-grade), acronyms spelled out on first use, "what this means for you" framing.
- **One deck per regulation, ~25–40 slides, `.pptx` only.** Standard Army branding from `docs/SETUP_NOTES.md` findings, never guessed. Every deck keeps the "unofficial training aid" disclaimer.
- No hosting. Everything runs locally.

## Conventions
- Python 3.12, `uv`, Typer CLI, Pydantic, pytest, ruff.
- Pipeline stages write to `data/{raw,md,json,specs}/` and `out/decks/` (gitignored except test fixtures).
- Don't put model version identifiers in code, commits, or docs. Refer to model tiers ("Opus", "Sonnet") only.
