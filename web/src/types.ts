// Mirrors backend/models.py. Amounts are integer grosz (1 PLN = 100).

export type Transaction = {
  id: string;
  date: string;
  amount_minor: number;
  label: string;
};

export type Deficit = {
  date: string;
  shortfall_minor: number;
};

export type DailyBalance = {
  date: string;
  balance_minor: number;
};

export type Projection = {
  days: DailyBalance[];
  first_deficit: Deficit | null;
};

export type Proposal = {
  limit_minor: number;
  first_shortfall: Deficit;
  deepest_shortfall: Deficit;
  relevant_transaction_ids: string[];
};

export type ForecastResponse = {
  transactions: Transaction[];
  baseline: Projection;
  scenario: Projection | null;
  /** Calculated by the backend. Null when the baseline never goes below zero. */
  proposal: Proposal | null;
};

export type AdviceResponse = {
  explanation: string;
  /** Null when there is no incoming payment after the gap to ask for. */
  email_draft: string | null;
  /** Served model name, or "demo sample" in demo mode. */
  model: string;
  latency_ms: number | null;
};

export type Decision = "approved" | "rejected" | null;

export type DecisionDay = {
  date: string;
  balance_minor: number;
  facility_used_minor: number;
  uncovered_minor: number;
};

/** The backend's simulation of the user's decision. Nothing is applied for or sent. */
export type DecisionResponse = {
  decision: Exclude<Decision, null>;
  simulated: true;
  limit_minor: number;
  days: DecisionDay[];
  largest_uncovered: Deficit | null;
};

export type OutcomeState =
  | { status: "idle" }
  | { status: "loading"; decision: Exclude<Decision, null> }
  | { status: "ready"; data: DecisionResponse }
  | { status: "error"; decision: Exclude<Decision, null>; message: string };

export type Move = {
  id: string;
  date: string;
};

export type Scenario = {
  projection: Projection;
  move: Move;
};

export type AdviceState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: AdviceResponse }
  | { status: "error"; message: string };
