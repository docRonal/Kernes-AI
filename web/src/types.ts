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
};

export type ForecastResponse = {
  transactions: Transaction[];
  baseline: Projection;
  scenario: Projection | null;
  /** Planned in the contract PR. The UI previews the agreed rule until the backend sends it. */
  proposal?: Proposal | null;
};

export type AdviceResponse = {
  explanation: string;
  email_draft: string;
};

export type Decision = "approved" | "rejected" | null;

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
