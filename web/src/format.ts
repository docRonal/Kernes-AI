const MINUS = "−";

const twoDecimals = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const wholeNumber = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const compactNumber = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });

export function signOf(minor: number, signed = false): string {
  if (minor < 0) return MINUS;
  return signed && minor > 0 ? "+" : "";
}

/** "PLN 5,000.00", "−PLN 5,000.00" or, with `signed`, "+PLN 9,000.00". */
export function money(minor: number, signed = false): string {
  return `${signOf(minor, signed)}PLN ${twoDecimals.format(Math.abs(minor) / 100)}`;
}

/** Whole złoty without the currency, for tight chart labels: "−17,000". */
export function moneyShort(minor: number, signed = false): string {
  return `${signOf(minor, signed)}${wholeNumber.format(Math.abs(minor) / 100)}`;
}

export function axisLabel(minor: number): string {
  return minor === 0 ? "0" : `${signOf(minor)}${compactNumber.format(Math.abs(minor) / 100)}`;
}

export function moneyParts(minor: number): { sign: string; int: string; dec: string } {
  const [int, dec] = twoDecimals.format(Math.abs(minor) / 100).split(".");
  return { sign: signOf(minor), int, dec };
}

const parseDay = (iso: string) => new Date(`${iso}T00:00:00Z`);
const shortFormat = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const longFormat = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const rangeFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const weekdayFormat = new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: "UTC" });

/** "Fri 27 Nov" */
export const shortDate = (iso: string) => shortFormat.format(parseDay(iso));
/** "Friday 27 November" */
export const longDate = (iso: string) => longFormat.format(parseDay(iso));
/** "27 Nov 2026" */
export const fullDate = (iso: string) => rangeFormat.format(parseDay(iso));
export const weekday = (iso: string) => weekdayFormat.format(parseDay(iso));
export const dayOfMonth = (iso: string) => parseDay(iso).getUTCDate();

export function isWeekend(iso: string): boolean {
  const day = parseDay(iso).getUTCDay();
  return day === 0 || day === 6;
}

export function addDays(iso: string, days: number): string {
  const date = parseDay(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function listLabels(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

export function truncate(text: string, maxChars: number): string | null {
  if (maxChars < 4) return null;
  return text.length <= maxChars ? text : `${text.slice(0, maxChars - 1)}…`;
}

/**
 * Parses what people actually type into a money field ("12000", "12 000",
 * "12,000.50", "12.000,50", "PLN 12000") into a grosz string. BigInt keeps
 * large balances exact.
 */
export function toMinor(raw: string): string {
  let value = raw.trim().replace(/[\s  _']/g, "").replace(/^pln/i, "").replace(/(pln|zł)$/i, "");
  if (/^-?\d{1,3}(,\d{3})+(\.\d{1,2})?$/.test(value)) value = value.replaceAll(",", "");
  else if (/^-?\d{1,3}(\.\d{3})+(,\d{1,2})?$/.test(value)) value = value.replaceAll(".", "");
  const match = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/.exec(value);
  if (!match) throw new Error("Enter the opening balance as a number, for example 12,000 or 12000.50.");
  const [, minus, int, fraction = ""] = match;
  const minor = BigInt(int) * 100n + BigInt(fraction.padEnd(2, "0"));
  return (minus ? -minor : minor).toString();
}

/** Tidies a typed balance on blur; leaves it untouched if it doesn't parse. */
export function tidyBalance(raw: string): string {
  try {
    const minor = Number(toMinor(raw));
    return `${signOf(minor)}${twoDecimals.format(Math.abs(minor) / 100)}`;
  } catch {
    return raw;
  }
}
