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
import { apiFetch, apiJson } from './Config';

const REFRESH_MS = 15000;

export default function Dashboard({ user, onLogout }) {
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [modal, setModal] = useState(null);
  const [flash, setFlash] = useState({ msg: "", err: false });
  const [wlAlerts, setWlAlerts] = useState(0);
  const [shortcutOpenedAt, setShortcutOpenedAt] = useState(0);
  const shortcutOpenedModal = useRef(false);
  const handleAuthFailure = useCallback(() => {
    setModal(null);
    setAccount(null);
    setPositions([]);
    setOrders([]);
    setChartData(null);
    setWlAlerts(0);
    onLogout();
  }, [onLogout]);

  const showFlash = useCallback((msg, isErr = false) => {
    setFlash({ msg, err: isErr });
    setTimeout(() => setFlash({ msg: "", err: false }), 4000);
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const [acct, pos, ord, chart] = await Promise.all([
        apiJson("/account"),
        apiJson("/portfolio"),
        apiJson("/orders"),
        apiJson("/chart"),
      ]);
      setAccount(acct);
      setPositions(Array.isArray(pos) ? pos : []);
      setOrders(Array.isArray(ord) ? ord : []);
      setChartData(chart);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch (e) {
      if (e?.status === 401) {
        handleAuthFailure();
        return;
      }
      showFlash(`Connection error: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }, [handleAuthFailure, showFlash]);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  useEffect(() => {
    const checkAlerts = async () => {
      try {
        const data = await apiJson("/watchlist/alerts");
        setWlAlerts(Array.isArray(data) ? data.length : 0);
      } catch (e) {
        if (e?.status === 401) {
          handleAuthFailure();
          return;
        }
        setWlAlerts(0);
      }
    };
    checkAlerts();
    const id = setInterval(checkAlerts, 30000);
    return () => clearInterval(id);
  }, [handleAuthFailure]);

  useEffect(() => {
    const handler = (e) => {
      const key = e.key.toLowerCase();
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
        default:
          break;
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

  const handleTradeSuccess = useCallback((msg) => {
    setModal(null);
    showFlash(msg, false);
    setTimeout(fetchAll, 500);
  }, [fetchAll, showFlash]);

  const handleLogout = useCallback(async () => {
    try {
      await apiFetch("/logout", { method: "POST" });
    } finally {
      onLogout();
    }
  }, [onLogout]);

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <AccountHeader
          account={account}
          lastUpdate={lastUpdate}
          onSettings={() => setModal("settings")}
          user={user}
          onLogout={handleLogout}
        />

        <PortfolioPanel positions={positions} loading={loading} />
        <OrdersPanel orders={orders} loading={loading} />
        <div className="lower-panel">
          <ChartsPanel chartData={chartData} loading={loading} />

          <div className="statusbar">
            <div className="statusbar-left">
              <span className="status-label">COMMAND DECK</span>
              <button className={`cmd-btn ${modal === 'buy' ? 'active' : ''}`} onClick={() => setModal("buy")}>
                <span className="cmd-shortcut">[B]</span>BUY
              </button>
              <button className={`cmd-btn ${modal === 'sell' ? 'active' : ''}`} onClick={() => setModal("sell")}>
                <span className="cmd-shortcut">[S]</span>SELL
              </button>
              <button className={`cmd-btn ${modal === 'quote' ? 'active' : ''}`} onClick={() => setModal("quote")}>
                <span className="cmd-shortcut">[Q]</span>QUOTE
              </button>
              <button className="cmd-btn" onClick={fetchAll}>
                <span className="cmd-shortcut">[R]</span>REFRESH
              </button>
              <button className={`cmd-btn ${modal === 'report' ? 'active' : ''}`} onClick={() => setModal("report")}>
                <span className="cmd-shortcut">[F]</span>FILTER
              </button>
              <button
                className={`cmd-btn cmd-btn-watch ${modal === 'watchlist' ? 'active' : ''}`}
                onClick={() => setModal("watchlist")}
              >
                <span className="cmd-shortcut">[W]</span>WATCH
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
      {modal === "quote" && <QuoteModal shortcutOpenedAt={shortcutOpenedAt} onClose={() => setModal(null)} />}
      {modal === "settings" && <SettingsPanel onClose={() => setModal(null)} />}
      {modal === "watchlist" && (
        <WatchlistPanel
          onClose={async () => {
            setModal(null);
            try {
              const data = await apiJson("/watchlist/alerts");
              setWlAlerts(Array.isArray(data) ? data.length : 0);
            } catch (e) {
              if (e?.status === 401) {
                handleAuthFailure();
              }
            }
          }}
        />
      )}
      {modal === "report" && <ReportPanel onClose={() => setModal(null)} />}
    </>
  );
}
