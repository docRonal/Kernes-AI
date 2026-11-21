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

/**
 * Project +extraDays beyond the known baseline horizon using daily balance velocity
 * and empirical volatility (confidence cone).
 */
export function buildForwardForecast(baselineDays, transactions = [], extraDays = 7) {
  if (!baselineDays || baselineDays.length === 0) {
    return { days: [], meanDailyMinor: 0 };
  }

  const deltas = [];
  for (let i = 1; i < baselineDays.length; i += 1) {
    deltas.push(baselineDays[i].balance_minor - baselineDays[i - 1].balance_minor);
  }

  const meanDailyMinor =
    deltas.length > 0 ? deltas.reduce((acc, v) => acc + v, 0) / deltas.length : 0;
  const variance =
    deltas.length > 0
      ? deltas.reduce((acc, v) => acc + (v - meanDailyMinor) ** 2, 0) / deltas.length
      : 0;
  const stdDailyMinor = Math.sqrt(variance);

  const lastDay = baselineDays[baselineDays.length - 1];
  const lastBalance = lastDay.balance_minor;
  const days = [];

  for (let k = 1; k <= extraDays; k += 1) {
    const balance_minor = Math.round(lastBalance + meanDailyMinor * k);
    const spread = Math.round(
      Math.max(
        stdDailyMinor * Math.sqrt(k) * 0.65,
        Math.abs(meanDailyMinor) * k * 0.25,
        50_000,
      ),
    );
    days.push({
      date: addDaysIso(lastDay.date, k),
      balance_minor,
      low_minor: balance_minor - spread,
      high_minor: balance_minor + spread,
    });
  }

  return { days, meanDailyMinor: Math.round(meanDailyMinor) };
}

/**
 * Deterministic combined stress-test curve (inflows delayed + outflows costlier),
 * matching backend/insights.py::stress_test integer rounding.
 */
export function buildStressCurve(
  baselineDays,
  transactions = [],
  { delayDays = 5, expenseShockPct = 10 } = {},
) {
  if (!baselineDays || baselineDays.length === 0) return [];
  const startDate = baselineDays[0].date;
  const endDate = baselineDays[baselineDays.length - 1].date;
  const changes = [];

  for (const t of transactions) {
    if (t.date < startDate || t.date > endDate) continue;
    const at = diffDaysIso(startDate, t.date);
    if (t.amount_minor > 0) {
      changes.push([at, t.amount_minor, at + delayDays, t.amount_minor]);
    } else if (t.amount_minor < 0) {
      const extra = Math.floor((Math.abs(t.amount_minor) * expenseShockPct + 50) / 100);
      changes.push([at, t.amount_minor, at, t.amount_minor - extra]);
    }
  }

  return baselineDays.map((day, idx) => {
    let delta = 0;
    for (const [oldOff, oldAmt, newOff, newAmt] of changes) {
      if (0 <= oldOff && oldOff <= idx) delta -= oldAmt;
      if (0 <= newOff && newOff <= idx) delta += newAmt;
    }
    return { date: day.date, balance_minor: day.balance_minor + delta };
  });
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
