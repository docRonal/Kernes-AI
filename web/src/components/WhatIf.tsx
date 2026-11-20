import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, Copy } from "lucide-react";
import { byDate, type Facts } from "../analysis";
import { errorMessage } from "../api";
import { addDays, longDate, money, shortDate } from "../format";
import type { AdviceState, ForecastResponse, Move, Scenario } from "../types";
import { Figure } from "./Figure";

type Props = {
  forecast: ForecastResponse;
  facts: Facts;
  scenario: Scenario | null;
  advice: AdviceState;
  onCompare: (move: Move) => Promise<void>;
  onClear: () => void;
};

export function WhatIf({ forecast, facts, scenario, advice, onCompare, onClear }: Props) {
  const days = forecast.baseline.days;
  const incoming = useMemo(
    () => forecast.transactions.filter((t) => t.amount_minor > 0).sort(byDate),
    [forecast],
  );
  // Suggest the payment that lands after the gap starts, moved to the day before it.
  const suggested = (facts.first && incoming.find((t) => t.date > facts.first!.date)) ?? incoming[0];
  const suggestedDate = facts.first ? addDays(facts.first.date, -1) : days[0].date;

  const [moveId, setMoveId] = useState(suggested?.id ?? "");
  const [moveDate, setMoveDate] = useState(suggestedDate < days[0].date ? days[0].date : suggestedDate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onCompare({ id: moveId, date: moveDate });
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  const keyDate = facts.first?.date ?? scenario?.move.date;
  const index = keyDate ? days.findIndex((day) => day.date === keyDate) : -1;
  const before = index >= 0 ? days[index].balance_minor : null;
  const after = index >= 0 && scenario ? scenario.projection.days[index].balance_minor : null;
  const movedLabel = scenario ? forecast.transactions.find((t) => t.id === scenario.move.id)?.label : undefined;

  return (
    <section id="whatif" className="whatif" aria-labelledby="whatif-title">
      <div className="whatif-intro">
        <p className="eyebrow">Or try this instead</p>
        <h3 id="whatif-title">What if a client paid earlier?</h3>
        <p>Pick an incoming payment and a new date. The original forecast and the proposal stay as they are, so you can compare.</p>
      </div>

      <div className="whatif-work">
        {incoming.length === 0 ? (
          <p className="muted">There are no incoming payments to move.</p>
        ) : (
          <form className="scenario-form" onSubmit={submit}>
            <p className="sentence">
              If{" "}
              <label className="inline select">
                <span className="sr-only">Incoming payment</span>
                <select value={moveId} onChange={(event) => setMoveId(event.target.value)} required>
                  {incoming.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label} · {money(t.amount_minor)}
                    </option>
                  ))}
                </select>
              </label>{" "}
              arrived on{" "}
              <label className="inline">
                <span className="sr-only">New payment date</span>
                <input
                  type="date"
                  value={moveDate}
                  min={days[0].date}
                  max={days[days.length - 1].date}
                  onChange={(event) => setMoveDate(event.target.value)}
                  required
                />
              </label>
            </p>
            <button type="submit" className="btn primary" disabled={busy || !moveId || !moveDate} aria-busy={busy}>
              {busy ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Comparing…
                </>
              ) : (
                <>
                  Compare
                  <ArrowRight className="arrow" size={18} aria-hidden="true" />
                </>
              )}
            </button>
          </form>
        )}

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <AnimatePresence initial={false}>
          {scenario && before !== null && after !== null && keyDate && (
            <motion.div
              key={`${scenario.move.id}-${scenario.move.date}`}
              className="compare"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <p className="compare-date">{longDate(keyDate)} · end of day</p>
              <div className="compare-figures">
                <div className="from">
                  <span className="compare-key">As planned</span>
                  <Figure minor={before} tone={before < 0 ? "neg" : undefined} />
                </div>
                <ArrowRight className="compare-arrow" aria-hidden="true" strokeWidth={1.5} />
                <div className="to">
                  <span className="compare-key">If paid {shortDate(scenario.move.date)}</span>
                  <Figure minor={after} tone={after < 0 ? "neg" : "scn"} count from={before} />
                </div>
              </div>
              <p className="compare-caption">
                {scenario.projection.first_deficit
                  ? `Still short: ${money(-scenario.projection.first_deficit.shortfall_minor)} on ${shortDate(scenario.projection.first_deficit.date)}.`
                  : `With ${movedLabel ?? "the payment"} on ${shortDate(scenario.move.date)} you stay above zero for all 14 days.`}
              </p>
              <button type="button" className="link-btn" onClick={onClear}>
                Clear the comparison
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {forecast.baseline.first_deficit && <Reminder advice={advice} />}
    </section>
  );
}

function Reminder({ advice }: { advice: AdviceState }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (advice.status === "ready") setDraft((current) => current || (advice.data.email_draft ?? ""));
  }, [advice]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft);
    } catch {
      const area = document.getElementById("draft") as HTMLTextAreaElement | null;
      area?.select();
      document.execCommand("copy");
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  const ready = advice.status === "ready" && advice.data.email_draft !== null;

  return (
    <div className="reminder">
      <div>
        <p className="eyebrow">Ask for the money sooner</p>
        <p className="muted">A short, polite reminder you can edit and send yourself.</p>
      </div>
      <div>
        {!open && (
          <button
            type="button"
            className="btn ghost"
            onClick={() => setOpen(true)}
            disabled={!ready}
            aria-expanded={open}
            aria-controls="draft"
          >
            Draft a payment reminder
            <ArrowRight className="arrow" size={18} aria-hidden="true" />
          </button>
        )}
        {!ready && !open && (
          <p className="muted small">
            {advice.status === "loading"
              ? "Preparing the draft…"
              : advice.status === "error"
                ? "The draft comes with the AI explanation, which is unavailable right now."
                : advice.status === "ready"
                  ? "No client payment arrives after the gap, so there is nothing to ask for sooner."
                  : null}
          </p>
        )}
        <AnimatePresence>
          {open && (
            <motion.div
              className="draft"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <label htmlFor="draft" className="sr-only">
                Reminder text
              </label>
              <textarea id="draft" rows={6} value={draft} onChange={(event) => setDraft(event.target.value)} />
              <div className="draft-actions">
                <button type="button" className="btn primary small" onClick={copy}>
                  {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
                  {copied ? "Copied" : "Copy text"}
                </button>
                <span className="muted small">Nothing is emailed. You send it yourself.</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
