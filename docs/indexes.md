# Indexes (stage 3b)

`army-trainer index <ID>` reads `data/json/<ID>.json` (the document tree) and writes `data/json/<ID>.indexes.json`. The code is in `src/army_trainer/index/`. It never reads the Markdown or the PDF. Every entry carries `node_id`, `cite` and `page` from the tree so a slide can cite it (`FM 3-09, <cite>`).

| Index | Key fields | How it works |
|---|---|---|
| `directives` | `verb`, `verbs`, `strength`, `sentence`, `possibly_historical` | Sentences containing `will not`, `must not`, `may not`, `should not`, `shall`, `will`, `must`, `may`, `should`. `verb` is the first one in the sentence, exactly as written. `strength` is `mandatory` (will/must/shall + not forms), `advisory` (should), `permissive` (may) or `prohibitive` (may not) |
| `deadlines` | `kind`, `durations`, `time_references`, `markers`, `sentence` | `deadline` = a marker (NLT, no later than, within, every, ...) with a duration, or a strong marker; `duration` = a duration with no marker; `time_reference` = H-hour / H-6 style only. `NLT` and `NET` match only in capitals |
| `roles` | `name`, `abbreviation`, `kind`, `source`, `mention_count`, `cites`, `duties[]` | Seeds from the glossary acronyms whose meaning has a role word, plus headings under "…PERSONNEL" / "…COMMAND POSTS" / "…FIRE SUPPORT ELEMENT". Squashed headings ("FIRESUPPORTOFFICER") are split using the document's own vocabulary. `duties` are sentences where the role is followed within 60 characters by a directive verb |
| `crossrefs` | `scope`, `kind`, `target`, `raw`, `see`, `target_exists` | `external`: publication numbers (ATP 3-09.50, JP 1 Volume 2, ...), normalized. `internal`: table/figure/chapter/appendix/paragraph/section. `target_exists` is checked against the tree for tables, figures and paragraphs |
| `glossary` | `terms`, `inline_definitions`, `acronyms` | `terms` and `acronyms` are the tree's nodes. `inline_definitions` are italic `_term_ is …` definitions in body text |

## Known limits (read before relying on an index)

- **Directives are lexical.** `may` often states capability ("Cannon artillery may reach..."), and `will` often predicts. FM 3-09 is a doctrine manual, so the counts are high. The planner should decide which are requirements. The fields it can filter on: `strength`, `possibly_historical`, the `section`, and the `verb`.
- **Sentence splitting is rule-based.** Tables flattened into paragraph text (e.g. para A-20) produce long junk "sentences".
- **Roles** are only those named in the glossary acronyms or the personnel/command-post headings. Roles without either (e.g. "Soldier") are not found. Mention counts are text matches (case-insensitive name, case-sensitive abbreviation), not entity resolution.
- **Crossrefs.** `target_exists: false` includes real misses in the FM itself (e.g. a few cited tables are not in the tree because they are images or sit in unconverted pages). External targets are not resolved to anything.
- **Deadlines** are rare in FMs (about 36 for FM 3-09) and several are not Soldier requirements (history quotes, report formats). ARs will have more.
