import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, RotateCcw, X } from "lucide-react";
import { byDate, simulate, type Facts } from "../analysis";
import { money, plural, shortDate } from "../format";
import type { AdviceState, Decision, ForecastResponse } from "../types";
import { Figure } from "./Figure";

type Props = {
  forecast: ForecastResponse;
  facts: Facts;
  limitMinor: number;
  advice: AdviceState;
  decision: Decision;
  onDecide: (decision: Decision) => void;
  onRetryAdvice: () => void;
};

const rise = {
  initial: { opacity: 0, y: 18 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.6, ease: [0.2, 0.8, 0.2, 1] },
} as const;

export function Proposal({ forecast, facts, limitMinor, advice, decision, onDecide, onRetryAdvice }: Props) {
  const facts4 = [
    facts.first && { term: "First day in the red", value: money(-facts.first.shortfall_minor), note: shortDate(facts.first.date) },
    facts.deepest && { term: "Deepest point", value: money(facts.deepest.balance_minor), note: shortDate(facts.deepest.date) },
    {
      term: "Days below zero",
      value: String(facts.daysBelow),
      note: facts.recovery ? `Back above zero on ${shortDate(facts.recovery.date)}` : "No recovery within 14 days",
    },
    { term: "Credit line", value: money(limitMinor), note: "Sized to the deepest gap" },
  ].filter((item): item is { term: string; value: string; note: string } => Boolean(item));

  return (
    <section className="proposal" aria-labelledby="proposal-title">
      <div className="proposal-main">
        <motion.div {...rise}>
          <p className="eyebrow">The agent recommends</p>
          <h3 id="proposal-title">
            A credit line of <Figure minor={limitMinor} /> covers the gap.
          </h3>
        </motion.div>

        <motion.dl className="facts" {...rise}>
          {facts4.map((item) => (
            <div key={item.term}>
              <dt>{item.term}</dt>
              <dd>
                {item.value}
                <small>{item.note}</small>
              </dd>
            </div>
          ))}
        </motion.dl>

        <Why advice={advice} onRetry={onRetryAdvice} />
      </div>

      <aside className="side">
        <Ledger forecast={forecast} facts={facts} />
        <DecisionPanel forecast={forecast} facts={facts} limitMinor={limitMinor} decision={decision} onDecide={onDecide} />
      </aside>
    </section>
  );
}

function Why({ advice, onRetry }: { advice: AdviceState; onRetry: () => void }) {
  return (
    <div className="why" aria-live="polite">
      <p className="eyebrow">Why, in plain words</p>
      <AnimatePresence mode="wait" initial={false}>
        {advice.status === "loading" && (
          <motion.div key="loading" className="skeleton" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <span />
            <span />
            <span />
            <span className="sr-only">Writing the explanation…</span>
          </motion.div>
        )}
        {advice.status === "ready" && (
          <motion.div key="ready" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <p className="why-text">{advice.data.explanation}</p>
            <p className="why-meta">Explained by the AI model · the amounts come from the calculation, not from the model</p>
          </motion.div>
        )}
        {advice.status === "error" && (
          <motion.div key="error" className="alert soft" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <p>
              The explanation isn't available right now ({advice.message}). The figures and the proposal are still
              correct.
            </p>
            <button type="button" className="btn ghost small" onClick={onRetry}>
              <RotateCcw size={16} aria-hidden="true" />
              Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Ledger({ forecast, facts }: { forecast: ForecastResponse; facts: Facts }) {
  const rows = [...forecast.transactions].sort(byDate);
  return (
    <motion.div className="ledger" {...rise}>
      <p className="eyebrow">Payments behind this</p>
      <ul>
        {rows.map((t) => {
          let note: string | null = null;
          if (facts.first && t.amount_minor < 0 && t.date === facts.first.date) note = "Pushes the balance below zero";
          else if (facts.first && t.amount_minor > 0 && t.date > facts.first.date) {
            note = facts.recovery?.date === t.date ? "Arrives after the gap and brings you back up" : "Arrives after the gap starts";
          }
          return (
            <li key={t.id} className={note ? "flag" : undefined}>
              <span className="tx-date">{shortDate(t.date)}</span>
              <span className="tx-main">
                <span className="tx-label">{t.label}</span>
                <span className="tx-id">{t.id}</span>
              </span>
              <span className={`tx-amount ${t.amount_minor < 0 ? "out" : "in"}`}>{money(t.amount_minor, true)}</span>
              {note && <span className="tx-note">{note}</span>}
            </li>
          );
        })}
      </ul>
    </motion.div>
  );
}

function DecisionPanel({
  forecast,
  facts,
  limitMinor,
  decision,
  onDecide,
}: Pick<Props, "forecast" | "facts" | "limitMinor" | "decision" | "onDecide">) {
  const outcome = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (decision) outcome.current?.focus({ preventScroll: true });
  }, [decision]);

  const deepestGap = facts.deepest ? -facts.deepest.balance_minor : 0;
  const result = decision ? simulate(forecast.baseline.days, limitMinor, decision) : null;
  const range =
    facts.first && facts.lastRed
      ? facts.first.date === facts.lastRed.date
        ? shortDate(facts.first.date)
        : `${shortDate(facts.first.date)} to ${shortDate(facts.lastRed.date)}`
      : "";

  return (
    <AnimatePresence mode="wait" initial={false}>
      {decision === null || !result ? (
        <motion.div
          key="ask"
          className="panel"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.25 }}
        >
          <p className="panel-title">Your call</p>
          <p>Approve to see what the credit line would do. It is a simulation: nothing is applied for and no money moves.</p>
          <div className="decide">
            <button type="button" className="btn primary block" onClick={() => onDecide("approved")}>
              <span>
                Approve <small>simulation</small>
              </span>
              <Check size={20} aria-hidden="true" />
            </button>
            <button type="button" className="btn ghost block" onClick={() => onDecide("rejected")}>
              <span>
                Reject <small>simulation</small>
              </span>
              <X size={20} aria-hidden="true" />
            </button>
          </div>
        </motion.div>
      ) : (
        <motion.div
          key={decision}
          ref={outcome}
          tabIndex={-1}
          className={`panel outcome ${decision}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.25 }}
        >
          <p className="outcome-status">
            {decision === "approved" ? <Check size={16} aria-hidden="true" /> : <X size={16} aria-hidden="true" />}
            {decision === "approved" ? "Approved" : "Rejected"} · simulated
          </p>
          <p className="outcome-label">Still uncovered on the worst day</p>
          <p className="outcome-figure">
            <Figure
              minor={result.worst.uncovered_minor}
              tone={result.worst.uncovered_minor > 0 ? "neg" : "ok"}
              count
              from={deepestGap}
            />
          </p>
          <p>
            {decision === "approved" ? (
              result.worst.uncovered_minor === 0 ? (
                <>
                  The credit line covers all {plural(facts.daysBelow, "day")} below zero ({range}). The forecast itself
                  doesn't change.
                </>
              ) : (
                <>
                  The credit line isn't enough: {money(result.worst.uncovered_minor)} is still short on{" "}
                  {shortDate(result.worst.date)}.
                </>
              )
            ) : (
              <>
                Without the credit line, {money(result.worst.uncovered_minor)} stays uncovered on{" "}
                {shortDate(result.worst.date)}. Moving a client payment earlier might help. <a href="#whatif">Try it below</a>.
              </>
            )}
          </p>
          <p className="fineprint">No application, transfer or message was sent.</p>
          <button type="button" className="btn ghost small" onClick={() => onDecide(null)}>
            <RotateCcw size={16} aria-hidden="true" />
            Decide again
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
