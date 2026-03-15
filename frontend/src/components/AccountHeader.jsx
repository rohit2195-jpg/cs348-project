// AccountHeader.jsx — Top bar: equity stats, market status, settings button
import { fmtK } from './helpers';

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

export default AccountHeader;