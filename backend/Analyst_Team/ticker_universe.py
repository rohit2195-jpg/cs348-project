"""
Analyst_Team/ticker_universe.py
══════════════════════════════════════════════════════════════════════════════
Builds the prioritised ticker list for each analyst run.

Held tickers come from the Portfolio table (symbol, purchasePrice, quantity).
Candidates come from yfinance screeners ranked by volume/momentum.
Merged, de-duplicated, and sorted so held stocks always run first.
══════════════════════════════════════════════════════════════════════════════
"""

import logging
from dataclasses import dataclass, field
import yfinance as yf
from database import get_portfolio

logger = logging.getLogger(__name__)

MAX_CANDIDATES_PER_SCREENER = 15
MAX_CANDIDATE_TICKERS       = 30


@dataclass
class TickerItem:
    priority:     int           # 1=held, 2=top mover, 3=trending
    score:        float         # higher = more interesting within same priority
    ticker:       str
    company_name: str  = ""
    reason:       str  = ""
    is_held:      bool = False


# ── Source 1: your Portfolio table ────────────────────────────────────────────

def get_held_tickers() -> list[TickerItem]:
    """
    Reads your Portfolio table directly.
    Each row has: symbol, purchasePrice, quantity, purchaseDate.
    Returns one TickerItem per position, always priority=1.
    """
    try:
        positions = get_portfolio()   # returns list of Portfolio ORM rows
        items = []
        for p in positions:
            items.append(TickerItem(
                priority     = 1,
                score        = 999.0,    # held stocks are always first
                ticker       = p.symbol.upper(),
                reason       = f"held  {p.quantity} shares @ ${p.purchasePrice:.2f}",
                is_held      = True,
            ))
        logger.info(f"[universe] Portfolio: {len(items)} held ticker(s): {[i.ticker for i in items]}")
        return items
    except Exception as e:
        logger.warning(f"[universe] Could not load portfolio: {e}")
        return []


# ── Source 2: yfinance screeners ──────────────────────────────────────────────

def _fetch_screener(screen_key: str, priority: int, reason_label: str) -> list[TickerItem]:
    """Calls one yfinance screener and returns scored TickerItems."""
    try:
        # yfinance >= 0.2.x uses Screener class, older versions used yf.screen()
        # Try the new API first, fall back to the old one
        try:
            from yfinance import Screener
            s = Screener()
            s.set_predefined_body(screen_key)
            result = s.response
        except Exception:
            result = yf.screen(screen_key)
        quotes = (result or {}).get("quotes", [])[:MAX_CANDIDATES_PER_SCREENER]
        items  = []
        for q in quotes:
            ticker = q.get("symbol", "").upper()
            if not ticker:
                continue
            chg   = abs(q.get("regularMarketChangePercent", 0) or 0)
            vol   = q.get("regularMarketVolume",        0) or 0
            avol  = q.get("averageDailyVolume3Month",   1) or 1
            # Score = price swing × relative volume — bigger = more interesting
            score = chg * (vol / avol)
            items.append(TickerItem(
                priority     = priority,
                score        = round(score, 4),
                ticker       = ticker,
                company_name = q.get("shortName", ""),
                reason       = f"{reason_label}  ({chg:+.1f}%)",
                is_held      = False,
            ))
        logger.info(f"[universe] {screen_key}: {len(items)} ticker(s)")
        return items
    except Exception as e:
        logger.warning(f"[universe] Screener '{screen_key}' failed: {e}")
        return []


def get_candidate_tickers() -> list[TickerItem]:
    """Pulls from four screeners, de-dupes, caps at MAX_CANDIDATE_TICKERS."""
    raw: list[TickerItem] = []
    raw += _fetch_screener("most_actives", priority=2, reason_label="most active")
    raw += _fetch_screener("day_gainers",  priority=2, reason_label="top gainer")
    raw += _fetch_screener("day_losers",   priority=2, reason_label="top loser")
    raw += _fetch_screener("trending",     priority=3, reason_label="trending")

    # Keep best score per ticker across all screeners
    seen: dict[str, TickerItem] = {}
    for item in raw:
        if item.ticker not in seen or item.score > seen[item.ticker].score:
            seen[item.ticker] = item

    ranked = sorted(seen.values(), key=lambda x: (x.priority, -x.score))
    capped = ranked[:MAX_CANDIDATE_TICKERS]
    logger.info(f"[universe] Candidates: {len(capped)} after dedup + cap")
    return capped


# ── Main entry point ──────────────────────────────────────────────────────────

def build_ticker_queue(
    include_candidates: bool = True,
    extra_tickers:      list[str] | None = None,
) -> list[TickerItem]:
    """
    Returns the full ordered list of tickers for one analyst run.

    include_candidates=False  →  portfolio-only mode (fast, no screener calls)
    extra_tickers             →  watchlist / CLI tickers to force-include
    """
    held     = get_held_tickers()
    held_set = {t.ticker for t in held}

    candidates = get_candidate_tickers() if include_candidates else []

    # Force-include extras (e.g. from watchlist or CLI --tickers flag)
    extras = [
        TickerItem(priority=2, score=50.0, ticker=t.upper(), reason="manually added")
        for t in (extra_tickers or [])
        if t.upper() not in held_set
    ]

    # Merge: held wins over any candidate with the same ticker
    all_items = held + extras + [c for c in candidates if c.ticker not in held_set]
    seen: dict[str, TickerItem] = {}
    for item in all_items:
        if item.ticker not in seen or item.priority < seen[item.ticker].priority:
            seen[item.ticker] = item

    ordered = sorted(seen.values(), key=lambda x: (x.priority, -x.score))
    logger.info(
        f"[universe] Final queue: {len(ordered)} tickers  "
        f"({len(held)} held  +  {len(ordered)-len(held)} candidates)"
    )
    return ordered


def print_queue(queue: list[TickerItem]) -> None:
    """Pretty-prints the ticker queue to stdout."""
    pri_label = {1: "HELD    ", 2: "MOVER   ", 3: "TRENDING"}
    print(f"\n  {'─'*55}")
    print(f"  Ticker queue  —  {len(queue)} tickers")
    print(f"  {'─'*55}")
    for i, t in enumerate(queue, 1):
        label = pri_label.get(t.priority, "        ")
        print(f"  {i:>3}. [{label}] {t.ticker:<8}  {t.reason}")
    print(f"  {'─'*55}\n")