import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_openapi import CONTRACT, generate  # noqa: E402

from backend.currency import CURRENCIES  # noqa: E402


def test_committed_contract_matches_the_app():
    # Regenerate with: uv run --locked python scripts/export_openapi.py
    assert CONTRACT.read_text(encoding="utf-8") == generate()


def test_every_route_is_described_with_its_errors():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for path, operations in contract["paths"].items():
        for method, operation in operations.items():
            assert operation.get("description"), f"{method.upper()} {path} has no description"
            if path.startswith("/api/"):
                assert "422" in operation["responses"], f"{method.upper()} {path} doesn't document 422"


def test_contract_lists_the_eu_currencies():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    currency = contract["components"]["schemas"]["ForecastResponse"]["properties"]["currency"]
    assert currency["enum"] == list(CURRENCIES)
