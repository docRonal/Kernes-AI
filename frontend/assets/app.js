const forecastForm = document.querySelector("#forecast-form");
const scenarioForm = document.querySelector("#scenario-form");
const adviceButton = document.querySelector("#advice-button");
const advice = document.querySelector("#advice");
const results = document.querySelector("#results");
const status = document.querySelector("#status");
const money = new Intl.NumberFormat("en-PL", { style: "currency", currency: "PLN" });
const calendar = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeZone: "UTC" });

let lastForecast;
let baselineInputs;

function toMinor(value) {
  const match = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/.exec(value.trim());
  if (!match) throw new Error("Enter an opening balance with up to two decimal places.");
  const [, sign, whole, fraction = ""] = match;
  const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return (sign === "-" ? -minor : minor).toString();
}

function printDate(value) {
  return calendar.format(new Date(value));
}

function printMoney(minor) {
  return money.format(minor / 100);
}

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}).`);
  }
  return response;
}

async function run(message, action) {
  for (const button of document.querySelectorAll("button")) button.disabled = true;
  status.classList.remove("error");
  status.textContent = message;
  try {
    await action();
    status.textContent = "";
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    for (const button of document.querySelectorAll("button")) button.disabled = false;
  }
}

function renderForecast(data) {
  const baseline = data.baseline;
  const deficit = baseline.first_deficit;
  const shortfall = document.querySelector("#shortfall");
  shortfall.classList.toggle("negative", Boolean(deficit));
  shortfall.textContent = deficit
    ? `Projected shortfall of ${printMoney(deficit.shortfall_minor)} on ${printDate(deficit.date)}.`
    : "No projected shortfall within 14 days.";

  const scenario = data.scenario;
  const scenarioMessage = document.querySelector("#scenario-message");
  document.querySelector("#scenario-heading").hidden = !scenario;
  scenarioMessage.hidden = !scenario;
  if (scenario) {
    const adjustedDeficit = scenario.first_deficit;
    scenarioMessage.textContent = adjustedDeficit
      ? `Adjusted shortfall of ${printMoney(adjustedDeficit.shortfall_minor)} on ${printDate(adjustedDeficit.date)}.`
      : "The adjusted forecast stays above or at zero for 14 days.";
  }
  document.querySelector("#balances").replaceChildren(...baseline.days.map((day, i) => {
    const row = document.createElement("tr");
    row.insertCell().textContent = printDate(day.date);
    const baselineCell = row.insertCell();
    baselineCell.textContent = printMoney(day.balance_minor);
    baselineCell.classList.toggle("negative", day.balance_minor < 0);
    if (scenario) {
      const adjusted = scenario.days[i].balance_minor;
      const scenarioCell = row.insertCell();
      scenarioCell.textContent = printMoney(adjusted);
      scenarioCell.classList.toggle("negative", adjusted < 0);
    }
    return row;
  }));
  adviceButton.hidden = !deficit;
  results.hidden = false;
}

forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  run("Calculating the forecast…", async () => {
    const inputs = new FormData(forecastForm);
    inputs.set("starting_balance_minor", toMinor(inputs.get("opening_balance")));
    inputs.delete("opening_balance");

    if (!inputs.get("file").name) {
      const sample = await request("/demo/transactions.csv");
      inputs.set("file", await sample.blob(), "transactions.csv");
    }

    const response = await request("/api/forecast", { method: "POST", body: inputs });
    lastForecast = await response.json();
    baselineInputs = inputs;

    const payments = lastForecast.transactions
      .filter(({ amount_minor }) => amount_minor > 0)
      .map(({ id, label }) => new Option(`${label} (${id})`, id));
    scenarioForm.elements.move_transaction_id.replaceChildren(...payments);
    scenarioForm.hidden = payments.length === 0;
    advice.hidden = true;
    renderForecast(lastForecast);
  });
});

scenarioForm.addEventListener("submit", (event) => {
  event.preventDefault();
  run("Calculating both scenarios…", async () => {
    const inputs = new FormData(scenarioForm);
    for (const [key, value] of baselineInputs) inputs.set(key, value);
    const response = await request("/api/forecast", { method: "POST", body: inputs });
    renderForecast(await response.json());
  });
});

adviceButton.addEventListener("click", () => {
  run("Preparing an explanation and draft…", async () => {
    const response = await request("/api/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_deficit: lastForecast.baseline.first_deficit,
        transactions: lastForecast.transactions,
      }),
    });
    const data = await response.json();
    document.querySelector("#explanation").textContent = data.explanation;
    document.querySelector("#draft").value = data.email_draft;
    advice.hidden = false;
  });
});
