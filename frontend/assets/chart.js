const SVG_NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  if (text) node.textContent = text;
  return node;
}

function niceStep(range, targetTicks = 5) {
  if (range <= 0) return 100000;
  const rough = range / targetTicks;
  const pow10 = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / pow10;
  let step;
  if (normalized <= 1) step = 1;
  else if (normalized <= 2) step = 2;
  else if (normalized <= 5) step = 5;
  else step = 10;
  return step * pow10;
}

function formatCompactMoney(minor, symbol = "€") {
  const value = minor / 100;
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1_000_000) return `${sign}${symbol}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}${symbol}${Math.round(abs / 1_000)}k`;
  if (abs >= 1_000) return `${sign}${symbol}${(abs / 1_000).toFixed(abs % 1000 === 0 ? 0 : 1)}k`;
  return `${sign}${symbol}${Math.round(abs)}`;
}

function formatShortDate(isoDate, includeYear = false) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    ...(includeYear ? { year: "2-digit" } : {}),
    timeZone: "UTC",
  }).format(d);
}

/**
 * Render an interactive cash balance SVG chart (supports 14-day, 30-day, or full-year statements).
 */
export function renderCashflowChart(container, config) {
  const {
    baselineDays,
    scenarioDays = null,
    transactionsByDate = new Map(),
    firstDeficitDate = null,
    peakDeficitDate = null,
    facilityLimitMinor = 0,
    simulationDecision = null, // null | "approved" | "rejected"
    currencySymbol = "€",
    formatMoney,
    formatDate,
  } = config;

  container.replaceChildren();

  if (!baselineDays || baselineDays.length === 0) return;

  const width = 760;
  const height = 310;
  const pad = { top: 24, right: 24, bottom: 44, left: 68 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const allValues = [0];
  for (const d of baselineDays) allValues.push(d.balance_minor);
  if (scenarioDays) {
    for (const d of scenarioDays) allValues.push(d.balance_minor);
  }
  if (simulationDecision === "approved" && facilityLimitMinor > 0) {
    allValues.push(-facilityLimitMinor);
  }

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const span = Math.max(rawMax - rawMin, 200_000);
  const step = niceStep(span, 5);
  const yMin = Math.floor((rawMin - step * 0.2) / step) * step;
  const yMax = Math.ceil((rawMax + step * 0.2) / step) * step;

  const xAt = (idx) =>
    pad.left + (baselineDays.length === 1 ? plotW / 2 : (idx / (baselineDays.length - 1)) * plotW);
  const yAt = (val) => pad.top + ((yMax - val) / (yMax - yMin)) * plotH;
  const zeroY = yAt(0);

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "cashflow-svg",
    role: "img",
    "aria-label": `${baselineDays.length}-day cash balance projection chart`,
  });

  // Gradients
  const defs = el("defs");
  const posGrad = el("linearGradient", { id: "baseline-pos-grad", x1: "0", y1: "0", x2: "0", y2: "1" });
  posGrad.append(
    el("stop", { offset: "0%", "stop-color": "#0f5132", "stop-opacity": "0.18" }),
    el("stop", { offset: "100%", "stop-color": "#0f5132", "stop-opacity": "0.01" }),
  );
  const negGrad = el("linearGradient", { id: "deficit-zone-grad", x1: "0", y1: "0", x2: "0", y2: "1" });
  negGrad.append(
    el("stop", { offset: "0%", "stop-color": "#dc2626", "stop-opacity": "0.06" }),
    el("stop", { offset: "100%", "stop-color": "#dc2626", "stop-opacity": "0.14" }),
  );
  defs.append(posGrad, negGrad);
  svg.append(defs);

  // Shaded deficit zone below 0
  if (yMin < 0) {
    const deficitTop = Math.max(pad.top, zeroY);
    const deficitHeight = Math.max(0, pad.top + plotH - deficitTop);
    svg.append(
      el("rect", {
        x: pad.left,
        y: deficitTop,
        width: plotW,
        height: deficitHeight,
        fill: "url(#deficit-zone-grad)",
      }),
    );
  }

  // Horizontal grid lines & Y labels
  const gridGroup = el("g", { class: "chart-grid" });
  for (let val = yMin; val <= yMax + 1; val += step) {
    const y = yAt(val);
    if (y < pad.top - 2 || y > pad.top + plotH + 2) continue;
    const isZero = val === 0;
    gridGroup.append(
      el("line", {
        x1: pad.left,
        y1: y,
        x2: pad.left + plotW,
        y2: y,
        class: isZero ? "grid-zero-line" : "grid-line",
      }),
    );
    gridGroup.append(
      el(
        "text",
        {
          x: pad.left - 10,
          y: y + 4,
          "text-anchor": "end",
          class: isZero ? "axis-label axis-label-zero" : "axis-label",
        },
        val === 0 ? `${currencySymbol}0` : formatCompactMoney(val, currencySymbol),
      ),
    );
  }
  svg.append(gridGroup);

  // Approved facility coverage band
  if (simulationDecision === "approved" && facilityLimitMinor > 0) {
    const limitY = yAt(-facilityLimitMinor);
    const bandTop = Math.min(zeroY, limitY);
    const bandHeight = Math.abs(limitY - zeroY);
    svg.append(
      el("rect", {
        x: pad.left,
        y: bandTop,
        width: plotW,
        height: bandHeight,
        class: "facility-band",
      }),
    );
    svg.append(
      el("line", {
        x1: pad.left,
        y1: limitY,
        x2: pad.left + plotW,
        y2: limitY,
        class: "facility-limit-line",
      }),
    );
    svg.append(
      el(
        "text",
        {
          x: pad.left + plotW - 4,
          y: limitY - 6,
          "text-anchor": "end",
          class: "facility-tag",
        },
        `Simulated facility limit (${formatCompactMoney(-facilityLimitMinor, currencySymbol)})`,
      ),
    );
  }

  // Baseline area & line
  const baselinePoints = baselineDays.map((d, i) => [xAt(i), yAt(d.balance_minor)]);
  const baselineLineD = baselinePoints
    .map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");

  const areaD = `${baselineLineD} L ${xAt(baselineDays.length - 1).toFixed(1)} ${zeroY.toFixed(1)} L ${xAt(0).toFixed(1)} ${zeroY.toFixed(1)} Z`;
  svg.append(el("path", { d: areaD, fill: "url(#baseline-pos-grad)" }));
  svg.append(el("path", { d: baselineLineD, fill: "none", class: "line-baseline" }));

  // Scenario (what-if) line
  if (scenarioDays && scenarioDays.length === baselineDays.length) {
    const scenarioD = scenarioDays
      .map((d, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(d.balance_minor).toFixed(1)}`)
      .join(" ");
    svg.append(el("path", { d: scenarioD, fill: "none", class: "line-scenario" }));
  }

  // Data points & X axis labels
  const pointsGroup = el("g", { class: "chart-points" });
  const xLabelsGroup = el("g", { class: "chart-x-labels" });
  const showAllDots = baselineDays.length <= 45;
  const labelInterval = Math.max(1, Math.ceil(baselineDays.length / 7));
  const includeYear = baselineDays.length > 90;

  baselineDays.forEach((day, i) => {
    const x = xAt(i);
    const y = yAt(day.balance_minor);
    const isNegative = day.balance_minor < 0;
    const isKeyDeficit = day.date === firstDeficitDate || day.date === peakDeficitDate;

    if (isKeyDeficit) {
      pointsGroup.append(el("circle", { cx: x, cy: y, r: 8, class: "point-ring-deficit" }));
    }

    if (showAllDots || isKeyDeficit) {
      pointsGroup.append(
        el("circle", {
          cx: x,
          cy: y,
          r: isKeyDeficit ? 4.5 : 3.5,
          class: isNegative ? "point-deficit" : "point-baseline",
        }),
      );
    }

    if (showAllDots && scenarioDays && scenarioDays[i]) {
      const sy = yAt(scenarioDays[i].balance_minor);
      pointsGroup.append(
        el("circle", {
          cx: x,
          cy: sy,
          r: 3.5,
          class: scenarioDays[i].balance_minor < 0 ? "point-deficit" : "point-scenario",
        }),
      );
    }

    if (i % labelInterval === 0 || i === baselineDays.length - 1) {
      xLabelsGroup.append(
        el(
          "text",
          {
            x,
            y: height - 14,
            "text-anchor": "middle",
            class: "axis-label",
          },
          formatShortDate(day.date, includeYear),
        ),
      );
    }
  });

  svg.append(pointsGroup, xLabelsGroup);

  // Hover crosshair
  const crosshair = el("line", {
    x1: pad.left,
    y1: pad.top,
    x2: pad.left,
    y2: pad.top + plotH,
    class: "chart-crosshair",
    visibility: "hidden",
  });
  svg.append(crosshair);

  // Floating tooltip
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;

  // Interactive hover columns (sample every step if > 120 days to keep DOM light)
  const hitGroup = el("g", { class: "chart-hits" });
  const hitStep = baselineDays.length > 120 ? Math.ceil(baselineDays.length / 90) : 1;
  const colWidth = (plotW / Math.max(1, baselineDays.length - 1)) * hitStep;

  for (let i = 0; i < baselineDays.length; i += hitStep) {
    const day = baselineDays[i];
    const cx = xAt(i);
    const rectX = i === 0 ? pad.left : cx - colWidth / 2;

    const hit = el("rect", {
      x: Math.max(pad.left, rectX),
      y: pad.top,
      width: Math.max(8, colWidth),
      height: plotH,
      fill: "transparent",
      tabindex: "0",
      "aria-label": `${formatDate(day.date)}: ${formatMoney(day.balance_minor)}`,
    });

    const showTip = () => {
      crosshair.setAttribute("x1", String(cx));
      crosshair.setAttribute("x2", String(cx));
      crosshair.setAttribute("visibility", "visible");

      const lines = [
        `<div class="tip-date">${formatDate(day.date)}</div>`,
        `<div class="tip-row"><span>Baseline</span><strong class="${day.balance_minor < 0 ? "neg" : ""}">${formatMoney(day.balance_minor)}</strong></div>`,
      ];

      if (scenarioDays && scenarioDays[i]) {
        const adj = scenarioDays[i].balance_minor;
        lines.push(
          `<div class="tip-row"><span>Adjusted</span><strong class="${adj < 0 ? "neg" : "pos"}">${formatMoney(adj)}</strong></div>`,
        );
      }

      if (simulationDecision) {
        const rawGap = Math.max(0, -day.balance_minor);
        const uncovered =
          simulationDecision === "approved"
            ? Math.max(0, rawGap - facilityLimitMinor)
            : rawGap;
        lines.push(
          `<div class="tip-row"><span>Uncovered gap (${simulationDecision})</span><strong class="${uncovered > 0 ? "neg" : "pos"}">${formatMoney(uncovered)}</strong></div>`,
        );
      }

      const dayTxs = transactionsByDate.get(day.date) || [];
      if (dayTxs.length > 0) {
        lines.push(`<div class="tip-divider"></div>`);
        for (const tx of dayTxs.slice(0, 4)) {
          const sign = tx.amount_minor > 0 ? "+" : "";
          const fxNote =
            tx.original_currency && tx.original_currency !== "EUR"
              ? ` (${tx.original_currency})`
              : "";
          lines.push(
            `<div class="tip-tx"><span>${tx.label}${fxNote}</span><strong class="${tx.amount_minor < 0 ? "neg" : "pos"}">${sign}${formatMoney(tx.amount_minor)}</strong></div>`,
          );
        }
        if (dayTxs.length > 4) {
          lines.push(`<div class="tip-tx"><span>+${dayTxs.length - 4} more transactions</span></div>`);
        }
      }

      tooltip.innerHTML = lines.join("");
      tooltip.hidden = false;

      const pct = cx / width;
      tooltip.style.left = `${Math.min(Math.max(pct * 100, 14), 86)}%`;
    };

    const hideTip = () => {
      crosshair.setAttribute("visibility", "hidden");
      tooltip.hidden = true;
    };

    hit.addEventListener("mouseenter", showTip);
    hit.addEventListener("focus", showTip);
    hit.addEventListener("mouseleave", hideTip);
    hit.addEventListener("blur", hideTip);

    hitGroup.append(hit);
  }

  svg.append(hitGroup);
  container.append(svg, tooltip);
}
