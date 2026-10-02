# Project Setup Notes

Working notes for Phase 0 (see [PROJECT_SCOPE.md](PROJECT_SCOPE.md) §6).

> **Update (2026-10-02, D9):** the user chose a **best-guess Army-style palette** instead of waiting for official sources. The palette in use, with contrast ratios, is in [`decisions/no-api-key.md`](decisions/no-api-key.md). It's built from the screenshot-sampled colors below. WP 0.3 is closed as superseded. The research notes are kept for reference; if the brand guide is ever obtained, update D9 with official values.

## Subtask: Army branding research (D5)

**Goal:** collect the standard Army branding rules and real-world examples so the deck template (`templates/base.pptx`) and `render/theme.py` are built from official sources, not guesses. Must be finished before Phase 3 (rendering).

**Sources:** pull from several official army.mil websites, for example:
- the Army's brand / visual identity guidance pages (brand guide, logo usage, color and font specs)
- the Army trademark licensing pages (rules on using the Army star logo and other marks)
- army.mil news and command pages, plus Army school / Center of Excellence sites, for examples of how the branding is applied in practice (slides, graphics, infographics)

Record the exact URL and date accessed for everything below.

### Checklist
- [ ] **Colors:** official brand palette with exact hex/RGB values (primary and accent); any rules on which colors go together
- [ ] **Typography:** brand fonts, whether they're freely available, and approved substitutes for PowerPoint (fonts that ship with Office)
- [ ] **Logo:** official logo files, clear-space and minimum-size rules, approved color versions, and whether unit/individual training products may use it
- [ ] **Trademark/usage limits:** what needs approval, what's prohibited, required disclaimers
- [ ] **Slide/graphic examples:** 5–10 examples of Army-produced briefings, infographics, or graphics from army.mil sites (link + notes on layout, color use, iconography)
- [ ] **Accessibility:** contrast-check the palette for text on backgrounds; pick a colorblind-safe set of semantic colors (responsibilities, deadlines, prohibitions, requirements, definitions) that fits the brand
- [ ] **Decision summary:** final palette, fonts, logo rule, and title/footer layout to implement in `render/theme.py` and `templates/base.pptx`

### Findings

**Status (2026-10-02, WP 0.3): incomplete: army.mil is unreachable from the build environment.** The network egress policy blocks `www.army.mil`, `api.army.mil`, `armypubs.army.mil`, `www.tradoc.army.mil`, and `www.goarmy.com` (WebFetch: `EGRESS_BLOCKED`; curl: proxy 403). No page content could be read, and no workaround was attempted. The only information gathered came from two web-search result summaries (snippets, not the primary pages). The checklist below marks which items were *not found* and which have only a *snippet-level lead* that must be verified on the primary page before use. **Nothing here may go into `render/theme.py` as-is.**

| Item | Value / rule | Source URL | Accessed |
|---|---|---|---|
| Colors: official Army brand palette (hex/RGB) | **Not found.** Primary pages unreachable. Search surfaced no hex values for the core Army brand. | searched: "Army brand guide colors hex fonts logo usage army.mil" | 2026-10-02 |
| Colors (unrelated lead) | An *Army MWR/IMCOM* guide lists "Light Camo" PMS 7535C, RGB 191/184/166, #BFB8AB. This is a program sub-brand, not the enterprise Army palette; do not adopt. Snippet only. | https://www.mwrbrandcentral.com/download_file/view/e1342f4c-fdd5-470d-8764-452c6c758643/196 | 2026-10-02 |
| Typography | **Not found.** | searched same queries | 2026-10-02 |
| Logo: what it is | Snippet only: enterprise brand centers on a re-engineered five-point star (box removed) with the "Be All You Can Be" tagline; the Army Star always has the U.S. Army tab beneath it and sits left of subordinate unit insignia. | https://www.army.mil/article/264594/new_army_brand_redefines_be_all_you_can_be_for_a_new_generation (not fetched) | 2026-10-02 |
| Logo: clear space, min size, color versions, files | **Not found.** | n/a | 2026-10-02 |
| Logo: may unit/individual training products use it? | **Not found / unresolved.** Snippet says use of Army insignia for *commercial* purposes needs a license via the Army Trademark Licensing Program (ATLP) and recommends the ® symbol on the Star in PowerPoint/web. Whether a locally made, hand-distributed training aid may use the Star is unknown. **Default until resolved: do not use the Star or any Army logo** (see PROJECT_SCOPE §7). | https://www.army.mil/atlp (not fetched); ATLP contact quoted in the search result: usarmy.pentagon.hqda-asa-mra.mbx.army-trademark-licensing@army.mil | 2026-10-02 |
| Trademark/usage limits | Snippet only: any mark/logo/name/motto associated with the Army qualifies as a trademark. License application form exists: https://api.army.mil/e2/c/downloads/2024/09/04/2c148fd9/license-application-2024.pdf (not fetched). The "unofficial training aid" disclaimer stays regardless. | https://www.army.mil/atlp | 2026-10-02 |
| Slide/graphic examples (5–10) | **Not found.** None retrieved. | n/a | 2026-10-02 |
| Related (not Army enterprise) | Other brand guides surfaced and not read: Chaplain Corps brand guide (https://api.army.mil/e2/c/downloads/2021/04/01/bc3c5489/3-0-brand-essence-voice-tone-chaplain-corps-brand-guide.pdf), USACE guides, Military OneSource style guides. | see URLs | 2026-10-02 |

### Addendum (2026-10-02): user-supplied screenshots
The user attached 4 screenshots of Army websites as style references (the originals were not saved in the repo). Colors below were **sampled from screenshot pixels**, so they are visual approximations. They are **not** official brand values (no brand guide was read) and must be confirmed against the Army brand guide before final use. The screenshots show an `army.mil` home page, the Army Publishing Directorate (APD) site, an Army ROTC page, and an Army Worldwide News page.

| Observed element | Sampled hex | Where seen |
|---|---|---|
| Near-black header/nav bar | #222021 | army.mil, ROTC page, news page |
| Army gold (buttons, headlines, accent rule, active filter) | #FFCD01 (also #FCCC00, #F1CC35) | "JOIN US TODAY", "FULL STORY", ROTC headline, news filter |
| Olive-gray secondary bar / tiles | #58574E / #585A52 | army.mil subnav and story strip |
| Dark green page background | #2E362F | ROTC page hero |
| Muted gold/tan nav band and info buttons | #CCB166 | APD nav bar, ROTC "Get in touch" bar (approx. #DBBBA1 light tan) |
| Light gray panels | #F2F2F2, #E6E6E6 | news filter, APD search panel |
| Info callout (light blue + cyan stripe) | #E7F6F8 / #00BDE3 | APD notice box |

Layout and style observations:
- Headlines: large, all-caps, thin/light geometric sans in gold or white on black or dark green; subheads and nav in bold caps with letter-spacing. APD uses a heavier condensed-style sans in caps, with a gold title on black.
- Logo: gold outlined star beside "U.S. ARMY" wordmark, top-left or centered in a black bar. A 1–2 px gold rule sits under the header bar. This is the brand mark, so the logo question (ATLP permission) is still open.
- Buttons: flat, rectangular, gold fill with black bold caps text; no rounded corners; thin-outline white buttons on gray panels.
- Data tables (APD): white background, 1 px black border, light-gray header row, alternating light-gray row banding, black text, blue underlined links.
- Photography is full-bleed with a dark overlay behind text. Icons are thin outline style.
- Contrast: gold #FFCD01 on #222021 is high contrast; gold on white is not usable for text; black on gold is fine. Formal ratios still to be computed in WP 3.1.

Tentative direction for WP 3.1, **pending verification**: black/charcoal + gold + white base, olive-gray secondary, all-caps light sans headings, flat rectangular shapes, gold accent rule. Fonts are not identified from screenshots (could not confirm); use a font that ships with Office as a substitute until the brand guide is read.

**ADP 3-09 test document:** the message said a PDF was attached, but no PDF is present in the session's files or in `data/raw/`. Please re-attach it or commit it to the repo (e.g. `tests/fixtures/` or `data/raw/`) and run `army-trainer fetch ADP-3-09 --pdf <path>`. Note ADP 3-09 (Fires) is an Army Doctrine Publication, not an AR; the Stage 2 cleanup rules assume AR layout, so treat it as an extra test case.

### Checklist status
- [~] Colors: screenshot-sampled approximations only (see addendum); official values still not found
- [ ] Typography: not found
- [ ] Logo: lead only; unresolved
- [ ] Trademark/usage: lead only; ATLP contact identified
- [~] Slide/graphic examples: 4 user-supplied screenshots (see addendum); not army.mil links
- [ ] Accessibility: **blocked** until a palette exists. Can be done in WP 3.1 once colors are known.
- [ ] Decision summary: **blocked.** Interim rule only: no Army logo; neutral placeholder palette; keep disclaimer.

### To unblock
Either (a) allow `www.army.mil`, `api.army.mil` and `armypubs.army.mil` in the environment's network settings and re-run WP 0.3, or (b) the user supplies the Army brand guide / palette / logo-usage decision directly. Phase 3 (WP 3.1) must not start until this is resolved.
