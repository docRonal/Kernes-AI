const moneyFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const calendarFormatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeZone: "UTC",
});

// EU currencies the API accepts. One forecast uses one currency; nothing is converted.
export const EU_CURRENCIES = ["EUR", "PLN", "CZK", "HUF", "RON", "SEK", "DKK"];

export function toMinor(value) {
  const match = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/.exec(String(value).trim());
  if (!match) {
    throw new Error("Enter an opening balance with up to two decimal places (e.g. 5000.00).");
  }
  const [, sign, whole, fraction = ""] = match;
  const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return (sign === "-" ? -minor : minor).toString();
}

export function printDate(isoDate) {
  return calendarFormatter.format(new Date(`${isoDate}T00:00:00Z`));
}

export function printMoney(minor, currency = "EUR") {
  return `${moneyFormatter.format(Number(minor) / 100)} ${currency}`;
}

export function replayFade(el) {
  if (!el) return;
  el.classList.remove("is-entering");
  void el.offsetWidth;
  el.classList.add("is-entering");
}
