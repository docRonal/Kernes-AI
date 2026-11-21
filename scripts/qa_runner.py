"""Multi-core QA & Verification Runner optimized for 8C/16T processors (e.g. Ryzen 7 5700U).

Shards local pytest modules across worker processes so the full unit/API suite
finishes in ~5-7 seconds instead of ~31 seconds sequentially, and orchestrates
remote OpenShift API + Playwright Browser E2E checks in a single command.

Usage:
  uv run --locked python scripts/qa_runner.py --local
  uv run --locked python scripts/qa_runner.py --remote
  uv run --locked python scripts/qa_runner.py --browser
  uv run --locked python scripts/qa_runner.py --all
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OPENSHIFT_URL = "https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com"
LOCAL_TEST_SHARDS: list[tuple[str, list[str]]] = [
    ("tests/test_advice.py [grounding]", ["tests/test_advice.py", "-k", "not unreachable and not fallback and not returns_503_when_both and not unusable_answers and not retries_once"]),
    ("tests/test_advice.py [retries_unusable]", ["tests/test_advice.py", "-k", "unusable_answers or retries_once"]),
    ("tests/test_advice.py [unreachable]", ["tests/test_advice.py", "-k", "unreachable and not fallback"]),
    ("tests/test_advice.py [fallback]", ["tests/test_advice.py", "-k", "fallback"]),
    ("tests/test_advice.py [both_fail]", ["tests/test_advice.py", "-k", "returns_503_when_both"]),
    ("tests/test_advisory_extras.py", ["tests/test_advisory_extras.py"]),
    ("tests/test_forecast.py", ["tests/test_forecast.py"]),
    ("tests/test_insights.py [scores]", ["tests/test_insights.py", "-k", "not question and not what_if and not late_invoice and not bigger_payment"]),
    ("tests/test_insights.py [ask_cfo]", ["tests/test_insights.py", "-k", "question or what_if or late_invoice or bigger_payment"]),
    ("tests/test_smoke.py", ["tests/test_smoke.py"]),
    ("tests/test_stress_csvs.py", ["tests/test_stress_csvs.py"]),
    ("tests/test_telemetry.py", ["tests/test_telemetry.py"]),
]


def _parse_pytest_summary(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for key in ("passed", "failed", "skipped", "error", "errors"):
        m = re.search(rf"(\d+)\s+{key}", output)
        if m:
            norm_key = "errors" if key.startswith("error") else key
            counts[norm_key] = int(m.group(1))
    return counts


def _run_pytest_shard(label: str, pytest_args: list[str]) -> dict:
    env = os.environ.copy()
    env.pop("CFO_BASE_URL", None)
    env.pop("CFO_REQUIRE_LIVE_ADVICE", None)
    env.pop("CFO_RUN_BROWSER_E2E", None)

    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *pytest_args],
        cwd=str(REPO_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.monotonic() - t0, 2)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = _parse_pytest_summary(out)
    return {
        "shard": label,
        "exit_code": proc.returncode,
        "elapsed_s": elapsed,
        **counts,
        "output": out.strip() if proc.returncode != 0 else "",
    }


def run_local_parallel(max_workers: int) -> dict:
    t0 = time.monotonic()
    shards: list[dict] = []
    active_shards = [(label, args) for label, args in LOCAL_TEST_SHARDS if (REPO_DIR / args[0]).is_file()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_run_pytest_shard, label, args) for label, args in active_shards]
        for fut in concurrent.futures.as_completed(futures):
            shards.append(fut.result())

    shards.sort(key=lambda s: s["shard"])
    total_elapsed = round(time.monotonic() - t0, 2)
    totals = {
        "passed": sum(s["passed"] for s in shards),
        "failed": sum(s["failed"] for s in shards),
        "skipped": sum(s["skipped"] for s in shards),
        "errors": sum(s["errors"] for s in shards),
    }
    ok = all(s["exit_code"] == 0 for s in shards)
    return {
        "stage": "local_parallel_pytest",
        "workers": max_workers,
        "ok": ok,
        "elapsed_s": total_elapsed,
        **totals,
        "shards": shards,
    }


def run_remote_workflow(base_url: str) -> dict:
    env = os.environ.copy()
    env["CFO_BASE_URL"] = base_url
    env["CFO_REQUIRE_LIVE_ADVICE"] = "1"

    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_smoke.py", "-k", "test_remote_deployment_workflow"],
        cwd=str(REPO_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.monotonic() - t0, 2)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = _parse_pytest_summary(out)
    return {
        "stage": "remote_openshift_workflow",
        "base_url": base_url,
        "ok": proc.returncode == 0,
        "elapsed_s": elapsed,
        **counts,
        "output": out.strip() if proc.returncode != 0 else "",
    }


def run_browser_e2e(base_url: str) -> dict:
    env = os.environ.copy()
    env["CFO_BASE_URL"] = base_url
    env["CFO_RUN_BROWSER_E2E"] = "1"
    py_cmd = "python" if os.name == "nt" else sys.executable

    t0 = time.monotonic()
    proc = subprocess.run(
        [py_cmd, "tests/test_e2e_browser.py"],
        cwd=str(REPO_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.monotonic() - t0, 2)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = _parse_pytest_summary(out)
    if proc.returncode == 0 and counts["passed"] == 0:
        counts["passed"] = 1
    elif proc.returncode != 0 and counts["failed"] == 0:
        counts["failed"] = 1
    return {
        "stage": "browser_e2e_playwright",
        "base_url": base_url,
        "ok": proc.returncode == 0,
        "elapsed_s": elapsed,
        **counts,
        "output": out.strip() if proc.returncode != 0 else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-core QA runner for Kernes-AI")
    parser.add_argument("--local", action="store_true", help="Run parallel local pytest shards")
    parser.add_argument("--remote", action="store_true", help="Run live OpenShift remote workflow test")
    parser.add_argument("--browser", action="store_true", help="Run Playwright browser E2E test")
    parser.add_argument("--all", action="store_true", help="Run local + remote + browser suites")
    parser.add_argument("--base-url", default=os.environ.get("CFO_BASE_URL", DEFAULT_OPENSHIFT_URL))
    parser.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 8))
    args = parser.parse_args()

    if not (args.local or args.remote or args.browser or args.all):
        args.local = True

    summary: dict = {"cpu_threads_detected": os.cpu_count(), "stages": []}

    if args.local or args.all:
        summary["stages"].append(run_local_parallel(args.workers))
    if args.remote or args.all:
        summary["stages"].append(run_remote_workflow(args.base_url))
    if args.browser or args.all:
        summary["stages"].append(run_browser_e2e(args.base_url))

    summary["all_ok"] = all(st["ok"] for st in summary["stages"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
