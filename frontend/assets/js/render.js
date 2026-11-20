import { renderCashflowChart } from "../chart.js";
import { printDate, printMoney } from "./format.js";
import { groupTransactionsByDate } from "./proposal.js";

export function renderKpis(state) {
  const { forecast, proposal, openingBalanceMinor, simulationDecision } = state;
  const baseline = forecast.baseline;
  const firstDay = baseline.days[0]?.date;
  const lastDay = baseline.days[baseline.days.length - 1]?.date;

  if (forecast.account_number) {
    document.querySelector("#account-pill").textContent = `EUR · ${forecast.account_number}`;
  }

  document.querySelector("#kpi-opening").textContent =
    openingBalanceMinor !== null ? printMoney(openingBalanceMinor) : "—";
  document.querySelector("#kpi-horizon").textContent =
    firstDay && lastDay
      ? `${printDate(firstDay)} – ${printDate(lastDay)}`
      : `${baseline.days.length}-day window`;

  const firstCard = document.querySelector("#kpi-first-card");
  const peakCard = document.querySelector("#kpi-peak-card");
  const facilityCard = document.querySelector("#kpi-facility-card");

  const firstVal = document.querySelector("#kpi-first-shortfall");
  const firstDate = document.querySelector("#kpi-first-date");
  const peakVal = document.querySelector("#kpi-peak-shortfall");
  const peakDate = document.querySelector("#kpi-peak-date");
  const facilityVal = document.querySelector("#kpi-facility-limit");
  const facilityStatus = document.querySelector("#kpi-facility-status");

  if (proposal) {
    firstCard.classList.add("is-danger");
    peakCard.classList.add("is-danger");
    facilityCard.classList.add("is-accent");

    firstVal.textContent = printMoney(proposal.firstDeficit.shortfall_minor);
    firstVal.className = "kpi-value negative";
    firstDate.textContent = `On ${printDate(proposal.firstDeficit.date)}`;

    peakVal.textContent = printMoney(proposal.peakDeficit.shortfall_minor);
    peakVal.className = "kpi-value negative";
    peakDate.textContent = `On ${printDate(proposal.peakDeficit.date)}`;

    facilityVal.textContent = printMoney(proposal.recommendedLimitMinor);
    facilityVal.className = "kpi-value positive";
    facilityStatus.textContent =
      simulationDecision === "approved"
        ? "Approved (simulation)"
        : simulationDecision === "rejected"
          ? "Rejected (simulation)"
          : "Pending review (simulation)";
  } else {
    firstCard.classList.remove("is-danger");
    peakCard.classList.remove("is-danger");
    facilityCard.classList.remove("is-accent");

    firstVal.textContent = "None";
    firstVal.className = "kpi-value positive";
    firstDate.textContent = `All ${baseline.days.length} days ≥ 0.00 EUR`;

    const lowestDay = baseline.days.reduce(
      (acc, d) => (d.balance_minor < acc.balance_minor ? d : acc),
      baseline.days[0],
    );
    peakVal.textContent = printMoney(lowestDay.balance_minor);
    peakVal.className = "kpi-value";
    peakDate.textContent = `Lowest on ${printDate(lowestDay.date)}`;

    facilityVal.textContent = printMoney(0);
    facilityVal.className = "kpi-value";
    facilityStatus.textContent = "No credit facility needed";
  }
}

export function renderLedgerAndChart(state) {
  const { forecast, proposal, simulationDecision } = state;
  const baseline = forecast.baseline;
  const scenario = forecast.scenario;
  const txByDate = groupTransactionsByDate(forecast.transactions);

  const shortfallEl = document.querySelector("#shortfall");
  shortfallEl.classList.toggle("negative", Boolean(baseline.first_deficit));
  shortfallEl.textContent = baseline.first_deficit
    ? `First shortfall of ${printMoney(baseline.first_deficit.shortfall_minor)} on ${printDate(baseline.first_deficit.date)} (deepest: ${printMoney(proposal.peakDeficit.shortfall_minor)} on ${printDate(proposal.peakDeficit.date)}).`
    : `No projected shortfall within the ${baseline.days.length}-day horizon.`;

  document.querySelector("#legend-scenario").hidden = !scenario;
  document.querySelector("#legend-facility").hidden = !(simulationDecision === "approved" && proposal);

  renderCashflowChart(document.querySelector("#chart-container"), {
    baselineDays: baseline.days,
    scenarioDays: scenario ? scenario.days : null,
    transactionsByDate: txByDate,
    firstDeficitDate: proposal?.firstDeficit.date ?? null,
    peakDeficitDate: proposal?.peakDeficit.date ?? null,
    facilityLimitMinor: proposal?.recommendedLimitMinor ?? 0,
    simulationDecision,
    currencySymbol: "€",
    formatMoney: (m) => printMoney(m, "EUR"),
    formatDate: printDate,
  });

  const scenarioMessage = document.querySelector("#scenario-message");
  const scenarioSummaryBox = document.querySelector("#scenario-summary-box");
  document.querySelector("#scenario-heading").hidden = !scenario;
  document.querySelector("#simulation-heading").hidden = !simulationDecision;
  scenarioMessage.hidden = !scenario;
  document.querySelector("#clear-scenario-btn").hidden = !scenario;

  if (scenario) {
    const adjDeficit = scenario.first_deficit;
    const summaryText = adjDeficit
      ? `Adjusted scenario still shows a shortfall of ${printMoney(adjDeficit.shortfall_minor)} on ${printDate(adjDeficit.date)}.`
      : `Adjusted scenario stays at or above 0.00 EUR for all ${baseline.days.length} days.`;
    scenarioMessage.textContent = summaryText;

    if (baseline.first_deficit) {
      const targetDate = baseline.first_deficit.date;
      const baseDay = baseline.days.find((d) => d.date === targetDate);
      const adjDay = scenario.days.find((d) => d.date === targetDate);
      scenarioSummaryBox.textContent =
        baseDay && adjDay
          ? `${summaryText} On ${printDate(targetDate)}, balance changes from ${printMoney(baseDay.balance_minor)} (baseline) to ${printMoney(adjDay.balance_minor)} (adjusted). Baseline and proposal remain preserved.`
          : summaryText;
    } else {
      scenarioSummaryBox.textContent = summaryText;
    }
    scenarioSummaryBox.hidden = false;
  } else {
    scenarioSummaryBox.hidden = true;
  }

  const limitMinor = proposal?.recommendedLimitMinor ?? 0;
  const visibleEntries = baseline.days
    .map((day, idx) => ({ day, idx }))
    .filter(({ day, idx }) => {
      if (baseline.days.length <= 60) return true;
      const hasTx = (txByDate.get(day.date) || []).length > 0;
      return hasTx || idx === 0 || idx === baseline.days.length - 1 || day.date === proposal?.peakDeficit.date;
    });

  document.querySelector("#table-count-pill").textContent =
    visibleEntries.length === baseline.days.length
      ? `${baseline.days.length} days`
      : `${visibleEntries.length} active of ${baseline.days.length} days`;

  const rows = visibleEntries.map(({ day, idx }) => {
    const tr = document.createElement("tr");
    if (day.balance_minor < 0) tr.classList.add("row-deficit");

    const dateCell = tr.insertCell();
    dateCell.textContent = printDate(day.date);

    const eventsCell = tr.insertCell();
    const dayTxs = txByDate.get(day.date) || [];
    if (dayTxs.length > 0) {
      const wrap = document.createElement("div");
      wrap.className = "event-chips";
      for (const tx of dayTxs) {
        const chip = document.createElement("span");
        chip.className = `event-chip ${tx.amount_minor < 0 ? "outflow" : "inflow"}`;
        const sign = tx.amount_minor > 0 ? "+" : "";
        const fxTag =
          tx.original_currency && tx.original_currency !== "EUR"
            ? ` [${printMoney(tx.original_amount_minor, tx.original_currency)}]`
            : "";
        chip.textContent = `${tx.label} (${sign}${printMoney(tx.amount_minor)})${fxTag}`;
        if (tx.reference) chip.title = `${tx.transaction_type || ""} · ${tx.reference}`;
        wrap.append(chip);
      }
      eventsCell.append(wrap);
    } else {
      eventsCell.textContent = "—";
      eventsCell.className = "muted-note";
    }

    const baseCell = tr.insertCell();
    baseCell.className = `num ${day.balance_minor < 0 ? "negative" : ""}`;
    baseCell.textContent = printMoney(day.balance_minor);

    if (scenario) {
      const adjBalance = scenario.days[idx].balance_minor;
      const adjCell = tr.insertCell();
      adjCell.className = `num ${adjBalance < 0 ? "negative" : "positive"}`;
      adjCell.textContent = printMoney(adjBalance);
    }

    if (simulationDecision) {
      const rawGap = Math.max(0, -day.balance_minor);
      const uncovered =
        simulationDecision === "approved" ? Math.max(0, rawGap - limitMinor) : rawGap;
      const simCell = tr.insertCell();
      simCell.className = `num ${uncovered > 0 ? "negative" : "positive"}`;
      simCell.textContent = printMoney(uncovered);
    }

    return tr;
  });

  document.querySelector("#balances").replaceChildren(...rows);
}

export function renderProposalPanel(state) {
  const { proposal, simulationDecision } = state;
  const noShortfallCard = document.querySelector("#no-shortfall-card");
  const proposalCard = document.querySelector("#proposal-card");
  const draftCard = document.querySelector("#draft-card");

  if (!proposal) {
    proposalCard.hidden = true;
    draftCard.hidden = true;
    noShortfallCard.hidden = false;
    return;
  }

  noShortfallCard.hidden = true;
  proposalCard.hidden = false;
  draftCard.hidden = false;

  document.querySelector("#proposal-limit-value").textContent = printMoney(proposal.recommendedLimitMinor);
  document.querySelector("#fact-first-shortfall").textContent =
    `${printMoney(proposal.firstDeficit.shortfall_minor)} · ${printDate(proposal.firstDeficit.date)}`;
  document.querySelector("#fact-peak-shortfall").textContent =
    `${printMoney(proposal.peakDeficit.shortfall_minor)} · ${printDate(proposal.peakDeficit.date)}`;

  document.querySelector("#relevant-transactions").replaceChildren(
    ...proposal.relevantTransactions.map((tx) => {
      const li = document.createElement("li");
      const meta = document.createElement("div");
      meta.className = "tx-meta";
      const label = document.createElement("span");
      label.className = "tx-label";
      label.textContent = tx.label;
      const sub = document.createElement("span");
      sub.className = "tx-sub";
      const typePart = tx.transaction_type ? `${tx.transaction_type} · ` : `${tx.id} · `;
      const fxPart =
        tx.original_currency && tx.original_currency !== "EUR"
          ? ` · ${printMoney(tx.original_amount_minor, tx.original_currency)}`
          : "";
      sub.textContent = `${typePart}${printDate(tx.date)}${fxPart}`;
      meta.append(label, sub);

      const amt = document.createElement("span");
      amt.className = `tx-amount ${tx.amount_minor < 0 ? "negative" : "positive"}`;
      amt.textContent = `${tx.amount_minor > 0 ? "+" : ""}${printMoney(tx.amount_minor)}`;

      li.append(meta, amt);
      return li;
    }),
  );

  const proposalBadge = document.querySelector("#proposal-badge");
  const simulationOutcome = document.querySelector("#simulation-outcome");
  const outcomeTitle = document.querySelector("#outcome-title");
  const outcomeDetails = document.querySelector("#outcome-details");
  const outcomeGapValue = document.querySelector("#outcome-gap-value");

  document.querySelector("#approve-sim-btn").classList.toggle("is-selected", simulationDecision === "approved");
  document.querySelector("#reject-sim-btn").classList.toggle("is-selected", simulationDecision === "rejected");

  if (simulationDecision === "approved") {
    proposalBadge.textContent = "Approved (Simulation)";
    proposalBadge.className = "pill pill-success";
    simulationOutcome.className = "outcome-box approved";
    outcomeTitle.textContent = "Simulation Approved — Credit Facility Applied";
    outcomeDetails.textContent = `Simulated access to a ${printMoney(proposal.recommendedLimitMinor)} credit facility covers the baseline cash shortfall. Underlying baseline balances remain unchanged.`;
    const peakUncovered = Math.max(0, proposal.peakDeficit.shortfall_minor - proposal.recommendedLimitMinor);
    outcomeGapValue.textContent = printMoney(peakUncovered);
    simulationOutcome.hidden = false;
  } else if (simulationDecision === "rejected") {
    proposalBadge.textContent = "Rejected (Simulation)";
    proposalBadge.className = "pill pill-danger";
    simulationOutcome.className = "outcome-box rejected";
    outcomeTitle.textContent = "Simulation Rejected — Shortfall Unfunded";
    outcomeDetails.textContent = `No credit facility is applied in this simulation. The projected shortfall on ${printDate(proposal.peakDeficit.date)} remains uncovered unless incoming settlements move earlier.`;
    outcomeGapValue.textContent = printMoney(proposal.peakDeficit.shortfall_minor);
    simulationOutcome.hidden = false;
  } else {
    proposalBadge.textContent = "Action Required";
    proposalBadge.className = "pill pill-warning";
    simulationOutcome.hidden = true;
  }
}

export function populateIncomingPayments(state, scenarioForm) {
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
        new Option(`${label} (+${printMoney(amount_minor)} · ${printDate(date)})`, id),
    );

  scenarioForm.elements.move_transaction_id.replaceChildren(...incoming);
  scenarioForm.hidden = incoming.length === 0;
  document.querySelector("#no-incoming-msg").hidden = incoming.length > 0;

  if (state.proposal?.firstDeficit?.date) {
    scenarioForm.elements.move_to_date.value = state.proposal.firstDeficit.date;
  } else if (startDate) {
    scenarioForm.elements.move_to_date.value = startDate;
  }
}
