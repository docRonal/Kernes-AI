import { parseRedHatBankCsv } from "./parser.js";
import {
  AMALFI_DEFAULT_MOVE_DATE,
  AMALFI_DEFAULT_OPENING_EUR,
  AMALFI_DEFAULT_START_DATE,
  AMALFI_SAMPLE_CSV,
  AMALFI_SAMPLE_FILENAME,
} from "./sample-amalfi.js";
import { requestAdvice, resolveForecast } from "./js/api.js";
import { toMinor } from "./js/format.js";
import { computeProposal } from "./js/proposal.js";
import {
  populateIncomingPayments,
  renderKpis,
  renderLedgerAndChart,
  renderProposalPanel,
} from "./js/render.js";

const forecastForm = document.querySelector("#forecast-form");
const scenarioForm = document.querySelector("#scenario-form");
const fileInput = document.querySelector("#csv-file");
const fileDropzone = document.querySelector("#file-dropzone");
const fileNameEl = document.querySelector("#file-name");
const loadSampleBtn = document.querySelector("#load-sample-btn");
const downloadSampleBtn = document.querySelector("#download-sample-btn");
const horizonSelect = document.querySelector("#horizon-select");

const statusBanner = document.querySelector("#status");
const resultsStatusBanner = document.querySelector("#results-status");
const setupScreen = document.querySelector("#setup-screen");
const resultsSection = document.querySelector("#results");
const changeFileBtn = document.querySelector("#change-file-btn");
const agentStatusPill = document.querySelector("#agent-status-pill");

const adviceLoading = document.querySelector("#advice-loading");
const adviceError = document.querySelector("#advice-error");
const retryAdviceBtn = document.querySelector("#retry-advice-btn");
const explanationEl = document.querySelector("#explanation");

const toggleLedgerBtn = document.querySelector("#toggle-ledger-btn");
const ledgerPanel = document.querySelector("#ledger-panel");
const horizonPills = document.querySelectorAll(".horizon-pill");

const tabCredit = document.querySelector("#tab-credit");
const tabWhatIf = document.querySelector("#tab-whatif");
const panelCredit = document.querySelector("#panel-credit");
const panelWhatIf = document.querySelector("#panel-whatif");

const adviceButton = document.querySelector("#advice-button");
const adviceWrap = document.querySelector("#advice");
const draftTextarea = document.querySelector("#draft");
const copyDraftBtn = document.querySelector("#copy-draft-btn");
const copyFeedback = document.querySelector("#copy-feedback");

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

function showStatus(message, isError = false) {
  const activeBanner = resultsSection.hidden ? statusBanner : resultsStatusBanner;
  const inactiveBanner = resultsSection.hidden ? resultsStatusBanner : statusBanner;
  inactiveBanner.hidden = true;
  activeBanner.textContent = message;
  activeBanner.classList.toggle("error", isError);
  activeBanner.hidden = !message;
}

function showSetupScreen() {
  setupScreen.hidden = false;
  resultsSection.hidden = true;
  changeFileBtn.hidden = true;
  resultsStatusBanner.hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setActiveTab(tab) {
  const isCredit = tab === "credit";
  tabCredit.classList.toggle("is-active", isCredit);
  tabCredit.setAttribute("aria-selected", String(isCredit));
  panelCredit.hidden = !isCredit;

  tabWhatIf.classList.toggle("is-active", !isCredit);
  tabWhatIf.setAttribute("aria-selected", String(!isCredit));
  panelWhatIf.hidden = isCredit;
}

function syncHorizonPills(value) {
  const strVal = String(value);
  for (const pill of horizonPills) {
    const active = pill.dataset.horizon === strVal;
    pill.classList.toggle("is-active", active);
    pill.setAttribute("aria-pressed", String(active));
  }
}

function renderAll() {
  setupScreen.hidden = true;
  resultsSection.hidden = false;
  changeFileBtn.hidden = false;
  syncHorizonPills(state.horizonDays);
  renderKpis(state);
  renderLedgerAndChart(state);
  renderProposalPanel(state);
}

async function fetchAdvice({ revealDraft = false } = {}) {
  if (!state.forecast || !state.forecast.baseline.first_deficit) return;

  const reqId = ++state.adviceRequestId;
  adviceLoading.hidden = false;
  adviceError.hidden = true;
  retryAdviceBtn.hidden = true;
  explanationEl.hidden = true;
  agentStatusPill.textContent = "Assistant thinking…";

  try {
    const data = await requestAdvice({
      firstDeficit: state.forecast.baseline.first_deficit,
      transactions: state.proposal?.relevantTransactions || state.forecast.transactions.slice(0, 20),
    });
    if (reqId !== state.adviceRequestId) return;

    state.advice = data;
    explanationEl.textContent = data.explanation;
    explanationEl.hidden = false;
    draftTextarea.value = data.email_draft || "";
    if (revealDraft) {
      adviceWrap.hidden = false;
      adviceButton.textContent = "Refresh email draft";
    }
    agentStatusPill.textContent = "Assistant Ready";
  } catch {
    if (reqId !== state.adviceRequestId) return;
    agentStatusPill.textContent = "AI Offline";
    adviceError.textContent =
      "Our AI writer is temporarily offline, but your cash numbers and suggested credit line below are accurate and ready to test.";
    adviceError.hidden = false;
    retryAdviceBtn.hidden = false;
  } finally {
    if (reqId === state.adviceRequestId) {
      adviceLoading.hidden = true;
    }
  }
}

async function runBaselineForecast() {
  const submitBtn = document.querySelector("#run-forecast-btn");
  submitBtn.disabled = true;
  loadSampleBtn.disabled = true;
  showStatus("Checking your upcoming cash…");

  try {
    const selectedFile = fileInput.files?.[0];
    const csvText = selectedFile ? await selectedFile.text() : AMALFI_SAMPLE_CSV;
    state.csvFile =
      selectedFile || new File([AMALFI_SAMPLE_CSV], AMALFI_SAMPLE_FILENAME, { type: "text/csv" });

    state.parsedCsv = parseRedHatBankCsv(csvText);
    state.openingBalanceMinor = Number(toMinor(forecastForm.elements.opening_balance.value));
    state.startDate = forecastForm.elements.start_date.value;
    state.horizonDays = horizonSelect.value === "all" ? "all" : Number(horizonSelect.value);

    const data = await resolveForecast({
      csvFile: state.csvFile,
      parsedCsv: state.parsedCsv,
      openingBalanceMinor: state.openingBalanceMinor,
      startDate: state.startDate,
      horizonDays: state.horizonDays,
    });

    state.forecast = data;
    state.proposal = computeProposal(data);
    state.simulationDecision = null;
    state.advice = null;
    adviceWrap.hidden = true;
    adviceButton.textContent = "Write reminder email draft";
    copyFeedback.textContent = "";

    populateIncomingPayments(state, scenarioForm);
    setActiveTab(state.proposal ? "credit" : "whatif");
    showStatus("");
    renderAll();

    if (state.proposal) {
      fetchAdvice({ revealDraft: false });
    } else {
      agentStatusPill.textContent = "Assistant Ready";
    }
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
    loadSampleBtn.disabled = false;
  }
}

// Return to Step 1 (Upload / Settings)
changeFileBtn.addEventListener("click", showSetupScreen);

// Live horizon switcher on Step 2 (14 days / 30 days / Whole file)
for (const pill of horizonPills) {
  pill.addEventListener("click", () => {
    const next = pill.dataset.horizon;
    if (!next || String(state.horizonDays) === next) return;
    horizonSelect.value = next;
    runBaselineForecast();
  });
}

// Tabs
tabCredit.addEventListener("click", () => setActiveTab("credit"));
tabWhatIf.addEventListener("click", () => setActiveTab("whatif"));

// Collapsible day-by-day table toggle
toggleLedgerBtn.addEventListener("click", () => {
  const isOpen = !ledgerPanel.hidden;
  ledgerPanel.hidden = isOpen;
  toggleLedgerBtn.setAttribute("aria-expanded", String(!isOpen));
  const count = document.querySelector("#table-count-pill").textContent;
  toggleLedgerBtn.innerHTML = isOpen
    ? `<span>Show table (<span id="table-count-pill">${count}</span>)</span>`
    : `<span>Hide table (<span id="table-count-pill">${count}</span>)</span>`;
});

// File upload & drag-and-drop
fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  fileNameEl.textContent = file
    ? `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`
    : "Pizzeria Amalfi example (ready to use)";
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

// Forecast & sample controls
forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runBaselineForecast();
});

loadSampleBtn.addEventListener("click", () => {
  fileInput.value = "";
  fileNameEl.textContent = "Pizzeria Amalfi example (ready to use)";
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
  showStatus("Testing earlier payment date…");
  try {
    state.forecast = await resolveForecast({
      csvFile: state.csvFile,
      parsedCsv: state.parsedCsv,
      openingBalanceMinor: state.openingBalanceMinor,
      startDate: state.startDate,
      horizonDays: state.horizonDays,
      moveTransactionId: scenarioForm.elements.move_transaction_id.value,
      moveToDate: scenarioForm.elements.move_to_date.value,
    });
    showStatus("");
    renderAll();
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    btn.disabled = false;
  }
});

document.querySelector("#clear-scenario-btn").addEventListener("click", () => {
  if (!state.forecast) return;
  state.forecast = { ...state.forecast, scenario: null };
  renderAll();
});

// Human decision simulation controls
document.querySelector("#approve-sim-btn").addEventListener("click", () => {
  if (!state.proposal) return;
  state.simulationDecision = "approved";
  renderAll();
});

document.querySelector("#reject-sim-btn").addEventListener("click", () => {
  if (!state.proposal) return;
  state.simulationDecision = "rejected";
  renderAll();
});

document.querySelector("#reset-sim-btn").addEventListener("click", () => {
  state.simulationDecision = null;
  renderAll();
});

// AI advice retry & editable reminder draft
retryAdviceBtn.addEventListener("click", () => {
  fetchAdvice({ revealDraft: !adviceWrap.hidden });
});

adviceButton.addEventListener("click", () => {
  if (state.advice && adviceWrap.hidden) {
    draftTextarea.value = state.advice.email_draft || "";
    adviceWrap.hidden = false;
    adviceButton.textContent = "Refresh email draft";
    return;
  }
  fetchAdvice({ revealDraft: true });
});

copyDraftBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(draftTextarea.value);
    copyFeedback.textContent = "Copied!";
    setTimeout(() => {
      copyFeedback.textContent = "";
    }, 2200);
  } catch {
    copyFeedback.textContent = "Select and copy manually";
  }
});
