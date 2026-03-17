"""
Analyst_Team/analyst_macro_agent.py
══════════════════════════════════════════════════════════════════════════════
The Macro Analyst agent.

Unlike the news analyst (which analyses one ticker at a time), this agent:
  1. Reads all recent macro/geopolitical headlines
  2. Identifies which sectors and specific tickers are most impacted
  3. Writes an AnalystReport (analyst_type="macro") for each impacted ticker

This means tickers can enter the researcher pipeline purely because of a
geopolitical event — even if they weren't in your portfolio or screener list.

Example reasoning:
  "New semiconductor export controls to China → NVDA, AMD, AMAT at risk → SELL signal"
  "Oil sanctions on Iran → supply squeeze → XOM, CVX potential BUY"
  "US-China trade deal progress → broad tech rally likely → QQQ context"

Output: AnalystReport rows with analyst_type="macro" in the DB.
The researcher team picks these up automatically alongside news reports.
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_deepseek import ChatDeepSeek

from database import (
    get_recent_news_for_ticker,
    insert_analyst_report,
    get_latest_reports,
)
from Analyst_Team.macro_collector import get_macro_headlines_text

load_dotenv()
logger     = logging.getLogger(__name__)
MODEL_NAME = "deepseek-chat"


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_macro_news(hours: int = 24) -> str:
    """
    Retrieves recent geopolitical and macroeconomic headlines from the database.
    These are sourced from Reuters, BBC, AP, CNBC, FT, and Politico.
    Call this first to understand the current macro environment.
    Input: hours — how many hours back to look (default 24)
    """
    return get_macro_headlines_text(hours=hours, limit=50)


@tool
def save_macro_impact_reports(impacts_json: str) -> str:
    """
    Saves macro impact assessments for multiple tickers to the database.
    Each ticker gets its own AnalystReport with analyst_type='macro'.

    Input must be a JSON array of objects, each with:
      {
        "ticker":     "NVDA",
        "signal":     "BUY" | "SELL" | "HOLD",
        "confidence": 0.75,
        "summary":    "2-3 sentence explanation of WHY this event impacts this ticker",
        "key_points": ["point 1", "point 2", "point 3"]
      }

    Include only tickers where you have HIGH CONFIDENCE of impact (≥ 0.55).
    Do not include tickers with weak or speculative connections to the events.
    Returns confirmation of how many reports were saved.
    """
    try:
        impacts = json.loads(impacts_json)
    except json.JSONDecodeError as e:
        return f"ERROR: invalid JSON — {e}"

    if not isinstance(impacts, list):
        return "ERROR: input must be a JSON array"

    saved    = []
    skipped  = []

    for item in impacts:
        ticker     = (item.get("ticker") or "").upper().strip()
        signal     = (item.get("signal") or "").upper().strip()
        confidence = float(item.get("confidence", 0))
        summary    = (item.get("summary") or "").strip()
        key_points = item.get("key_points") or []

        if not ticker:
            skipped.append("(missing ticker)")
            continue
        if signal not in ("BUY", "SELL", "HOLD"):
            skipped.append(f"{ticker}: invalid signal '{signal}'")
            continue
        if not (0.55 <= confidence <= 1.0):
            skipped.append(f"{ticker}: confidence {confidence:.2f} below 0.55 threshold")
            continue
        if not summary:
            skipped.append(f"{ticker}: empty summary")
            continue

        row_id = insert_analyst_report(
            ticker        = ticker,
            analyst_type  = "macro",
            signal        = signal,
            confidence    = confidence,
            summary       = summary,
            key_points    = key_points,
            sources_used  = [{"source": "macro_feeds", "title": "geopolitical/macro headlines"}],
            article_count = None,
            model_used    = MODEL_NAME,
        )
        saved.append(f"{ticker} → {signal} ({confidence:.0%})  id={row_id}")

    result_lines = [f"Saved {len(saved)} macro impact report(s):"]
    result_lines += [f"  ✓ {s}" for s in saved]
    if skipped:
        result_lines += [f"  ✗ skipped: {s}" for s in skipped]
    return "\n".join(result_lines)


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the Macro Analyst for an algorithmic trading system.
Your job is to identify which publicly traded stocks are most impacted by
current geopolitical events, trade policy changes, sanctions, and macro news.

Your process:
1. Call get_macro_news() to retrieve recent headlines.
2. Identify the most significant market-moving events — focus on:
   - Tariffs, export controls, or trade deal changes
   - Sanctions or embargoes on countries or companies
   - Military conflicts or geopolitical escalations
   - Central bank decisions or major economic data
   - Supply chain disruptions for key commodities
3. For each significant event, determine which specific tickers are most affected.
4. Call save_macro_impact_reports(...) with your assessments.

Ticker selection rules:
- Be SPECIFIC — name actual ticker symbols (NVDA not "chip companies")
- Prioritise DIRECT impact over indirect (NVDA for chip export ban, not AAPL)
- Maximum 10 tickers per run — quality over quantity
- Only include tickers where the causal link is clear and strong
- Confidence ≥ 0.55 required — skip speculative connections

Signal logic for geopolitical events:
- SELL + high confidence: direct negative impact (export ban on their product/market)
- BUY  + high confidence: direct positive impact (competitor sanctioned, commodity squeeze)
- HOLD: indirect or uncertain impact
- If no significant geopolitical events exist, call save with an empty array []

Sector → ticker mappings to reason about:
- Semiconductors: NVDA, AMD, INTC, AMAT, ASML, TSM, QCOM
- Energy/Oil: XOM, CVX, COP, BP, SLB, HAL
- Defence: LMT, RTX, NOC, GD, BA
- Banks/Finance: JPM, BAC, GS, MS (impacted by rate decisions)
- Retail/Consumer: WMT, AMZN, TGT (impacted by tariffs on imports)
- Pharma: PFE, MRK, JNJ (impacted by drug pricing policy)
- Autos: TSLA, GM, F (impacted by EV policy, steel tariffs)
- Airlines: DAL, UAL, AAL (impacted by oil prices, conflict zones)

Always call save_macro_impact_reports as your final action, even if the array is empty.
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

def build_macro_analyst_agent():
    model = ChatDeepSeek(
        model       = MODEL_NAME,
        temperature = 0.2,
        max_tokens  = 2048,
        max_retries = 3,
    )
    return create_agent(
        model,
        tools         = [get_macro_news, save_macro_impact_reports],
        system_prompt = SYSTEM_PROMPT,
        name          = "macro_analyst",
    )


# ── Public interface ──────────────────────────────────────────────────────────

def run_macro_analyst() -> list[dict]:
    """
    Runs the macro analyst once.
    Returns list of saved AnalystReport dicts (analyst_type='macro').
    These are automatically picked up by the researcher team for any ticker
    that also has a news analyst report.
    """
    logger.info("[macro_analyst] Analysing geopolitical/macro impact on tickers...")

    agent = build_macro_analyst_agent()
    try:
        agent.invoke({
            "messages": [{
                "role":    "user",
                "content": (
                    "Review today's macro and geopolitical headlines. "
                    "Identify which specific stock tickers are most impacted "
                    "and save your assessments."
                ),
            }]
        })
    except Exception as e:
        logger.error(f"[macro_analyst] Agent failed: {e}")
        return []

    # Fetch all macro reports saved in this run (last 1 hour to be safe)
    from database import get_recent_news_for_ticker
    from sqlalchemy.orm import sessionmaker
    from database import engine, AnalystReport
    from datetime import timedelta

    session = sessionmaker(bind=engine)()
    cutoff  = __import__("datetime").datetime.utcnow() - timedelta(hours=1)
    try:
        rows = (
            session.query(AnalystReport)
            .filter(
                AnalystReport.analyst_type == "macro",
                AnalystReport.created_at   >= cutoff,
            )
            .order_by(AnalystReport.created_at.desc())
            .all()
        )
        results = []
        for r in rows:
            results.append({
                "ticker":     r.ticker,
                "signal":     r.signal.value,
                "confidence": r.confidence,
                "summary":    r.summary,
            })
        logger.info(f"[macro_analyst] Saved {len(results)} macro impact report(s)")
        return results
    finally:
        session.close()


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from database import Base, engine
    Base.metadata.create_all(bind=engine)

    from Analyst_Team.macro_collector import collect_macro_news
    print("Collecting macro news first...")
    collect_macro_news()

    print("\nRunning macro analyst...")
    reports = run_macro_analyst()
    if not reports:
        print("No macro impacts identified today.")
    else:
        print(f"\n{len(reports)} tickers flagged by macro events:")
        for r in reports:
            print(f"  {r['ticker']:<8} {r['signal']:<6} ({r['confidence']:.0%})  {r['summary'][:80]}...")