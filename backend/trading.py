"""
trading.py — Alpaca API wrapper
Handles order execution, live quotes, and historical data for charts.
All chart data methods return plain dicts/lists so they can be
consumed by both the terminal UI and a future React frontend.
"""

import os
import dotenv
from datetime import datetime, timedelta, timezone
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest,
    StockBarsRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from validation import normalize_symbol

dotenv.load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)


# ── Account ──────────────────────────────────────────────────────────────────

def get_account():
    return trading_client.get_account()


def is_market_open() -> bool:
    return trading_client.get_clock().is_open


# ── Quotes ───────────────────────────────────────────────────────────────────

def get_latest_price(symbol: str) -> float:
    """
    Fetch latest price. Falls back to bid_price when ask_price is 0 (outside hours).
    Raises ValueError with a clear message for invalid symbols.
    """
    sym = normalize_symbol(symbol)
    try:
        req   = StockLatestQuoteRequest(symbol_or_symbols=sym, feed=DataFeed.IEX)
        quote = data_client.get_stock_latest_quote(req)
        q     = quote[sym]
        price = float(q.ask_price) or float(q.bid_price)
        if price == 0:
            raise ValueError(f"No price data for '{sym}'. Market may be closed or symbol unrecognised.")
        return price
    except KeyError:
        raise ValueError(f"Symbol '{sym}' not found on Alpaca. Check the ticker (e.g. AAPL not APPL).")


def get_latest_prices(symbols: list) -> dict:
    """Batch fetch prices for multiple symbols. Returns {symbol: price}."""
    if not symbols:
        return {}
    syms   = [normalize_symbol(s) for s in symbols]
    req    = StockLatestQuoteRequest(symbol_or_symbols=syms, feed=DataFeed.IEX)
    quotes = data_client.get_stock_latest_quote(req)
    result = {}
    for sym, q in quotes.items():
        price = float(q.ask_price) or float(q.bid_price)
        result[sym] = price
    return result


# ── Positions ────────────────────────────────────────────────────────────────

def get_alpaca_positions():
    return trading_client.get_all_positions()


# ── Orders ───────────────────────────────────────────────────────────────────

def buy_stock(symbol: str, quantity: int):
    order = MarketOrderRequest(
        symbol=symbol.upper(),
        qty=quantity,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    return trading_client.submit_order(order)


def sell_stock(symbol: str, quantity: int):
    order = MarketOrderRequest(
        symbol=symbol.upper(),
        qty=quantity,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    return trading_client.submit_order(order)


def cancel_all_orders():
    return trading_client.cancel_orders()


# ── Historical Data (for charts) ──────────────────────────────────────────────

def get_price_history(symbol: str, days: int = 30) -> list:
    """
    Return daily closing prices for a symbol over the last N days.

    Returns list of {"date": "YYYY-MM-DD", "close": float}
    — same shape expected by Recharts/Chart.js on the React side.
    """
    sym = normalize_symbol(symbol)

    # Alpaca requires timezone-aware datetimes
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 7)  # buffer for weekends/holidays

    # Try IEX first (free tier), fall back to default SIP feed.
    # BarSet supports direct key access (bars[sym]) not .get() — use try/except.
    def _fetch(feed=None):
        kwargs = dict(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start, end=end)
        if feed:
            kwargs["feed"] = feed
        req  = StockBarsRequest(**kwargs)
        bars = data_client.get_stock_bars(req)
        try:
            data = bars[sym]
            return list(data) if data else []
        except (KeyError, TypeError):
            return []

    raw = []
    try:
        raw = _fetch(DataFeed.IEX)
    except Exception:
        pass

    if not raw:
        try:
            raw = _fetch()          # retry without feed restriction (SIP)
        except Exception as e:
            raise ValueError(f"Could not fetch data for '{sym}': {e}")

    if not raw:
        raise ValueError(f"No historical data available for '{sym}'. Market may be closed or symbol invalid.")

    result = []
    for bar in raw:
        result.append({
            "date":  bar.timestamp.strftime("%Y-%m-%d"),
            "close": round(float(bar.close), 2),
        })
    return result[-days:]


def get_daily_bars_between(symbol: str, start: datetime, end: datetime) -> list[dict]:
    """
    Returns daily bars between two datetimes, inclusive of available bars.
    Used for post-trade/post-signal evaluation.
    """
    sym = normalize_symbol(symbol)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    def _fetch(feed=None):
        kwargs = dict(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start, end=end)
        if feed:
            kwargs["feed"] = feed
        req  = StockBarsRequest(**kwargs)
        bars = data_client.get_stock_bars(req)
        try:
            data = bars[sym]
            return list(data) if data else []
        except (KeyError, TypeError):
            return []

    raw = []
    try:
        raw = _fetch(DataFeed.IEX)
    except Exception:
        pass
    if not raw:
        raw = _fetch()

    return [
        {
            "date":      bar.timestamp.strftime("%Y-%m-%d"),
            "timestamp": bar.timestamp,
            "close":     round(float(bar.close), 4),
        }
        for bar in raw
    ]


def get_spy_history(days: int = 30) -> list:
    """SPY (S&P 500 ETF) daily closes as benchmark. Same shape as get_price_history."""
    return get_price_history("SPY", days)


def get_portfolio_vs_spy(symbols_with_purchase: list, days: int = 30) -> dict:
    """
    Compare portfolio performance vs SPY.

    symbols_with_purchase: list of {
        "symbol": str, "purchasePrice": float,
        "quantity": int, "purchaseDate": str
    }

    Returns React-ready dict:
    {
        "portfolio": [{"date": str, "value": float}, ...],
        "spy":       [{"date": str, "value": float}, ...],  # normalized to portfolio start
        "stocks":    {symbol: [{"date": str, "close": float}, ...]}
    }
    """
    if not symbols_with_purchase:
        return {"portfolio": [], "spy": [], "stocks": {}}

    all_symbols = [p["symbol"] for p in symbols_with_purchase] + ["SPY"]
    histories = {}
    for sym in all_symbols:
        try:
            histories[sym] = get_price_history(sym, days)
        except Exception:
            histories[sym] = []

    spy_data = histories.pop("SPY", [])

    date_set = set()
    for data in histories.values():
        for d in data:
            date_set.add(d["date"])
    dates = sorted(date_set)

    price_map = {}
    for sym, data in histories.items():
        price_map[sym] = {d["date"]: d["close"] for d in data}

    portfolio_series = []
    for date in dates:
        total = 0.0
        for p in symbols_with_purchase:
            sym = p["symbol"]
            if date in price_map.get(sym, {}):
                total += price_map[sym][date] * p["quantity"]
            else:
                known = [v for d, v in sorted(price_map.get(sym, {}).items()) if d <= date]
                if known:
                    total += known[-1] * p["quantity"]
        portfolio_series.append({"date": date, "value": round(total, 2)})

    spy_lookup = {d["date"]: d["close"] for d in spy_data}
    start_portfolio = portfolio_series[0]["value"] if portfolio_series else 1
    start_spy = spy_lookup.get(dates[0], 1) if dates else 1
    spy_normalized = []
    for date in dates:
        if date in spy_lookup:
            spy_normalized.append({
                "date": date,
                "value": round(spy_lookup[date] / start_spy * start_portfolio, 2),
            })

    return {
        "portfolio": portfolio_series,
        "spy": spy_normalized,
        "stocks": histories,
    }


# ── Order status polling ───────────────────────────────────────────────────────

def get_order(alpaca_order_id: str):
    """Fetch a single order from Alpaca by its ID."""
    return trading_client.get_order_by_id(alpaca_order_id)


def wait_for_fill(alpaca_order_id: str, timeout: int = 10) -> dict:
    """
    Poll Alpaca until the order is filled or canceled/rejected.
    Returns a dict: {"status": str, "filled_price": float or None}

    timeout: max seconds to wait. For paper trading, fills are near-instant
    during market hours. Outside hours, DAY orders stay pending.
    """
    import time

    # Terminal states — stop polling when we hit one of these
    FILLED    = "filled"
    DONE      = {"canceled", "rejected", "expired", "done_for_day"}

    deadline = time.time() + timeout
    while time.time() < deadline:
        order  = trading_client.get_order_by_id(alpaca_order_id)
        status = order.status.value  # always use .value to get the string

        if status == FILLED:
            return {
                "status":       "filled",
                "filled_price": float(order.filled_avg_price),
                "filled_qty":   int(float(order.filled_qty)),
            }
        if status in DONE:
            return {
                "status":       status,
                "filled_price": None,
                "filled_qty":   0,
            }
        # still pending/new/accepted — wait and retry
        time.sleep(1)

    # timed out — return current state without updating portfolio
    order  = trading_client.get_order_by_id(alpaca_order_id)
    status = order.status.value
    return {
        "status":       status,
        "filled_price": float(order.filled_avg_price) if order.filled_avg_price else None,
        "filled_qty":   int(float(order.filled_qty)) if order.filled_qty else 0,
    }
