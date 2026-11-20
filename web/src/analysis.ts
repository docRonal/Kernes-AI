import type { DailyBalance, Decision, Deficit, ForecastResponse, Projection, Proposal, Transaction } from "./types";

export const byDate = (a: { date: string }, b: { date: string }) => a.date.localeCompare(b.date);

export type Facts = {
  first: Deficit | null;
  firstIndex: number;
  /** Lowest negative balance; the earliest day wins a tie. */
  deepest: DailyBalance | null;
  deepestIndex: number;
  lowest: DailyBalance;
  /** First day back at or above zero after the first deficit. */
  recovery: DailyBalance | null;
  daysBelow: number;
  lastRed: DailyBalance | null;
};

/** Reads facts off a projection the backend already calculated. No money maths happens here. */
export function analyse(projection: Projection): Facts {
  const { days, first_deficit: first } = projection;
  const firstIndex = first ? days.findIndex((day) => day.date === first.date) : -1;

  let deepestIndex = -1;
  days.forEach((day, index) => {
    if (day.balance_minor < 0 && (deepestIndex < 0 || day.balance_minor < days[deepestIndex].balance_minor)) {
      deepestIndex = index;
    }
  });

  const recoveryIndex = firstIndex < 0 ? -1 : days.findIndex((day, index) => index > firstIndex && day.balance_minor >= 0);
  const endOfRed = recoveryIndex >= 0 ? recoveryIndex : days.length;

  return {
    first,
    firstIndex,
    deepest: deepestIndex >= 0 ? days[deepestIndex] : null,
    deepestIndex,
    lowest: days.reduce((low, day) => (day.balance_minor < low.balance_minor ? day : low)),
    recovery: recoveryIndex >= 0 ? days[recoveryIndex] : null,
    daysBelow: firstIndex < 0 ? 0 : endOfRed - firstIndex,
    lastRed: firstIndex < 0 ? null : days[endOfRed - 1],
  };
}

/**
 * The backend owns the proposal. Until the contract PR adds `proposal` to the
 * forecast response, preview the agreed rule max(0, -min(balances)) so the
 * flow can be demoed. Remove the fallback once the backend sends it.
 */
export function proposalFor(forecast: ForecastResponse): Proposal | null {
  if (forecast.proposal !== undefined) return forecast.proposal;
  const lowest = Math.min(...forecast.baseline.days.map((day) => day.balance_minor));
  return lowest < 0 ? { limit_minor: -lowest } : null;
}

export type Simulation = {
  gaps: { date: string; uncovered_minor: number }[];
  worst: { date: string; uncovered_minor: number };
};

/** Same placeholder status as `proposalFor`: replace with the backend's decision response. */
export function simulate(days: DailyBalance[], limitMinor: number, decision: Exclude<Decision, null>): Simulation {
  const available = decision === "approved" ? limitMinor : 0;
  const gaps = days.map((day) => ({ date: day.date, uncovered_minor: Math.max(0, -day.balance_minor - available) }));
  const worst = gaps.reduce((max, gap) => (gap.uncovered_minor > max.uncovered_minor ? gap : max), gaps[0]);
  return { gaps, worst };
}

export function groupByDate(transactions: Transaction[]): Map<string, Transaction[]> {
  const groups = new Map<string, Transaction[]>();
  for (const transaction of [...transactions].sort(byDate)) {
    groups.set(transaction.date, [...(groups.get(transaction.date) ?? []), transaction]);
  }
  return groups;
}

/** Round axis ticks that always include zero, with a little headroom. */
export function niceTicks(min: number, max: number, count: number): number[] {
  const low = Math.min(0, min);
  const high = Math.max(0, max);
  const span = high - low || 100_000;
  const paddedLow = low < 0 ? low - span * 0.06 : low;
  const paddedHigh = high > 0 ? high + span * 0.06 : paddedLow === 0 ? span : high;
  const raw = (paddedHigh - paddedLow) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const step = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
  const start = Math.floor(paddedLow / step) * step;
  const end = Math.ceil(paddedHigh / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= end + step / 2; value += step) ticks.push(Math.round(value));
  return ticks;
}
