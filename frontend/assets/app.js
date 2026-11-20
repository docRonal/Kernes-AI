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
const emptyState = document.querySelector("#empty-state");
const resultsSection = document.querySelector("#results");
const agentStatusPill = document.querySelector("#agent-status-pill");

const agentPulse = document.querySelector("#agent-pulse");
const adviceLoading = document.querySelector("#advice-loading");
const adviceError = document.querySelector("#advice-error");
const retryAdviceBtn = document.querySelector("#retry-advice-btn");
const explanationEl = document.querySelector("#explanation");

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
  statusBanner.textContent = message;
  statusBanner.classList.toggle("error", isError);
  statusBanner.hidden = !message;
}

function renderAll() {
  emptyState.hidden = true;
  resultsSection.hidden = false;
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
  agentPulse.className = "agent-pulse is-loading";
  agentStatusPill.textContent = "AI Agent Thinking…";

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

async function runBaselineForecast() {
  const submitBtn = document.querySelector("#run-forecast-btn");
  submitBtn.disabled = true;
  loadSampleBtn.disabled = true;
  showStatus("Parsing bank statement and calculating cash forecast…");

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
    adviceButton.textContent = "Show editable reminder draft";
    copyFeedback.textContent = "";

    populateIncomingPayments(state, scenarioForm);
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

// File upload & drag-and-drop
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

// Forecast & sample controls
forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runBaselineForecast();
});

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
