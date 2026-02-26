"""
trading.py — Alpaca API wrapper
Handles order execution, live quotes, and historical data for charts.
All chart data methods return plain dicts/lists so they can be
consumed by both the terminal UI and a future React frontend.
"""

import os
import dotenv
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest,
    StockBarsRequest,
)
from alpaca.data.timeframe import TimeFrame

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
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
    quote = data_client.get_stock_latest_quote(req)
    return float(quote[symbol.upper()].ask_price)


def get_latest_prices(symbols: list) -> dict:
    """Batch fetch prices for multiple symbols. Returns {symbol: price}."""
    if not symbols:
        return {}
    req = StockLatestQuoteRequest(symbol_or_symbols=[s.upper() for s in symbols])
    quotes = data_client.get_stock_latest_quote(req)
    return {sym: float(q.ask_price) for sym, q in quotes.items()}


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
    end = datetime.now()
    start = end - timedelta(days=days + 7)  # buffer for weekends/holidays

    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
    )
    bars = data_client.get_stock_bars(req)
    result = []
    for bar in bars[symbol.upper()]:
        result.append({
            "date": bar.timestamp.strftime("%Y-%m-%d"),
            "close": round(float(bar.close), 2),
        })
    return result[-days:]


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