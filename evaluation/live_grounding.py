"""Check the deployed model's explanations on every real shortfall window of the Amalfi statement.

For each weekly 14-day window of 2025 where the statement really goes below zero,
the script sends the real balances and transactions to /api/advice on the deployed
app and checks the answer on this side:
- every amount it cites is one of the facts the server gives the model: balances,
  transaction amounts and the totals the server calculates (same-day payments,
  regular obligations); the fact list comes from backend.advice.build_facts,
- it cites the first gap and the deepest gap, taken straight from the statement,
- it names which model answered and how long it took.
Every answer is saved to evaluation/live_grounding.jsonl for review.

The server already refuses answers that fail its own check (HTTP 503 after a retry
and the fallback model), so a 503 counts as a failed explanation here.

    uv run --locked python -m evaluation.live_grounding --url https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import date

from pathlib import Path

from backend.advice import build_facts, cited_amounts
from backend.models import AdviceRequest
from evaluation.backtest import actual_balances, load_statement, origins

ANSWERS = Path(__file__).resolve().parent / "live_grounding.jsonl"

DAYS = 14


def window_payload(start: date) -> tuple[dict, dict] | None:
    transactions, opening = load_statement()
    _, balances = actual_balances(transactions, opening, start, DAYS)
    if min(balances) >= 0:
        return None
    end = start.toordinal() + DAYS - 1
    rows = [t for t in transactions if start <= t.date and t.date.toordinal() <= end]
    days = [{"date": date.fromordinal(start.toordinal() + i).isoformat(), "balance_minor": b} for i, b in enumerate(balances)]
    first = next(d for d in days if d["balance_minor"] < 0)
    deepest = min(days, key=lambda d: d["balance_minor"])
    payload = {
        "baseline": {"days": days, "first_deficit": {"date": first["date"], "shortfall_minor": -first["balance_minor"]}},
        "transactions": [t.model_dump(mode="json", exclude_none=True) for t in rows],
        "currency": "EUR",
    }
    facts = {
        "first": -first["balance_minor"],
        "deepest": -deepest["balance_minor"],
        "allowed": set(build_facts(AdviceRequest.model_validate(payload)).allowed_minor),
    }
    return payload, facts


def check(explanation: str, facts: dict) -> list[str]:
    cited = cited_amounts(explanation)
    problems = [f"cites {amount / 100:,.2f}, not a fact" for amount in cited if amount not in facts["allowed"]]
    for name in ("first", "deepest"):
        if facts[name] not in cited:
            problems.append(f"misses the {name} gap {facts[name] / 100:,.2f}")
    return problems


def post(url: str, body: dict, timeout: float) -> tuple[int, dict, float]:
    request = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST"
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read()), time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), time.monotonic() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", required=True, help="the deployed app, without a trailing slash")
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()

    transactions, _ = load_statement()
    rows, latencies, models = [], [], {}
    answers = ANSWERS.open("w", encoding="utf-8")
    for start in origins(transactions, DAYS):
        built = window_payload(start)
        if built is None:
            continue
        payload, facts = built
        status, body, seconds = post(f"{args.url}/api/advice", payload, args.timeout)
        problems = check(body.get("explanation", ""), facts) if status == 200 else [f"HTTP {status}: {body.get('detail', '')[:80]}"]
        if status == 200:
            latencies.append(seconds)
            models[body.get("model")] = models.get(body.get("model"), 0) + 1
        rows.append((start, facts["first"], facts["deepest"], status, body.get("model", "-"), seconds, problems))
        answers.write(json.dumps({"start": start.isoformat(), "status": status, "seconds": round(seconds, 1),
                                  "problems": problems, "answer": body}, ensure_ascii=False) + "\n")
        print(f"{start}  gap {facts['first'] / 100:>9,.2f} / {facts['deepest'] / 100:>9,.2f}  HTTP {status}  "
              f"{body.get('model', '-'):<16} {seconds:5.1f}s  {'OK' if not problems else '; '.join(problems)}", flush=True)

    answers.close()
    grounded = sum(1 for *_, problems in rows if not problems)
    print(f"\n{grounded} of {len(rows)} real shortfall windows got a fully grounded explanation.")
    if latencies:
        print(f"Latency: median {statistics.median(latencies):.1f}s, max {max(latencies):.1f}s. Models: {models}")


if __name__ == "__main__":
    main()
