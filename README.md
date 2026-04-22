# CS348 Trading Simulator

A stock trading simulator built on top of Alpaca paper trading. The project provides a React dashboard for placing simulated trades with live market data, tracking portfolio performance, viewing order history, and managing a watchlist with price alerts.

Trades are submitted to Alpaca's paper environment, while local application state such as portfolio positions, order history, and watchlist entries is stored in SQLite.

## Features

- Live paper trading through Alpaca
- Portfolio dashboard with current holdings and P/L
- Order history with filterable reports
- Watchlist with target-price alerts
- Portfolio vs. SPY charting
- Background order settlement and watchlist polling
- Local SQLite persistence via SQLAlchemy

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite, Recharts |
| Backend | Flask |
| Database | SQLite, SQLAlchemy |
| Market / Trading API | Alpaca paper trading |
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
- An Alpaca paper trading account

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

The frontend is configured to call the backend at [frontend/src/components/Config.js](/Users/rohitsattuluri/Projects/cs348-project/frontend/src/components/Config.js:5):

```js
export const API = "http://127.0.0.1:5000/api";
```

If you change the backend port, update that file as well.

For deploys, the frontend can also read `VITE_API_BASE_URL` at build time.
See [frontend/.env.example](/Users/rohitsattuluri/Projects/cs348-project/frontend/.env.example:1).

### SQLite database location

The application uses a local SQLite database:

- `backend/my_database.db`

Tables and indexes are managed by [backend/database.py](/Users/rohitsattuluri/Projects/cs348-project/backend/database.py:1).

## Core API Endpoints

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/account` | Alpaca account summary |
| `GET` | `/api/portfolio` | Local portfolio with live prices |
| `GET` | `/api/orders` | Local order history |
| `GET` | `/api/quote/<symbol>` | Latest quote for one ticker |
| `GET` | `/api/chart` | Portfolio vs. SPY chart data |
| `GET` | `/api/chart/<symbol>` | Historical chart for a ticker |
| `POST` | `/api/buy` | Place a paper buy order |
| `POST` | `/api/sell` | Place a paper sell order |
| `POST` | `/api/sync` | Sync pending order status |
| `GET` | `/api/watchlist` | Watchlist entries |
| `POST` | `/api/watchlist` | Add or update a watchlist entry |

## Order Lifecycle

1. A user places a buy or sell order from the frontend.
2. The backend validates the symbol and quantity and fetches a live quote.
3. The order is stored locally in `order_history` as pending.
4. The order is submitted to Alpaca paper trading.
5. The backend attempts to settle it immediately.
6. If it remains pending, the frontend and background server processes continue syncing until it is filled or canceled.

Important behavior:

- Portfolio positions are updated only after a confirmed fill.
- The backend also runs background checks for pending orders and watchlist targets.

## Watchlist and Alerts

The watchlist supports:

- adding symbols with optional target prices
- background polling for target hits
- unread triggered alerts

The app now also creates indexes to speed up common order-history and watchlist queries when the backend initializes.

## Troubleshooting

### Backend starts but Alpaca calls fail

Check:

- your `.env` file exists in `backend/`
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are valid
- you are using Alpaca paper credentials

### Frontend loads but API calls fail

Check:

- backend is running on `127.0.0.1:5000`
- frontend API base URL matches the backend port
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
