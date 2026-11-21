import { toMinor } from "./format.js?v=tc11";
import { addDaysIso } from "./predictions.js?v=tc20";

function readRows(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch !== '"') {
        field += ch;
      } else if (text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else {
        inQuotes = false;
      }
    } else if (ch === '"' && !field) {
      inQuotes = true;
    } else if (ch === ";") {
      row.push(field.trim());
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      row.push(field.trim());
      rows.push(row);
      row = [];
      field = "";
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
    } else {
      field += ch;
    }
  }
  row.push(field.trim());
  rows.push(row);
  return rows.filter((cells) => cells.some(Boolean));
}

function parseBankDateIso(raw) {
  const s = String(raw || "").trim();
  const dot = /^(\d{2})\.(\d{2})\.(\d{2}|\d{4})$/.exec(s);
  const iso = dot ? [dot[3].padStart(4, "20"), dot[2], dot[1]].join("-") : s;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
  const dt = new Date(iso + "T00:00:00Z");
  return !Number.isNaN(dt.getTime()) && dt.toISOString().slice(0, 10) === iso ? iso : null;
}

function parseBankMinor(raw) {
  const normalized = String(raw || "")
    .trim()
    .replace(/[\s\u00a0]/g, "")
    .replace(/\.(?=\d{3}(?:,|$))/g, "")
    .replace(/^\+/, "");
  try {
    return BigInt(toMinor(normalized));
  } catch {
    return null;
  }
}

function openingForRowOrder(rows) {
  let opening = null;
  let movement = 0n;
  for (const row of rows) {
    movement += row.amountMinor;
    if (row.balanceMinor === null) continue;
    const candidate = row.balanceMinor - movement;
    if (opening !== null && opening !== candidate) return null;
    opening = candidate;
  }
  return opening;
}

function reconstructOpening(rows) {
  // The balance is in the account currency. Don't subtract raw amounts in a different currency.
  if (new Set(rows.map((row) => row.currency)).size !== 1 || !rows[0].currency) return null;
  const byDate = (left, right) => left.iso.localeCompare(right.iso);
  const ordered = [...rows].sort(byDate);
  const anchorRow = ordered.find((row) => row.balanceMinor !== null);
  if (!anchorRow) return null;
  const anchorDate = anchorRow.iso;
  const throughAnchor = ordered.filter((row) => row.iso <= anchorDate);
  if (throughAnchor.some((row) => row.amountMinor === null)) return null;

  // A row balance is after that payment. Try both within-day orders used by bank exports.
  const reversedTies = [...throughAnchor].reverse().sort(byDate);
  const candidates = new Set([openingForRowOrder(throughAnchor), openingForRowOrder(reversedTies)]);
  candidates.delete(null);
  return candidates.size === 1 ? Number([...candidates][0]) : null;
}

export function extractCsvDefaults(csvText, horizonDays) {
  const [header = [], ...records] = readRows(String(csvText || "").replace(/^\uFEFF/, ""));
  const headers = header.map((name) => name.toLowerCase());
  const valDateIdx = headers.indexOf("value date");
  const bookDateIdx = headers.indexOf("booking date");
  const amountIdx = headers.indexOf("amount");
  const currencyIdx = headers.indexOf("currency");
  const balanceIdx = headers.findIndex((name) => ["balance", "saldo", "closing balance", "running balance"].includes(name));

  const rows = [];
  let latestDateIso = "";
  for (const cols of records) {
    const iso = parseBankDateIso(cols[valDateIdx] || cols[bookDateIdx]);
    if (!iso) continue;
    if (iso > latestDateIso) latestDateIso = iso;
    rows.push({
      iso,
      amountMinor: parseBankMinor(cols[amountIdx]),
      balanceMinor: parseBankMinor(cols[balanceIdx]),
      currency: cols[currencyIdx]?.toUpperCase(),
    });
  }

  const startDate = latestDateIso
    ? addDaysIso(latestDateIso, -(horizonDays - 1))
    : new Date().toISOString().slice(0, 10);
  const windowRows = rows.filter((row) => row.iso >= startDate);

  const priorBalances = rows.filter((row) => row.iso < startDate && row.balanceMinor !== null);
  if (priorBalances.length > 0) {
    priorBalances.sort((left, right) => left.iso.localeCompare(right.iso));
    return {
      startDate,
      openingBalanceMinor: Number(priorBalances.at(-1).balanceMinor),
      balanceSourceLabel: "From CSV balance",
    };
  }
  if (windowRows.some((row) => row.balanceMinor !== null)) {
    return {
      startDate,
      openingBalanceMinor: reconstructOpening(windowRows),
      balanceSourceLabel: "From CSV balance",
    };
  }

  // CSVs without a balance use the existing cushion estimate.
  const inflowsMinor = windowRows.reduce(
    (sum, row) => sum + (row.amountMinor > 0n ? row.amountMinor : 0n),
    0n,
  );
  const rounded = ((inflowsMinor / 2n + 25_000n) / 50_000n) * 50_000n;
  return {
    startDate,
    openingBalanceMinor: Number(rounded < 100_000n ? 100_000n : rounded),
    balanceSourceLabel: "Auto-estimated balance",
  };
}
