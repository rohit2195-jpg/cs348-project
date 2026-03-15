// PortfolioPanel.jsx — Left panel: current holdings with live P/L
import { fmt, fmtK, sign } from './helpers';

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

export default PortfolioPanel;