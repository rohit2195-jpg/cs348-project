"""
Analyst_Team/analyst.py
══════════════════════════════════════════════════════════════════════════════
Analyst stage — pure data collection, ZERO LLM calls.

Collects news articles and price snapshots for a ticker and stores them in
the database. The researcher stage reads these raw articles and forms its own
signal — no intermediate LLM opinion needed here.

What this replaces:
  Before: news collector → LLM analyst → analyst_report row → researcher
  After:  news collector → raw_news rows + price_snapshot → researcher

The researcher now calls get_raw_news_for_ticker() directly and reads the
actual headlines rather than a pre-digested LLM summary. This is strictly
better — the researcher LLM sees more information and forms its own view.
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from database import get_recent_news_for_ticker, get_latest_price_snapshot

logger = logging.getLogger(__name__)


def run_news_analyst(ticker: str) -> dict:
    """
    No-op — kept for interface compatibility with main.py.
    The analyst stage no longer produces analyst_report rows or calls any LLM.
    The researcher reads raw_news and price_snapshots directly.

    Returns a minimal dict so main.py stage logging still works.
    """
    ticker    = ticker.upper()
    articles  = get_recent_news_for_ticker(ticker, hours=48, limit=5)
    snap      = get_latest_price_snapshot(ticker)
    n         = len(articles)
    price_str = f"${snap['price']}" if snap else "no price"

    logger.info(f"[analyst] {ticker}: {n} articles in DB  {price_str}  — ready for researcher")
    return {
        "ticker":       ticker,
        "signal":       "COLLECTED",
        "confidence":   1.0,
        "summary":      f"{n} articles collected",
        "analyst_type": "news",
    }


def run_news_analyst_batch(tickers: list[str]) -> list[dict]:
    return [run_news_analyst(t) for t in tickers]