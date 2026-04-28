# CS348 Trading Simulator

A multi-user trading simulator with a React dashboard and Flask backend. The project uses Alpaca for market data while user accounts, cash balances, positions, order history, and watchlist entries are stored locally in SQLite.

## Link to Project

https://d39xe7wu5kbzn1.cloudfront.net/

## Features

- Multi-user simulated trading
- Portfolio dashboard with current holdings and P/L
- Order history with filterable reports
- Watchlist with target-price alerts
- Portfolio vs. SPY charting
- Local login/register and user-isolated accounts
- Background watchlist polling
- Local SQLite persistence via SQLAlchemy

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite, Recharts |
| Backend | Flask |
| Database | SQLite, SQLAlchemy |
| Market Data API | Alpaca |
| Config | `.env` via `python-dotenv` |

## Project Structure

```text
backend/
  server.py         Flask API entrypoint
  database.py       SQLAlchemy models and DB access layer
  trading.py        Alpaca integration and market-data helpers
  validation.py     Input validation helpers
  my_database.db    Local SQLite database

frontend/
  src/              React application
  package.json      Frontend scripts and dependencies

scripts/
  validate.sh       Project validation entrypoint
```

## Prerequisites

Make sure you have the following installed:

- Python 3.11+ recommended
- Node.js 18+ and npm
- An Alpaca API key for market data

## Environment Setup

Create a `.env` file in `backend/`:

```env
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```

The backend loads this automatically from [backend/trading.py](/Users/rohitsattuluri/Projects/cs348-project/backend/trading.py:23).

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd cs348-project
```

### 2. Set up the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install flask alpaca-py sqlalchemy python-dotenv
```

If your team already committed or shared a backend virtualenv convention, keep using `backend/.venv`, because the validation script looks there automatically.

### 3. Set up the frontend

From the repo root:

```bash
npm --prefix frontend install
```

Or:

```bash
cd frontend
npm install
```

## Running the Project

You need two terminals: one for the backend and one for the frontend.

### Start the backend

```bash
cd backend
source .venv/bin/activate
python server.py
```

Backend default URL:

```text
http://127.0.0.1:5000
```

The Flask app runs on port `5000` in [backend/server.py](/Users/rohitsattuluri/Projects/cs348-project/backend/server.py:1).

### Start the frontend

```bash
cd frontend
npm run dev
```

Frontend default URL:

```text
http://localhost:5173
```

The frontend defaults to the same hostname as the page, so:

- `http://localhost:5173` talks to `http://localhost:5000/api`
- `http://127.0.0.1:5173` talks to `http://127.0.0.1:5000/api`

That keeps cookie-based auth same-site in local development.

See [frontend/src/components/Config.js](/Users/rohitsattuluri/Projects/cs348-project/frontend/src/components/Config.js:1):

```js
const host = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
const defaultApi = `http://${host}:5000/api`;
```

If you change the backend port, set `VITE_API_BASE_URL`.

For deploys, the frontend can also read `VITE_API_BASE_URL` at build time.
See [frontend/.env.example](/Users/rohitsattuluri/Projects/cs348-project/frontend/.env.example:1).

### Migrated test account

If you already had data in the legacy single-user tables, the backend seeds a simulator user on startup:

- username: `testuser`
- password: `testpass123`

That account is only intended to preserve visibility into the old local portfolio, order history, and watchlist after the multi-user cutover.

### SQLite database location

The application uses a local SQLite database:

- `backend/my_database.db`

Tables and indexes are managed by [backend/database.py](/Users/rohitsattuluri/Projects/cs348-project/backend/database.py:1).

## Core API Endpoints

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/session` | Session status |
| `GET` | `/api/account` | Simulated account summary |
| `GET` | `/api/portfolio` | User portfolio with live prices |
| `GET` | `/api/orders` | User order history |
| `GET` | `/api/quote/<symbol>` | Latest quote for one ticker |
| `GET` | `/api/chart` | Portfolio vs. SPY chart data |
| `GET` | `/api/chart/<symbol>` | Historical chart for a ticker |
| `POST` | `/api/register` | Create a local simulator user |
| `POST` | `/api/login` | Log in |
| `POST` | `/api/logout` | Log out |
| `POST` | `/api/buy` | Execute a simulated buy |
| `POST` | `/api/sell` | Execute a simulated sell |
| `GET` | `/api/watchlist` | Watchlist entries |
| `POST` | `/api/watchlist` | Add or update a watchlist entry |

## Order Lifecycle

1. A logged-in user places a buy or sell order from the frontend.
2. The backend validates the symbol and quantity and fetches a live quote from Alpaca.
3. The backend executes the trade locally, updating cash, positions, and order history atomically in SQLite.
4. The dashboard refreshes with the new simulated account state.

Important behavior:

- Portfolio positions and cash update immediately on successful simulated fills.
- The backend runs background checks for watchlist targets.

## Watchlist and Alerts

The watchlist supports:

- adding symbols with optional target prices
- background polling for target hits
- unread triggered alerts

The app now also creates indexes to speed up common order-history and watchlist queries when the backend initializes.

## Troubleshooting

### Backend starts but market-data calls fail

Check:

- your `.env` file exists in `backend/`
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are valid
- your Alpaca credentials have access to stock market data

### Frontend loads but API calls fail

Check:

- backend is running on `127.0.0.1:5000`
- you opened the frontend on the same hostname family as the backend (`localhost` with `localhost`, or `127.0.0.1` with `127.0.0.1`)
- `VITE_API_BASE_URL` matches the backend port if you overrode it
- browser console and backend terminal for request errors

### Python import errors

Make sure you activated the backend virtual environment before running the server:

```bash
cd backend
source .venv/bin/activate
```

Then reinstall dependencies if needed:

```bash
pip install flask alpaca-py sqlalchemy python-dotenv
```

## Contributing

When making changes:

1. Run the validation script before committing.
2. Keep backend and frontend ports in sync.
3. Avoid running multiple backend instances against the same SQLite DB.
4. Prefer updating this README when setup or runtime behavior changes.

## Use of AI in This Project

AI was used for some parts of the coding in this project, mainly to offload repetitive programming tasks and help polish the user interface and frontend experience.

I designed the database structure myself using DB Browser for SQLite. I also wrote the initial database interaction logic for selecting from tables such as `order_history` and `portfolio`, then used AI assistance to refine that code and extend the same patterns to additional tables as the project grew.

Even though I used some AI-assisted coding, I did not rely on its generated output blindly. For each change, I reviewed the code carefully to understand how it would affect the existing application and compared it against the behavior I originally intended. Because I understood the codebase thoroughly, I was able to diagnose and fix issues that came up during testing, including cases where the frontend called the wrong endpoints and where the `portfolio` table was not producing the correct profit values.

## License

Add your project license here if one is intended for the repository.
