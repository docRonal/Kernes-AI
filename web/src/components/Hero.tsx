import { useRef, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import { motion } from "motion/react";
import { ArrowRight, FileSpreadsheet } from "lucide-react";
import { errorMessage } from "../api";
import { tidyBalance, toMinor } from "../format";

export type SetupValues = {
  file: File | null;
  startingMinor: string;
  startDate: string;
};

const ease = [0.2, 0.8, 0.2, 1] as const;

function Line({ children, delay }: { children: ReactNode; delay: number }) {
  return (
    <span className="mask">
      <motion.span
        className="mask-inner"
        initial={{ y: "105%" }}
        animate={{ y: "0%" }}
        transition={{ duration: 0.9, ease, delay }}
      >
        {children}
      </motion.span>
    </span>
  );
}

export function Hero({ onSubmit }: { onSubmit: (values: SetupValues) => Promise<void> }) {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-head">
        <motion.p className="eyebrow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
          Liquidity agent
        </motion.p>
        <h1 id="hero-title">
          <Line delay={0.05}>Your cash,</Line>
          <Line delay={0.16}>
            <em>fourteen days</em> ahead.
          </Line>
        </h1>
        <motion.p
          className="lead"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease, delay: 0.35 }}
        >
          Add the payments you expect. The agent checks every day of the next two weeks, warns you before the
          account dips below zero and suggests a fix. You decide what happens.
        </motion.p>
      </div>
      <SetupForm onSubmit={onSubmit} />
    </section>
  );
}

function SetupForm({ onSubmit }: { onSubmit: (values: SetupValues) => Promise<void> }) {
  const [balance, setBalance] = useState("12,000.00");
  const [startDate, setStartDate] = useState("2026-11-23");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    let startingMinor: string;
    try {
      startingMinor = toMinor(balance);
    } catch (problem) {
      setError(errorMessage(problem));
      return;
    }
    if (!startDate) {
      setError("Pick the day the forecast should start.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit({ file, startingMinor, startDate });
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  function clearFile() {
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  function onDrag(event: DragEvent<HTMLLabelElement>, over: boolean) {
    event.preventDefault();
    if (over) setDragging(true);
    else if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  return (
    <motion.form
      className="setup"
      onSubmit={submit}
      noValidate
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease, delay: 0.45 }}
    >
      <div className="setup-cell">
        <p className="cell-label">
          <span>01</span>Where you start
        </p>
        <p className="sentence">
          I have{" "}
          <label className="inline">
            <span className="sr-only">Opening balance in PLN</span>
            <span className="unit">PLN</span>
            <input
              value={balance}
              onChange={(event) => setBalance(event.target.value)}
              onBlur={() => setBalance(tidyBalance(balance))}
              inputMode="decimal"
              autoComplete="off"
              spellCheck={false}
              style={{ width: `${Math.max(5, balance.length + 0.5)}ch` }}
            />
          </label>{" "}
          in the account on{" "}
          <label className="inline">
            <span className="sr-only">Forecast start date</span>
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
          </label>
          .
        </p>
      </div>

      <div className="setup-cell">
        <p className="cell-label">
          <span>02</span>What's coming
        </p>
        <label
          className={`drop${dragging ? " is-over" : ""}${file ? " has-file" : ""}`}
          onDragEnter={(event) => onDrag(event, true)}
          onDragOver={(event) => onDrag(event, true)}
          onDragLeave={(event) => onDrag(event, false)}
          onDrop={onDrop}
        >
          <input
            ref={fileInput}
            className="sr-only"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <FileSpreadsheet className="drop-icon" aria-hidden="true" strokeWidth={1.5} />
          <span className="drop-text">
            <span className="drop-title">{file ? file.name : "Upcoming payments"}</span>
            <span className="drop-sub">
              {file ? `${(file.size / 1024).toFixed(1)} KB · ready` : "CSV file · drop it here or click to choose"}
            </span>
          </span>
        </label>
        <p className="hint">
          {file ? (
            <button type="button" className="link-btn" onClick={clearFile}>
              Remove the file and use the sample
            </button>
          ) : (
            <>
              No file? We'll use the <a href="/demo/transactions.csv">sample payments</a>.
            </>
          )}
        </p>
      </div>

      <div className="setup-cell setup-action">
        <p className="cell-label">
          <span>03</span>Run the agent
        </p>
        <button type="submit" className="btn primary big" disabled={busy} aria-busy={busy}>
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Calculating…
            </>
          ) : (
            <>
              Show my next 14 days
              <ArrowRight className="arrow" aria-hidden="true" size={20} />
            </>
          )}
        </button>
      </div>

      {error && (
        <p className="alert setup-error" role="alert">
          {error}
        </p>
      )}
    </motion.form>
  );
}
