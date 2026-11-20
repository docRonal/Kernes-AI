import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MotionConfig } from "motion/react";
import { analyse, proposalFor } from "./analysis";
import { errorMessage, fetchAdvice, fetchForecast, loadSampleFile, type ForecastInputs } from "./api";
import { AgentSteps } from "./components/AgentSteps";
import { ChartBlock } from "./components/CashChart";
import { Footer, TopBar } from "./components/Chrome";
import { Hero, type SetupValues } from "./components/Hero";
import { Proposal } from "./components/Proposal";
import { Verdict } from "./components/Verdict";
import { WhatIf } from "./components/WhatIf";
import type { AdviceState, Decision, ForecastResponse, Move, Scenario } from "./types";

type Baseline = { forecast: ForecastResponse; inputs: ForecastInputs; run: number };

export function App() {
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [advice, setAdvice] = useState<AdviceState>({ status: "idle" });
  const [decision, setDecision] = useState<Decision>(null);
  const adviceTicket = useRef(0);
  const results = useRef<HTMLElement>(null);

  const loadAdvice = useCallback(async (forecast: ForecastResponse) => {
    const ticket = ++adviceTicket.current;
    if (!forecast.baseline.first_deficit) {
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
      setDecision(null);
      void loadAdvice(forecast);
    },
    [loadAdvice],
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
  const proposal = baseline ? proposalFor(baseline.forecast) : null;

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
              coveredMinor={decision === "approved" && proposal ? proposal.limit_minor : 0}
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
                decision={decision}
                onDecide={setDecision}
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
