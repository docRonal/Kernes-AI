import { printDate, printMoney, replayFade, toMinor } from "./format.js?v=tc11";
import { groupTransactionsByDate } from "./proposal.js?v=tc10";

const SVG_NS = "http://www.w3.org/2000/svg";

const CATEGORY_META = {
  staff_payroll: { label: "Staff payroll", color: "#121211" },
  b2b_supplier: { label: "Suppliers & stock", color: "#ff7b4b" },
  rent: { label: "Rent & space", color: "#4f46e5" },
  tax_social: { label: "Taxes & social", color: "#d9383a" },
  utility: { label: "Utilities", color: "#0284c7" },
  owner_draw: { label: "Owner draw", color: "#7c3aed" },
  b2b_client: { label: "Client invoices", color: "#1f8a4c" },
  retail_card: { label: "Debit card sales", color: "#10b981" },
  card_acquirer: { label: "Credit card payouts", color: "#047857" },
  card_purchase: { label: "Card / POS purchases", color: "#d97706" },
  early_payment: { label: "Early payment (Sim)", color: "#0ea5e9" },
  planned_purchase: { label: "Planned purchase (Sim)", color: "#ea580c" },
  other_income: { label: "Other income", color: "#65a30d" },
  other: { label: "Other expenses", color: "#78716c" },
};

function svgEl(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, val] of Object.entries(attrs)) {
    node.setAttribute(key, String(val));
  }
  if (text !== "") node.textContent = text;
  return node;
}

const ACTIONABILITY_META = {
  fixed_mandatory: { text: "Fixed · Don't delay", cls: "tag-fixed" },
  email_defer_supplier: { text: "Negotiable · Ask supplier", cls: "tag-defer" },
  email_collect_early: { text: "Collect early · Remind client", cls: "tag-collect" },
  owner_draw_flexible: { text: "Flexible · Owner draw", cls: "tag-flexible" },
  retail_non_contactable: { text: "Auto · Card sales", cls: "tag-auto" },
};

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

function formatShortDayLabel(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(d);
}

function formatCompactMoney(minor, currency = "EUR") {
  const symbol =
    currency === "EUR" ? "€" : currency === "USD" ? "$" : currency === "GBP" ? "£" : `${currency} `;
  const value = minor / 100;
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1_000_000) return `${sign}${symbol}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}${symbol}${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}${symbol}${(abs / 1_000).toFixed(1)}k`;
  return `${sign}${symbol}${Math.round(abs)}`;
}

function inferActionability(tx) {
  if (tx.actionability) return tx.actionability;
  const label = `${tx.label || ""} ${tx.transaction_type || ""}`.toLowerCase();
  if (tx.amount_minor > 0) {
    if (label.includes("customer") || label.includes("card") || label.includes("global pay")) {
      return "retail_non_contactable";
    }
    return "email_collect_early";
  }
  if (
    label.includes("tax") ||
    label.includes("krankenkasse") ||
    label.includes("social") ||
    label.includes("salary") ||
    label.includes("payroll") ||
    label.includes("energy") ||
    label.includes("utility")
  ) {
    return "fixed_mandatory";
  }
  return "email_defer_supplier";
}

function inferCategory(tx) {
  const isOutflow = tx.amount_minor < 0;
  const label = `${tx.label || ""} ${tx.transaction_type || ""} ${tx.payment_reference || ""}`.toLowerCase();

  // Outgoing card/giro purchases should never be labeled as "Card sales"
  if (isOutflow && (tx.category === "retail_card" || tx.category === "card_acquirer" || label.includes("giro card") || label.includes("wholesale market"))) {
    return "card_purchase";
  }
  if (!isOutflow) {
    if (tx.category === "retail_card" || tx.category === "card_acquirer" || tx.category === "b2b_client") {
      return tx.category;
    }
    if (label.includes("global pay") || label.includes("credit card")) return "card_acquirer";
    if (label.includes("card") || label.includes("customer")) return "retail_card";
    if (label.includes("invoice") || label.includes("client")) return "b2b_client";
    return "other_income";
  }

  if (tx.category && CATEGORY_META[tx.category]) return tx.category;
  if (label.includes("rent") || label.includes("real estate")) return "rent";
  if (label.includes("tax") || label.includes("krankenkasse") || label.includes("social")) return "tax_social";
  if (label.includes("salary") || label.includes("payroll")) return "staff_payroll";
  if (label.includes("utility") || label.includes("energy") || label.includes("electric")) return "utility";
  if (label.includes("owner")) return "owner_draw";
  return "b2b_supplier";
}

/* --------------------------------------------------------------------------
   1. Workspace Navigation (Tabs + Show All toggle)
   -------------------------------------------------------------------------- */
export function createWorkspaceController() {
  const resultsEl = document.querySelector("#results");
  const tabs = Array.from(document.querySelectorAll(".ws-tab"));
  const panels = Array.from(document.querySelectorAll(".workspace-panel"));
  const viewAllBtn = document.querySelector("#ws-view-all-btn");

  let activeWorkspace = "overview";
  let showAll = false;

  function applyView() {
    resultsEl?.classList.toggle("is-show-all", showAll);
    if (viewAllBtn) {
      viewAllBtn.classList.toggle("is-active", showAll);
      viewAllBtn.setAttribute("aria-pressed", String(showAll));
      viewAllBtn.textContent = showAll ? "Focus mode" : "Show all sections";
    }
    for (const tab of tabs) {
      const isMatch = !showAll && tab.dataset.workspace === activeWorkspace;
      tab.classList.toggle("is-active", isMatch);
      tab.setAttribute("aria-selected", String(isMatch));
    }
    for (const panel of panels) {
      const isVisible = showAll || panel.dataset.workspacePanel === activeWorkspace;
      panel.hidden = !isVisible;
    }
  }

  function setWorkspace(name, scrollSelector = null) {
    activeWorkspace = name;
    showAll = false;
    applyView();
    if (scrollSelector) {
      requestAnimationFrame(() => {
        document.querySelector(scrollSelector)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  function setShowAll(val) {
    showAll = Boolean(val);
    applyView();
  }

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      setWorkspace(tab.dataset.workspace || "overview");
    });
  }

  viewAllBtn?.addEventListener("click", () => {
    setShowAll(!showAll);
  });

  // Wire Signal Strip click-to-jump
  document.querySelector("#sig-tile-health")?.addEventListener("click", () => {
    setWorkspace("health", "#credit-score-card");
  });
  document.querySelector("#sig-tile-savings")?.addEventListener("click", () => {
    setWorkspace("actions", "#optimize-card");
  });
  document.querySelector("#sig-tile-anomalies")?.addEventListener("click", () => {
    setWorkspace("health", "#anomalies-card");
  });
  document.querySelector("#sig-tile-runway")?.addEventListener("click", () => {
    setWorkspace("overview", "#breakdown-card");
  });

  applyView();
  return { setWorkspace, setShowAll, applyView };
}

/* --------------------------------------------------------------------------
   2. Signal Strip (Glanceable KPIs from Forecast + Insights)
   -------------------------------------------------------------------------- */
export function renderSignalStripBase(state) {
  const forecast = state.forecast;
  if (!forecast) return;
  const currency = forecast.currency ?? "EUR";
  const days = forecast.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[days.length - 1]?.date;

  // Compute Cash Runway from opening balance & average daily outflow
  const windowTxs = (forecast.transactions || []).filter(
    (tx) => (!startDate || tx.date >= startDate) && (!endDate || tx.date <= endDate),
  );
  let totalOutflowsMinor = 0;
  for (const tx of windowTxs) {
    if (tx.amount_minor < 0) totalOutflowsMinor += Math.abs(tx.amount_minor);
  }
  const avgDailyOutflow = days.length > 0 ? totalOutflowsMinor / days.length : 0;
  const opening = Math.max(0, Number(state.openingBalanceMinor ?? 0));
  const runwayValEl = document.querySelector("#sig-runway-value");
  const runwaySubEl = document.querySelector("#sig-runway-sub");
  const runwayDotEl = document.querySelector("#sig-runway-dot");

  if (avgDailyOutflow <= 0) {
    if (runwayValEl) runwayValEl.textContent = "14+ days";
    if (runwaySubEl) runwaySubEl.textContent = "No outflows in window";
    if (runwayDotEl) runwayDotEl.className = "signal-dot is-ok";
  } else {
    const rawDays = Math.floor(opening / avgDailyOutflow);
    if (runwayValEl) runwayValEl.textContent = rawDays >= 30 ? "30+ days" : `${rawDays} days`;
    if (runwaySubEl) {
      runwaySubEl.textContent = `Avg burn ${printMoney(Math.round(avgDailyOutflow), currency)}/day`;
    }
    if (runwayDotEl) {
      runwayDotEl.className =
        rawDays >= 10 ? "signal-dot is-ok" : rawDays >= 5 ? "signal-dot is-warn" : "signal-dot is-danger";
    }
  }

  // Reset insight-driven tiles to loading state
  const healthVal = document.querySelector("#sig-health-value");
  const healthSub = document.querySelector("#sig-health-sub");
  const healthDot = document.querySelector("#sig-health-dot");
  if (healthVal) healthVal.textContent = "Checking…";
  if (healthSub) healthSub.textContent = "Readiness & stress test";
  if (healthDot) healthDot.className = "signal-dot";

  const savingsVal = document.querySelector("#sig-savings-value");
  const savingsSub = document.querySelector("#sig-savings-sub");
  const savingsDot = document.querySelector("#sig-savings-dot");
  if (savingsVal) savingsVal.textContent = "Checking…";
  if (savingsSub) savingsSub.textContent = "Payment timing moves";
  if (savingsDot) savingsDot.className = "signal-dot";

  const anomVal = document.querySelector("#sig-anomalies-value");
  const anomSub = document.querySelector("#sig-anomalies-sub");
  const anomDot = document.querySelector("#sig-anomalies-dot");
  const anomTile = document.querySelector("#sig-tile-anomalies");
  if (anomVal) anomVal.textContent = "Checking…";
  if (anomSub) anomSub.textContent = "Scanning CSV for outliers";
  if (anomDot) anomDot.className = "signal-dot";
  anomTile?.classList.remove("is-alert");
}

export function updateSignalStripInsights({ forecast, insights }) {
  if (!forecast) return;
  const currency = forecast.currency ?? "EUR";
  const hasShortfall = Boolean(forecast.baseline?.first_deficit);
  const { anomalies, compare, stress, credit, optimize } = insights || {};

  // 1. Health Tile + Health Tab Badge
  const healthVal = document.querySelector("#sig-health-value");
  const healthSub = document.querySelector("#sig-health-sub");
  const healthDot = document.querySelector("#sig-health-dot");
  const healthBadge = document.querySelector("#ws-badge-health");

  if (!hasShortfall) {
    if (healthVal) healthVal.textContent = "100 / 100";
    if (healthSub) healthSub.textContent = "Low risk · Healthy cash";
    if (healthDot) healthDot.className = "signal-dot is-ok";
  } else if (credit) {
    if (healthVal) healthVal.textContent = `${credit.score} / 100`;
    if (healthSub) {
      const riskText = credit.risk.charAt(0).toUpperCase() + credit.risk.slice(1);
      healthSub.textContent = `${riskText} risk · Click for breakdown`;
    }
    if (healthDot) {
      healthDot.className =
        credit.risk === "low"
          ? "signal-dot is-ok"
          : credit.risk === "medium"
            ? "signal-dot is-warn"
            : "signal-dot is-danger";
    }
  } else if (stress) {
    if (healthVal) healthVal.textContent = printMoney(stress.recommended_limit_minor, currency);
    if (healthSub) healthSub.textContent = "Stress-tested buffer";
    if (healthDot) healthDot.className = "signal-dot is-warn";
  }

  // 2. Savings Tile + Actions Tab Badge
  const savingsVal = document.querySelector("#sig-savings-value");
  const savingsSub = document.querySelector("#sig-savings-sub");
  const savingsDot = document.querySelector("#sig-savings-dot");
  const actionsBadge = document.querySelector("#ws-badge-actions");

  const moves = optimize?.actions || [];
  if (moves.length > 0) {
    const top = moves[0];
    if (savingsVal) savingsVal.textContent = `Save ${printMoney(top.saves_minor, currency)}`;
    if (savingsSub) {
      savingsSub.textContent = `${moves.length} timing move${moves.length > 1 ? "s" : ""} found`;
    }
    if (savingsDot) savingsDot.className = "signal-dot is-ok";
  } else {
    if (savingsVal) savingsVal.textContent = hasShortfall ? "Buffer needed" : "No moves needed";
    if (savingsSub) {
      savingsSub.textContent = hasShortfall
        ? "Compare buffer options →"
        : "Cash stays positive";
    }
    if (savingsDot) savingsDot.className = hasShortfall ? "signal-dot is-warn" : "signal-dot is-ok";
  }

  if (actionsBadge) {
    const optCount = compare?.options?.length || 0;
    const totalCount = moves.length + optCount;
    if (totalCount > 0) {
      actionsBadge.textContent = String(totalCount);
      actionsBadge.className = hasShortfall ? "ws-tab-badge is-warn" : "ws-tab-badge is-ok";
      actionsBadge.hidden = false;
    } else {
      actionsBadge.hidden = true;
    }
  }

  // 3. Anomalies Tile + Health Tab Badge
  const anomVal = document.querySelector("#sig-anomalies-value");
  const anomSub = document.querySelector("#sig-anomalies-sub");
  const anomDot = document.querySelector("#sig-anomalies-dot");
  const anomTile = document.querySelector("#sig-tile-anomalies");

  const findingCount = anomalies?.findings?.length || 0;
  if (forecast.forecast_basis === "history") {
    if (anomVal) anomVal.textContent = "History mode";
    if (anomSub) anomSub.textContent = "Estimated from 2025 CSV";
    if (anomDot) anomDot.className = "signal-dot is-ok";
    anomTile?.classList.remove("is-alert");
  } else if (anomalies) {
    if (findingCount > 0) {
      if (anomVal) anomVal.textContent = `${findingCount} flagged`;
      if (anomSub) anomSub.textContent = "Duplicate or large payment";
      if (anomDot) anomDot.className = "signal-dot is-warn";
      anomTile?.classList.add("is-alert");
    } else {
      if (anomVal) anomVal.textContent = "Looks clean";
      if (anomSub) anomSub.textContent = "No unusual charges found";
      if (anomDot) anomDot.className = "signal-dot is-ok";
      anomTile?.classList.remove("is-alert");
    }
  }

  if (healthBadge) {
    if (findingCount > 0) {
      healthBadge.textContent = `${findingCount} alert${findingCount > 1 ? "s" : ""}`;
      healthBadge.className = "ws-tab-badge is-warn";
      healthBadge.hidden = false;
    } else if (!hasShortfall) {
      healthBadge.textContent = "100";
      healthBadge.className = "ws-tab-badge is-ok";
      healthBadge.hidden = false;
    } else if (credit) {
      healthBadge.textContent = `${credit.score}`;
      healthBadge.className = "ws-tab-badge";
      healthBadge.hidden = false;
    } else {
      healthBadge.hidden = true;
    }
  }
}

/* --------------------------------------------------------------------------
   3. Interactive Day Inspector (Synced with Chart Clicks)
   -------------------------------------------------------------------------- */
export function renderDayInspector(state, selectedDateIso, onSelectDate, onQuickAction) {
  const stripEl = document.querySelector("#day-strip");
  const detailEl = document.querySelector("#day-detail-box");
  if (!stripEl || !detailEl || !state.forecast) return;

  const forecast = state.forecast;
  const currency = forecast.currency ?? "EUR";
  const days = forecast.baseline?.days || [];
  if (days.length === 0) return;

  const defaultDate =
    selectedDateIso && days.some((d) => d.date === selectedDateIso)
      ? selectedDateIso
      : state.proposal?.firstDeficit?.date ||
        state.proposal?.peakDeficit?.date ||
        days[0].date;

  const txByDate = groupTransactionsByDate(forecast.transactions);

  stripEl.replaceChildren(
    ...days.map((day) => {
      const isSelected = day.date === defaultDate;
      const isDeficit = day.balance_minor < 0;
      const btn = el(
        "button",
        `day-pill${isDeficit ? " is-deficit" : ""}${isSelected ? " is-selected" : ""}`,
      );
      btn.type = "button";
      btn.setAttribute("aria-pressed", String(isSelected));
      btn.append(
        el("span", "day-pill-date", formatShortDayLabel(day.date)),
        el("span", "day-pill-bal", formatCompactMoney(day.balance_minor, currency)),
      );
      btn.addEventListener("click", () => onSelectDate(day.date));
      return btn;
    }),
  );

  const selectedDay = days.find((d) => d.date === defaultDate) || days[0];
  const dayTxs = txByDate.get(selectedDay.date) || [];

  const header = el("div", "day-detail-header");
  header.append(
    el(
      "span",
      "day-detail-date",
      `${printDate(selectedDay.date)} · ${dayTxs.length} payment${dayTxs.length === 1 ? "" : "s"}`,
    ),
    el(
      "span",
      `day-detail-balance ${selectedDay.balance_minor < 0 ? "negative" : "positive"}`,
      `End-of-day balance: ${printMoney(selectedDay.balance_minor, currency)}`,
    ),
  );

  const children = [header];

  if (dayTxs.length === 0) {
    children.push(
      el("p", "muted-note", "No scheduled incoming or outgoing payments on this day."),
    );
  } else {
    const list = el("div", "calendar-list");
    list.style.marginTop = "4px";
    for (const tx of dayTxs) {
      list.append(buildTransactionRow(tx, currency, onQuickAction));
    }
    children.push(list);
  }

  detailEl.replaceChildren(...children);
}

function buildTransactionRow(tx, currency, onQuickAction) {
  const row = el("div", "calendar-row");
  const main = el("div", "calendar-row-main");

  const titleLine = el("div", "calendar-row-title-line");
  titleLine.append(el("span", "calendar-row-label", tx.counterparty || tx.label));

  const actKey = inferActionability(tx);
  const actMeta = ACTIONABILITY_META[actKey] || ACTIONABILITY_META.fixed_mandatory;
  titleLine.append(el("span", `action-tag ${actMeta.cls}`, actMeta.text));

  const catKey = inferCategory(tx);
  const catLabel = CATEGORY_META[catKey]?.label || "Other";
  const subParts = [printDate(tx.date), catLabel];
  if (tx.payment_reference) subParts.push(tx.payment_reference);
  const sub = el("span", "calendar-row-sub", subParts.join(" · "));

  main.append(titleLine, sub);

  const right = el("div", "calendar-row-right");
  const amt = el(
    "span",
    `tx-amount ${tx.amount_minor < 0 ? "negative" : "positive"}`,
    `${tx.amount_minor > 0 ? "+" : ""}${printMoney(tx.amount_minor, currency)}`,
  );
  right.append(amt);

  if (onQuickAction && (actKey === "email_collect_early" || actKey === "email_defer_supplier")) {
    const btn = el(
      "button",
      "btn btn-stone btn-xs",
      actKey === "email_collect_early" ? "Move / Remind →" : "Ask for extension →",
    );
    btn.type = "button";
    btn.addEventListener("click", () => onQuickAction(tx, actKey));
    right.append(btn);
  }

  row.append(main, right);
  return row;
}

/* --------------------------------------------------------------------------
   4. Cash Breakdown & Dual Income / Expense Donut Charts
   -------------------------------------------------------------------------- */
function renderDonutPanel({ chartEl, legendEl, entries, totalMinor, currency, centerTitle, emptyText, labelOverrides = {} }) {
  if (!chartEl || !legendEl) return;

  if (totalMinor <= 0 || entries.length === 0) {
    chartEl.replaceChildren(el("div", "donut-empty", emptyText));
    legendEl.replaceChildren();
    return;
  }

  const size = 180;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 64;
  const circumference = 2 * Math.PI * radius;
  const gapPx = entries.length > 1 ? 2.5 : 0;

  const svg = svgEl("svg", {
    viewBox: `0 0 ${size} ${size}`,
    class: "donut-svg",
    role: "img",
    "aria-label": `${centerTitle}: ${printMoney(totalMinor, currency)}`,
  });

  // Subtle background ring
  svg.append(
    svgEl("circle", {
      cx,
      cy,
      r: radius,
      fill: "none",
      stroke: "#eaeae7",
      "stroke-width": 22,
    }),
  );

  const centerTitleEl = svgEl("text", { x: cx, y: cy - 11, "text-anchor": "middle", class: "donut-center-label" }, centerTitle);
  const centerValEl = svgEl("text", { x: cx, y: cy + 9, "text-anchor": "middle", class: "donut-center-value" }, formatCompactMoney(totalMinor, currency));
  const centerSubEl = svgEl("text", { x: cx, y: cy + 25, "text-anchor": "middle", class: "donut-center-sub" }, "100%");

  const sliceNodes = [];
  const rowNodes = [];

  let offset = 0;
  entries.forEach(([cat, amount], idx) => {
    const baseMeta = CATEGORY_META[cat] || CATEGORY_META.other;
    const meta = {
      ...baseMeta,
      label: labelOverrides[cat] || baseMeta.label,
    };
    const share = amount / totalMinor;
    const rawLen = share * circumference;
    const dashLen = Math.max(2, rawLen - gapPx);
    const pct = Math.max(1, Math.round(share * 100));

    const circle = svgEl("circle", {
      cx,
      cy,
      r: radius,
      fill: "none",
      stroke: meta.color,
      "stroke-width": 22,
      "stroke-dasharray": `${dashLen.toFixed(2)} ${(circumference - dashLen).toFixed(2)}`,
      "stroke-dashoffset": (-offset).toFixed(2),
      transform: `rotate(-90 ${cx} ${cy})`,
      class: "donut-slice",
    });

    const titleTag = svgEl("title", {}, `${meta.label}: ${printMoney(amount, currency)} (${pct}%)`);
    circle.append(titleTag);
    svg.append(circle);
    sliceNodes.push({ circle, meta, amount, pct });
    offset += rawLen;

    const row = el("li", "donut-legend-row");
    const left = el("div", "donut-legend-left");
    const swatch = el("span", "breakdown-swatch");
    swatch.style.background = meta.color;
    left.append(swatch, el("span", "breakdown-cat-name", meta.label));

    const right = el("div", "donut-legend-right");
    right.append(
      el("span", "breakdown-cat-val", printMoney(amount, currency)),
      el("span", "donut-pct-pill", `${pct}%`),
    );

    row.append(left, right);
    rowNodes.push(row);

    const setHighlight = (activeIdx) => {
      sliceNodes.forEach((s, i) => {
        s.circle.classList.toggle("is-active", activeIdx === i);
        s.circle.classList.toggle("is-dimmed", activeIdx !== null && activeIdx !== i);
      });
      rowNodes.forEach((r, i) => {
        r.classList.toggle("is-active", activeIdx === i);
      });
      if (activeIdx === null) {
        centerTitleEl.textContent = centerTitle;
        centerValEl.textContent = formatCompactMoney(totalMinor, currency);
        centerSubEl.textContent = "100%";
      } else {
        const picked = sliceNodes[activeIdx];
        const shortName =
          picked.meta.label.length > 13 ? `${picked.meta.label.slice(0, 12)}…` : picked.meta.label;
        centerTitleEl.textContent = shortName;
        centerValEl.textContent = formatCompactMoney(picked.amount, currency);
        centerSubEl.textContent = `${picked.pct}% of total`;
      }
    };

    circle.addEventListener("mouseenter", () => setHighlight(idx));
    circle.addEventListener("mouseleave", () => setHighlight(null));
    row.addEventListener("mouseenter", () => setHighlight(idx));
    row.addEventListener("mouseleave", () => setHighlight(null));
  });

  svg.append(centerTitleEl, centerValEl, centerSubEl);
  chartEl.replaceChildren(svg);
  legendEl.replaceChildren(...rowNodes);
}

export function renderCashBreakdown(state) {
  const card = document.querySelector("#breakdown-card");
  if (!card || !state.forecast) return;

  const forecast = state.forecast;
  const currency = forecast.currency ?? "EUR";
  const days = forecast.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[days.length - 1]?.date;

  const windowTxs = (forecast.transactions || []).filter(
    (tx) => (!startDate || tx.date >= startDate) && (!endDate || tx.date <= endDate),
  );

  let totalIn = 0;
  let totalOut = 0;
  const inByCat = new Map();
  const outByCat = new Map();
  const inLabelOverrides = {};
  const outLabelOverrides = {};
  let hasSimChanges = false;

  const earlyPay = state.earlyPaySim?.enabled ? state.earlyPaySim : null;

  for (const tx of windowTxs) {
    if (tx.amount_minor > 0) {
      totalIn += tx.amount_minor;
      // If this incoming payment is accelerated via Early Pay, highlight it in the Early payment (Sim) slice
      if (earlyPay && tx.id === earlyPay.txId) {
        inByCat.set("early_payment", (inByCat.get("early_payment") || 0) + tx.amount_minor);
        hasSimChanges = true;
      } else {
        const cat = inferCategory(tx);
        inByCat.set(cat, (inByCat.get(cat) || 0) + tx.amount_minor);
      }
    } else if (tx.amount_minor < 0) {
      const absAmt = Math.abs(tx.amount_minor);
      totalOut += absAmt;
      const cat = inferCategory(tx);
      outByCat.set(cat, (outByCat.get(cat) || 0) + absAmt);
    }
  }

  // If Early Pay accelerated a payment from outside the 14-day window into the window, add it to totalIn & Early payment slice
  if (earlyPay && !inByCat.has("early_payment") && earlyPay.amountMinor > 0) {
    totalIn += earlyPay.amountMinor;
    inByCat.set("early_payment", earlyPay.amountMinor);
    hasSimChanges = true;
  }
  if (earlyPay && inByCat.has("early_payment")) {
    const shortParty =
      earlyPay.label.length > 22 ? `${earlyPay.label.slice(0, 21)}…` : earlyPay.label;
    inLabelOverrides.early_payment = `Early pay: ${shortParty}`;
  }

  // Include all enabled planned purchases in the Expenses donut chart and totals
  const enabledPurchases = (state.plannedPurchases || []).filter((p) => p.enabled && p.amountMinor > 0);
  if (enabledPurchases.length > 0) {
    hasSimChanges = true;
    let purchaseTotal = 0;
    for (const p of enabledPurchases) {
      purchaseTotal += p.amountMinor;
    }
    totalOut += purchaseTotal;
    outByCat.set("planned_purchase", (outByCat.get("planned_purchase") || 0) + purchaseTotal);
    outLabelOverrides.planned_purchase =
      enabledPurchases.length === 1
        ? `Planned: ${enabledPurchases[0].name}`
        : `Planned purchases (${enabledPurchases.length})`;
  }

  const simBadge = document.querySelector("#breakdown-sim-badge");
  if (simBadge) simBadge.hidden = !hasSimChanges;

  const net = totalIn - totalOut;
  const inEl = document.querySelector("#breakdown-inflows");
  const outEl = document.querySelector("#breakdown-outflows");
  const netEl = document.querySelector("#breakdown-net");

  if (inEl) inEl.textContent = `+${printMoney(totalIn, currency)}`;
  if (outEl) outEl.textContent = `−${printMoney(totalOut, currency)}`;
  if (netEl) {
    netEl.textContent = `${net >= 0 ? "+" : "−"}${printMoney(Math.abs(net), currency)}`;
    netEl.className = `breakdown-stat-value ${net < 0 ? "negative" : "positive"}`;
  }

  const sortedIn = Array.from(inByCat.entries()).sort((a, b) => b[1] - a[1]);
  const sortedOut = Array.from(outByCat.entries()).sort((a, b) => b[1] - a[1]);

  renderDonutPanel({
    chartEl: document.querySelector("#donut-inflows-chart"),
    legendEl: document.querySelector("#donut-inflows-legend"),
    entries: sortedIn,
    totalMinor: totalIn,
    currency,
    centerTitle: "Income",
    emptyText: "No incoming payments in this 14-day window.",
    labelOverrides: inLabelOverrides,
  });

  renderDonutPanel({
    chartEl: document.querySelector("#donut-outflows-chart"),
    legendEl: document.querySelector("#donut-outflows-legend"),
    entries: sortedOut,
    totalMinor: totalOut,
    currency,
    centerTitle: "Expenses",
    emptyText: "No outgoing payments in this 14-day window.",
    labelOverrides: outLabelOverrides,
  });
}

/* --------------------------------------------------------------------------
   4b. Combined What-If Curve & Active Simulations Control Bar
   -------------------------------------------------------------------------- */
export function buildCombinedWhatIfOverlay(state) {
  const days = state.forecast?.baseline?.days || [];
  if (days.length === 0) return null;

  const currency = state.forecast?.currency ?? "EUR";
  const enabledPurchases = (state.plannedPurchases || []).filter((p) => p.enabled && p.amountMinor > 0);
  const activeCustom = state.customWhatIf?.enabled && state.customWhatIf?.days?.length === days.length
    ? state.customWhatIf
    : null;

  if (enabledPurchases.length === 0 && !activeCustom) return null;

  const combinedDays = days.map((day, idx) => {
    let bal = activeCustom ? activeCustom.days[idx].balance_minor : day.balance_minor;
    for (const p of enabledPurchases) {
      if (day.date >= p.date) {
        bal -= p.amountMinor;
      }
    }
    return { date: day.date, balance_minor: bal };
  });

  let label = "";
  if (enabledPurchases.length === 1 && !activeCustom) {
    const p = enabledPurchases[0];
    label = `Buy ${p.name} (−${printMoney(p.amountMinor, currency)})`;
  } else if (enabledPurchases.length === 0 && activeCustom) {
    label = activeCustom.label;
  } else {
    const totalCount = enabledPurchases.length + (activeCustom ? 1 : 0);
    const totalSpend = enabledPurchases.reduce((acc, p) => acc + p.amountMinor, 0);
    label =
      totalSpend > 0
        ? `${totalCount} active scenarios (−${printMoney(totalSpend, currency)})`
        : `${totalCount} active scenarios`;
  }

  return { label, days: combinedDays };
}

export function renderActiveSimsBar(state, callbacks = {}) {
  const bar = document.querySelector("#active-sims-bar");
  const list = document.querySelector("#active-sims-list");
  if (!bar || !list || !state.forecast) return;

  const currency = state.forecast.currency ?? "EUR";
  const items = [];

  for (const p of state.plannedPurchases || []) {
    items.push({
      kind: "sim-expense",
      enabled: p.enabled,
      label: `Buy ${p.name}`,
      amount: `−${printMoney(p.amountMinor, currency)} · ${printDate(p.date)}`,
      onToggle: () => callbacks.onTogglePurchase?.(p.id),
      onRemove: () => callbacks.onRemovePurchase?.(p.id),
    });
  }

  if (state.earlyPaySim) {
    const ep = state.earlyPaySim;
    items.push({
      kind: "sim-income",
      enabled: ep.enabled,
      label: `Early pay: ${ep.label}`,
      amount: `+${printMoney(ep.amountMinor, currency)} → ${printDate(ep.newDate)}`,
      onToggle: () => callbacks.onToggleEarlyPay?.(),
      onRemove: () => callbacks.onRemoveEarlyPay?.(),
    });
  }

  if (state.customWhatIf) {
    const cw = state.customWhatIf;
    items.push({
      kind: "sim-expense",
      enabled: cw.enabled,
      label: cw.label,
      amount: "",
      onToggle: () => callbacks.onToggleCustomWhatIf?.(),
      onRemove: () => callbacks.onRemoveCustomWhatIf?.(),
    });
  }

  if (state.showStress) {
    items.push({
      kind: "sim-stress",
      enabled: true,
      label: "Stress test",
      amount: "Receipts +5d late / +10% costs",
      onToggle: () => callbacks.onRemoveStress?.(),
      onRemove: () => callbacks.onRemoveStress?.(),
    });
  }

  if (state.simulationDecision) {
    const isApproved = state.simulationDecision === "approved";
    const limit = state.simulationOutcome?.limit_minor ?? state.proposal?.recommendedLimitMinor ?? 0;
    items.push({
      kind: "sim-buffer",
      enabled: true,
      label: isApproved ? "Safety buffer approved" : "Safety buffer rejected",
      amount: isApproved && limit > 0 ? printMoney(limit, currency) : "",
      onToggle: () => callbacks.onResetBuffer?.(),
      onRemove: () => callbacks.onResetBuffer?.(),
    });
  }

  if (items.length === 0) {
    bar.hidden = true;
    list.replaceChildren();
    return;
  }

  list.replaceChildren(
    ...items.map((item) => {
      const chip = el(
        "div",
        `sim-chip ${item.kind} ${item.enabled ? "is-enabled" : "is-paused"}`,
      );

      const toggleBtn = el("button", "sim-chip-toggle");
      toggleBtn.type = "button";
      toggleBtn.setAttribute("aria-pressed", String(item.enabled));
      toggleBtn.title = item.enabled ? "Click to pause this simulation" : "Click to re-enable this simulation";
      toggleBtn.append(
        el("span", "sim-chip-check", item.enabled ? "✓" : ""),
        el("span", "", item.label),
      );
      if (item.amount) {
        toggleBtn.append(el("span", "sim-chip-amount", item.amount));
      }
      toggleBtn.addEventListener("click", item.onToggle);

      const removeBtn = el("button", "sim-chip-remove", "×");
      removeBtn.type = "button";
      removeBtn.setAttribute("aria-label", `Remove ${item.label}`);
      removeBtn.addEventListener("click", item.onRemove);

      chip.append(toggleBtn, removeBtn);
      return chip;
    }),
  );

  bar.hidden = false;
}

/* --------------------------------------------------------------------------
   5. Smart Cash Calendar (Filterable upcoming bills & inflows)
   -------------------------------------------------------------------------- */
export function renderSmartCalendar(state, activeFilter = "all", onQuickAction = null) {
  const listEl = document.querySelector("#calendar-list");
  const countEl = document.querySelector("#calendar-count");
  if (!listEl || !state.forecast) return;

  const forecast = state.forecast;
  const currency = forecast.currency ?? "EUR";
  const days = forecast.baseline?.days || [];
  const startDate = days[0]?.date;
  const endDate = days[days.length - 1]?.date;

  const windowTxs = (forecast.transactions || [])
    .filter((tx) => (!startDate || tx.date >= startDate) && (!endDate || tx.date <= endDate))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.amount_minor - b.amount_minor));

  const filtered = windowTxs.filter((tx) => {
    const act = inferActionability(tx);
    if (activeFilter === "actionable") {
      return act === "email_defer_supplier" || act === "email_collect_early" || act === "owner_draw_flexible";
    }
    if (activeFilter === "fixed") return act === "fixed_mandatory";
    if (activeFilter === "incoming") return tx.amount_minor > 0;
    return true;
  });

  if (countEl) {
    countEl.textContent = `${filtered.length} of ${windowTxs.length} payments`;
  }

  if (filtered.length === 0) {
    listEl.replaceChildren(
      el("p", "muted-note", "No payments match this filter in the current 14-day window."),
    );
    return;
  }

  const effectiveQuickAction = forecast.forecast_basis === "history" ? null : onQuickAction;
  listEl.replaceChildren(
    ...filtered.map((tx) => buildTransactionRow(tx, currency, effectiveQuickAction)),
  );
}

/* --------------------------------------------------------------------------
   6. "Can I Afford It?" Planned Expense Sandbox (Deterministic Integer Math)
   -------------------------------------------------------------------------- */
export function buildPlannedExpenseCurve(baselineDays, expenseMinor, expenseDate) {
  if (!baselineDays || baselineDays.length === 0 || !expenseMinor || !expenseDate) return null;
  return baselineDays.map((day) => ({
    date: day.date,
    balance_minor: day.date >= expenseDate ? day.balance_minor - expenseMinor : day.balance_minor,
  }));
}

export function initAffordSandbox({ getState, onAddPurchase, onJumpToChart, onJumpToBreakdown }) {
  const form = document.querySelector("#afford-form");
  const nameInput = document.querySelector("#afford-name-input");
  const amountInput = document.querySelector("#afford-amount-input");
  const dateInput = document.querySelector("#afford-date-input");
  const resultBox = document.querySelector("#afford-result");
  const presets = document.querySelectorAll(".afford-preset-chip");

  function syncDateBounds() {
    const forecast = getState().forecast;
    const days = forecast?.baseline?.days || [];
    if (!dateInput || days.length === 0) return;
    dateInput.min = days[0].date;
    dateInput.max = days[days.length - 1].date;
    if (!dateInput.value || dateInput.value < dateInput.min || dateInput.value > dateInput.max) {
      dateInput.value = days[Math.min(3, days.length - 1)].date;
    }
    if (resultBox) resultBox.hidden = true;
  }

  function runEvaluation() {
    const state = getState();
    const forecast = state.forecast;
    if (!forecast || !resultBox) return;

    const currency = forecast.currency ?? "EUR";
    const days = forecast.baseline?.days || [];
    const label = (nameInput?.value || "").trim() || "Planned purchase";
    const chosenDate = dateInput?.value || days[0]?.date;

    let expenseMinor = 0;
    try {
      expenseMinor = Number(toMinor(amountInput?.value || "0"));
    } catch {
      expenseMinor = 0;
    }

    if (!Number.isFinite(expenseMinor) || expenseMinor <= 0) {
      resultBox.className = "afford-result is-risky";
      resultBox.replaceChildren(
        el("p", "afford-result-detail", "Enter a positive amount to test this purchase."),
      );
      resultBox.hidden = false;
      return;
    }

    const curve = buildPlannedExpenseCurve(days, expenseMinor, chosenDate);
    if (!curve) return;

    const lowest = curve.reduce(
      (min, d) => (d.balance_minor < min.balance_minor ? d : min),
      curve[0],
    );
    const isSafe = lowest.balance_minor >= 0;

    // Check if there is a safer later date inside the window
    let safestDate = null;
    if (!isSafe) {
      for (const candidate of days) {
        if (candidate.date <= chosenDate) continue;
        const testCurve = buildPlannedExpenseCurve(days, expenseMinor, candidate.date);
        const testMin = testCurve.reduce(
          (min, d) => (d.balance_minor < min.balance_minor ? d : min),
          testCurve[0],
        );
        if (testMin.balance_minor >= 0) {
          safestDate = candidate.date;
          break;
        }
      }
    }

    onAddPurchase?.({ name: label, amountMinor: expenseMinor, date: chosenDate });

    resultBox.className = `afford-result ${isSafe ? "is-safe" : "is-risky"}`;
    const head = el("div", "afford-result-head");
    head.append(
      el(
        "h3",
        "afford-result-title",
        isSafe
          ? `Safe to buy "${label}" on ${printDate(chosenDate)}`
          : `Tight cash if you buy "${label}" on ${printDate(chosenDate)}`,
      ),
      el("span", isSafe ? "pill pill-success" : "pill pill-danger", isSafe ? "Affordable" : "Causes dip"),
    );

    const detailText = isSafe
      ? `Added to your active simulations and Expenses pie chart. After spending ${printMoney(expenseMinor, currency)}, your lowest balance stays at ${printMoney(lowest.balance_minor, currency)} on ${printDate(lowest.date)}.`
      : `Added to your active simulations and Expenses pie chart. Spending ${printMoney(expenseMinor, currency)} pushes your lowest balance to −${printMoney(Math.abs(lowest.balance_minor), currency)} on ${printDate(lowest.date)}.${
          safestDate
            ? ` Good news: waiting until ${printDate(safestDate)} keeps your balance positive!`
            : " Consider splitting the payment or using a temporary safety buffer."
        }`;

    const actions = el("div", "afford-result-actions");
    const viewBtn = el("button", "btn-link", "View on cash chart ↑");
    viewBtn.type = "button";
    viewBtn.addEventListener("click", () => onJumpToChart?.());
    const pieBtn = el("button", "btn-link", "View in Expenses pie chart ↓");
    pieBtn.type = "button";
    pieBtn.addEventListener("click", () => onJumpToBreakdown?.());
    actions.append(viewBtn, pieBtn);

    resultBox.replaceChildren(head, el("p", "afford-result-detail", detailText), actions);
    resultBox.hidden = false;
    replayFade(resultBox);
  }

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    runEvaluation();
  });

  for (const chip of presets) {
    chip.addEventListener("click", () => {
      if (nameInput) nameInput.value = chip.dataset.affordName || "";
      if (amountInput) amountInput.value = chip.dataset.affordAmount || "";
      runEvaluation();
    });
  }

  return { syncDateBounds };
}

/* --------------------------------------------------------------------------
   7. Full-Year Forecast Intelligence & Recurring Pattern Table
   -------------------------------------------------------------------------- */
export function resetForecastIntelligence() {
  const wrap = document.querySelector("#forecast-intel");
  if (wrap) wrap.hidden = true;
}

export function renderForecastIntelligence(analysis) {
  const wrap = document.querySelector("#forecast-intel");
  const metaEl = document.querySelector("#forecast-intel-meta");
  const modelEl = document.querySelector("#forecast-intel-model");
  const summaryEl = document.querySelector("#forecast-intel-summary");
  const calloutsEl = document.querySelector("#forecast-intel-callouts");
  const detailsEl = document.querySelector("#forecast-patterns-details");
  const detailsSummaryEl = document.querySelector("#forecast-patterns-summary");
  const tbodyEl = document.querySelector("#forecast-patterns-tbody");

  if (!wrap || !analysis) {
    if (wrap) wrap.hidden = true;
    return;
  }

  const currency = analysis.currency || "EUR";
  const spanDays = Number(analysis.history_span_days || 0);
  const txCount = Number(analysis.transactions_analyzed || 0);
  const months = Number(analysis.months_analyzed || 0);
  const vol = Number(analysis.daily_volatility_minor || 0);

  if (metaEl) {
    const parts = [
      `${txCount.toLocaleString()} transactions`,
      `${spanDays}d history${months >= 2 ? ` (${months} mo)` : ""}`,
    ];
    if (vol > 0) parts.push(`±${printMoney(vol, currency)}/day swing`);
    metaEl.textContent = parts.join(" · ");
  }

  if (modelEl) {
    const m = analysis.model || "demo-deterministic";
    const ms = Number.isFinite(analysis.latency_ms) && analysis.latency_ms > 0 ? ` · ${analysis.latency_ms}ms` : "";
    if (m === "demo-deterministic") {
      modelEl.textContent = "Full-year pattern engine";
    } else if (m === "deterministic-fallback") {
      modelEl.textContent = "Pattern engine (AI offline)";
    } else {
      modelEl.textContent = `AI · ${m}${ms}`;
    }
    modelEl.classList.toggle("is-live-ai", m !== "demo-deterministic" && m !== "deterministic-fallback");
  }

  if (summaryEl) {
    summaryEl.textContent = analysis.trend_summary || "";
  }

  if (calloutsEl) {
    const items = (analysis.ai_callouts || []).slice(0, 4);
    calloutsEl.replaceChildren(
      ...items.map((text) => el("span", "intel-callout-chip", text)),
    );
    calloutsEl.hidden = items.length === 0;
  }

  const patterns = analysis.patterns || [];
  if (detailsEl && tbodyEl) {
    if (patterns.length === 0) {
      detailsEl.hidden = true;
      tbodyEl.replaceChildren();
    } else {
      detailsEl.hidden = false;
      if (detailsSummaryEl) {
        detailsSummaryEl.textContent = `Inspect ${patterns.length} detected recurring schedules & payment regularity`;
      }
      const rows = patterns.map((p) => {
        const tr = document.createElement("tr");

        const cpTd = document.createElement("td");
        const dirBadge = el(
          "span",
          `pattern-dir-dot ${p.direction === "inflow" ? "is-in" : "is-out"}`,
        );
        dirBadge.setAttribute("aria-hidden", "true");
        cpTd.append(dirBadge, document.createTextNode(p.counterparty));

        const cadTd = el("td", "pattern-cadence-cell", p.cadence);
        const obsTd = el("td", "pattern-obs-cell", `${p.occurrences}×`);

        const amtTd = el(
          "td",
          `num-col pattern-amt-cell ${p.direction === "inflow" ? "pos" : "neg"}`,
          `${p.direction === "inflow" ? "+" : "−"}${printMoney(p.typical_amount_minor, currency)}`,
        );

        const regTd = document.createElement("td");
        const hasDelay = Number(p.max_delay_days || 0) > 0;
        regTd.append(
          el("span", `delay-pill ${hasDelay ? "is-drift" : "is-ontime"}`, p.regularity),
        );

        tr.append(cpTd, cadTd, obsTd, amtTd, regTd);
        return tr;
      });
      tbodyEl.replaceChildren(...rows);
    }
  }

  wrap.hidden = false;
  replayFade(wrap);
}
