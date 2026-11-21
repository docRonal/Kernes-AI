import {
  buildInsightPayload,
  formatCsvError,
  request,
  requestAdvice,
  requestAnomalies,
  requestAskCfo,
  requestCompareOptions,
  requestCreditCheck,
  requestDecision,
  requestOptimizePayments,
  requestPredictDelays,
  requestSendReminder,
  requestStressTest,
  resolveForecast,
} from "./js/api.js?v=tc16";
import { renderActionPlan } from "./js/action_plan.js?v=amalfi-chat";
import { extractCsvDefaults } from "./js/csv.js?v=1";
import { printDate, printMoney, replayFade, toMinor } from "./js/format.js?v=tc11";
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
} from "./js/insights.js?v=tc25";
import { buildWhatIfCurve, addDaysIso } from "./js/predictions.js?v=history-chart";
import { readProposal } from "./js/proposal.js?v=tc11";
import {
  buildReminderTemplate,
  populateIncomingPayments,
  renderKpis,
  renderLedgerAndChart,
  renderProposalPanel,
} from "./js/render.js?v=history-chart";
import {
  buildCombinedWhatIfOverlay,
  createWorkspaceController,
  initAffordSandbox,
  renderActiveSimsBar,
  renderCashBreakdown,
  renderSignalStripBase,
  renderSmartCalendar,
  updateSignalStripInsights,
} from "./js/workspace.js?v=tc27";

const HORIZON_DAYS = 14;
const AMALFI_OPENING_BALANCE_MINOR = 3_326_635;
const AMALFI_FORECAST_START_DATE = "2026-01-01";

const forecastForm = document.querySelector("#forecast-form");
const businessTypeInput = document.querySelector("#business-type-input");
const businessGoalInput = document.querySelector("#business-goal-input");
const promptChips = document.querySelectorAll(".prompt-chip");
const scenarioForm = document.querySelector("#scenario-form");
const fileInput = document.querySelector("#csv-file");
const fileDropzone = document.querySelector("#file-dropzone");
const csvOpeningBalanceGroup = document.querySelector("#csv-opening-balance-group");
const csvOpeningBalance = document.querySelector("#csv-opening-balance");
const csvOpeningBalanceHint = document.querySelector("#csv-opening-balance-hint");
const fileNameEl = document.querySelector("#file-name");
const sampleFileLabel = fileNameEl.textContent;
const sampleHint = document.querySelector("#sample-hint");
const sampleDownloadLink = document.querySelector("#download-sample-link");
const useSampleBtn = document.querySelector("#use-sample-btn");
const editBalanceBtn = document.querySelector("#edit-balance-btn");
const inlineBalanceForm = document.querySelector("#inline-balance-form");
const inlineBalanceInput = document.querySelector("#inline-balance-input");
const cancelBalanceBtn = document.querySelector("#cancel-balance-btn");

const statusBanner = document.querySelector("#status");
const resultsStatusBanner = document.querySelector("#results-status");
const setupScreen = document.querySelector("#setup-screen");
const resultsSection = document.querySelector("#results");
const changeFileBtn = document.querySelector("#change-file-btn");
const printReportBtn = document.querySelector("#print-report-btn");
const calendarFilterChips = Array.from(document.querySelectorAll("[data-cal-filter]"));
const simAddPurchaseBtn = document.querySelector("#sim-add-purchase-btn");
const simResetAllBtn = document.querySelector("#sim-reset-all-btn");
const workspace = createWorkspaceController();
const affordSandbox = initAffordSandbox({
  getState: () => state,
  onAddPurchase: (purchase) => addPlannedPurchase(purchase),
  onJumpToChart: () => workspace.setWorkspace("overview", "#chart-heading"),
  onJumpToBreakdown: () => workspace.setWorkspace("overview", "#breakdown-card"),
});

const adviceLoading = document.querySelector("#advice-loading");
const adviceError = document.querySelector("#advice-error");
const retryAdviceBtn = document.querySelector("#retry-advice-btn");
const explanationEl = document.querySelector("#explanation");
const adviceModelEl = document.querySelector("#advice-model");

const toggleForecastBtn = document.querySelector("#toggle-forecast-btn");
const toggleStressBtn = document.querySelector("#toggle-stress-btn");
const clearWhatIfOverlayBtn = document.querySelector("#clear-whatif-overlay-btn");
const whatIfModeAskBtn = document.querySelector("#whatif-mode-ask");
const whatIfModeDelayBtn = document.querySelector("#whatif-mode-delay");
const whatIfPanelAsk = document.querySelector("#whatif-panel-ask");
const whatIfPanelDelay = document.querySelector("#whatif-panel-delay");
const whatIfChartBanner = document.querySelector("#whatif-chart-banner");
const whatIfChartLabel = document.querySelector("#whatif-chart-label");
const scrollToChartBtn = document.querySelector("#scroll-to-chart-btn");
const clearWhatIfCardBtn = document.querySelector("#clear-whatif-card-btn");
const askForm = document.querySelector("#ask-cfo-form");
const askInput = document.querySelector("#ask-cfo-input");
const askBtn = document.querySelector("#ask-cfo-btn");
const askLoading = document.querySelector("#ask-loading");
const askChips = document.querySelectorAll("#ask-cfo-card .ask-chip");
const delayForm = document.querySelector("#delay-form");
const delayTxSelect = document.querySelector("#delay-tx-select");
const delayDaysInput = document.querySelector("#delay-days-input");
const delayPredictBtn = document.querySelector("#delay-predict-btn");
const delayLoading = document.querySelector("#delay-loading");

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

const state = {
  openingBalanceMinor: null,
  balanceSourceLabel: "",
  startDate: "",
  horizonDays: HORIZON_DAYS,
  csvFile: null,
  profile: {
    business_type: "",
    goal: "",
    experience_level: "beginner",
  },
  forecast: null,
  proposal: null,
  advice: null,
  advicePreviewOnly: false,
  draftEdited: false,
  adviceRequestId: 0,
  insightsRequestId: 0,
  simulationDecision: null,
  simulationOutcome: null,
  showForecast: true,
  showStress: false,
  whatIfOverlay: null,
  plannedPurchases: [],
  earlyPaySim: null,
  customWhatIf: null,
  calendarFilter: "all",
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
  state.proposal = null;
  state.advice = null;
  state.adviceRequestId += 1;
  state.insightsRequestId += 1;
  setupScreen.hidden = false;
  resultsSection.hidden = true;
  changeFileBtn.hidden = true;
  if (printReportBtn) printReportBtn.hidden = true;
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

function handleQuickTransactionAction(tx, actKey) {
  if (!tx || !state.forecast || state.forecast.forecast_basis === "history") return;
  const currency = state.forecast.currency ?? "EUR";
  const party = tx.counterparty || tx.label;
  const amountText = printMoney(Math.abs(tx.amount_minor), currency);

  workspace.setWorkspace("actions");
  setActiveTab("whatif");

  if (actKey === "email_collect_early" && scenarioForm?.elements?.move_transaction_id) {
    const optExists = Array.from(scenarioForm.elements.move_transaction_id.options).some(
      (o) => o.value === tx.id,
    );
    if (optExists) {
      scenarioForm.elements.move_transaction_id.value = tx.id;
      state.draftEdited = false;
      applyTemplateDraft({ force: true });
    }
  } else if (actKey === "email_defer_supplier") {
    const refPart = tx.payment_reference ? ` (${tx.payment_reference})` : "";
    reminderSubjectInput.value = `Short payment extension request: ${party}`;
    draftTextarea.value = `Hello ${party},\n\nWe have an upcoming payment of ${amountText}${refPart} scheduled for ${tx.date}. Would it be possible to extend the due date by 3–4 days to align with our incoming receipts?\n\nThank you very much for your flexibility.\n\nBest regards,\nKERNES CFO`;
    draftSourceNote.textContent = "Supplier extension draft · editable, sent manually by you";
    state.draftEdited = true;
    replayFade(draftTextarea);
  }

  requestAnimationFrame(() => {
    document.querySelector("#actions-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function syncSimulationsAndRender() {
  state.whatIfOverlay = buildCombinedWhatIfOverlay(state);
  if (state.whatIfOverlay) {
    if (whatIfChartLabel) whatIfChartLabel.textContent = `${state.whatIfOverlay.label} plotted on the cash chart.`;
    if (whatIfChartBanner) whatIfChartBanner.hidden = false;
  } else if (whatIfChartBanner) {
    whatIfChartBanner.hidden = true;
  }
  if (state.forecast) renderAll();
}

function addPlannedPurchase({ name, amountMinor, date }) {
  const existing = state.plannedPurchases.find(
    (p) => p.name.toLowerCase() === name.toLowerCase() && p.date === date,
  );
  if (existing) {
    existing.amountMinor = amountMinor;
    existing.enabled = true;
  } else {
    state.plannedPurchases.push({
      id: `buy-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      amountMinor,
      date,
      enabled: true,
    });
  }
  syncSimulationsAndRender();
}

const simBarCallbacks = {
  onTogglePurchase(id) {
    const item = state.plannedPurchases.find((p) => p.id === id);
    if (!item) return;
    item.enabled = !item.enabled;
    syncSimulationsAndRender();
  },
  onRemovePurchase(id) {
    state.plannedPurchases = state.plannedPurchases.filter((p) => p.id !== id);
    syncSimulationsAndRender();
  },
  onToggleEarlyPay() {
    if (!state.earlyPaySim || !state.forecast) return;
    state.earlyPaySim.enabled = !state.earlyPaySim.enabled;
    state.forecast = {
      ...state.forecast,
      scenario: state.earlyPaySim.enabled ? state.earlyPaySim.scenario : null,
    };
    syncSimulationsAndRender();
  },
  onRemoveEarlyPay() {
    state.earlyPaySim = null;
    if (state.forecast) {
      state.forecast = { ...state.forecast, scenario: null };
    }
    syncSimulationsAndRender();
  },
  onToggleCustomWhatIf() {
    if (!state.customWhatIf) return;
    state.customWhatIf.enabled = !state.customWhatIf.enabled;
    syncSimulationsAndRender();
  },
  onRemoveCustomWhatIf() {
    state.customWhatIf = null;
    syncSimulationsAndRender();
  },
  onRemoveStress() {
    state.showStress = false;
    toggleStressBtn?.classList.remove("is-active");
    toggleStressBtn?.setAttribute("aria-pressed", "false");
    syncSimulationsAndRender();
  },
  onResetBuffer() {
    state.simulationDecision = null;
    state.simulationOutcome = null;
    syncSimulationsAndRender();
  },
};

simAddPurchaseBtn?.addEventListener("click", () => {
  workspace.setWorkspace("whatif", "#afford-card");
  requestAnimationFrame(() => document.querySelector("#afford-name-input")?.focus());
});

simResetAllBtn?.addEventListener("click", () => {
  state.plannedPurchases = [];
  state.earlyPaySim = null;
  state.customWhatIf = null;
  state.showStress = false;
  toggleStressBtn?.classList.remove("is-active");
  toggleStressBtn?.setAttribute("aria-pressed", "false");
  state.simulationDecision = null;
  state.simulationOutcome = null;
  if (state.forecast) {
    state.forecast = { ...state.forecast, scenario: null };
  }
  syncSimulationsAndRender();
});

function renderAll() {
  setupScreen.hidden = true;
  resultsSection.hidden = false;
  changeFileBtn.hidden = false;
  if (printReportBtn) printReportBtn.hidden = false;
  renderKpis(state);
  renderLedgerAndChart(state);
  renderCashBreakdown(state);
  renderSmartCalendar(state, state.calendarFilter, handleQuickTransactionAction);
  renderProposalPanel(state);
  renderActiveSimsBar(state, simBarCallbacks);
}

function applyTemplateDraft({ force = false } = {}) {
  if (!state.forecast || (!force && state.draftEdited)) return;
  if (state.forecast.forecast_basis === "history") {
    reminderSubjectInput.value = "";
    draftTextarea.value = "";
    return;
  }
  const { subject, body } = buildReminderTemplate(state, scenarioForm);
  reminderSubjectInput.value = subject;
  draftTextarea.value = body;
  draftSourceNote.textContent = "Template for selected payment · editable, sent manually by you";
  replayFade(draftTextarea);
  replayFade(draftSourceNote);
}

function validateCsvUpload(file, text) {
  if (file && file.size > 1_000_000) {
    throw new Error("This file is larger than 1 MB. Export a shorter date range as CSV and try again.");
  }
  const name = (file?.name || "").toLowerCase();
  if (name && /\.(pdf|xlsx?|docx?|png|jpe?g|zip|json|xml)$/.test(name)) {
    throw new Error(
      "Please upload a plain CSV file (.csv). Spreadsheet, PDF, or image files can't be imported directly.",
    );
  }
  if (!text || !text.trim()) {
    throw new Error("This file is empty. Choose a semicolon-delimited bank CSV file.");
  }
  if (/\x00/.test(text)) {
    throw new Error(
      "This file doesn't look like plain text CSV. Export a CSV from your bank or spreadsheet and try again.",
    );
  }
  const firstLine = text.replace(/^\uFEFF/, "").trimStart().split(/\r?\n/, 1)[0] || "";
  if (!firstLine.includes(";")) {
    throw new Error(
      "Unsupported CSV format. Upload a semicolon-delimited bank statement CSV (Pizzeria Amalfi standard).",
    );
  }
}

function pickDecisionBaseline(forecast) {
  const insightBaseline = buildInsightPayload(forecast)?.baseline;
  if (insightBaseline?.first_deficit) return insightBaseline;

  const allDays = forecast?.baseline?.days || [];
  if (allDays.length < 14) return forecast?.baseline ?? null;

  const peakDate = forecast?.proposal?.deepest_shortfall?.date || forecast?.baseline?.first_deficit?.date;
  const peakIdx = peakDate ? allDays.findIndex((d) => d.date === peakDate) : 0;
  const startIdx = Math.max(0, Math.min(allDays.length - 14, peakIdx > 0 ? peakIdx - 6 : 0));
  const slice = allDays.slice(startIdx, startIdx + 14).map(({ date, balance_minor }) => ({
    date,
    balance_minor: Math.trunc(Number(balance_minor)),
  }));
  const firstNeg = slice.find((d) => d.balance_minor < 0);
  return {
    days: slice,
    first_deficit: firstNeg ? { date: firstNeg.date, shortfall_minor: -firstNeg.balance_minor } : null,
  };
}

async function fetchAdvice({ forceDraft = false } = {}) {
  const payload = buildInsightPayload(state.forecast);
  if (!state.forecast || !payload || !state.proposal) return;

  const reqId = ++state.adviceRequestId;
  adviceLoading.hidden = false;
  adviceError.hidden = true;
  adviceError.className = "inline-alert inline-alert-soft";
  retryAdviceBtn.hidden = true;
  explanationEl.hidden = true;
  adviceModelEl.hidden = true;

  try {
    const data = await requestAdvice(payload);
    if (reqId !== state.adviceRequestId) return;

    state.advice = data;
    explanationEl.textContent = data.explanation;
    explanationEl.hidden = false;
    replayFade(explanationEl);
    adviceModelEl.textContent = data.model;
    adviceModelEl.hidden = !data.model;
    if (state.forecast.forecast_basis !== "history" && data.email_draft && (forceDraft || !state.draftEdited)) {
      draftTextarea.value = data.email_draft;
      draftSourceNote.textContent = "Drafted by AI · editable, sent manually by you";
      replayFade(draftTextarea);
      replayFade(draftSourceNote);
    }
    adviceWrap.hidden = false;
    adviceButton.textContent = "Regenerate draft";
    return data;
  } catch (error) {
    if (reqId !== state.adviceRequestId) return null;
    if (error?.status === 422) {
      state.advicePreviewOnly = true;
      adviceError.className = "inline-alert inline-alert-soft";
      adviceError.textContent =
        "AI explanation is not available for this forecast in preview mode. You can still review the projected balances and test a decision.";
      adviceError.hidden = false;
      retryAdviceBtn.hidden = true;
    } else {
      adviceError.className = "inline-alert inline-alert-warn";
      const titleEl = document.createElement("strong");
      titleEl.className = "alert-title";
      titleEl.textContent = "AI explanation is temporarily unavailable";
      const msgEl = document.createElement("span");
      msgEl.textContent =
        "Your cash numbers and suggested safety buffer are calculated accurately and ready to test below.";
      adviceError.replaceChildren(titleEl, msgEl);
      adviceError.hidden = false;
      retryAdviceBtn.hidden = false;
    }
    if (forceDraft) {
      applyTemplateDraft({ force: true });
    }
    return null;
  } finally {
    if (reqId === state.adviceRequestId) {
      adviceLoading.hidden = true;
    }
  }
}

async function loadForecastSetup() {
  const selectedFile = fileInput.files?.[0];
  if (selectedFile) {
    const csvText = await selectedFile.text();
    validateCsvUpload(selectedFile, csvText);
    const defaults = extractCsvDefaults(csvText, HORIZON_DAYS);
    if (defaults.openingBalanceMinor === null) {
      const instructions = `Enter the account balance before any payments on ${printDate(defaults.startDate)}.`;
      csvOpeningBalanceHint.textContent = instructions;
      csvOpeningBalanceGroup.hidden = false;
      if (!csvOpeningBalance.value.trim()) {
        csvOpeningBalance.focus();
        throw new Error(`We couldn't reconstruct the opening balance from this CSV. ${instructions}`);
      }
      defaults.openingBalanceMinor = Number(toMinor(csvOpeningBalance.value));
      defaults.balanceSourceLabel = "Custom balance";
    }
    return { csvFile: selectedFile, ...defaults };
  }

  const response = await request(sampleDownloadLink.href);
  return {
    csvFile: new File([await response.blob()], sampleDownloadLink.download, { type: "text/csv" }),
    openingBalanceMinor: AMALFI_OPENING_BALANCE_MINOR,
    startDate: AMALFI_FORECAST_START_DATE,
    balanceSourceLabel: "2025 closing balance",
  };
}

async function runBaselineForecast({ customOpeningMinor = null } = {}) {
  const submitBtn = document.querySelector("#run-forecast-btn");
  submitBtn.disabled = true;
  showStatus("Checking your upcoming cash…");

  try {
    const editingBalance = customOpeningMinor !== null && state.csvFile;
    const recordedHistory = state.forecast?.history_days;
    const setup = editingBalance
      ? {
          csvFile: state.csvFile,
          startDate: state.startDate,
          openingBalanceMinor: customOpeningMinor,
          balanceSourceLabel: "Custom balance",
        }
      : await loadForecastSetup();
    const data = await resolveForecast(setup);
    if (editingBalance) data.history_days = recordedHistory;

    Object.assign(state, setup);
    state.profile = {
      business_type: businessTypeInput?.value.trim() || "",
      goal: businessGoalInput?.value.trim() || "",
      experience_level: "beginner",
    };
    state.horizonDays = HORIZON_DAYS;
    if (inlineBalanceForm) inlineBalanceForm.hidden = true;
    if (editBalanceBtn) editBalanceBtn.hidden = false;
    state.forecast = data;
    const estimatedFromHistory = data.forecast_basis === "history";
    setForecastOverlay(!estimatedFromHistory);
    toggleForecastBtn.hidden = estimatedFromHistory;
    toggleForecastBtn.disabled = estimatedFromHistory;
    state.adviceRequestId += 1;
    adviceLoading.hidden = true;
    adviceError.hidden = true;
    adviceError.className = "inline-alert inline-alert-soft";
    adviceError.replaceChildren();
    retryAdviceBtn.hidden = true;
    explanationEl.hidden = true;
    adviceModelEl.hidden = true;
    state.proposal = readProposal(data);
    state.simulationDecision = null;
    state.simulationOutcome = null;
    state.whatIfOverlay = null;
    state.plannedPurchases = [];
    state.earlyPaySim = null;
    state.customWhatIf = null;
    state.showStress = false;
    toggleStressBtn?.classList.remove("is-active");
    toggleStressBtn?.setAttribute("aria-pressed", "false");
    state.advice = null;
    state.advicePreviewOnly = false;
    state.draftEdited = false;
    adviceWrap.hidden = false;
    adviceButton.textContent = "Regenerate draft";
    copyFeedback.textContent = "";
    reminderReceipt.hidden = true;
    reminderError.hidden = true;

    populateIncomingPayments(state, scenarioForm);
    applyTemplateDraft({ force: true });
    setActiveTab(state.proposal ? "credit" : "whatif");
    workspace.setWorkspace("overview");
    affordSandbox.syncDateBounds();
    renderSignalStripBase(state);
    showStatus("");
    renderAll();

    const insightsPromise = loadInsights();
    const advicePromise = state.proposal
      ? fetchAdvice({ forceDraft: false })
      : Promise.resolve(null);
    const combinedPromise = Promise.all([insightsPromise, advicePromise]).then(([ins, adv]) => ({
      ...(ins || {}),
      advice: adv,
    }));
    renderActionPlan({
      state,
      insightsPromise: combinedPromise,
      onOpenEmailTab: data.forecast_basis === "history"
        ? null
        : (step) => {
            workspace.setWorkspace("actions");
            setActiveTab("whatif");
            if (step?.email_draft) {
              draftTextarea.value = step.email_draft;
              if (step.counterparty) {
                reminderSubjectInput.value =
                  step.email_kind === "defer_supplier"
                    ? `Short payment extension request: ${step.counterparty}`
                    : `Early payment request: ${step.counterparty}`;
              }
              draftSourceNote.textContent = "Drafted for your action plan · editable, sent manually by you";
              state.draftEdited = true;
              replayFade(draftTextarea);
            }
            requestAnimationFrame(() => {
              document.querySelector("#actions-heading")?.scrollIntoView({ behavior: "smooth", block: "start" });
            });
          },
    });
  } catch (error) {
    showStatus(formatCsvError(error.message), true);
    if (resultsSection.hidden) {
      statusBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } finally {
    submitBtn.disabled = false;
  }
}

// Return to Step 1 (Upload / Settings) & Export Brief
changeFileBtn.addEventListener("click", showSetupScreen);
printReportBtn?.addEventListener("click", () => window.print());

// Tabs
tabCredit.addEventListener("click", () => setActiveTab("credit"));
tabWhatIf.addEventListener("click", () => setActiveTab("whatif"));

// Smart Cash Calendar Filters
for (const chip of calendarFilterChips) {
  chip.addEventListener("click", () => {
    state.calendarFilter = chip.dataset.calFilter || "all";
    for (const c of calendarFilterChips) {
      const isMatch = c === chip;
      c.classList.toggle("is-active", isMatch);
      c.setAttribute("aria-pressed", String(isMatch));
    }
    if (state.forecast) {
      renderSmartCalendar(state, state.calendarFilter, handleQuickTransactionAction);
    }
  });
}

// Load the backend insight milestones in parallel without blocking the main forecast
function previewCollectAction(action) {
  if (!action || !scenarioForm.elements.move_transaction_id) return;
  scenarioForm.elements.move_transaction_id.value = action.transaction_id;
  scenarioForm.elements.move_to_date.value = action.new_date;
  applyTemplateDraft();
  workspace.setWorkspace("actions");
  setActiveTab("whatif");
  requestAnimationFrame(() => {
    document.querySelector("#actions-heading")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  scenarioForm.requestSubmit();
}

async function loadInsights() {
  const reqId = ++state.insightsRequestId;
  resetInsightsUi();

  const payload = buildInsightPayload(state.forecast);
  if (!payload) return null;

  const currency = state.forecast.currency ?? "EUR";
  const hasShortfall = Boolean(payload.baseline.first_deficit);

  const [anomaliesRes, compareRes, stressRes, creditRes, optimizeRes] = await Promise.allSettled([
    state.forecast.forecast_basis === "history" ? Promise.resolve(null) : requestAnomalies(payload),
    requestCompareOptions(payload),
    requestStressTest(payload),
    hasShortfall ? requestCreditCheck(payload) : Promise.resolve(null),
    requestOptimizePayments(payload),
  ]);

  if (reqId !== state.insightsRequestId || !state.forecast) return null;

  const anomalies = anomaliesRes.status === "fulfilled" ? anomaliesRes.value : null;
  const compare = compareRes.status === "fulfilled" ? compareRes.value : null;
  const stress = stressRes.status === "fulfilled" ? stressRes.value : null;
  const credit = creditRes.status === "fulfilled" ? creditRes.value : null;
  const optimize = optimizeRes.status === "fulfilled" ? optimizeRes.value : null;

  if (anomalies) {
    renderAnomalies(anomalies, currency);
  }
  if (compare) {
    renderCompareOptions(compare, currency);
  }
  if (stress) {
    renderStressTest(stress, currency);
  }
  if (!hasShortfall) {
    renderHealthyCreditScore();
  } else if (credit) {
    renderCreditCheck(credit, currency);
  }
  if (optimize) {
    renderOptimizePayments(
      optimize,
      state.forecast.transactions,
      currency,
      previewCollectAction,
    );
  }
  populateDelayCandidates(state.forecast, currency);
  updateSignalStripInsights({
    forecast: state.forecast,
    insights: { anomalies, compare, stress, credit, optimize },
  });
  return { anomalies, compare, stress, credit, optimize };
}

function setWhatIfMode(mode) {
  const isAsk = mode === "ask";
  whatIfModeAskBtn?.classList.toggle("is-active", isAsk);
  whatIfModeAskBtn?.setAttribute("aria-selected", String(isAsk));
  whatIfModeDelayBtn?.classList.toggle("is-active", !isAsk);
  whatIfModeDelayBtn?.setAttribute("aria-selected", String(!isAsk));
  if (whatIfPanelAsk) whatIfPanelAsk.hidden = !isAsk;
  if (whatIfPanelDelay) whatIfPanelDelay.hidden = isAsk;
}

function showWhatIfOverlay(label, days) {
  if (!days) return;
  state.customWhatIf = { label, days, enabled: true };
  syncSimulationsAndRender();
}

function clearWhatIfOverlay() {
  state.plannedPurchases = [];
  state.customWhatIf = null;
  syncSimulationsAndRender();
}

whatIfModeAskBtn?.addEventListener("click", () => setWhatIfMode("ask"));
whatIfModeDelayBtn?.addEventListener("click", () => setWhatIfMode("delay"));

function setForecastOverlay(enabled) {
  state.showForecast = enabled;
  toggleForecastBtn.classList.toggle("is-active", enabled);
  toggleForecastBtn.setAttribute("aria-pressed", String(enabled));
}

toggleForecastBtn.addEventListener("click", () => {
  setForecastOverlay(!state.showForecast);
  if (state.forecast) renderLedgerAndChart(state);
});

toggleStressBtn?.addEventListener("click", () => {
  state.showStress = !state.showStress;
  toggleStressBtn.classList.toggle("is-active", state.showStress);
  toggleStressBtn.setAttribute("aria-pressed", String(state.showStress));
  syncSimulationsAndRender();
});

clearWhatIfOverlayBtn?.addEventListener("click", clearWhatIfOverlay);
clearWhatIfCardBtn?.addEventListener("click", clearWhatIfOverlay);
scrollToChartBtn?.addEventListener("click", () => {
  workspace.setWorkspace("overview", "#chart-heading");
});

// Ask the CFO (Milestone 1)
async function askCfoCore(question) {
  const payload = buildInsightPayload(state.forecast);
  if (!payload) {
    throw new Error("Questions require at least 14 days in your forecast.");
  }
  const data = await requestAskCfo(payload, question);
  renderAskAnswer(data, state.forecast.currency ?? "EUR");
  if (data.what_if) {
    const curveDays = buildWhatIfCurve(state.forecast.baseline.days, state.forecast.transactions, {
      transactionId: data.what_if.transaction_id,
      newAmountMinor: data.what_if.new_amount_minor,
      newDate: data.what_if.new_date,
    });
    showWhatIfOverlay("What-if scenario", curveDays);
  }
  return data;
}

async function submitAskQuestion(question) {
  const trimmed = String(question || "").trim();
  if (!trimmed || !state.forecast) return;

  askBtn.disabled = true;
  askBtn.textContent = "Checking…";
  askLoading.hidden = false;
  document.querySelector("#ask-answer-box").hidden = true;
  document.querySelector("#ask-error").hidden = true;
  try {
    await askCfoCore(trimmed);
  } catch (error) {
    renderAskError(
      error.status === 503
        ? "Free-form questions need the live AI model on OpenShift AI. Right now the server is running in local preview mode."
        : error.message,
    );
  } finally {
    askLoading.hidden = true;
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
  const delayDays = Number.parseInt(delayDaysInput.value, 10);
  if (!txId || !Number.isFinite(delayDays) || delayDays < 1 || delayDays > 365) {
    renderDelayError("Enter a delay between 1 and 365 days.");
    return;
  }

  delayPredictBtn.disabled = true;
  delayPredictBtn.textContent = "Checking…";
  delayLoading.hidden = false;
  document.querySelector("#delay-result-box").hidden = true;
  document.querySelector("#delay-error").hidden = true;
  try {
    const data = await requestPredictDelays(payload, { [txId]: delayDays });
    renderDelayResult(data);
    const curveDays = buildWhatIfCurve(state.forecast.baseline.days, state.forecast.transactions, {
      transactionId: txId,
      delayDays,
    });
    showWhatIfOverlay(`If ${txId} +${delayDays}d late`, curveDays);
  } catch (error) {
    renderDelayError(
      error.status === 503
        ? "The AI assistant is temporarily unavailable. Your main numbers and safety buffer estimate are still ready above."
        : error.message,
    );
  } finally {
    delayLoading.hidden = true;
    delayPredictBtn.disabled = false;
    delayPredictBtn.textContent = "Check late impact →";
  }
});

// File upload & drag-and-drop
fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  csvOpeningBalance.value = "";
  csvOpeningBalanceGroup.hidden = true;
  sampleHint.hidden = Boolean(file);
  useSampleBtn.hidden = !file;
  fileNameEl.textContent = file
    ? `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`
    : sampleFileLabel;
});

useSampleBtn.addEventListener("click", () => {
  fileInput.value = "";
  fileInput.dispatchEvent(new Event("change"));
  showStatus("");
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

// Forecast controls
forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runBaselineForecast();
});

// What-if scenario comparison
scenarioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.forecast) return;

  const { baseline, history_days: recordedHistory } = state.forecast;
  const btn = document.querySelector("#compare-dates-btn");
  btn.disabled = true;
  showStatus("Testing earlier payment date…");
  try {
    const moveTxId = scenarioForm.elements.move_transaction_id.value;
    const moveToDate = scenarioForm.elements.move_to_date.value;
    const data = await resolveForecast({
      csvFile: state.csvFile,
      openingBalanceMinor: state.openingBalanceMinor,
      startDate: state.startDate,
      moveTransactionId: moveTxId,
      moveToDate,
    });
    if (state.forecast?.baseline !== baseline) return;
    state.forecast = { ...data, history_days: recordedHistory };
    const movedTx = (data.transactions || []).find((tx) => tx.id === moveTxId);
    if (movedTx && data.scenario) {
      state.earlyPaySim = {
        txId: movedTx.id,
        label: movedTx.counterparty || movedTx.label || moveTxId,
        amountMinor: Math.max(0, Number(movedTx.amount_minor || 0)),
        originalDate: movedTx.date,
        newDate: moveToDate,
        enabled: true,
        scenario: data.scenario,
      };
    }
    showStatus("");
    syncSimulationsAndRender();
  } catch (error) {
    if (state.forecast?.baseline === baseline) showStatus(error.message, true);
  } finally {
    btn.disabled = false;
  }
});

document.querySelector("#clear-scenario-btn").addEventListener("click", () => {
  if (!state.forecast) return;
  state.earlyPaySim = null;
  state.forecast = { ...state.forecast, scenario: null };
  syncSimulationsAndRender();
});

// Human decision simulation controls
const approveButton = document.querySelector("#approve-sim-btn");
const rejectButton = document.querySelector("#reject-sim-btn");

async function simulateDecision(decision) {
  if (!state.proposal || !state.forecast) return null;
  const baseline = state.forecast.baseline;
  const decisionBaseline = pickDecisionBaseline(state.forecast);
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    const outcome = await requestDecision({ baseline: decisionBaseline, decision });
    if (state.forecast?.baseline !== baseline) return null;
    state.simulationDecision = outcome.decision;
    state.simulationOutcome = outcome;
    showStatus("");
    renderAll();
    return outcome;
  } catch (error) {
    if (state.forecast?.baseline === baseline) showStatus(error.message, true);
    return null;
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
  if (state.proposal && !state.advicePreviewOnly) {
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
    const badge = document.createElement("span");
    badge.className = "autonomy-badge level-4-dark";
    badge.textContent = "Simulation only — nothing sent";
    const title = document.createElement("strong");
    title.textContent = "Simulated · Nothing sent";
    const meta = document.createElement("span");
    meta.textContent = `To: ${data.recipient} · Subject: ${data.subject}`;
    const msg = document.createElement("span");
    msg.textContent = data.message;
    reminderReceipt.replaceChildren(badge, title, meta, msg);
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

// Screen 1 Onboarding Question Chips (never auto-filled)
function syncPromptChipsFor(target, value) {
  const clean = String(value || "").trim();
  for (const chip of promptChips) {
    if (chip.dataset.questionTarget !== target) continue;
    const matched = clean !== "" && chip.dataset.value === clean;
    chip.classList.toggle("is-selected", matched);
    chip.setAttribute("aria-pressed", String(matched));
  }
}

if (businessTypeInput) {
  businessTypeInput.value = "";
  businessTypeInput.addEventListener("input", () => syncPromptChipsFor("business", businessTypeInput.value));
}
if (businessGoalInput) {
  businessGoalInput.value = "";
  businessGoalInput.addEventListener("input", () => syncPromptChipsFor("goal", businessGoalInput.value));
}

for (const chip of promptChips) {
  chip.setAttribute("aria-pressed", "false");
  chip.addEventListener("click", () => {
    const target = chip.dataset.questionTarget;
    const val = chip.dataset.value || "";
    const input = target === "business" ? businessTypeInput : businessGoalInput;
    if (!input) return;
    input.value = input.value.trim() === val ? "" : val;
    syncPromptChipsFor(target, input.value);
  });
}

// Screen 2 inline opening balance editor
editBalanceBtn?.addEventListener("click", () => {
  if (!inlineBalanceForm || !inlineBalanceInput) return;
  const currentMinor = state.openingBalanceMinor ?? 500_000;
  inlineBalanceInput.value = (currentMinor / 100).toFixed(2);
  inlineBalanceForm.hidden = false;
  editBalanceBtn.hidden = true;
  inlineBalanceInput.focus();
  inlineBalanceInput.select();
});

cancelBalanceBtn?.addEventListener("click", () => {
  if (inlineBalanceForm) inlineBalanceForm.hidden = true;
  if (editBalanceBtn) editBalanceBtn.hidden = false;
});

inlineBalanceForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.csvFile || !inlineBalanceInput) return;
  try {
    const customOpeningMinor = Number(toMinor(inlineBalanceInput.value));
    await runBaselineForecast({ customOpeningMinor });
  } catch (error) {
    showStatus(error.message, true);
  }
});
