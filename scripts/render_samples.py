"""Render one sample slide per pattern and (if LibreOffice is installed) PNG thumbnails.

usage: uv run python scripts/render_samples.py [spec.json] [out-dir]
Defaults: tests/fixtures/spec_all_patterns.json -> out/samples/
Needs `soffice` and `pdftoppm` for thumbnails (apt: libreoffice-impress poppler-utils).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from army_trainer.plan.spec import SlideSpec
from army_trainer.render.deck import render_slides

spec_path = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/spec_all_patterns.json")
out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "out/samples")
out_dir.mkdir(parents=True, exist_ok=True)
pptx = out_dir / "samples.pptx"
ctx = render_slides(SlideSpec.model_validate_json(spec_path.read_text()), pptx)
print(pptx, "warnings:", ctx.warnings or "none")
if shutil.which("soffice") and shutil.which("pdftoppm"):
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["pdftoppm", "-r", "50", "-png", str(out_dir / "samples.pdf"), str(out_dir / "slide")],
        check=True,
    )
    print("thumbnails in", out_dir)
else:
    print("soffice/pdftoppm not found: skipped thumbnails")
