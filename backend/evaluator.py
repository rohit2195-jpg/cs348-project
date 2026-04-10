"""
evaluator.py — ex-post evaluation for verdicts and filled trades

This is not a full historical backtester. It is a daily evaluation loop that
scores recent signals and actual executions after 1/3/5 trading-day horizons.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging

import trading as t
from database import (
    get_existing_signal_evaluations,
    get_recent_signal_evaluations,
    get_research_verdicts_for_evaluation,
    get_trade_decisions_for_evaluation,
    insert_signal_evaluation,
)

logger = logging.getLogger(__name__)

EVALUATION_HORIZONS = (1, 3, 5)
LOOKBACK_DAYS = 45
BENCHMARK_TICKER = "SPY"


def _to_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _direction_from_label(label: str) -> str:
    return "BUY" if "BUY" in label.upper() else "SELL"


def _pct_change(reference: float, current: float) -> float:
    if not reference:
        return 0.0
    return ((current - reference) / reference) * 100


def _outcome(thesis_return_pct: float) -> str:
    if thesis_return_pct > 1.0:
        return "win"
    if thesis_return_pct < -1.0:
        return "loss"
    return "flat"


def _load_bar_cache(symbol: str, reference_dt: datetime, cache: dict[str, list[dict]]) -> list[dict]:
    if symbol not in cache:
        start = reference_dt - timedelta(days=3)
        end   = datetime.now(timezone.utc) + timedelta(days=1)
        cache[symbol] = t.get_daily_bars_between(symbol, start, end)
    return cache[symbol]


def _first_bar_on_or_after(bars: list[dict], target_date: str) -> tuple[int, dict] | tuple[None, None]:
    for idx, bar in enumerate(bars):
        if bar["date"] >= target_date:
            return idx, bar
    return None, None


def _bar_by_date_or_after(bars: list[dict], target_date: str) -> dict | None:
    for bar in bars:
        if bar["date"] >= target_date:
            return bar
    return None


def _evaluate_verdicts(existing: set[tuple[int, int]], cache: dict[str, list[dict]]) -> list[dict]:
    inserted = []
    verdicts = get_research_verdicts_for_evaluation(days=LOOKBACK_DAYS)
    for verdict in verdicts:
        source_id = verdict["id"]
        direction = _direction_from_label(verdict["verdict"])
        created_at = _to_datetime(verdict["created_at"])
        bars = _load_bar_cache(verdict["ticker"], created_at, cache)
        ref_idx, ref_bar = _first_bar_on_or_after(bars, created_at.strftime("%Y-%m-%d"))
        if ref_bar is None:
            continue

        spy_bars = _load_bar_cache(BENCHMARK_TICKER, created_at, cache)
        spy_ref  = _bar_by_date_or_after(spy_bars, ref_bar["date"])
        if spy_ref is None:
            continue

        for horizon in EVALUATION_HORIZONS:
            if (source_id, horizon) in existing:
                continue
            eval_idx = ref_idx + horizon
            if eval_idx >= len(bars):
                continue
            eval_bar = bars[eval_idx]
            spy_eval = _bar_by_date_or_after(spy_bars, eval_bar["date"])
            if spy_eval is None:
                continue

            raw_ret = _pct_change(ref_bar["close"], eval_bar["close"])
            bench_ret = _pct_change(spy_ref["close"], spy_eval["close"])
            direction_mult = 1 if direction == "BUY" else -1
            thesis_ret = raw_ret * direction_mult
            excess_ret = thesis_ret - (bench_ret * direction_mult)

            eval_id = insert_signal_evaluation(
                source_type="verdict",
                source_id=source_id,
                ticker=verdict["ticker"],
                direction=direction,
                horizon_days=horizon,
                reference_date=ref_bar["date"],
                reference_price=ref_bar["close"],
                evaluation_date=eval_bar["date"],
                evaluation_price=eval_bar["close"],
                raw_return_pct=round(raw_ret, 3),
                benchmark_return_pct=round(bench_ret, 3),
                thesis_return_pct=round(thesis_ret, 3),
                excess_return_pct=round(excess_ret, 3),
                outcome=_outcome(thesis_ret),
                notes=f"{verdict['verdict']} evaluated against {BENCHMARK_TICKER}",
            )
            inserted.append({"id": eval_id, "source_type": "verdict", "ticker": verdict["ticker"], "horizon": horizon})
    return inserted


def _evaluate_trades(existing: set[tuple[int, int]], cache: dict[str, list[dict]]) -> list[dict]:
    inserted = []
    trades = get_trade_decisions_for_evaluation(days=LOOKBACK_DAYS)
    for trade in trades:
        source_id = trade["id"]
        direction = trade["action"].upper()
        created_at = _to_datetime(trade["created_at"])
        bars = _load_bar_cache(trade["ticker"], created_at, cache)
        start_idx, first_bar = _first_bar_on_or_after(bars, created_at.strftime("%Y-%m-%d"))
        if first_bar is None:
            continue

        spy_bars = _load_bar_cache(BENCHMARK_TICKER, created_at, cache)
        spy_ref  = _bar_by_date_or_after(spy_bars, first_bar["date"])
        if spy_ref is None:
            continue

        for horizon in EVALUATION_HORIZONS:
            if (source_id, horizon) in existing:
                continue
            eval_idx = start_idx + (horizon - 1)
            if eval_idx >= len(bars):
                continue
            eval_bar = bars[eval_idx]
            spy_eval = _bar_by_date_or_after(spy_bars, eval_bar["date"])
            if spy_eval is None:
                continue

            raw_ret = _pct_change(trade["price"], eval_bar["close"])
            bench_ret = _pct_change(spy_ref["close"], spy_eval["close"])
            direction_mult = 1 if direction == "BUY" else -1
            thesis_ret = raw_ret * direction_mult
            excess_ret = thesis_ret - (bench_ret * direction_mult)

            eval_id = insert_signal_evaluation(
                source_type="trade",
                source_id=source_id,
                ticker=trade["ticker"],
                direction=direction,
                horizon_days=horizon,
                reference_date=created_at.strftime("%Y-%m-%d"),
                reference_price=trade["price"],
                evaluation_date=eval_bar["date"],
                evaluation_price=eval_bar["close"],
                raw_return_pct=round(raw_ret, 3),
                benchmark_return_pct=round(bench_ret, 3),
                thesis_return_pct=round(thesis_ret, 3),
                excess_return_pct=round(excess_ret, 3),
                outcome=_outcome(thesis_ret),
                notes=f"Filled {direction} trade evaluated against {BENCHMARK_TICKER}",
            )
            inserted.append({"id": eval_id, "source_type": "trade", "ticker": trade["ticker"], "horizon": horizon})
    return inserted


def run_evaluation_cycle() -> dict:
    """
    Computes any missing 1/3/5-day evaluations for recent verdicts and trades.
    Intended to run once per day before the next trading cycle.
    """
    bar_cache: dict[str, list[dict]] = {}
    verdict_existing = get_existing_signal_evaluations("verdict")
    trade_existing   = get_existing_signal_evaluations("trade")

    verdict_rows = _evaluate_verdicts(verdict_existing, bar_cache)
    trade_rows   = _evaluate_trades(trade_existing, bar_cache)

    recent = get_recent_signal_evaluations(days=LOOKBACK_DAYS)
    summary = defaultdict(lambda: {"count": 0, "wins": 0, "avg_thesis_return_pct": 0.0, "avg_excess_return_pct": 0.0})
    for row in recent:
        key = f"{row['source_type']}:{row['horizon_days']}d"
        summary[key]["count"] += 1
        summary[key]["wins"]  += 1 if row["outcome"] == "win" else 0
        summary[key]["avg_thesis_return_pct"] += row["thesis_return_pct"]
        summary[key]["avg_excess_return_pct"] += row["excess_return_pct"]

    for value in summary.values():
        if value["count"]:
            value["avg_thesis_return_pct"] = round(value["avg_thesis_return_pct"] / value["count"], 3)
            value["avg_excess_return_pct"] = round(value["avg_excess_return_pct"] / value["count"], 3)
            value["win_rate"] = round(value["wins"] / value["count"], 3)

    result = {
        "new_verdict_evaluations": len(verdict_rows),
        "new_trade_evaluations":   len(trade_rows),
        "summary":                 dict(summary),
    }
    logger.info(
        "[evaluator] added %s verdict evaluation(s), %s trade evaluation(s)",
        len(verdict_rows),
        len(trade_rows),
    )
    return result
