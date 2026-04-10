"""
Researcher_Team/researcher_team.py
══════════════════════════════════════════════════════════════════════════════
Researcher Team — reads stored feature packets plus supporting normalized
events and decides whether a ticker has a durable 1-5 day edge.
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
    get_latest_feature_snapshot,
    get_latest_verdict,
    insert_research_verdict,
    get_all_latest_reports_for_ticker,  # still used for macro signals
    get_recent_news_events_for_ticker,
    mark_universe_candidate_reviewed,
)
from feature_store import build_feature_snapshot

load_dotenv()
logger     = logging.getLogger(__name__)
MODEL_NAME = "deepseek-chat"


def _build_research_packet(ticker: str) -> dict:
    ticker = ticker.upper()
    feature = get_latest_feature_snapshot(ticker)
    if not feature:
        feature = build_feature_snapshot(ticker)

    reports = get_all_latest_reports_for_ticker(ticker)
    macro = reports.get("macro")
    events = get_recent_news_events_for_ticker(ticker, hours=72, limit=10)
    history_context = feature.get("history_context") or {}

    return {
        "ticker":                   ticker,
        "is_held":                  feature["is_held"],
        "article_count":            feature["article_count"],
        "unique_sources":           sorted({e.get("source", "") for e in events if e.get("source")}),
        "unique_source_count":      feature["unique_source_count"],
        "high_signal_source_count": feature["high_signal_source_count"],
        "dominant_event_tags":      feature["dominant_event_tags"],
        "signal_quality":           feature["signal_quality"],
        "evidence_score":           feature["evidence_score"],
        "triage_score":             feature["triage_score"],
        "block_reasons":            feature["block_reasons"],
        "price_snapshot":           {
            "price": feature.get("price"),
            "day_change_pct": feature.get("day_change_pct"),
            "market_cap": feature.get("market_cap"),
            "sector": feature.get("sector"),
            "avg_volume_ratio": feature.get("avg_volume_ratio"),
        },
        "history_context":          history_context,
        "macro_signal":             {
            "signal": macro["signal"],
            "confidence": macro["confidence"],
            "summary": macro["summary"],
        } if macro else None,
        "headlines": [
            {
                "source": event.get("source"),
                "source_tier": event.get("source_tier"),
                "title": event.get("title"),
                "published": event.get("published"),
                "event_tags": event.get("event_tags"),
                "body_summary": event.get("body_summary"),
            }
            for event in events
        ],
    }


# ── Eligibility check ─────────────────────────────────────────────────────────

def is_worth_researching(ticker: str) -> tuple[bool, str]:
    """
    The researcher should only review names that survived deterministic triage.
    """
    packet = _build_research_packet(ticker)
    macro  = packet["macro_signal"]

    if packet["block_reasons"] and not packet["is_held"]:
        return False, f"blocked by triage filters: {', '.join(packet['block_reasons'])}"
    if packet["is_held"] and (packet["article_count"] >= 1 or macro):
        return True, f"held position with fresh signal context ({packet['signal_quality']})"
    if packet["triage_score"] >= 5 and packet["article_count"] >= 2:
        return True, f"triage score {packet['triage_score']:.1f} with {packet['article_count']} events"
    if macro and macro["confidence"] >= 0.70:
        return True, f"high-confidence macro signal ({macro['signal']} {macro['confidence']:.0%})"

    return False, (
        f"insufficient edge: articles={packet['article_count']} "
        f"sources={packet['unique_source_count']} triage={packet['triage_score']:.1f} "
        f"quality={packet['signal_quality']}"
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_ticker_data(ticker: str) -> str:
    """
    Retrieves the latest stored feature packet, supporting normalized events,
    and macro context for a ticker. This is the complete research packet.
    Always call this first.
    Input: ticker symbol e.g. 'AAPL'
    """
    packet = _build_research_packet(ticker)
    lines = [f"=== Data for {ticker.upper()} ===\n"]
    lines.append("STRUCTURED SIGNAL SUMMARY:")
    lines.append(json.dumps({
        "ticker":                   packet["ticker"],
        "is_held":                  packet["is_held"],
        "article_count":            packet["article_count"],
        "unique_sources":           packet["unique_sources"],
        "high_signal_source_count": packet["high_signal_source_count"],
        "dominant_event_tags":      packet["dominant_event_tags"],
        "signal_quality":           packet["signal_quality"],
        "evidence_score":           packet["evidence_score"],
        "triage_score":             packet["triage_score"],
        "block_reasons":            packet["block_reasons"],
    }, indent=2))
    lines.append("")

    # Price snapshot
    snap = packet["price_snapshot"]
    if snap:
        chg  = f"{snap['day_change_pct']:+.2f}%" if snap.get("day_change_pct") is not None else "N/A"
        mcap = f"${snap['market_cap']/1e9:.1f}B" if snap.get("market_cap") else "N/A"
        lines.append(
            f"PRICE: ${snap.get('price','N/A')}  Day:{chg}  "
            f"Cap:{mcap}  Sector:{snap.get('sector','N/A')}  "
            f"RelVol:{snap.get('avg_volume_ratio','N/A')}x\n"
        )
    else:
        lines.append("PRICE: no snapshot available\n")

    hist = packet["history_context"]
    if hist:
        lines.append("HISTORICAL CONTEXT:")
        lines.append(json.dumps(hist, indent=2))
        lines.append("")

    # Normalized supporting events
    articles = packet["headlines"]
    if articles:
        lines.append(f"NEWS EVENTS ({len(articles)} from last 72h):")
        for i, a in enumerate(articles, 1):
            tags = ",".join(a.get("event_tags") or [])
            lines.append(f"  {i}. [{a['source']}/{a.get('source_tier','standard')}] {a['title']} ({tags})")
            if a.get("body_summary"):
                lines.append(f"     {a['body_summary'][:200]}")
        lines.append("")
    else:
        lines.append("NEWS: no recent articles\n")

    # Macro signals if any
    macro = packet["macro_signal"]
    if macro:
        lines.append(f"MACRO SIGNAL: {macro['signal']} ({macro['confidence']:.0%})")
        lines.append(f"  {macro['summary'][:300]}\n")

    return "\n".join(lines)


@tool
def save_research_verdict(
    ticker:          str,
    verdict:         str,
    conviction:      float,
    bull_case:       str,
    bear_case:       str,
    final_reasoning: str,
    key_risks:       list,
    key_catalysts:   list,
) -> str:
    """
    Saves the research verdict to the database.
    This MUST be your final action.

    Args:
        ticker:          Stock ticker e.g. 'AAPL'
        verdict:         STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
        conviction:      Float 0.0–1.0. Be generous — paper trading, skew high.
        bull_case:       Argument FOR buying. Be specific — cite headlines.
        bear_case:       Argument AGAINST. Be honest about risks.
        final_reasoning: Why one side won. Which data points decided it.
        key_risks:       List of 3-5 risk strings.
        key_catalysts:   List of 3-5 catalyst strings.
    """
    verdict = verdict.upper().strip()
    valid   = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    if verdict not in valid:
        return f"ERROR: verdict must be one of {valid} — got '{verdict}'"

    reports  = get_all_latest_reports_for_ticker(ticker.upper())
    snapshot = {k: {"signal": v["signal"], "confidence": v["confidence"]} for k, v in reports.items()}

    row_id = insert_research_verdict(
        ticker          = ticker,
        verdict         = verdict,
        conviction      = float(conviction),
        bull_case       = bull_case,
        bear_case       = bear_case,
        final_reasoning = final_reasoning,
        key_risks       = key_risks,
        key_catalysts   = key_catalysts,
        analyst_signals = snapshot,
        model_used      = MODEL_NAME,
    )
    return f"Verdict saved. id={row_id}  {ticker.upper()} → {verdict}  conviction={float(conviction):.0%}"


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the researcher for a daily event-driven swing trading system.
Your job is to decide whether a ticker has a durable 1-5 trading day edge.

PROCESS:
1. Call get_ticker_data(ticker) — get all news, price, and macro data.
2. Form a bull case: what in the data supports buying?
3. Form a bear case: what risks or negatives exist?
4. Decide a verdict and call save_research_verdict(...).

PRIMARY OBJECTIVE:
  - Prefer precision over activity.
  - HOLD is the correct answer when the edge is weak, crowded, stale, or mostly noise.
  - Only issue BUY/SELL when the evidence suggests follow-through over the next 1-5 trading days.

VERDICT CALIBRATION:
  STRONG_BUY  — multiple high-quality sources, clear positive catalyst, likely 1-5 day continuation. Conviction 0.82+
  BUY         — good but not overwhelming evidence of positive follow-through. Conviction 0.68–0.81
  HOLD        — conflicting, weak, generic, low-novelty, or already fully-explained news. Use freely.
  SELL        — good but not overwhelming evidence of negative follow-through. Conviction 0.68–0.81
  STRONG_SELL — multiple high-quality sources, clear negative catalyst, likely 1-5 day downside continuation. Conviction 0.82+

ONLY TRADE WHEN:
  - There is a company-specific catalyst, or a direct sector/macro catalyst.
  - Evidence is supported by multiple independent sources, OR one strong source plus a meaningful price move.
  - The move still looks likely to continue rather than reverse immediately.

AVOID FALSE POSITIVES:
  - Generic market commentary is usually HOLD.
  - Broad "AI is exciting" or "stocks are volatile" headlines are not enough.
  - Do not force action because a stock is moving; explain whether the move is likely exhausted.
  - If data quality is weak or the signal is mostly inferred, choose HOLD.

READING THE DATA:
  - Start with the structured signal summary. It tells you source diversity, signal quality, event tags, price context, and triage status.
  - Price momentum matters, but only when it is paired with a catalyst that can continue to matter.
  - Multiple headlines repeating the same theme strengthen the case.
  - Macro signals are valid only when the ticker linkage is direct and economically meaningful.
  - Use historical context to judge whether this setup is fresh and durable, not to override the current catalyst.
  - Think like a swing trader managing a real portfolio, not a paper-trading action generator.

Always call save_research_verdict as your final action.
Do not ask for clarification.
"""


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_researcher_agent():
    model = ChatDeepSeek(
        model       = MODEL_NAME,
        temperature = 0.2,
        max_tokens  = 3000,
        max_retries = 3,
    )
    return create_agent(
        model,
        tools         = [get_ticker_data, save_research_verdict],
        system_prompt = SYSTEM_PROMPT,
        name          = "researcher_team",
    )


# ── Public interface ──────────────────────────────────────────────────────────

def run_researcher(ticker: str, run_date: str | None = None) -> dict:
    ticker = ticker.upper()

    eligible, reason = is_worth_researching(ticker)
    if not eligible:
        logger.info(f"[researcher] Skipping {ticker}: {reason}")
        return {"skipped": True, "ticker": ticker, "reason": reason}

    logger.info(f"[researcher] Debating {ticker}: {reason}")
    agent = build_researcher_agent()

    try:
        agent.invoke({
            "messages": [{
                "role":    "user",
                "content": (
                    f"Research {ticker}. Get all available data, "
                    f"decide whether it has a real 1-5 day follow-through edge, "
                    f"then save your verdict."
                ),
            }]
        })
    except Exception as e:
        logger.error(f"[researcher] Agent failed for {ticker}: {e}")
        return {"error": str(e), "ticker": ticker}

    verdict = get_latest_verdict(ticker)
    if verdict:
        if run_date:
            mark_universe_candidate_reviewed(run_date, ticker, trade_ready=True)
        logger.info(f"[researcher] {ticker} → {verdict['verdict']} ({verdict['conviction']:.0%})")
        return verdict

    return {"error": "Agent ran but no verdict was saved.", "ticker": ticker}


def run_researcher_batch(tickers: list[str], run_date: str | None = None) -> list[dict]:
    return [run_researcher(t, run_date=run_date) for t in tickers]
