# KERNES CFO — 5-Minute Live Interactive Demo Script

> **Format:** 100% live browser walkthrough on the deployed OpenShift AI app (`https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com`) — **no slide deck**.
> **Core Story:** **Luigi**, a former pizzaiolo who left his restaurant job to open *Pizzeria Amalfi* with a small starting capital, needs an Autonomous CFO that tells him in plain English how to survive a cash crunch and stay in control.
> **Cast:** 5 Speaking Blocks (~50–70s each = **5:00 total**) + **1 Dedicated Laptop Driver** (operates clicks/scrolling smoothly while speakers talk).

---

## Pre-Stage Checklist (2 Minutes Before Going Live)

- [ ] **Download the June scenario file:** open `https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com/demo/amalfi.csv` and keep `pizzeria-amalfi-sample-2025.csv` on the desktop for Block 1.
- [ ] **Warm up GPU model + prepare the Block 4 tab:** In a second tab, click **`Check my cash →`** with the default sample (*Pizzeria Amalfi · Full 2025 statement* → 1–14 January 2026, learned from history). This removes the `kernes-qwen-7b` (vLLM on NVIDIA L4 GPU) cold start and stays open for Block 4.
- [ ] **Open clean browser tab** at `https://autonomous-cfo-kernes-ai.apps.ocp.9hpps.sandbox580.opentlc.com` (`100%` zoom, bookmarks bar hidden).
- [ ] **Have backup local tab ready** (`http://127.0.0.1:8080`) in case conference Wi-Fi drops.
- [ ] **Reset to Setup Screen (`#setup-screen`)** before stepping on stage.

---

## Quick Speaker Merge Guide (If Using 3 or 4 Speakers Instead of 5)

| Team Setup | How to Split the 5 Blocks |
| --- | --- |
| **5 Speakers** | Speaker 1 → Block 1 · Speaker 2 → Block 2 · Speaker 3 → Block 3 · Speaker 4 → Block 4 · Speaker 5 → Block 5 |
| **4 Speakers** | Merge **Block 3 + Block 4** into one technical/power-user speaker (~1:50). |
| **3 Speakers** | Speaker A: **Block 1 + Block 2** (Luigi & Simple Mode, ~2:10) · Speaker B: **Block 3 + Block 4** (Advanced & Tech, ~1:50) · Speaker C: **Block 5** (Business Model & Close, ~1:00). |

---

## Block 1 (0:00–1:00) — Luigi's Story & 2-Click Onboarding
**Suggested Speaker:** Yurii · **Goal:** Hook the jury with the real human problem and show *"Innovations for all generations"* immediately.

> **[Драйвер за ноутбуком:]** Показати чистий стартовий екран (`#setup-screen`). Повільно навести курсор на чіпси питань, але ще не тиснути.

**Spoken (EN):**
"Meet Luigi. Two weeks ago, Luigi quit his job as a pizzaiolo and used his father's small savings to open *Pizzeria Amalfi*. He knows dough and wood-fired ovens—not cash-flow spreadsheets. When rent, staff salaries, taxes, and wholesale food deliveries land in the same week before card settlements clear, Luigi doesn't want an 8-chart analytics terminal. He wants one clear answer: *Will I run out of cash, and what do I do today?*

That's **KERNES CFO**—our Autonomous Liquidity Assistant built for *Innovations for all generations*."

> **[Драйвер за ноутбуком:]** Натиснути чіп `Pizzeria / Restaurant`, потім `Avoid running out of cash`. Перетягнути з робочого столу `pizzeria-amalfi-sample-2025.csv` і натиснути **`Check my cash →`**. Застосунок сам бере старт 22 червня, але оцінює баланс у €4,500: натиснути **`Edit`** біля *Opening balance*, ввести `5000.00` і натиснути **`Update`**. Не натискати *Use Amalfi sample* — це січень 2026 без нестачі грошей.

**Spoken (EN):**
"Two taps—his business type and his main goal—plus his bank export. KERNES picks the forecast window by itself; Luigi only corrects his balance to **€5,000** on June 22nd, and everything recalculates instantly. This June story uses his payments as **known, scheduled payments**—in a moment you'll also see KERNES forecast entirely on its own from a full year of real history."

---

## Block 2 (1:00–2:10) — Simple Mode: Action Plan, Outreach & Credit Simulation
**Suggested Speaker:** Tsimur · **Goal:** Show immediate practical value for Luigi + all 4 Challenge Card autonomy boundaries.

> **[Драйвер за ноутбуком:]** Почекати 1–2 сек, поки завантажаться вердикт і **Tailored next steps** (`#action-plan-steps`). Показати курсором на 4 бейджі автономності зверху (`1 · Analyzed by agent` → `4 · Simulation only — nothing sent`).

**Spoken (EN):**
"Within seconds, KERNES CFO translates Luigi's statement into plain English—not jargon. Notice our **4 autonomy boundaries** right at the top: what the agent analyzes independently, what it recommends, what needs Luigi's approval, and what is 100% simulation-only.

On **June 28**, Luigi hits a first shortfall of **−€6,250.00**, deepening to **−€8,248.91 on July 3rd** when rent and supplier invoices stack up.

Look at his tailored **Action Plan**. Under the hood, our deterministic **Transaction & Counterparty Classifier** separates walk-in card customers and mandatory taxes or staff payroll—which the AI will *never* touch—from real B2B counterparties."

> **[Драйвер за ноутбуком:]** Натиснути **`Draft payment email →`** на кроці з постачальником/орендодавцем, щоб показати готову чернетку листа, а потім перемкнутися на вкладку **`1. Short-term safety buffer`** і натиснути **`Approve preview`**.

**Spoken (EN):**
"With one click, Luigi gets a polite, editable email draft to a real B2B supplier or landlord—sent manually by him, never automatically. And to cover the remaining gap, he can preview a **€8,248.91 temporary safety buffer**. Click **Approve preview**—instantly, the uncovered gap drops to **EUR 0.00** on the chart, while the simulation badge confirms zero real loans or transfers were triggered."

---

## Block 3 (2:10–3:10) — Advanced Mode: Progressive Disclosure for Power Users
**Suggested Speaker:** Andrii · **Goal:** Prove the depth is there for finance-savvy owners without cluttering Luigi's first screen.

> **[Драйвер за ноутбуком:]** Проскролити до **`More details & deeper analysis`** (`#advanced-details-section`). Розгорнути акордеон **`What-if simulator & Q&A`**.

**Spoken (EN):**
"For Luigi, the top half of the screen was enough to act. But what if an experienced owner—or Luigi's accountant—wants deeper control? Everything else stays neatly collapsed below under **More details & deeper analysis**."

> **[Драйвер за ноутбуком:]** Натиснути чіп **`What if the client pays 3 days late?`** (або перейти на вкладку **`Client pays late`** і натиснути `Check late impact →`), потім показати графік угорі, де з'явилася нова крива What-If. Коротко розкрити або проскролити повз **`Compare ways to cover the dip`** та **`Cash health score & stress test`**.

**Spoken (EN):**
"Here, a user can stress-test what happens if a key incoming payment slips by 3 days—plotting the shifted curve directly onto the forecast chart without touching the baseline—compare financing options side-by-side with transparent estimated fees, or check their **Cash Health Score** and worst-case stress buffer."

---

## Block 4 (3:10–4:00) — Technical Architecture & Zero-Hallucination Trust
**Suggested Speaker:** Ivan · **Goal:** Impress Red Hat & Commerzbank engineers with OpenShift AI, vLLM, and deterministic grounding.

> **[Драйвер за ноутбуком:]** Залишитись на результатах (можна підсвітити бейдж моделі `kernes-qwen-7b` і час відповіді під Action Plan / Briefing).

**Spoken (EN):**
"In finance, an LLM hallucinating even a single digit breaks trust. So in KERNES CFO, **the AI never does math**.

Every balance, shortfall, anomaly, and fee is computed deterministically in Python using **integer minor units**. Only verified facts are passed to our open-weight **Qwen2.5 7B Instruct** model running via **vLLM on Red Hat OpenShift AI with an NVIDIA L4 GPU**, backed by a **Qwen2.5 1.5B** CPU fallback. Every response is checked by our numeric-boundary `cited_amounts()` guard—if a figure doesn't match the backend calculation, it retries or falls back cleanly without ever hiding the numbers. We also evaluated model accuracy in a **Jupyter Notebook on OpenShift AI**."

> **[Драйвер за ноутбуком:]** Перемкнутися на другу вкладку з січневим прогнозом (повна виписка 2025, напис *Estimated from past transactions*). Якщо час закінчується — пропустити цей абзац.

**Spoken (EN, ~20 s):**
"And Luigi doesn't need a list of future bills. Here the engine read the organizers' real 2025 Pizzeria Amalfi statement—1,125 transactions—learned his rhythm, like rent on the same day every month and weekly supplier runs, and forecast January 2026 by itself: a healthy month, with **€23,333.39** still above zero after our stress test. We backtested that rule on the full year: once it had three months of history, it caught every real shortfall in 38 weekly windows, with no false alarms and a third of the error of a naive forecast."

---

## Block 5 (4:00–5:00) — Business Model (B2B2C for Commerzbank) & Close
**Suggested Speaker:** Mikhail · **Goal:** Answer *"How does this make money?"* clearly for Commerzbank judges and close on a memorable note.

> **[Драйвер за ноутбуком:]** Повернутися поглядом/курсором на головний екран з Action Plan та симуляцією кредитного буфера.

**Spoken (EN):**
"So how do we monetize KERNES CFO? We designed a **two-layer B2B2C Embedded Banking model** *(team draft for final pricing validation)*:

1. **White-Label for Commerzbank:** Commerzbank embeds KERNES CFO directly inside its SME business banking portal—free for everyday owners like Luigi. The bank wins twice: early cash-crunch warnings reduce SME defaults, and the *Approve preview* step turns cold credit products into **high-intent, pre-qualified credit-line and factoring leads** at the exact moment the business needs liquidity.
2. **Optional Pro Tier (€19–€49/month):** Power users and multi-branch SMEs pay a lightweight SaaS fee for multi-currency forecasting, automated PSD2 bank-feed sync, and custom stress scenarios.

From a stressed pizzaiolo staring at a CSV to an actionable, zero-hallucination survival plan in under 60 seconds—**that is KERNES CFO**. Thank you, and we're ready for your questions!"

---

## Jury Q&A Cheat Sheet

1. **Why is Luigi's balance on June 22 €5,000 if the raw statement had a negative reconstructed balance?**
   - *Answer:* "`€5,000` on June 22 is our explicit known-payments demo scenario; the reconstructed real balance that day was `−€8,848.69`. The forecast learned purely from history is live in the app: the one-click sample forecasts January 2026 from the full 2025 statement, and the same rule is backtested in PR #17."
2. **Can Ask CFO simulate buying a brand-new €3,000 pizza oven?**
   - *Answer:* "Current `/api/ask-cfo` shifts or scales existing scheduled transactions in the CSV (e.g., delayed client payments or payroll growth). Supporting net-new capex injection is next on our roadmap."
3. **What happens if the GPU LLM goes down during a surge?**
   - *Answer:* "First, it fails over automatically from `kernes-qwen-7b` (vLLM GPU) to `kernes-qwen` (CPU). If both are unreachable, the API returns HTTP 503 and the UI still displays all deterministic forecasts, shortfalls, and proposals."
4. **How do you prevent the AI from suggesting emailing walk-in pizzeria customers or delaying taxes?**
   - *Answer:* "Our deterministic `classify_transaction()` engine tags `CARD SETTLEMENT` as `retail_non_contactable` and taxes, social security, and staff salaries as `fixed_mandatory`, strictly excluding them from email recommendations."
5. **Do you execute real bank transfers or send real emails?**
   - *Answer:* "Never. Every approval and email send is 100% simulated—explicitly labeled with Challenge Card autonomy level `4 · Simulation only — nothing sent`."
6. **Does it really forecast, or does it just replay the CSV?**
   - *Answer:* "Both, and the app says which. Payments the statement already lists for the forecast dates are used as known, scheduled payments—that's the June story. When the forecast starts after the statement ends, it reads only rows before the start date: monthly and weekly payees it has seen three times in a row, plus a 28-day average for the rest, and the screen says *Estimated from past transactions*. Our backtest of the same rule multiplies the future rows by 10 and checks the forecast doesn't move."
