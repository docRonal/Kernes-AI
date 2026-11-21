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
export function buildForwardForecast(baselineDays, transactions = [], extraDays = 14) {
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
