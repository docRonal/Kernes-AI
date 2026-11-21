"""Write contracts/openapi.json from the routes and models the app serves.

Run from the repository root: uv run --locked python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.main import create_app  # noqa: E402

CONTRACT = ROOT / "contracts" / "openapi.json"


def generate() -> str:
    return json.dumps(create_app("demo").openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    CONTRACT.write_text(generate(), encoding="utf-8")
    print(f"Wrote {CONTRACT.relative_to(ROOT)}")
