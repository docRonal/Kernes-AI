import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .advice import get_advice, predict_delays, send_reminder
from .consultant import (
    run_ask_cfo,
    run_credit_check,
    run_optimize_payments,
    run_stress_test,
)
from .forecast import DEMO_FILE, get_decision, get_forecast
from .models import (
    AdviceRequest,
    AdviceResponse,
    AskCfoRequest,
    AskCfoResponse,
    CreditCheckRequest,
    CreditCheckResponse,
    DecisionRequest,
    DecisionResponse,
    DelayPredictResponse,
    ForecastRequest,
    ForecastResponse,
    OptimizePaymentsRequest,
    OptimizePaymentsResponse,
    ReminderSendRequest,
    ReminderSendResponse,
    StressTestRequest,
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
    app = FastAPI(title="Autonomous CFO", version="0.1.0")
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

    @app.get("/demo/transactions.csv", include_in_schema=False)
    def sample_csv() -> FileResponse:
        return FileResponse(DEMO_FILE, media_type="text/csv", filename="transactions.csv")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
        return get_advice(mode=mode, request=request)

    @app.post("/api/predict-delays", response_model=DelayPredictResponse)
    def delay_prediction(request: AdviceRequest) -> DelayPredictResponse:
        return predict_delays(mode=mode, request=request)

    @app.post("/api/send-reminder", response_model=ReminderSendResponse)
    def reminder(request: ReminderSendRequest) -> ReminderSendResponse:
        return send_reminder(request)

    @app.post("/api/credit-check", response_model=CreditCheckResponse)
    def credit_check(request: CreditCheckRequest) -> CreditCheckResponse:
        return run_credit_check(mode=mode, request=request)

    @app.post("/api/stress-test", response_model=StressTestResponse)
    def stress_test(request: StressTestRequest) -> StressTestResponse:
        return run_stress_test(mode=mode, request=request)

    @app.post("/api/optimize-payments", response_model=OptimizePaymentsResponse)
    def optimize_payments(request: OptimizePaymentsRequest) -> OptimizePaymentsResponse:
        return run_optimize_payments(mode=mode, request=request)

    @app.post("/api/ask-cfo", response_model=AskCfoResponse)
    def ask_cfo(request: AskCfoRequest) -> AskCfoResponse:
        return run_ask_cfo(mode=mode, request=request)

    return app


app = create_app()
