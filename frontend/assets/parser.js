const REQUIRED_REDHAT_HEADERS = [
  "Account Number",
  "Booking Date",
  "Value Date",
  "Transaction Type",
  "Payment Reference",
  "Beneficiary/Payer",
  "Amount",
  "Currency",
];

function parseCsvLine(line, delimiter = ";") {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === delimiter && !inQuotes) {
      values.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  values.push(current.trim());
  return values;
}

function parseBankDate(raw) {
  const trimmed = raw.trim();
  // DD.MM.YY or DD.MM.YYYY
  const dotMatch = /^(\d{2})\.(\d{2})\.(\d{2}|\d{4})$/.exec(trimmed);
  if (dotMatch) {
    const [, dd, mm, yy] = dotMatch;
    const yyyy = yy.length === 2 ? `20${yy}` : yy;
    return `${yyyy}-${mm}-${dd}`;
  }
  // ISO YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return trimmed;
  }
  throw new Error(`Unsupported booking date format: "${raw}". Expected DD.MM.YY.`);
}

function parseGermanAmountMinor(raw) {
  const normalized = raw.trim().replace(/\s+/g, "").replace(/\.(?=\d{3}(?:,|$))/g, "");
  const match = /^(-?)(\d+)(?:,(\d{1,2})|\.(\d{1,2}))?$/.exec(normalized);
  if (!match) {
    throw new Error(`Invalid amount format: "${raw}". Expected German decimal comma (e.g. -3800,00).`);
  }
  const [, sign, whole, commaFrac, dotFrac] = match;
  const frac = (commaFrac ?? dotFrac ?? "").padEnd(2, "0");
  const minor = Number(BigInt(whole) * 100n + BigInt(frac));
  return sign === "-" ? -minor : minor;
}

function extractFxRate(reference, currency) {
  if (!currency || currency.toUpperCase() === "EUR") return 1;
  const match = /@\s*(\d+(?:[.,]\d+)?)\s*EUR\/CHF/i.exec(reference || "");
  if (match) {
    const rate = Number(match[1].replace(",", "."));
    if (Number.isFinite(rate) && rate > 0) return rate;
  }
  // Default EUR/CHF rate used across the Red Hat Pizzeria Amalfi dataset
  return currency.toUpperCase() === "CHF" ? 1.047 : 1;
}

/**
 * Parse a Red Hat / German online banking semicolon-delimited CSV file.
 */
export function parseRedHatBankCsv(csvText) {
  const cleanText = csvText.replace(/^\uFEFF/, "").trim();
  const lines = cleanText.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) {
    throw new Error("CSV file must contain a header row and at least one transaction.");
  }

  const headers = parseCsvLine(lines[0], ";");
  const colIndex = new Map(headers.map((h, idx) => [h, idx]));
  const missing = REQUIRED_REDHAT_HEADERS.filter((h) => !colIndex.has(h));
  if (missing.length > 0) {
    throw new Error(
      `CSV does not match Red Hat bank statement format (semicolon-delimited). Missing columns: ${missing.join(", ")}.`,
    );
  }

  const get = (row, name) => {
    const idx = colIndex.get(name);
    return idx !== undefined && idx < row.length ? row[idx] : "";
  };

  let accountNumber = "";
  const transactions = [];

  for (let i = 1; i < lines.length; i += 1) {
    const row = parseCsvLine(lines[i], ";");
    if (row.length < 8) continue;

    const acct = get(row, "Account Number");
    if (acct && !accountNumber) accountNumber = acct;

    const bookingDate = parseBankDate(get(row, "Booking Date"));
    const valueDate = get(row, "Value Date") ? parseBankDate(get(row, "Value Date")) : bookingDate;
    const txType = get(row, "Transaction Type") || "TRANSFER";
    const reference = get(row, "Payment Reference");
    const counterparty = get(row, "Beneficiary/Payer") || txType;
    const currency = (get(row, "Currency") || "EUR").toUpperCase();
    const originalMinor = parseGermanAmountMinor(get(row, "Amount"));
    const fxRate = extractFxRate(reference, currency);
    const amountMinorEur = currency === "EUR" ? originalMinor : Math.round(originalMinor * fxRate);

    transactions.push({
      id: `TX-${String(i).padStart(4, "0")}`,
      date: valueDate || bookingDate,
      booking_date: bookingDate,
      amount_minor: amountMinorEur,
      original_amount_minor: originalMinor,
      original_currency: currency,
      fx_rate: fxRate,
      transaction_type: txType,
      label: counterparty,
      reference,
      counterparty_account: get(row, "Counterparty Account"),
      bank_code: get(row, "Bank Code"),
      info: get(row, "Info"),
    });
  }

  if (transactions.length === 0) {
    throw new Error("No valid transactions found in the CSV.");
  }

  // Sort chronologically ascending
  transactions.sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));

  return {
    accountNumber,
    currency: "EUR",
    transactions,
  };
}

function addDaysIso(isoDate, offset) {
  const dt = new Date(`${isoDate}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + offset);
  return dt.toISOString().slice(0, 10);
}

function daysBetweenIso(startIso, endIso) {
  const a = new Date(`${startIso}T00:00:00Z`).getTime();
  const b = new Date(`${endIso}T00:00:00Z`).getTime();
  return Math.max(1, Math.round((b - a) / 86_400_000) + 1);
}

function projectSeries(transactions, startingBalanceMinor, startDate, totalDays) {
  const endDate = addDaysIso(startDate, totalDays - 1);
  const deltaByDate = new Map();

  for (const tx of transactions) {
    if (tx.date >= startDate && tx.date <= endDate) {
      deltaByDate.set(tx.date, (deltaByDate.get(tx.date) || 0) + tx.amount_minor);
    }
  }

  const days = [];
  let running = Number(startingBalanceMinor);
  let firstDeficit = null;

  for (let i = 0; i < totalDays; i += 1) {
    const date = addDaysIso(startDate, i);
    running += deltaByDate.get(date) || 0;
    days.push({ date, balance_minor: running });
    if (firstDeficit === null && running < 0) {
      firstDeficit = { date, shortfall_minor: -running };
    }
  }

  return { days, first_deficit: firstDeficit };
}

/**
 * Compute a ForecastResponse-compatible object from parsed Red Hat bank statement rows.
 */
export function buildForecastFromRedHat({
  parsed,
  startingBalanceMinor,
  startDate,
  horizonDays = 14,
  moveTransactionId = null,
  moveToDate = null,
}) {
  const { transactions, accountNumber, currency } = parsed;
  let effectiveStart = startDate;
  let totalDays = horizonDays;

  if (horizonDays === "all") {
    effectiveStart = transactions[0].date;
    const lastDate = transactions[transactions.length - 1].date;
    totalDays = daysBetweenIso(effectiveStart, lastDate);
  }

  const baseline = projectSeries(transactions, startingBalanceMinor, effectiveStart, totalDays);

  let scenario = null;
  if (moveTransactionId && moveToDate) {
    const endDate = addDaysIso(effectiveStart, totalDays - 1);
    if (moveToDate < effectiveStart || moveToDate > endDate) {
      throw new Error(`New payment date must be within the projection window (${effectiveStart} to ${endDate}).`);
    }
    const target = transactions.find((tx) => tx.id === moveTransactionId);
    if (!target) {
      throw new Error(`Transaction ${moveTransactionId} was not found.`);
    }
    if (target.amount_minor <= 0) {
      throw new Error("Only incoming (positive) payments can be rescheduled.");
    }
    const adjustedTxs = transactions.map((tx) =>
      tx.id === moveTransactionId ? { ...tx, date: moveToDate } : tx,
    );
    scenario = projectSeries(adjustedTxs, startingBalanceMinor, effectiveStart, totalDays);
  }

  return {
    account_number: accountNumber,
    currency,
    transactions,
    baseline,
    scenario,
  };
}
