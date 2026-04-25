// AccountHeader.jsx — Top bar: equity stats, market status, settings button
import { fmtK } from './helpers';

function AccountHeader({ account, lastUpdate, onSettings, user, onLogout }) {
  return (
    <div className="header">
      <div className="header-main">
        <span className="header-title">TERMINAL<span className="blink">_</span></span>
        {account ? (
          <>
            <div className={`market-badge ${account.market_open ? "open" : "closed"}`}>
              {account.market_open ? "● MKT OPEN" : "● MKT CLOSED"}
            </div>
            {lastUpdate && <span className="last-update">UPD {lastUpdate}</span>}
          </>
        ) : (
          <span className="loading" style={{ fontSize: 13, height: "auto" }}>
            CONNECTING<span className="blink">_</span>
          </span>
        )}
      </div>

      {account && (
        <div className="header-stats">
          {[
            ["Equity", account.equity],
            ["Portfolio", account.portfolio_value],
            ["Buying Power", account.buying_power],
            ["Cash", account.cash],
            ["User", user?.username || account.username],
          ].map(([label, val]) => (
            <div className="header-stat" key={label}>
              <span className="header-stat-label">{label}</span>
              <span className="header-stat-value">
                {typeof val === "number" ? fmtK(val) : val}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="header-actions">
        <button className="cmd-btn" onClick={onSettings}>
          ⚙ CFG
        </button>
        {account && (
          <button className="cmd-btn" onClick={onLogout}>
            EXIT
          </button>
        )}
      </div>
    </div>
  );
}

export default AccountHeader;
