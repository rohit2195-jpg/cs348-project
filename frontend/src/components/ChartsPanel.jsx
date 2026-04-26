// ChartsPanel.jsx — Bottom panel: portfolio vs SPY + per-stock sparkline
import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { CustomTooltip } from './helpers';

function ChartsPanel({
  chartData,
  loading,
  collapsed = false,
  onToggle,
  selectedSymbol,
  onSelectSymbol,
  timeframe,
  timeframeOptions,
  onTimeframeChange,
}) {
  const stockSymbols = useMemo(() => Object.keys(chartData?.stocks || {}), [chartData?.stocks]);
  const portfolioData = useMemo(() => {
    const spyByDate = new Map((chartData?.spy || []).map((point) => [point.date, point.value]));

    return (chartData?.portfolio || []).map((point) => ({
      date: point.date,
      portfolio: point.value,
      spy: spyByDate.get(point.date),
    }));
  }, [chartData?.portfolio, chartData?.spy]);

  const summary = loading
    ? 'LOADING'
    : selectedSymbol
      ? `${selectedSymbol} SELECTED`
      : 'NO STOCK DATA';

  return (
    <div className={`charts-panel panel panel-charts ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="panel-title panel-title-bar">
        <span className="panel-title-label">▸ CHARTS</span>
        <span className="panel-summary">{summary}</span>
        <div className="chart-timeframe-group" role="group" aria-label="Chart timeframe">
          {timeframeOptions.map((option) => (
            <button
              key={option}
              type="button"
              className={`chart-timeframe-btn ${timeframe === option ? 'active' : ''}`}
              onClick={() => onTimeframeChange(option)}
              aria-pressed={timeframe === option}
            >
              {option}
            </button>
          ))}
        </div>
        <button type="button" className="panel-toggle" onClick={onToggle} aria-expanded={!collapsed}>
          {collapsed ? 'EXPAND' : 'COLLAPSE'}
        </button>
      </div>
      <div className="charts-inner">

        {/* Portfolio vs SPY */}
        <div className="chart-block">
          <div className="chart-label">Portfolio vs SPY ({timeframe})</div>
          {loading || !chartData ? (
            <div className="loading" style={{ fontSize: 13, flex: 1 }}>
              {loading ? <>LOADING<span className="blink">_</span></> : "NO DATA"}
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={84}>
                <LineChart data={portfolioData}>
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
          <div className="chart-toolbar">
            <div className="chart-label">
              {selectedSymbol
                ? `${selectedSymbol} — ${timeframe} price`
                : `Stock Price (${timeframe})`}
            </div>
            <label className="chart-select-wrap">
              <span className="sr-only">Select holding chart</span>
              <select
                className="chart-select"
                value={selectedSymbol}
                onChange={(e) => onSelectSymbol(e.target.value)}
                disabled={!stockSymbols.length}
              >
                {!stockSymbols.length && <option value="">NO HOLDINGS</option>}
                {stockSymbols.map((symbol) => (
                  <option key={symbol} value={symbol}>{symbol}</option>
                ))}
              </select>
            </label>
          </div>
          {loading || !chartData ? (
            <div className="loading" style={{ fontSize: 13, flex: 1 }}>
              {loading ? <>LOADING<span className="blink">_</span></> : "NO DATA"}
            </div>
          ) : (() => {
            const sym  = selectedSymbol;
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
