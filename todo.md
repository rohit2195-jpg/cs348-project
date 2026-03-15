# TODO.md — Project Improvements

## 🔴 High Priority / Core Trading Features

### Portfolio & Positions
- [ ] **Fractional shares** — Alpaca supports fractional buying, currently only whole shares allowed
- [ ] **Multiple positions per symbol** — currently upserts average price, but should track individual lots for tax/FIFO purposes
- [ ] **Short selling** — add ability to short a stock (sell shares you don't own)
- [ ] **Position limits** — max % of portfolio in a single stock (risk management)
- [ ] **Stop-loss / take-profit orders** — automatically sell when price hits a threshold
- [ ] **Limit orders** — buy/sell at a specific price instead of market price only

### Order Management
- [ ] **Cancel pending orders** — UI button to cancel a pending order on Alpaca and update local DB
- [ ] **Order confirmation page** — show full order details before submitting (estimated cost, buying power impact)
- [ ] **Order types** — market, limit, stop, stop-limit — currently only market orders
- [ ] **Extended hours trading** — Alpaca supports pre/post market, currently DAY only
- [ ] **Partial fills** — handle when only some shares of an order are filled

### Account
- [ ] **Starting balance display** — show how much you started with vs current value
- [ ] **Reset portfolio** — wipe all positions and start fresh (like Investopedia's reset)
- [ ] **Multiple portfolios** — run different strategies side by side
- [ ] **Deposit/withdraw simulation** — add/remove virtual cash

---

## 🟡 Medium Priority / Better Data & Charts

### Charts & Visualization
- [ ] **Intraday charts** — 1min/5min/15min/1hr timeframes, not just daily
- [ ] **Candlestick charts** — OHLC candles instead of just close price line
- [ ] **Volume bars** — show trading volume below price chart
- [ ] **More chart timeframes** — 1W, 1M, 3M, 6M, 1Y, 5Y selectable in UI
- [ ] **Technical indicators** — SMA, EMA, RSI, MACD, Bollinger Bands overlaid on chart
- [ ] **Portfolio allocation pie chart** — visual breakdown of holdings by weight
- [ ] **P/L over time chart** — daily portfolio value history stored in DB
- [ ] **Benchmark comparison** — compare portfolio vs SPY, QQQ, DIA selectable

### Market Data
- [ ] **Watchlist** — track stocks you don't own but want to monitor
- [ ] **Market movers** — top gainers/losers for the day
- [ ] **Sector performance** — show how different sectors are doing
- [ ] **Earnings calendar** — show upcoming earnings dates for held stocks
- [ ] **Dividend tracking** — track dividend payments for held stocks
- [ ] **52-week high/low** — show in portfolio table

---

## 🟢 Nice to Have / Polish

### UI / UX
- [ ] **Search/autocomplete for tickers** — type company name and get ticker suggestions
- [ ] **Mobile responsive layout** — current grid doesn't work well on small screens
- [ ] **Keyboard shortcuts** — B to buy, S to sell, Q to quote without clicking buttons
- [ ] **Toast notifications** — better than the current flash bar for fill confirmations
- [ ] **Dark/light mode toggle in header** — one-click instead of going into settings
- [ ] **Sortable columns** — click table headers to sort by P/L, value, etc.
- [ ] **Transaction history filters** — filter orders by symbol, date range, status, type
- [ ] **Export to CSV** — download portfolio or order history as spreadsheet

### Performance Tracking (Investopedia-style)
- [ ] **Total return %** — overall portfolio return since inception
- [ ] **Annualized return** — normalize return to per-year basis
- [ ] **Best/worst trade** — track which individual trades made/lost the most
- [ ] **Win rate** — % of closed trades that were profitable
- [ ] **Sharpe ratio** — risk-adjusted return metric
- [ ] **Max drawdown** — largest peak-to-trough decline
- [ ] **Leaderboard** — if multiple users, rank portfolios by return

### Backend & Data
- [ ] **Store daily portfolio snapshots** — save total value each day for P/L history chart
- [ ] **Cache market data** — avoid hitting Alpaca on every request, cache quotes for 15s
- [ ] **WebSockets for live prices** — push price updates to frontend instead of polling
- [ ] **Rate limit handling** — graceful backoff when Alpaca API limits are hit
- [ ] **Symbol search endpoint** — `/api/search?q=apple` returns matching tickers
- [ ] **News feed per stock** — fetch recent headlines for held symbols

---

## 🤖 LLM Agent Layer (Next Major Phase)

> The DB already has `StockAnalysis` and `NewsSummary` tables ready for this.

- [ ] **News summarization** — agent reads news and writes summary to `NewsSummary` table
- [ ] **Sentiment scoring** — agent rates stock sentiment -10 to +10, stores in `StockAnalysis`
- [ ] **Buy/sell recommendations** — agent suggests trades with reasoning
- [ ] **Automated execution** — agent places trades autonomously within risk limits
- [ ] **Portfolio rebalancing** — agent suggests/executes rebalancing based on targets
- [ ] **Earnings reaction** — agent monitors earnings and reacts to beats/misses
- [ ] **Natural language queries** — "how is my portfolio doing?" answered in plain English
- [ ] **Agent activity log** — show what the agent is thinking/doing in a separate panel
- [ ] **Human approval mode** — agent proposes trades, human approves before execution
- [ ] **Backtesting** — run the agent strategy against historical data

---

## 🐛 Technical Debt / Known Issues

- [ ] **`alpaca_order_id` migration** — existing DBs need manual `ALTER TABLE` (documented in CLAUDE.md)
- [ ] **No authentication** — anyone who can reach port 5000 can trade; add API key or session auth before deploying
- [ ] **SQLite concurrency** — background settler + Flask requests can cause write conflicts under load; migrate to PostgreSQL for production
- [ ] **No input sanitization on symbol** — basic alpha check exists but no validation against real ticker list
- [ ] **Error state in UI** — API errors show in flash bar only; add persistent error panel for repeated failures
- [ ] **`use_reloader=False`** — means code changes need manual server restart; fine for now but annoying in dev
- [ ] **Chart only shows first holding** — second chart panel hardcoded to `stocks[0]`; should be selectable