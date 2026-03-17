"""
Trader_Team/trader_agent.py
══════════════════════════════════════════════════════════════════════════════
The Trader Agent — final stage of the pipeline.

Reads researcher verdicts, checks the account, sizes positions, and executes
trades via Alpaca. All hard limits are enforced inside the tools themselves
so the LLM cannot bypass them regardless of its reasoning.

Trigger logic (applied before the agent is even invoked):
  BUY  — verdict BUY/STRONG_BUY, conviction ≥ 0.65, ≥ 2 analyst types agree
  SELL — verdict SELL/STRONG_SELL, conviction ≥ 0.65, ≥ 2 analyst types agree
         OR: holding the stock AND conviction ≥ 0.70 (protect existing positions)

Position sizing guardrails (enforced in execute_buy tool):
  - Max 25% of available cash on any single trade
  - Conviction scales the allocation: 0.65 → 10%, 0.75 → 17%, 0.90 → 25%
  - LLM proposes a share quantity; tool validates it fits within the cap
  - Never buy fractional shares (quantities are integers)

Trade log:
  Every executed trade writes to order_history (via existing DB functions)
  and also to trade_decisions (new table) which stores the full LLM rationale.
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_deepseek import ChatDeepSeek

import trading as t
from database import (
    get_actionable_verdicts,
    get_all_latest_reports_for_ticker,
    get_position,
    create_order,
    fill_order,
    set_alpaca_order_id,
    upsert_position,
    get_portfolio,
    insert_trade_decision,        # new — added below
    get_recent_trade_decisions,   # new — added below
)

load_dotenv()
logger     = logging.getLogger(__name__)
MODEL_NAME = "deepseek-chat"

# ── Guardrail constants ───────────────────────────────────────────────────────
MAX_POSITION_PCT         = 0.30   # max 30% of cash on any single trade
MIN_CONVICTION_BUY       = 0.50   # lowered: act on any non-trivial BUY signal
MIN_CONVICTION_SELL      = 0.50   # lowered: act on any non-trivial SELL signal
MIN_CONVICTION_SELL_HELD = 0.55   # slightly higher bar to exit existing positions
MIN_ANALYST_AGREEMENT    = 1      # any single analyst signal is enough to act


def _conviction_to_allocation(conviction: float) -> float:
    """
    Maps conviction (0.65–1.0) to a cash allocation fraction (0.10–0.25).
    Linear scale so higher conviction → larger position, capped at MAX_POSITION_PCT.
    """
    if conviction <= 0.50:
        return 0.10
    if conviction >= 0.80:
        return MAX_POSITION_PCT
    # linear interpolation between 0.50→10% and 0.80→30%
    slope = (MAX_POSITION_PCT - 0.10) / (0.80 - 0.50)
    return round(0.10 + slope * (conviction - 0.50), 4)


# ══════════════════════════════════════════════════════════════════════════════
# Tools
# ══════════════════════════════════════════════════════════════════════════════

@tool
def get_account_context() -> str:
    """
    Returns current account state: cash balance, portfolio value, open positions,
    and whether the market is currently open.
    Always call this first so you understand what resources you have.
    """
    try:
        account   = t.get_account()
        cash      = float(account.cash)
        portfolio_val = float(account.portfolio_value)
        buying_power  = float(account.buying_power)
        market_open   = t.is_market_open()

        # Current holdings from local DB (source of truth for our positions)
        positions = get_portfolio()
        pos_lines = []
        if positions:
            symbols = [p.symbol for p in positions]
            prices  = t.get_latest_prices(symbols)
            for p in positions:
                cur_price = prices.get(p.symbol, p.purchasePrice)
                pl_pct    = ((cur_price - p.purchasePrice) / p.purchasePrice * 100) if p.purchasePrice else 0
                mkt_val   = cur_price * p.quantity
                pos_lines.append(
                    f"  {p.symbol:<6} {p.quantity} shares  "
                    f"avg ${p.purchasePrice:.2f}  "
                    f"now ${cur_price:.2f}  "
                    f"P/L {pl_pct:+.1f}%  "
                    f"value ${mkt_val:.0f}"
                )

        lines = [
            "=== Account Context ===\n",
            f"Cash available:   ${cash:,.2f}",
            f"Buying power:     ${buying_power:,.2f}",
            f"Portfolio value:  ${portfolio_val:,.2f}",
            f"Market open:      {'YES' if market_open else 'NO (DAY orders will queue)'}",
            "",
            f"Current holdings ({len(positions)} position(s)):",
        ]
        lines += pos_lines if pos_lines else ["  (none)"]
        return "\n".join(lines)

    except Exception as e:
        return f"ERROR fetching account: {e}"


@tool
def get_trade_opportunities() -> str:
    """
    Returns all actionable research verdicts from the last 24 hours that meet
    the minimum conviction and analyst agreement thresholds.
    These are the candidates you should consider trading.
    """
    verdicts = get_actionable_verdicts(min_conviction=MIN_CONVICTION_BUY)
    if not verdicts:
        # Fall back to checking eligible verdicts which includes macro-only
        from Trader_Team.trader_agent import get_eligible_verdicts
        verdicts = get_eligible_verdicts()
    if not verdicts:
        return "No actionable signals right now."

    lines = ["=== Trade Opportunities ===\n"]
    for v in verdicts:
        # Count how many analyst types agree with the verdict direction
        reports   = get_all_latest_reports_for_ticker(v["ticker"])
        direction = "BUY" if "BUY" in v["verdict"] else "SELL"
        agreeing  = [
            r["analyst_type"] for r in reports.values()
            if r["signal"] == direction
        ]
        agreement_count = len(agreeing)
        agreement_str   = ", ".join(agreeing) if agreeing else "none"

        # Flag whether this meets the trigger
        is_held   = get_position(v["ticker"]) is not None
        meets_trigger = (
            agreement_count >= MIN_ANALYST_AGREEMENT
            and (
                (direction == "BUY"  and v["conviction"] >= MIN_CONVICTION_BUY)
                or (direction == "SELL" and v["conviction"] >= (MIN_CONVICTION_SELL_HELD if is_held else MIN_CONVICTION_SELL))
            )
        )

        lines.append(f"── {v['ticker']}  {v['verdict']}  (conviction {v['conviction']:.0%})")
        lines.append(f"   Analysts agreeing: {agreement_count} ({agreement_str})")
        lines.append(f"   Currently held:    {'YES' if is_held else 'no'}")
        lines.append(f"   Meets trigger:     {'✓ YES' if meets_trigger else '✗ NO (below threshold)'}")
        lines.append(f"   Bull case:  {v['bull_case'][:150]}...")
        lines.append(f"   Bear case:  {v['bear_case'][:150]}...")
        lines.append(f"   Reasoning:  {v['final_reasoning'][:200]}...")
        lines.append("")

    return "\n".join(lines)


@tool
def get_current_price(ticker: str) -> str:
    """
    Fetches the latest market price for a ticker.
    Call this before sizing any trade so you know the current price.
    Input: ticker symbol e.g. 'AAPL'
    """
    try:
        price = t.get_latest_price(ticker.upper())
        return f"{ticker.upper()} current price: ${price:.2f}"
    except Exception as e:
        return f"ERROR: {e}"


@tool
def execute_buy(
    ticker:     str,
    quantity:   int,
    rationale:  str,
) -> str:
    """
    Executes a market BUY order for the given ticker and quantity.

    Guardrails enforced here (cannot be overridden):
      - quantity must be ≥ 1
      - total cost must not exceed 25% of available cash
      - conviction must be ≥ 0.65 (checked against DB verdict)
      - ≥ 2 analyst types must agree on BUY direction

    Args:
        ticker:    Stock ticker e.g. 'NVDA'
        quantity:  Number of whole shares to buy (integer, no fractional)
        rationale: 2-3 sentences explaining why you are buying this size.
                   Must reference the conviction score and analyst agreement.
    """
    ticker = ticker.upper().strip()

    # ── Guardrail 1: quantity sanity ──────────────────────────────────────────
    if not isinstance(quantity, int) or quantity < 1:
        return f"BLOCKED: quantity must be a positive integer — got {quantity}"

    # ── Guardrail 2: verdict + conviction + analyst agreement ─────────────────
    verdicts = get_actionable_verdicts(min_conviction=MIN_CONVICTION_BUY)
    verdict  = next((v for v in verdicts if v["ticker"] == ticker), None)
    if not verdict:
        return (
            f"BLOCKED: no actionable BUY verdict for {ticker} "
            f"with conviction ≥ {MIN_CONVICTION_BUY:.0%}. "
            f"Cannot buy without researcher approval."
        )
    if "BUY" not in verdict["verdict"]:
        return f"BLOCKED: verdict for {ticker} is {verdict['verdict']}, not BUY/STRONG_BUY."

    reports   = get_all_latest_reports_for_ticker(ticker)
    agreeing  = [r["analyst_type"] for r in reports.values() if r["signal"] == "BUY"]
    if len(agreeing) < MIN_ANALYST_AGREEMENT:
        return (
            f"BLOCKED: only {len(agreeing)} analyst type(s) agree on BUY for {ticker}. "
            f"Need ≥ {MIN_ANALYST_AGREEMENT}. Agreeing: {agreeing}"
        )

    # ── Guardrail 3: position size cap ────────────────────────────────────────
    try:
        account      = t.get_account()
        cash         = float(account.cash)
        price        = t.get_latest_price(ticker)
        trade_cost   = price * quantity
        max_allowed  = cash * MAX_POSITION_PCT

        if trade_cost > max_allowed:
            max_shares = int(max_allowed // price)
            return (
                f"BLOCKED: ${trade_cost:.0f} ({quantity} × ${price:.2f}) exceeds "
                f"the 25% cash cap of ${max_allowed:.0f}. "
                f"Max allowed quantity at current price: {max_shares} shares."
            )
        if trade_cost > cash:
            return (
                f"BLOCKED: insufficient cash. "
                f"${trade_cost:.0f} needed, ${cash:.0f} available."
            )
    except Exception as e:
        return f"ERROR checking account balance: {e}"

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        order    = t.buy_stock(ticker, quantity)
        order_id = str(order.id)

        # Record in DB immediately as pending
        local_id = create_order(
            symbol          = ticker,
            price           = price,
            quantity        = quantity,
            trade_type      = "buy",
            alpaca_order_id = order_id,
        )
        set_alpaca_order_id(local_id, order_id)

        # Poll for fill (Alpaca paper fills are near-instant during market hours)
        fill = t.wait_for_fill(order_id, timeout=15)

        if fill["status"] == "filled":
            filled_price = fill["filled_price"]
            fill_order(local_id)
            # Update local portfolio
            existing = get_position(ticker)
            if existing:
                new_qty   = existing["quantity"] + quantity
                avg_price = (
                    (existing["purchasePrice"] * existing["quantity"] + filled_price * quantity)
                    / new_qty
                )
                upsert_position(ticker, round(avg_price, 4), new_qty, datetime.now().strftime("%Y-%m-%d"))
            else:
                upsert_position(ticker, filled_price, quantity, datetime.now().strftime("%Y-%m-%d"))

            # Log the trade decision
            insert_trade_decision(
                ticker       = ticker,
                action       = "BUY",
                quantity     = quantity,
                price        = filled_price,
                conviction   = verdict["conviction"],
                rationale    = rationale,
                verdict_id   = verdict["id"],
                alpaca_id    = order_id,
                status       = "filled",
            )
            return (
                f"BUY FILLED: {quantity} × {ticker} @ ${filled_price:.2f}  "
                f"Total: ${filled_price * quantity:.2f}  "
                f"Alpaca order: {order_id}"
            )
        else:
            insert_trade_decision(
                ticker       = ticker,
                action       = "BUY",
                quantity     = quantity,
                price        = price,
                conviction   = verdict["conviction"],
                rationale    = rationale,
                verdict_id   = verdict["id"],
                alpaca_id    = order_id,
                status       = fill["status"],
            )
            return (
                f"BUY SUBMITTED (not yet filled): {quantity} × {ticker}  "
                f"Status: {fill['status']}  Alpaca order: {order_id}"
            )

    except Exception as e:
        return f"ERROR executing buy for {ticker}: {e}"


@tool
def execute_sell(
    ticker:    str,
    quantity:  int,
    rationale: str,
) -> str:
    """
    Executes a market SELL order for the given ticker and quantity.

    Guardrails enforced here:
      - Can only sell shares you actually own (checked against portfolio)
      - quantity cannot exceed your held quantity
      - conviction must be ≥ 0.65 (or 0.70 for existing positions)
      - ≥ 2 analyst types must agree on SELL direction

    Args:
        ticker:    Stock ticker e.g. 'NVDA'
        quantity:  Number of whole shares to sell (use full held quantity to exit fully)
        rationale: 2-3 sentences explaining why you are selling this amount.
    """
    ticker = ticker.upper().strip()

    # ── Guardrail 1: must own the stock ──────────────────────────────────────
    position = get_position(ticker)
    if not position:
        return f"BLOCKED: no position in {ticker}. Cannot sell shares you don't own."

    held_qty = position["quantity"]
    if quantity < 1:
        return f"BLOCKED: quantity must be ≥ 1 — got {quantity}"
    if quantity > held_qty:
        return (
            f"BLOCKED: you only hold {held_qty} shares of {ticker}. "
            f"Cannot sell {quantity}."
        )

    # ── Guardrail 2: verdict + conviction + analyst agreement ─────────────────
    verdicts     = get_actionable_verdicts(min_conviction=MIN_CONVICTION_SELL_HELD)
    verdict      = next((v for v in verdicts if v["ticker"] == ticker), None)
    min_conv_req = MIN_CONVICTION_SELL_HELD  # stricter for held positions

    if not verdict or "SELL" not in verdict["verdict"]:
        # Check if there's a weaker verdict that still meets the bar
        all_v = get_actionable_verdicts(min_conviction=0.0)
        verdict = next((v for v in all_v if v["ticker"] == ticker), None)
        if not verdict or "SELL" not in verdict["verdict"]:
            return (
                f"BLOCKED: no SELL verdict for {ticker}. "
                f"Cannot sell without researcher team recommending SELL/STRONG_SELL."
            )
        if verdict["conviction"] < min_conv_req:
            return (
                f"BLOCKED: SELL verdict for {ticker} has conviction {verdict['conviction']:.0%}, "
                f"below the {min_conv_req:.0%} minimum required to sell a held position."
            )

    reports  = get_all_latest_reports_for_ticker(ticker)
    agreeing = [r["analyst_type"] for r in reports.values() if r["signal"] == "SELL"]
    if len(agreeing) < MIN_ANALYST_AGREEMENT:
        return (
            f"BLOCKED: only {len(agreeing)} analyst type(s) agree on SELL for {ticker}. "
            f"Need ≥ {MIN_ANALYST_AGREEMENT}. Agreeing: {agreeing}"
        )

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        price    = t.get_latest_price(ticker)
        order    = t.sell_stock(ticker, quantity)
        order_id = str(order.id)

        local_id = create_order(
            symbol          = ticker,
            price           = price,
            quantity        = quantity,
            trade_type      = "sell",
            alpaca_order_id = order_id,
        )
        set_alpaca_order_id(local_id, order_id)

        fill = t.wait_for_fill(order_id, timeout=15)

        if fill["status"] == "filled":
            filled_price = fill["filled_price"]
            fill_order(local_id)
            # Update local portfolio
            new_qty = held_qty - quantity
            if new_qty == 0:
                upsert_position(ticker, 0.0, 0, "")   # removes from portfolio
            else:
                upsert_position(ticker, position["purchasePrice"], new_qty,
                                position["purchaseDate"])

            pl = (filled_price - position["purchasePrice"]) * quantity
            pl_pct = ((filled_price - position["purchasePrice"]) / position["purchasePrice"] * 100)

            insert_trade_decision(
                ticker       = ticker,
                action       = "SELL",
                quantity     = quantity,
                price        = filled_price,
                conviction   = verdict["conviction"],
                rationale    = rationale,
                verdict_id   = verdict["id"],
                alpaca_id    = order_id,
                status       = "filled",
            )
            return (
                f"SELL FILLED: {quantity} × {ticker} @ ${filled_price:.2f}  "
                f"P/L on this lot: ${pl:+.2f} ({pl_pct:+.1f}%)  "
                f"Alpaca order: {order_id}"
            )
        else:
            insert_trade_decision(
                ticker       = ticker,
                action       = "SELL",
                quantity     = quantity,
                price        = price,
                conviction   = verdict["conviction"],
                rationale    = rationale,
                verdict_id   = verdict["id"],
                alpaca_id    = order_id,
                status       = fill["status"],
            )
            return (
                f"SELL SUBMITTED (not yet filled): {quantity} × {ticker}  "
                f"Status: {fill['status']}  Alpaca order: {order_id}"
            )

    except Exception as e:
        return f"ERROR executing sell for {ticker}: {e}"


@tool
def skip_trade(ticker: str, reason: str) -> str:
    """
    Records a deliberate decision NOT to trade a ticker this run.
    Call this for every opportunity you reviewed but chose not to act on.
    This keeps a clean audit trail of all decisions.

    Args:
        ticker: Stock ticker
        reason: Why you are not trading this opportunity right now.
    """
    insert_trade_decision(
        ticker     = ticker,
        action     = "SKIP",
        quantity   = 0,
        price      = 0.0,
        conviction = 0.0,
        rationale  = reason,
        verdict_id = None,
        alpaca_id  = None,
        status     = "skipped",
    )
    logger.info(f"[trader] SKIP {ticker}: {reason}")
    return f"Recorded SKIP for {ticker}."


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an aggressive trader managing a paper Alpaca account. Your single goal is to
beat the S&P 500. Idle cash is your enemy — uninvested cash earns nothing and
guarantees underperformance.

MINDSET:
  - Cash sitting idle is a losing position. Every day uninvested = guaranteed underperformance.
  - The research team filtered out weak signals. Everything you see passed analyst +
    researcher review. Trust it and act on it.
  - A calculated risk on a 65% conviction signal beats holding $90,000 in cash.
  - Spread capital across multiple opportunities — diversification reduces single-stock risk.

Your process every run:
1. Call get_account_context() — check cash balance, existing positions, market status.
2. Call get_trade_opportunities() — your pre-vetted signal list, sorted by conviction.
3. For EACH opportunity (highest conviction first):
   a. Call get_current_price(ticker) — never guess the price.
   b. Calculate shares: floor(cash_allocation / price).
   c. Call execute_buy() or execute_sell(). DEFAULT IS TO ACT.
4. Call skip_trade() only if you have a SPECIFIC reason to skip (e.g. already hold
   a large position in that sector, price moved sharply against the signal today).

CAPITAL DEPLOYMENT — most important rule:
  - If cash > 50% of total portfolio value, you MUST deploy capital this run.
  - Target: get cash below 20% of portfolio value by end of this run.
  - Spread buys across 3-6 different stocks — never concentrate in just one.
  - Work through the full opportunity list until cash is deployed.

Position sizing per trade (tool enforces 30% hard cap):
  - Conviction 0.50-0.59 → 10% of available cash
  - Conviction 0.60-0.69 → 15% of available cash
  - Conviction 0.70-0.79 → 20% of available cash
  - Conviction 0.80+     → 30% of available cash
  - shares = floor(target_dollar_amount / current_price)

Sell rules:
  - STRONG_SELL: exit 100% of position immediately.
  - SELL: exit 50-75% of position.
  - Never sell to free up cash for buys — only sell on a SELL signal.

Hard limits enforced by tools (cannot bypass):
  - Max 30% of cash per single trade.
  - Cannot sell shares you do not own.
  - Must call get_current_price() before every trade.
"""


# ── Eligibility filter (runs before agent) ────────────────────────────────────

def get_eligible_verdicts() -> list[dict]:
    """
    Returns all verdicts that meet the (now low) conviction threshold.
    Also pulls macro-only analyst signals for tickers that have no
    researcher verdict yet — so macro events can directly trigger trades.
    """
    from database import SessionLocal, AnalystReport, AnalystSignal
    from datetime import timedelta

    eligible = []
    seen     = set()

    # ── Path 1: researcher verdicts ───────────────────────────────────
    verdicts = get_actionable_verdicts(min_conviction=MIN_CONVICTION_BUY)
    for v in verdicts:
        ticker    = v["ticker"]
        direction = "BUY" if "BUY" in v["verdict"] else "SELL"
        reports   = get_all_latest_reports_for_ticker(ticker)
        agreeing  = [r["analyst_type"] for r in reports.values() if r["signal"] == direction]
        is_held   = get_position(ticker) is not None
        min_conv  = MIN_CONVICTION_SELL_HELD if (direction == "SELL" and is_held) else MIN_CONVICTION_BUY

        if v["conviction"] >= min_conv:
            v["_agreeing_analysts"] = agreeing
            v["_is_held"]           = is_held
            v["_source"]            = "researcher"
            eligible.append(v)
            seen.add(ticker)

    # ── Path 2: macro-only signals (no researcher verdict needed) ─────
    # High-conviction macro signals (e.g. XOM BUY on oil shock) should
    # be tradeable even if XOM was never in the ticker queue.
    cutoff  = datetime.utcnow() - timedelta(hours=24)
    session = SessionLocal()
    try:
        macro_rows = (
            session.query(AnalystReport)
            .filter(
                AnalystReport.analyst_type == "macro",
                AnalystReport.confidence   >= 0.65,   # higher bar for macro-only
                AnalystReport.signal       != AnalystSignal.HOLD,
                AnalystReport.created_at   >= cutoff,
            )
            .order_by(AnalystReport.confidence.desc())
            .all()
        )
    finally:
        session.close()

    for row in macro_rows:
        if row.ticker in seen:
            continue   # already covered by a researcher verdict
        is_held = get_position(row.ticker) is not None
        eligible.append({
            "id":               None,
            "ticker":           row.ticker,
            "verdict":          row.signal.value,
            "conviction":       row.confidence,
            "bull_case":        row.summary,
            "bear_case":        "",
            "final_reasoning":  row.summary,
            "key_risks":        [],
            "key_catalysts":    [],
            "_agreeing_analysts": ["macro"],
            "_is_held":           is_held,
            "_source":            "macro_only",
        })
        seen.add(row.ticker)

    # Sort by conviction descending so agent tackles best signals first
    eligible.sort(key=lambda x: x["conviction"], reverse=True)
    return eligible


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_trader_agent():
    model = ChatDeepSeek(
        model       = MODEL_NAME,
        temperature = 0.1,     # low — trading decisions should be consistent
        max_tokens  = 2048,
        max_retries = 3,
    )
    return create_agent(
        model,
        tools         = [
            get_account_context,
            get_trade_opportunities,
            get_current_price,
            execute_buy,
            execute_sell,
            skip_trade,
        ],
        system_prompt = SYSTEM_PROMPT,
        name          = "trader_agent",
    )


# ── Public interface ──────────────────────────────────────────────────────────

def run_trader() -> dict:
    """
    Runs the trader agent for one pipeline cycle.
    Returns a summary of actions taken.
    """
    eligible = get_eligible_verdicts()

    if not eligible:
        logger.info("[trader] No eligible verdicts — nothing to trade this run.")
        return {
            "trades_executed": 0,
            "skipped":         0,
            "error":           None,
            "message":         "No verdicts met the conviction + analyst agreement threshold.",
        }

    logger.info(f"[trader] {len(eligible)} eligible verdict(s) — invoking agent...")

    agent = build_trader_agent()
    try:
        agent.invoke({
            "messages": [{
                "role":    "user",
                "content": (
                    f"Run the trading cycle. There are {len(eligible)} eligible "
                    f"trade opportunity/opportunities ready to review. "
                    f"Check the account, review each opportunity, and execute the best trades."
                ),
            }]
        })
    except Exception as e:
        logger.error(f"[trader] Agent failed: {e}")
        return {"trades_executed": 0, "skipped": 0, "error": str(e), "message": "Agent error"}

    # Summarise what happened from the trade log
    decisions = get_recent_trade_decisions(minutes=10)
    executed  = [d for d in decisions if d["action"] in ("BUY", "SELL") and d["status"] == "filled"]
    skipped   = [d for d in decisions if d["action"] == "SKIP"]

    for d in executed:
        logger.info(
            f"[trader] {d['action']} {d['quantity']} × {d['ticker']} "
            f"@ ${d['price']:.2f}  (conviction {d['conviction']:.0%})"
        )

    return {
        "trades_executed": len(executed),
        "skipped":         len(skipped),
        "error":           None,
        "decisions":       decisions,
        "message":         f"{len(executed)} trade(s) executed, {len(skipped)} skipped.",
    }


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from database import Base, engine
    Base.metadata.create_all(bind=engine)

    result = run_trader()
    print(f"\n{result['message']}")
    if result.get("decisions"):
        print("\nDecisions this run:")
        for d in result["decisions"]:
            print(f"  {d['action']:<6} {d['ticker']:<8} {d.get('quantity',0):>4} shares  {d['rationale'][:60]}...")