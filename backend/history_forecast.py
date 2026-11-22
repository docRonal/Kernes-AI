"""Estimate future cash movements and full-year cadence/delay patterns from statement history."""

from calendar import monthrange
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from fractions import Fraction
from statistics import median

from .models import MAX_ABS_MINOR, MAX_LABEL_LENGTH, Transaction, TransactionCategory


ESTIMATED_ID_PREFIX = "FC-"
AVERAGE_DAYS = 28
REGIME_LOOKBACK_DAYS = 84
MIN_REPEATS = 3
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTH_ORDER = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _monthly(earlier: date, later: date) -> bool:
    months_apart = (later.year - earlier.year) * 12 + later.month - earlier.month
    return months_apart == 1 and earlier.day == later.day


def _monthly_jittered(earlier: date, later: date) -> bool:
    months_apart = (later.year - earlier.year) * 12 + later.month - earlier.month
    return months_apart == 1 and abs(later.day - earlier.day) <= 5


def _quarterly(earlier: date, later: date) -> bool:
    months_apart = (later.year - earlier.year) * 12 + later.month - earlier.month
    return months_apart == 3 and earlier.day == later.day


def _weekly(earlier: date, later: date) -> bool:
    return (later - earlier).days == 7


def _biweekly(earlier: date, later: date) -> bool:
    return 12 <= (later - earlier).days <= 16


def _add_months(day: date, months: int, *, target_day: int | None = None) -> date | None:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    if year > date.max.year:
        return None
    month = month_index + 1
    dom = target_day if target_day is not None else day.day
    return date(year, month, min(dom, monthrange(year, month)[1]))


def _streak(rows: list[Transaction], follows: Callable[[date, date], bool]) -> list[Transaction]:
    """The latest occurrence and the consecutive ones within 25% of its amount."""
    latest = rows[-1]
    chain = [latest]
    for row in reversed(rows[:-1]):
        if not follows(row.date, chain[-1].date):
            break
        if abs(row.amount_minor - latest.amount_minor) * 4 > abs(latest.amount_minor):
            break
        chain.append(row)
    return chain


def _average_amount(rows: list[Transaction]) -> int:
    return round(Fraction(sum(row.amount_minor for row in rows), len(rows)))


def _recency_weighted_amount(rows: list[Transaction]) -> int:
    """Blend recent occurrences (last 4) with broader regime history so seasonal/regime shifts show up cleanly."""
    if len(rows) <= 4:
        return _average_amount(rows)
    recent_avg = Fraction(sum(r.amount_minor for r in rows[-4:]), 4)
    full_avg = Fraction(sum(r.amount_minor for r in rows), len(rows))
    return round(recent_avg * Fraction(7, 10) + full_avg * Fraction(3, 10))


def _empirical_weekday_amount(
    rows: list[Transaction],
    target_date: date,
    *,
    base: int | None = None,
) -> int:
    """Apply deterministic week-to-week empirical variation observed across statement history (>= 8 repeats).

    Small statements (< 8 occurrences on a weekday) keep the exact average so short-history
    predictions stay strictly deterministic to the cent.
    """
    anchor_val = base if base is not None else _average_amount(rows)
    if len(rows) < 8:
        return anchor_val
    full_vals = [r.amount_minor for r in rows]
    lo, hi = min(full_vals), max(full_vals)
    if lo == hi:
        return anchor_val
    pool = full_vals[-26:]
    pool_mean = round(Fraction(sum(pool), len(pool)))
    week_idx = target_date.toordinal() // 7
    day_salt = target_date.day * 7 + target_date.weekday() * 5
    label_salt = sum(ord(ch) for ch in rows[-1].label[:24])
    pick = (week_idx * 7 + day_salt + label_salt) % len(pool)
    residual = pool[pick] - pool_mean
    # Amplify natural weekday variance while staying strictly inside the real observed [lo, hi] band
    amplified = round(Fraction(residual * 16, 10))
    candidate = anchor_val + amplified
    return max(lo, min(hi, candidate))


def _split_amount_clusters(rows: list[Transaction]) -> list[list[Transaction]]:
    """Split a counterparty's rows into distinct amount streams (e.g. monthly €880 vs quarterly €1,150 tax)."""
    clusters: list[list[Transaction]] = []
    anchors: list[int] = []
    for row in rows:
        placed = False
        for idx, anchor in enumerate(anchors):
            if abs(row.amount_minor - anchor) * 4 <= abs(anchor):
                clusters[idx].append(row)
                placed = True
                break
        if not placed:
            clusters.append([row])
            anchors.append(row.amount_minor)
    return clusters


def _crosses_closure(earlier: date, later: date, closure_months: set[str]) -> bool:
    if not closure_months or (later - earlier).days <= 7:
        return False
    cur = date(earlier.year, earlier.month, 1)
    end_m = date(later.year, later.month, 1)
    while cur <= end_m:
        if cur.strftime("%Y-%m") in closure_months:
            return True
        nxt = _add_months(cur, 1, target_day=1)
        if nxt is None:
            break
        cur = nxt
    return False


def estimate_transactions(transactions: list[Transaction], window: list[date]) -> list[Transaction]:
    """Estimate recurring monthly/quarterly/weekday payments and daily baseline from full history."""
    start, end = window[0], window[-1]
    history = sorted((row for row in transactions if row.date < start), key=lambda row: row.date)
    if not history:
        return []

    # Anchor recency checks to the end of the recorded statement so projecting weeks 3-4 (+14d)
    # preserves every active schedule instead of letting them expire mid-projection.
    history_end = history[-1].date
    anchor = min(start, history_end + timedelta(days=1)) if history_end < date.max else start
    regime_cutoff = anchor - timedelta(days=min(REGIME_LOOKBACK_DAYS, max(1, (anchor - date.min).days)))

    groups: dict[tuple[str, bool], list[Transaction]] = defaultdict(list)
    for row in history:
        if row.amount_minor:
            groups[(row.label, row.amount_minor > 0)].append(row)

    expected: list[tuple[date, int, str, TransactionCategory]] = []
    explained_ids: set[str] = set()

    for (_group_label, _is_pos), group_rows in groups.items():
        clusters = _split_amount_clusters(group_rows)
        remaining_for_weekday: list[Transaction] = []

        for sub_rows in clusters:
            latest = sub_rows[-1]
            label = f"Estimated {latest.label}"[:MAX_LABEL_LENGTH]
            category = latest.category or "other"

            # 1a. Exact monthly schedule (same day-of-month, >= 3 consecutive months)
            monthly = _streak(sub_rows, _monthly)
            first_next_month = _add_months(latest.date, 1)
            if len(monthly) >= MIN_REPEATS and first_next_month is not None and first_next_month >= anchor:
                for r in sub_rows:
                    explained_ids.add(r.id)
                amount = _average_amount(monthly)
                month_step = 1
                due = first_next_month
                while due is not None and due <= end:
                    if due >= start:
                        expected.append((due, amount, label, category))
                    month_step += 1
                    due = _add_months(latest.date, month_step)
                continue

            # 1b. Jittered / regularly delayed monthly schedule (±5d drift around typical settlement day)
            monthly_jit = _streak(sub_rows, _monthly_jittered)
            if len(monthly_jit) >= MIN_REPEATS:
                typical_dom = round(median(r.date.day for r in monthly_jit))
                first_jit_due = _add_months(latest.date, 1, target_day=typical_dom)
                if first_jit_due is not None and (anchor - latest.date).days <= 38:
                    for r in sub_rows:
                        explained_ids.add(r.id)
                    amount = _average_amount(monthly_jit)
                    month_step = 1
                    due = first_jit_due
                    while due is not None and due <= end:
                        if due >= start:
                            expected.append((due, amount, label, category))
                        month_step += 1
                        due = _add_months(latest.date, month_step, target_day=typical_dom)
                    continue

            # 2. Quarterly schedule (every 3 months on same day-of-month, >= 3 consecutive quarters)
            quarterly = _streak(sub_rows, _quarterly)
            first_next_quarter = _add_months(latest.date, 3)
            if len(quarterly) >= MIN_REPEATS and first_next_quarter is not None and first_next_quarter >= anchor:
                # Mark explained even if next quarter > end so quarterly tax isn't smeared as daily spending!
                for r in sub_rows:
                    explained_ids.add(r.id)
                amount = _average_amount(quarterly)
                q_step = 3
                due = first_next_quarter
                while due is not None and due <= end:
                    if due >= start:
                        expected.append((due, amount, label, category))
                    q_step += 3
                    due = _add_months(latest.date, q_step)
                continue

            remaining_for_weekday.extend(sub_rows)

        if not remaining_for_weekday:
            continue

        remaining_for_weekday.sort(key=lambda r: r.date)
        latest_any = remaining_for_weekday[-1]
        label = f"Estimated {latest_any.label}"[:MAX_LABEL_LENGTH]

        # 3. Weekday cadence: strict weekly streak OR resilient full-regime frequency (>=60% active weeks)
        matched_any_weekday = False
        for weekday in range(7):
            on_weekday = [row for row in remaining_for_weekday if row.date.weekday() == weekday]
            if len(on_weekday) < MIN_REPEATS:
                continue

            latest_weekly = on_weekday[-1]
            weekly = _streak(on_weekday, _weekly)
            category = latest_weekly.category or "other"

            # Still active at end of statement: within 7 days of anchor (exact weekly cadence)
            if len(weekly) >= MIN_REPEATS and (anchor - latest_weekly.date).days <= 7:
                matched_any_weekday = True
                for r in on_weekday:
                    explained_ids.add(r.id)
                base_amount = _average_amount(weekly)
                for day in window:
                    if day.weekday() == weekday:
                        amount = _empirical_weekday_amount(on_weekday, day, base=base_amount)
                        expected.append((day, amount, label, category))
                continue

            # Resilient check for high-frequency counterparties with occasional skipped days (e.g. wholesale market)
            recent_wd = [r for r in on_weekday if r.date >= regime_cutoff]
            if len(recent_wd) >= 4:
                days_since_first = max(7, (anchor - recent_wd[0].date).days)
                active_weeks = max(1, round(days_since_first / 7))
                if len(recent_wd) / active_weeks >= 0.60 and (anchor - recent_wd[-1].date).days <= 21:
                    matched_any_weekday = True
                    for r in on_weekday:
                        explained_ids.add(r.id)
                    base_amount = _recency_weighted_amount(recent_wd)
                    for day in window:
                        if day.weekday() == weekday:
                            amount = _empirical_weekday_amount(on_weekday, day, base=base_amount)
                            expected.append((day, amount, label, category))

        # 4. Biweekly schedule (every ~14 days ± 2d, >= 3 consecutive cycles)
        if not matched_any_weekday:
            biweekly = _streak(remaining_for_weekday, _biweekly)
            if len(biweekly) >= MIN_REPEATS and (anchor - biweekly[0].date).days <= 18:
                for r in remaining_for_weekday:
                    explained_ids.add(r.id)
                amount = _average_amount(biweekly)
                category = biweekly[0].category or "other"
                gaps = [(biweekly[i].date - biweekly[i + 1].date).days for i in range(len(biweekly) - 1)]
                step_days = max(12, min(16, round(median(gaps)))) if gaps else 14
                due = biweekly[0].date
                while due <= end:
                    if due >= start:
                        expected.append((due, amount, label, category))
                    if (date.max - due).days < step_days:
                        break
                    due += timedelta(days=step_days)

    span = min(AVERAGE_DAYS, (anchor - history[0].date).days)
    recent = [row for row in history if (anchor - row.date).days <= span]
    rest = [row for row in recent if row.id not in explained_ids]
    for label, total in (
        ("Estimated daily income", sum(row.amount_minor for row in rest if row.amount_minor > 0)),
        ("Estimated daily spending", sum(row.amount_minor for row in rest if row.amount_minor < 0)),
    ):
        per_day = round(Fraction(total, span)) if span > 0 else 0
        if abs(per_day) > MAX_ABS_MINOR:
            raise ValueError(f"The {label.lower()} is out of range.")
        if per_day:
            expected.extend((day, per_day, label, "other") for day in window)

    expected.sort(key=lambda payment: (payment[0], payment[2], payment[1]))
    return [
        Transaction(
            id=f"{ESTIMATED_ID_PREFIX}{number:04d}",
            date=day,
            amount_minor=amount,
            label=label,
            transaction_type="ESTIMATE",
            category=category,
            actionability="retail_non_contactable" if amount > 0 else "fixed_mandatory",
        )
        for number, (day, amount, label, category) in enumerate(expected, start=1)
    ]


def _measure_weekday_jitter(rows: list[Transaction], closure_months: set[str]) -> tuple[int, int]:
    """Measure average and max late-day slippage across each active weekday (ignoring closure gaps)."""
    delays: list[int] = []
    for wd in range(7):
        wd_rows = [r for r in rows if r.date.weekday() == wd]
        for i in range(1, len(wd_rows)):
            earlier, later = wd_rows[i - 1].date, wd_rows[i].date
            if _crosses_closure(earlier, later, closure_months):
                continue
            gap = (later - earlier).days
            if gap > 7:
                delays.append(gap - 7)
    if not delays:
        return 0, 0
    return round(sum(delays) / len(delays)), max(delays)


def _measure_daily_skips(rows: list[Transaction], closure_months: set[str]) -> tuple[int, int]:
    """Measure skipped-day gaps for a 7-day daily stream (ignoring closure gaps)."""
    skips: list[int] = []
    for i in range(1, len(rows)):
        earlier, later = rows[i - 1].date, rows[i].date
        if _crosses_closure(earlier, later, closure_months):
            continue
        gap = (later - earlier).days
        if gap > 1:
            skips.append(gap - 1)
    if not skips:
        return 0, 0
    return round(sum(skips) / len(skips)), max(skips)


def analyze_statement_patterns(transactions: list[Transaction], start: date) -> dict:
    """Summarize full-history trends, seasonality, closure months, recurring cadences, and payment delays."""
    history = sorted((row for row in transactions if row.date < start), key=lambda row: row.date)
    if not history:
        history = sorted(transactions, key=lambda row: row.date)
    if not history:
        return {
            "history_span_days": 0,
            "transactions_analyzed": 0,
            "months_analyzed": 0,
            "monthly_totals": [],
            "trend_note": None,
            "seasonality_note": None,
            "weekend_lift_note": None,
            "closure_months": [],
            "daily_volatility_minor": 0,
            "patterns": [],
        }

    span_days = max(1, (history[-1].date - history[0].date).days + 1)
    by_month: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    daily_net: dict[date, int] = defaultdict(int)
    for row in history:
        ym = row.date.strftime("%Y-%m")
        daily_net[row.date] += row.amount_minor
        if row.amount_minor > 0:
            by_month[ym][0] += row.amount_minor
        elif row.amount_minor < 0:
            by_month[ym][1] += abs(row.amount_minor)

    monthly_totals = [
        {"month": ym, "inflow_minor": vals[0], "outflow_minor": vals[1], "net_minor": vals[0] - vals[1]}
        for ym, vals in sorted(by_month.items())
    ]
    closure_months = [m["month"] for m in monthly_totals if m["inflow_minor"] == 0 and m["outflow_minor"] > 0]
    closure_set = set(closure_months)

    # Daily net cash-flow volatility (MAD over active days, excluding closure months)
    active_nets = [
        net for d, net in daily_net.items() if d.strftime("%Y-%m") not in closure_set
    ]
    if len(active_nets) >= 5:
        med_net = median(active_nets)
        mad = median(abs(v - med_net) for v in active_nets)
        daily_volatility_minor = round(mad)
    else:
        daily_volatility_minor = 0

    # Structural trend note (compare earlier active half vs recent active half when >= 6 active months)
    active_months = [m for m in monthly_totals if m["inflow_minor"] > 0]
    trend_note = None
    if len(active_months) >= 6:
        mid = len(active_months) // 2
        early_half = active_months[:mid]
        late_half = active_months[mid:]
        early_avg = round(sum(m["inflow_minor"] for m in early_half) / len(early_half))
        late_avg = round(sum(m["inflow_minor"] for m in late_half) / len(late_half))
        if early_avg > 0:
            pct = round(((late_avg - early_avg) / early_avg) * 100)
            if abs(pct) >= 5:
                sign = "+" if pct > 0 else ""
                closure_suffix = (
                    f" (excluding {', '.join(closure_months)} closure)" if closure_months else ""
                )
                trend_note = (
                    f"Recent {len(late_half)}-month inflows averaged {sign}{pct}% vs the earlier "
                    f"{len(early_half)} months{closure_suffix}."
                )

    # Seasonality comparison: same calendar month in prior year vs latest active month
    seasonality_note = None
    target_mm = start.strftime("%m")
    same_month_prior = [m for m in active_months if m["month"].endswith(f"-{target_mm}")]
    if same_month_prior and active_months:
        prior = same_month_prior[-1]
        latest_m = active_months[-1]
        if prior["month"] != latest_m["month"] and latest_m["inflow_minor"] > 0:
            pct_diff = round(((prior["inflow_minor"] - latest_m["inflow_minor"]) / latest_m["inflow_minor"]) * 100)
            direction = "lower" if pct_diff < 0 else "higher"
            seasonality_note = (
                f"In {prior['month']}, inflows were {abs(pct_diff)}% {direction} than {latest_m['month']}."
            )

    # Weekend vs weekday lift for daily retail receipts
    weekend_lift_note = None
    retail_in = [r for r in history if r.amount_minor > 0 and r.category == "retail_card"]
    if len(retail_in) >= 28:
        wkday = [r.amount_minor for r in retail_in if r.date.weekday() < 4]
        wkend = [r.amount_minor for r in retail_in if r.date.weekday() >= 4]
        if wkday and wkend:
            avg_wd = sum(wkday) / len(wkday)
            avg_we = sum(wkend) / len(wkend)
            if avg_wd > 0:
                lift = round(((avg_we - avg_wd) / avg_wd) * 100)
                if lift >= 10:
                    weekend_lift_note = f"Fri–Sun card settlements averaged +{lift}% higher than Mon–Thu."

    groups: dict[tuple[str, bool], list[Transaction]] = defaultdict(list)
    for row in history:
        if row.amount_minor:
            groups[(row.label, row.amount_minor > 0)].append(row)

    patterns: list[dict] = []
    for (cp_label, is_pos), rows in groups.items():
        rows.sort(key=lambda r: r.date)
        clusters = _split_amount_clusters(rows)

        # Only keep clusters separate when they represent distinct fixed monthly/quarterly schedules
        # (e.g. Tax Office monthly wage tax vs quarterly income tax). Keep variable weekday streams unified.
        fixed_clusters: list[list[Transaction]] = []
        variable_rows: list[Transaction] = []
        for sub in clusters:
            if len(sub) >= 3 and (
                len(_streak(sub, _monthly)) >= 3
                or len(_streak(sub, _monthly_jittered)) >= 3
                or len(_streak(sub, _quarterly)) >= 3
            ):
                fixed_clusters.append(sub)
            else:
                variable_rows.extend(sub)

        streams = fixed_clusters + ([sorted(variable_rows, key=lambda r: r.date)] if variable_rows else [])

        for sub in streams:
            if len(sub) < 2:
                continue
            gaps = [
                (sub[i].date - sub[i - 1].date).days
                for i in range(1, len(sub))
                if (sub[i].date - sub[i - 1].date).days > 0
                and not _crosses_closure(sub[i - 1].date, sub[i].date, closure_set)
            ]
            if not gaps:
                continue

            med_gap = float(median(gaps))
            doms = sorted({r.date.day for r in sub})
            wds = sorted({r.date.weekday() for r in sub})
            avg_delay = 0
            max_delay = 0

            if len(sub) >= 3 and len(_streak(sub, _monthly)) >= 3:
                cadence_label = f"Monthly · day {sub[-1].date.day}"
                regularity = "On time (±0d)"
            elif len(sub) >= 3 and len(_streak(sub, _monthly_jittered)) >= 3:
                min_dom = min(r.date.day for r in sub)
                drifts = [r.date.day - min_dom for r in sub]
                avg_delay = round(sum(drifts) / len(drifts))
                max_delay = max(drifts)
                typical_dom = round(median(r.date.day for r in sub))
                cadence_label = f"Monthly · ~day {typical_dom}"
                regularity = (
                    "On time (±0d)"
                    if max_delay == 0
                    else f"Regular drift (+{avg_delay}d avg, up to +{max_delay}d)"
                )
            elif len(sub) >= 3 and len(_streak(sub, _quarterly)) >= 3:
                months_str = "/".join(
                    sorted({r.date.strftime("%b") for r in sub}, key=lambda m: MONTH_ORDER.index(m))
                )
                cadence_label = f"Quarterly ({months_str}) · day {sub[-1].date.day}"
                regularity = "On time (±0d)"
            elif len(wds) == 7 and med_gap <= 1.5:
                avg_delay, max_delay = _measure_daily_skips(sub, closure_set)
                cadence_label = "Daily · 7 days/week"
                regularity = "On time (±0d)" if max_delay == 0 else f"Occasional skip (up to +{max_delay}d)"
            elif len(wds) <= 5 and med_gap <= 7.5:
                wd_str = ", ".join(WEEKDAY_NAMES[w] for w in wds)
                avg_delay, max_delay = _measure_weekday_jitter(sub, closure_set)
                cadence_label = f"{len(wds)}×/week · {wd_str}"
                regularity = "On time (±0d)" if max_delay == 0 else f"Occasional skip (up to +{max_delay}d)"
            elif len(sub) >= 3 and len(_streak(sub, _biweekly)) >= 3:
                jitter = [abs(g - 14) for g in gaps]
                avg_delay = round(sum(jitter) / len(jitter))
                max_delay = max(jitter)
                cadence_label = "Every 2 weeks"
                regularity = "On time (±0d)" if max_delay == 0 else f"±{max_delay}d timing drift"
            elif len(doms) <= 3 and 26 <= med_gap <= 33:
                drifts = [abs(r.date.day - round(median(x.date.day for x in sub))) for r in sub]
                max_delay = max(drifts)
                avg_delay = round(sum(drifts) / len(drifts))
                cadence_label = f"Monthly · ~day {round(median(r.date.day for r in sub))}"
                regularity = "On time (±0d)" if max_delay == 0 else f"±{max_delay}d timing drift"
            else:
                max_delay = max(0, round(max(gaps) - med_gap))
                avg_delay = round(sum(max(0, round(g - med_gap)) for g in gaps) / len(gaps))
                cadence_label = f"Every ~{round(med_gap)} days"
                regularity = "Regular" if max_delay <= 1 else f"Variable (up to +{max_delay}d)"

            recent_slice = sub[-min(len(sub), 12):]
            avg_amt = abs(_average_amount(recent_slice))
            patterns.append(
                {
                    "counterparty": cp_label,
                    "direction": "inflow" if is_pos else "outflow",
                    "category": sub[-1].category or "other",
                    "cadence": cadence_label,
                    "occurrences": len(sub),
                    "typical_amount_minor": avg_amt,
                    "regularity": regularity,
                    "avg_delay_days": avg_delay,
                    "max_delay_days": max_delay,
                    "total_volume_minor": sum(abs(r.amount_minor) for r in sub),
                }
            )

    patterns.sort(key=lambda p: (-p["total_volume_minor"], -p["occurrences"]))
    return {
        "history_span_days": span_days,
        "transactions_analyzed": len(history),
        "months_analyzed": len(monthly_totals),
        "monthly_totals": monthly_totals,
        "trend_note": trend_note,
        "seasonality_note": seasonality_note,
        "weekend_lift_note": weekend_lift_note,
        "closure_months": closure_months,
        "daily_volatility_minor": daily_volatility_minor,
        "patterns": patterns[:16],
    }
