// ChartsPanel.jsx — Bottom panel: portfolio vs SPY + per-stock sparkline
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { CustomTooltip } from './helpers';

function ChartsPanel({ chartData, loading }) {
  const firstSymbol = chartData?.stocks && Object.keys(chartData.stocks)[0]
    ? Object.keys(chartData.stocks)[0]
    : null;

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
              <ResponsiveContainer width="100%" height={84}>
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
              <div className="chart-legend">
                <span style={{ color: "var(--accent)" }}>── Portfolio</span>
                <span style={{ color: "var(--warn)" }}>- - SPY</span>
              </div>
            </>
          )}
        </div>

        {/* First stock chart */}
        <div className="chart-block">
          <div className="chart-label">
            {firstSymbol
              ? `${firstSymbol} — 20d price`
              : "Stock Price (20d)"}
          </div>
          {loading || !chartData ? (
            <div className="loading" style={{ fontSize: 13, flex: 1 }}>
              {loading ? <>LOADING<span className="blink">_</span></> : "NO DATA"}
            </div>
          ) : (() => {
            const sym  = firstSymbol;
            const data = chartData.stocks?.[sym] || [];
            if (!data.length) return <div className="empty">// NO STOCK DATA</div>;
            const first = data[0]?.close;
            return (
              <>
                <ResponsiveContainer width="100%" height={84}>
                  <LineChart data={data}>
                    <XAxis dataKey="date" hide />
                    <YAxis hide domain={["auto", "auto"]} />
                    <Tooltip content={<CustomTooltip />} formatter={(v) => [`$${v}`, sym]} />
                    <ReferenceLine y={first} stroke="var(--accent3)" strokeDasharray="2 2" />
                    <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={1.5} name={sym} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="chart-legend">
                  <span style={{ color: "var(--accent)" }}>── {sym}</span>
                  <span style={{ color: "var(--accent3)" }}>- - OPENING BASE</span>
                </div>
              </>
            );
          })()}
        </div>

      </div>
    </div>
  );
}

export default ChartsPanel;
