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
    throw new Error(detail);
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

export function requestAdvice({ baseline, transactions }) {
  return post("/api/advice", { baseline, transactions });
}

export function requestDecision({ baseline, decision }) {
  return post("/api/decision", { baseline, decision });
}
