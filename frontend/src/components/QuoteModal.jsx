// QuoteModal.jsx — Live price lookup + 30-day history chart
import { useState, useEffect, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { CustomTooltip } from './helpers';

import { apiJson } from "./Config.js";

function QuoteModal({ onClose, shortcutOpenedAt = 0 }) {
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
      const [q, h] = await Promise.all([
        apiJson(`/quote/${symbol}`),
        apiJson(`/chart/${symbol}?days=30`),
      ]);
      if (q.price) setQuote(q.price);
      if (Array.isArray(h)) setHistory(h);
    } catch {
      setQuote(null);
      setHistory([]);
    }
    setLoading(false);
  };

  const shouldIgnoreShortcutEcho = (e) => (
    shortcutOpenedAt
    && Date.now() - shortcutOpenedAt < 250
    && e.key.length === 1
    && !e.ctrlKey
    && !e.metaKey
    && !e.altKey
    && e.currentTarget.value === ""
  );

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 500 }}>
        <div className="modal-title">▸ QUOTE</div>
        <div className="field quote-search-row">
          <input ref={inputRef} value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (shouldIgnoreShortcutEcho(e)) {
                e.preventDefault();
                return;
              }
              if (e.key === "Enter") fetchQuote();
            }}
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

export default QuoteModal;
