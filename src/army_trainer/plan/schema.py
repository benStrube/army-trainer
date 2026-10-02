"""Write schemas/slide_spec.schema.json from the Pydantic models.

uv run python -m army_trainer.plan.schema
"""

import json
from pathlib import Path

from .spec import SlideSpec

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "slide_spec.schema.json"


def schema_json() -> str:
    schema = SlideSpec.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "army-trainer/slide_spec.schema.json"
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(schema_json())
    print(f"wrote {SCHEMA_PATH}")
