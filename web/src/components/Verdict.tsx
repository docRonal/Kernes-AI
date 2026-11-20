import { motion } from "motion/react";
import { byDate, type Facts } from "../analysis";
import { listLabels, longDate, money, plural, shortDate } from "../format";
import type { ForecastResponse } from "../types";
import { Figure } from "./Figure";

export function Verdict({ forecast, facts }: { forecast: ForecastResponse; facts: Facts }) {
  const { first } = facts;

  let sub: string;
  if (first) {
    const sentences: string[] = [];
    const dueThatDay = forecast.transactions.filter((t) => t.date === first.date && t.amount_minor < 0);
    const nextIncoming = forecast.transactions.filter((t) => t.amount_minor > 0 && t.date > first.date).sort(byDate)[0];
    if (dueThatDay.length) {
      const total = dueThatDay.reduce((sum, t) => sum + t.amount_minor, 0);
      const verb = dueThatDay.length > 1 ? "are" : "is";
      const late = nextIncoming
        ? `, but ${nextIncoming.label} (${money(nextIncoming.amount_minor, true)}) only arrives on ${shortDate(nextIncoming.date)}`
        : "";
      sentences.push(`${listLabels(dueThatDay.map((t) => t.label))} (${money(total)}) ${verb} due that day${late}.`);
    }
    sentences.push(
      facts.recovery
        ? `You stay below zero for ${plural(facts.daysBelow, "day")}, until ${shortDate(facts.recovery.date)}.`
        : "The balance doesn't recover within these 14 days.",
    );
    if (facts.deepest && facts.deepest.date !== first.date) {
      sentences.push(`The lowest point is ${money(facts.deepest.balance_minor)} on ${shortDate(facts.deepest.date)}.`);
    }
    sub = sentences.join(" ");
  } else {
    sub = `Your lowest balance is ${money(facts.lowest.balance_minor)} on ${shortDate(facts.lowest.date)}. Nothing needs your approval.`;
  }

  return (
    <motion.div
      className="verdict"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <p className={first ? "chip tone-alert" : "chip tone-ok"}>{first ? "Action needed" : "All clear"}</p>
      <h2 id="verdict-title">
        {first ? (
          <>
            On <em>{longDate(first.date)}</em> your account goes{" "}
            <Figure minor={first.shortfall_minor} tone="neg" count /> into the red.
          </>
        ) : (
          <>
            You stay above zero for the next <em>fourteen days</em>.
          </>
        )}
      </h2>
      <p className="verdict-sub">{sub}</p>
    </motion.div>
  );
}
