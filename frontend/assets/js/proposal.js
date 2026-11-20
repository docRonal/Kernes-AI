export function groupTransactionsByDate(transactions) {
  const map = new Map();
  for (const tx of transactions) {
    const list = map.get(tx.date) || [];
    list.push(tx);
    map.set(tx.date, list);
  }
  return map;
}

export function computeProposal(forecastData) {
  const baseline = forecastData.baseline;
  const firstDeficit = baseline.first_deficit;
  if (!firstDeficit) return null;

  let minBalance = 0;
  let peakDate = firstDeficit.date;
  for (const day of baseline.days) {
    if (day.balance_minor < minBalance) {
      minBalance = day.balance_minor;
      peakDate = day.date;
    }
  }

  const backendProposal = forecastData.credit_proposal || forecastData.proposal || null;
  const peakShortfallMinor =
    backendProposal?.deepest_deficit?.shortfall_minor ??
    backendProposal?.peak_shortfall_minor ??
    Math.max(0, -minBalance);
  const peakShortfallDate =
    backendProposal?.deepest_deficit?.date ??
    backendProposal?.peak_shortfall_date ??
    peakDate;
  const recommendedLimitMinor =
    backendProposal?.recommended_limit_minor ??
    backendProposal?.limit_minor ??
    peakShortfallMinor;

  const startDate = baseline.days[0]?.date;
  const endDate = baseline.days[baseline.days.length - 1]?.date;
  const inWindow = forecastData.transactions.filter(
    (tx) => (!startDate || tx.date >= startDate) && (!endDate || tx.date <= endDate),
  );

  // Highlight largest outflows/inflows in window (up to 6 items)
  const keyTxs = [...inWindow]
    .sort((a, b) => Math.abs(b.amount_minor) - Math.abs(a.amount_minor))
    .slice(0, 6)
    .sort((a, b) => a.date.localeCompare(b.date));

  return {
    recommendedLimitMinor,
    firstDeficit,
    peakDeficit: {
      date: peakShortfallDate,
      shortfall_minor: peakShortfallMinor,
    },
    relevantTransactions: keyTxs,
  };
}
