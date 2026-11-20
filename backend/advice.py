import json
from pathlib import Path

from fastapi import HTTPException

from .models import AdviceRequest, AdviceResponse


DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"


def get_advice(*, mode: str, request: AdviceRequest) -> AdviceResponse:
    if mode == "live":
        # Replace this branch with a real OpenShift AI adapter. Read
        # CFO_MODEL_URL, CFO_MODEL_NAME and CFO_MODEL_TOKEN from the environment.
        raise HTTPException(503, "OpenShift AI is not connected in this starter.")

    forecast = json.loads((DEMO_DIR / "forecast.example.json").read_text(encoding="utf-8"))
    expected = {
        "first_deficit": forecast["baseline"]["first_deficit"],
        "transactions": forecast["transactions"],
    }
    if request.model_dump(mode="json") != expected:
        raise HTTPException(422, "Submit the bundled baseline forecast in demo mode.")

    return AdviceResponse.model_validate_json(
        (DEMO_DIR / "advice.example.json").read_text(encoding="utf-8")
    )
