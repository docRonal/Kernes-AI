import { printDate, printMoney, replayFade } from "./format.js?v=tc9";

const ANOMALY_LABELS = {
  duplicate_payment: "Possible repeat charge",
  outlier_expense: "Unusually large payment",
  same_day_spike: "Busy payment day",
};

const FACTOR_LABELS = {
  repayment: "Money coming back in",
  coverage: "Days needed",
  duration: "Length of dip",
  depth: "Lowest balance",
  concentration: "Customer spread",
  delays: "Late-payment track record",
};

const RISK_META = {
  low: { label: "Low risk", pillClass: "pill pill-success", barClass: "score-bar-low" },
  medium: { label: "Medium risk", pillClass: "pill pill-warning", barClass: "score-bar-medium" },
  high: { label: "High risk", pillClass: "pill pill-danger", barClass: "score-bar-high" },
};

function createEl(tag, className, text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function resetInsightsUi() {
  const grid = document.querySelector("#health-stress-grid");
  grid?.classList.remove("is-expanded");

  const sections = [
    "#anomalies-card",
    "#compare-card",
    "#health-stress-grid",
    "#optimize-card",
    "#delay-predict-card",
  ];
  for (const sel of sections) {
    const el = document.querySelector(sel);
    if (el) el.hidden = true;
  }
  const hiddenIds = [
    "#ask-loading",
    "#ask-answer-box",
    "#ask-error",
    "#delay-loading",
    "#delay-result-box",
    "#delay-error",
    "#credit-explain-error",
    "#credit-factors-toggle",
    "#optimize-footer",
  ];
  for (const sel of hiddenIds) {
    const el = document.querySelector(sel);
    if (el) el.hidden = true;
  }
}

export function renderAnomalies(data, currency = "EUR") {
  const card = document.querySelector("#anomalies-card");
  const badge = document.querySelector("#anomalies-badge");
  const summary = document.querySelector("#anomalies-summary");
  const list = document.querySelector("#anomalies-list");

  const isReview = data.risk_flag === "review_recommended";
  badge.textContent = isReview ? "Review recommended" : "Looks clean";
  badge.className = isReview ? "pill pill-warning" : "pill pill-success";
  summary.textContent = data.summary || "";

  if (!data.findings || data.findings.length === 0) {
    list.replaceChildren(
      createEl(
        "div",
        "bento-tile insight-empty",
        "No repeat charges, unusual spikes, or extra-large payments detected in this 14-day window.",
      ),
    );
  } else {
    list.replaceChildren(
      ...data.findings.map((finding) => {
        const tile = createEl("article", "bento-tile anomaly-tile");
        const top = createEl("div", "anomaly-top");
        top.append(
          createEl("span", "anomaly-kind", ANOMALY_LABELS[finding.kind] || finding.kind),
          createEl("strong", "anomaly-amount", printMoney(finding.amount_minor, currency)),
        );
        const detail = createEl("p", "anomaly-detail", finding.detail);
        const meta = createEl(
          "span",
          "anomaly-meta",
          `${printDate(finding.date)} · ${finding.transaction_ids.join(", ")}`,
        );
        tile.append(top, detail, meta);
        return tile;
      }),
    );
  }

  card.hidden = false;
}

export function renderCompareOptions(data, currency = "EUR") {
  const card = document.querySelector("#compare-card");
  const grid = document.querySelector("#compare-grid");
  const explanation = document.querySelector("#compare-explanation");

  if (!data.options || data.options.length === 0) {
    card.hidden = true;
    return;
  }

  grid.replaceChildren(
    ...data.options.map((opt) => {
      const isRec = opt.option_kind === data.recommended_option;
      const col = createEl("article", `compare-tile${isRec ? " is-recommended" : ""}`);

      const head = createEl("div", "compare-head");
      head.append(createEl("h3", "compare-title", opt.title));
      if (isRec) {
        head.append(createEl("span", "pill pill-coral", "Recommended"));
      }

      const metrics = createEl("dl", "compare-metrics");
      const costWrap = document.createElement("div");
      costWrap.append(
        createEl("dt", "", "Estimated fee"),
        createEl("dd", "", printMoney(opt.estimated_cost_minor, currency)),
      );
      const creditWrap = document.createElement("div");
      creditWrap.append(
        createEl("dt", "", "Buffer needed"),
        createEl("dd", "", printMoney(opt.credit_needed_minor, currency)),
      );
      metrics.append(costWrap, creditWrap);

      const detail = createEl("p", "compare-detail", opt.detail);
      col.append(head, metrics, detail);
      return col;
    }),
  );

  explanation.textContent = data.explanation || "";
  explanation.hidden = !data.explanation;
  card.hidden = false;
}

export function renderCreditCheck(data, currency = "EUR") {
  const grid = document.querySelector("#health-stress-grid");
  const badge = document.querySelector("#credit-risk-badge");
  const scoreVal = document.querySelector("#credit-score-value");
  const scoreBar = document.querySelector("#credit-score-fill");
  const scoreNote = document.querySelector("#credit-score-note");
  const explainErrEl = document.querySelector("#credit-explain-error");
  const factorsList = document.querySelector("#credit-factors-list");
  const toggleBtn = document.querySelector("#credit-factors-toggle");

  const meta = RISK_META[data.risk] || RISK_META.medium;
  badge.textContent = meta.label;
  badge.className = meta.pillClass;

  scoreVal.textContent = String(data.score);
  scoreBar.style.width = `${Math.max(4, Math.min(100, data.score))}%`;
  scoreBar.className = `score-bar-fill ${meta.barClass}`;

  scoreNote.textContent =
    data.explanation ||
    `Calculated for a ${printMoney(data.limit_minor, currency)} buffer based on incoming payments, dip length, lowest balance, and customer spread.`;

  if (explainErrEl) {
    if (data.explanation_error) {
      explainErrEl.textContent =
        "AI commentary is temporarily offline, but your readiness score and factor breakdown above are calculated accurately.";
      explainErrEl.hidden = false;
    } else {
      explainErrEl.hidden = true;
    }
  }

  const factors = data.factors || [];
  let expanded = false;

  const renderFactorRows = () => {
    const visibleFactors = expanded ? factors : factors.slice(0, 3);
    factorsList.replaceChildren(
      ...visibleFactors.map((f) => {
        const li = createEl("li", "factor-row");
        const left = createEl("div", "factor-left");
        left.append(
          createEl("span", "factor-name", FACTOR_LABELS[f.name] || f.name),
          createEl("span", "factor-reason", f.reason),
        );
        const pts = createEl("strong", "factor-pts", `+${f.points}`);
        li.append(left, pts);
        return li;
      }),
    );
    grid.classList.toggle("is-expanded", expanded);
    if (factors.length > 3) {
      toggleBtn.textContent = expanded ? "Show fewer" : `Show all ${factors.length} factors`;
      toggleBtn.hidden = false;
    } else {
      toggleBtn.hidden = true;
    }
  };

  toggleBtn.onclick = () => {
    expanded = !expanded;
    renderFactorRows();
  };
  renderFactorRows();

  grid.hidden = false;
}

export function renderHealthyCreditScore() {
  const grid = document.querySelector("#health-stress-grid");
  const badge = document.querySelector("#credit-risk-badge");
  const scoreVal = document.querySelector("#credit-score-value");
  const scoreBar = document.querySelector("#credit-score-fill");
  const scoreNote = document.querySelector("#credit-score-note");
  const explainErrEl = document.querySelector("#credit-explain-error");
  const factorsList = document.querySelector("#credit-factors-list");
  const toggleBtn = document.querySelector("#credit-factors-toggle");

  badge.textContent = "Low risk";
  badge.className = "pill pill-success";
  scoreVal.textContent = "100";
  scoreBar.style.width = "100%";
  scoreBar.className = "score-bar-fill score-bar-low";
  scoreNote.textContent = "Your balance stays positive across all 14 days — no safety buffer is needed.";
  if (explainErrEl) explainErrEl.hidden = true;

  const healthyRows = [
    { name: "Cash cushion", reason: "Balance stays positive every day", pts: "+40" },
    { name: "Buffer needed", reason: "No temporary buffer required", pts: "+35" },
    { name: "Shortfall risk", reason: "Zero negative days projected", pts: "+25" },
  ];
  factorsList.replaceChildren(
    ...healthyRows.map((row) => {
      const li = createEl("li", "factor-row");
      const left = createEl("div", "factor-left");
      left.append(
        createEl("span", "factor-name", row.name),
        createEl("span", "factor-reason", row.reason),
      );
      const pts = createEl("strong", "factor-pts", row.pts);
      li.append(left, pts);
      return li;
    }),
  );

  grid.classList.remove("is-expanded");
  toggleBtn.hidden = true;
  toggleBtn.onclick = null;
  grid.hidden = false;
}

export function renderStressTest(data, currency = "EUR") {
  const grid = document.querySelector("#health-stress-grid");
  const recValue = document.querySelector("#stress-rec-limit");
  const bufferSub = document.querySelector("#stress-buffer-sub");
  const list = document.querySelector("#stress-scenarios-list");

  recValue.textContent = printMoney(data.recommended_limit_minor, currency);
  bufferSub.textContent =
    data.buffer_minor > 0
      ? `Includes +${printMoney(data.buffer_minor, currency)} extra safety cushion over your main estimate.`
      : "Your main safety buffer already covers all what-if scenarios.";

  list.replaceChildren(
    ...(data.scenarios || []).map((sc) => {
      const li = createEl("li", "stress-row");
      const left = createEl("div", "stress-left");
      left.append(
        createEl("strong", "stress-name", sc.description),
        createEl(
          "span",
          "stress-sub",
          sc.deepest_shortfall
            ? `Lowest: −${printMoney(sc.deepest_shortfall.shortfall_minor, currency)} on ${printDate(sc.deepest_shortfall.date)}`
            : "Stays at or above zero",
        ),
      );
      const extra = createEl(
        "span",
        `stress-extra ${sc.extra_needed_minor > 0 ? "negative" : "positive"}`,
        sc.extra_needed_minor > 0
          ? `+${printMoney(sc.extra_needed_minor, currency)}`
          : "Covered",
      );
      li.append(left, extra);
      return li;
    }),
  );

  grid.hidden = false;
}

export function renderAskAnswer(data, currency = "EUR") {
  const box = document.querySelector("#ask-answer-box");
  const text = document.querySelector("#ask-answer-text");
  const meta = document.querySelector("#ask-answer-meta");
  const errorEl = document.querySelector("#ask-error");

  errorEl.hidden = true;
  text.textContent = data.answer;

  const parts = [];
  if (data.what_if) {
    const gap = data.what_if.deepest_shortfall
      ? `New shortfall if this happens: ${printMoney(data.what_if.deepest_shortfall.shortfall_minor, currency)} on ${printDate(data.what_if.deepest_shortfall.date)}`
      : "New shortfall if this happens: 0.00 (no shortfall)";
    parts.push(gap);
  }
  if (data.model) {
    parts.push(`Model: ${data.model}${data.latency_ms != null ? ` · ${data.latency_ms} ms` : ""}`);
  }
  meta.textContent = parts.join(" · ");
  meta.hidden = parts.length === 0;
  box.hidden = false;
  replayFade(box);
}

export function renderAskError(message) {
  const box = document.querySelector("#ask-answer-box");
  const errorEl = document.querySelector("#ask-error");
  box.hidden = true;
  errorEl.textContent = message;
  errorEl.hidden = false;
  replayFade(errorEl);
}

export function renderOptimizePayments(data, transactions, currency = "EUR", onPreviewCollect = null) {
  const card = document.querySelector("#optimize-card");
  const list = document.querySelector("#optimize-list");
  const footer = document.querySelector("#optimize-footer");
  const toggleBtn = document.querySelector("#optimize-toggle");

  const labelById = new Map((transactions || []).map((tx) => [tx.id, tx.label]));
  const actions = data?.actions || [];
  let expanded = false;

  const renderActions = () => {
    if (actions.length === 0) {
      list.classList.add("is-single");
      list.replaceChildren(
        createEl(
          "div",
          "bento-tile insight-empty",
          "No payment timing moves reduce the buffer needed in this window.",
        ),
      );
      footer.hidden = true;
      toggleBtn.onclick = null;
      return;
    }

    const visibleActions = expanded ? actions : actions.slice(0, 4);
    list.classList.toggle("is-single", visibleActions.length === 1);
    list.replaceChildren(
      ...visibleActions.map((action) => {
        const tile = createEl("article", "bento-tile optimize-tile");
        const top = createEl("div", "optimize-top");
        const isCollect = action.kind === "collect_earlier";
        const kindBadge = createEl(
          "span",
          isCollect ? "pill pill-success" : "pill pill-neutral",
          isCollect ? "Collect earlier" : "Pay later",
        );
        const savings = createEl(
          "strong",
          "optimize-savings positive",
          `Saves ${printMoney(action.saves_minor, currency)}`,
        );
        top.append(kindBadge, savings);

        const label = labelById.get(action.transaction_id) || action.transaction_id;
        const title = createEl("strong", "optimize-title", `${label} (${action.transaction_id})`);
        const meta = createEl(
          "span",
          "optimize-meta",
          `${printDate(action.due_date)} → ${printDate(action.new_date)} · Buffer after: ${printMoney(action.limit_after_minor, currency)}`,
        );

        tile.append(top, title, meta);

        if (isCollect && onPreviewCollect) {
          const btnWrap = createEl("div", "optimize-actions");
          const btn = createEl("button", "btn btn-stone btn-xs", "Preview on chart");
          btn.type = "button";
          btn.addEventListener("click", () => onPreviewCollect(action));
          btnWrap.append(btn);
          tile.append(btnWrap);
        }

        return tile;
      }),
    );

    if (actions.length > 4) {
      toggleBtn.textContent = expanded ? "Show fewer" : `Show all ${actions.length} moves`;
      footer.hidden = false;
    } else {
      footer.hidden = true;
    }
  };

  toggleBtn.onclick = () => {
    expanded = !expanded;
    renderActions();
  };
  renderActions();
  card.hidden = false;
}

export function populateDelayCandidates(forecast, currency = "EUR") {
  const card = document.querySelector("#delay-predict-card");
  const form = document.querySelector("#delay-form");
  const select = document.querySelector("#delay-tx-select");
  const emptyEl = document.querySelector("#delay-empty");
  const resultBox = document.querySelector("#delay-result-box");
  const errorEl = document.querySelector("#delay-error");

  resultBox.hidden = true;
  errorEl.hidden = true;

  const days = forecast?.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[Math.min(13, days.length - 1)]?.date;
  const hasShortfall = Boolean(forecast?.baseline?.first_deficit);

  const incoming = (forecast?.transactions || [])
    .filter(
      ({ amount_minor, date }) =>
        amount_minor > 0 && (!startDate || date >= startDate) && (!endDate || date <= endDate),
    )
    .sort((a, b) => b.amount_minor - a.amount_minor)
    .slice(0, 40);

  select.replaceChildren(
    ...incoming.map(
      ({ id, label, date, amount_minor }) =>
        new Option(`${label} (+${printMoney(amount_minor, currency)} on ${printDate(date)})`, id),
    ),
  );

  if (hasShortfall && incoming.length > 0) {
    form.hidden = false;
    emptyEl.hidden = true;
  } else {
    form.hidden = true;
    emptyEl.textContent =
      "Late-payment check is available when your forecast dips below zero and has an incoming payment in the next 14 days.";
    emptyEl.hidden = false;
  }

  card.hidden = false;
}

export function renderDelayResult(data) {
  const resultBox = document.querySelector("#delay-result-box");
  const warningBox = document.querySelector("#delay-warning-box");
  const explanationEl = document.querySelector("#delay-explanation");
  const metaEl = document.querySelector("#delay-meta");
  const errorEl = document.querySelector("#delay-error");

  errorEl.hidden = true;

  if (data.delay_warning) {
    warningBox.textContent = data.delay_warning;
    warningBox.className = "delay-warning";
  } else {
    warningBox.textContent =
      "Local preview mode shows a saved example note. When connected to the live AI model, specific late-payment warnings appear here.";
    warningBox.className = "delay-warning is-note";
  }

  explanationEl.textContent = data.explanation || "";

  const metaParts = [];
  if (data.model) metaParts.push(`Model: ${data.model}`);
  if (data.latency_ms != null) metaParts.push(`${data.latency_ms} ms`);
  metaEl.textContent = metaParts.join(" · ");
  metaEl.hidden = metaParts.length === 0;

  resultBox.hidden = false;
  replayFade(resultBox);
}

export function renderDelayError(message) {
  const resultBox = document.querySelector("#delay-result-box");
  const errorEl = document.querySelector("#delay-error");
  resultBox.hidden = true;
  errorEl.textContent = message;
  errorEl.hidden = false;
  replayFade(errorEl);
}
