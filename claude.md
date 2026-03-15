# CLAUDE.md — Project Context

## Project Overview
A stock trading simulator built on top of **Alpaca's paper trading API**. Functions like Investopedia's simulator — real market data, fake money. The project has two UIs: a legacy terminal (curses) UI and the current React frontend. All trades are executed through Alpaca and also stored in a local SQLite database.

The end goal is to add an **LLM agent layer** on top of this to automate trading decisions. The current phase is purely the human-facing trading interface.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React (Vite), Recharts for charts |
| Backend | Flask (Python), port 5000 |
| Database | SQLite via SQLAlchemy ORM |
| Trading API | Alpaca paper trading (`alpaca-py`) |
| Data Feed | Alpaca IEX feed (free tier), falls back to SIP |

---

## File Structure

```
backend/
  server.py       — Flask API, all endpoints, background order settler
  trading.py      — Alpaca API wrapper (orders, quotes, historical data)
  database.py     — SQLAlchemy models + all DB read/write functions
  .env            — ALPACA_API_KEY, ALPACA_SECRET_KEY

frontend/
  src/
    App.jsx       — Main dashboard, all panels, modals, auto-refresh
    Settings.jsx  — Theme context/provider + settings drawer

legacy/
  cli.py          — Original curses-based terminal dashboard (still works)
```

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/account` | Alpaca account summary (equity, buying power, cash) |
| GET | `/api/portfolio` | Local DB positions with live prices + P/L injected |
| GET | `/api/orders` | Full order history from local DB |
| GET | `/api/quote/<symbol>` | Live price for a single symbol |
| GET | `/api/chart` | Portfolio vs SPY (20d), per-stock sparklines |
| GET | `/api/chart/<symbol>` | 30d price history for a single symbol |
| POST | `/api/buy` | `{ symbol, quantity }` — place buy order |
| POST | `/api/sell` | `{ symbol, quantity }` — place sell order |
| POST | `/api/sync` | `{ order_id, alpaca_order_id, trade_type, symbol, quantity }` — settle a pending order |

---

## Database Schema

### `Portfolio`
| Column | Type | Notes |
|--------|------|-------|
| symbol | String PK | Ticker e.g. "AAPL" |
| purchasePrice | Float | Weighted average buy price |
| quantity | Integer | Current shares held |
| purchaseDate | String | YYYY-MM-DD of first purchase |

### `order_history`
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| symbol | String | Ticker |
| price | Float | Quote price at time of order |
| quantity | Integer | Shares |
| timestamp | DateTime | UTC |
| status | Enum | `pending`, `filled`, `canceled` |
| trade_type | Enum | `buy`, `sell` |
| alpaca_order_id | String | Alpaca UUID — used by background settler |

---

## Order Lifecycle

```
User places order
  → Price validated (must be > 0, must get live quote)
  → Order saved to DB as "pending" with alpaca_order_id
  → Submitted to Alpaca paper trading
  → wait_for_fill() polls Alpaca for up to 10s
      ├── filled    → DB updated to "filled", portfolio updated with real fill price
      ├── canceled  → DB updated to "canceled", portfolio unchanged
      └── timeout   → Returns pending:true to frontend

If pending:
  → Frontend polls /api/sync every 5s for up to 2 min
  → Background settler (server-side) also checks every 30s automatically
  → When Alpaca confirms fill → portfolio updated, order marked filled
  → Works even if browser is closed (server must be running)
```

**Key rule:** Portfolio is only updated after a confirmed fill. Never on order submission.

---

## CORS Setup
`flask-cors` is NOT used. CORS is handled manually via:
- `@app.after_request` — injects headers on every response
- `@app.before_request` — returns 204 for all OPTIONS preflights

`use_reloader=False` in `app.run()` — prevents Chrome CORS issues caused by Flask's debug reloader spawning a child process.

---

## Alpaca Configuration
- Paper trading only (`paper=True`)
- Data feed: IEX (free tier) with automatic fallback to SIP
- Market hours: orders placed after hours sit as `pending` until next open
- DAY orders expire as `done_for_day` if not filled by market close

---

## Frontend Architecture

### Dashboard Layout (CSS Grid)
```
┌─────────────────────────────────────┐
│  Header: account stats + market     │  48px
├──────────────────┬──────────────────┤
│  Portfolio       │  Order History   │  flex 1
├──────────────────┴──────────────────┤
│  Charts: portfolio vs SPY + stock   │  120px
├─────────────────────────────────────┤
│  Status bar: [B]uy [S]ell [Q]uote   │  32px
└─────────────────────────────────────┘
```

### Auto-refresh
- Full data refresh every **15 seconds** via `setInterval`
- Pending order sync polls every **5 seconds** for up to 2 minutes

### Themes (Settings.jsx)
6 themes via CSS variables injected on `<html>` — switching is instant, no re-render.
- Dark: Green Phosphor, White Phosphor, Amber Phosphor
- Light: Paper, Bloomberg, Slate
- Stored in `localStorage` as `terminal_theme`
- Light themes suppress CRT scanline/vignette via `html.light-theme` class

---

## Known Behaviors / Things to Keep in Mind

- **$0.00 price bug** was fixed — price fetch failure is now a hard error before order creation, not a silent fallback
- **IEX feed returns empty outside market hours** — chart endpoint falls back to SIP automatically
- **`alpaca_order_id` column** was added to `order_history` after initial schema creation. If using an existing DB, run:
  ```bash
  python3 -c "
  import sqlite3; conn = sqlite3.connect('my_database.db')
  conn.execute('ALTER TABLE order_history ADD COLUMN alpaca_order_id VARCHAR(64)')
  conn.commit()
  "
  ```
- **Port 5000 on Mac** conflicts with AirPlay Receiver — disable in System Settings or switch Flask to port 8000 and update `const API` in App.jsx

---

## Running the Project

```bash
# Backend
cd backend
pip install flask alpaca-py sqlalchemy python-dotenv
python server.py

# Frontend
cd frontend
npm install
npm run dev        # runs on http://localhost:5173
```

`.env` file (in backend/):
```
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
```

---

## Planned Next Steps
- Add LLM agent layer to automate trading decisions
- Agent will use `StockAnalysis` and `NewsSummary` DB tables (already defined in schema) for sentiment/reasoning storage
- `trading.get_portfolio_vs_spy()` returns React-ready data shape — already wired for the frontend charts