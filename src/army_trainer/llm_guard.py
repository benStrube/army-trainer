"""Guard for the Claude API client: refuse any document without a passing gate record."""

from __future__ import annotations

import json
from pathlib import Path

from .fetch.models import PubMetadata


class GateError(RuntimeError):
    pass


def require_gate_pass(meta: PubMetadata) -> None:
    g = meta.gate
    if g.status != "pass" or g.distribution != "A":
        raise GateError(
            f"{meta.pub_id} has no passing Distribution A gate record ({g.reason}); "
            "refusing to send it to the Claude API."
        )


def load_gated_metadata(pub_id: str, raw_dir: Path = Path("data/raw")) -> PubMetadata:
    """Load metadata for `pub_id` and enforce the gate. Every API call path must use this."""
    path = raw_dir / f"{pub_id}.meta.json"
    if not path.exists():
        raise GateError(f"No gate record for {pub_id} at {path}; run `army-trainer fetch` first.")
    meta = PubMetadata.model_validate(json.loads(path.read_text()))
    require_gate_pass(meta)
    return meta
