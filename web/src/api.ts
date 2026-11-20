import type { AdviceResponse, ForecastResponse, Move } from "./types";

export type ForecastInputs = {
  file: File;
  startingMinor: string;
  startDate: string;
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function detailOf(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean);
    return messages.length ? messages.join(" ") : null;
  }
  return null;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("Can't reach the server. Check the connection and try again.");
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new Error(detailOf(body) ?? `The request failed (HTTP ${response.status}).`);
  }
  return response;
}

let sample: Promise<File> | null = null;

export function loadSampleFile(): Promise<File> {
  sample ??= request("/demo/transactions.csv").then(
    async (response) => new File([await response.blob()], "transactions.csv", { type: "text/csv" }),
  );
  sample.catch(() => {
    sample = null;
  });
  return sample;
}

export async function fetchForecast(inputs: ForecastInputs, move?: Move): Promise<ForecastResponse> {
  const body = new FormData();
  body.set("file", inputs.file, inputs.file.name || "transactions.csv");
  body.set("starting_balance_minor", inputs.startingMinor);
  body.set("start_date", inputs.startDate);
  if (move) {
    body.set("move_transaction_id", move.id);
    body.set("move_to_date", move.date);
  }
  const response = await request("/api/forecast", { method: "POST", body });
  return (await response.json()) as ForecastResponse;
}

export async function fetchAdvice(forecast: ForecastResponse): Promise<AdviceResponse> {
  const response = await request("/api/advice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      first_deficit: forecast.baseline.first_deficit,
      transactions: forecast.transactions,
    }),
  });
  return (await response.json()) as AdviceResponse;
}
