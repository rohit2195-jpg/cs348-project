// ReportPanel.jsx — Filter & Report panel
// Lets the user filter portfolio positions and order history with dynamic
// dropdowns built from live DB data (symbols are never hardcoded).
// Also provides a before/after snapshot diff report.

import { useState, useEffect, useCallback } from 'react';

import { apiJson } from "./Config.js";

const fmt  = (n) => (n ?? 0).toFixed(2);
const fmtK = (n) => n != null
  ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : "—";

// ── Reusable multi-select checkbox list ───────────────────────────────────────
// Options are built from a live DB query (/api/symbols), never hardcoded.
function MultiSelect({ label, options, selected, onChange }) {
  return (
    <div className="rp-field">
      <div className="rp-label">{label}</div>
      <div className="rp-checkgroup">
        {options.length === 0
          ? <span className="rp-dim">No symbols in DB yet</span>
          : options.map((opt) => (
            <label key={opt} className="rp-check">
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() =>
                  onChange(selected.includes(opt)
                    ? selected.filter(s => s !== opt)
                    : [...selected, opt])
                }
              />
              {opt}
            </label>
          ))
        }
      </div>
    </div>
  );
}

// ── Range input pair ──────────────────────────────────────────────────────────
function RangeInput({ label, minVal, maxVal, onMinChange, onMaxChange, prefix = "" }) {
  return (
    <div className="rp-field">
      <div className="rp-label">{label}</div>
      <div className="rp-range">
        <input className="rp-input" type="number" placeholder="Min"
          value={minVal} onChange={e => onMinChange(e.target.value)} />
        <span className="rp-dim">—</span>
        <input className="rp-input" type="number" placeholder="Max"
          value={maxVal} onChange={e => onMaxChange(e.target.value)} />
        {prefix && <span className="rp-unit">{prefix}</span>}
      </div>
    </div>
  );
}

// ── Portfolio results table ───────────────────────────────────────────────────
function PortfolioResults({ results, count, filters }) {
  if (!results) return null;
  const totalVal = results.reduce((s, r) => s + r.market_value, 0);
  const totalPl  = results.reduce((s, r) => s + r.pl, 0);
  return (
    <div className="rp-results">
      <div className="rp-results-header">
        <span>PORTFOLIO — {count} RESULT{count !== 1 ? "S" : ""}</span>
        <span className="rp-dim" style={{ fontSize: 10 }}>
          {filters.symbols?.length ? `SYM: ${filters.symbols.join(",")}  ` : "ALL SYMBOLS  "}
          {filters.pl_min  != null ? `P/L ≥ ${filters.pl_min}%  ` : ""}
          {filters.pl_max  != null ? `P/L ≤ ${filters.pl_max}%  ` : ""}
          {filters.val_min != null ? `VAL ≥ $${filters.val_min}  ` : ""}
          {filters.val_max != null ? `VAL ≤ $${filters.val_max}` : ""}
        </span>
      </div>
      {count === 0 ? <div className="rp-empty">// NO POSITIONS MATCH FILTERS</div> : (
        <table className="rp-table">
          <thead>
            <tr><th>SYMBOL</th><th>QTY</th><th>AVG PRICE</th><th>CURR PRICE</th>
              <th>MKT VALUE</th><th>P/L $</th><th>P/L %</th></tr>
          </thead>
          <tbody>
            {results.map(r => (
              <tr key={r.symbol}>
                <td className="rp-sym">{r.symbol}</td>
                <td>{r.quantity}</td>
                <td>{fmtK(r.avg_price)}</td>
                <td>{fmtK(r.current_price)}</td>
                <td>{fmtK(r.market_value)}</td>
                <td className={r.pl >= 0 ? "rp-profit" : "rp-loss"}>
                  {r.pl >= 0 ? "+" : ""}${fmt(Math.abs(r.pl))}
                </td>
                <td className={r.pl_pct >= 0 ? "rp-profit" : "rp-loss"}>
                  {r.pl_pct >= 0 ? "+" : ""}{fmt(r.pl_pct)}%
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4} className="rp-dim" style={{ fontSize: 10 }}>TOTALS</td>
              <td style={{ fontWeight: "bold" }}>{fmtK(totalVal)}</td>
              <td className={totalPl >= 0 ? "rp-profit" : "rp-loss"} style={{ fontWeight: "bold" }}>
                {totalPl >= 0 ? "+" : ""}${fmt(Math.abs(totalPl))}
              </td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}

// ── Order results table ───────────────────────────────────────────────────────
function OrderResults({ results, count, filters }) {
  if (!results) return null;
  const totalVal = results.reduce((s, o) => s + o.total_value, 0);
  return (
    <div className="rp-results">
      <div className="rp-results-header">
        <span>ORDERS — {count} RESULT{count !== 1 ? "S" : ""}</span>
        <span className="rp-dim" style={{ fontSize: 10 }}>
          {filters.symbols?.length   ? `SYM: ${filters.symbols.join(",")}  ` : "ALL SYMBOLS  "}
          {filters.trade_type        ? `TYPE: ${filters.trade_type.toUpperCase()}  ` : ""}
          {filters.status            ? `STATUS: ${filters.status.toUpperCase()}  ` : ""}
          {filters.date_from         ? `FROM: ${filters.date_from}  ` : ""}
          {filters.date_to           ? `TO: ${filters.date_to}  ` : ""}
          {filters.price_min != null ? `PRICE ≥ $${filters.price_min}` : ""}
          {filters.price_max != null ? `  PRICE ≤ $${filters.price_max}` : ""}
        </span>
      </div>
      {count === 0 ? <div className="rp-empty">// NO ORDERS MATCH FILTERS</div> : (
        <table className="rp-table">
          <thead>
            <tr><th>#</th><th>SYMBOL</th><th>TYPE</th><th>QTY</th>
              <th>PRICE</th><th>TOTAL</th><th>STATUS</th><th>DATE</th></tr>
          </thead>
          <tbody>
            {results.map(o => (
              <tr key={o.id}>
                <td className="rp-dim">#{o.id}</td>
                <td className="rp-sym">{o.symbol}</td>
                <td><span className={`rp-badge ${o.trade_type}`}>{o.trade_type.toUpperCase()}</span></td>
                <td>{o.quantity}</td>
                <td>{fmtK(o.price)}</td>
                <td>{fmtK(o.total_value)}</td>
                <td><span className={`rp-badge ${o.status}`}>{o.status}</span></td>
                <td className="rp-dim" style={{ fontSize: 11 }}>{o.timestamp.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5} className="rp-dim" style={{ fontSize: 10 }}>TOTAL VALUE</td>
              <td style={{ fontWeight: "bold" }}>{fmtK(totalVal)}</td>
              <td colSpan={2}></td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}

// ── Before/After snapshot diff ────────────────────────────────────────────────
function SnapshotDiff({ before, after }) {
  if (!before || !after) return null;
  const allSymbols = [...new Set([
    ...before.snapshot.map(r => r.symbol),
    ...after.snapshot.map(r => r.symbol),
  ])].sort();

  const bMap = Object.fromEntries(before.snapshot.map(r => [r.symbol, r]));
  const aMap = Object.fromEntries(after.snapshot.map(r => [r.symbol, r]));

  const changed = allSymbols
    .map(sym => {
      const b = bMap[sym], a = aMap[sym];
      const qtyDiff = (a?.quantity ?? 0) - (b?.quantity ?? 0);
      const valDiff = (a?.market_value ?? 0) - (b?.market_value ?? 0);
      const hasChange = (b?.quantity ?? 0) !== (a?.quantity ?? 0) ||
                        (b?.avg_price ?? 0) !== (a?.avg_price ?? 0);
      return { sym, b, a, qtyDiff, valDiff, hasChange, isNew: !b, isRemoved: !a };
    })
    .filter(r => r.hasChange);

  return (
    <div className="rp-results" style={{ marginTop: 12 }}>
      <div className="rp-results-header">
        <span>DIFF REPORT</span>
        <span className="rp-dim" style={{ fontSize: 10 }}>
          BEFORE: {before.taken_at} → AFTER: {after.taken_at}
          {"  "}{changed.length} CHANGE{changed.length !== 1 ? "S" : ""}
        </span>
      </div>
      {changed.length === 0
        ? <div className="rp-empty">// NO CHANGES DETECTED BETWEEN SNAPSHOTS</div>
        : (
          <table className="rp-table">
            <thead>
              <tr><th>SYMBOL</th><th>QTY BEFORE</th><th>QTY AFTER</th><th>Δ QTY</th>
                <th>AVG BEFORE</th><th>AVG AFTER</th><th>VAL BEFORE</th><th>VAL AFTER</th><th>Δ VALUE</th></tr>
            </thead>
            <tbody>
              {changed.map(({ sym, b, a, qtyDiff, valDiff, isNew, isRemoved }) => (
                <tr key={sym} className={isNew ? "rp-row-new" : isRemoved ? "rp-row-removed" : ""}>
                  <td className="rp-sym">{sym}</td>
                  <td className={qtyDiff !== 0 ? "rp-changed" : ""}>{b?.quantity ?? "—"}</td>
                  <td className={qtyDiff !== 0 ? "rp-changed" : ""}>{a?.quantity ?? "—"}</td>
                  <td className={qtyDiff > 0 ? "rp-profit" : qtyDiff < 0 ? "rp-loss" : ""}>
                    {qtyDiff > 0 ? "+" : ""}{qtyDiff !== 0 ? qtyDiff : "—"}
                  </td>
                  <td>{b ? fmtK(b.avg_price) : "—"}</td>
                  <td>{a ? fmtK(a.avg_price) : "—"}</td>
                  <td>{b ? fmtK(b.market_value) : "—"}</td>
                  <td>{a ? fmtK(a.market_value) : "—"}</td>
                  <td className={valDiff >= 0 ? "rp-profit" : "rp-loss"} style={{ fontWeight: "bold" }}>
                    {isNew ? "NEW +" + fmtK(a.market_value)
                     : isRemoved ? "CLOSED"
                     : (valDiff >= 0 ? "+" : "") + fmtK(valDiff)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={6} className="rp-dim" style={{ fontSize: 10 }}>PORTFOLIO TOTAL</td>
                <td style={{ fontWeight: "bold" }}>{fmtK(before.total_value)}</td>
                <td style={{ fontWeight: "bold" }}>{fmtK(after.total_value)}</td>
                <td className={after.total_value - before.total_value >= 0 ? "rp-profit" : "rp-loss"}
                    style={{ fontWeight: "bold" }}>
                  {after.total_value - before.total_value >= 0 ? "+" : ""}
                  {fmtK(after.total_value - before.total_value)}
                </td>
              </tr>
            </tfoot>
          </table>
        )
      }
    </div>
  );
}

// ── Main ReportPanel ──────────────────────────────────────────────────────────
export default function ReportPanel({ onClose }) {
  const [tab,     setTab]     = useState("portfolio");
  const [symbols, setSymbols] = useState([]);   // live from DB
  const [loading, setLoading] = useState(false);

  // Portfolio filters
  const [pfSymbols, setPfSymbols] = useState([]);
  const [pfPlMin,   setPfPlMin]   = useState("");
  const [pfPlMax,   setPfPlMax]   = useState("");
  const [pfValMin,  setPfValMin]  = useState("");
  const [pfValMax,  setPfValMax]  = useState("");
  const [pfResults, setPfResults] = useState(null);
  const [pfFilters, setPfFilters] = useState({});

  // Order filters
  const [orSymbols,  setOrSymbols]  = useState([]);
  const [orType,     setOrType]     = useState("");
  const [orStatus,   setOrStatus]   = useState("");
  const [orDateFrom, setOrDateFrom] = useState("");
  const [orDateTo,   setOrDateTo]   = useState("");
  const [orPrMin,    setOrPrMin]    = useState("");
  const [orPrMax,    setOrPrMax]    = useState("");
  const [orResults,  setOrResults]  = useState(null);
  const [orFilters,  setOrFilters]  = useState({});

  // Snapshots
  const [snapBefore, setSnapBefore] = useState(null);
  const [snapAfter,  setSnapAfter]  = useState(null);
  const [snapMsg,    setSnapMsg]    = useState("");

  // ── Fetch symbols from DB on mount ─────────────────────────────────────────
  // This is the dynamic dropdown — built from /api/symbols, never hardcoded.
  // Any symbol you trade automatically appears here.
  useEffect(() => {
    apiJson('/symbols').then(setSymbols).catch(() => {});
  }, []);

  // ── Run portfolio filter ───────────────────────────────────────────────────
  const runPortfolioFilter = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (pfSymbols.length) p.set("symbols", pfSymbols.join(","));
      if (pfPlMin  !== "")  p.set("pl_min",  pfPlMin);
      if (pfPlMax  !== "")  p.set("pl_max",  pfPlMax);
      if (pfValMin !== "")  p.set("val_min", pfValMin);
      if (pfValMax !== "")  p.set("val_max", pfValMax);
      const data = await apiJson(`/filter/portfolio?${p}`);
      setPfResults(data.results);
      setPfFilters(data.filters);
    } finally { setLoading(false); }
  }, [pfSymbols, pfPlMin, pfPlMax, pfValMin, pfValMax]);

  // ── Run order filter ───────────────────────────────────────────────────────
  const runOrderFilter = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (orSymbols.length) p.set("symbols",    orSymbols.join(","));
      if (orType)           p.set("trade_type", orType);
      if (orStatus)         p.set("status",     orStatus);
      if (orDateFrom)       p.set("date_from",  orDateFrom);
      if (orDateTo)         p.set("date_to",    orDateTo);
      if (orPrMin !== "")   p.set("price_min",  orPrMin);
      if (orPrMax !== "")   p.set("price_max",  orPrMax);
      const data = await apiJson(`/filter/orders?${p}`);
      setOrResults(data.results);
      setOrFilters(data.filters);
    } finally { setLoading(false); }
  }, [orSymbols, orType, orStatus, orDateFrom, orDateTo, orPrMin, orPrMax]);

  // ── Snapshot ───────────────────────────────────────────────────────────────
  const takeSnapshot = async (which) => {
    try {
      const data = await apiJson('/report/snapshot');
      if (which === "before") {
        setSnapBefore(data); setSnapAfter(null);
        setSnapMsg("✓ Before snapshot taken. Make your changes, then take After snapshot.");
      } else {
        setSnapAfter(data);
        setSnapMsg("✓ After snapshot taken — diff shown below.");
      }
    } catch { setSnapMsg("✗ Failed to fetch snapshot."); }
  };

  return (
    <>
      <style>{rpStyles}</style>
      <div className="rp-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="rp-panel">

          <div className="rp-header">
            <span className="rp-title">REPORTS &amp; FILTERS<span className="blink">_</span></span>
            <button className="settings-close" onClick={onClose}>[X] CLOSE</button>
          </div>

          <div className="rp-tabs">
            {[["portfolio","PORTFOLIO FILTER"],["orders","ORDER FILTER"],["snapshot","BEFORE / AFTER"]].map(([k,l]) => (
              <button key={k} className={`rp-tab ${tab===k?"active":""}`} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>

          <div className="rp-body">

            {/* ── Portfolio Filter ── */}
            {tab === "portfolio" && (
              <>
                <div className="rp-filters">
                  <MultiSelect
                    label={`SYMBOLS — ${symbols.length} found in DB (dynamic)`}
                    options={symbols} selected={pfSymbols} onChange={setPfSymbols}
                  />
                  <RangeInput label="P/L % RANGE" minVal={pfPlMin} maxVal={pfPlMax}
                    onMinChange={setPfPlMin} onMaxChange={setPfPlMax} prefix="%" />
                  <RangeInput label="MARKET VALUE RANGE" minVal={pfValMin} maxVal={pfValMax}
                    onMinChange={setPfValMin} onMaxChange={setPfValMax} prefix="$" />
                  <div className="rp-actions">
                    <button className="rp-btn-run" onClick={runPortfolioFilter} disabled={loading}>
                      {loading ? "RUNNING_" : "▶ RUN FILTER"}
                    </button>
                    <button className="rp-btn-clear" onClick={() => {
                      setPfSymbols([]); setPfPlMin(""); setPfPlMax("");
                      setPfValMin(""); setPfValMax(""); setPfResults(null);
                    }}>CLEAR</button>
                  </div>
                </div>
                <PortfolioResults results={pfResults} count={pfResults?.length ?? 0} filters={pfFilters} />
              </>
            )}

            {/* ── Order Filter ── */}
            {tab === "orders" && (
              <>
                <div className="rp-filters">
                  <MultiSelect
                    label={`SYMBOLS — ${symbols.length} found in DB (dynamic)`}
                    options={symbols} selected={orSymbols} onChange={setOrSymbols}
                  />
                  <div className="rp-row">
                    <div className="rp-field">
                      <div className="rp-label">TRADE TYPE</div>
                      <select className="rp-select" value={orType} onChange={e => setOrType(e.target.value)}>
                        <option value="">All</option>
                        <option value="buy">Buy</option>
                        <option value="sell">Sell</option>
                      </select>
                    </div>
                    <div className="rp-field">
                      <div className="rp-label">STATUS</div>
                      <select className="rp-select" value={orStatus} onChange={e => setOrStatus(e.target.value)}>
                        <option value="">All</option>
                        <option value="filled">Filled</option>
                        <option value="canceled">Canceled</option>
                      </select>
                    </div>
                  </div>
                  <div className="rp-row">
                    <div className="rp-field">
                      <div className="rp-label">DATE FROM</div>
                      <input className="rp-input" type="date" value={orDateFrom} onChange={e => setOrDateFrom(e.target.value)} />
                    </div>
                    <div className="rp-field">
                      <div className="rp-label">DATE TO</div>
                      <input className="rp-input" type="date" value={orDateTo} onChange={e => setOrDateTo(e.target.value)} />
                    </div>
                  </div>
                  <RangeInput label="PRICE PER SHARE RANGE ($)" minVal={orPrMin} maxVal={orPrMax}
                    onMinChange={setOrPrMin} onMaxChange={setOrPrMax} prefix="$" />
                  <div className="rp-actions">
                    <button className="rp-btn-run" onClick={runOrderFilter} disabled={loading}>
                      {loading ? "RUNNING_" : "▶ RUN FILTER"}
                    </button>
                    <button className="rp-btn-clear" onClick={() => {
                      setOrSymbols([]); setOrType(""); setOrStatus("");
                      setOrDateFrom(""); setOrDateTo(""); setOrPrMin(""); setOrPrMax("");
                      setOrResults(null);
                    }}>CLEAR</button>
                  </div>
                </div>
                <OrderResults results={orResults} count={orResults?.length ?? 0} filters={orFilters} />
              </>
            )}

            {/* ── Before / After Snapshot ── */}
            {tab === "snapshot" && (
              <>
                <div className="rp-snapshot-info">
                  Take a <strong>Before</strong> snapshot, execute a trade in the main dashboard,
                  then take an <strong>After</strong> snapshot to see exactly what changed.
                </div>
                <div className="rp-actions" style={{ padding: "14px 0 4px" }}>
                  <button className="rp-btn-run" onClick={() => takeSnapshot("before")}>
                    📸 SNAP BEFORE
                  </button>
                  <button
                    className={`rp-btn-run ${!snapBefore ? "rp-btn-disabled" : ""}`}
                    onClick={() => takeSnapshot("after")} disabled={!snapBefore}
                  >
                    📸 SNAP AFTER
                  </button>
                  <button className="rp-btn-clear" onClick={() => {
                    setSnapBefore(null); setSnapAfter(null); setSnapMsg("");
                  }}>RESET</button>
                </div>
                {snapMsg && <div className="rp-snap-msg">{snapMsg}</div>}

                {snapBefore && (
                  <div className="rp-results" style={{ marginTop: 12 }}>
                    <div className="rp-results-header">
                      <span>BEFORE SNAPSHOT</span>
                      <span className="rp-dim" style={{ fontSize: 10 }}>
                        {snapBefore.taken_at} — TOTAL: {fmtK(snapBefore.total_value)}
                      </span>
                    </div>
                    <table className="rp-table">
                      <thead><tr>
                        <th>SYMBOL</th><th>QTY</th><th>AVG PRICE</th>
                        <th>CURR PRICE</th><th>MKT VALUE</th><th>P/L %</th>
                      </tr></thead>
                      <tbody>
                        {snapBefore.snapshot.map(r => (
                          <tr key={r.symbol}>
                            <td className="rp-sym">{r.symbol}</td>
                            <td>{r.quantity}</td>
                            <td>{fmtK(r.avg_price)}</td>
                            <td>{fmtK(r.current_price)}</td>
                            <td>{fmtK(r.market_value)}</td>
                            <td className={r.pl_pct >= 0 ? "rp-profit" : "rp-loss"}>
                              {r.pl_pct >= 0 ? "+" : ""}{fmt(r.pl_pct)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <SnapshotDiff before={snapBefore} after={snapAfter} />
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ── Component-scoped styles ───────────────────────────────────────────────────
const rpStyles = `
  .rp-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.75);
    z-index: 2000; display: flex; align-items: flex-start;
    justify-content: center; padding: 24px 16px; overflow-y: auto;
  }
  .rp-panel {
    width: 100%; max-width: 920px; background: var(--bg);
    border: 1px solid var(--border); box-shadow: 0 8px 60px rgba(0,0,0,0.6);
    display: flex; flex-direction: column;
    animation: rpIn 0.18s ease-out;
  }
  @keyframes rpIn { from { transform: translateY(-16px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
  .rp-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; border-bottom: 1px solid var(--border); background: var(--panel);
  }
  .rp-title {
    font-family: 'VT323', monospace; font-size: 22px; letter-spacing: 3px;
    color: var(--accent); text-shadow: var(--title-shadow);
  }
  .rp-tabs { display: flex; border-bottom: 1px solid var(--border); }
  .rp-tab {
    background: transparent; border: none; border-right: 1px solid var(--border);
    color: var(--text-dim); font-family: 'Share Tech Mono', monospace;
    font-size: 11px; letter-spacing: 2px; padding: 8px 20px;
    cursor: pointer; text-transform: uppercase; transition: all 0.1s;
  }
  .rp-tab:hover { color: var(--accent2); background: var(--panel); }
  .rp-tab.active { color: var(--accent); background: var(--panel); border-bottom: 2px solid var(--accent); margin-bottom: -1px; }
  .rp-body { padding: 16px 18px; overflow-y: auto; max-height: 72vh; }
  .rp-filters { background: var(--panel); border: 1px solid var(--border); padding: 14px 16px; margin-bottom: 16px; }
  .rp-field { margin-bottom: 12px; }
  .rp-label { font-size: 10px; letter-spacing: 1.5px; color: var(--text-dim); text-transform: uppercase; margin-bottom: 6px; }
  .rp-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .rp-checkgroup { display: flex; flex-wrap: wrap; gap: 6px; }
  .rp-check {
    display: flex; align-items: center; gap: 5px; font-size: 12px;
    color: var(--text); cursor: pointer; padding: 3px 8px;
    border: 1px solid var(--border); transition: border-color 0.1s;
  }
  .rp-check:hover { border-color: var(--accent2); }
  .rp-check input[type=checkbox] { accent-color: var(--accent); cursor: pointer; }
  .rp-range { display: flex; align-items: center; gap: 8px; }
  .rp-input {
    background: transparent; border: 1px solid var(--accent3);
    color: var(--text); font-family: 'Share Tech Mono', monospace;
    font-size: 12px; padding: 4px 8px; outline: none; width: 90px;
    transition: border-color 0.15s;
  }
  .rp-input[type=date] { width: auto; color-scheme: dark; }
  .rp-input:focus { border-color: var(--accent); }
  .rp-select {
    background: var(--bg); border: 1px solid var(--accent3); color: var(--text);
    font-family: 'Share Tech Mono', monospace; font-size: 12px; padding: 4px 8px;
    outline: none; width: 100%; cursor: pointer; transition: border-color 0.15s;
  }
  .rp-select:focus { border-color: var(--accent); }
  .rp-unit { font-size: 11px; color: var(--text-dim); }
  .rp-actions { display: flex; gap: 10px; margin-top: 12px; }
  .rp-btn-run {
    background: var(--dim); border: 1px solid var(--accent); color: var(--accent);
    font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1px;
    padding: 6px 16px; cursor: pointer; transition: all 0.1s; text-transform: uppercase;
  }
  .rp-btn-run:hover  { background: var(--accent); color: var(--bg); }
  .rp-btn-run:disabled, .rp-btn-disabled { opacity: 0.4; cursor: not-allowed; }
  .rp-btn-clear {
    background: transparent; border: 1px solid var(--accent3); color: var(--text-dim);
    font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1px;
    padding: 6px 16px; cursor: pointer; transition: all 0.1s; text-transform: uppercase;
  }
  .rp-btn-clear:hover { border-color: var(--loss); color: var(--loss); }
  .rp-results { margin-top: 8px; }
  .rp-results-header {
    display: flex; justify-content: space-between; align-items: baseline;
    font-size: 11px; letter-spacing: 1.5px; color: var(--accent2);
    padding: 6px 0; border-bottom: 1px solid var(--border); margin-bottom: 6px;
  }
  .rp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .rp-table th {
    font-size: 10px; letter-spacing: 1px; color: var(--text-dim); text-align: right;
    padding: 4px 10px; border-bottom: 1px solid var(--dim); text-transform: uppercase;
  }
  .rp-table th:first-child { text-align: left; }
  .rp-table td { padding: 5px 10px; text-align: right; border-bottom: 1px solid var(--panel); font-variant-numeric: tabular-nums; }
  .rp-table td:first-child { text-align: left; }
  .rp-table tr:hover td { background: var(--panel); }
  .rp-table tfoot td { font-size: 11px; padding-top: 8px; border-top: 1px solid var(--border); }
  .rp-sym     { color: var(--accent); font-weight: bold; }
  .rp-profit  { color: var(--profit); }
  .rp-loss    { color: var(--loss); }
  .rp-dim     { color: var(--text-dim); }
  .rp-changed { color: var(--warn); font-weight: bold; }
  .rp-row-new     td { background: rgba(0,200,80,0.05); }
  .rp-row-removed td { background: rgba(255,50,50,0.05); }
  .rp-badge { padding: 1px 6px; border: 1px solid; font-size: 10px; letter-spacing: 1px; }
  .rp-badge.buy      { color: var(--profit); border-color: var(--accent3); }
  .rp-badge.sell     { color: var(--loss);   border-color: var(--loss); }
  .rp-badge.filled   { color: var(--profit); border-color: transparent; }
  .rp-badge.pending  { color: var(--warn);   border-color: transparent; }
  .rp-badge.canceled { color: var(--text-dim); border-color: transparent; }
  .rp-empty { color: var(--text-dim); font-size: 11px; padding: 12px; letter-spacing: 1px; }
  .rp-snapshot-info {
    font-size: 11px; color: var(--text-dim); line-height: 1.7;
    padding: 10px 12px; border: 1px solid var(--border); background: var(--panel); letter-spacing: 0.5px;
  }
  .rp-snap-msg { font-size: 11px; color: var(--accent2); letter-spacing: 1px; padding: 8px 0; }
`;
