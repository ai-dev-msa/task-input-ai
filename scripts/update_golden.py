import json
from pathlib import Path

from alokasi_agent.schema import CREATE_ALOKASI_TOOL

TARGET = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "golden"
    / "create_alokasi_input_schema.json"
)
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(
    json.dumps(CREATE_ALOKASI_TOOL["input_schema"], indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"wrote {TARGET}")
