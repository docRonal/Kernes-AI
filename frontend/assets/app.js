import { parseRedHatBankCsv } from "./parser.js?v=tc7";
import {
  AMALFI_DEFAULT_MOVE_DATE,
  AMALFI_DEFAULT_OPENING_EUR,
  AMALFI_DEFAULT_START_DATE,
  AMALFI_SAMPLE_CSV,
  AMALFI_SAMPLE_FILENAME,
} from "./sample-amalfi.js?v=tc7";
import {
  buildInsightPayload,
  request,
  requestAdvice,
  requestAnomalies,
  requestAskCfo,
  requestCompareOptions,
  requestCreditCheck,
  requestDecision,
  requestHealth,
  requestOptimizePayments,
  requestPredictDelays,
  requestSendReminder,
  requestStressTest,
  resolveForecast,
} from "./js/api.js?v=tc7";
import { EU_CURRENCIES, replayFade, toMinor } from "./js/format.js?v=tc7";
import {
  populateDelayCandidates,
  renderAnomalies,
  renderAskAnswer,
  renderAskError,
  renderCompareOptions,
  renderCreditCheck,
  renderDelayError,
  renderDelayResult,
  renderHealthyCreditScore,
  renderOptimizePayments,
  renderStressTest,
  resetInsightsUi,
} from "./js/insights.js?v=tc7";
import { computeProposal } from "./js/proposal.js?v=tc7";
import {
  buildReminderTemplate,
  populateIncomingPayments,
  renderKpis,
  renderLedgerAndChart,
  renderProposalPanel,
} from "./js/render.js?v=tc7";

const forecastForm = document.querySelector("#forecast-form");
const scenarioForm = document.querySelector("#scenario-form");
const fileInput = document.querySelector("#csv-file");
const fileDropzone = document.querySelector("#file-dropzone");
const fileNameEl = document.querySelector("#file-name");
const loadSampleBtn = document.querySelector("#load-sample-btn");
const loadKernesSampleBtn = document.querySelector("#load-kernes-sample-btn");
const downloadSampleBtn = document.querySelector("#download-sample-btn");
const horizonSelect = document.querySelector("#horizon-select");

const statusBanner = document.querySelector("#status");
const resultsStatusBanner = document.querySelector("#results-status");
const setupScreen = document.querySelector("#setup-screen");
const resultsSection = document.querySelector("#results");
const changeFileBtn = document.querySelector("#change-file-btn");
const healthPill = document.querySelector("#health-pill");
const agentStatusPill = document.querySelector("#agent-status-pill");

const adviceLoading = document.querySelector("#advice-loading");
const adviceError = document.querySelector("#advice-error");
const retryAdviceBtn = document.querySelector("#retry-advice-btn");
const explanationEl = document.querySelector("#explanation");
const adviceModelEl = document.querySelector("#advice-model");

const horizonPills = document.querySelectorAll(".horizon-pill");
const askForm = document.querySelector("#ask-cfo-form");
const askInput = document.querySelector("#ask-cfo-input");
const askBtn = document.querySelector("#ask-cfo-btn");
const askChips = document.querySelectorAll(".ask-chip");
const delayForm = document.querySelector("#delay-form");
const delayTxSelect = document.querySelector("#delay-tx-select");
const delayDaysInput = document.querySelector("#delay-days-input");
const delayPredictBtn = document.querySelector("#delay-predict-btn");

const tabCredit = document.querySelector("#tab-credit");
const tabWhatIf = document.querySelector("#tab-whatif");
const panelCredit = document.querySelector("#panel-credit");
const panelWhatIf = document.querySelector("#panel-whatif");

const adviceButton = document.querySelector("#advice-button");
const adviceWrap = document.querySelector("#advice");
const draftSourceNote = document.querySelector("#draft-source-note");
const draftTextarea = document.querySelector("#draft");
const reminderEmailInput = document.querySelector("#reminder-email");
const reminderSubjectInput = document.querySelector("#reminder-subject");
const sendReminderBtn = document.querySelector("#send-reminder-btn");
const reminderReceipt = document.querySelector("#reminder-receipt");
const reminderError = document.querySelector("#reminder-error");
const copyDraftBtn = document.querySelector("#copy-draft-btn");
const copyFeedback = document.querySelector("#copy-feedback");

let selectedSample = null;

const state = {
  currency: "EUR",
  openingBalanceMinor: null,
  startDate: AMALFI_DEFAULT_START_DATE,
  horizonDays: 14,
  csvFile: null,
  parsedCsv: null,
  forecast: null,
  proposal: null,
  advice: null,
  draftEdited: false,
  adviceRequestId: 0,
  insightsRequestId: 0,
  simulationDecision: null,
  simulationOutcome: null,
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
  state.forecast = null;
  state.adviceRequestId += 1;
  agentStatusPill.textContent = "Assistant Ready";
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

function applyTemplateDraft({ force = false } = {}) {
  if (!state.forecast || (!force && state.draftEdited)) return;
  const { subject, body } = buildReminderTemplate(state, scenarioForm);
  reminderSubjectInput.value = subject;
  draftTextarea.value = body;
  draftSourceNote.textContent = "Template for selected payment · editable, sent manually by you";
  replayFade(draftTextarea);
  replayFade(draftSourceNote);
}

async function fetchAdvice({ forceDraft = false } = {}) {
  if (!state.forecast || state.parsedCsv || !state.forecast.baseline.first_deficit) return;

  const reqId = ++state.adviceRequestId;
  adviceLoading.hidden = false;
  adviceError.hidden = true;
  retryAdviceBtn.hidden = true;
  explanationEl.hidden = true;
  adviceModelEl.hidden = true;
  agentStatusPill.textContent = "Assistant thinking…";

  try {
    const data = await requestAdvice({
      baseline: state.forecast.baseline,
      transactions: state.forecast.transactions,
      currency: state.forecast.currency,
    });
    if (reqId !== state.adviceRequestId) return;

    state.advice = data;
    explanationEl.textContent = data.explanation;
    explanationEl.hidden = false;
    replayFade(explanationEl);
    adviceModelEl.textContent = data.model;
    adviceModelEl.hidden = !data.model;
    if (data.email_draft && (forceDraft || !state.draftEdited)) {
      draftTextarea.value = data.email_draft;
      draftSourceNote.textContent = "Drafted by AI · editable, sent manually by you";
      replayFade(draftTextarea);
      replayFade(draftSourceNote);
    }
    adviceWrap.hidden = false;
    adviceButton.textContent = "Regenerate draft";
    agentStatusPill.textContent = "Assistant Ready";
  } catch {
    if (reqId !== state.adviceRequestId) return;
    agentStatusPill.textContent = "AI Offline";
    adviceError.textContent =
      "Our AI writer is temporarily offline, but your cash numbers and suggested credit line below are accurate and ready to test.";
    adviceError.hidden = false;
    retryAdviceBtn.hidden = false;
    if (forceDraft) {
      applyTemplateDraft({ force: true });
    }
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
  loadKernesSampleBtn.disabled = true;
  showStatus("Checking your upcoming cash…");

  try {
    const selectedFile = fileInput.files?.[0] || selectedSample;
    const csvText = selectedFile ? await selectedFile.text() : AMALFI_SAMPLE_CSV;
    state.csvFile =
      selectedFile || new File([AMALFI_SAMPLE_CSV], AMALFI_SAMPLE_FILENAME, { type: "text/csv" });

    const header = csvText.trimStart().split(/\r?\n/, 1)[0];
    state.parsedCsv = header.includes(";") ? parseRedHatBankCsv(csvText) : null;
    if (!state.parsedCsv) horizonSelect.value = "14";
    // A bank statement names its own currency; a transaction CSV uses the one the owner picked.
    if (EU_CURRENCIES.includes(state.parsedCsv?.currency)) {
      forecastForm.elements.currency.value = state.parsedCsv.currency;
    }
    state.currency = forecastForm.elements.currency.value;
    state.openingBalanceMinor = Number(toMinor(forecastForm.elements.opening_balance.value));
    state.startDate = forecastForm.elements.start_date.value;
    state.horizonDays = horizonSelect.value === "all" ? "all" : Number(horizonSelect.value);

    const data = await resolveForecast({
      csvFile: state.csvFile,
      parsedCsv: state.parsedCsv,
      openingBalanceMinor: state.openingBalanceMinor,
      currency: state.currency,
      startDate: state.startDate,
      horizonDays: state.horizonDays,
    });

    state.forecast = data;
    for (const option of horizonSelect.options) {
      option.disabled = !state.parsedCsv && option.value !== "14";
    }
    for (const pill of horizonPills) {
      pill.hidden = !state.parsedCsv && pill.dataset.horizon !== "14";
    }
    state.adviceRequestId += 1;
    adviceLoading.hidden = true;
    adviceError.hidden = true;
    retryAdviceBtn.hidden = true;
    explanationEl.hidden = true;
    adviceModelEl.hidden = true;
    state.proposal = computeProposal(data);
    state.simulationDecision = null;
    state.simulationOutcome = null;
    state.advice = null;
    state.draftEdited = false;
    adviceWrap.hidden = false;
    adviceButton.textContent = "Regenerate draft";
    copyFeedback.textContent = "";
    reminderReceipt.hidden = true;
    reminderError.hidden = true;

    populateIncomingPayments(state, scenarioForm);
    applyTemplateDraft({ force: true });
    setActiveTab(state.proposal ? "credit" : "whatif");
    showStatus("");
    renderAll();
    loadInsights();

    if (state.proposal && state.parsedCsv) {
      adviceError.textContent =
        "This bank statement is analyzed locally. Your cash summary, credit preview, and editable email draft in Tab 2 are ready below.";
      adviceError.hidden = false;
      agentStatusPill.textContent = "Local forecast";
    } else if (state.proposal) {
      fetchAdvice({ forceDraft: false });
    } else {
      agentStatusPill.textContent = "Assistant Ready";
    }
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
    loadSampleBtn.disabled = false;
    loadKernesSampleBtn.disabled = false;
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

// Backend health check (/health)
async function checkHealth() {
  try {
    const data = await requestHealth();
    if (data?.status === "ok") {
      healthPill.textContent = "API Online";
      healthPill.classList.remove("is-down");
      healthPill.classList.add("is-ok");
      return;
    }
  } catch {
    // Fall through to offline indicator
  }
  healthPill.textContent = "API Offline";
  healthPill.classList.remove("is-ok");
  healthPill.classList.add("is-down");
}
checkHealth();

// Load the backend insight milestones in parallel without blocking the main forecast
function previewCollectAction(action) {
  if (!action || !scenarioForm.elements.move_transaction_id) return;
  scenarioForm.elements.move_transaction_id.value = action.transaction_id;
  scenarioForm.elements.move_to_date.value = action.new_date;
  applyTemplateDraft();
  setActiveTab("whatif");
  document.querySelector("#actions-heading")?.scrollIntoView({ behavior: "smooth", block: "center" });
  scenarioForm.requestSubmit();
}

async function loadInsights() {
  const reqId = ++state.insightsRequestId;
  resetInsightsUi();

  const payload = buildInsightPayload(state.forecast);
  if (!payload) return;

  const currency = state.forecast.currency ?? "EUR";
  const hasShortfall = Boolean(payload.baseline.first_deficit);

  const [anomaliesRes, compareRes, stressRes, creditRes, optimizeRes] = await Promise.allSettled([
    requestAnomalies(payload),
    requestCompareOptions(payload),
    requestStressTest(payload),
    hasShortfall ? requestCreditCheck(payload) : Promise.resolve(null),
    requestOptimizePayments(payload),
  ]);

  if (reqId !== state.insightsRequestId) return;

  if (anomaliesRes.status === "fulfilled" && anomaliesRes.value) {
    renderAnomalies(anomaliesRes.value, currency);
  }
  if (compareRes.status === "fulfilled" && compareRes.value) {
    renderCompareOptions(compareRes.value, currency);
  }
  if (stressRes.status === "fulfilled" && stressRes.value) {
    renderStressTest(stressRes.value, currency);
  }
  if (!hasShortfall) {
    renderHealthyCreditScore();
  } else if (creditRes.status === "fulfilled" && creditRes.value) {
    renderCreditCheck(creditRes.value, currency);
  }
  if (optimizeRes.status === "fulfilled" && optimizeRes.value) {
    renderOptimizePayments(
      optimizeRes.value,
      state.forecast.transactions,
      currency,
      previewCollectAction,
    );
  }
  populateDelayCandidates(state.forecast, currency);
}

// Ask the CFO (Milestone 1)
async function submitAskQuestion(question) {
  const trimmed = String(question || "").trim();
  if (!trimmed || !state.forecast) return;

  const payload = buildInsightPayload(state.forecast);
  if (!payload) {
    renderAskError("Ask the CFO requires at least 14 forecast days.");
    return;
  }

  askBtn.disabled = true;
  askBtn.textContent = "Thinking…";
  try {
    const data = await requestAskCfo(payload, trimmed);
    renderAskAnswer(data, state.forecast.currency ?? "EUR");
  } catch (error) {
    renderAskError(
      error.status === 503
        ? "Ask the CFO runs with the live OpenShift AI model. Switch the server to live mode to ask free-form questions."
        : error.message,
    );
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask →";
  }
}

askForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAskQuestion(askInput.value);
});

for (const chip of askChips) {
  chip.addEventListener("click", () => {
    askInput.value = chip.dataset.question || chip.textContent;
    submitAskQuestion(askInput.value);
  });
}

// Client payment delay prediction (/api/predict-delays)
delayForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.forecast) return;

  const payload = buildInsightPayload(state.forecast);
  if (!payload) {
    renderDelayError("Delay prediction requires at least 14 forecast days.");
    return;
  }

  const txId = delayTxSelect.value;
  const days = Number.parseInt(delayDaysInput.value, 10);
  if (!txId || !Number.isFinite(days) || days < 1 || days > 365) {
    renderDelayError("Enter a delay between 1 and 365 days.");
    return;
  }

  delayPredictBtn.disabled = true;
  delayPredictBtn.textContent = "Checking…";
  try {
    const data = await requestPredictDelays(payload, { [txId]: days });
    renderDelayResult(data);
  } catch (error) {
    renderDelayError(error.message);
  } finally {
    delayPredictBtn.disabled = false;
    delayPredictBtn.textContent = "Predict delay impact →";
  }
});

// File upload & drag-and-drop
fileInput.addEventListener("change", () => {
  selectedSample = null;
  for (const option of horizonSelect.options) option.disabled = false;
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
  selectedSample = null;
  fileInput.value = "";
  fileNameEl.textContent = "Pizzeria Amalfi example (ready to use)";
  forecastForm.elements.opening_balance.value = AMALFI_DEFAULT_OPENING_EUR;
  forecastForm.elements.start_date.value = AMALFI_DEFAULT_START_DATE;
  horizonSelect.value = "14";
  scenarioForm.elements.move_to_date.value = AMALFI_DEFAULT_MOVE_DATE;
  runBaselineForecast();
});

loadKernesSampleBtn.addEventListener("click", async () => {
  loadKernesSampleBtn.disabled = true;
  try {
    const response = await request("/demo/transactions.csv");
    selectedSample = new File([await response.blob()], "transactions.csv", { type: "text/csv" });
    fileInput.value = "";
    fileNameEl.textContent = "Kernes demo (EUR)";
    forecastForm.elements.opening_balance.value = "12000.00";
    forecastForm.elements.currency.value = "EUR";
    forecastForm.elements.start_date.value = "2026-11-23";
    horizonSelect.value = "14";
    await runBaselineForecast();
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    loadKernesSampleBtn.disabled = false;
  }
});

// What-if scenario comparison
scenarioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.forecast) return;

  const baseline = state.forecast.baseline;
  const btn = document.querySelector("#compare-dates-btn");
  btn.disabled = true;
  showStatus("Testing earlier payment date…");
  try {
    const data = await resolveForecast({
      csvFile: state.csvFile,
      parsedCsv: state.parsedCsv,
      openingBalanceMinor: state.openingBalanceMinor,
      currency: state.currency,
      startDate: state.startDate,
      horizonDays: state.horizonDays,
      moveTransactionId: scenarioForm.elements.move_transaction_id.value,
      moveToDate: scenarioForm.elements.move_to_date.value,
    });
    if (state.forecast?.baseline !== baseline) return;
    state.forecast = data;
    showStatus("");
    renderAll();
  } catch (error) {
    if (state.forecast?.baseline === baseline) showStatus(error.message, true);
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
const approveButton = document.querySelector("#approve-sim-btn");
const rejectButton = document.querySelector("#reject-sim-btn");

async function simulateDecision(decision) {
  if (!state.proposal) return;
  const baseline = state.forecast.baseline;
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    const outcome = state.parsedCsv
      ? null
      : await requestDecision({ baseline, decision, currency: state.forecast.currency });
    if (state.forecast?.baseline !== baseline) return;
    state.simulationDecision = outcome?.decision ?? decision;
    state.simulationOutcome = outcome;
    showStatus("");
    renderAll();
  } catch (error) {
    if (state.forecast?.baseline === baseline) showStatus(error.message, true);
  } finally {
    approveButton.disabled = false;
    rejectButton.disabled = false;
  }
}

approveButton.addEventListener("click", () => simulateDecision("approved"));
rejectButton.addEventListener("click", () => simulateDecision("rejected"));

document.querySelector("#reset-sim-btn").addEventListener("click", () => {
  state.simulationDecision = null;
  state.simulationOutcome = null;
  renderAll();
});

// AI advice retry & editable reminder draft
retryAdviceBtn.addEventListener("click", () => {
  fetchAdvice({ forceDraft: false });
});

draftTextarea.addEventListener("input", () => {
  state.draftEdited = true;
});

scenarioForm.elements.move_transaction_id.addEventListener("change", () => {
  applyTemplateDraft();
});

scenarioForm.elements.move_to_date.addEventListener("change", () => {
  applyTemplateDraft();
});

adviceButton.addEventListener("click", () => {
  state.draftEdited = false;
  reminderReceipt.hidden = true;
  reminderError.hidden = true;
  if (!state.parsedCsv && state.proposal) {
    fetchAdvice({ forceDraft: true });
    return;
  }
  applyTemplateDraft({ force: true });
  copyFeedback.textContent = "Draft updated";
  setTimeout(() => {
    copyFeedback.textContent = "";
  }, 2000);
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

// Simulated reminder email sender (/api/send-reminder)
sendReminderBtn.addEventListener("click", async () => {
  const to_email = reminderEmailInput.value.trim();
  const subject = reminderSubjectInput.value.trim();
  const body = draftTextarea.value.trim();

  reminderError.hidden = true;
  if (to_email.length < 3 || !subject || !body) {
    reminderReceipt.hidden = true;
    reminderError.textContent = "Enter a recipient email, subject, and message body first.";
    reminderError.hidden = false;
    return;
  }

  sendReminderBtn.disabled = true;
  sendReminderBtn.textContent = "Simulating…";
  try {
    const data = await requestSendReminder({ to_email, subject, body });
    const title = document.createElement("strong");
    title.textContent = "Simulated · Nothing sent";
    const meta = document.createElement("span");
    meta.textContent = `To: ${data.recipient} · Subject: ${data.subject}`;
    const msg = document.createElement("span");
    msg.textContent = data.message;
    reminderReceipt.replaceChildren(title, meta, msg);
    reminderReceipt.hidden = false;
    replayFade(reminderReceipt);
  } catch (error) {
    reminderReceipt.hidden = true;
    reminderError.textContent = error.message;
    reminderError.hidden = false;
  } finally {
    sendReminderBtn.disabled = false;
    sendReminderBtn.textContent = "Simulate send";
  }
});
