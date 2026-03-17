"""
Researcher_Team/researcher_team.py
══════════════════════════════════════════════════════════════════════════════
Bull vs bear structured debate for each ticker that passes the analyst filter.

Only runs on tickers where analyst_reports shows a non-HOLD signal with
enough confidence — weak/mixed signals are skipped to save LLM calls.

Flow per ticker:
  1. Read all analyst reports from DB
  2. Bull researcher argues FOR the position
  3. Bear researcher argues AGAINST / surfaces risks
  4. Synthesis produces a final verdict + conviction score
  5. ResearchVerdictRow written to DB for the Portfolio Manager to consume
══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_deepseek import ChatDeepSeek

from database import (
    get_all_latest_reports_for_ticker,
    get_latest_price_snapshot,
    get_latest_verdict,
    insert_research_verdict,
)

load_dotenv()
logger     = logging.getLogger(__name__)
MODEL_NAME = "deepseek-chat"

MIN_ANALYST_CONFIDENCE = 0.45   # lowered: let more tickers through to debate
MIN_ANALYST_AGREEMENT  = 0.0    # removed: single analyst signal is enough to debate


# ── Eligibility check (called by main.py before spinning up agent) ────────────

def is_worth_researching(ticker: str) -> tuple[bool, str]:
    """
    Returns (eligible, reason_string).
    Checks analyst_reports for a clear enough signal before wasting an LLM call.
    """
    reports = get_all_latest_reports_for_ticker(ticker)
    if not reports:
        return False, "no analyst reports in DB"

    signals  = [r["signal"] for r in reports.values()]
    confs    = [r["confidence"] for r in reports.values()]
    avg_conf = sum(confs) / len(confs) if confs else 0

    if avg_conf < MIN_ANALYST_CONFIDENCE:
        return False, f"avg confidence {avg_conf:.0%} below {MIN_ANALYST_CONFIDENCE:.0%}"

    buys  = signals.count("BUY")
    sells = signals.count("SELL")
    total = len(signals)
    dominant = max(buys, sells)

    # Agreement gate removed — any directional signal warrants a debate.
    # MIN_ANALYST_AGREEMENT=0.0 means this check never blocks; kept for clarity.
    direction = "BUY" if buys >= sells else "SELL"
    return True, f"{direction} ({dominant}/{total} analysts agree, avg conf {avg_conf:.0%})"


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_analyst_reports(ticker: str) -> str:
    """
    Fetches all latest analyst team reports for a ticker from the database.
    Returns signals, confidence scores, summaries, and key points from every
    analyst type available (news, sentiment, technical, fundamentals).
    Always call this first before constructing any argument.
    Input: ticker symbol e.g. 'AAPL'
    """
    reports = get_all_latest_reports_for_ticker(ticker.upper())
    if not reports:
        return f"No analyst reports found for {ticker.upper()}."

    snap  = get_latest_price_snapshot(ticker.upper())
    lines = [f"=== Analyst Reports: {ticker.upper()} ===\n"]

    if snap:
        chg  = f"{snap['day_change_pct']:+.2f}%" if snap.get("day_change_pct") is not None else "N/A"
        mcap = f"${snap['market_cap']/1e9:.1f}B"  if snap.get("market_cap")       else "N/A"
        lines.append(
            f"Price: ${snap.get('price','N/A')}  "
            f"Day: {chg}  Cap: {mcap}  "
            f"Sector: {snap.get('sector','N/A')}\n"
        )

    for analyst_type, r in reports.items():
        lines.append(f"── {analyst_type.upper()} ANALYST ──────────────")
        lines.append(f"Signal:     {r['signal']}  (confidence {r['confidence']:.0%})")
        lines.append(f"Summary:    {r['summary'][:500]}")
        if r.get("key_points"):
            for pt in r["key_points"]:
                lines.append(f"  • {pt}")
        lines.append("")

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
    Saves the completed research verdict to the database.
    This MUST be your final action after constructing both arguments.

    Args:
        ticker:          Stock ticker e.g. 'AAPL'
        verdict:         STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
        conviction:      Float 0.0–1.0.
                           0.5 = evenly matched debate
                           0.7 = one side moderately stronger
                           0.85+ = clear winner, strong evidence
        bull_case:       2-3 paragraphs arguing FOR the bullish position.
                         Must cite specific findings from the analyst reports.
        bear_case:       2-3 paragraphs arguing AGAINST / key risks.
                         Must cite specific findings from the analyst reports.
        final_reasoning: 1-2 paragraphs: which side won and the deciding factors.
        key_risks:       List of 3-5 specific risk strings (one sentence each).
        key_catalysts:   List of 3-5 specific catalyst strings (one sentence each).
    """
    verdict = verdict.upper().strip()
    valid   = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    if verdict not in valid:
        return f"ERROR: verdict must be one of {valid} — got '{verdict}'"
    if not (0.0 <= float(conviction) <= 1.0):
        return "ERROR: conviction must be between 0.0 and 1.0"
    if not all([bull_case.strip(), bear_case.strip(), final_reasoning.strip()]):
        return "ERROR: bull_case, bear_case, and final_reasoning cannot be empty"
    if not isinstance(key_risks, list) or not isinstance(key_catalysts, list):
        return "ERROR: key_risks and key_catalysts must be lists"

    # Snapshot the analyst signals used as inputs
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
    return (
        f"Verdict saved. id={row_id}  "
        f"{ticker.upper()} → {verdict}  conviction={float(conviction):.0%}"
    )


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the Researcher Team for an algorithmic trading system.
You will conduct a structured bull vs bear debate for a given stock ticker.

STEP 1 — Call get_analyst_reports(ticker) to retrieve all analyst findings.

STEP 2 — BULL RESEARCHER
Write the strongest possible case FOR the bullish position.
Mine the analyst reports for every piece of supporting evidence.
Be specific — cite actual signal levels, themes, and data from the reports.

STEP 3 — BEAR RESEARCHER  
Now argue the opposite. Challenge every bullish assumption.
Surface risks, macro headwinds, valuation concerns, weak signals.
Find the holes in the bull case. Be equally aggressive and specific.

STEP 4 — SYNTHESIS
Decide which side won and produce a final verdict.
  STRONG_BUY  — bull case clearly dominant, conviction ≥ 0.80
  BUY         — bull case stronger, some risks remain, conviction 0.60–0.79
  HOLD        — debate evenly matched or evidence insufficient
  SELL        — bear case stronger, risks outweigh upside, conviction 0.60–0.79
  STRONG_SELL — bear case clearly dominant, conviction ≥ 0.80

STEP 5 — Call save_research_verdict(...) with the full debate output.
         This is always your final action.

Rules:
- Only cite evidence from the analyst reports. Never fabricate news or data.
- STRONG_BUY / STRONG_SELL requires clear analyst agreement AND conviction ≥ 0.80.
- If signals are mixed or weak, verdict = HOLD.
- Do not ask for clarification — work with whatever the tools return.
"""


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_researcher_agent():
    model = ChatDeepSeek(
        model       = MODEL_NAME,
        temperature = 0.3,      # slightly higher than analyst — debate benefits from varied reasoning
        max_tokens  = 3000,
        max_retries = 3,
    )
    return create_agent(
        model,
        tools         = [get_analyst_reports, save_research_verdict],
        system_prompt = SYSTEM_PROMPT,
        name          = "researcher_team",
    )


# ── Public interface ──────────────────────────────────────────────────────────

def run_researcher(ticker: str) -> dict:
    """
    Runs the bull/bear debate for one ticker.
    Returns the saved verdict dict, a skip dict, or an error dict.
    """
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
                    f"Research the stock {ticker}. "
                    f"Retrieve the analyst reports, run the bull vs bear debate, "
                    f"then save your verdict."
                ),
            }]
        })
    except Exception as e:
        logger.error(f"[researcher] Agent failed for {ticker}: {e}")
        return {"error": str(e), "ticker": ticker}

    verdict = get_latest_verdict(ticker)
    if verdict:
        logger.info(f"[researcher] {ticker} → {verdict['verdict']} ({verdict['conviction']:.0%})")
        return verdict

    return {"error": "Agent ran but no verdict was saved.", "ticker": ticker}


def run_researcher_batch(tickers: list[str]) -> list[dict]:
    """Runs researcher sequentially across a list of tickers. Skips ineligible ones."""
    return [run_researcher(t) for t in tickers]