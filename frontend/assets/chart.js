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

function escapeText(value) {
  const text = document.createElement("span");
  text.textContent = value;
  return text.innerHTML;
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
 * Render an interactive cash balance chart with optional recorded balances and scenario overlays.
 */
export function renderCashflowChart(container, config) {
  const {
    historyDays = [],
    estimatedFromHistory = false,
    baselineDays,
    scenarioDays = null,
    decisionDays = null,
    forecastDays = null,
    whatIfDays = null,
    whatIfLabel = "What-if",
    stressDays = null,
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

  const hasForecast = !estimatedFromHistory && Boolean(forecastDays?.length);
  const hasFutureStress = !estimatedFromHistory && Boolean(stressDays?.length);
  const windowStressDays = estimatedFromHistory ? stressDays : null;
  const futureDays = hasForecast ? forecastDays : hasFutureStress ? stressDays : [];
  const hasFuture = futureDays.length > 0;
  const baselineStartIdx = historyDays.length;
  const baselineEndIdx = baselineStartIdx + baselineDays.length - 1;
  const hasHistory = baselineStartIdx > 0;
  const allDays = [...historyDays, ...baselineDays, ...futureDays];

  const width = 760;
  const height = 330;
  const pad = { top: 34, right: 32, bottom: 44, left: 68 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const allValues = [0];
  for (const d of [...historyDays, ...baselineDays]) allValues.push(d.balance_minor);
  if (scenarioDays) {
    for (const d of scenarioDays) allValues.push(d.balance_minor);
  }
  if (hasForecast) {
    for (const d of forecastDays) {
      allValues.push(d.balance_minor, d.low_minor, d.high_minor);
    }
  }
  if (whatIfDays) {
    for (const d of whatIfDays) allValues.push(d.balance_minor);
  }
  if (stressDays) {
    for (const d of stressDays) allValues.push(d.balance_minor);
  }
  if (simulationDecision === "approved" && facilityLimitMinor > 0) {
    allValues.push(-facilityLimitMinor);
  }

  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const span = Math.max(rawMax - rawMin, 200_000);
  const step = niceStep(span, 5);
  const yMin = Math.floor((rawMin - step * 0.25) / step) * step;
  const yMax = Math.ceil((rawMax + step * 0.35) / step) * step;

  const xAt = (idx) =>
    pad.left + (allDays.length === 1 ? plotW / 2 : (idx / (allDays.length - 1)) * plotW);
  const yAt = (val) => pad.top + ((yMax - val) / (yMax - yMin)) * plotH;
  const zeroY = yAt(0);
  const baselineX = (idx) => xAt(baselineStartIdx + idx);
  const historyDividerX = (xAt(baselineStartIdx - 1) + baselineX(0)) / 2;
  const linePath = (days, x) => days
    .map((day, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${yAt(day.balance_minor).toFixed(1)}`)
    .join(" ");

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "cashflow-svg",
    role: "img",
    "aria-label": hasHistory
      ? `${historyDays.length} days of recorded balances and ${baselineDays.length} days of estimated balances`
      : `${baselineDays.length}-day cash balance projection chart`,
  });

  // Gradients
  const defs = el("defs");
  const posGrad = el("linearGradient", { id: "baseline-pos-grad", x1: "0", y1: "0", x2: "0", y2: "1" });
  posGrad.append(
    el("stop", { offset: "0%", "stop-color": "#121211", "stop-opacity": "0.10" }),
    el("stop", { offset: "100%", "stop-color": "#121211", "stop-opacity": "0.01" }),
  );
  const negGrad = el("linearGradient", { id: "deficit-zone-grad", x1: "0", y1: "0", x2: "0", y2: "1" });
  negGrad.append(
    el("stop", { offset: "0%", "stop-color": "#dc2626", "stop-opacity": "0.06" }),
    el("stop", { offset: "100%", "stop-color": "#dc2626", "stop-opacity": "0.14" }),
  );
  defs.append(posGrad, negGrad);
  svg.append(defs);

  // Shade the estimated portion of the chart.
  if (hasHistory || hasFuture) {
    const dividerX = hasHistory ? historyDividerX : xAt(baselineEndIdx);
    const zoneW = Math.max(0, pad.left + plotW - dividerX);
    svg.append(
      el("rect", {
        x: dividerX,
        y: pad.top,
        width: zoneW,
        height: plotH,
        class: "forecast-zone",
      }),
    );
  }

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

  if (hasHistory) {
    svg.append(
      el("line", {
        x1: historyDividerX,
        y1: pad.top,
        x2: historyDividerX,
        y2: pad.top + plotH,
        class: "forecast-divider history-divider",
      }),
      el("text", {
        x: (pad.left + historyDividerX) / 2,
        y: pad.top - 12,
        "text-anchor": "middle",
        class: "chart-period-label",
      }, "Recorded balance"),
      el("text", {
        x: (historyDividerX + pad.left + plotW) / 2,
        y: pad.top - 12,
        "text-anchor": "middle",
        class: "chart-period-label chart-period-estimate",
      }, "Estimated forecast"),
    );
  }

  // Approved facility coverage band
  if (simulationDecision === "approved" && facilityLimitMinor > 0) {
    const limitY = yAt(-facilityLimitMinor);
    const bandTop = Math.min(zeroY, limitY);
    const bandHeight = Math.abs(limitY - zeroY);
    const bandStart = hasHistory ? historyDividerX : pad.left;
    svg.append(
      el("rect", {
        x: bandStart,
        y: bandTop,
        width: pad.left + plotW - bandStart,
        height: bandHeight,
        class: "facility-band",
      }),
    );
    svg.append(
      el("line", {
        x1: bandStart,
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
          y: Math.min(limitY + 14, pad.top + plotH - 4),
          "text-anchor": "end",
          class: "facility-tag",
        },
        `Safety buffer (${formatCompactMoney(-facilityLimitMinor, currencySymbol)})`,
      ),
    );
  }

  // Forward projection cone + dashed divider + trend & stress lines
  if (hasFuture) {
    const lastX = xAt(baselineEndIdx);
    const lastY = yAt(baselineDays[baselineDays.length - 1].balance_minor);

    svg.append(
      el("line", {
        x1: lastX,
        y1: pad.top,
        x2: lastX,
        y2: pad.top + plotH,
        class: "forecast-divider",
      }),
    );
    svg.append(
      el(
        "text",
        {
          x: Math.min(lastX + 6, pad.left + plotW - 84),
          y: pad.top + 14,
          class: "forecast-divider-label",
        },
        `Projected +${futureDays.length}d →`,
      ),
    );

    if (hasForecast) {
      const upperPts = [
        [lastX, lastY],
        ...forecastDays.map((d, j) => [xAt(baselineEndIdx + j + 1), yAt(d.high_minor)]),
      ];
      const lowerPts = [
        ...forecastDays
          .map((d, j) => [xAt(baselineEndIdx + j + 1), yAt(d.low_minor)])
          .reverse(),
        [lastX, lastY],
      ];
      const bandPath = [
        ...upperPts.map(([x, y], idx) => `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`),
        ...lowerPts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`),
        "Z",
      ].join(" ");
      svg.append(el("path", { d: bandPath, class: "forecast-band" }));

      const trendPts = [
        [lastX, lastY],
        ...forecastDays.map((d, j) => [xAt(baselineEndIdx + j + 1), yAt(d.balance_minor)]),
      ];
      const trendD = trendPts
        .map(([x, y], idx) => `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
        .join(" ");
      svg.append(el("path", { d: trendD, fill: "none", class: "line-forecast" }));
    }

    if (hasFutureStress) {
      const stressPts = [
        [lastX, lastY],
        ...stressDays.map((d, j) => [xAt(baselineEndIdx + j + 1), yAt(d.balance_minor)]),
      ];
      const stressD = stressPts
        .map(([x, y], idx) => `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
        .join(" ");
      svg.append(el("path", { d: stressD, fill: "none", class: "line-stress" }));
    }
  }

  if (hasHistory) {
    svg.append(el("path", { d: linePath(historyDays, xAt), fill: "none", class: "line-baseline line-history" }));
  }

  const baselineLineD = linePath(baselineDays, baselineX);
  if (!estimatedFromHistory) {
    const areaD = `${baselineLineD} L ${xAt(baselineEndIdx).toFixed(1)} ${zeroY.toFixed(1)} L ${baselineX(0).toFixed(1)} ${zeroY.toFixed(1)} Z`;
    svg.append(el("path", { d: areaD, fill: "url(#baseline-pos-grad)" }));
  }
  svg.append(el("path", {
    d: baselineLineD,
    fill: "none",
    class: estimatedFromHistory ? "line-estimate" : "line-baseline",
  }));

  if (scenarioDays?.length === baselineDays.length) {
    svg.append(el("path", { d: linePath(scenarioDays, baselineX), fill: "none", class: "line-scenario" }));
  }
  if (whatIfDays?.length === baselineDays.length) {
    svg.append(el("path", { d: linePath(whatIfDays, baselineX), fill: "none", class: "line-whatif" }));
  }
  if (windowStressDays?.length === baselineDays.length) {
    svg.append(el("path", { d: linePath(windowStressDays, baselineX), fill: "none", class: "line-stress" }));
  }

  // Data points & X axis labels anchored to the CSV boundaries
  const pointsGroup = el("g", { class: "chart-points" });
  const xLabelsGroup = el("g", { class: "chart-x-labels" });
  const showAllDots = allDays.length <= 45;
  const includeYear =
    allDays.length > 90 ||
    allDays[0].date.slice(0, 4) !== allDays[allDays.length - 1].date.slice(0, 4);

  const tickIndices = new Set([0, baselineStartIdx, baselineEndIdx, allDays.length - 1]);
  const addMidTicks = (fromIdx, toIdx, count) => {
    const span = toIdx - fromIdx;
    if (span < 4) return;
    for (let k = 1; k <= count; k += 1) {
      const idx = Math.round(fromIdx + (span * k) / (count + 1));
      if (idx - fromIdx >= 3 && toIdx - idx >= 3) {
        tickIndices.add(idx);
      }
    }
  };
  if (hasHistory) {
    tickIndices.add(baselineStartIdx - 1);
    addMidTicks(0, baselineStartIdx - 1, 1);
    addMidTicks(baselineStartIdx, baselineEndIdx, 1);
  } else {
    addMidTicks(0, baselineEndIdx, hasFuture ? 2 : 3);
  }
  if (hasFuture) {
    addMidTicks(baselineEndIdx, allDays.length - 1, 2);
  }

  for (const [i, day] of historyDays.entries()) {
    pointsGroup.append(el("circle", {
      cx: xAt(i),
      cy: yAt(day.balance_minor),
      r: 3.5,
      class: "point-baseline point-history",
    }));
  }

  baselineDays.forEach((day, i) => {
    const x = baselineX(i);
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
          class: isNegative ? "point-deficit" : estimatedFromHistory ? "point-forecast" : "point-baseline",
        }),
      );
    }

    if (day.date === peakDeficitDate && day.balance_minor < 0) {
      const labelY = y + 18 <= pad.top + plotH - 4 ? y + 18 : Math.max(pad.top + 12, y - 12);
      const chartIndex = baselineStartIdx + i;
      const anchor = chartIndex > allDays.length - 4 ? "end" : chartIndex < 2 ? "start" : "middle";
      pointsGroup.append(
        el(
          "text",
          {
            x,
            y: labelY,
            "text-anchor": anchor,
            class: "chart-callout-peak",
          },
          `Lowest ${formatCompactMoney(day.balance_minor, currencySymbol)}`,
        ),
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

    if (showAllDots && whatIfDays && whatIfDays[i]) {
      const wy = yAt(whatIfDays[i].balance_minor);
      pointsGroup.append(
        el("circle", {
          cx: x,
          cy: wy,
          r: 3.5,
          class: whatIfDays[i].balance_minor < 0 ? "point-deficit" : "point-whatif",
        }),
      );
    }
  });

  let forecastEndLabelY = null;
  if (hasForecast) {
    forecastDays.forEach((day, j) => {
      const x = xAt(baselineEndIdx + j + 1);
      const y = yAt(day.balance_minor);
      if (showAllDots || j === forecastDays.length - 1) {
        pointsGroup.append(
          el("circle", {
            cx: x,
            cy: y,
            r: j === forecastDays.length - 1 ? 4.2 : 3,
            class: "point-forecast",
          }),
        );
      }
      if (j === forecastDays.length - 1) {
        forecastEndLabelY = Math.max(pad.top + 14, Math.min(pad.top + plotH - 6, y - 10));
        pointsGroup.append(
          el(
            "text",
            {
              x,
              y: forecastEndLabelY,
              "text-anchor": "end",
              class: "chart-callout-forecast",
            },
            `Est. ${formatCompactMoney(day.balance_minor, currencySymbol)}`,
          ),
        );
      }
    });
  }

  if (hasFutureStress) {
    stressDays.forEach((day, j) => {
      const x = xAt(baselineEndIdx + j + 1);
      const y = yAt(day.balance_minor);
      if (showAllDots || j === stressDays.length - 1) {
        pointsGroup.append(
          el("circle", {
            cx: x,
            cy: y,
            r: j === stressDays.length - 1 ? 4.2 : 2.8,
            class: "point-stress",
          }),
        );
      }
      if (j === stressDays.length - 1) {
        let stressLabelY = Math.min(pad.top + plotH - 4, Math.max(pad.top + 14, y + 15));
        if (forecastEndLabelY !== null && Math.abs(stressLabelY - forecastEndLabelY) < 14) {
          stressLabelY = Math.min(pad.top + plotH - 4, forecastEndLabelY + 15);
        }
        pointsGroup.append(
          el(
            "text",
            {
              x,
              y: stressLabelY,
              "text-anchor": "end",
              class: "chart-callout-stress",
            },
            `Stress ${formatCompactMoney(day.balance_minor, currencySymbol)}`,
          ),
        );
      }
    });
  }

  for (const i of [...tickIndices].sort((a, b) => a - b)) {
    const day = allDays[i];
    if (!day) continue;
    xLabelsGroup.append(
      el(
        "text",
        {
          x: xAt(i),
          y: height - 14,
          "text-anchor": hasHistory && i === baselineStartIdx - 1
            ? "end"
            : hasHistory && i === baselineStartIdx ? "start" : "middle",
          class:
            (hasHistory && i === baselineStartIdx - 1) || (hasFuture && i === baselineEndIdx)
              ? "axis-label axis-label-divider"
              : i > baselineEndIdx || (estimatedFromHistory && i >= baselineStartIdx)
                ? "axis-label axis-label-forecast"
                : "axis-label",
        },
        formatShortDate(day.date, includeYear),
      ),
    );
  }

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

  const decisionByDate = new Map((decisionDays || []).map((d) => [d.date, d]));

  // Floating tooltip
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;

  // Interactive hover columns across baseline + forecast days
  const hitGroup = el("g", { class: "chart-hits" });
  const hitStep = allDays.length > 120 ? Math.ceil(allDays.length / 90) : 1;
  const colWidth = (plotW / Math.max(1, allDays.length - 1)) * hitStep;

  for (let i = 0; i < allDays.length; i += hitStep) {
    const day = allDays[i];
    const isRecorded = i < baselineStartIdx;
    const isPredicted = i > baselineEndIdx;
    const chartBalanceLabel = isRecorded
      ? "Recorded balance"
      : isPredicted || estimatedFromHistory ? "Estimated balance" : "Projected cash";
    const baselineIndex = i - baselineStartIdx;
    const cx = xAt(i);
    const rectX = Math.max(pad.left, cx - colWidth / 2);
    const rectEnd = Math.min(pad.left + plotW, cx + colWidth / 2);

    const hit = el("rect", {
      x: rectX,
      y: pad.top,
      width: rectEnd - rectX,
      height: plotH,
      fill: "transparent",
      tabindex: "0",
      "aria-label": `${formatDate(day.date)}. ${chartBalanceLabel}: ${formatMoney(day.balance_minor)}`,
    });

    const showTip = () => {
      crosshair.setAttribute("x1", String(cx));
      crosshair.setAttribute("x2", String(cx));
      crosshair.setAttribute("visibility", "visible");

      const lines = [`<div class="tip-date">${formatDate(day.date)}</div>`];

      if (isRecorded) {
        lines.push(
          `<div class="tip-row"><span>Recorded balance</span><strong class="${day.balance_minor < 0 ? "neg" : ""}">${formatMoney(day.balance_minor)}</strong></div>`,
        );
      } else if (isPredicted) {
        const futureIdx = i - baselineEndIdx - 1;
        if (hasForecast && forecastDays[futureIdx]) {
          const fDay = forecastDays[futureIdx];
          lines.push(
            `<div class="tip-row"><span>Predicted cash</span><strong class="${fDay.balance_minor < 0 ? "neg" : ""}">${formatMoney(fDay.balance_minor)}</strong></div>`,
            `<div class="tip-row"><span>Confidence range</span><strong>${formatMoney(fDay.low_minor)} to ${formatMoney(fDay.high_minor)}</strong></div>`,
          );
        }
        if (hasFutureStress && stressDays[futureIdx]) {
          const sDay = stressDays[futureIdx];
          lines.push(
            `<div class="tip-row"><span>Stress case</span><strong class="${sDay.balance_minor < 0 ? "neg" : ""}">${formatMoney(sDay.balance_minor)}</strong></div>`,
          );
        }
        const tipNote = hasFutureStress
          ? "Projected from −15% inflows / +10% outflows"
          : "Projected from 14-day trend";
        lines.push(`<div class="tip-tx"><span>${tipNote}</span></div>`);
      } else {
        lines.push(
          `<div class="tip-row"><span>${chartBalanceLabel}</span><strong class="${day.balance_minor < 0 ? "neg" : ""}">${formatMoney(day.balance_minor)}</strong></div>`,
        );

        if (windowStressDays?.[baselineIndex]) {
          const stressBalance = windowStressDays[baselineIndex].balance_minor;
          lines.push(
            `<div class="tip-row"><span>Stress case</span><strong class="${stressBalance < 0 ? "neg" : ""}">${formatMoney(stressBalance)}</strong></div>`,
            '<div class="tip-tx"><span>Receipts five days later · expenses 10% higher</span></div>',
          );
        }

        if (scenarioDays?.[baselineIndex]) {
          const adj = scenarioDays[baselineIndex].balance_minor;
          lines.push(
            `<div class="tip-row"><span>If paid earlier</span><strong class="${adj < 0 ? "neg" : "pos"}">${formatMoney(adj)}</strong></div>`,
          );
        }

        if (whatIfDays?.[baselineIndex]) {
          const wVal = whatIfDays[baselineIndex].balance_minor;
          lines.push(
            `<div class="tip-row"><span>${escapeText(whatIfLabel)}</span><strong class="${wVal < 0 ? "neg" : "pos"}">${formatMoney(wVal)}</strong></div>`,
          );
        }

        if (simulationDecision) {
          const serverDay = decisionByDate.get(day.date);
          const rawGap = Math.max(0, -day.balance_minor);
          const uncovered = serverDay
            ? serverDay.uncovered_minor
            : simulationDecision === "approved"
              ? Math.max(0, rawGap - facilityLimitMinor)
              : rawGap;
          const statusLabel = simulationDecision === "approved" ? "approved" : "rejected";
          lines.push(
            `<div class="tip-row"><span>Still short (${statusLabel})</span><strong class="${uncovered > 0 ? "neg" : "pos"}">${formatMoney(uncovered)}</strong></div>`,
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
              `<div class="tip-tx"><span>${escapeText(tx.label + fxNote)}</span><strong class="${tx.amount_minor < 0 ? "neg" : "pos"}">${sign}${formatMoney(tx.amount_minor)}</strong></div>`,
            );
          }
          if (dayTxs.length > 4) {
            lines.push(`<div class="tip-tx"><span>+${dayTxs.length - 4} more transactions</span></div>`);
          }
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
    hit.addEventListener("click", showTip);
    hit.addEventListener("mouseleave", hideTip);
    hit.addEventListener("blur", hideTip);

    hitGroup.append(hit);
  }

  svg.append(hitGroup);
  container.append(svg, tooltip);
}
