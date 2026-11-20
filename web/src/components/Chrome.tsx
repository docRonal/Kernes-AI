export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="4" />
      <path d="M7 20h5v-6h5v4h5V9h3" />
    </svg>
  );
}

export function TopBar() {
  return (
    <header className="topbar">
      <a className="brand" href="/">
        <BrandMark />
        <span className="brand-name">Kernes</span>
        <span className="brand-sub">Autonomous CFO</span>
      </a>
      <p className="sim-badge">
        <span className="sim-dot" aria-hidden="true" />
        Simulation mode<span className="sim-long">&nbsp;· no real money moves</span>
      </p>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <span>Kernes · Autonomous CFO</span>
      <span>Collabothon 2026 · Red Hat challenge</span>
      <span>Synthetic data · every action is a simulation</span>
    </footer>
  );
}
