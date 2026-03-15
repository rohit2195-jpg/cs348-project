// TradeModal.jsx — Buy / Sell order modal
import { useState, useEffect, useCallback, useRef } from 'react';

import { API } from "./Config.js";

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

      // Always close modal immediately — pending orders show in flash bar
      if (data.pending) {
        onSuccess(data.message, {
          pending:         true,
          order_id:        data.order_id,
          alpaca_order_id: data.alpaca_order_id,
          trade_type:      mode,
          symbol,
          quantity:        parseInt(quantity),
        });
      } else {
        onSuccess(data.message);
      }
    } catch (e) {
      setErr(e.message);
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

export default TradeModal;