import { buildInsightPayload, requestActionPlan } from "./api.js?v=tc16";
import { printDate, printMoney, replayFade } from "./format.js?v=tc11";

const AUTONOMY_BADGES = {
  analyzed: { cls: "level-1", text: "1 · Analyzed by agent" },
  recommended: { cls: "level-2", text: "2 · Agent recommends" },
  requires_approval: { cls: "level-3", text: "3 · Your decision needed" },
  simulation_only: { cls: "level-4", text: "4 · Simulation only — nothing sent" },
};

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

function makeBadge(level) {
  const spec = AUTONOMY_BADGES[level] || AUTONOMY_BADGES.analyzed;
  return el("span", `autonomy-badge ${spec.cls}`, spec.text);
}

function buildFallbackSteps({ forecast, insights, adviceData }) {
  const currency = forecast.currency ?? "EUR";
  const money = (minor) => printMoney(minor, currency);
  const proposal = forecast.proposal;
  const baselineDays = forecast.baseline?.days || [];
  const anomalies = insights?.anomalies || null;
  const optimize = insights?.optimize || null;
  const stress = insights?.stress || null;
  const steps = [];
  let num = 1;

  if (proposal) {
    if (anomalies?.findings?.length > 0) {
      const top = anomalies.findings[0];
      steps.push({
        step_number: num++,
        title: "Double-check an unusual or repeat charge",
        detail: `${top.detail} (${money(top.amount_minor)} on ${printDate(top.date)}). Confirm it's expected before shifting cash.`,
        autonomy_level: "analyzed",
        action_kind: "review_anomaly",
        impact_minor: top.amount_minor,
        counterparty: null,
        email_kind: null,
      });
    }

    const firstMove = optimize?.actions?.[0];
    if (firstMove) {
      const movedTx = (forecast.transactions || []).find((tx) => tx.id === firstMove.transaction_id);
      const isCollect = firstMove.kind === "collect_earlier";
      const counterparty = movedTx?.counterparty || movedTx?.label || firstMove.transaction_id;
      steps.push({
        step_number: num++,
        title: isCollect
          ? `Ask ${counterparty} to pay earlier (${printDate(firstMove.new_date)})`
          : `Ask ${counterparty} for a short payment adjustment (${printDate(firstMove.new_date)})`,
        detail: `Shifting this payment reduces the safety buffer needed by ${money(firstMove.saves_minor)} (down to ${money(firstMove.limit_after_minor)}).`,
        autonomy_level: "recommended",
        action_kind: "shift_payment",
        impact_minor: firstMove.saves_minor,
        counterparty,
        email_kind: isCollect ? "collect_early" : "defer_supplier",
      });
    }

    steps.push({
      step_number: num++,
      title: `Decide on a ${money(proposal.limit_minor)} temporary safety buffer below`,
      detail: `Covers your lowest projected balance (−${money(proposal.deepest_shortfall.shortfall_minor)} on ${printDate(proposal.deepest_shortfall.date)}). Previewing here sends nothing real.`,
      autonomy_level: "requires_approval",
      action_kind: "credit_facility",
      impact_minor: proposal.limit_minor,
      counterparty: null,
      email_kind: null,
    });

    return {
      headline: null,
      steps: steps.slice(0, 4),
      model: adviceData?.model || "demo-deterministic",
      latency_ms: adviceData?.latency_ms ?? null,
    };
  }

  const lowestDay = baselineDays.reduce(
    (min, d) => (d.balance_minor < min.balance_minor ? d : min),
    baselineDays[0],
  );
  const stressBuffer = stress?.buffer_minor ?? 0;

  steps.push({
    step_number: num++,
    title: "Your baseline stays positive",
    detail: `Lowest projected balance over ${baselineDays.length} days is ${money(lowestDay.balance_minor)} on ${printDate(lowestDay.date)} — no safety buffer needed.`,
    autonomy_level: "analyzed",
    action_kind: "none",
    impact_minor: Math.max(0, lowestDay.balance_minor),
    counterparty: null,
    email_kind: null,
  });

  if (stress) {
    const worstScenario = (stress.scenarios || []).find((s) => s.extra_needed_minor > 0);
    steps.push({
      step_number: num++,
      title: "Reserve a safety cushion before reinvesting",
      detail: worstScenario
        ? `Even under a tougher week (${worstScenario.description}), your cash holds up${stressBuffer > 0 ? ` with a ${money(stressBuffer)} cushion` : ""}. Expand the What-If simulator below to test equipment purchases.`
        : "Your cushion handles delay and revenue-dip checks cleanly. Expand the What-If simulator below to test any planned purchase.",
      autonomy_level: "recommended",
      action_kind: "growth_buffer",
      impact_minor: Math.max(0, lowestDay.balance_minor),
      counterparty: null,
      email_kind: null,
    });
  }

  return {
    headline: "Safe growth checklist",
    steps,
    model: "demo-deterministic",
    latency_ms: null,
  };
}

function renderPlanIntoContainer(container, plan, currency, profile, onOpenEmailTab) {
  if (!container) return;
  const money = (minor) => printMoney(minor, currency);

  const header = el("div", "plan-steps-header");
  const titleLabel = [profile?.business_type, profile?.goal].filter(Boolean).join(" · ");
  header.append(
    el("h3", "", titleLabel ? `Tailored next steps · ${titleLabel}` : "Recommended next steps"),
    el(
      "span",
      "plan-steps-meta",
      [plan.model, plan.latency_ms != null ? `${plan.latency_ms} ms` : ""].filter(Boolean).join(" · "),
    ),
  );

  const children = [header];
  if (plan.headline) {
    children.push(el("p", "plan-headline", plan.headline));
  }

  const list = el("div", "plan-steps-list");
  for (const step of plan.steps || []) {
    const card = el("article", "plan-step-card");

    const head = el("div", "plan-step-head");
    const titleWrap = el("div", "plan-step-title-wrap");
    titleWrap.append(
      el("span", "plan-step-num", String(step.step_number)),
      el("h4", "plan-step-title", step.title),
    );
    const meta = el("div", "plan-step-meta");
    meta.append(makeBadge(step.autonomy_level));
    if (step.impact_minor > 0) {
      meta.append(el("span", "pill pill-neutral", money(step.impact_minor)));
    }
    if (step.counterparty) {
      meta.append(el("span", "pill pill-neutral", step.counterparty));
    }
    head.append(titleWrap, meta);

    const detail = el("p", "plan-step-detail", step.detail);
    card.append(head, detail);

    if (step.action_kind === "shift_payment" && onOpenEmailTab) {
      const ctaRow = el("div", "plan-step-cta-row");
      const btn = el("button", "btn btn-stone", "Draft payment email →");
      btn.type = "button";
      btn.addEventListener("click", () => onOpenEmailTab(step));
      ctaRow.append(btn);
      card.append(ctaRow);
    }

    list.append(card);
  }
  children.push(list);

  container.replaceChildren(...children);
  container.hidden = false;
  replayFade(container);
}

export async function renderActionPlan({ state, insightsPromise, onOpenEmailTab }) {
  const forecast = state.forecast;
  const shortfallContainer = document.querySelector("#action-plan-steps");
  const growthContainer = document.querySelector("#growth-plan-steps");
  if (shortfallContainer) shortfallContainer.hidden = true;
  if (growthContainer) growthContainer.hidden = true;
  if (!forecast) return;

  const target = state.proposal ? shortfallContainer : growthContainer;
  const payload = buildInsightPayload(forecast);
  if (!payload || !target) return;

  let plan = null;
  try {
    plan = await requestActionPlan(payload, state.profile);
  } catch {
    const settled = insightsPromise ? await insightsPromise : {};
    if (state.forecast !== forecast) return;
    plan = buildFallbackSteps({
      forecast,
      insights: settled,
      adviceData: state.advice,
    });
  }

  if (state.forecast !== forecast) return;
  renderPlanIntoContainer(target, plan, forecast.currency ?? "EUR", state.profile, onOpenEmailTab);
}
