import { buildInsightPayload, request } from "./api.js";
import { printMoney, replayFade } from "./format.js";

const AUTONOMY_BADGE_MAP = {
  1: { label: "1 · Analyzed by agent", cls: "level-1" },
  2: { label: "2 · Agent recommends", cls: "level-2" },
  3: { label: "3 · Your decision needed", cls: "level-3" },
  4: { label: "4 · Simulation only — nothing sent", cls: "level-4" },
  analyzed: { label: "1 · Analyzed by agent", cls: "level-1" },
  recommended: { label: "2 · Agent recommends", cls: "level-2" },
  requires_approval: { label: "3 · Your decision needed", cls: "level-3" },
  simulation_only: { label: "4 · Simulation only — nothing sent", cls: "level-4" },
};

const FALLBACK_MCP_MANIFEST = {
  protocol: "mcp",
  protocol_version: "2024-11-05",
  server_name: "kernes-cfo-mcp",
  server_version: "0.1.0",
  is_fallback: true,
  tools: [
    {
      name: "liquidity_stress_test",
      description: "Runs deterministic 14-day liquidity stress scenarios and computes safety buffer.",
      autonomy_level: "analyzed",
      annotations: { autonomy_badge: "1 · Analyzed by agent", agent: "Liquidity Agent" },
    },
    {
      name: "liquidity_optimize_payments",
      description: "Identifies negotiable payment timing shifts to reduce working-capital shortfall.",
      autonomy_level: "recommended",
      annotations: { autonomy_badge: "2 · Agent recommends", agent: "Liquidity Agent" },
    },
    {
      name: "fx_hedging_agent",
      description: "Scans cross-border exposure and simulates Commerzbank FX Forward and FX Option hedges.",
      autonomy_level: "simulation_only",
      annotations: { autonomy_badge: "4 · Simulation only — nothing sent", agent: "FX Hedging Agent" },
    },
    {
      name: "tax_planning_agent",
      description: "Estimates quarterly advance tax reserve, deductible operating costs, and coverage checks.",
      autonomy_level: "recommended",
      annotations: { autonomy_badge: "2 · Agent recommends", agent: "Tax Agent" },
    },
    {
      name: "investment_advisory_agent",
      description: "Evaluates investable surplus above stress buffer for Festgeld, Money Market, or Capex Leasing.",
      autonomy_level: "simulation_only",
      annotations: { autonomy_badge: "4 · Simulation only — nothing sent", agent: "Investment Agent" },
    },
  ],
};

const containerRequestSeq = new WeakMap();

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "" && text !== null && text !== undefined) {
    node.textContent = String(text);
  }
  return node;
}

function makeAutonomyBadge(level, dark = false) {
  const meta = AUTONOMY_BADGE_MAP[level] || AUTONOMY_BADGE_MAP[1];
  const suffix = dark && meta.cls !== "level-1" ? "-dark" : "";
  return el("span", `autonomy-badge ${meta.cls}${suffix}`, meta.label);
}

function pickMinor(obj, keys, fallback = 0) {
  if (!obj || typeof obj !== "object") return fallback;
  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null && !Number.isNaN(Number(obj[key]))) {
      return Math.trunc(Number(obj[key]));
    }
  }
  return fallback;
}

function pickStr(obj, keys, fallback = "") {
  if (!obj || typeof obj !== "object") return fallback;
  for (const key of keys) {
    if (typeof obj[key] === "string" && obj[key].trim()) {
      return obj[key].trim();
    }
  }
  return fallback;
}

function pickArr(obj, keys) {
  if (!obj || typeof obj !== "object") return [];
  for (const key of keys) {
    if (Array.isArray(obj[key])) return obj[key];
  }
  return [];
}

function buildSampleMcpCurl(toolName = "fx_hedging_agent", currency = "EUR") {
  const origin =
    typeof window !== "undefined" && window.location && window.location.origin
      ? window.location.origin
      : "http://127.0.0.1:8000";
  const payload = JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {
      name: toolName,
      arguments: {
        currency,
        baseline: { days: [], first_deficit: null },
        transactions: [],
      },
    },
  });
  return `curl -sS -X POST "${origin}/mcp" -H "Content-Type: application/json" -d '${payload}'`;
}

async function copyText(text) {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fallback below
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "true");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

function renderLoadingSkeleton(container) {
  const wrap = el("section", "cfo-suite");
  wrap.setAttribute("aria-label", "Loading Autonomous Multi-Agent CFO Suite");

  const header = el("div", "cfo-suite-header");
  header.append(
    el("span", "cfo-suite-eyebrow", "Autonomous Multi-Agent CFO Suite"),
    el("h2", "cfo-suite-title", "Coordinating Liquidity, FX, Tax, and Investment agents..."),
    el("div", "thinking-row"),
  );
  const thinkRow = header.lastChild;
  thinkRow.append(
    el("span", "spinner"),
    el("span", "", "Running deterministic sub-agent analysis and MCP tool discovery"),
  );

  const grid = el("div", "cfo-skeleton-grid");
  for (let i = 0; i < 3; i += 1) {
    const card = el("div", "cfo-skeleton-card");
    card.append(
      el("div", "cfo-skeleton-bar is-short"),
      el("div", "cfo-skeleton-bar is-title"),
      el("div", "cfo-skeleton-bar"),
      el("div", "cfo-skeleton-bar"),
      el("div", "cfo-skeleton-bar is-short"),
    );
    grid.append(card);
  }

  wrap.append(header, grid);
  container.replaceChildren(wrap);
}

function renderErrorState(container, message, onRetry) {
  const wrap = el("section", "cfo-suite");
  const card = el("div", "cfo-error-card");
  const copy = el("div", "cfo-error-copy");
  copy.append(
    el("strong", "", "Multi-Agent CFO Suite unavailable"),
    el("span", "", message || "Could not load sub-agent analysis right now."),
  );
  card.append(copy);

  if (typeof onRetry === "function") {
    const btn = el("button", "btn btn-primary", "Try again");
    btn.type = "button";
    btn.addEventListener("click", onRetry);
    card.append(btn);
  }

  wrap.append(card);
  container.replaceChildren(wrap);
}

function buildHeaderStrip(data, mcpManifest, currency) {
  const manifest =
    mcpManifest && Array.isArray(mcpManifest.tools) ? mcpManifest : FALLBACK_MCP_MANIFEST;
  const protocolVersion = pickStr(manifest, ["protocol_version", "protocolVersion"], "2024-11-05");
  const serverName = pickStr(manifest, ["server_name", "serverName"], "kernes-cfo-mcp");
  const tools = manifest.tools || [];
  const isFallback = Boolean(manifest.is_fallback);

  const header = el("div", "cfo-suite-header");

  const top = el("div", "cfo-suite-header-top");
  const titleBlock = el("div", "cfo-suite-title-block");
  const eyebrowRow = el("div", "cfo-suite-eyebrow-row");
  eyebrowRow.append(
    el("span", "cfo-suite-eyebrow", "Autonomous Multi-Agent CFO Suite"),
    makeAutonomyBadge(1, false),
  );
  const title = el("h2", "cfo-suite-title", "4 Coordinated CFO Agents Active");
  const headlineText = pickStr(
    data,
    ["summary_headline", "headline", "summary"],
    "Liquidity, FX Hedging, Tax Planning, and Investment agents evaluated your 14-day cash forecast.",
  );
  const headline = el("p", "cfo-suite-headline", headlineText);
  titleBlock.append(eyebrowRow, title, headline);

  const mcpControls = el("div", "cfo-mcp-controls");
  const mcpBtn = el("button", "cfo-mcp-badge-btn");
  mcpBtn.type = "button";
  mcpBtn.setAttribute("aria-expanded", "false");

  const mcpDot = el("span", `cfo-mcp-dot${isFallback ? " is-fallback" : ""}`);
  mcpDot.setAttribute("aria-hidden", "true");
  const mcpLabel = el(
    "span",
    "",
    `MCP ${protocolVersion} · ${tools.length} tool${tools.length === 1 ? "" : "s"} ${isFallback ? "standby" : "ready"}`,
  );
  const chevron = el("span", "cfo-mcp-chevron", "v");
  chevron.setAttribute("aria-hidden", "true");
  mcpBtn.append(mcpDot, mcpLabel, chevron);
  mcpControls.append(mcpBtn);

  top.append(titleBlock, mcpControls);

  const strip = el("div", "cfo-agent-strip");
  strip.setAttribute("role", "list");
  strip.setAttribute("aria-label", "Active Challenge Card agents");

  const agents = [
    { name: "Liquidity Agent", role: "Core Forecast" },
    { name: "FX Hedging Agent", role: "Cross-Border" },
    { name: "Tax Agent", role: "Reserves & VAT" },
    { name: "Investment Agent", role: "Surplus & Capex" },
  ];
  for (const agent of agents) {
    const pill = el("div", "cfo-agent-pill");
    pill.setAttribute("role", "listitem");
    const left = el("div", "cfo-agent-pill-left");
    const dot = el("span", "cfo-agent-status-dot");
    dot.setAttribute("aria-hidden", "true");
    left.append(dot, el("span", "cfo-agent-pill-name", agent.name));
    pill.append(left, el("span", "cfo-agent-pill-role", agent.role));
    strip.append(pill);
  }

  // Expandable MCP Tool Inspector Drawer
  const drawer = el("div", "cfo-mcp-drawer");
  drawer.hidden = true;

  const drawerHead = el("div", "cfo-mcp-drawer-head");
  drawerHead.append(
    el("h3", "cfo-mcp-drawer-title", "Model Context Protocol (MCP) Live Tool Registry"),
    el("span", "cfo-mcp-drawer-meta", `${serverName} · JSON-RPC 2.0 · POST /mcp`),
  );

  const toolList = el("div", "cfo-mcp-tool-list");
  for (const tool of tools) {
    const item = el("div", "cfo-mcp-tool-item");
    const itemTop = el("div", "cfo-mcp-tool-top");
    itemTop.append(el("span", "cfo-mcp-tool-name", tool.name || "unnamed_tool"));

    const badgeText =
      tool.annotations?.autonomy_badge ||
      AUTONOMY_BADGE_MAP[tool.autonomy_level]?.label ||
      "1 · Analyzed by agent";
    itemTop.append(el("span", "cfo-mcp-tool-level", badgeText));

    item.append(itemTop, el("p", "cfo-mcp-tool-desc", tool.description || "Deterministic CFO tool."));
    toolList.append(item);
  }

  const sampleTool = tools.find((t) => t.name === "fx_hedging_agent")?.name || tools[0]?.name || "liquidity_stress_test";
  const curlCommand = buildSampleMcpCurl(sampleTool, currency);

  const curlBox = el("div", "cfo-mcp-curl-box");
  const curlHead = el("div", "cfo-mcp-curl-head");
  curlHead.append(el("span", "cfo-mcp-curl-label", "Sample JSON-RPC 2.0 tools/call (POST /mcp)"));

  const copyBtn = el("button", "cfo-mcp-copy-btn", "Copy JSON-RPC curl");
  copyBtn.type = "button";
  copyBtn.addEventListener("click", async () => {
    const ok = await copyText(curlCommand);
    copyBtn.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => {
      copyBtn.textContent = "Copy JSON-RPC curl";
    }, 1800);
  });
  curlHead.append(copyBtn);

  const curlCode = el("pre", "cfo-mcp-curl-code", curlCommand);
  curlBox.append(curlHead, curlCode);

  drawer.append(drawerHead, toolList, curlBox);

  mcpBtn.addEventListener("click", () => {
    const nextOpen = drawer.hidden;
    drawer.hidden = !nextOpen;
    mcpBtn.setAttribute("aria-expanded", nextOpen ? "true" : "false");
  });

  header.append(top, strip, drawer);
  return header;
}

function buildFxAgentCard(fxData, currency) {
  const fx = fxData && typeof fxData === "object" ? fxData : {};
  const exposureMinor = pickMinor(fx, [
    "total_exposure_minor",
    "fx_exposure_minor",
    "exposure_minor",
    "foreign_exposure_minor",
  ]);
  const shockMinor = pickMinor(
    fx,
    ["adverse_shock_impact_minor", "adverse_shock_5pct_minor", "shock_5pct_minor", "fx_shock_minor"],
    Math.round(exposureMinor * 0.05),
  );
  const exposures = pickArr(fx, ["exposures"]);
  const detectedCurrencies = pickArr(fx, ["detected_currencies", "foreign_currencies", "currencies"]);
  const currencies =
    detectedCurrencies.length > 0
      ? detectedCurrencies
      : Array.from(
          new Set(
            exposures
              .map((item) => (typeof item?.detected_currency === "string" ? item.detected_currency.trim() : ""))
              .filter(Boolean),
          ),
        );
  const rawOptions = pickArr(fx, ["hedges", "hedge_options", "options", "products", "recommendations"]);

  const hedgeOptions =
    rawOptions.length > 0
      ? rawOptions
      : [
          {
            product_name: "Commerzbank FX Forward (Devisentermingeschäft)",
            coverage_pct: 80,
            estimated_cost_minor: Math.round(exposureMinor * 0.004),
            protected_amount_minor: Math.round(exposureMinor * 0.8),
            note: "Locks exchange rate for cross-border supplier invoices.",
          },
          {
            product_name: "Commerzbank FX Option",
            coverage_pct: 100,
            estimated_cost_minor: Math.round(exposureMinor * 0.012),
            protected_amount_minor: exposureMinor,
            note: "Caps downside FX loss while keeping favorable rate upside.",
          },
        ];

  const card = el("article", "cfo-agent-card");

  const head = el("div", "cfo-card-head");
  const badges = el("div", "cfo-card-badges");
  badges.append(el("span", "cfo-card-eyebrow", "FX Hedging Agent"), makeAutonomyBadge(2));
  const title = el("h3", "cfo-card-title", "Cross-Border FX Protection");
  const summary = el(
    "p",
    "cfo-card-summary",
    pickStr(
      fx,
      ["summary", "explanation", "headline"],
      exposureMinor > 0
        ? "Cross-border payments carry exchange-rate sensitivity across this 14-day window."
        : "No material foreign-currency supplier exposure detected in this 14-day window.",
    ),
  );
  head.append(badges, title, summary);

  // Metrics
  const metrics = el("div", "cfo-metric-pair");
  const expTile = el("div", "cfo-metric-tile");
  expTile.append(
    el("span", "cfo-metric-label", "Detected FX exposure"),
    el("strong", "cfo-metric-value", printMoney(exposureMinor, currency)),
    el("span", "cfo-metric-sub", currencies.length > 0 ? currencies.join(", ") : "Home currency only"),
  );

  const shockTile = el("div", `cfo-metric-tile${shockMinor > 0 ? " is-warn" : ""}`);
  shockTile.append(
    el("span", "cfo-metric-label", "5% adverse FX shock"),
    el(
      "strong",
      `cfo-metric-value${shockMinor > 0 ? " is-warn" : ""}`,
      printMoney(shockMinor, currency),
    ),
    el("span", "cfo-metric-sub", "Downside cash impact"),
  );
  metrics.append(expTile, shockTile);

  // Hedge options list
  const optionsStack = el("div", "cfo-options-stack");
  let selectedIndex = 0;
  let previewActive = false;

  const optionTiles = [];
  const simPanel = el("div", "cfo-sim-panel");
  simPanel.hidden = true;

  function renderSimPanel() {
    const opt = hedgeOptions[selectedIndex] || hedgeOptions[0];
    const optName = pickStr(opt, ["product_name", "name", "title", "instrument"], "Commerzbank FX Forward");
    const protectedMinor = pickMinor(
      opt,
      ["protected_amount_minor", "hedged_amount_minor", "covered_exposure_minor"],
      exposureMinor,
    );
    const costMinor = pickMinor(
      opt,
      ["estimated_cost_minor", "hedge_cost_minor", "fee_minor", "premium_minor"],
      0,
    );
    const shockMitigatedMinor = pickMinor(
      opt,
      ["shock_mitigated_minor", "protected_shock_minor"],
      Math.round(protectedMinor * 0.05),
    );
    const residualShockMinor = Math.max(0, shockMinor - shockMitigatedMinor);

    simPanel.replaceChildren();
    simPanel.append(makeAutonomyBadge(4, true));

    const r1 = el("div", "cfo-sim-row");
    r1.append(el("span", "", "Selected instrument"), el("strong", "", optName));

    const r2 = el("div", "cfo-sim-row");
    r2.append(
      el("span", "", "Simulated protected amount"),
      el("strong", "is-accent", printMoney(protectedMinor, currency)),
    );

    const r3 = el("div", "cfo-sim-row");
    r3.append(
      el("span", "", "Estimated hedge cost"),
      el("strong", "", printMoney(costMinor, currency)),
    );

    const r4 = el("div", "cfo-sim-row");
    r4.append(
      el("span", "", "Residual 5% FX shock"),
      el("strong", "", printMoney(residualShockMinor, currency)),
    );

    const note = el(
      "p",
      "cfo-sim-disclaimer",
      "Preview only — no Commerzbank FX Forward or FX Option order is booked or transmitted.",
    );

    simPanel.append(r1, r2, r3, r4, note);
  }

  hedgeOptions.slice(0, 2).forEach((opt, idx) => {
    const tile = el("div", `cfo-option-tile${idx === 0 ? " is-selected" : ""}`);
    tile.style.cursor = "pointer";

    const optName = pickStr(opt, ["product_name", "name", "title", "instrument"], "Commerzbank FX Hedge");
    const covPct = pickMinor(opt, ["coverage_pct", "hedge_ratio_pct"], idx === 0 ? 80 : 100);
    const costMinor = pickMinor(opt, ["estimated_cost_minor", "hedge_cost_minor", "fee_minor", "premium_minor"], 0);
    const protectedMinor = pickMinor(
      opt,
      ["protected_amount_minor", "hedged_amount_minor", "covered_exposure_minor"],
      Math.round((exposureMinor * covPct) / 100),
    );

    const top = el("div", "cfo-option-top");
    top.append(
      el("span", "cfo-option-name", optName),
      el("span", "cfo-option-rate", `${covPct}% cover`),
    );

    const meta = el("div", "cfo-option-meta");
    meta.append(
      el("span", "", `Protects ${printMoney(protectedMinor, currency)}`),
      el("span", "", `Est. cost ${printMoney(costMinor, currency)}`),
    );

    tile.append(top, meta);
    const noteText = pickStr(opt, ["detail", "note", "description", "rationale"], "");
    if (noteText) {
      tile.append(el("p", "cfo-option-note", noteText));
    }

    tile.addEventListener("click", () => {
      selectedIndex = idx;
      optionTiles.forEach((t, i) => t.classList.toggle("is-selected", i === selectedIndex));
      if (previewActive) {
        renderSimPanel();
      }
    });

    optionTiles.push(tile);
    optionsStack.append(tile);
  });

  const footer = el("div", "cfo-card-footer");
  const toggleBtn = el("button", "cfo-sim-toggle-btn", "Preview FX Hedge");
  toggleBtn.type = "button";
  toggleBtn.setAttribute("aria-pressed", "false");

  toggleBtn.addEventListener("click", () => {
    previewActive = !previewActive;
    toggleBtn.setAttribute("aria-pressed", previewActive ? "true" : "false");
    toggleBtn.textContent = previewActive ? "Hide FX Hedge Preview" : "Preview FX Hedge";
    if (previewActive) {
      renderSimPanel();
      simPanel.hidden = false;
    } else {
      simPanel.hidden = true;
    }
  });

  footer.append(toggleBtn, simPanel);
  card.append(head, metrics, optionsStack, footer);
  return card;
}

function buildTaxAgentCard(taxData, currency) {
  const tax = taxData && typeof taxData === "object" ? taxData : {};
  const reserveMinor = pickMinor(tax, [
    "recommended_quarterly_reserve_minor",
    "estimated_quarterly_reserve_minor",
    "quarterly_tax_reserve_minor",
    "tax_reserve_minor",
    "estimated_reserve_minor",
  ]);
  const deductibleMinor = pickMinor(tax, [
    "total_deductible_minor",
    "deductible_expenses_minor",
    "tax_deductible_expenses_minor",
    "deductible_total_minor",
  ]);

  const explicitWarning = Boolean(
    tax.reserve_at_risk ||
      tax.reserve_shortfall_warning ||
      tax.cash_below_reserve ||
      pickMinor(tax, ["reserve_shortfall_minor", "reserve_gap_minor", "shortfall_vs_reserve_minor"], 0) > 0,
  );
  const statusText = pickStr(
    tax,
    ["coverage_status", "status_label"],
    explicitWarning ? "Cash dips below tax reserve" : "Tax reserve covered",
  );
  const dipWarning = pickStr(tax, ["cash_dip_warning"], "");

  const rawCategories = pickArr(tax, ["deductible_categories", "deductible_items", "categories"]);
  const rawChecklist = pickArr(tax, ["checklist", "action_items", "tax_prep_checklist", "steps"]);

  const checklistItems =
    rawChecklist.length > 0
      ? rawChecklist
      : [
          "Ring-fence estimated quarterly advance tax reserve in a dedicated sub-account.",
          "Archive supplier invoices and payroll receipts for deductible operating expenses.",
          "Confirm VAT and advance tax filing dates with your tax advisor (Steuerberater).",
        ];

  const card = el("article", "cfo-agent-card");

  const head = el("div", "cfo-card-head");
  const badges = el("div", "cfo-card-badges");
  badges.append(el("span", "cfo-card-eyebrow", "Tax Agent"), makeAutonomyBadge(2));
  const title = el("h3", "cfo-card-title", "Quarterly Tax & Deductions");
  const summary = el(
    "p",
    "cfo-card-summary",
    pickStr(
      tax,
      ["summary", "explanation", "headline"],
      "Tracks scheduled tax obligations, VAT advance reserves, and deductible operating expenses.",
    ),
  );
  head.append(badges, title, summary);

  // Metrics
  const metrics = el("div", "cfo-metric-pair");
  const resTile = el("div", `cfo-metric-tile${explicitWarning ? " is-danger" : ""}`);
  resTile.append(
    el("span", "cfo-metric-label", "Quarterly tax reserve"),
    el(
      "strong",
      `cfo-metric-value${explicitWarning ? " is-danger" : ""}`,
      printMoney(reserveMinor, currency),
    ),
    el("span", "cfo-metric-sub", "Estimated advance reserve"),
  );

  const dedTile = el("div", "cfo-metric-tile");
  dedTile.append(
    el("span", "cfo-metric-label", "Deductible opex"),
    el("strong", "cfo-metric-value", printMoney(deductibleMinor, currency)),
    el("span", "cfo-metric-sub", "Rent, payroll, utilities, B2B"),
  );
  metrics.append(resTile, dedTile);

  // Cash vs Tax Reserve status pill
  const statusRow = el("div", "cfo-status-row");
  statusRow.append(
    el("span", "cfo-status-text", dipWarning || "Cash vs. tax reserve"),
    el("span", `pill ${explicitWarning ? "pill-danger" : "pill-success"}`, statusText),
  );

  // Deductible category chips (if provided)
  let chipRow = null;
  if (rawCategories.length > 0) {
    chipRow = el("div", "cfo-chip-row");
    for (const cat of rawCategories.slice(0, 5)) {
      const label =
        typeof cat === "string"
          ? cat
          : `${pickStr(cat, ["display_name", "category", "name", "label"], "Expense")}: ${printMoney(
              pickMinor(cat, ["total_minor", "amount_minor"], 0),
              currency,
            )}`;
      chipRow.append(el("span", "cfo-chip", label));
    }
  }

  // Actionable tax-prep checklist
  const checklistWrap = el("div", "cfo-options-stack");
  const checklistHead = el("div", "cfo-card-badges");
  checklistHead.append(el("span", "cfo-card-eyebrow", "Tax-prep checklist"), makeAutonomyBadge(3));
  const ul = el("ul", "cfo-checklist");

  checklistItems.slice(0, 4).forEach((item, idx) => {
    const text = typeof item === "string" ? item : pickStr(item, ["label", "text", "title", "step"], "");
    if (!text) return;
    const li = el("li", "cfo-checklist-item");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = `cfo-tax-check-${idx}`;
    const span = el("span", "", text);
    cb.addEventListener("change", () => {
      li.classList.toggle("is-checked", cb.checked);
    });
    li.append(cb, span);
    ul.append(li);
  });

  checklistWrap.append(checklistHead, ul);

  card.append(head, metrics, statusRow);
  if (chipRow) card.append(chipRow);
  card.append(checklistWrap);
  return card;
}

function buildInvestmentAgentCard(invData, currency) {
  const inv = invData && typeof invData === "object" ? invData : {};
  const surplusMinor = pickMinor(inv, [
    "investable_surplus_minor",
    "safe_surplus_minor",
    "surplus_minor",
  ]);
  const safetyCushionMinor = pickMinor(inv, [
    "safety_cushion_minor",
    "stress_buffer_minor",
    "recommended_limit_minor",
    "required_buffer_minor",
  ]);
  const thresholdMinor = pickMinor(
    inv,
    ["surplus_threshold_needed_minor", "surplus_threshold_minor", "threshold_needed_minor"],
    safetyCushionMinor,
  );
  const isSurplusMode =
    typeof inv.liquidity_first_mode === "boolean" ? !inv.liquidity_first_mode && surplusMinor > 0 : surplusMinor > 0;

  const rawOptions = pickArr(inv, ["options", "investment_options", "products", "recommendations"]);
  const defaultSurplusOptions = [
    {
      product_name: "Commerzbank Fixed-Term Deposit (Festgeld)",
      annual_rate_pct: 3.1,
      yield_30d_minor: Math.round((surplusMinor * 31 * 30) / (1000 * 365)),
      yield_90d_minor: Math.round((surplusMinor * 31 * 90) / (1000 * 365)),
      note: "Fixed return on cash safely above your 14-day stress buffer.",
    },
    {
      product_name: "Commerzbank Money Market Fund",
      annual_rate_pct: 3.4,
      yield_30d_minor: Math.round((surplusMinor * 34 * 30) / (1000 * 365)),
      yield_90d_minor: Math.round((surplusMinor * 34 * 90) / (1000 * 365)),
      note: "Daily-liquid treasury yield for flexible working capital.",
    },
  ];
  const defaultShortfallOptions = [
    {
      product_name: "Commerzbank Capex Equipment Leasing",
      annual_rate_pct: null,
      preserved_cash_minor: Math.max(thresholdMinor, 500000),
      note: "Preserves operating cash by spreading equipment upgrades into monthly installments.",
    },
  ];

  const options =
    rawOptions.length > 0
      ? rawOptions
      : isSurplusMode
        ? defaultSurplusOptions
        : defaultShortfallOptions;

  const card = el("article", "cfo-agent-card");

  const head = el("div", "cfo-card-head");
  const badges = el("div", "cfo-card-badges");
  badges.append(el("span", "cfo-card-eyebrow", "Investment & Capex Agent"), makeAutonomyBadge(2));
  const title = el(
    "h3",
    "cfo-card-title",
    isSurplusMode ? "Treasury Yield & Surplus" : "Liquidity-First & Capex Preservation",
  );
  const summary = el(
    "p",
    "cfo-card-summary",
    pickStr(
      inv,
      ["summary", "explanation", "headline"],
      isSurplusMode
        ? "Excess cash above your stress-tested safety buffer can earn short-term treasury yield."
        : "Protect operating liquidity first. Use Capex Equipment Leasing instead of draining cash reserves.",
    ),
  );
  head.append(badges, title, summary);

  // Metrics
  const metrics = el("div", "cfo-metric-pair");
  const surpTile = el("div", `cfo-metric-tile${isSurplusMode ? " is-positive" : " is-warn"}`);
  surpTile.append(
    el("span", "cfo-metric-label", "Safe investable surplus"),
    el(
      "strong",
      `cfo-metric-value${isSurplusMode ? " is-positive" : " is-warn"}`,
      printMoney(surplusMinor, currency),
    ),
    el("span", "cfo-metric-sub", isSurplusMode ? "Above stress buffer" : "Hold cash for now"),
  );

  const bufTile = el("div", "cfo-metric-tile");
  bufTile.append(
    el("span", "cfo-metric-label", isSurplusMode ? "Protected safety buffer" : "Surplus threshold"),
    el("strong", "cfo-metric-value", printMoney(isSurplusMode ? safetyCushionMinor : thresholdMinor, currency)),
    el("span", "cfo-metric-sub", isSurplusMode ? "Kept liquid" : "Needed before investing"),
  );
  metrics.append(surpTile, bufTile);

  // Option cards
  const optionsStack = el("div", "cfo-options-stack");
  let selectedIndex = 0;
  let simActive = false;
  const optionTiles = [];
  const simPanel = el("div", "cfo-sim-panel");
  simPanel.hidden = true;

  function renderSimPanel() {
    const opt = options[selectedIndex] || options[0];
    const optName = pickStr(opt, ["product_name", "name", "title"], "Commerzbank Treasury Option");
    const y30 = pickMinor(opt, ["projected_yield_30d_minor", "yield_30d_minor"], 0);
    const y90 = pickMinor(opt, ["projected_yield_90d_minor", "yield_90d_minor"], 0);
    const rawPreserved = pickMinor(
      opt,
      ["preserved_cash_minor", "working_capital_preserved_minor"],
      0,
    );
    const preserved = rawPreserved > 0 ? rawPreserved : Math.max(thresholdMinor, 500000);

    simPanel.replaceChildren();
    simPanel.append(makeAutonomyBadge(4, true));

    const r1 = el("div", "cfo-sim-row");
    r1.append(el("span", "", "Simulated product"), el("strong", "", optName));

    if (isSurplusMode) {
      const r2 = el("div", "cfo-sim-row");
      r2.append(
        el("span", "", "Allocated surplus"),
        el("strong", "", printMoney(surplusMinor, currency)),
      );
      const r3 = el("div", "cfo-sim-row");
      r3.append(
        el("span", "", "Projected 30d / 90d yield"),
        el("strong", "is-accent", `${printMoney(y30, currency)} / ${printMoney(y90, currency)}`),
      );
      const r4 = el("div", "cfo-sim-row");
      r4.append(
        el("span", "", "Remaining liquid buffer"),
        el("strong", "", printMoney(safetyCushionMinor, currency)),
      );
      simPanel.append(r1, r2, r3, r4);
    } else {
      const r2 = el("div", "cfo-sim-row");
      r2.append(
        el("span", "", "Working capital preserved"),
        el("strong", "is-accent", printMoney(preserved, currency)),
      );
      const r3 = el("div", "cfo-sim-row");
      r3.append(
        el("span", "", "Cash investment allocated"),
        el("strong", "", printMoney(0, currency)),
      );
      simPanel.append(r1, r2, r3);
    }

    simPanel.append(
      el(
        "p",
        "cfo-sim-disclaimer",
        "Preview only — no deposit, fund order, or leasing contract is initiated.",
      ),
    );
  }

  options.slice(0, 2).forEach((opt, idx) => {
    const tile = el("div", `cfo-option-tile${idx === 0 ? " is-selected" : ""}`);
    tile.style.cursor = "pointer";

    const optName = pickStr(opt, ["product_name", "name", "title"], "Commerzbank Treasury Option");
    const rateBps = opt.annual_rate_bps;
    const rateVal = opt.annual_rate_pct ?? opt.rate_pct ?? opt.apy_pct;
    const rateLabel =
      rateBps !== undefined && rateBps !== null && Number(rateBps) > 0
        ? `${(Number(rateBps) / 100).toFixed(1)}% p.a.`
        : rateVal !== undefined && rateVal !== null && !Number.isNaN(Number(rateVal)) && Number(rateVal) > 0
          ? `${Number(rateVal).toFixed(1)}% p.a.`
          : "Cash-preserving";

    const top = el("div", "cfo-option-top");
    top.append(el("span", "cfo-option-name", optName), el("span", "cfo-option-rate", rateLabel));

    const meta = el("div", "cfo-option-meta");
    if (isSurplusMode) {
      const y30 = pickMinor(opt, ["projected_yield_30d_minor", "yield_30d_minor"], 0);
      const y90 = pickMinor(opt, ["projected_yield_90d_minor", "yield_90d_minor"], 0);
      meta.append(
        el("span", "", `30d: +${printMoney(y30, currency)}`),
        el("span", "", `90d: +${printMoney(y90, currency)}`),
      );
    } else {
      const rawPreserved = pickMinor(
        opt,
        ["preserved_cash_minor", "working_capital_preserved_minor"],
        0,
      );
      const preserved = rawPreserved > 0 ? rawPreserved : Math.max(thresholdMinor, 500000);
      meta.append(el("span", "", `Preserves ~${printMoney(preserved, currency)} working capital`));
    }

    tile.append(top, meta);
    const noteText = pickStr(opt, ["detail", "note", "description", "rationale"], "");
    if (noteText) {
      tile.append(el("p", "cfo-option-note", noteText));
    }

    tile.addEventListener("click", () => {
      selectedIndex = idx;
      optionTiles.forEach((t, i) => t.classList.toggle("is-selected", i === selectedIndex));
      if (simActive) {
        renderSimPanel();
      }
    });

    optionTiles.push(tile);
    optionsStack.append(tile);
  });

  const footer = el("div", "cfo-card-footer");
  const toggleBtn = el(
    "button",
    "cfo-sim-toggle-btn",
    isSurplusMode ? "Simulate Allocation" : "Simulate Capex Leasing",
  );
  toggleBtn.type = "button";
  toggleBtn.setAttribute("aria-pressed", "false");

  toggleBtn.addEventListener("click", () => {
    simActive = !simActive;
    toggleBtn.setAttribute("aria-pressed", simActive ? "true" : "false");
    toggleBtn.textContent = simActive
      ? "Hide Allocation Preview"
      : isSurplusMode
        ? "Simulate Allocation"
        : "Simulate Capex Leasing";
    if (simActive) {
      renderSimPanel();
      simPanel.hidden = false;
    } else {
      simPanel.hidden = true;
    }
  });

  footer.append(toggleBtn, simPanel);
  card.append(head, metrics, optionsStack, footer);
  return card;
}

/**
 * Render the Autonomous Multi-Agent CFO Suite into `container`.
 * @param {HTMLElement} container
 * @param {object} data - Response from POST /api/multi-agent
 * @param {object|null} mcpManifest - Response from GET /api/mcp/tools (optional)
 * @param {string} [currency="EUR"]
 */
export function renderCfoSuite(container, data, mcpManifest = null, currency = "EUR") {
  if (!container) return;

  const safeData = data && typeof data === "object" ? data : {};
  const resolvedCurrency = currency || safeData.currency || "EUR";

  const suite = el("section", "cfo-suite");
  suite.setAttribute("aria-label", "Autonomous Multi-Agent CFO Suite");

  const headerStrip = buildHeaderStrip(safeData, mcpManifest, resolvedCurrency);

  const grid = el("div", "cfo-agent-grid");
  grid.append(
    buildFxAgentCard(safeData.fx_hedging, resolvedCurrency),
    buildTaxAgentCard(safeData.tax_agent, resolvedCurrency),
    buildInvestmentAgentCard(safeData.investment_agent, resolvedCurrency),
  );

  suite.append(headerStrip, grid);
  container.replaceChildren(suite);
  replayFade(suite);
}

/**
 * Fetch POST /api/multi-agent and GET /api/mcp/tools and render into `container`.
 * Gracefully handles unmounted MCP endpoints, loading skeletons, and errors.
 * @param {HTMLElement} container
 * @param {object} state - App state containing `forecast` (and optional `currency`)
 */
export async function fetchAndRenderCfoSuite(container, state) {
  if (!container) return null;

  const forecast = state?.forecast ?? state;
  const payload = buildInsightPayload(forecast);
  if (!payload) {
    renderErrorState(
      container,
      "Load a 14-day cash forecast to activate the FX, Tax, and Investment agents.",
      null,
    );
    return null;
  }

  const nextSeq = (containerRequestSeq.get(container) || 0) + 1;
  containerRequestSeq.set(container, nextSeq);

  renderLoadingSkeleton(container);

  const multiAgentPromise = request("/api/multi-agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => res.json());

  const mcpPromise = request("/api/mcp/tools", { method: "GET" })
    .then((res) => res.json())
    .catch(() => null);

  try {
    const [multiAgentData, mcpManifest] = await Promise.all([multiAgentPromise, mcpPromise]);
    if (containerRequestSeq.get(container) !== nextSeq) {
      return null;
    }
    const currency = state?.currency || payload.currency || "EUR";
    renderCfoSuite(container, multiAgentData, mcpManifest, currency);
    return { data: multiAgentData, mcpManifest };
  } catch (err) {
    if (containerRequestSeq.get(container) !== nextSeq) {
      return null;
    }
    const message =
      err?.status === 404
        ? "Multi-agent endpoint (/api/multi-agent) is not mounted yet."
        : err?.message || "Could not reach the Multi-Agent CFO Suite.";
    renderErrorState(container, message, () => {
      fetchAndRenderCfoSuite(container, state);
    });
    return null;
  }
}
