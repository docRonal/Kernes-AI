import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MotionConfig } from "motion/react";
import { analyse } from "./analysis";
import { errorMessage, fetchAdvice, fetchDecision, fetchForecast, loadSampleFile, type ForecastInputs } from "./api";
import { AgentSteps } from "./components/AgentSteps";
import { ChartBlock } from "./components/CashChart";
import { Footer, TopBar } from "./components/Chrome";
import { Hero, type SetupValues } from "./components/Hero";
import { Proposal } from "./components/Proposal";
import { Verdict } from "./components/Verdict";
import { WhatIf } from "./components/WhatIf";
import type { AdviceState, Decision, ForecastResponse, Move, OutcomeState, Scenario } from "./types";

type Baseline = { forecast: ForecastResponse; inputs: ForecastInputs; run: number };

export function App() {
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [advice, setAdvice] = useState<AdviceState>({ status: "idle" });
  const [outcome, setOutcome] = useState<OutcomeState>({ status: "idle" });
  const adviceTicket = useRef(0);
  const decisionTicket = useRef(0);
  const results = useRef<HTMLElement>(null);

  const loadAdvice = useCallback(async (forecast: ForecastResponse) => {
    const ticket = ++adviceTicket.current;
    if (!forecast.proposal) {
      setAdvice({ status: "idle" });
      return;
    }
    setAdvice({ status: "loading" });
    try {
      const data = await fetchAdvice(forecast);
      if (ticket === adviceTicket.current) setAdvice({ status: "ready", data });
    } catch (problem) {
      if (ticket === adviceTicket.current) setAdvice({ status: "error", message: errorMessage(problem) });
    }
  }, []);

  const runForecast = useCallback(
    async (values: SetupValues) => {
      const inputs: ForecastInputs = {
        file: values.file ?? (await loadSampleFile()),
        startingMinor: values.startingMinor,
        startDate: values.startDate,
      };
      const forecast = await fetchForecast(inputs);
      setBaseline((previous) => ({ forecast, inputs, run: (previous?.run ?? 0) + 1 }));
      setScenario(null);
      decisionTicket.current++;
      setOutcome({ status: "idle" });
      void loadAdvice(forecast);
    },
    [loadAdvice],
  );

  const decide = useCallback(
    async (choice: Decision) => {
      const ticket = ++decisionTicket.current;
      if (!baseline || choice === null) {
        setOutcome({ status: "idle" });
        return;
      }
      setOutcome({ status: "loading", decision: choice });
      try {
        const data = await fetchDecision(baseline.forecast, choice);
        if (ticket === decisionTicket.current) setOutcome({ status: "ready", data });
      } catch (problem) {
        if (ticket === decisionTicket.current) {
          setOutcome({ status: "error", decision: choice, message: errorMessage(problem) });
        }
      }
    },
    [baseline],
  );

  const compare = useCallback(
    async (move: Move) => {
      if (!baseline) return;
      const response = await fetchForecast(baseline.inputs, move);
      if (!response.scenario) throw new Error("The server didn't return a comparison.");
      setScenario({ projection: response.scenario, move });
    },
    [baseline],
  );

  useEffect(() => {
    if (baseline?.run) results.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [baseline?.run]);

  const facts = useMemo(() => (baseline ? analyse(baseline.forecast.baseline) : null), [baseline]);
  const proposal = baseline?.forecast.proposal ?? null;
  // The chart and steps follow the backend's simulated result, not the click itself.
  const decision: Decision = outcome.status === "ready" ? outcome.data.decision : null;

  return (
    <MotionConfig reducedMotion="user">
      <TopBar />
      <main>
        <Hero onSubmit={runForecast} />

        {baseline && facts && (
          <section key={baseline.run} ref={results} className="results" aria-labelledby="verdict-title">
            <Verdict forecast={baseline.forecast} facts={facts} />
            <ChartBlock
              forecast={baseline.forecast}
              facts={facts}
              scenario={scenario}
              coveredMinor={outcome.status === "ready" && decision === "approved" ? outcome.data.limit_minor : 0}
            />
            <AgentSteps
              forecast={baseline.forecast}
              facts={facts}
              limitMinor={proposal?.limit_minor ?? null}
              decision={decision}
              openingMinor={Number(baseline.inputs.startingMinor)}
            />
            {proposal && (
              <Proposal
                forecast={baseline.forecast}
                facts={facts}
                limitMinor={proposal.limit_minor}
                advice={advice}
                outcome={outcome}
                onDecide={(choice) => void decide(choice)}
                onRetryAdvice={() => void loadAdvice(baseline.forecast)}
              />
            )}
            <WhatIf
              forecast={baseline.forecast}
              facts={facts}
              scenario={scenario}
              advice={advice}
              onCompare={compare}
              onClear={() => setScenario(null)}
            />
          </section>
        )}
      </main>
      <Footer />
    </MotionConfig>
  );
}
