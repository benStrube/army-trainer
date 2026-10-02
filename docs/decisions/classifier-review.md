# Classifier review: rule-based pattern hints on FM 3-09 (WP 2.1)

- **Date:** 2026-10-02
- **Owner:** Opus
- **Labels:** `tests/fixtures/classifier_review.json` (65 units). A slow test (`RUN_SLOW=1`) checks that accuracy doesn't fall below this review.

## Method
1. A unit is a division, section or heading that directly holds content. FM 3-09 has 390 of them. The samples skip units under 60 words and the Preface, Glossary, References and Source Notes.
2. For each sampled unit I read the text **without seeing the classifier's output** and recorded the best pattern for a junior-Soldier slide (`gold`), plus any patterns that would also be fine (`acceptable`).
3. Three samples, drawn with different random seeds and no overlap:
   - **Development (30):** used to find failure causes and fix the rules.
   - **Held-out (20):** scored once, then used for one more round of *general* fixes (not unit-specific ones).
   - **Final blind (15):** scored once after all changes. No changes were made after seeing it.

## Results

| Sample | Top-1 exact | Top-1 acceptable | Gold in top 3 |
|---|---|---|---|
| Development (30), first rules | 50% | 67% | 67% |
| Development (30), final rules | 63% | 80% | 77% |
| Held-out (20), before general fixes | 25% | 55% | 60% |
| Held-out (20), final rules | 40% | 60% | 70% |
| **Final blind (15)** | **47%** | **67%** | **73%** |

The honest numbers are the held-out and final-blind rows: **top-1 is right about half the time, and the right pattern is in the top 3 about 70% of the time.** The development rows are optimistic because the rules were tuned on them.

## What the rules get right
- **Roles:** headings that name a role or organization ("FORWARD OBSERVER", "…FIRE SUPPORT ELEMENT").
- **Checklists:** a lead-in ending in ":" followed by a list ("Considerations include:").
- **Tables**, chapter-intro **dividers**, and **CAUTION/WARNING** blocks (→ `do_dont`).
- **Comparisons** that announce themselves ("three types of…").

## Where they fail (and why that's acceptable)
- **`key_idea` vs `checklist` vs `roles`** for prose units. The choice depends on what a junior Soldier needs, which the text doesn't signal.
- **Process vs. checklist:** order words ("then", "after") appear in descriptive prose too.
- **Do/don't** without a CAUTION block: the advice sits inside conditional prose ("If radars are sited too close…").
- **Comparisons** that don't announce themselves ("deliberate targeting … while dynamic targeting …").

## Decision
Use the hints as a **shortlist with reasons** in the planning packet (WP 2.2). The planning session (D10) reads the unit and picks the pattern. Don't spend more effort tuning rules on FM 3-09: the samples are small, and further tuning would overfit this one manual. Revisit when ARs are added, since their Responsibilities chapters and deadlines are more rule-friendly.

Fixes applied during the review (all general, not unit-specific):
- "restrictive", "deny" and "lethal and nonlethal" are FM topic words, not prohibitions or comparisons, so they no longer count.
- Order-word and conditional counts are scaled by length.
- Key terms need definition-dense text.
- Divider fires only for chapters and appendixes.
- Big numbers fire only on short units.
- Added signals: role mentions, CAUTION blocks, list lead-ins, and action-verb lists (→ process).
