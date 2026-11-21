import { printDate, printMoney } from "./format.js";

const ANOMALY_LABELS = {
  duplicate_payment: "Possible duplicate",
  outlier_expense: "Unusually large expense",
  same_day_spike: "Heavy payment day",
};

const FACTOR_LABELS = {
  repayment: "Repayment",
  coverage: "Coverage",
  duration: "Duration",
  depth: "Gap depth",
  concentration: "Client mix",
  delays: "Delay history",
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
  const sections = [
    "#anomalies-card",
    "#compare-card",
    "#health-stress-grid",
    "#optimize-delay-grid",
    "#optimize-card",
    "#delay-predict-card",
  ];
  for (const sel of sections) {
    const el = document.querySelector(sel);
    if (el) el.hidden = true;
  }
  const hiddenIds = [
    "#ask-answer-box",
    "#ask-error",
    "#delay-result-box",
    "#delay-error",
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
        "No duplicate charges, unusual spikes, or outlier expenses detected in this 14-day window.",
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
        createEl("dt", "", "Estimated cost"),
        createEl("dd", "", printMoney(opt.estimated_cost_minor, currency)),
      );
      const creditWrap = document.createElement("div");
      creditWrap.append(
        createEl("dt", "", "Credit needed"),
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
  const factorsList = document.querySelector("#credit-factors-list");

  const meta = RISK_META[data.risk] || RISK_META.medium;
  badge.textContent = meta.label;
  badge.className = meta.pillClass;

  scoreVal.textContent = String(data.score);
  scoreBar.style.width = `${Math.max(4, Math.min(100, data.score))}%`;
  scoreBar.className = `score-bar-fill ${meta.barClass}`;

  scoreNote.textContent =
    data.explanation ||
    `Calculated for a ${printMoney(data.limit_minor, currency)} credit line based on repayment, coverage, gap depth, and client concentration.`;

  factorsList.replaceChildren(
    ...(data.factors || []).map((f) => {
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

  grid.hidden = false;
}

export function renderHealthyCreditScore() {
  const grid = document.querySelector("#health-stress-grid");
  const badge = document.querySelector("#credit-risk-badge");
  const scoreVal = document.querySelector("#credit-score-value");
  const scoreBar = document.querySelector("#credit-score-fill");
  const scoreNote = document.querySelector("#credit-score-note");
  const factorsList = document.querySelector("#credit-factors-list");

  badge.textContent = "Low risk";
  badge.className = "pill pill-success";
  scoreVal.textContent = "100";
  scoreBar.style.width = "100%";
  scoreBar.className = "score-bar-fill score-bar-low";
  scoreNote.textContent = "Your balance stays positive across the entire 14-day window — no credit facility is needed.";
  factorsList.replaceChildren();
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
      ? `Includes +${printMoney(data.buffer_minor, currency)} extra safety buffer over baseline.`
      : "Baseline limit already covers all stress scenarios.";

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
      ? `Recalculated gap: ${printMoney(data.what_if.deepest_shortfall.shortfall_minor, currency)} on ${printDate(data.what_if.deepest_shortfall.date)}`
      : "Recalculated gap: 0.00 (no shortfall)";
    parts.push(gap);
  }
  if (data.model) {
    parts.push(`Model: ${data.model}${data.latency_ms != null ? ` · ${data.latency_ms} ms` : ""}`);
  }
  meta.textContent = parts.join(" · ");
  meta.hidden = parts.length === 0;
  box.hidden = false;
}

export function renderAskError(message) {
  const box = document.querySelector("#ask-answer-box");
  const errorEl = document.querySelector("#ask-error");
  box.hidden = true;
  errorEl.textContent = message;
  errorEl.hidden = false;
}

export function renderOptimizePayments(data, transactions, currency = "EUR", onPreviewCollect = null) {
  const grid = document.querySelector("#optimize-delay-grid");
  const card = document.querySelector("#optimize-card");
  const list = document.querySelector("#optimize-list");

  const labelById = new Map((transactions || []).map((tx) => [tx.id, tx.label]));
  const actions = data?.actions || [];

  if (actions.length === 0) {
    list.replaceChildren(
      createEl(
        "div",
        "bento-tile insight-empty",
        "No payment timing moves improve the credit limit in this window.",
      ),
    );
  } else {
    list.replaceChildren(
      ...actions.map((action) => {
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
          `${printDate(action.due_date)} → ${printDate(action.new_date)} · Credit after: ${printMoney(action.limit_after_minor, currency)}`,
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
  }

  card.hidden = false;
  grid.hidden = false;
}

export function populateDelayCandidates(forecast, currency = "EUR") {
  const grid = document.querySelector("#optimize-delay-grid");
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
      "Delay prediction requires a projected shortfall and at least one incoming payment in the 14-day window.";
    emptyEl.hidden = false;
  }

  card.hidden = false;
  grid.hidden = false;
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
      "Demo mode returned the bundled explanation. In live mode, delay-specific warnings appear here.";
    warningBox.className = "delay-warning is-note";
  }

  explanationEl.textContent = data.explanation || "";

  const metaParts = [];
  if (data.model) metaParts.push(`Model: ${data.model}`);
  if (data.latency_ms != null) metaParts.push(`${data.latency_ms} ms`);
  metaEl.textContent = metaParts.join(" · ");
  metaEl.hidden = metaParts.length === 0;

  resultBox.hidden = false;
}

export function renderDelayError(message) {
  const resultBox = document.querySelector("#delay-result-box");
  const errorEl = document.querySelector("#delay-error");
  resultBox.hidden = true;
  errorEl.textContent = message;
  errorEl.hidden = false;
}
