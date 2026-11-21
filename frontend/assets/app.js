import {
  AMALFI_DEFAULT_OPENING_EUR,
  AMALFI_SAMPLE_CSV,
  AMALFI_SAMPLE_FILENAME,
} from "./sample-amalfi.js?v=tc11";
import {
  buildInsightPayload,
  formatCsvError,
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
import { renderActionPlan } from "./js/action_plan.js?v=tc16";
import { printMoney, replayFade, toMinor } from "./js/format.js?v=tc11";
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
} from "./js/insights.js?v=tc11";
import { buildWhatIfCurve, addDaysIso } from "./js/predictions.js?v=tc20";
import { readProposal } from "./js/proposal.js?v=tc11";
import {
  buildReminderTemplate,
  populateIncomingPayments,
  renderKpis,
  renderLedgerAndChart,
  renderProposalPanel,
} from "./js/render.js?v=tc22";

const HORIZON_DAYS = 14;

const forecastForm = document.querySelector("#forecast-form");
const businessTypeInput = document.querySelector("#business-type-input");
const businessGoalInput = document.querySelector("#business-goal-input");
const promptChips = document.querySelectorAll(".prompt-chip");
const scenarioForm = document.querySelector("#scenario-form");
const fileInput = document.querySelector("#csv-file");
const fileDropzone = document.querySelector("#file-dropzone");
const fileNameEl = document.querySelector("#file-name");
const downloadSampleBtn = document.querySelector("#download-sample-btn");
const editBalanceBtn = document.querySelector("#edit-balance-btn");
const inlineBalanceForm = document.querySelector("#inline-balance-form");
const inlineBalanceInput = document.querySelector("#inline-balance-input");
const cancelBalanceBtn = document.querySelector("#cancel-balance-btn");

const statusBanner = document.querySelector("#status");
const resultsStatusBanner = document.querySelector("#results-status");
const setupScreen = document.querySelector("#setup-screen");
const resultsSection = document.querySelector("#results");
const changeFileBtn = document.querySelector("#change-file-btn");
const toggleAllDetailsBtn = document.querySelector("#toggle-all-details-btn");
const detailAccordions = Array.from(document.querySelectorAll(".detail-accordion"));
const accCompare = document.querySelector("#acc-compare");
const accComparePill = document.querySelector("#acc-compare-pill");
const accHealth = document.querySelector("#acc-health");
const accHealthPill = document.querySelector("#acc-health-pill");
const accOptimize = document.querySelector("#acc-optimize");
const accOptimizePill = document.querySelector("#acc-optimize-pill");
const accAnomalies = document.querySelector("#acc-anomalies");
const accAnomaliesPill = document.querySelector("#acc-anomalies-pill");

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
const askChips = document.querySelectorAll(".ask-chip");
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
};

function showStatus(message, isError = false) {
  const activeBanner = resultsSection.hidden ? statusBanner : resultsStatusBanner;
  const inactiveBanner = resultsSection.hidden ? resultsStatusBanner : statusBanner;
  inactiveBanner.hidden = true;
  activeBanner.textContent = message;
  activeBanner.classList.toggle("error", isError);
  activeBanner.hidden = !message;
}

function syncDetailToggleControls() {
  const visible = detailAccordions.filter((acc) => !acc.hidden);
  const allOpen = visible.length > 0 && visible.every((acc) => acc.open);

  if (toggleAllDetailsBtn) {
    toggleAllDetailsBtn.textContent = allOpen ? "Collapse all" : "Expand all";
  }
}

function setAllAccordions(openBool) {
  for (const acc of detailAccordions) {
    acc.open = Boolean(openBool);
  }
  syncDetailToggleControls();
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

function renderAll() {
  setupScreen.hidden = true;
  resultsSection.hidden = false;
  changeFileBtn.hidden = false;
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
    if (data.email_draft && (forceDraft || !state.draftEdited)) {
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
        "AI explanation is not available for this forecast in preview mode. Your server cash numbers, decision preview, and editable email draft below are ready.";
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

function splitSemicolonCsvLine(line) {
  const cols = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ";" && !inQuotes) {
      cols.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  cols.push(cur.trim());
  return cols;
}

function parseBankDateIso(raw) {
  const s = String(raw || "").trim();
  const dot = /^(\d{2})\.(\d{2})\.(\d{2}|\d{4})$/.exec(s);
  if (dot) {
    const day = Number(dot[1]);
    const month = Number(dot[2]);
    const year = dot[3].length === 2 ? Number(`20${dot[3]}`) : Number(dot[3]);
    const dt = new Date(Date.UTC(year, month - 1, day));
    if (dt.getUTCFullYear() === year && dt.getUTCMonth() === month - 1 && dt.getUTCDate() === day) {
      return dt.toISOString().slice(0, 10);
    }
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const dt = new Date(`${s}T00:00:00Z`);
    if (!Number.isNaN(dt.getTime()) && dt.toISOString().slice(0, 10) === s) {
      return s;
    }
  }
  return null;
}

function parseBankMinorSafe(raw) {
  const normalized = String(raw || "")
    .trim()
    .replace(/[\s\u00a0]/g, "")
    .replace(/\.(?=\d{3}(?:,|$))/g, "")
    .replace(",", ".");
  if (!/^[+-]?\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  try {
    return BigInt(toMinor(normalized));
  } catch {
    return null;
  }
}

function extractCsvDefaults(csvText, { isSample = false } = {}) {
  const lines = String(csvText || "")
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "");
  const headers = lines.length > 0 ? splitSemicolonCsvLine(lines[0]).map((h) => h.toLowerCase()) : [];

  const idxOf = (...candidates) => {
    for (const c of candidates) {
      const idx = headers.indexOf(c);
      if (idx !== -1) return idx;
    }
    return -1;
  };

  const valDateIdx = idxOf("value date");
  const bookDateIdx = idxOf("booking date");
  const amountIdx = idxOf("amount");
  const balanceIdx = idxOf("balance", "saldo", "closing balance", "running balance");

  const rows = [];
  let latestDateIso = null;

  for (let i = 1; i < lines.length; i += 1) {
    const cols = splitSemicolonCsvLine(lines[i]);
    const iso =
      (valDateIdx !== -1 ? parseBankDateIso(cols[valDateIdx]) : null) ||
      (bookDateIdx !== -1 ? parseBankDateIso(cols[bookDateIdx]) : null);
    if (!iso) continue;

    if (!latestDateIso || iso > latestDateIso) {
      latestDateIso = iso;
    }
    rows.push({
      iso,
      amountMinor: amountIdx !== -1 ? parseBankMinorSafe(cols[amountIdx]) : null,
      balanceMinor: balanceIdx !== -1 ? parseBankMinorSafe(cols[balanceIdx]) : null,
    });
  }

  // Anchor the 14-day window so its last day always equals the latest CSV date (chart divider).
  const startDate = latestDateIso
    ? addDaysIso(latestDateIso, -(HORIZON_DAYS - 1))
    : new Date().toISOString().slice(0, 10);
  const endDate = latestDateIso || addDaysIso(startDate, HORIZON_DAYS - 1);

  let openingBalanceMinor = null;
  let balanceSourceLabel = "";

  // 1. Prefer an explicit Balance/Saldo column if the bank CSV includes one.
  const preWindowRows = rows.filter((r) => r.iso < startDate && r.balanceMinor !== null);
  const windowBalanceRows = rows.filter((r) => r.balanceMinor !== null);
  if (preWindowRows.length > 0) {
    preWindowRows.sort((a, b) => (a.iso < b.iso ? -1 : a.iso > b.iso ? 1 : 0));
    openingBalanceMinor = Number(preWindowRows[preWindowRows.length - 1].balanceMinor);
    balanceSourceLabel = "From CSV balance";
  } else if (windowBalanceRows.length > 0) {
    openingBalanceMinor = Number(windowBalanceRows[0].balanceMinor);
    balanceSourceLabel = "From CSV balance";
  } else if (isSample) {
    // 2. Canonical bundled Amalfi sample synced opening balance.
    openingBalanceMinor = Number(toMinor(AMALFI_DEFAULT_OPENING_EUR));
    balanceSourceLabel = "Synced demo balance";
  } else {
    // 3. Auto-estimate an opening liquidity cushion (50% of 14-day inflows, rounded to 500.00, min 1,000.00).
    let inflowsMinor = 0n;
    for (const r of rows) {
      if (r.iso >= startDate && r.iso <= endDate && r.amountMinor !== null && r.amountMinor > 0n) {
        inflowsMinor += r.amountMinor;
      }
    }
    const half = inflowsMinor / 2n;
    const rounded = ((half + 25_000n) / 50_000n) * 50_000n;
    const clamped = rounded < 100_000n ? 100_000n : rounded;
    openingBalanceMinor = Number(clamped);
    balanceSourceLabel = "Auto-estimated balance";
  }

  return { startDate, openingBalanceMinor, balanceSourceLabel };
}

async function runBaselineForecast({ customOpeningMinor = null } = {}) {
  const submitBtn = document.querySelector("#run-forecast-btn");
  submitBtn.disabled = true;
  showStatus("Checking your upcoming cash…");

  try {
    if (customOpeningMinor !== null && state.csvFile) {
      state.openingBalanceMinor = customOpeningMinor;
      state.balanceSourceLabel = "Custom balance";
    } else {
      const selectedFile = fileInput.files?.[0] || null;
      const isSample = !selectedFile;
      const csvText = selectedFile ? await selectedFile.text() : AMALFI_SAMPLE_CSV;
      if (selectedFile) {
        validateCsvUpload(selectedFile, csvText);
      }
      state.csvFile =
        selectedFile || new File([AMALFI_SAMPLE_CSV], AMALFI_SAMPLE_FILENAME, { type: "text/csv" });

      const resolved = extractCsvDefaults(csvText, { isSample });
      state.openingBalanceMinor = resolved.openingBalanceMinor;
      state.balanceSourceLabel = resolved.balanceSourceLabel;
      state.startDate = resolved.startDate;
    }

    state.profile = {
      business_type: businessTypeInput?.value.trim() || "",
      goal: businessGoalInput?.value.trim() || "",
      experience_level: "beginner",
    };
    state.horizonDays = HORIZON_DAYS;
    if (inlineBalanceForm) inlineBalanceForm.hidden = true;
    if (editBalanceBtn) editBalanceBtn.hidden = false;

    const data = await resolveForecast({
      csvFile: state.csvFile,
      openingBalanceMinor: state.openingBalanceMinor,
      startDate: state.startDate,
    });

    state.forecast = data;
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
    setAllAccordions(false);
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
      onOpenEmailTab: () => {
        setActiveTab("whatif");
        document.querySelector("#actions-heading")?.scrollIntoView({ behavior: "smooth", block: "center" });
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

// Return to Step 1 (Upload / Settings)
changeFileBtn.addEventListener("click", showSetupScreen);

// Tabs
tabCredit.addEventListener("click", () => setActiveTab("credit"));
tabWhatIf.addEventListener("click", () => setActiveTab("whatif"));

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
  if (accCompare) accCompare.hidden = true;
  if (accHealth) accHealth.hidden = true;
  if (accOptimize) accOptimize.hidden = true;
  if (accAnomalies) accAnomalies.hidden = true;
  syncDetailToggleControls();

  const payload = buildInsightPayload(state.forecast);
  if (!payload) return null;

  const currency = state.forecast.currency ?? "EUR";
  const hasShortfall = Boolean(payload.baseline.first_deficit);

  const [anomaliesRes, compareRes, stressRes, creditRes, optimizeRes] = await Promise.allSettled([
    requestAnomalies(payload),
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
    if (accAnomalies) accAnomalies.hidden = false;
    if (accAnomaliesPill) {
      const count = anomalies.findings?.length || 0;
      accAnomaliesPill.textContent = count > 0 ? `${count} flagged` : "Looks clean";
      accAnomaliesPill.className = count > 0 ? "pill pill-warning" : "pill pill-success";
    }
  }
  if (compare) {
    renderCompareOptions(compare, currency);
    if (compare.options?.length > 0 && accCompare) {
      accCompare.hidden = false;
      if (accComparePill) {
        accComparePill.textContent = `${compare.options.length} options`;
      }
    }
  }
  if (stress) {
    renderStressTest(stress, currency);
  }
  if (!hasShortfall) {
    renderHealthyCreditScore();
  } else if (credit) {
    renderCreditCheck(credit, currency);
  }
  if (!hasShortfall || stress || credit) {
    if (accHealth) accHealth.hidden = false;
    if (accHealthPill) {
      accHealthPill.textContent = !hasShortfall
        ? "100 / 100 · Low risk"
        : credit
          ? `${credit.score} / 100 · ${credit.risk} risk`
          : `Buffer ${printMoney(stress.recommended_limit_minor, currency)}`;
    }
  }
  if (optimize) {
    renderOptimizePayments(
      optimize,
      state.forecast.transactions,
      currency,
      previewCollectAction,
    );
    if (accOptimize) accOptimize.hidden = false;
    if (accOptimizePill) {
      const moves = optimize.actions?.length || 0;
      accOptimizePill.textContent = moves > 0 ? `${moves} moves` : "None needed";
    }
  }
  populateDelayCandidates(state.forecast, currency);
  syncDetailToggleControls();
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
  state.whatIfOverlay = { label, days };
  if (whatIfChartLabel) whatIfChartLabel.textContent = `${label} plotted on the cash chart above.`;
  if (whatIfChartBanner) whatIfChartBanner.hidden = false;
  if (state.forecast) renderLedgerAndChart(state);
}

function clearWhatIfOverlay() {
  state.whatIfOverlay = null;
  if (whatIfChartBanner) whatIfChartBanner.hidden = true;
  if (state.forecast) renderLedgerAndChart(state);
}

whatIfModeAskBtn?.addEventListener("click", () => setWhatIfMode("ask"));
whatIfModeDelayBtn?.addEventListener("click", () => setWhatIfMode("delay"));

toggleForecastBtn?.addEventListener("click", () => {
  state.showForecast = !state.showForecast;
  toggleForecastBtn.classList.toggle("is-active", state.showForecast);
  toggleForecastBtn.setAttribute("aria-pressed", String(state.showForecast));
  if (state.forecast) renderLedgerAndChart(state);
});

toggleStressBtn?.addEventListener("click", () => {
  state.showStress = !state.showStress;
  toggleStressBtn.classList.toggle("is-active", state.showStress);
  toggleStressBtn.setAttribute("aria-pressed", String(state.showStress));
  if (state.forecast) renderLedgerAndChart(state);
});

clearWhatIfOverlayBtn?.addEventListener("click", clearWhatIfOverlay);
clearWhatIfCardBtn?.addEventListener("click", clearWhatIfOverlay);
scrollToChartBtn?.addEventListener("click", () => {
  document.querySelector("#chart-heading")?.scrollIntoView({ behavior: "smooth", block: "center" });
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
function downloadSampleCsv() {
  const blob = new Blob([AMALFI_SAMPLE_CSV], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = AMALFI_SAMPLE_FILENAME;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
downloadSampleBtn.addEventListener("click", downloadSampleCsv);

// Forecast controls
forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runBaselineForecast();
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
      openingBalanceMinor: state.openingBalanceMinor,
      startDate: state.startDate,
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

// Screen 2 Inline "Cash today" Editor
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

// Screen 2 Progressive Disclosure Accordions
for (const acc of detailAccordions) {
  acc.addEventListener("toggle", syncDetailToggleControls);
}

toggleAllDetailsBtn?.addEventListener("click", () => {
  const visible = detailAccordions.filter((acc) => !acc.hidden);
  const allOpen = visible.length > 0 && visible.every((acc) => acc.open);
  setAllAccordions(!allOpen);
});

syncDetailToggleControls();
