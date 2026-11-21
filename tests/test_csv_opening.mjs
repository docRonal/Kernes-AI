import assert from "node:assert/strict";
import test from "node:test";

import { extractCsvDefaults } from "../frontend/assets/js/csv.js";

function statement(rows, balanceHeader = "Balance") {
  const header = "Account Number;Booking Date;Value Date;Transaction Type;Payment Reference;Beneficiary/Payer;Amount;Currency";
  return [
    balanceHeader ? header + ";" + balanceHeader : header,
    ...rows.map(([date, amount, balance, currency = "EUR", reference = "Rent"]) => {
      const payment = ["DE00", date, date, "TRANSFER", reference, "Vendor", amount, currency];
      if (balanceHeader) payment.push(balance);
      return payment.join(";");
    }),
  ].join("\r\n");
}

test("undoes a payment already counted in the imported row balance", () => {
  const csv = statement([["31.12.25", "-1.200,00", "300,00"]]);
  assert.deepEqual(extractCsvDefaults(csv, 14), {
    startDate: "2025-12-18",
    openingBalanceMinor: 150_000,
    balanceSourceLabel: "From CSV balance",
  });
});

test("accounts for earlier movements and quoted multiline fields in a newest-first export", () => {
  const csv = statement([
    ["31.12.25", "-1200,00", "400,00"],
    ["30.12.25", "+100,00", "", "EUR", '"Payment;\r\nend of year"'],
  ], "Saldo");
  assert.equal(extractCsvDefaults(csv, 14).openingBalanceMinor, 150_000);
});

test("reconciles newest-first running balances from the same day", () => {
  const csv = statement([
    ["31.12.25", "-1200,00", "300,00"],
    ["31.12.25", "+100,00", "1500,00"],
  ], "Running Balance");
  assert.equal(extractCsvDefaults(csv, 14).openingBalanceMinor, 140_000);
});

test("requires an opening balance when the order or currency makes reversal ambiguous", () => {
  const rows = [
    ["31.12.25", "-1200,00", "300,00"],
    ["31.12.25", "+100,00", ""],
  ];
  assert.equal(extractCsvDefaults(statement(rows), 14).openingBalanceMinor, null);
  rows[1][3] = "CHF";
  assert.equal(extractCsvDefaults(statement(rows), 14).openingBalanceMinor, null);
});

test("keeps a known pre-window balance and still supports statements without a balance", () => {
  const csv = statement([
    ["31.12.25", "-1200,00", "300,00"],
    ["17.12.25", "+100,00", "1500,00"],
  ]);
  assert.equal(extractCsvDefaults(csv, 14).openingBalanceMinor, 150_000);

  const withoutBalance = statement([["31.12.25", "5000,00"]], null);
  assert.equal(extractCsvDefaults(withoutBalance, 14).balanceSourceLabel, "Auto-estimated balance");
  assert.equal(extractCsvDefaults(withoutBalance, 14).openingBalanceMinor, 250_000);
});
