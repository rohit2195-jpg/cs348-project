// Dashboard.jsx — Main state container: data fetching, auto-refresh, keyboard shortcuts
import { useState, useEffect, useCallback, useRef } from 'react';
import { SettingsPanel } from '../Settings';
import ReportPanel from './ReportPanel';
import WatchlistPanel from './WatchListPanel';
import AccountHeader from './AccountHeader';
import PortfolioPanel from './PortfolioPanel';
import OrdersPanel from './OrdersPanel';
import ChartsPanel from './ChartsPanel';
import TradeModal from './TradeModal';
import QuoteModal from './QuoteModal';
import { styles } from './styles';

import { API } from "./Config";
const REFRESH_MS   = 15000;

export default function Dashboard() {
  const [account,    setAccount]    = useState(null);
  const [positions,  setPositions]  = useState([]);
  const [orders,     setOrders]     = useState([]);
  const [chartData,  setChartData]  = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [modal,      setModal]      = useState(null); // "buy"|"sell"|"quote"|"settings"|null
  const [flash,      setFlash]      = useState({ msg: "", err: false });
  const [wlAlerts,   setWlAlerts]   = useState(0);  // unread watchlist alerts
  const [shortcutOpenedAt, setShortcutOpenedAt] = useState(0);
  const shortcutOpenedModal = useRef(false);

  // ── Flash message ───────────────────────────────────────────────────────────
  const showFlash = useCallback((msg, isErr = false) => {
    setFlash({ msg, err: isErr });
    setTimeout(() => setFlash({ msg: "", err: false }), 4000);
  }, []);

  // ── Data fetch ──────────────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    try {
      const [acct, pos, ord, chart] = await Promise.all([
        fetch(`${API}/account`).then(r  => r.json()),
        fetch(`${API}/portfolio`).then(r => r.json()),
        fetch(`${API}/orders`).then(r   => r.json()),
        fetch(`${API}/chart`).then(r    => r.json()),
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
  }, [showFlash]);

  // ── Auto-refresh ─────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  // Poll watchlist alerts independently (30s) — lightweight, just a count
  useEffect(() => {
    const checkAlerts = async () => {
      try {
        const res  = await fetch(`${API}/watchlist/alerts`);
        const data = await res.json();
        setWlAlerts(Array.isArray(data) ? data.length : 0);
      } catch {}
    };
    checkAlerts();
    const id = setInterval(checkAlerts, 30000);
    return () => clearInterval(id);
  }, []);

  // ── Keyboard shortcuts ───────────────────────────────────────────────────────
  // B = buy  |  S = sell  |  Q = quote  |  R = refresh  |  Esc = close modal
  // Shortcuts are disabled when any modal is open (user is typing in inputs)
  useEffect(() => {
    const handler = (e) => {
      const key = e.key.toLowerCase();

      // Don't fire shortcuts if user is typing in an input/textarea
      const tag = document.activeElement?.tagName;
      const isEditable = document.activeElement?.isContentEditable;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || isEditable) return;

      switch (key) {
        case 'b':
        case 's':
        case 'q':
        case 'w':
        case 'f':
          if (!modal) {
            e.preventDefault();
            shortcutOpenedModal.current = true;
            setShortcutOpenedAt(Date.now());
            setModal(
              key === 'b' ? 'buy'
              : key === 's' ? 'sell'
              : key === 'q' ? 'quote'
              : key === 'w' ? 'watchlist'
              : 'report'
            );
          }
          break;
        case 'r':
          if (!modal) {
            e.preventDefault();
            fetchAll();
          }
          break;
        case 'escape':
          shortcutOpenedModal.current = false;
          setModal(null);
          break;
        default: break;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [modal, fetchAll]);

  useEffect(() => {
    if (!modal || !shortcutOpenedModal.current) return;

    const clearShortcutFlag = () => {
      shortcutOpenedModal.current = false;
      window.removeEventListener('keyup', clearShortcutFlag, true);
    };

    window.addEventListener('keyup', clearShortcutFlag, true);
    return () => window.removeEventListener('keyup', clearShortcutFlag, true);
  }, [modal]);

  // ── Trade success handler (pending poll) ────────────────────────────────────
  const handleTradeSuccess = useCallback((msg, pendingInfo = null) => {
    setModal(null);
    showFlash(msg, false);

    if (pendingInfo) {
      showFlash("⏳ Order pending — will auto-update when filled");
      let attempts = 0;
      const maxAttempts = 24;

      const syncPayload = {
        order_id:        pendingInfo.order_id,
        alpaca_order_id: pendingInfo.alpaca_order_id,
        trade_type:      pendingInfo.trade_type,
        symbol:          pendingInfo.symbol,
        quantity:        pendingInfo.quantity,
      };

      const poll = setInterval(async () => {
        attempts++;
        try {
          const res  = await fetch(`${API}/sync`, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(syncPayload),
          });
          const data = await res.json();
          if (data.settled) {
            clearInterval(poll);
            if (data.status === "filled") {
              showFlash(`✓ ${pendingInfo.symbol} filled @ $${data.filled_price?.toFixed(2)}`);
            } else {
              showFlash(`Order ${data.status}. Portfolio unchanged.`, true);
            }
            fetchAll();
          } else if (attempts >= maxAttempts) {
            clearInterval(poll);
            showFlash("Order still pending after 2min. Refresh manually.", true);
          }
        } catch (e) {
          console.error("[sync] poll error:", e);
          if (attempts >= maxAttempts) clearInterval(poll);
        }
      }, 5000);
    } else {
      setTimeout(fetchAll, 1500);
    }
  }, [showFlash, fetchAll]);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{styles}</style>
      <div className="app">

        <AccountHeader
          account={account}
          lastUpdate={lastUpdate}
          onSettings={() => setModal("settings")}
        />

        <PortfolioPanel positions={positions} loading={loading} />
        <OrdersPanel    orders={orders}       loading={loading} />
        <div className="lower-panel">
          <ChartsPanel chartData={chartData} loading={loading} />

          <div className="statusbar">
            <div className="statusbar-left">
              <span className="status-label">COMMAND DECK</span>
              <button className={`cmd-btn ${modal === 'buy'   ? 'active' : ''}`} onClick={() => setModal("buy")}>
                [B] BUY
              </button>
              <button className={`cmd-btn ${modal === 'sell'  ? 'active' : ''}`} onClick={() => setModal("sell")}>
                [S] SELL
              </button>
              <button className={`cmd-btn ${modal === 'quote' ? 'active' : ''}`} onClick={() => setModal("quote")}>
                [Q] QUOTE
              </button>
              <button className="cmd-btn" onClick={fetchAll}>
                [R] REFRESH
              </button>
              <button className={`cmd-btn ${modal === 'report' ? 'active' : ''}`} onClick={() => setModal("report")}>
                [F] FILTER
              </button>
              <button
                className={`cmd-btn cmd-btn-watch ${modal === 'watchlist' ? 'active' : ''}`}
                onClick={() => setModal("watchlist")}
              >
                [W] WATCH
                {wlAlerts > 0 && <span className="watch-alert">{wlAlerts}</span>}
              </button>
            </div>

            <div className="statusbar-right">
              {flash.msg ? (
                <span className={`flash-msg ${flash.err ? "err" : ""}`}>
                  {flash.err ? "✗" : "✓"} {flash.msg}
                </span>
              ) : (
                <span className="flash-msg idle">SYSTEM NOMINAL</span>
              )}

              <span className="kbd-hint">B · S · Q · R · F · W · ESC</span>
            </div>
          </div>
        </div>

      </div>

      {(modal === "buy" || modal === "sell") && (
        <TradeModal
          mode={modal}
          shortcutOpenedAt={shortcutOpenedAt}
          onClose={() => setModal(null)}
          onSuccess={handleTradeSuccess}
        />
      )}
      {modal === "quote" && (
        <QuoteModal shortcutOpenedAt={shortcutOpenedAt} onClose={() => setModal(null)} />
      )}
      {modal === "settings" && (
        <SettingsPanel onClose={() => setModal(null)} />
      )}
      {modal === "report" && (
        <ReportPanel onClose={() => setModal(null)} />
      )}
      {modal === "watchlist" && (
        <WatchlistPanel onClose={() => {
          setModal(null);
          // Refresh alert count after closing (user may have dismissed alerts)
          fetch(`${API}/watchlist/alerts`)
            .then(r => r.json())
            .then(d => setWlAlerts(Array.isArray(d) ? d.length : 0))
            .catch(() => {});
        }} />
      )}
    </>
  );
}
