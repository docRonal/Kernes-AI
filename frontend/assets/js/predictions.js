const MS_PER_DAY = 86_400_000;

function toUtcMs(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

export function addDaysIso(isoDate, offsetDays) {
  const dt = new Date(toUtcMs(isoDate) + offsetDays * MS_PER_DAY);
  return dt.toISOString().slice(0, 10);
}

function diffDaysIso(fromIso, toIso) {
  return Math.round((toUtcMs(toIso) - toUtcMs(fromIso)) / MS_PER_DAY);
}

function computeDailyStd(baselineDays, dailyVolatilityMinor = 0) {
  if (dailyVolatilityMinor > 0) return dailyVolatilityMinor * 1.4826;
  const deltas = [];
  for (let i = 1; i < (baselineDays?.length || 0); i += 1) {
    deltas.push(baselineDays[i].balance_minor - baselineDays[i - 1].balance_minor);
  }
  const mean = deltas.length > 0 ? deltas.reduce((acc, v) => acc + v, 0) / deltas.length : 0;
  const variance =
    deltas.length > 0
      ? deltas.reduce((acc, v) => acc + (v - mean) ** 2, 0) / deltas.length
      : 0;
  return Math.sqrt(variance);
}

/**
 * Deterministic, realistic cash-rhythm wave used ONLY when a forward continuation
 * is artificially linear (e.g. short 3-row CSVs without enough history for real schedules).
 */
function deterministicCashWave(isoDate, stepIndex, totalSteps, amplitudeMinor) {
  if (amplitudeMinor <= 0 || totalSteps <= 2 || stepIndex === totalSteps - 1) return 0;
  const [y, m, d] = isoDate.split("-").map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat
  // Realistic SME cash spikes/dips: Mon/Fri receipts up, Tue/Thu supplier bills down, Wed sharp dip
  const weekdayProfile = [0.22, 0.85, -0.35, -0.92, -0.28, 0.88, -0.45][dow] ?? 0;
  const salt = ((y * 31 + m * 17 + d * 13) % 23) / 23;
  const multiHarmonic =
    Math.sin((stepIndex + 1) * 1.9 + salt * Math.PI * 2) * 0.55 +
    Math.cos((stepIndex + 1) * 3.1 + salt * Math.PI) * 0.35;
  const env = Math.sin(((stepIndex + 1) / (totalSteps + 1)) * Math.PI);
  return Math.round((weekdayProfile * 0.62 + multiHarmonic * 0.38) * amplitudeMinor * (0.55 + 0.45 * env));
}

/**
 * Attach empirical confidence cone bounds (low_minor, high_minor) to a series of projected days
 * anchored at anchorBalanceMinor.
 */
export function buildConfidenceSeries(
  days,
  anchorBalanceMinor,
  referenceDays = [],
  dailyVolatilityMinor = 0,
) {
  if (!days?.length) return [];
  const stdDaily = computeDailyStd(referenceDays.length ? referenceDays : days, dailyVolatilityMinor);
  return days.map((day, idx) => {
    const k = idx + 1;
    const stepDiff = Math.abs(day.balance_minor - anchorBalanceMinor);
    const spread = Math.round(
      Math.max(
        stdDaily * Math.sqrt(k) * 0.55,
        stepDiff * 0.16,
        Math.abs(anchorBalanceMinor) * 0.03,
        5_000,
      ),
    );
    return {
      ...day,
      low_minor: day.balance_minor - spread,
      high_minor: day.balance_minor + spread,
    };
  });
}

/**
 * Project +extraDays beyond the known baseline horizon using daily balance velocity,
 * empirical volatility (confidence cone), and realistic SME weekday cash rhythm.
 */
export function buildForwardForecast(
  baselineDays,
  transactions = [],
  extraDays = 14,
  dailyVolatilityMinor = 0,
) {
  if (!baselineDays || baselineDays.length === 0) {
    return { days: [], meanDailyMinor: 0 };
  }

  const deltas = [];
  for (let i = 1; i < baselineDays.length; i += 1) {
    deltas.push(baselineDays[i].balance_minor - baselineDays[i - 1].balance_minor);
  }

  const meanDailyMinor =
    deltas.length > 0 ? deltas.reduce((acc, v) => acc + v, 0) / deltas.length : 0;
  const stdDailyMinor = computeDailyStd(baselineDays, dailyVolatilityMinor);

  const lastDay = baselineDays[baselineDays.length - 1];
  const lastBalance = lastDay.balance_minor;
  const waveAmp = Math.max(stdDailyMinor * 1.05, Math.abs(meanDailyMinor) * 1.85, 18_000);
  const days = [];

  for (let k = 1; k <= extraDays; k += 1) {
    const iso = addDaysIso(lastDay.date, k);
    const trendBal = Math.round(lastBalance + meanDailyMinor * k);
    const spread = Math.round(
      Math.max(
        stdDailyMinor * Math.sqrt(k) * 0.72,
        Math.abs(meanDailyMinor) * k * 0.28,
        Math.abs(lastBalance) * 0.06,
        8_000,
      ),
    );
    const wobble = deterministicCashWave(iso, k - 1, extraDays, Math.min(waveAmp, spread * 0.88));
    const balance_minor = trendBal + wobble;
    days.push({
      date: iso,
      balance_minor,
      low_minor: trendBal - spread,
      high_minor: trendBal + spread,
    });
  }

  return { days, meanDailyMinor: Math.round(meanDailyMinor) };
}

/**
 * Project a pessimistic +extraDays future stress scenario starting from the last baseline day,
 * assuming inflows slow down (-inflowDropPct%) and expenses run higher (+expenseShockPct%).
 */
export function buildStressCurve(
  baselineDays,
  transactions = [],
  { extraDays = 14, inflowDropPct = 15, expenseShockPct = 10 } = {},
) {
  if (!baselineDays || baselineDays.length === 0) return [];

  const startDate = baselineDays[0].date;
  const lastDay = baselineDays[baselineDays.length - 1];
  const spanDays = Math.max(1, baselineDays.length - 1);
  const meanDailyMinor = (lastDay.balance_minor - baselineDays[0].balance_minor) / spanDays;

  let totalInflows = 0;
  let totalOutflows = 0;
  for (const t of transactions) {
    if (t.date < startDate || t.date > lastDay.date) continue;
    if (t.amount_minor > 0) totalInflows += t.amount_minor;
    else if (t.amount_minor < 0) totalOutflows += Math.abs(t.amount_minor);
  }

  const avgInPerDay = totalInflows / baselineDays.length;
  const avgOutPerDay = totalOutflows / baselineDays.length;
  const stressDailyDelta =
    avgInPerDay * (1 - inflowDropPct / 100) - avgOutPerDay * (1 + expenseShockPct / 100);

  // Keep stress strictly worse than the base trend so the scenario divergence is always clear.
  const minWorsening = Math.max(Math.abs(meanDailyMinor) * 0.25, 15_000);
  const dailyStress = Math.min(stressDailyDelta, meanDailyMinor - minWorsening);

  const days = [];
  for (let k = 1; k <= extraDays; k += 1) {
    days.push({
      date: addDaysIso(lastDay.date, k),
      balance_minor: Math.round(lastDay.balance_minor + dailyStress * k),
    });
  }
  return days;
}

/**
 * Combined stress case within the forecast window: receipts five days later and costs 10% higher.
 */
export function buildWindowStressCurve(baselineDays, transactions) {
  const firstDate = baselineDays[0].date;
  const lastDate = baselineDays[baselineDays.length - 1].date;
  const deltas = new Map();
  const addDelta = (date, delta) => deltas.set(date, (deltas.get(date) ?? 0) + delta);

  for (const { date, amount_minor } of transactions) {
    if (date < firstDate || date > lastDate) continue;
    if (amount_minor > 0) {
      addDelta(date, -amount_minor);
      addDelta(addDaysIso(date, 5), amount_minor);
    } else {
      addDelta(date, -Math.round(-amount_minor / 10));
    }
  }

  let cumulativeDelta = 0;
  return baselineDays.map(({ date, balance_minor }) => {
    cumulativeDelta += deltas.get(date) ?? 0;
    return { date, balance_minor: balance_minor + cumulativeDelta };
  });
}

/**
 * Wrap real backend +14d forecast days (from POST /api/forecast history mode)
 * with an empirical confidence cone driven by full-year historical daily volatility
 * (falling back to baseline window variance if full-year volatility isn't available yet).
 */
export function buildBackendForwardOverlay(
  baselineDays,
  forwardForecast,
  dailyVolatilityMinor = 0,
) {
  const rawDays = forwardForecast?.baseline?.days;
  if (!baselineDays?.length || !rawDays?.length) return null;

  const stdDaily = computeDailyStd(baselineDays, dailyVolatilityMinor);
  const lastBalance = baselineDays[baselineDays.length - 1].balance_minor;

  // Detect whether the backend continuation is a flat linear daily-average fallback
  // (which only occurs on short CSVs without multi-month recurring patterns).
  const fwdDeltas = [];
  let prevBal = lastBalance;
  for (const d of rawDays) {
    fwdDeltas.push(d.balance_minor - prevBal);
    prevBal = d.balance_minor;
  }
  const fwdMean = fwdDeltas.reduce((a, b) => a + b, 0) / Math.max(1, fwdDeltas.length);
  const fwdStd = Math.sqrt(
    fwdDeltas.reduce((acc, v) => acc + (v - fwdMean) ** 2, 0) / Math.max(1, fwdDeltas.length),
  );
  const isFlatLinearFallback = fwdStd < Math.max(Math.abs(fwdMean) * 0.2, 5_000);
  const waveAmp = Math.max(stdDaily * 1.05, Math.abs(fwdMean) * 1.85, 18_000);

  const days = rawDays.map((day, idx) => {
    const k = idx + 1;
    const stepDiff = Math.abs(day.balance_minor - lastBalance);
    const spread = Math.round(
      Math.max(
        stdDaily * Math.sqrt(k) * 0.62,
        stepDiff * 0.18,
        Math.abs(lastBalance) * 0.05,
        8_000,
      ),
    );
    const wobble = isFlatLinearFallback
      ? deterministicCashWave(day.date, idx, rawDays.length, Math.min(waveAmp, spread * 0.88))
      : 0;
    const balance_minor = day.balance_minor + wobble;
    return {
      date: day.date,
      balance_minor,
      low_minor: day.balance_minor - spread,
      high_minor: day.balance_minor + spread,
    };
  });

  return {
    days,
    transactions: forwardForecast.transactions || [],
  };
}

/**
 * Combined stress case across the active baseline window AND any +14d forward projection:
 * receipts arrive 5 days later and expenses are 10% higher, flowing continuously across the divider.
 */
export function buildContinuousStressCurve(
  baselineDays,
  baselineTransactions = [],
  forwardDays = null,
  forwardTransactions = [],
) {
  if (!baselineDays?.length) return [];
  const hasForward = Boolean(forwardDays?.length);
  const allDays = hasForward ? [...baselineDays, ...forwardDays] : baselineDays;
  const baseFirst = baselineDays[0].date;
  const baseLast = baselineDays[baselineDays.length - 1].date;
  const fwdFirst = hasForward ? forwardDays[0].date : null;
  const fwdLast = hasForward ? forwardDays[forwardDays.length - 1].date : null;

  const deltas = new Map();
  const addDelta = (date, delta) => deltas.set(date, (deltas.get(date) ?? 0) + delta);

  const applyTx = ({ date, amount_minor }) => {
    if (amount_minor > 0) {
      addDelta(date, -amount_minor);
      addDelta(addDaysIso(date, 5), amount_minor);
    } else if (amount_minor < 0) {
      addDelta(date, -Math.round(-amount_minor / 10));
    }
  };

  for (const tx of baselineTransactions) {
    if (tx.date >= baseFirst && tx.date <= baseLast) {
      applyTx(tx);
    }
  }

  let hasForwardTxs = false;
  if (hasForward) {
    for (const tx of forwardTransactions || []) {
      if (tx.date >= fwdFirst && tx.date <= fwdLast) {
        applyTx(tx);
        hasForwardTxs = true;
      }
    }
    // If forward projection is using client-side fallback without itemized forward txs,
    // carry a proportional 10% cost / 15% inflow stress slope smoothly across forwardDays.
    if (!hasForwardTxs) {
      let totalIn = 0;
      let totalOut = 0;
      for (const tx of baselineTransactions) {
        if (tx.date < baseFirst || tx.date > baseLast) continue;
        if (tx.amount_minor > 0) totalIn += tx.amount_minor;
        else if (tx.amount_minor < 0) totalOut += Math.abs(tx.amount_minor);
      }
      const dailyDrag = Math.round((totalIn * 0.15 + totalOut * 0.1) / baselineDays.length);
      if (dailyDrag > 0) {
        for (const fDay of forwardDays) {
          addDelta(fDay.date, -dailyDrag);
        }
      }
    }
  }

  let cumulativeDelta = 0;
  return allDays.map(({ date, balance_minor }) => {
    cumulativeDelta += deltas.get(date) ?? 0;
    return { date, balance_minor: balance_minor + cumulativeDelta };
  });
}

/**
 * Stress curve strictly over the projected future days (after the blue vertical divider):
 * receipts arrive 5 days later and expenses are 10% higher.
 */
export function buildProjectedStressCurve(
  projectedDays,
  projectedTransactions = [],
  referenceTransactions = [],
) {
  if (!projectedDays?.length) return [];
  const firstDate = projectedDays[0].date;
  const lastDate = projectedDays[projectedDays.length - 1].date;
  const deltas = new Map();
  const addDelta = (date, delta) => deltas.set(date, (deltas.get(date) ?? 0) + delta);

  let appliedAny = false;
  for (const { date, amount_minor } of projectedTransactions || []) {
    if (date < firstDate || date > lastDate) continue;
    if (amount_minor > 0) {
      addDelta(date, -amount_minor);
      addDelta(addDaysIso(date, 5), amount_minor);
      appliedAny = true;
    } else if (amount_minor < 0) {
      addDelta(date, -Math.round(-amount_minor / 10));
      appliedAny = true;
    }
  }

  if (!appliedAny) {
    let totalIn = 0;
    let totalOut = 0;
    for (const tx of referenceTransactions || []) {
      if (tx.amount_minor > 0) totalIn += tx.amount_minor;
      else if (tx.amount_minor < 0) totalOut += Math.abs(tx.amount_minor);
    }
    const dailyDrag = Math.max(
      Math.round((totalIn * 0.15 + totalOut * 0.1) / Math.max(1, projectedDays.length)),
      8_000,
    );
    for (const day of projectedDays) {
      addDelta(day.date, -dailyDrag);
    }
  }

  let cumulativeDelta = 0;
  return projectedDays.map(({ date, balance_minor }) => {
    cumulativeDelta += deltas.get(date) ?? 0;
    return { date, balance_minor: balance_minor + cumulativeDelta };
  });
}

/**
 * Project a baseline-window simulation overlay (What-If, Buy X, If paid earlier) strictly onto
 * the projected future days after the blue vertical divider by applying each day's cash delta.
 */
export function mapOverlayToProjectedDays(baselineDays, overlayDays, projectedDays) {
  if (!baselineDays?.length || !overlayDays?.length || !projectedDays?.length) return null;
  if (overlayDays.length !== baselineDays.length) return null;
  // If projectedDays already shares the exact dates with baselineDays (history mode), return overlayDays directly.
  if (projectedDays[0].date === baselineDays[0].date && projectedDays.length === baselineDays.length) {
    return overlayDays.map((d) => ({ date: d.date, balance_minor: d.balance_minor }));
  }
  return projectedDays.map((pDay, idx) => {
    const srcIdx = Math.min(idx, baselineDays.length - 1);
    const delta = overlayDays[srcIdx].balance_minor - baselineDays[srcIdx].balance_minor;
    return {
      date: pDay.date,
      balance_minor: pDay.balance_minor + delta,
    };
  });
}

/**
 * Extend a baseline-length overlay (If paid earlier or What-If) continuously across +14d forwardDays
 * by carrying forward its ending cash delta.
 */
export function extendOverlayAcrossFuture(baselineDays, overlayDays, forwardDays) {
  if (!baselineDays?.length || !overlayDays || overlayDays.length !== baselineDays.length) {
    return overlayDays;
  }
  if (!forwardDays?.length) return overlayDays;

  const endDelta =
    overlayDays[overlayDays.length - 1].balance_minor -
    baselineDays[baselineDays.length - 1].balance_minor;

  return [
    ...overlayDays,
    ...forwardDays.map((day) => ({
      date: day.date,
      balance_minor: day.balance_minor + endDelta,
    })),
  ];
}

/**
 * Deterministic single-transaction what-if or late-payment curve over baselineDays.
 */
export function buildWhatIfCurve(
  baselineDays,
  transactions = [],
  { transactionId, newAmountMinor = null, newDate = null, delayDays = 0 },
) {
  if (!baselineDays || baselineDays.length === 0 || !transactionId) return null;
  const tx = transactions.find((t) => t.id === transactionId);
  if (!tx) return null;

  const startDate = baselineDays[0].date;
  const oldOffset = diffDaysIso(startDate, tx.date);
  const newOffset = newDate ? diffDaysIso(startDate, newDate) : oldOffset + delayDays;
  const nextAmount =
    newAmountMinor !== null && newAmountMinor !== undefined ? newAmountMinor : tx.amount_minor;

  return baselineDays.map((day, idx) => {
    let delta = 0;
    if (0 <= oldOffset && oldOffset <= idx) delta -= tx.amount_minor;
    if (0 <= newOffset && newOffset <= idx) delta += nextAmount;
    return { date: day.date, balance_minor: day.balance_minor + delta };
  });
}
