import json
from datetime import date
from pathlib import Path

from fastapi import HTTPException, UploadFile


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"
DEMO_FILE = DEMO_DIR / "transactions.csv"
DEMO_START = date(2026, 11, 23)
DEMO_STARTING_BALANCE_MINOR = 1_200_000
DEMO_MOVE = ("INV-001", date(2026, 11, 26))


async def get_forecast(
    *,
    mode: str,
    file: UploadFile,
    starting_balance_minor: int,
    start_date: date,
    move_transaction_id: str | None,
    move_to_date: date | None,
) -> dict:
    if mode == "live":
        raise HTTPException(503, "Live forecast is not implemented in this starter.")

    scenario = (move_transaction_id, move_to_date)
    if scenario not in ((None, None), DEMO_MOVE):
        raise HTTPException(422, "Demo scenario: move INV-001 to 2026-11-26.")

    if (starting_balance_minor, start_date) != (DEMO_STARTING_BALANCE_MINOR, DEMO_START):
        raise HTTPException(422, "Use 12000 PLN and start date 2026-11-23 in demo mode.")

    sample = DEMO_FILE.read_text(encoding="utf-8")
    raw = await file.read(len(sample.encode("utf-8")) + 32)
    try:
        actual = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "The CSV must use UTF-8 encoding.") from exc
    if actual.splitlines() != sample.splitlines():
        raise HTTPException(422, "Use the bundled transactions.csv in demo mode.")

    result = json.loads((DEMO_DIR / "forecast.example.json").read_text(encoding="utf-8"))
    if scenario == (None, None):
        result["scenario"] = None
    return result
