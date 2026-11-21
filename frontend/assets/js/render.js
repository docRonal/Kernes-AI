import { renderCashflowChart } from "../chart.js?v=tc22";
import { printDate, printMoney, replayFade } from "./format.js?v=tc10";
import { buildForwardForecast, buildStressCurve } from "./predictions.js?v=tc20";
import { groupTransactionsByDate } from "./proposal.js?v=tc10";

export function renderKpis(state) {
  const { forecast, proposal, openingBalanceMinor, simulationDecision } = state;
  const currency = forecast.currency ?? "EUR";
  const money = (amount, unit = currency) => printMoney(amount, unit);
  const baseline = forecast.baseline;
  const firstDay = baseline.days[0]?.date;
  const lastDay = baseline.days[baseline.days.length - 1]?.date;

  const account = document.querySelector("#account-pill");
  if (forecast.account_number) {
    const shortIban = `${forecast.account_number.slice(0, 6)}…${forecast.account_number.slice(-4)}`;
    account.textContent = `${currency} · ${shortIban}`;
  } else {
    account.textContent = `${currency} Account`;
  }

  document.querySelector("#kpi-opening").textContent =
    openingBalanceMinor !== null ? money(openingBalanceMinor) : "—";
  const dateRange =
    firstDay && lastDay
      ? `${printDate(firstDay)} – ${printDate(lastDay)}`
      : `${baseline.days.length} days`;
  document.querySelector("#kpi-horizon").textContent = state.balanceSourceLabel
    ? `${dateRange} · ${state.balanceSourceLabel}`
    : dateRange;

  const heroCard = document.querySelector("#hero-card");
  const heroBadge = document.querySelector("#hero-badge");
  const heroTitle = document.querySelector("#hero-title");
  const heroSummary = document.querySelector("#hero-summary");
  const prevTitle = heroTitle.textContent;

  const firstCard = document.querySelector("#kpi-first-card");
  const peakCard = document.querySelector("#kpi-peak-card");
  const firstVal = document.querySelector("#kpi-first-shortfall");
  const firstDate = document.querySelector("#kpi-first-date");
  const peakVal = document.querySelector("#kpi-peak-shortfall");
  const peakDate = document.querySelector("#kpi-peak-date");

  if (proposal) {
    heroCard.classList.add("is-warning");
    heroCard.classList.remove("is-healthy");
    firstCard.classList.add("is-danger");
    peakCard.classList.add("is-danger");

    const activeLimit = state.simulationOutcome?.limit_minor ?? proposal.recommendedLimitMinor;

    if (simulationDecision === "approved") {
      heroBadge.textContent = "Preview: Covered";
      heroBadge.className = "pill pill-success";
      heroTitle.textContent = `Covered with a ${money(activeLimit)} safety buffer`;
      heroSummary.textContent = `In this simulation preview, a temporary ${money(activeLimit)} safety buffer covers your cash dip so money still short drops to ${money(0)}.`;
    } else if (simulationDecision === "rejected") {
      heroBadge.textContent = "Preview: Uncovered";
      heroBadge.className = "pill pill-danger";
      heroTitle.textContent = `Short by ${money(proposal.peakDeficit.shortfall_minor)} on ${printDate(proposal.peakDeficit.date)}`;
      heroSummary.textContent = `Without a safety buffer, your account dips below zero on ${printDate(proposal.firstDeficit.date)} and runs up to ${money(proposal.peakDeficit.shortfall_minor)} short. Try testing an earlier customer payment below.`;
    } else {
      heroBadge.textContent = "Heads up · Cash dip ahead";
      heroBadge.className = "pill pill-warning";
      heroTitle.textContent = `You may run ${money(proposal.peakDeficit.shortfall_minor)} short on ${printDate(proposal.peakDeficit.date)}`;
      heroSummary.textContent = `Your cash first goes below zero on ${printDate(proposal.firstDeficit.date)} (−${money(proposal.firstDeficit.shortfall_minor)}). Review the options below to see what helps.`;
    }

    firstVal.textContent = `−${money(proposal.firstDeficit.shortfall_minor)}`;
    firstVal.className = "hero-stat-value negative";
    firstDate.textContent = `On ${printDate(proposal.firstDeficit.date)}`;

    peakVal.textContent = `−${money(proposal.peakDeficit.shortfall_minor)}`;
    peakVal.className = "hero-stat-value negative";
    peakDate.textContent = `Lowest on ${printDate(proposal.peakDeficit.date)}`;
  } else {
    heroCard.classList.remove("is-warning");
    heroCard.classList.add("is-healthy");
    firstCard.classList.remove("is-danger");
    peakCard.classList.remove("is-danger");

    const lowestDay = baseline.days.reduce(
      (acc, d) => (d.balance_minor < acc.balance_minor ? d : acc),
      baseline.days[0],
    );

    heroBadge.textContent = "All good";
    heroBadge.className = "pill pill-success";
    heroTitle.textContent = "Your cash looks healthy";
    heroSummary.textContent = `Your balance stays at or above zero for all ${baseline.days.length} days. Your lowest projected day is ${money(lowestDay.balance_minor)} on ${printDate(lowestDay.date)}.`;

    firstVal.textContent = "None";
    firstVal.className = "hero-stat-value positive";
    firstDate.textContent = "Stays at or above zero";

    peakVal.textContent = money(lowestDay.balance_minor);
    peakVal.className = "hero-stat-value";
    peakDate.textContent = `Lowest on ${printDate(lowestDay.date)}`;
  }

  if (heroTitle.textContent !== prevTitle) {
    replayFade(heroTitle);
    replayFade(heroSummary);
  }
}

export function renderLedgerAndChart(state) {
  const { forecast, proposal, simulationDecision, simulationOutcome } = state;
  const currency = forecast.currency ?? "EUR";
  const money = (amount, unit = currency) => printMoney(amount, unit);
  const baseline = forecast.baseline;
  const scenario = forecast.scenario;
  const txByDate = groupTransactionsByDate(forecast.transactions);

  const shortfallEl = document.querySelector("#shortfall");
  shortfallEl.textContent = baseline.first_deficit
    ? "Red dots mark days below zero. Hover or tap any day to see the payments."
    : "Your balance stays at or above zero every day. Hover or tap any day for details.";

  const forecastDays = state.showForecast
    ? buildForwardForecast(baseline.days, forecast.transactions, 14).days
    : null;
  const stressDays = state.showStress
    ? buildStressCurve(baseline.days, forecast.transactions, { extraDays: 14 })
    : null;
  const whatIfDays = state.whatIfOverlay?.days ?? null;
  const whatIfLabel = state.whatIfOverlay?.label ?? "What-if";

  document.querySelector("#legend-forecast").hidden = !forecastDays;
  document.querySelector("#legend-scenario").hidden = !scenario;
  document.querySelector("#legend-whatif").hidden = !whatIfDays;
  const whatIfLegendLabel = document.querySelector("#legend-whatif-label");
  if (whatIfLegendLabel) whatIfLegendLabel.textContent = whatIfLabel;
  document.querySelector("#legend-stress").hidden = !stressDays;
  document.querySelector("#legend-facility").hidden = !(simulationDecision === "approved" && proposal);
  const clearOverlayBtn = document.querySelector("#clear-whatif-overlay-btn");
  if (clearOverlayBtn) clearOverlayBtn.hidden = !whatIfDays;

  renderCashflowChart(document.querySelector("#chart-container"), {
    baselineDays: baseline.days,
    scenarioDays: scenario ? scenario.days : null,
    decisionDays: simulationOutcome?.days ?? null,
    forecastDays,
    whatIfDays,
    whatIfLabel,
    stressDays,
    transactionsByDate: txByDate,
    firstDeficitDate: proposal?.firstDeficit.date ?? null,
    peakDeficitDate: proposal?.peakDeficit.date ?? null,
    facilityLimitMinor: simulationOutcome?.limit_minor ?? proposal?.recommendedLimitMinor ?? 0,
    simulationDecision,
    currencySymbol:
      currency === "EUR" ? "€" : currency === "USD" ? "$" : currency === "GBP" ? "£" : `${currency} `,
    formatMoney: money,
    formatDate: printDate,
  });

  const scenarioSummaryBox = document.querySelector("#scenario-summary-box");
  document.querySelector("#clear-scenario-btn").hidden = !scenario;

  if (scenario) {
    const adjDeficit = scenario.first_deficit;
    const summaryText = adjDeficit
      ? `Even if paid earlier, you would still dip by ${money(adjDeficit.shortfall_minor)} on ${printDate(adjDeficit.date)}.`
      : `Great news — moving that payment keeps your balance at or above ${money(0)} for the whole period!`;

    if (baseline.first_deficit) {
      const targetDate = baseline.first_deficit.date;
      const baseDay = baseline.days.find((d) => d.date === targetDate);
      const adjDay = scenario.days.find((d) => d.date === targetDate);
      scenarioSummaryBox.textContent =
        baseDay && adjDay
          ? `${summaryText} On ${printDate(targetDate)}, your balance improves from ${money(baseDay.balance_minor)} to ${money(adjDay.balance_minor)}.`
          : summaryText;
    } else {
      scenarioSummaryBox.textContent = summaryText;
    }
    scenarioSummaryBox.hidden = false;
    replayFade(scenarioSummaryBox);
  } else {
    scenarioSummaryBox.hidden = true;
  }
}

export function renderProposalPanel(state) {
  const { forecast, proposal, simulationDecision, simulationOutcome } = state;
  const currency = forecast.currency ?? "EUR";
  const money = (amount, unit = currency) => printMoney(amount, unit);
  const noShortfallCard = document.querySelector("#no-shortfall-card");
  const assistantCard = document.querySelector("#assistant-card");
  const proposalCard = document.querySelector("#proposal-card");
  const creditNoneNote = document.querySelector("#credit-none-note");
  const draftCard = document.querySelector("#draft-card");
  const whatifGrid = document.querySelector("#whatif-grid");

  const days = forecast.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[days.length - 1]?.date;
  const hasIncomingInWindow = (forecast.transactions || []).some(
    ({ amount_minor, date }) =>
      amount_minor > 0 && (!startDate || date >= startDate) && (!endDate || date <= endDate),
  );
  const showDraft = Boolean(proposal || hasIncomingInWindow);

  if (!proposal) {
    assistantCard.hidden = true;
    proposalCard.hidden = true;
    draftCard.hidden = !showDraft;
    whatifGrid?.classList.toggle("is-single", !showDraft);
    noShortfallCard.hidden = false;
    creditNoneNote.hidden = false;
    return;
  }

  noShortfallCard.hidden = true;
  creditNoneNote.hidden = true;
  assistantCard.hidden = false;
  proposalCard.hidden = false;
  draftCard.hidden = !showDraft;
  whatifGrid?.classList.toggle("is-single", !showDraft);

  const limitMinor = simulationOutcome?.limit_minor ?? proposal.recommendedLimitMinor;

  document.querySelector("#proposal-limit-value").textContent = money(limitMinor);
  document.querySelector("#fact-peak-shortfall").textContent =
    `Covers your lowest projected day (${printDate(proposal.peakDeficit.date)})`;

  // Populate 2-3 plain-English "Why it happens" bullets
  const outflows = proposal.relevantTransactions.filter((tx) => tx.amount_minor < 0);
  const topOutflow = outflows[0];
  const bullets = [
    `Your balance first dips below zero on ${printDate(proposal.firstDeficit.date)} (−${money(proposal.firstDeficit.shortfall_minor)}).`,
  ];
  if (proposal.peakDeficit.date !== proposal.firstDeficit.date) {
    bullets.push(
      `It reaches its lowest point on ${printDate(proposal.peakDeficit.date)} (−${money(proposal.peakDeficit.shortfall_minor)}).`,
    );
  }
  if (topOutflow) {
    bullets.push(
      `One of the largest outgoing payments is ${topOutflow.label} (${money(topOutflow.amount_minor)}) on ${printDate(topOutflow.date)}.`,
    );
  }
  bullets.push(
    `A ${money(limitMinor)} safety buffer covers every negative day in this forecast.`,
  );

  document.querySelector("#why-bullets").replaceChildren(
    ...bullets.slice(0, 3).map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }),
  );

  document.querySelector("#relevant-transactions").replaceChildren(
    ...proposal.relevantTransactions.slice(0, 5).map((tx) => {
      const li = document.createElement("li");
      const meta = document.createElement("div");
      meta.className = "tx-meta";
      const label = document.createElement("span");
      label.className = "tx-label";
      label.textContent = tx.label;
      const sub = document.createElement("span");
      sub.className = "tx-sub";
      const fxPart =
        tx.original_currency && tx.original_currency !== currency
          ? ` · ${money(tx.original_amount_minor, tx.original_currency)}`
          : "";
      sub.textContent = `${printDate(tx.date)}${fxPart}`;
      meta.append(label, sub);

      const amt = document.createElement("span");
      amt.className = `tx-amount ${tx.amount_minor < 0 ? "negative" : "positive"}`;
      amt.textContent = `${tx.amount_minor > 0 ? "+" : ""}${money(tx.amount_minor)}`;

      li.append(meta, amt);
      return li;
    }),
  );

  const outcomeBox = document.querySelector("#simulation-outcome");
  const outcomeTitle = document.querySelector("#outcome-title");
  const outcomeDetails = document.querySelector("#outcome-details");
  const outcomeGapValue = document.querySelector("#outcome-gap-value");

  document.querySelector("#approve-sim-btn").classList.toggle("is-selected", simulationDecision === "approved");
  document.querySelector("#reject-sim-btn").classList.toggle("is-selected", simulationDecision === "rejected");

  if (simulationDecision === "approved") {
    outcomeBox.className = "outcome-box approved";
    outcomeTitle.textContent = "Preview Approved — You're Covered";
    outcomeDetails.textContent = `A ${money(limitMinor)} safety buffer covers every negative day in this simulation.`;
    const peakUncovered = simulationOutcome
      ? simulationOutcome.largest_uncovered?.shortfall_minor ?? 0
      : Math.max(0, proposal.peakDeficit.shortfall_minor - limitMinor);
    outcomeGapValue.textContent = money(peakUncovered);
    outcomeBox.hidden = false;
    replayFade(outcomeBox);
  } else if (simulationDecision === "rejected") {
    outcomeBox.className = "outcome-box rejected";
    outcomeTitle.textContent = "Preview Rejected — Gap Remains";
    outcomeDetails.textContent = `Without a temporary buffer, you'll still be short on ${printDate(proposal.peakDeficit.date)}. Try testing an earlier customer payment in Tab 2.`;
    outcomeGapValue.textContent = money(simulationOutcome?.largest_uncovered?.shortfall_minor ?? proposal.peakDeficit.shortfall_minor);
    outcomeBox.hidden = false;
    replayFade(outcomeBox);
  } else {
    outcomeBox.hidden = true;
  }
}

export function populateIncomingPayments(state, scenarioForm) {
  const money = (amount) => printMoney(amount, state.forecast.currency ?? "EUR");
  const baseline = state.forecast.baseline;
  const startDate = baseline.days[0]?.date;
  const endDate = baseline.days[baseline.days.length - 1]?.date;

  const incoming = state.forecast.transactions
    .filter(
      ({ amount_minor, date }) =>
        amount_minor > 0 && (!startDate || date >= startDate) && (!endDate || date <= endDate),
    )
    .sort((a, b) => b.amount_minor - a.amount_minor)
    .slice(0, 40)
    .map(
      ({ id, label, date, amount_minor }) =>
        new Option(`${label} (+${money(amount_minor)} on ${printDate(date)})`, id),
    );

  scenarioForm.elements.move_transaction_id.replaceChildren(...incoming);
  scenarioForm.hidden = incoming.length === 0;
  document.querySelector("#no-incoming-msg").hidden = incoming.length > 0;

  const suggestedDate = state.forecast.earlier_payments?.[0]?.pay_by;
  const moveDateInput = scenarioForm.elements.move_to_date;
  if (moveDateInput) {
    moveDateInput.min = startDate || "";
    moveDateInput.max = endDate || "";
    if (suggestedDate) {
      moveDateInput.value = suggestedDate;
    } else if (state.proposal?.firstDeficit?.date) {
      moveDateInput.value = state.proposal.firstDeficit.date;
    } else if (startDate) {
      moveDateInput.value = startDate;
    }
  }
}

export function buildReminderTemplate(state, scenarioForm) {
  const currency = state.forecast?.currency ?? "EUR";
  const money = (amount) => printMoney(amount, currency);
  const days = state.forecast?.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[days.length - 1]?.date;
  const selectedId = scenarioForm?.elements?.move_transaction_id?.value;

  const incoming = (state.forecast?.transactions || []).filter(
    ({ amount_minor, date }) =>
      amount_minor > 0 && (!startDate || date >= startDate) && (!endDate || date <= endDate),
  );
  const chosenTx =
    incoming.find((tx) => tx.id === selectedId) ||
    incoming.sort((a, b) => b.amount_minor - a.amount_minor)[0] ||
    null;

  const requestedDateIso =
    scenarioForm?.elements?.move_to_date?.value ||
    state.proposal?.firstDeficit?.date ||
    chosenTx?.date;
  const requestedDate = requestedDateIso ? printDate(requestedDateIso) : "earlier this week";

  if (!chosenTx) {
    return {
      subject: "Payment schedule request",
      body: `Hello,\n\nCould we arrange an earlier settlement on ${requestedDate} to support our upcoming cash schedule?\n\nThank you very much,\nKERNES CFO`,
    };
  }

  const amountText = money(chosenTx.amount_minor);
  const dueDate = printDate(chosenTx.date);
  const isSameDate = requestedDateIso === chosenTx.date;
  const askLine = isSameDate
    ? `Could we confirm payment of ${chosenTx.label} (${amountText}) for ${dueDate}?`
    : `Would it be possible to settle ${chosenTx.label} (${amountText}, currently scheduled for ${dueDate}) earlier on ${requestedDate}?`;

  return {
    subject: `Early payment request: ${chosenTx.label} (${amountText})`,
    body: `Hello,\n\n${askLine} Settling on that date helps keep our upcoming supplier and payroll schedule smooth.\n\nPlease let us know if that works on your end.\n\nBest regards,\nKERNES CFO`,
  };
}
