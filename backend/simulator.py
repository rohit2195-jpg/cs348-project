"""
simulator.py
Simple historical replay over stored feature snapshots and verdicts.

This is a first replay layer, not a full institutional backtester. It reuses
the dated packets the live pipeline writes and simulates deterministic entries
and exits with next-available daily close fills.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging

import trading as t
from database import (
    get_actionable_verdicts_for_date,
    get_feature_snapshots_between_dates,
    insert_simulation_position,
    insert_simulation_run,
    update_simulation_run,
)

logger = logging.getLogger(__name__)

MAX_NEW_BUYS_PER_DAY = 3
MIN_CONVICTION = 0.68


def _group_by_run_date(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["run_date"]].append(row)
    return grouped


def _load_price_cache(symbols: set[str], start_date: str, end_date: str) -> dict[str, list[dict]]:
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc) - timedelta(days=5)
    end = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=10)
    cache = {}
    for symbol in symbols:
        try:
            cache[symbol] = t.get_daily_bars_between(symbol, start, end)
        except Exception as exc:
            logger.warning("[simulator] failed loading bars for %s: %s", symbol, exc)
            cache[symbol] = []
    return cache


def _first_close_on_or_after(bars: list[dict], target_date: str) -> dict | None:
    for bar in bars:
        if bar["date"] >= target_date:
            return bar
    return None


def _first_close_after(bars: list[dict], target_date: str) -> dict | None:
    for bar in bars:
        if bar["date"] > target_date:
            return bar
    return None


def simulate_recorded_strategy(start_date: str, end_date: str, initial_cash: float = 100_000.0) -> dict:
    snapshots = get_feature_snapshots_between_dates(start_date, end_date)
    if not snapshots:
        return {"error": "No feature snapshots available for the requested period."}

    run_dates = sorted({row["run_date"] for row in snapshots})
    snapshots_by_date = _group_by_run_date(snapshots)
    universe_symbols = {row["ticker"] for row in snapshots}
    verdicts_by_date = {date: get_actionable_verdicts_for_date(date, min_conviction=MIN_CONVICTION) for date in run_dates}
    universe_symbols.update(v["ticker"] for rows in verdicts_by_date.values() for v in rows)
    price_cache = _load_price_cache(universe_symbols, start_date, end_date)

    sim_id = insert_simulation_run(start_date, end_date, initial_cash)
    cash = initial_cash
    positions: dict[str, dict] = {}
    equity_curve = []

    for run_date in run_dates:
        verdicts = verdicts_by_date.get(run_date, [])
        sell_verdicts = [v for v in verdicts if "SELL" in v["verdict"]]
        buy_verdicts = [v for v in verdicts if "BUY" in v["verdict"]][:MAX_NEW_BUYS_PER_DAY]

        for verdict in sell_verdicts:
            position = positions.get(verdict["ticker"])
            if not position:
                continue
            fill_bar = _first_close_after(price_cache.get(verdict["ticker"], []), run_date)
            if not fill_bar:
                continue
            proceeds = fill_bar["close"] * position["quantity"]
            cash += proceeds
            del positions[verdict["ticker"]]
            insert_simulation_position(
                sim_id, run_date, verdict["ticker"], "SELL", position["quantity"], fill_bar["close"],
                cash_after=round(cash, 2), equity_after=round(cash, 2), notes=f"Replay sell {verdict['verdict']}",
            )

        if buy_verdicts:
            allocation = cash / len(buy_verdicts)
            for verdict in buy_verdicts:
                if verdict["ticker"] in positions:
                    continue
                fill_bar = _first_close_after(price_cache.get(verdict["ticker"], []), run_date)
                if not fill_bar or fill_bar["close"] <= 0:
                    continue
                quantity = int(allocation // fill_bar["close"])
                if quantity < 1:
                    continue
                cost = quantity * fill_bar["close"]
                cash -= cost
                positions[verdict["ticker"]] = {"quantity": quantity, "entry_price": fill_bar["close"]}
                insert_simulation_position(
                    sim_id, run_date, verdict["ticker"], "BUY", quantity, fill_bar["close"],
                    cash_after=round(cash, 2), equity_after=round(cash, 2), notes=f"Replay buy {verdict['verdict']}",
                )

        equity = cash
        for ticker, position in positions.items():
            mark_bar = _first_close_on_or_after(price_cache.get(ticker, []), run_date)
            if mark_bar:
                equity += position["quantity"] * mark_bar["close"]
        equity_curve.append({"date": run_date, "equity": round(equity, 2), "cash": round(cash, 2), "positions": len(positions)})

    ending_equity = equity_curve[-1]["equity"] if equity_curve else initial_cash
    max_equity = initial_cash
    max_drawdown = 0.0
    for point in equity_curve:
        max_equity = max(max_equity, point["equity"])
        if max_equity:
            drawdown = (max_equity - point["equity"]) / max_equity
            max_drawdown = max(max_drawdown, drawdown)

    metrics = {
        "days": len(run_dates),
        "total_return_pct": round(((ending_equity - initial_cash) / initial_cash) * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 3),
        "ending_positions": len(positions),
        "equity_curve": equity_curve,
    }
    update_simulation_run(sim_id, ending_cash=round(cash, 2), ending_equity=round(ending_equity, 2), metrics=metrics)
    return {"simulation_run_id": sim_id, **metrics}
