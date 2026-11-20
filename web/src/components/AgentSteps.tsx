import { AnimatePresence, motion } from "motion/react";
import type { Facts } from "../analysis";
import { money, plural, shortDate } from "../format";
import type { Decision, ForecastResponse } from "../types";

type Tone = "done" | "alert" | "wait" | "idle" | "scn";
type Step = { title: string; tag: [Tone, string]; body: string };

type Props = {
  forecast: ForecastResponse;
  facts: Facts;
  limitMinor: number | null;
  decision: Decision;
  openingMinor: number;
};

/**
 * The challenge asks teams to separate what the agent analyses on its own,
 * what it recommends, what needs approval and whether execution is real.
 * These four columns answer exactly that, live.
 */
export function AgentSteps({ forecast, facts, limitMinor, decision, openingMinor }: Props) {
  const days = forecast.baseline.days;

  const steps: Step[] = [
    {
      title: "Checks on its own",
      tag: ["done", "Done"],
      body: `Read ${plural(forecast.transactions.length, "payment")} and worked out 14 end-of-day balances, starting from ${money(openingMinor)} on ${shortDate(days[0].date)}.`,
    },
    limitMinor && facts.deepest
      ? {
          title: "Recommends",
          tag: ["alert", "1 proposal"],
          body: `A credit line of ${money(limitMinor)}, enough for the deepest gap on ${shortDate(facts.deepest.date)}. Or ask a client to pay earlier.`,
        }
      : { title: "Recommends", tag: ["done", "Nothing to fix"], body: "No action. The balance never drops below zero." },
    !limitMinor
      ? { title: "Asks for your OK", tag: ["idle", "Not needed"], body: "There is nothing to approve." }
      : decision === null
        ? { title: "Asks for your OK", tag: ["wait", "Waiting for you"], body: "Nothing happens until you press Approve or Reject." }
        : decision === "approved"
          ? { title: "Asks for your OK", tag: ["done", "You approved"], body: "You approved the credit line." }
          : { title: "Asks for your OK", tag: ["alert", "You rejected"], body: "You declined the credit line." },
    {
      title: "Executes",
      tag: ["scn", "Simulation only"],
      body:
        decision === null
          ? "Only ever as a simulation. It never applies for credit, moves money or sends an email."
          : "Ran as a simulation. No application was sent and no money moved.",
    },
  ];

  return (
    <section className="steps-block" aria-labelledby="steps-title">
      <p id="steps-title" className="eyebrow">
        What the agent did, and what it left to you
      </p>
      <ol className="steps">
        {steps.map((step, index) => (
          <motion.li
            key={step.title}
            className="step"
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.5, delay: index * 0.08 }}
          >
            <div className="step-top">
              <span className="step-num">0{index + 1}</span>
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={step.tag[1]}
                  className={`tag tone-${step.tag[0]}`}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  transition={{ duration: 0.18 }}
                >
                  {step.tag[1]}
                </motion.span>
              </AnimatePresence>
            </div>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
