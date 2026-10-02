"""Write schemas/doc_tree.schema.json from the Pydantic models.

uv run python -m army_trainer.structure.schema
"""

import json
from pathlib import Path

from .models import DocTree

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "doc_tree.schema.json"


def schema_json() -> str:
    schema = DocTree.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "army-trainer/doc_tree.schema.json"
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(schema_json())
    print(f"wrote {SCHEMA_PATH}")
