export function formatCsvError(rawMessage) {
  const msg = String(rawMessage || "").trim();
  if (!msg) {
    return "We couldn't read this file. Upload a valid CSV export or try one of the built-in samples below.";
  }
  if (/must be the header id,date,amount_minor,label/i.test(msg)) {
    return "This CSV doesn't match the expected columns. Upload a bank CSV export (with Booking Date, Amount, Currency) or a CSV with header: id,date,amount_minor,label — or try one of the sample buttons below.";
  }
  if (/missing required columns/i.test(msg)) {
    return "This bank CSV doesn't have the required columns (Account Number, Booking Date, Value Date, Transaction Type, Payment Reference, Beneficiary/Payer, Amount, Currency). Export a fresh CSV from your bank or try one of the built-in samples below.";
  }
  if (/unsupported currency/i.test(msg)) {
    return `${msg} Right now EUR and CHF transactions are supported.`;
  }
  if (/Use 12000 EUR|Use the bundled transactions\.csv/i.test(msg)) {
    return "In local preview mode, custom comma CSVs aren't active yet — click 'Try Kernes demo (EUR)' or 'Try Pizzeria Amalfi sample' below to explore.";
  }
  if (/UTF-8/i.test(msg)) {
    return "This file isn't readable plain text (UTF-8 CSV). Export a fresh CSV from your bank or spreadsheet and try again.";
  }
  if (/larger than 1 MB/i.test(msg)) {
    return "This file is larger than 1 MB. Export a shorter date range as CSV and try again.";
  }
  return msg;
}

export async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail =
      typeof error.detail === "string"
        ? error.detail
        : error.detail?.map?.((issue) => issue.msg).filter(Boolean).join(" ") ||
          `Request failed (HTTP ${response.status}).`;
    const err = new Error(detail);
    err.status = response.status;
    throw err;
  }
  return response;
}

export async function resolveForecast({
  csvFile,
  openingBalanceMinor,
  startDate,
  moveTransactionId = null,
  moveToDate = null,
}) {
  const formData = new FormData();
  formData.set("file", csvFile, csvFile.name);
  formData.set("starting_balance_minor", String(openingBalanceMinor));
  formData.set("start_date", startDate);
  if (moveTransactionId && moveToDate) {
    formData.set("move_transaction_id", moveTransactionId);
    formData.set("move_to_date", moveToDate);
  }
  const response = await request("/api/forecast", { method: "POST", body: formData });
  return response.json();
}

async function post(path, body) {
  const response = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

/**
 * Build a strict 14-day { baseline, transactions } payload matching backend InsightRequest/AdviceRequest.
 */
export function buildInsightPayload(forecast) {
  const rawDays = forecast?.baseline?.days;
  if (!rawDays || rawDays.length < 14) return null;

  const days = rawDays.slice(0, 14).map(({ date, balance_minor }) => ({
    date,
    balance_minor: Math.trunc(Number(balance_minor)),
  }));
  const firstNeg = days.find((d) => d.balance_minor < 0);
  const first_deficit = firstNeg
    ? { date: firstNeg.date, shortfall_minor: -firstNeg.balance_minor }
    : null;

  const transactions = (forecast.transactions || [])
    .slice(0, 5000)
    .map(({ id, date, amount_minor, label }) => ({
      id: String(id).replace(/[\x00-\x1f\x7f-\x9f]/g, " ").slice(0, 64),
      date,
      amount_minor: Math.trunc(Number(amount_minor)),
      label: String(label || "Transaction").replace(/[\x00-\x1f\x7f-\x9f]/g, " ").slice(0, 200),
    }));

  if (transactions.length === 0) return null;

  return {
    baseline: { days, first_deficit },
    transactions,
  };
}

export function requestAdvice({ baseline, transactions }) {
  return post("/api/advice", { baseline, transactions });
}

export function requestDecision({ baseline, decision }) {
  return post("/api/decision", { baseline, decision });
}

export function requestAnomalies(payload) {
  return post("/api/detect-anomalies", payload);
}

export function requestCompareOptions(payload) {
  return post("/api/compare-options", payload);
}

export function requestCreditCheck(payload) {
  return post("/api/credit-check", payload);
}

export function requestStressTest(payload) {
  return post("/api/stress-test", payload);
}

export function requestAskCfo(payload, question) {
  return post("/api/ask-cfo", { ...payload, question });
}

export async function requestHealth() {
  const response = await request("/health");
  return response.json();
}

export function requestOptimizePayments(payload) {
  return post("/api/optimize-payments", payload);
}

export function requestPredictDelays(payload, clientDelays) {
  return post("/api/predict-delays", { ...payload, client_delays: clientDelays });
}

export function requestSendReminder({ to_email, subject, body }) {
  return post("/api/send-reminder", { to_email, subject, body });
}
