import { buildForecastFromRedHat } from "../parser.js";
import { AMALFI_SAMPLE_FILENAME } from "../sample-amalfi.js";

export async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail =
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (HTTP ${response.status}).`;
    const err = new Error(detail);
    err.status = response.status;
    throw err;
  }
  return response;
}

export async function resolveForecast({
  csvFile,
  parsedCsv,
  openingBalanceMinor,
  startDate,
  horizonDays,
  moveTransactionId = null,
  moveToDate = null,
}) {
  const formData = new FormData();
  formData.set("file", csvFile, csvFile.name || AMALFI_SAMPLE_FILENAME);
  formData.set("starting_balance_minor", String(openingBalanceMinor));
  formData.set("start_date", startDate);
  if (moveTransactionId && moveToDate) {
    formData.set("move_transaction_id", moveTransactionId);
    formData.set("move_to_date", moveToDate);
  }

  // Prefer backend /api/forecast; fall back to local Red Hat CSV projection if
  // the backend is still in demo mode or hasn't switched to the Red Hat schema yet.
  try {
    const response = await request("/api/forecast", { method: "POST", body: formData });
    return await response.json();
  } catch (error) {
    if (error.status === 422 || error.status === 503) {
      return buildForecastFromRedHat({
        parsed: parsedCsv,
        startingBalanceMinor: openingBalanceMinor,
        startDate,
        horizonDays,
        moveTransactionId,
        moveToDate,
      });
    }
    throw error;
  }
}

export async function requestAdvice({ firstDeficit, transactions }) {
  const compactTxs = transactions.map(({ id, date, amount_minor, label }) => ({
    id,
    date,
    amount_minor,
    label,
  }));

  const response = await request("/api/advice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      first_deficit: firstDeficit,
      transactions: compactTxs,
    }),
  });
  return response.json();
}
