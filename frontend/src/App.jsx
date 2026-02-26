import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine
} from "recharts";
import { ThemeProvider, SettingsPanel } from "./Settings";

const API = "http://localhost:5000/api";

// ── Styles (use CSS vars set by ThemeProvider) ────────────────────────────────
const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body, #root {
    height: 100%; width: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    overflow: hidden;
  }

  body::before {
    content: '';
    position: fixed; inset: 0;
    background: repeating-linear-gradient(
      0deg, transparent, transparent 2px,
      var(--scanline, rgba(0,0,0,0.15)) 2px,
      var(--scanline, rgba(0,0,0,0.15)) 4px
    );
    pointer-events: none;
    z-index: 9999;
  }

  body::after {
    content: '';
    position: fixed; inset: 0;
    background: radial-gradient(ellipse at center, transparent 60%, var(--vignette, rgba(0,0,0,0.7)) 100%);
    pointer-events: none;
    z-index: 9998;
  }

  /* Light themes: kill CRT effects and glow */
  html.light-theme body::before,
  html.light-theme body::after { display: none; }

  html.light-theme .header-title { text-shadow: none; letter-spacing: 2px; }
  html.light-theme .market-badge { animation: none; }
  html.light-theme .blink { animation: none; opacity: 1; }

  .app {
    height: 100vh;
    display: grid;
    grid-template-rows: 48px 1fr 120px 32px;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--border);
    padding: 1px;
  }

  .header {
    grid-column: 1 / -1;
    background: var(--bg);
    display: flex;
    align-items: center;
    gap: 28px;
    padding: 0 16px;
    border-bottom: 1px solid var(--border);
  }

  .header-title {
    font-family: 'VT323', monospace;
    font-size: 28px;
    color: var(--accent);
    letter-spacing: 3px;
    text-shadow: var(--title-shadow);
    flex-shrink: 0;
  }

  .header-stat { display: flex; flex-direction: column; gap: 1px; }
  .header-stat-label {
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .header-stat-value { font-size: 15px; font-weight: bold; color: var(--text); }

  .market-badge {
    font-size: 11px;
    letter-spacing: 2px;
    padding: 3px 10px;
    border: 1px solid;
    animation: pulse 2s infinite;
  }
  .market-badge.open   { color: var(--profit); border-color: var(--profit); }
  .market-badge.closed { color: var(--loss);   border-color: var(--loss);   animation: none; }

  @keyframes pulse { 0%,100%{ opacity:1 } 50%{ opacity:0.4 } }

  .last-update { font-size: 10px; color: var(--text-dim); margin-left: 4px; }

  .panel { background: var(--bg); overflow: hidden; display: flex; flex-direction: column; }
  .panel-title {
    font-family: 'VT323', monospace;
    font-size: 18px;
    letter-spacing: 2px;
    color: var(--accent2);
    padding: 6px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    flex-shrink: 0;
  }

  .panel-scroll { overflow-y: auto; flex: 1; padding: 8px 0; }
  .panel-scroll::-webkit-scrollbar { width: 4px; }
  .panel-scroll::-webkit-scrollbar-thumb { background: var(--dim); }

  .tbl { width: 100%; border-collapse: collapse; }
  .tbl th {
    font-size: 10px;
    letter-spacing: 1px;
    color: var(--text-dim);
    text-align: right;
    padding: 3px 12px;
    border-bottom: 1px solid var(--dim);
    text-transform: uppercase;
  }
  .tbl th:first-child { text-align: left; }
  .tbl td {
    padding: 5px 12px;
    text-align: right;
    border-bottom: 1px solid var(--panel);
    font-variant-numeric: tabular-nums;
    transition: background 0.15s;
  }
  .tbl td:first-child { text-align: left; }
  .tbl tr:hover td { background: var(--panel); }

  .sym    { color: var(--accent); font-weight: bold; font-size: 14px; }
  .profit { color: var(--profit); }
  .loss   { color: var(--loss); }
  .neutral { color: var(--text-dim); }

  .order-row {
    display: grid;
    grid-template-columns: 36px 52px 44px 44px 72px 68px 1fr;
    gap: 4px; padding: 4px 12px;
    border-bottom: 1px solid var(--panel);
    font-size: 12px;
  }
  .order-row.hdr {
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: var(--panel);
  }
  .order-row:not(.hdr):hover { background: var(--panel); }

  .badge { padding: 1px 6px; border: 1px solid; font-size: 10px; letter-spacing: 1px; }
  .badge.buy     { color: var(--profit); border-color: var(--accent3); }
  .badge.sell    { color: var(--loss);   border-color: var(--loss); }
  .badge.filled  { color: var(--profit); border-color: transparent; }
  .badge.pending { color: var(--warn);   border-color: transparent; }
  .badge.canceled { color: var(--text-dim); border-color: transparent; }

  .charts-panel {
    grid-column: 1 / -1;
    background: var(--bg);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
  }
  .charts-inner {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px; flex: 1;
    background: var(--border);
  }
  .chart-block {
    background: var(--bg);
    padding: 6px 8px 2px;
    display: flex;
    flex-direction: column;
  }
  .chart-label {
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--text-dim);
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  .statusbar {
    grid-column: 1 / -1;
    background: var(--panel);
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 12px;
    font-size: 12px;
  }

  .cmd-btn {
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--accent2);
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    letter-spacing: 1px;
    padding: 2px 10px;
    cursor: pointer;
    transition: all 0.1s;
    text-transform: uppercase;
  }
  .cmd-btn:hover { background: var(--accent3); color: var(--bg); border-color: var(--accent); }

  .flash-msg { margin-left: auto; font-size: 11px; letter-spacing: 1px; color: var(--profit); }
  .flash-msg.err { color: var(--loss); }

  /* Modal */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.85);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000;
  }
  .modal {
    background: var(--bg);
    border: 1px solid var(--accent2);
    box-shadow: 0 0 40px rgba(0,0,0,0.5);
    padding: 24px 28px;
    min-width: 360px; max-width: 460px; width: 100%;
  }
  .modal-title {
    font-family: 'VT323', monospace;
    font-size: 22px;
    letter-spacing: 3px;
    margin-bottom: 20px;
    color: var(--accent);
    text-shadow: 0 0 8px var(--accent);
  }

  .field { margin-bottom: 14px; }
  .field label {
    display: block;
    font-size: 10px; letter-spacing: 1px;
    color: var(--text-dim);
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  .field input {
    width: 100%;
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 14px;
    padding: 6px 10px;
    outline: none;
    letter-spacing: 1px;
    text-transform: uppercase;
    transition: border-color 0.15s;
  }
  .field input:focus { border-color: var(--accent); box-shadow: 0 0 8px var(--panel); }

  .modal-preview {
    font-size: 12px; color: var(--text-dim);
    margin-bottom: 16px; letter-spacing: 1px; min-height: 18px;
  }
  .modal-actions { display: flex; gap: 10px; }
  .modal-error { color: var(--loss); font-size: 11px; margin-top: 8px; letter-spacing: 1px; }

  .btn-confirm {
    flex: 1;
    background: var(--dim);
    border: 1px solid var(--accent);
    color: var(--accent);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px; letter-spacing: 2px; padding: 8px;
    cursor: pointer; text-transform: uppercase; transition: all 0.1s;
  }
  .btn-confirm:hover { background: var(--accent); color: var(--bg); }
  .btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-cancel {
    flex: 1;
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--text-dim);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px; letter-spacing: 2px; padding: 8px;
    cursor: pointer; text-transform: uppercase; transition: all 0.1s;
  }
  .btn-cancel:hover { border-color: var(--loss); color: var(--loss); }

  .live-quote {
    font-family: 'VT323', monospace;
    font-size: 32px;
    color: var(--accent);
    text-shadow: 0 0 12px var(--accent);
    letter-spacing: 2px;
    text-align: center;
    padding: 12px 0;
  }

  .recharts-tooltip-wrapper .custom-tooltip {
    background: var(--bg);
    border: 1px solid var(--accent3);
    padding: 6px 10px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    color: var(--text);
  }

  .blink { animation: blink 1s step-start infinite; }
  @keyframes blink { 50% { opacity: 0; } }

  .loading {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: var(--text-dim); letter-spacing: 3px;
    font-family: 'VT323', monospace; font-size: 20px;
  }

  .empty { color: var(--text-dim); font-size: 11px; padding: 12px; letter-spacing: 1px; }
`;

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt   = (n) => n?.toFixed(2) ?? "—";
const fmtK  = (n) => n != null ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—";
const sign  = (n) => n >= 0 ? "+" : "";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div style={{ color: "var(--text-dim)", fontSize: 10, marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `$${p.value.toLocaleString()}` : "—"}
        </div>
      ))}
    </div>
  );
};

// ── Panels ────────────────────────────────────────────────────────────────────

function AccountHeader({ account, lastUpdate, onSettings }) {
  return (
    <div className="header">
      <span className="header-title">TERMINAL<span className="blink">_</span></span>
      {account ? (
        <>
          {[
            ["Equity",         account.equity],
            ["Portfolio",      account.portfolio_value],
            ["Buying Power",   account.buying_power],
            ["Cash",           account.cash],
          ].map(([label, val]) => (
            <div className="header-stat" key={label}>
              <span className="header-stat-label">{label}</span>
              <span className="header-stat-value">{fmtK(val)}</span>
            </div>
          ))}
          {lastUpdate && <span className="last-update">UPD {lastUpdate}</span>}
          <div className={`market-badge ${account.market_open ? "open" : "closed"}`} style={{ marginLeft: "auto" }}>
            {account.market_open ? "● MKT OPEN" : "● MKT CLOSED"}
          </div>
        </>
      ) : (
        <span className="loading" style={{ fontSize: 13, height: "auto" }}>
          CONNECTING<span className="blink">_</span>
        </span>
      )}
      <button className="cmd-btn" style={{ marginLeft: account ? "8px" : "auto" }} onClick={onSettings}>
        ⚙ CFG
      </button>
    </div>
  );
}

function PortfolioPanel({ positions, loading }) {
  return (
    <div className="panel">
      <div className="panel-title">▸ PORTFOLIO</div>
      <div className="panel-scroll">
        {loading && <div className="loading" style={{ fontSize: 14 }}>LOADING<span className="blink">_</span></div>}
        {!loading && positions.length === 0 && <div className="empty">// NO OPEN POSITIONS</div>}
        {!loading && positions.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>SYM</th><th>QTY</th><th>AVG</th><th>PRICE</th>
                <th>VALUE</th><th>P/L</th><th>%</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const cls = p.pl >= 0 ? "profit" : "loss";
                return (
                  <tr key={p.symbol}>
                    <td><span className="sym">{p.symbol}</span></td>
                    <td>{p.quantity}</td>
                    <td className="neutral">${fmt(p.avg_price)}</td>
                    <td>${fmt(p.current_price)}</td>
                    <td>{fmtK(p.market_value)}</td>
                    <td className={cls}>{sign(p.pl)}${fmt(Math.abs(p.pl))}</td>
                    <td className={cls}>{sign(p.pl_pct)}{fmt(p.pl_pct)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function OrdersPanel({ orders, loading }) {
  return (
    <div className="panel">
      <div className="panel-title">▸ ORDER HISTORY</div>
      <div className="panel-scroll">
        {loading && <div className="loading" style={{ fontSize: 14 }}>LOADING<span className="blink">_</span></div>}
        {!loading && orders.length === 0 && <div className="empty">// NO ORDERS</div>}
        {!loading && orders.length > 0 && (
          <>
            <div className="order-row hdr">
              <span>ID</span><span>SYM</span><span>TYPE</span>
              <span>QTY</span><span>PRICE</span><span>STATUS</span><span>TIME</span>
            </div>
            {orders.slice(0, 30).map((o) => (
              <div className="order-row" key={o.id}>
                <span className="neutral">#{o.id}</span>
                <span className="sym" style={{ fontSize: 12 }}>{o.symbol}</span>
                <span><span className={`badge ${o.trade_type}`}>{o.trade_type.toUpperCase()}</span></span>
                <span>{o.quantity}</span>
                <span>${fmt(o.price)}</span>
                <span className={`badge ${o.status}`}>{o.status}</span>
                <span className="neutral" style={{ fontSize: 11 }}>{o.timestamp.slice(11)}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function ChartsPanel({ chartData, loading }) {
  return (
    <div className="charts-panel">
      <div className="panel-title" style={{ borderBottom: "1px solid var(--border)" }}>▸ CHARTS</div>
      <div className="charts-inner">

        {/* Portfolio vs SPY */}
        <div className="chart-block">
          <div className="chart-label">Portfolio vs SPY (20d)</div>
          {loading || !chartData ? (
            <div className="loading" style={{ fontSize: 13, flex: 1 }}>
              {loading ? <>LOADING<span className="blink">_</span></> : "NO DATA"}
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={72}>
                <LineChart data={chartData.portfolio?.map((p, i) => ({
                  date: p.date,
                  portfolio: p.value,
                  spy: chartData.spy?.[i]?.value,
                }))}>
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="portfolio" stroke="var(--accent)"  dot={false} strokeWidth={1.5} name="Portfolio" />
                  <Line type="monotone" dataKey="spy"       stroke="var(--warn)"   dot={false} strokeWidth={1}   name="SPY" strokeDasharray="3 3" />
                </LineChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", gap: 16, fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>
                <span style={{ color: "var(--accent)" }}>── Portfolio</span>
                <span style={{ color: "var(--warn)" }}>- - SPY</span>
              </div>
            </>
          )}
        </div>

        {/* First stock chart */}
        <div className="chart-block">
          <div className="chart-label">
            {chartData?.stocks && Object.keys(chartData.stocks)[0]
              ? `${Object.keys(chartData.stocks)[0]} — 20d price`
              : "Stock Price (20d)"}
          </div>
          {loading || !chartData ? (
            <div className="loading" style={{ fontSize: 13, flex: 1 }}>
              {loading ? <>LOADING<span className="blink">_</span></> : "NO DATA"}
            </div>
          ) : (() => {
            const sym  = Object.keys(chartData.stocks || {})[0];
            const data = chartData.stocks?.[sym] || [];
            if (!data.length) return <div className="empty">// NO STOCK DATA</div>;
            const first = data[0]?.close;
            return (
              <ResponsiveContainer width="100%" height={72}>
                <LineChart data={data}>
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip content={<CustomTooltip />} formatter={(v) => [`$${v}`, sym]} />
                  <ReferenceLine y={first} stroke="var(--accent3)" strokeDasharray="2 2" />
                  <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={1.5} name={sym} />
                </LineChart>
              </ResponsiveContainer>
            );
          })()}
        </div>

      </div>
    </div>
  );
}

// ── Trade Modal ───────────────────────────────────────────────────────────────

function TradeModal({ mode, onClose, onSuccess }) {
  const [symbol,   setSymbol]   = useState("");
  const [quantity, setQuantity] = useState("");
  const [quote,    setQuote]    = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [err,      setErr]      = useState("");
  const symRef = useRef();

  useEffect(() => { symRef.current?.focus(); }, []);

  const fetchQuote = useCallback(async (sym) => {
    if (!sym) { setQuote(null); return; }
    try {
      const r = await fetch(`${API}/quote/${sym}`);
      const d = await r.json();
      if (d.price) setQuote(d.price);
    } catch { setQuote(null); }
  }, []);

  const handleSubmit = async () => {
    setErr("");
    if (!symbol || !quantity) { setErr("Symbol and quantity required."); return; }
    setLoading(true);
    try {
      const res  = await fetch(`${API}/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, quantity: parseInt(quantity) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Order failed");
      onSuccess(data.message);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  const est = quote && quantity ? (quote * parseInt(quantity || 0)).toFixed(2) : null;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">{mode === "buy" ? "▸ BUY ORDER" : "▸ SELL ORDER"}</div>
        <div className="field">
          <label>Symbol</label>
          <input ref={symRef} value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onBlur={() => fetchQuote(symbol)}
            onKeyDown={(e) => e.key === "Enter" && fetchQuote(symbol)}
            placeholder="AAPL" maxLength={6} />
        </div>
        {quote && <div className="live-quote">${quote.toFixed(2)}</div>}
        <div className="field">
          <label>Quantity</label>
          <input value={quantity}
            onChange={(e) => setQuantity(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            placeholder="1" type="number" min="1" />
        </div>
        {est && <div className="modal-preview">EST. {mode === "buy" ? "COST" : "PROCEEDS"}: ${parseFloat(est).toLocaleString()}</div>}
        {err && <div className="modal-error">✗ {err}</div>}
        <div className="modal-actions">
          <button className="btn-cancel" onClick={onClose}>CANCEL</button>
          <button className="btn-confirm" onClick={handleSubmit} disabled={loading}>
            {loading ? "SENDING_" : `CONFIRM ${mode.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Quote Modal ───────────────────────────────────────────────────────────────

function QuoteModal({ onClose }) {
  const [symbol,  setSymbol]  = useState("");
  const [quote,   setQuote]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const inputRef = useRef();

  useEffect(() => { inputRef.current?.focus(); }, []);

  const fetchQuote = async () => {
    if (!symbol) return;
    setLoading(true); setQuote(null); setHistory([]);
    try {
      const [qRes, hRes] = await Promise.all([
        fetch(`${API}/quote/${symbol}`),
        fetch(`${API}/chart/${symbol}?days=30`),
      ]);
      const q = await qRes.json();
      const h = await hRes.json();
      if (q.price) setQuote(q.price);
      if (Array.isArray(h)) setHistory(h);
    } catch {}
    setLoading(false);
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 500 }}>
        <div className="modal-title">▸ QUOTE</div>
        <div className="field" style={{ display: "flex", gap: 8 }}>
          <input ref={inputRef} value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && fetchQuote()}
            placeholder="SYMBOL" maxLength={6} style={{ flex: 1 }} />
          <button className="cmd-btn" onClick={fetchQuote}>FETCH</button>
        </div>
        {loading && <div className="loading" style={{ height: 60, fontSize: 13 }}>LOADING<span className="blink">_</span></div>}
        {quote && !loading && (
          <>
            <div className="live-quote">${quote.toFixed(2)}</div>
            {history.length > 0 && (
              <ResponsiveContainer width="100%" height={80}>
                <LineChart data={history}>
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip content={<CustomTooltip />} formatter={(v) => [`$${v}`, symbol]} />
                  <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            )}
            <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>30-DAY HISTORY</div>
          </>
        )}
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn-cancel" onClick={onClose}>CLOSE</button>
        </div>
      </div>
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────────

const REFRESH_MS = 15000;

function Dashboard() {
  const [account,    setAccount]    = useState(null);
  const [positions,  setPositions]  = useState([]);
  const [orders,     setOrders]     = useState([]);
  const [chartData,  setChartData]  = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [modal,      setModal]      = useState(null); // "buy"|"sell"|"quote"|"settings"|null
  const [flash,      setFlash]      = useState({ msg: "", err: false });

  const showFlash = (msg, isErr = false) => {
    setFlash({ msg, err: isErr });
    setTimeout(() => setFlash({ msg: "", err: false }), 4000);
  };

  const fetchAll = useCallback(async () => {
    try {
      const [acct, pos, ord, chart] = await Promise.all([
        fetch(`${API}/account`).then((r)  => r.json()),
        fetch(`${API}/portfolio`).then((r) => r.json()),
        fetch(`${API}/orders`).then((r)   => r.json()),
        fetch(`${API}/chart`).then((r)    => r.json()),
      ]);
      setAccount(acct);
      setPositions(Array.isArray(pos)  ? pos  : []);
      setOrders(Array.isArray(ord)     ? ord  : []);
      setChartData(chart);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch (e) {
      showFlash(`Connection error: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleTradeSuccess = (msg) => {
    setModal(null);
    showFlash(msg);
    setTimeout(fetchAll, 1500);
  };

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <AccountHeader account={account} lastUpdate={lastUpdate} onSettings={() => setModal("settings")} />
        <PortfolioPanel positions={positions} loading={loading} />
        <OrdersPanel    orders={orders}       loading={loading} />
        <ChartsPanel    chartData={chartData} loading={loading} />

        <div className="statusbar">
          <button className="cmd-btn" onClick={() => setModal("buy")}>[ B ] BUY</button>
          <button className="cmd-btn" onClick={() => setModal("sell")}>[ S ] SELL</button>
          <button className="cmd-btn" onClick={() => setModal("quote")}>[ Q ] QUOTE</button>
          <button className="cmd-btn" onClick={fetchAll}>[ R ] REFRESH</button>
          {flash.msg && (
            <span className={`flash-msg ${flash.err ? "err" : ""}`}>
              {flash.err ? "✗" : "✓"} {flash.msg}
            </span>
          )}
          <span style={{ marginLeft: "auto", color: "var(--text-dim)", fontSize: 10, letterSpacing: 2 }}>
            AUTO-REFRESH 15s
          </span>
        </div>
      </div>

      {(modal === "buy" || modal === "sell") && (
        <TradeModal mode={modal} onClose={() => setModal(null)} onSuccess={handleTradeSuccess} />
      )}
      {modal === "quote" && <QuoteModal onClose={() => setModal(null)} />}
      {modal === "settings" && <SettingsPanel onClose={() => setModal(null)} />}
    </>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <Dashboard />
    </ThemeProvider>
  );
}