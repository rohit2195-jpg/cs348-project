"""
analyst_news_agent.py
══════════════════════════════════════════════════════════════════════════════
The News Analyst agent — built with the current LangChain create_agent API.

API used: langchain.agents.create_agent (LangChain 1.0+)
  - No AgentExecutor, no create_tool_calling_agent, no ChatPromptTemplate
  - create_agent(model, tools=tools, system_prompt=...) builds a LangGraph
    graph-based agent directly
  - Invoke with: agent.invoke({"messages": [{"role": "user", "content": ...}]})

Flow:
  1.  Agent calls get_news_articles + get_price_context tools (reads from DB)
  2.  Agent calls save_analyst_report tool (writes structured report to DB)
  3.  Downstream teams call get_latest_reports() / get_all_latest_reports_for_ticker()
══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import os
import sys

# Add backend/ root to path so 'database' is importable from Analyst_Team/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_deepseek import ChatDeepSeek

from database import (
    get_recent_news_for_ticker,
    get_latest_price_snapshot,
    insert_analyst_report,
    get_latest_reports,
)

load_dotenv()
logger = logging.getLogger(__name__)

MODEL_NAME = "deepseek-chat"


# ── Tools ────────────────────────────────────────────────────────────────────
# The agent calls these in its ReAct loop.
# Tools must have clear docstrings — the model reads them to decide when to call.

@tool
def get_news_articles(ticker: str) -> str:
    """
    Retrieves the latest news articles for a stock ticker from the database.
    Returns a formatted list of headlines, sources, and summaries.
    Always call this first before analysing any ticker.
    Input: ticker symbol e.g. 'AAPL'
    """
    articles = get_recent_news_for_ticker(ticker.upper(), hours=48, limit=25)
    if not articles:
        return f"No recent news found for {ticker.upper()}."

    lines = [f"=== Recent News for {ticker.upper()} ({len(articles)} articles) ===\n"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        if a.get("published"):
            lines.append(f"   Published: {a['published']}")
        if a.get("body_summary"):
            lines.append(f"   Summary:   {a['body_summary'][:300]}")
        if a.get("url"):
            lines.append(f"   URL:       {a['url']}")
        lines.append("")
    return "\n".join(lines)


@tool
def get_price_context(ticker: str) -> str:
    """
    Retrieves the latest price snapshot and key fundamentals for a stock ticker.
    Returns price, day change %, volume, market cap, P/E ratio, 52-week range.
    Call this alongside get_news_articles for full context before writing a report.
    Input: ticker symbol e.g. 'AAPL'
    """
    snap = get_latest_price_snapshot(ticker.upper())
    if not snap:
        return f"No price snapshot available for {ticker.upper()}."

    chg  = f"{snap['day_change_pct']:+.2f}%" if snap.get("day_change_pct") is not None else "N/A"
    mcap = f"${snap['market_cap']/1e9:.1f}B" if snap.get("market_cap") else "N/A"
    vol  = f"{snap['volume']:,}"              if snap.get("volume")     else "N/A"
    avol = f"{snap['avg_volume']:,}"          if snap.get("avg_volume") else "N/A"

    return (
        f"=== Price Snapshot: {snap['ticker']} ===\n"
        f"Price:         ${snap.get('price', 'N/A')}\n"
        f"Day Change:    {chg}\n"
        f"Volume:        {vol}\n"
        f"Avg Volume:    {avol}\n"
        f"Market Cap:    {mcap}\n"
        f"P/E Ratio:     {snap.get('pe_ratio', 'N/A')}\n"
        f"Forward P/E:   {snap.get('forward_pe', 'N/A')}\n"
        f"52W High:      ${snap.get('week_52_high', 'N/A')}\n"
        f"52W Low:       ${snap.get('week_52_low', 'N/A')}\n"
        f"Sector:        {snap.get('sector', 'N/A')}\n"
        f"Snapshot At:   {snap.get('snapshot_at', 'N/A')}"
    )


@tool
def save_analyst_report(
    ticker:     str,
    signal:     str,
    confidence: float,
    summary:    str,
    key_points: list,
) -> str:
    """
    Saves the completed news analyst report to the database.
    This MUST be your final action after retrieving news and price context.

    Args:
        ticker:     Stock ticker symbol e.g. 'AAPL'
        signal:     Must be exactly 'BUY', 'SELL', or 'HOLD'
        confidence: Float between 0.0 and 1.0.
                    0.3 = weak/conflicting evidence
                    0.5 = mixed/neutral
                    0.8+ = strong clear signal
        summary:    2-4 paragraph narrative analysis. Be specific about which
                    news themes drove your conclusion.
        key_points: List of 4-6 concise bullet point strings summarising findings.

    Returns confirmation string with the saved database row id.
    """
    signal = signal.upper().strip()
    if signal not in ("BUY", "SELL", "HOLD"):
        return f"ERROR: signal must be 'BUY', 'SELL', or 'HOLD' — got '{signal}'"

    confidence = float(confidence)
    if not (0.0 <= confidence <= 1.0):
        return f"ERROR: confidence must be between 0.0 and 1.0 — got {confidence}"

    if not summary or not summary.strip():
        return "ERROR: summary cannot be empty"

    if not isinstance(key_points, list) or len(key_points) < 1:
        return "ERROR: key_points must be a non-empty list of strings"

    # Attach the actual source articles used (pulled fresh from DB)
    articles = get_recent_news_for_ticker(ticker.upper(), hours=48, limit=25)
    sources  = [{"title": a["title"], "source": a["source"], "url": a["url"]} for a in articles]

    row_id = insert_analyst_report(
        ticker        = ticker,
        analyst_type  = "news",
        signal        = signal,
        confidence    = confidence,
        summary       = summary,
        key_points    = key_points,
        sources_used  = sources,
        article_count = len(articles),
        model_used    = MODEL_NAME,
    )
    return (
        f"Report saved. DB id={row_id}  "
        f"Ticker={ticker.upper()}  Signal={signal}  Confidence={confidence:.0%}  "
        f"Articles used={len(articles)}"
    )


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the News Analyst agent for an algorithmic trading system.

For each stock ticker you are given, you must:
1. Call get_news_articles with the ticker to retrieve recent headlines and summaries.
2. Call get_price_context with the ticker to get price and fundamentals.
3. Analyse both together to determine market sentiment and near-term outlook.
4. Call save_analyst_report with your conclusions — this is always your final action.

Signal guidelines:
- BUY:  News is predominantly positive, catalysts present, price momentum supportive
- SELL: News is predominantly negative, risks materialising, or significant red flags
- HOLD: News is mixed, neutral, insufficient, or contradictory

Confidence guidelines:
- 0.3  — Very little news or strongly contradictory signals
- 0.5  — Mixed signals, no clear direction
- 0.7  — Moderately clear signal with reasonable evidence
- 0.85+ — Strong, consistent signal across multiple sources

Rules:
- Only base your signal on evidence from the tools — never fabricate news or events.
- If there is no recent news, set signal=HOLD, confidence=0.3, and explain why.
- Do not ask for clarification — work with whatever the tools return.
- Always call save_analyst_report as your last step, even if data is sparse.
"""


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_news_analyst_agent():
    """
    Builds the news analyst agent using the current LangChain create_agent API.
    Returns a compiled LangGraph agent ready for .invoke() calls.
    """
    model = ChatDeepSeek(
        model       = MODEL_NAME,
        temperature = 0.1,    # low temp = more consistent structured output
        max_tokens  = 2048,
        max_retries = 3,
    )

    return create_agent(
        model,
        tools         = [get_news_articles, get_price_context, save_analyst_report],
        system_prompt = SYSTEM_PROMPT,
        name          = "news_analyst",
    )


# ── Public interface ──────────────────────────────────────────────────────────

def run_news_analyst(ticker: str) -> dict:
    """
    Runs the news analyst for one ticker.
    Returns the saved DB report as a dict, or an error dict on failure.
    """
    ticker = ticker.upper()
    logger.info(f"[news_analyst] Starting analysis for {ticker}")

    agent = build_news_analyst_agent()

    try:
        agent.invoke({
            "messages": [{
                "role":    "user",
                "content": (
                    f"Analyse the stock {ticker}. "
                    f"Get its news articles and price context, then save your report."
                ),
            }]
        })
    except Exception as e:
        logger.error(f"[news_analyst] Agent failed for {ticker}: {e}")
        return {"error": str(e), "ticker": ticker}

    # Return whatever was just written to the DB
    reports = get_latest_reports(ticker, analyst_type="news", limit=1)
    if reports:
        r = reports[0]
        logger.info(f"[news_analyst] {ticker} → {r['signal']} (confidence={r['confidence']:.0%})")
        return r

    return {"error": "Agent completed but no report was saved.", "ticker": ticker}


def run_news_analyst_batch(tickers: list[str]) -> list[dict]:
    """Run the news analyst sequentially across multiple tickers."""
    results = []
    for ticker in tickers:
        results.append(run_news_analyst(ticker))
    return results


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from database import Base, engine
    Base.metadata.create_all(bind=engine)

    result = run_news_analyst("AAPL")
    print("\n=== Analyst Report ===")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Ticker:     {result['ticker']}")
        print(f"Signal:     {result['signal']}")
        print(f"Confidence: {result['confidence']:.0%}")
        print(f"Articles:   {result.get('article_count', 'N/A')}")
        print(f"\nSummary:\n{result['summary']}")
        print(f"\nKey Points:")
        for pt in result.get("key_points", []):
            print(f"  • {pt}")