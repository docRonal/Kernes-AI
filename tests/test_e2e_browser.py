import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None

REPO_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_DIR / "demo"


def _skip_if_not_enabled(func):
    if pytest is None:
        return func
    return pytest.mark.skipif(
        os.environ.get("CFO_RUN_BROWSER_E2E") != "1",
        reason="Set CFO_RUN_BROWSER_E2E=1 to run Playwright browser E2E checks.",
    )(func)


def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True, channel="msedge")
    except Exception:
        return playwright.chromium.launch(headless=True)


def _start_local_server(port: int = 8095) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("CFO_MODE", "demo")
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "--locked",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 25.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2.0) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("Local uvicorn server did not start within 25s")


@_skip_if_not_enabled
def test_browser_end_to_end_workflow():
    from playwright.sync_api import sync_playwright

    remote_url = os.environ.get("CFO_BASE_URL", "").strip().rstrip("/")
    local_proc = None
    if remote_url:
        base_url = remote_url
        is_live_remote = True
    else:
        local_proc = _start_local_server(8095)
        base_url = "http://127.0.0.1:8095"
        is_live_remote = False

    console_errors: list[str] = []
    page_errors: list[str] = []
    unexpected_http_errors: list[dict] = []
    intercept_503 = {"enabled": False}

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            page.on("pageerror", lambda err: page_errors.append(str(err)))
            page.on(
                "console",
                lambda msg: None
                if (intercept_503["enabled"] and "503" in msg.text)
                else (console_errors.append(msg.text) if msg.type == "error" else None),
            )

            def on_route(route):
                if intercept_503["enabled"] and "/api/advice" in route.request.url:
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body=json.dumps({"detail": "Simulated 503 outage"}),
                    )
                    return
                route.continue_()

            page.route("**/api/advice*", on_route)

            def on_response(resp):
                if resp.url.startswith(base_url) and resp.status >= 400:
                    path = resp.url[len(base_url):]
                    if not (intercept_503["enabled"] and path.startswith("/api/advice")):
                        unexpected_http_errors.append({"path": path, "status": resp.status})

            page.on("response", on_response)

            # 1. Landing Page & Health Pill
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            page.locator("#setup-screen").wait_for(state="visible", timeout=15000)
            page.wait_for_function(
                "() => document.getElementById('health-pill')?.textContent?.trim() === 'API Online'",
                timeout=15000,
            )
            assert page.title() == "KERNES CFO — Simple Cash Assistant"
            assert page.locator("header h1").inner_text().strip() == "KERNES CFO"
            assert page.locator("#account-pill").inner_text().strip() == "EUR Account"

            # 2. Case 1 — Default Pizzeria Amalfi EUR + All Insight Cards + Decisions + What-If + Simulate Send
            with (
                page.expect_response("**/api/forecast", timeout=30000) as c1_fc,
                page.expect_response("**/api/advice", timeout=120000) as c1_adv,
                page.expect_response("**/api/compare-options", timeout=120000) as c1_cmp,
                page.expect_response("**/api/credit-check", timeout=120000) as c1_cred,
                page.expect_response("**/api/stress-test", timeout=30000) as c1_str,
                page.expect_response("**/api/optimize-payments", timeout=30000) as c1_opt,
                page.expect_response("**/api/detect-anomalies", timeout=120000) as c1_anom,
            ):
                page.locator("#run-forecast-btn").click()

            for r in (c1_fc, c1_adv, c1_cmp, c1_cred, c1_str, c1_opt, c1_anom):
                assert r.value.status == 200

            page.locator("#results").wait_for(state="visible", timeout=10000)
            page.locator("#explanation").wait_for(state="visible", timeout=10000)
            page.locator("#compare-card").wait_for(state="visible", timeout=15000)
            page.locator("#health-stress-grid").wait_for(state="visible", timeout=15000)
            page.locator("#optimize-card").wait_for(state="visible", timeout=15000)
            page.locator("#anomalies-card").wait_for(state="visible", timeout=15000)

            assert "8,248.91 EUR short on 3 Jul 2025" in page.locator("#hero-title").inner_text()
            assert page.locator("#proposal-limit-value").inner_text().strip() == "8,248.91 EUR"

            with page.expect_response("**/api/decision", timeout=20000):
                page.locator("#approve-sim-btn").click()
            assert page.locator("#outcome-gap-value").inner_text().strip() == "0.00 EUR"

            with page.expect_response("**/api/decision", timeout=20000):
                page.locator("#reject-sim-btn").click()
            assert page.locator("#outcome-gap-value").inner_text().strip() == "8,248.91 EUR"

            page.locator("#tab-whatif").click()
            page.locator("#panel-whatif").wait_for(state="visible", timeout=5000)
            with page.expect_response("**/api/forecast", timeout=30000):
                page.locator("#compare-dates-btn").click()
            page.locator("#scenario-summary-box").wait_for(state="visible", timeout=5000)

            with page.expect_response("**/api/send-reminder", timeout=20000) as rem_info:
                page.locator("#send-reminder-btn").click()
            assert rem_info.value.status == 200
            page.locator("#reminder-receipt").wait_for(state="visible", timeout=5000)

            if page.locator("#optimize-footer").is_visible():
                before = page.locator("#optimize-toggle").inner_text().strip()
                page.locator("#optimize-toggle").click()
                after = page.locator("#optimize-toggle").inner_text().strip()
                assert before != after

            if is_live_remote:
                page.locator("#whatif-mode-delay").click()
                page.locator("#delay-days-input").fill("2")
                with page.expect_response("**/api/predict-delays", timeout=120000) as del_info:
                    page.locator("#delay-predict-btn").click()
                assert del_info.value.status == 200
                page.locator("#delay-result-box").wait_for(state="visible", timeout=10000)

                page.locator("#whatif-mode-ask").click()
                with page.expect_response("**/api/ask-cfo", timeout=120000) as ask_info:
                    page.locator('.ask-chip[data-question*="riskiest"]').click()
                assert ask_info.value.status == 200
                page.locator("#ask-answer-box").wait_for(state="visible", timeout=10000)

            # 3. Case 2 — No Shortfall CSV
            page.locator("#change-file-btn").click()
            page.locator("#setup-screen").wait_for(state="visible", timeout=10000)
            page.locator("#csv-file").set_input_files(str(DEMO_DIR / "no_shortfall_case.csv"))
            page.locator("#opening-balance").fill("15000.00")
            page.locator("#start-date").fill("2026-11-23")
            with (
                page.expect_response("**/api/forecast", timeout=30000) as ns_fc,
                page.expect_response("**/api/compare-options", timeout=120000),
                page.expect_response("**/api/stress-test", timeout=30000),
                page.expect_response("**/api/optimize-payments", timeout=30000),
                page.expect_response("**/api/detect-anomalies", timeout=120000),
            ):
                page.locator("#run-forecast-btn").click()
            assert ns_fc.value.status == 200
            assert page.locator("#hero-badge").inner_text().strip() == "All good"
            assert page.locator("#credit-score-value").inner_text().strip() == "100"

            # 4. Case 3 — Simulated /api/advice HTTP 503 outage on credit_peak_case.csv
            page.locator("#change-file-btn").click()
            page.locator("#setup-screen").wait_for(state="visible", timeout=10000)
            intercept_503["enabled"] = True
            page.locator("#csv-file").set_input_files(str(DEMO_DIR / "credit_peak_case.csv"))
            page.locator("#opening-balance").fill("1000.00")
            page.locator("#start-date").fill("2026-11-23")
            with (
                page.expect_response("**/api/forecast", timeout=30000) as out_fc,
                page.expect_response("**/api/advice", timeout=30000) as out_adv,
                page.expect_response("**/api/compare-options", timeout=120000),
                page.expect_response("**/api/credit-check", timeout=120000),
                page.expect_response("**/api/detect-anomalies", timeout=120000),
            ):
                page.locator("#run-forecast-btn").click()
            assert out_fc.value.status == 200 and out_adv.value.status == 503
            page.locator("#advice-error").wait_for(state="visible", timeout=10000)
            assert page.locator("#retry-advice-btn").is_visible()
            assert page.locator("#proposal-limit-value").inner_text().strip() == "700.00 EUR"
            with page.expect_response("**/api/decision", timeout=20000):
                page.locator("#approve-sim-btn").click()
            assert page.locator("#outcome-gap-value").inner_text().strip() == "0.00 EUR"
            intercept_503["enabled"] = False

            browser.close()

        assert not page_errors, f"Uncaught page errors: {page_errors}"
        assert not console_errors, f"Console errors: {console_errors}"
        assert not unexpected_http_errors, f"Unexpected HTTP errors: {unexpected_http_errors}"
    finally:
        if local_proc is not None:
            local_proc.terminate()
            try:
                local_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                local_proc.kill()


if __name__ == "__main__":
    os.environ.setdefault("CFO_RUN_BROWSER_E2E", "1")
    test_browser_end_to_end_workflow()
    print("1 passed in browser E2E")
