import { buildForecastFromRedHat } from "../parser.js";

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
  parsedCsv,
  openingBalanceMinor,
  startDate,
  horizonDays,
  moveTransactionId = null,
  moveToDate = null,
}) {
  // Bank statements are analyzed locally in EUR, including the longer horizons.
  if (parsedCsv) {
    return buildForecastFromRedHat({
      parsed: parsedCsv,
      startingBalanceMinor: openingBalanceMinor,
      startDate,
      horizonDays,
      moveTransactionId,
      moveToDate,
    });
  }

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
