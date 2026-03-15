// WatchlistPanel.jsx — Watchlist: track stocks, set price targets, get alerts
import { useState, useEffect, useCallback } from 'react';
import { API } from './Config.js';

const fmt  = (n) => (n ?? 0).toFixed(2);
const fmtK = (n) => n != null
  ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : "—";

// ── Add / Edit form ───────────────────────────────────────────────────────────
function WatchlistForm({ onAdd, loading }) {
  const [symbol,    setSymbol]    = useState("");
  const [target,    setTarget]    = useState("");
  const [direction, setDirection] = useState("below");
  const [notes,     setNotes]     = useState("");
  const [err,       setErr]       = useState("");

  const handleSubmit = async () => {
    setErr("");
    if (!symbol) { setErr("Symbol is required"); return; }
    const result = await onAdd({
      symbol,
      target_price:     target !== "" ? parseFloat(target) : null,
      target_direction: target !== "" ? direction : null,
      notes,
    });
    if (result.error) { setErr(result.error); return; }
    setSymbol(""); setTarget(""); setNotes(""); setDirection("below");
  };

  return (
    <div className="wl-form">
      <div className="wl-form-title">ADD TO WATCHLIST</div>
      <div className="wl-form-row">
        <div className="wl-field">
          <label>SYMBOL</label>
          <input
            className="wl-input" value={symbol} maxLength={5}
            placeholder="AAPL"
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
          />
        </div>
        <div className="wl-field" style={{ flex: 1.5 }}>
          <label>TARGET PRICE (optional)</label>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              className="wl-input" type="number" value={target}
              placeholder="e.g. 180.00" style={{ flex: 1 }}
              onChange={e => setTarget(e.target.value)}
            />
            <select
              className="wl-select" value={direction}
              onChange={e => setDirection(e.target.value)}
              disabled={target === ""}
            >
              <option value="below">Falls below</option>
              <option value="above">Rises above</option>
            </select>
          </div>
        </div>
        <div className="wl-field" style={{ flex: 2 }}>
          <label>NOTES (optional)</label>
          <input
            className="wl-input" value={notes} maxLength={200}
            placeholder="Reason for watching..."
            onChange={e => setNotes(e.target.value)}
          />
        </div>
        <div className="wl-field" style={{ alignSelf: "flex-end" }}>
          <button className="wl-btn-add" onClick={handleSubmit} disabled={loading}>
            {loading ? "ADDING_" : "+ ADD"}
          </button>
        </div>
      </div>
      {err && <div className="wl-err">✗ {err}</div>}
    </div>
  );
}

// ── Single watchlist row ──────────────────────────────────────────────────────
function WatchlistRow({ entry, onRemove, onDismiss, onEdit }) {
  const [editing, setEditing]       = useState(false);
  const [editTarget, setEditTarget] = useState(entry.target_price ?? "");
  const [editDir,    setEditDir]    = useState(entry.target_direction ?? "below");
  const [editNotes,  setEditNotes]  = useState(entry.notes ?? "");

  const isTriggered  = entry.triggered === 1;
  const isDismissed  = entry.triggered === 2;
  const hasTarget    = entry.target_price != null;
  const price        = entry.current_price;

  const distancePct  = entry.target_distance_pct;
  const approaching  = hasTarget && !isTriggered && distancePct != null &&
    Math.abs(distancePct) < 5; // within 5% of target

  const rowClass = isTriggered ? "wl-row wl-row-triggered"
                 : approaching ? "wl-row wl-row-approaching"
                 : "wl-row";

  const saveEdit = () => {
    onEdit(entry.symbol, {
      target_price:     editTarget !== "" ? parseFloat(editTarget) : null,
      target_direction: editTarget !== "" ? editDir : null,
      notes:            editNotes,
    });
    setEditing(false);
  };

  return (
    <>
      <tr className={rowClass}>
        {/* Symbol */}
        <td className="wl-sym">
          {entry.symbol}
          {isTriggered && <span className="wl-alert-dot" title="Target hit!">●</span>}
        </td>

        {/* Current price */}
        <td className="wl-price">
          {price != null ? fmtK(price) : <span className="wl-dim">—</span>}
        </td>

        {/* Target */}
        <td>
          {hasTarget ? (
            <span className={isTriggered ? "wl-triggered-text" : approaching ? "wl-approaching-text" : ""}>
              {entry.target_direction === "below" ? "↓" : "↑"} {fmtK(entry.target_price)}
            </span>
          ) : (
            <span className="wl-dim">Watch only</span>
          )}
        </td>

        {/* Distance */}
        <td>
          {isTriggered ? (
            <span className="wl-triggered-text" style={{ fontSize: 10 }}>
              HIT @ {fmtK(entry.triggered_price)}<br/>
              <span className="wl-dim">{entry.triggered_at}</span>
            </span>
          ) : hasTarget && distancePct != null ? (
            <span className={Math.abs(distancePct) < 5
              ? "wl-approaching-text"
              : distancePct < 0 ? "wl-profit" : "wl-loss"}>
              {distancePct >= 0 ? "+" : ""}{fmt(distancePct)}%
            </span>
          ) : <span className="wl-dim">—</span>}
        </td>

        {/* Notes */}
        <td className="wl-notes-cell">
          <span className="wl-dim" style={{ fontSize: 11 }}>{entry.notes || ""}</span>
        </td>

        {/* Added */}
        <td className="wl-dim" style={{ fontSize: 10 }}>{entry.added_date}</td>

        {/* Actions */}
        <td>
          <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
            {isTriggered && (
              <button className="wl-btn-sm wl-btn-dismiss" onClick={() => onDismiss(entry.symbol)}>
                DISMISS
              </button>
            )}
            <button className="wl-btn-sm wl-btn-edit" onClick={() => setEditing(!editing)}>
              {editing ? "CANCEL" : "EDIT"}
            </button>
            <button className="wl-btn-sm wl-btn-remove" onClick={() => onRemove(entry.symbol)}>
              ✕
            </button>
          </div>
        </td>
      </tr>

      {/* Inline edit row */}
      {editing && (
        <tr className="wl-edit-row">
          <td colSpan={7}>
            <div className="wl-edit-form">
              <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                <div className="wl-field">
                  <label>TARGET PRICE</label>
                  <input className="wl-input" type="number" value={editTarget}
                    placeholder="Remove to watch-only"
                    onChange={e => setEditTarget(e.target.value)} style={{ width: 110 }} />
                </div>
                <div className="wl-field">
                  <label>DIRECTION</label>
                  <select className="wl-select" value={editDir}
                    onChange={e => setEditDir(e.target.value)} disabled={editTarget === ""}>
                    <option value="below">Falls below</option>
                    <option value="above">Rises above</option>
                  </select>
                </div>
                <div className="wl-field" style={{ flex: 1, minWidth: 160 }}>
                  <label>NOTES</label>
                  <input className="wl-input" value={editNotes} maxLength={200}
                    onChange={e => setEditNotes(e.target.value)} style={{ width: "100%" }} />
                </div>
                <button className="wl-btn-add" onClick={saveEdit}>SAVE</button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Main WatchlistPanel ───────────────────────────────────────────────────────
export default function WatchlistPanel({ onClose }) {
  const [entries,   setEntries]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [addLoading,setAddLoading]= useState(false);
  const [flash,     setFlash]     = useState({ msg: "", err: false });
  const [sortBy,    setSortBy]    = useState("added"); // added|symbol|price|distance

  const showFlash = (msg, isErr = false) => {
    setFlash({ msg, err: isErr });
    setTimeout(() => setFlash({ msg: "", err: false }), 3500);
  };

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const fetchEntries = useCallback(async () => {
    try {
      const res  = await fetch(`${API}/watchlist`);
      const data = await res.json();
      setEntries(Array.isArray(data) ? data : []);
    } catch (e) {
      showFlash("Failed to load watchlist", true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
    // Refresh prices every 15s while panel is open
    const id = setInterval(fetchEntries, 15000);
    return () => clearInterval(id);
  }, [fetchEntries]);

  // ── Add ────────────────────────────────────────────────────────────────────
  const handleAdd = async (payload) => {
    setAddLoading(true);
    try {
      const res  = await fetch(`${API}/watchlist`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) return { error: data.error };
      showFlash(`✓ ${payload.symbol} added to watchlist`);
      fetchEntries();
      return {};
    } catch (e) {
      return { error: e.message };
    } finally {
      setAddLoading(false);
    }
  };

  // ── Remove ─────────────────────────────────────────────────────────────────
  const handleRemove = async (symbol) => {
    try {
      await fetch(`${API}/watchlist/${symbol}`, { method: "DELETE" });
      setEntries(prev => prev.filter(e => e.symbol !== symbol));
      showFlash(`${symbol} removed`);
    } catch (e) {
      showFlash("Remove failed", true);
    }
  };

  // ── Dismiss alert ──────────────────────────────────────────────────────────
  const handleDismiss = async (symbol) => {
    try {
      await fetch(`${API}/watchlist/${symbol}/dismiss`, { method: "POST" });
      fetchEntries();
    } catch {}
  };

  // ── Edit ───────────────────────────────────────────────────────────────────
  const handleEdit = async (symbol, payload) => {
    try {
      const res  = await fetch(`${API}/watchlist/${symbol}`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) { showFlash(data.error, true); return; }
      showFlash(`✓ ${symbol} updated`);
      fetchEntries();
    } catch (e) {
      showFlash("Update failed", true);
    }
  };

  // ── Sorted entries ─────────────────────────────────────────────────────────
  const sorted = [...entries].sort((a, b) => {
    // Always show triggered alerts at top
    if (a.triggered === 1 && b.triggered !== 1) return -1;
    if (b.triggered === 1 && a.triggered !== 1) return  1;
    switch (sortBy) {
      case "symbol":   return a.symbol.localeCompare(b.symbol);
      case "price":    return (b.current_price ?? 0) - (a.current_price ?? 0);
      case "distance": return Math.abs(a.target_distance_pct ?? 999) - Math.abs(b.target_distance_pct ?? 999);
      default:         return new Date(b.added_date) - new Date(a.added_date);
    }
  });

  const alertCount    = entries.filter(e => e.triggered === 1).length;
  const approachCount = entries.filter(e =>
    e.triggered === 0 && e.target_distance_pct != null && Math.abs(e.target_distance_pct) < 5
  ).length;

  return (
    <>
      <style>{wlStyles}</style>
      <div className="wl-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="wl-panel">

          {/* Header */}
          <div className="wl-header">
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span className="wl-title">WATCHLIST<span className="blink">_</span></span>
              {alertCount > 0 && (
                <span className="wl-badge-alert">{alertCount} ALERT{alertCount > 1 ? "S" : ""}</span>
              )}
              {approachCount > 0 && alertCount === 0 && (
                <span className="wl-badge-approaching">{approachCount} NEAR TARGET</span>
              )}
              <span className="wl-dim" style={{ fontSize: 11 }}>
                {entries.length} watching · refreshes every 15s
              </span>
            </div>
            <button className="settings-close" onClick={onClose}>[X] CLOSE</button>
          </div>

          <div className="wl-body">
            {/* Add form */}
            <WatchlistForm onAdd={handleAdd} loading={addLoading} />

            {/* Flash */}
            {flash.msg && (
              <div className={`wl-flash ${flash.err ? "wl-flash-err" : ""}`}>
                {flash.msg}
              </div>
            )}

            {/* Table */}
            {loading ? (
              <div className="wl-loading">LOADING<span className="blink">_</span></div>
            ) : entries.length === 0 ? (
              <div className="wl-empty">
                // YOUR WATCHLIST IS EMPTY<br />
                <span style={{ fontSize: 11, opacity: 0.6 }}>
                  Add symbols above to track prices and set target alerts.
                </span>
              </div>
            ) : (
              <>
                {/* Sort controls */}
                <div className="wl-sort-bar">
                  <span className="wl-dim" style={{ fontSize: 10 }}>SORT BY:</span>
                  {["added","symbol","price","distance"].map(s => (
                    <button
                      key={s} onClick={() => setSortBy(s)}
                      className={`wl-sort-btn ${sortBy === s ? "active" : ""}`}
                    >
                      {s.toUpperCase()}
                    </button>
                  ))}
                </div>

                <table className="wl-table">
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>SYMBOL</th>
                      <th>CURR PRICE</th>
                      <th>TARGET</th>
                      <th>DISTANCE</th>
                      <th style={{ textAlign: "left" }}>NOTES</th>
                      <th>ADDED</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map(entry => (
                      <WatchlistRow
                        key={entry.symbol}
                        entry={entry}
                        onRemove={handleRemove}
                        onDismiss={handleDismiss}
                        onEdit={handleEdit}
                      />
                    ))}
                  </tbody>
                </table>

                {/* Legend */}
                <div className="wl-legend">
                  <span className="wl-triggered-text">● TARGET HIT</span>
                  <span className="wl-approaching-text">● WITHIN 5%</span>
                  <span className="wl-dim">● WATCHING</span>
                </div>
              </>
            )}
          </div>

        </div>
      </div>
    </>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const wlStyles = `
  .wl-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.75);
    z-index: 2000; display: flex; align-items: flex-start;
    justify-content: center; padding: 24px 16px; overflow-y: auto;
  }
  .wl-panel {
    width: 100%; max-width: 960px; background: var(--bg);
    border: 1px solid var(--border); box-shadow: 0 8px 60px rgba(0,0,0,0.6);
    animation: wlIn 0.18s ease-out;
  }
  @keyframes wlIn { from { transform: translateY(-16px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

  .wl-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; border-bottom: 1px solid var(--border); background: var(--panel);
    flex-wrap: wrap; gap: 8px;
  }
  .wl-title {
    font-family: 'VT323', monospace; font-size: 22px; letter-spacing: 3px;
    color: var(--accent); text-shadow: var(--title-shadow);
  }
  .wl-badge-alert {
    font-size: 10px; letter-spacing: 1.5px; padding: 2px 8px;
    background: var(--loss); color: #fff; font-family: 'Share Tech Mono', monospace;
    animation: pulse 1.5s infinite;
  }
  .wl-badge-approaching {
    font-size: 10px; letter-spacing: 1.5px; padding: 2px 8px;
    background: var(--warn); color: #000; font-family: 'Share Tech Mono', monospace;
  }

  .wl-body { padding: 16px 18px; overflow-y: auto; max-height: 74vh; }

  /* Form */
  .wl-form {
    background: var(--panel); border: 1px solid var(--border);
    padding: 14px 16px; margin-bottom: 16px;
  }
  .wl-form-title {
    font-size: 10px; letter-spacing: 2px; color: var(--text-dim);
    text-transform: uppercase; margin-bottom: 10px;
  }
  .wl-form-row { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
  .wl-field { display: flex; flex-direction: column; gap: 4px; min-width: 90px; }
  .wl-field label { font-size: 9px; letter-spacing: 1.5px; color: var(--text-dim); text-transform: uppercase; }
  .wl-input {
    background: transparent; border: 1px solid var(--accent3);
    color: var(--text); font-family: 'Share Tech Mono', monospace;
    font-size: 12px; padding: 5px 8px; outline: none;
    text-transform: uppercase; transition: border-color 0.15s; width: 100%;
  }
  .wl-input:focus { border-color: var(--accent); }
  .wl-input[type=number] { text-transform: none; }
  .wl-select {
    background: var(--bg); border: 1px solid var(--accent3); color: var(--text);
    font-family: 'Share Tech Mono', monospace; font-size: 12px; padding: 5px 8px;
    outline: none; cursor: pointer; transition: border-color 0.15s;
  }
  .wl-select:disabled { opacity: 0.4; cursor: not-allowed; }
  .wl-select:focus { border-color: var(--accent); }
  .wl-btn-add {
    background: var(--dim); border: 1px solid var(--accent); color: var(--accent);
    font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1px;
    padding: 6px 16px; cursor: pointer; transition: all 0.1s; text-transform: uppercase;
    white-space: nowrap;
  }
  .wl-btn-add:hover  { background: var(--accent); color: var(--bg); }
  .wl-btn-add:disabled { opacity: 0.4; cursor: not-allowed; }
  .wl-err { color: var(--loss); font-size: 11px; letter-spacing: 1px; margin-top: 8px; }

  /* Flash */
  .wl-flash { font-size: 11px; letter-spacing: 1px; color: var(--profit); padding: 6px 0; }
  .wl-flash-err { color: var(--loss); }

  /* Sort bar */
  .wl-sort-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 0 10px; border-bottom: 1px solid var(--border); margin-bottom: 6px;
  }
  .wl-sort-btn {
    background: transparent; border: 1px solid var(--border); color: var(--text-dim);
    font-family: 'Share Tech Mono', monospace; font-size: 10px; letter-spacing: 1px;
    padding: 2px 8px; cursor: pointer; transition: all 0.1s;
  }
  .wl-sort-btn:hover, .wl-sort-btn.active {
    border-color: var(--accent2); color: var(--accent2);
  }

  /* Table */
  .wl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .wl-table th {
    font-size: 9px; letter-spacing: 1px; color: var(--text-dim); text-align: right;
    padding: 4px 10px; border-bottom: 1px solid var(--dim); text-transform: uppercase;
  }
  .wl-table th:first-child { text-align: left; }
  .wl-row td {
    padding: 7px 10px; text-align: right;
    border-bottom: 1px solid var(--panel); vertical-align: middle;
  }
  .wl-row td:first-child { text-align: left; }
  .wl-row:hover td { background: var(--panel); }
  .wl-row-triggered td { background: rgba(255,49,49,0.06); }
  .wl-row-triggered:hover td { background: rgba(255,49,49,0.1); }
  .wl-row-approaching td { background: rgba(255,176,0,0.05); }
  .wl-row-approaching:hover td { background: rgba(255,176,0,0.09); }

  /* Edit row */
  .wl-edit-row td { padding: 0; border-bottom: 1px solid var(--border); }
  .wl-edit-form {
    padding: 10px 12px; background: var(--panel);
    border-left: 2px solid var(--accent2);
  }

  /* Cell styles */
  .wl-sym   { color: var(--accent); font-weight: bold; font-size: 14px; }
  .wl-price { font-variant-numeric: tabular-nums; }
  .wl-notes-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
  .wl-dim   { color: var(--text-dim); }
  .wl-profit { color: var(--profit); }
  .wl-loss   { color: var(--loss); }
  .wl-alert-dot { color: var(--loss); margin-left: 5px; font-size: 10px; animation: pulse 1s infinite; }
  .wl-triggered-text  { color: var(--loss); font-weight: bold; }
  .wl-approaching-text { color: var(--warn); font-weight: bold; }

  /* Buttons */
  .wl-btn-sm {
    background: transparent; border: 1px solid var(--border); color: var(--text-dim);
    font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 1px;
    padding: 2px 7px; cursor: pointer; transition: all 0.1s; text-transform: uppercase;
  }
  .wl-btn-dismiss { border-color: var(--loss); color: var(--loss); }
  .wl-btn-dismiss:hover { background: var(--loss); color: var(--bg); }
  .wl-btn-edit:hover { border-color: var(--accent2); color: var(--accent2); }
  .wl-btn-remove:hover { border-color: var(--loss); color: var(--loss); }

  /* Legend + misc */
  .wl-legend {
    display: flex; gap: 16px; padding: 10px 0 2px;
    font-size: 10px; letter-spacing: 1px; border-top: 1px solid var(--border); margin-top: 8px;
  }
  .wl-loading {
    font-family: 'VT323', monospace; font-size: 20px; letter-spacing: 3px;
    color: var(--text-dim); padding: 24px; text-align: center;
  }
  .wl-empty {
    color: var(--text-dim); font-size: 12px; letter-spacing: 1px;
    padding: 24px; text-align: center; line-height: 2;
  }
`;