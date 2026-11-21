import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .action_plan import build_action_plan
from .advice import check_ai_health, get_advice, predict_delays, send_reminder, use_currency
from .advisory_extras import compare_financing_options, detect_anomalies
from .consultant import ask_cfo, credit_check
from .forecast import AMALFI_DEMO_FILE, get_decision, get_forecast
from .insights import optimize_payments, stress_test
from .models import (
    ActionPlanRequest,
    ActionPlanResponse,
    AdviceRequest,
    AdviceResponse,
    AnomalyDetectRequest,
    AnomalyDetectResponse,
    AskRequest,
    AskResponse,
    CompareOptionsRequest,
    CompareOptionsResponse,
    CreditCheckResponse,
    DecisionRequest,
    DecisionResponse,
    DelayPredictResponse,
    ForecastRequest,
    ForecastResponse,
    InsightRequest,
    PaymentOptimizationResponse,
    ReminderSendRequest,
    ReminderSendResponse,
    StressTestResponse,
)


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def _log_to_stderr() -> None:
    """Send the app's own log lines, such as each model call's latency, to the pod log."""
    logger = logging.getLogger("autonomous_cfo")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def create_app(mode: str | None = None) -> FastAPI:
    if mode is None:
        mode = os.environ.get("CFO_MODE", "demo")
    if mode not in {"demo", "live"}:
        raise ValueError("CFO_MODE must be demo or live.")

    _log_to_stderr()
    app = FastAPI(title="KERNES CFO", version="0.1.0")
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

    @app.get("/demo/amalfi.csv", include_in_schema=False)
    def amalfi_sample_csv() -> FileResponse:
        return FileResponse(
            AMALFI_DEMO_FILE,
            media_type="text/csv",
            filename="pizzeria-amalfi-sample-2025.csv",
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ai", description="Reachability of the configured OpenShift AI primary and fallback models.")
    def health_ai() -> dict:
        return check_ai_health()

    @app.post("/api/forecast", response_model=ForecastResponse)
    async def forecast(request: Annotated[ForecastRequest, File()]) -> ForecastResponse | dict:
        return await get_forecast(
            mode=mode,
            file=request.file,
            starting_balance_minor=request.starting_balance_minor,
            start_date=request.start_date,
            move_transaction_id=request.move_transaction_id,
            move_to_date=request.move_to_date,
        )

    @app.post("/api/decision", response_model=DecisionResponse)
    def decision(request: DecisionRequest) -> DecisionResponse:
        return get_decision(request)

    @app.post("/api/advice", response_model=AdviceResponse)
    def advice(request: AdviceRequest) -> AdviceResponse:
        with use_currency(request.currency):
            return get_advice(mode=mode, request=request)

    @app.post("/api/predict-delays", response_model=DelayPredictResponse)
    def delay_prediction(request: AdviceRequest) -> DelayPredictResponse:
        with use_currency(request.currency):
            return predict_delays(mode=mode, request=request)

    @app.post("/api/send-reminder", response_model=ReminderSendResponse)
    def reminder(request: ReminderSendRequest) -> ReminderSendResponse:
        return send_reminder(request)

    @app.post("/api/stress-test", response_model=StressTestResponse)
    def stress(request: InsightRequest) -> StressTestResponse:
        with use_currency(request.currency):
            return stress_test(request)

    @app.post("/api/optimize-payments", response_model=PaymentOptimizationResponse)
    def optimize(request: InsightRequest) -> PaymentOptimizationResponse:
        with use_currency(request.currency):
            return optimize_payments(request)

    @app.post("/api/credit-check", response_model=CreditCheckResponse)
    def credit(request: AdviceRequest) -> CreditCheckResponse:
        with use_currency(request.currency):
            return credit_check(mode=mode, request=request)

    @app.post("/api/ask-cfo", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        with use_currency(request.currency):
            return ask_cfo(mode=mode, request=request)

    @app.post("/api/detect-anomalies", response_model=AnomalyDetectResponse)
    def anomalies(request: AnomalyDetectRequest) -> AnomalyDetectResponse:
        with use_currency(request.currency):
            return detect_anomalies(mode=mode, request=request)

    @app.post("/api/compare-options", response_model=CompareOptionsResponse)
    def compare_options(request: CompareOptionsRequest) -> CompareOptionsResponse:
        with use_currency(request.currency):
            return compare_financing_options(mode=mode, request=request)

    @app.post("/api/action-plan", response_model=ActionPlanResponse)
    def action_plan(request: ActionPlanRequest) -> ActionPlanResponse:
        with use_currency(request.currency):
            return build_action_plan(mode=mode, request=request)

    return app


app = create_app()
