export function groupTransactionsByDate(transactions) {
  const map = new Map();
  for (const tx of transactions) {
    const list = map.get(tx.date) || [];
    list.push(tx);
    map.set(tx.date, list);
  }
  return map;
}

/**
 * Read the server-supplied proposal without recalculating credit limits in the browser.
 */
export function readProposal(forecastData) {
  const raw = forecastData?.proposal;
  if (!raw) return null;

  const byId = new Map((forecastData.transactions || []).map((tx) => [tx.id, tx]));
  const relevantTransactions = (raw.relevant_transaction_ids || [])
    .map((id) => byId.get(id))
    .filter(Boolean)
    .sort((a, b) => Math.abs(b.amount_minor) - Math.abs(a.amount_minor))
    .slice(0, 6)
    .sort((a, b) => a.date.localeCompare(b.date));

  return {
    recommendedLimitMinor: raw.limit_minor,
    firstDeficit: raw.first_shortfall,
    peakDeficit: raw.deepest_shortfall,
    relevantTransactions,
  };
}
