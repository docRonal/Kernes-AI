# Does the Liquidity Agent predict correctly?

Two separate questions, two checks:

1. **The forecast:** do the predicted balances, shortfalls and facility limits match what really happened? Python calculates them, so we check them with rolling-origin cross-validation on a real statement ([backtest.py](backtest.py), tests in [tests/test_backtest.py](../tests/test_backtest.py)).
2. **The AI:** does the model served on OpenShift AI explain each real shortfall with the right figures? [live_grounding.py](live_grounding.py) runs that check against the deployed app.

## Data and ground truth

The organizers' Pizzeria Amalfi statement for 2025: 1,125 rows, EUR, with CHF transfers converted at the rate in the payment reference. The statement has no balance column. The info sheet gives the closing balance (EUR 33,266.35), which implies an opening balance of EUR 2,500.00 on 1 January. From there, the real daily balances reproduce the organizers' chart to the cent: the lowest point is −EUR 22,097.60 on 3 July. A test pins all three figures.

## 1. Forecast: rolling-origin cross-validation

Every 7 days from February, each forecaster gets only the rows dated before that day plus the real balance on that morning. It predicts 14 or 30 end-of-day balances, which are then compared with the statement.

- **Mean abs error:** average daily distance between predicted and real balance.
- **Shortfall precision and recall:** whether the forecast warns about a below-zero day inside the horizon, compared with whether one really happens.
- **Limit covered real gap:** whether the proposed facility (the predicted deepest gap) would have covered the real deepest gap. The next column shows the same with a 10% buffer.
- **Uses only the past:** whether the future rows are multiplied by 10 and the forecast still doesn't move.

Forecasters:

- **flat:** the balance never changes. A naive baseline.
- **average net:** the last 28 days' average daily net, every day. A naive baseline.
- **recurring:** learns payees paid on the same day of the month 3 months running, or on the same weekday 3 weeks running, and averages everything else over the last 28 days. Same rule as `backend/history_forecast.py`, which `/api/forecast` uses when the forecast starts after the statement ends; run through this backtest, it gives exactly the same figures.
- **current /api/forecast:** the known-payments path, used when the statement already has rows inside the window. It sums the statement rows dated inside the window.

<!-- backtest:start -->
### Every weekly origin from February

| Forecaster | Horizon | Windows | Mean abs error | Median error on last day | Shortfall precision | Recall | F1 | Limit covered real gap | With +10% buffer | Uses only the past |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flat (baseline) | 14 days | 47 | EUR 3,842 | EUR 5,213 | 100% | 58% | 0.74 | 0% | 12% | yes |
| average net (baseline) | 14 days | 47 | EUR 3,907 | EUR 4,428 | 100% | 62% | 0.77 | 21% | 21% | yes |
| recurring (history) | 14 days | 47 | EUR 1,820 | EUR 1,583 | 91% | 83% | 0.87 | 58% | 71% | yes |
| current /api/forecast, history only | 14 days | 47 | EUR 3,842 | EUR 5,213 | 100% | 58% | 0.74 | 0% | 12% | no, it peeks |
| flat (baseline) | 30 days | 44 | EUR 5,051 | EUR 5,480 | 100% | 44% | 0.61 | 0% | 9% | yes |
| average net (baseline) | 30 days | 44 | EUR 5,389 | EUR 3,170 | 100% | 50% | 0.67 | 22% | 22% | yes |
| recurring (history) | 30 days | 44 | EUR 3,048 | EUR 1,736 | 100% | 84% | 0.92 | 50% | 59% | yes |

### Origins from 01 April (3 months of history)

| Forecaster | Horizon | Windows | Mean abs error | Median error on last day | Shortfall precision | Recall | F1 | Limit covered real gap | With +10% buffer | Uses only the past |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flat (baseline) | 14 days | 38 | EUR 3,854 | EUR 5,290 | 100% | 74% | 0.85 | 0% | 16% | yes |
| average net (baseline) | 14 days | 38 | EUR 3,847 | EUR 4,272 | 100% | 74% | 0.85 | 26% | 26% | yes |
| recurring (history) | 14 days | 38 | EUR 1,267 | EUR 1,035 | 100% | 100% | 1.00 | 68% | 84% | yes |
| current /api/forecast, history only | 14 days | 38 | EUR 3,854 | EUR 5,290 | 100% | 74% | 0.85 | 0% | 16% | no, it peeks |
| flat (baseline) | 30 days | 35 | EUR 5,303 | EUR 5,760 | 100% | 61% | 0.76 | 0% | 13% | yes |
| average net (baseline) | 30 days | 35 | EUR 5,557 | EUR 4,573 | 100% | 61% | 0.76 | 26% | 26% | yes |
| recurring (history) | 30 days | 35 | EUR 2,662 | EUR 1,631 | 100% | 96% | 0.98 | 61% | 74% | yes |
<!-- backtest:end -->

### What this shows

- **Known payments are not a forecast; the history rule is.** Fed only the past, the known-payments path predicts no movement at all, the same as the flat baseline. With the whole statement it copies the real future, and the leak check catches this. That is why the app switches to `backend/history_forecast.py` when the forecast starts after the statement ends, and why the demo presents the June case as known, scheduled payments.
- **Learning from history works.** After 3 months of history, the recurring forecaster warns about every real 14-day shortfall with no false alarms (precision and recall 100%). Its error is a third of the baselines' (EUR 1,267 against about EUR 3,850).
- **Under 3 months of history, it misses shortfalls** (February and March). Monthly payments aren't recognised yet. The app should say "not enough history" instead of showing a confident forecast.
- **The June closure can't be learnt from history.** Late May and early June windows under-propose the facility. On 4 June the 30-day forecast expects −EUR 6,426 against a real −EUR 22,098. The fix is a planned-event input ("closed 8–28 June"), not a better average.
- **A 10% buffer on the limit** lifts real-gap coverage from 68% to 84% (14 days, after warm-up). The remaining misses are the closure. This supports proposing the limit with the stress-test buffer.

## 2. AI: grounding of the live explanations

<!-- live:start -->
Run on 21 November 2026 against https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com (`main` at `cec6f25`). Every 14-day window of 2025 where the statement really goes below zero was sent with its real balances and transactions. The answers are saved in [live_grounding.jsonl](live_grounding.jsonl).

**24 of 24 real shortfall windows got a fully grounded explanation.** Every amount cited was one of the facts the server gives the model. Every answer named the first and the deepest gap. Median latency was 8.2 s and the maximum 17.9 s. `kernes-qwen-7b` (vLLM, GPU) answered 23 windows. The CPU fallback `kernes-qwen` answered 1 (11 June) after the primary failed the server's figure check. Three other answers took 17 s, which looks like a second attempt on the primary.

| Window from | First gap | Deepest gap | HTTP | Model | Seconds | Check |
| --- | --- | --- | --- | --- | --- | --- |
| 2025-01-29 | EUR 1,329.99 | EUR 1,329.99 | 200 | `kernes-qwen-7b` | 8.1 | OK |
| 2025-02-19 | EUR 2,580.02 | EUR 2,580.02 | 200 | `kernes-qwen-7b` | 9.6 | OK |
| 2025-02-26 | EUR 2,580.02 | EUR 2,580.02 | 200 | `kernes-qwen-7b` | 7.6 | OK |
| 2025-03-19 | EUR 1,200.18 | EUR 2,140.30 | 200 | `kernes-qwen-7b` | 17.3 | OK |
| 2025-03-26 | EUR 1,200.18 | EUR 2,777.85 | 200 | `kernes-qwen-7b` | 7.4 | OK |
| 2025-04-02 | EUR 2,112.57 | EUR 2,777.85 | 200 | `kernes-qwen-7b` | 7.3 | OK |
| 2025-04-23 | EUR 2,015.84 | EUR 2,015.84 | 200 | `kernes-qwen-7b` | 6.7 | OK |
| 2025-04-30 | EUR 2,015.84 | EUR 2,015.84 | 200 | `kernes-qwen-7b` | 7.3 | OK |
| 2025-05-21 | EUR 1,793.69 | EUR 1,793.69 | 200 | `kernes-qwen-7b` | 5.5 | OK |
| 2025-05-28 | EUR 1,793.69 | EUR 4,473.69 | 200 | `kernes-qwen-7b` | 7.1 | OK |
| 2025-06-04 | EUR 1,793.69 | EUR 8,848.69 | 200 | `kernes-qwen-7b` | 6.5 | OK |
| 2025-06-11 | EUR 4,473.69 | EUR 8,848.69 | 200 | `kernes-qwen` | 17.9 | OK |
| 2025-06-18 | EUR 8,848.69 | EUR 21,609.46 | 200 | `kernes-qwen-7b` | 8.2 | OK |
| 2025-06-25 | EUR 8,848.69 | EUR 22,097.60 | 200 | `kernes-qwen-7b` | 8.7 | OK |
| 2025-07-02 | EUR 21,598.53 | EUR 22,097.60 | 200 | `kernes-qwen-7b` | 7.7 | OK |
| 2025-07-09 | EUR 14,178.55 | EUR 16,317.64 | 200 | `kernes-qwen-7b` | 9.3 | OK |
| 2025-07-16 | EUR 13,763.30 | EUR 14,467.40 | 200 | `kernes-qwen-7b` | 8.5 | OK |
| 2025-07-23 | EUR 7,129.78 | EUR 12,113.71 | 200 | `kernes-qwen-7b` | 17.1 | OK |
| 2025-07-30 | EUR 10,708.09 | EUR 12,113.71 | 200 | `kernes-qwen-7b` | 8.9 | OK |
| 2025-08-06 | EUR 7,788.39 | EUR 8,424.05 | 200 | `kernes-qwen-7b` | 8.7 | OK |
| 2025-08-13 | EUR 1,735.68 | EUR 4,519.72 | 200 | `kernes-qwen-7b` | 8.8 | OK |
| 2025-08-20 | EUR 280.15 | EUR 4,720.27 | 200 | `kernes-qwen-7b` | 8.1 | OK |
| 2025-08-27 | EUR 4,720.27 | EUR 4,720.27 | 200 | `kernes-qwen-7b` | 8.4 | OK |
| 2025-09-03 | EUR 999.39 | EUR 1,551.25 | 200 | `kernes-qwen-7b` | 7.7 | OK |

### What this shows

- **The guardrail works on real data.** No explanation reached the user with a wrong figure. The one case the primary couldn't ground went to the fallback, which got it right.
- **The first and deepest gaps are always named,** including windows where they differ, from EUR 280.15 against EUR 4,720.27 up to EUR 21,598.53 against EUR 22,097.60.
- **An earlier version of this check flagged amounts such as EUR 2,680.00.** They turned out to be totals the server calculates and gives the model (same-day payments, regular obligations), not invented figures. The check now uses the same fact list as the server.
<!-- live:end -->

## Reproduce

```sh
uv run --locked pytest -q tests/test_backtest.py
uv run --locked python -m evaluation.backtest --write
uv run --locked python -m evaluation.live_grounding --url https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com
```
