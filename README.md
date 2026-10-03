# army-trainer

Converts publicly released Army regulations (PDF) into structured Markdown and then into visual, diagram-rich PowerPoint decks to make dense regulatory text easier to digest.

See [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) for the full project scope, architecture, and phased plan, and [docs/ACTION_PLAN.md](docs/ACTION_PLAN.md) for work packages and current status. Claude sessions start from [CLAUDE.md](CLAUDE.md).

> Decks produced by this project are unofficial training aids. The published regulation is always the authoritative source.

## Optional tools for the review report

`army-trainer qa <ID> --report` shows each slide's thumbnail beside its cited text. That needs LibreOffice Impress and poppler on the machine (CI does not need them):

- Debian/Ubuntu: `apt-get install libreoffice-impress poppler-utils`
- macOS: `brew install --cask libreoffice` and `brew install poppler`

If they are missing the command still writes the report, but prints a warning with these instructions and puts a banner at the top of the page.

## Batch mode and update checks

```
army-trainer batch publications.txt        # every deterministic stage, per publication
army-trainer batch publications.txt --stages fetch,convert,index
army-trainer check-updates                 # has anything we hold been revised?
army-trainer build FM-3-09                 # the same pipeline for one publication
```

`publications.txt` has one publication per line: `ID`, `ID path/to.pdf` or `ID https://armypubs.army.mil/...pdf` (`#` starts a comment). With no source, the PDF is taken from `data/inbox/<ID>.pdf`, or from `data/raw/` if already fetched.

Every PDF goes through the Distribution A gate; a rejected one stops there and the rest of the list carries on. Stages that are up to date are skipped (`--force` redoes them). A publication with no committed `specs/<ID>.spec.json` stops after `index` with its planning packet in `data/packets/<ID>/` and the status "needs planning": planning is one Opus session per publication. `render` and `qa` run only where a spec exists. The result table is also saved as `data/batch/report.json`.

`check-updates` never changes `data/raw`: it runs a candidate PDF (from the list, `data/inbox/<ID>.pdf`, or the URL it was fetched from) through the gate in a temp folder and compares hash and date.
