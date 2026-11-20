import { renderCashflowChart } from "./chart.js";
import { buildForecastFromRedHat, parseRedHatBankCsv } from "./parser.js";
import {
  AMALFI_DEFAULT_MOVE_DATE,
  AMALFI_DEFAULT_OPENING_EUR,
  AMALFI_DEFAULT_START_DATE,
  AMALFI_SAMPLE_CSV,
  AMALFI_SAMPLE_FILENAME,
} from "./sample-amalfi.js";

const forecastForm = document.querySelector("#forecast-form");
const scenarioForm = document.querySelector("#scenario-form");
const fileInput = document.querySelector("#csv-file");
const fileDropzone = document.querySelector("#file-dropzone");
const fileNameEl = document.querySelector("#file-name");
const loadSampleBtn = document.querySelector("#load-sample-btn");
const downloadSampleBtn = document.querySelector("#download-sample-btn");
const horizonSelect = document.querySelector("#horizon-select");

const statusBanner = document.querySelector("#status");
const emptyState = document.querySelector("#empty-state");
const resultsSection = document.querySelector("#results");
const accountPill = document.querySelector("#account-pill");
const agentStatusPill = document.querySelector("#agent-status-pill");
const tableCountPill = document.querySelector("#table-count-pill");

const chartContainer = document.querySelector("#chart-container");
const legendScenario = document.querySelector("#legend-scenario");
const legendFacility = document.querySelector("#legend-facility");

const noShortfallCard = document.querySelector("#no-shortfall-card");
const proposalCard = document.querySelector("#proposal-card");
const proposalBadge = document.querySelector("#proposal-badge");
const proposalLimitValue = document.querySelector("#proposal-limit-value");
const factFirstShortfall = document.querySelector("#fact-first-shortfall");
const factPeakShortfall = document.querySelector("#fact-peak-shortfall");
const relevantTxList = document.querySelector("#relevant-transactions");

const agentPulse = document.querySelector("#agent-pulse");
const adviceLoading = document.querySelector("#advice-loading");
const adviceError = document.querySelector("#advice-error");
const retryAdviceBtn = document.querySelector("#retry-advice-btn");
const explanationEl = document.querySelector("#explanation");

const approveSimBtn = document.querySelector("#approve-sim-btn");
const rejectSimBtn = document.querySelector("#reject-sim-btn");
const resetSimBtn = document.querySelector("#reset-sim-btn");
const simulationOutcome = document.querySelector("#simulation-outcome");
const outcomeTitle = document.querySelector("#outcome-title");
const outcomeDetails = document.querySelector("#outcome-details");
const outcomeGapValue = document.querySelector("#outcome-gap-value");

const clearScenarioBtn = document.querySelector("#clear-scenario-btn");
const noIncomingMsg = document.querySelector("#no-incoming-msg");
const scenarioSummaryBox = document.querySelector("#scenario-summary-box");

const draftCard = document.querySelector("#draft-card");
const adviceButton = document.querySelector("#advice-button");
const adviceWrap = document.querySelector("#advice");
const draftTextarea = document.querySelector("#draft");
const copyDraftBtn = document.querySelector("#copy-draft-btn");
const copyFeedback = document.querySelector("#copy-feedback");

const moneyFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const calendar = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeZone: "UTC",
});

const state = {
  openingBalanceMinor: null,
  startDate: AMALFI_DEFAULT_START_DATE,
  horizonDays: 14,
  csvFile: null,
  parsedCsv: null,
  forecast: null,
  proposal: null,
  advice: null,
  adviceRequestId: 0,
  simulationDecision: null, // null | "approved" | "rejected"
};

function toMinor(value) {
  const match = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/.exec(String(value).trim());
  if (!match) throw new Error("Enter an opening balance with up to two decimal places (e.g. 5000.00).");
  const [, sign, whole, fraction = ""] = match;
  const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return (sign === "-" ? -minor : minor).toString();
}

function printDate(isoDate) {
  return calendar.format(new Date(`${isoDate}T00:00:00Z`));
}

function printMoney(minor, currency = "EUR") {
  return `${moneyFormatter.format(Number(minor) / 100)} ${currency}`;
}

function showStatus(message, isError = false) {
  statusBanner.textContent = message;
  statusBanner.classList.toggle("error", isError);
  statusBanner.hidden = !message;
}

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === "string" ? error.detail : `Request failed (HTTP ${response.status}).`;
    const err = new Error(detail);
    err.status = response.status;
    throw err;
  }
  return response;
}

function computeProposal(forecastData) {
  const baseline = forecastData.baseline;
  const firstDeficit = baseline.first_deficit;
  if (!firstDeficit) return null;

  let minBalance = 0;
  let peakDate = firstDeficit.date;
  for (const day of baseline.days) {
    if (day.balance_minor < minBalance) {
      minBalance = day.balance_minor;
      peakDate = day.date;
    }
  }

  const backendProposal = forecastData.credit_proposal || forecastData.proposal || null;
  const peakShortfallMinor =
    backendProposal?.deepest_deficit?.shortfall_minor ??
    backendProposal?.peak_shortfall_minor ??
    Math.max(0, -minBalance);
  const peakShortfallDate =
    backendProposal?.deepest_deficit?.date ??
    backendProposal?.peak_shortfall_date ??
    peakDate;
  const recommendedLimitMinor =
    backendProposal?.recommended_limit_minor ??
    backendProposal?.limit_minor ??
    peakShortfallMinor;

  const startDate = baseline.days[0]?.date;
  const endDate = baseline.days[baseline.days.length - 1]?.date;
  const inWindow = forecastData.transactions.filter(
    (tx) => (!startDate || tx.date >= startDate) && (!endDate || tx.date <= endDate),
  );

  // Highlight largest outflows up to peak shortfall + largest inflows in window (up to 6 items)
  const keyTxs = [...inWindow]
    .sort((a, b) => Math.abs(b.amount_minor) - Math.abs(a.amount_minor))
    .slice(0, 6)
    .sort((a, b) => a.date.localeCompare(b.date));

  return {
    recommendedLimitMinor,
    firstDeficit,
    peakDeficit: {
      date: peakShortfallDate,
      shortfall_minor: peakShortfallMinor,
    },
    relevantTransactions: keyTxs,
  };
}

function groupTransactionsByDate(transactions) {
  const map = new Map();
  for (const tx of transactions) {
    const list = map.get(tx.date) || [];
    list.push(tx);
    map.set(tx.date, list);
  }
  return map;
}

function renderKpis() {
  const { forecast, proposal, openingBalanceMinor, simulationDecision } = state;
  const baseline = forecast.baseline;
  const firstDay = baseline.days[0]?.date;
  const lastDay = baseline.days[baseline.days.length - 1]?.date;

  if (forecast.account_number) {
    accountPill.textContent = `EUR · ${forecast.account_number}`;
  }

  document.querySelector("#kpi-opening").textContent =
    openingBalanceMinor !== null ? printMoney(openingBalanceMinor) : "—";
  document.querySelector("#kpi-horizon").textContent =
    firstDay && lastDay ? `${printDate(firstDay)} – ${printDate(lastDay)}` : `${baseline.days.length}-day window`;

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

    const lowestDay = baseline.days.reduce((acc, d) => (d.balance_minor < acc.balance_minor ? d : acc), baseline.days[0]);
    peakVal.textContent = printMoney(lowestDay.balance_minor);
    peakVal.className = "kpi-value";
    peakDate.textContent = `Lowest on ${printDate(lowestDay.date)}`;

    facilityVal.textContent = printMoney(0);
    facilityVal.className = "kpi-value";
    facilityStatus.textContent = "No credit facility needed";
  }
}

function renderLedgerAndChart() {
  const { forecast, proposal, simulationDecision } = state;
  const baseline = forecast.baseline;
  const scenario = forecast.scenario;
  const txByDate = groupTransactionsByDate(forecast.transactions);

  const shortfallEl = document.querySelector("#shortfall");
  shortfallEl.classList.toggle("negative", Boolean(baseline.first_deficit));
  shortfallEl.textContent = baseline.first_deficit
    ? `First shortfall of ${printMoney(baseline.first_deficit.shortfall_minor)} on ${printDate(baseline.first_deficit.date)} (deepest: ${printMoney(proposal.peakDeficit.shortfall_minor)} on ${printDate(proposal.peakDeficit.date)}).`
    : `No projected shortfall within the ${baseline.days.length}-day horizon.`;

  legendScenario.hidden = !scenario;
  legendFacility.hidden = !(simulationDecision === "approved" && proposal);

  renderCashflowChart(chartContainer, {
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
  document.querySelector("#scenario-heading").hidden = !scenario;
  document.querySelector("#simulation-heading").hidden = !simulationDecision;
  scenarioMessage.hidden = !scenario;
  clearScenarioBtn.hidden = !scenario;

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

  // For full-year statements (> 60 days), show active movement days & key deficit days to keep the table scannable
  const limitMinor = proposal?.recommendedLimitMinor ?? 0;
  const visibleEntries = baseline.days
    .map((day, idx) => ({ day, idx }))
    .filter(({ day, idx }) => {
      if (baseline.days.length <= 60) return true;
      const hasTx = (txByDate.get(day.date) || []).length > 0;
      return hasTx || idx === 0 || idx === baseline.days.length - 1 || day.date === proposal?.peakDeficit.date;
    });

  tableCountPill.textContent =
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

function renderProposalPanel() {
  const { proposal, simulationDecision } = state;

  if (!proposal) {
    proposalCard.hidden = true;
    draftCard.hidden = true;
    noShortfallCard.hidden = false;
    return;
  }

  noShortfallCard.hidden = true;
  proposalCard.hidden = false;
  draftCard.hidden = false;

  proposalLimitValue.textContent = printMoney(proposal.recommendedLimitMinor);
  factFirstShortfall.textContent = `${printMoney(proposal.firstDeficit.shortfall_minor)} · ${printDate(proposal.firstDeficit.date)}`;
  factPeakShortfall.textContent = `${printMoney(proposal.peakDeficit.shortfall_minor)} · ${printDate(proposal.peakDeficit.date)}`;

  relevantTxList.replaceChildren(
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

  approveSimBtn.classList.toggle("is-selected", simulationDecision === "approved");
  rejectSimBtn.classList.toggle("is-selected", simulationDecision === "rejected");

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

async function fetchAdvice({ revealDraft = false } = {}) {
  if (!state.forecast || !state.forecast.baseline.first_deficit) return;

  const reqId = ++state.adviceRequestId;
  adviceLoading.hidden = false;
  adviceError.hidden = true;
  retryAdviceBtn.hidden = true;
  explanationEl.hidden = true;
  agentPulse.className = "agent-pulse is-loading";
  agentStatusPill.textContent = "AI Agent Thinking…";

  const compactTxs = (state.proposal?.relevantTransactions || state.forecast.transactions.slice(0, 20)).map(
    ({ id, date, amount_minor, label }) => ({ id, date, amount_minor, label }),
  );

  try {
    const response = await request("/api/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_deficit: state.forecast.baseline.first_deficit,
        transactions: compactTxs,
      }),
    });
    const data = await response.json();
    if (reqId !== state.adviceRequestId) return;

    state.advice = data;
    explanationEl.textContent = data.explanation;
    explanationEl.hidden = false;
    draftTextarea.value = data.email_draft || "";
    if (revealDraft) {
      adviceWrap.hidden = false;
      adviceButton.textContent = "Refresh reminder draft";
    }
    agentPulse.className = "agent-pulse";
    agentStatusPill.textContent = "AI Explanation Ready";
  } catch (error) {
    if (reqId !== state.adviceRequestId) return;
    agentPulse.className = "agent-pulse is-error";
    agentStatusPill.textContent = "AI Model Unavailable";
    adviceError.textContent = `AI explanation unavailable (${error.message}). Forecast and deterministic credit facility figures above remain valid.`;
    adviceError.hidden = false;
    retryAdviceBtn.hidden = false;
  } finally {
    if (reqId === state.adviceRequestId) {
      adviceLoading.hidden = true;
    }
  }
}

function populateIncomingPayments() {
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
  noIncomingMsg.hidden = incoming.length > 0;

  if (state.proposal?.firstDeficit?.date) {
    scenarioForm.elements.move_to_date.value = state.proposal.firstDeficit.date;
  } else if (startDate) {
    scenarioForm.elements.move_to_date.value = startDate;
  }
}

function renderAll() {
  emptyState.hidden = true;
  resultsSection.hidden = false;
  renderKpis();
  renderLedgerAndChart();
  renderProposalPanel();
}

async function resolveForecast({ moveTransactionId = null, moveToDate = null }) {
  const formData = new FormData();
  formData.set("file", state.csvFile, state.csvFile.name || AMALFI_SAMPLE_FILENAME);
  formData.set("starting_balance_minor", String(state.openingBalanceMinor));
  formData.set("start_date", state.startDate);
  if (moveTransactionId && moveToDate) {
    formData.set("move_transaction_id", moveTransactionId);
    formData.set("move_to_date", moveToDate);
  }

  // Try the backend API first; if the backend hasn't been updated to the Red Hat
  // semicolon CSV format yet (422/503), fall back to the parsed Red Hat projection.
  try {
    const response = await request("/api/forecast", { method: "POST", body: formData });
    return await response.json();
  } catch (error) {
    if (error.status === 422 || error.status === 503) {
      return buildForecastFromRedHat({
        parsed: state.parsedCsv,
        startingBalanceMinor: state.openingBalanceMinor,
        startDate: state.startDate,
        horizonDays: state.horizonDays,
        moveTransactionId,
        moveToDate,
      });
    }
    throw error;
  }
}

async function runBaselineForecast() {
  const submitBtn = document.querySelector("#run-forecast-btn");
  submitBtn.disabled = true;
  loadSampleBtn.disabled = true;
  showStatus("Parsing bank statement and calculating cash forecast…");

  try {
    const selectedFile = fileInput.files?.[0];
    let csvText;
    if (selectedFile) {
      csvText = await selectedFile.text();
      state.csvFile = selectedFile;
    } else {
      csvText = AMALFI_SAMPLE_CSV;
      state.csvFile = new File([AMALFI_SAMPLE_CSV], AMALFI_SAMPLE_FILENAME, { type: "text/csv" });
    }

    state.parsedCsv = parseRedHatBankCsv(csvText);
    state.openingBalanceMinor = Number(toMinor(forecastForm.elements.opening_balance.value));
    state.startDate = forecastForm.elements.start_date.value;
    state.horizonDays = horizonSelect.value === "all" ? "all" : Number(horizonSelect.value);

    const data = await resolveForecast({});
    state.forecast = data;
    state.proposal = computeProposal(data);
    state.simulationDecision = null;
    state.advice = null;
    adviceWrap.hidden = true;
    adviceButton.textContent = "Show editable reminder draft";
    copyFeedback.textContent = "";

    populateIncomingPayments();
    showStatus("");
    renderAll();

    if (state.proposal) {
      fetchAdvice({ revealDraft: false });
    } else {
      agentStatusPill.textContent = "AI Agent Ready";
    }
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
    loadSampleBtn.disabled = false;
  }
}

// File input & drag-and-drop UX
fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  fileNameEl.textContent = file
    ? `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`
    : `Using built-in sample (${AMALFI_SAMPLE_FILENAME})`;
});

["dragenter", "dragover"].forEach((evt) => {
  fileDropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    fileDropzone.classList.add("is-dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  fileDropzone.addEventListener(evt, () => {
    fileDropzone.classList.remove("is-dragover");
  });
});

// Download Red Hat sample CSV
downloadSampleBtn.addEventListener("click", () => {
  const blob = new Blob([AMALFI_SAMPLE_CSV], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = AMALFI_SAMPLE_FILENAME;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});

// Forecast form submit
forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runBaselineForecast();
});

// Load built-in Pizzeria Amalfi sample
loadSampleBtn.addEventListener("click", () => {
  fileInput.value = "";
  fileNameEl.textContent = `Using built-in sample (${AMALFI_SAMPLE_FILENAME})`;
  forecastForm.elements.opening_balance.value = AMALFI_DEFAULT_OPENING_EUR;
  forecastForm.elements.start_date.value = AMALFI_DEFAULT_START_DATE;
  horizonSelect.value = "14";
  scenarioForm.elements.move_to_date.value = AMALFI_DEFAULT_MOVE_DATE;
  runBaselineForecast();
});

// What-if scenario comparison
scenarioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.parsedCsv) return;

  const btn = document.querySelector("#compare-dates-btn");
  btn.disabled = true;
  showStatus("Comparing baseline and adjusted payment date…");
  try {
    const moveTransactionId = scenarioForm.elements.move_transaction_id.value;
    const moveToDate = scenarioForm.elements.move_to_date.value;
    state.forecast = await resolveForecast({ moveTransactionId, moveToDate });
    showStatus("");
    renderAll();
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    btn.disabled = false;
  }
});

clearScenarioBtn.addEventListener("click", () => {
  if (!state.forecast) return;
  state.forecast = { ...state.forecast, scenario: null };
  renderAll();
});

// Human decision simulation controls
approveSimBtn.addEventListener("click", () => {
  if (!state.proposal) return;
  state.simulationDecision = "approved";
  renderAll();
});

rejectSimBtn.addEventListener("click", () => {
  if (!state.proposal) return;
  state.simulationDecision = "rejected";
  renderAll();
});

resetSimBtn.addEventListener("click", () => {
  state.simulationDecision = null;
  renderAll();
});

// Retry AI explanation
retryAdviceBtn.addEventListener("click", () => {
  fetchAdvice({ revealDraft: !adviceWrap.hidden });
});

// Editable reminder draft
adviceButton.addEventListener("click", () => {
  if (state.advice && adviceWrap.hidden) {
    draftTextarea.value = state.advice.email_draft || "";
    adviceWrap.hidden = false;
    adviceButton.textContent = "Refresh reminder draft";
    return;
  }
  fetchAdvice({ revealDraft: true });
});

copyDraftBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(draftTextarea.value);
    copyFeedback.textContent = "Copied to clipboard";
    setTimeout(() => {
      copyFeedback.textContent = "";
    }, 2200);
  } catch {
    copyFeedback.textContent = "Select and copy manually";
  }
});
