# army-trainer

Converts publicly released Army regulations (PDF) into structured Markdown and then into visual, diagram-rich PowerPoint decks to make dense regulatory text easier to digest.

See [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) for the full project scope, architecture, and phased plan, and [docs/ACTION_PLAN.md](docs/ACTION_PLAN.md) for work packages and current status. Claude sessions start from [CLAUDE.md](CLAUDE.md).

> Decks produced by this project are unofficial training aids. The published regulation is always the authoritative source.

## Optional tools for the review report

`army-trainer qa <ID> --report` shows each slide's thumbnail beside its cited text. That needs LibreOffice Impress and poppler on the machine (CI does not need them):

- Debian/Ubuntu: `apt-get install libreoffice-impress poppler-utils`
- macOS: `brew install --cask libreoffice` and `brew install poppler`

If they are missing the command still writes the report, but prints a warning with these instructions and puts a banner at the top of the page.
