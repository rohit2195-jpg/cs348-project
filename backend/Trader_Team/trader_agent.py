"""
Trader_Team/trader_agent.py
══════════════════════════════════════════════════════════════════════════════
Deterministic rule-based trade executor — NO LLM.

Given a list of eligible verdicts, this executes ALL of them mechanically:
  - BUY verdicts: divide available cash equally among all BUY tickers,
    allocate proportionally to conviction, buy as many whole shares as possible.
  - SELL verdicts on held positions: sell 100% of the position.
  - SELL verdicts on stocks not held: skip (can't short).

No LLM means:
  - No skipping because "I want to be cautious"
  - No concentration in 1-2 stocks
  - No running out of iterations
  - Deterministic, fast, and fully auditable

Capital rules:
  - Cash is split across ALL BUY opportunities (weighted by conviction).
  - Never go negative (trade cost checked before every order).
  - Minimum 1 share per trade — skip if allocation < 1 share at current price.
══════════════════════════════════════════════════════════════════════════════
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
from datetime import datetime
from dotenv import load_dotenv

import trading as t
from database import (
    get_actionable_verdicts,
    get_position,
    create_order,
    fill_order,
    set_alpaca_order_id,
    upsert_position,
    get_portfolio,
    insert_trade_decision,
    get_recent_trade_decisions,
    SessionLocal,
    AnalystReport,
    AnalystSignal,
    get_trade_ready_tickers,
)

load_dotenv()
logger = logging.getLogger(__name__)

# Minimum conviction to act on a verdict
MIN_CONVICTION = 0.62
MACRO_ONLY_MIN_CONFIDENCE = 0.75

# Keep this much cash as reserve (never invest 100%)
CASH_RESERVE_PCT = 0.10

# Execution/risk controls
MAX_NEW_BUYS_PER_RUN = 3
MAX_TOTAL_BUY_IDEAS = 6
MAX_POSITION_PCT = 0.40


# ── Eligibility ───────────────────────────────────────────────────────────────

def get_eligible_verdicts() -> list[dict]:
    """
    Returns one entry per ticker (highest conviction), sorted conviction desc.
    Includes both researcher verdicts and macro-only signals.
    """
    from datetime import timedelta

    eligible = []
    seen     = set()
    trade_ready_tickers = get_trade_ready_tickers()

    # Path 1: researcher verdicts — deduplicated to highest conviction per ticker
    verdicts = get_actionable_verdicts(min_conviction=MIN_CONVICTION, hours=30)
    best: dict[str, dict] = {}
    for v in verdicts:
        ticker = v["ticker"]
        if trade_ready_tickers and ticker not in trade_ready_tickers:
            continue
        if ticker not in best or v["conviction"] > best[ticker]["conviction"]:
            best[ticker] = v

    for ticker, v in best.items():
        direction = "BUY" if "BUY" in v["verdict"] else "SELL"
        is_held   = get_position(ticker) is not None
        v["_is_held"]  = is_held
        v["_source"]   = "researcher"
        v["_direction"] = direction
        eligible.append(v)
        seen.add(ticker)

    # Path 2: macro-only signals not covered by a researcher verdict
    cutoff  = datetime.utcnow() - timedelta(hours=48)
    session = SessionLocal()
    try:
        macro_rows = (
            session.query(AnalystReport)
            .filter(
                AnalystReport.analyst_type == "macro",
                AnalystReport.confidence   >= MACRO_ONLY_MIN_CONFIDENCE,
                AnalystReport.signal       != AnalystSignal.HOLD,
                AnalystReport.created_at   >= cutoff,
            )
            .order_by(AnalystReport.confidence.desc())
            .all()
        )
    finally:
        session.close()

    macro_best: dict[str, AnalystReport] = {}
    for row in macro_rows:
        if row.ticker in seen:
            continue
        if row.ticker not in macro_best or row.confidence > macro_best[row.ticker].confidence:
            macro_best[row.ticker] = row

    for ticker, row in macro_best.items():
        if trade_ready_tickers and ticker not in trade_ready_tickers:
            continue
        direction = row.signal.value
        is_held   = get_position(ticker) is not None
        eligible.append({
            "id":          None,
            "ticker":      ticker,
            "verdict":     direction,
            "conviction":  row.confidence,
            "bull_case":   row.summary,
            "bear_case":   "",
            "final_reasoning": row.summary,
            "key_risks":   [],
            "key_catalysts": [],
            "_is_held":    is_held,
            "_source":     "macro_only",
            "_direction":  direction,
        })
        seen.add(ticker)

    eligible.sort(key=lambda x: x["conviction"], reverse=True)
    return eligible


# ── Core execution ────────────────────────────────────────────────────────────

def _execute_buy(ticker: str, conviction: float, dollar_allocation: float,
                 verdict_id, rationale: str, allow_cap_override: bool = False) -> dict:
    """Buy as many whole shares as the allocation allows. Returns result dict."""
    try:
        price    = t.get_latest_price(ticker)
        account  = t.get_account()
        cash     = float(account.cash)
        portfolio_value = float(account.portfolio_value)
        existing = get_position(ticker)
        existing_value = (existing["quantity"] * price) if existing else 0.0
        position_cap = max(0.0, portfolio_value * MAX_POSITION_PCT - existing_value)
        if allow_cap_override:
            position_cap = max(position_cap, cash)
        capped_allocation = min(dollar_allocation, cash, position_cap)
        shares   = int(capped_allocation // price)

        if shares < 1:
            logger.info(f"[trader] SKIP BUY {ticker}: allocation ${capped_allocation:.0f} < 1 share at ${price:.2f}")
            insert_trade_decision(
                ticker=ticker, action="SKIP", quantity=0, price=price,
                conviction=conviction,
                rationale=(
                    f"Allocation ${capped_allocation:.0f} too small for 1 share at ${price:.2f}. "
                    f"Position cap is {MAX_POSITION_PCT:.0%} of portfolio."
                ),
                verdict_id=verdict_id, alpaca_id=None, status="skipped"
            )
            return {"ticker": ticker, "action": "SKIP", "reason": "allocation < 1 share or position capped"}

        cost     = price * shares
        if cost > cash:
            shares = int(cash // price)
            if shares < 1:
                return {"ticker": ticker, "action": "SKIP", "reason": "insufficient cash"}
            cost = price * shares

        order    = t.buy_stock(ticker, shares)
        order_id = str(order.id)
        local_id = create_order(ticker, price, shares, "buy", order_id)
        set_alpaca_order_id(local_id, order_id)

        fill = t.wait_for_fill(order_id, timeout=15)
        if fill["status"] == "filled":
            fp = fill["filled_price"]
            fill_order(local_id)
            if existing:
                new_qty   = existing["quantity"] + shares
                avg_price = (existing["purchasePrice"] * existing["quantity"] + fp * shares) / new_qty
                upsert_position(ticker, round(avg_price, 4), new_qty, datetime.now().strftime("%Y-%m-%d"))
            else:
                upsert_position(ticker, fp, shares, datetime.now().strftime("%Y-%m-%d"))

            insert_trade_decision(
                ticker=ticker, action="BUY", quantity=shares, price=fp,
                conviction=conviction, rationale=rationale,
                verdict_id=verdict_id, alpaca_id=order_id, status="filled"
            )
            logger.info(f"[trader] BUY FILLED {shares}×{ticker} @ ${fp:.2f}  total=${fp*shares:.0f}")
            return {"ticker": ticker, "action": "BUY", "shares": shares,
                    "price": fp, "total": fp * shares, "status": "filled"}
        else:
            insert_trade_decision(
                ticker=ticker, action="BUY", quantity=shares, price=price,
                conviction=conviction, rationale=rationale,
                verdict_id=verdict_id, alpaca_id=order_id, status=fill["status"]
            )
            return {"ticker": ticker, "action": "BUY", "shares": shares,
                    "price": price, "status": fill["status"]}

    except Exception as e:
        logger.error(f"[trader] BUY ERROR {ticker}: {e}")
        return {"ticker": ticker, "action": "ERROR", "reason": str(e)}


def _queue_buy(ticker: str, conviction: float, dollar_allocation: float,
               verdict_id, rationale: str, available_cash: float,
               allow_cap_override: bool = False) -> dict:
    """Queue a next-open buy without submitting an order."""
    try:
        existing_queue = next(
            (
                d for d in get_recent_trade_decisions(minutes=24 * 60)
                if d["ticker"] == ticker and d["action"] == "BUY" and d["status"] == "queued"
            ),
            None,
        )
        if existing_queue:
            logger.info("[trader] Existing queued BUY for %s found — skipping duplicate queue", ticker)
            return {
                "ticker": ticker,
                "action": "BUY",
                "shares": existing_queue["quantity"],
                "price": existing_queue["price"],
                "total": round(existing_queue["quantity"] * existing_queue["price"], 2),
                "status": "queued",
            }

        price = t.get_latest_price(ticker)
        account = t.get_account()
        portfolio_value = float(account.portfolio_value)
        existing = get_position(ticker)
        existing_value = (existing["quantity"] * price) if existing else 0.0
        position_cap = max(0.0, portfolio_value * MAX_POSITION_PCT - existing_value)
        if allow_cap_override:
            position_cap = max(position_cap, available_cash)
        capped_allocation = min(dollar_allocation, available_cash, position_cap)
        shares = int(capped_allocation // price)
        if shares < 1:
            insert_trade_decision(
                ticker=ticker, action="SKIP", quantity=0, price=price,
                conviction=conviction,
                rationale=(
                    f"Queued allocation ${capped_allocation:.0f} too small for 1 share at ${price:.2f}. "
                    f"Position cap is {MAX_POSITION_PCT:.0%} of portfolio."
                ),
                verdict_id=verdict_id, alpaca_id=None, status="skipped"
            )
            return {"ticker": ticker, "action": "SKIP", "reason": "allocation < 1 share or position capped"}

        insert_trade_decision(
            ticker=ticker, action="BUY", quantity=shares, price=price,
            conviction=conviction, rationale=rationale,
            verdict_id=verdict_id, alpaca_id=None, status="queued"
        )
        logger.info("[trader] QUEUED BUY %s×%s @ ~$%.2f for next open", shares, ticker, price)
        return {
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": price,
            "total": round(price * shares, 2),
            "status": "queued",
        }
    except Exception as e:
        logger.error(f"[trader] QUEUE BUY ERROR {ticker}: {e}")
        return {"ticker": ticker, "action": "ERROR", "reason": str(e)}


def _execute_sell(ticker: str, conviction: float, verdict_id, rationale: str) -> dict:
    """Sell 100% of held position."""
    position = get_position(ticker)
    if not position:
        logger.info(f"[trader] SKIP SELL {ticker}: not held")
        insert_trade_decision(
            ticker=ticker, action="SKIP", quantity=0, price=0,
            conviction=conviction, rationale="SELL signal but not held — cannot short",
            verdict_id=verdict_id, alpaca_id=None, status="skipped"
        )
        return {"ticker": ticker, "action": "SKIP", "reason": "not held"}

    shares = position["quantity"]
    try:
        price    = t.get_latest_price(ticker)
        order    = t.sell_stock(ticker, shares)
        order_id = str(order.id)
        local_id = create_order(ticker, price, shares, "sell", order_id)
        set_alpaca_order_id(local_id, order_id)

        fill = t.wait_for_fill(order_id, timeout=15)
        if fill["status"] == "filled":
            fp  = fill["filled_price"]
            pl  = (fp - position["purchasePrice"]) * shares
            fill_order(local_id)
            upsert_position(ticker, 0.0, 0, "")

            insert_trade_decision(
                ticker=ticker, action="SELL", quantity=shares, price=fp,
                conviction=conviction, rationale=rationale,
                verdict_id=verdict_id, alpaca_id=order_id, status="filled"
            )
            logger.info(f"[trader] SELL FILLED {shares}×{ticker} @ ${fp:.2f}  P/L=${pl:+.0f}")
            return {"ticker": ticker, "action": "SELL", "shares": shares,
                    "price": fp, "pl": pl, "status": "filled"}
        else:
            insert_trade_decision(
                ticker=ticker, action="SELL", quantity=shares, price=price,
                conviction=conviction, rationale=rationale,
                verdict_id=verdict_id, alpaca_id=order_id, status=fill["status"]
            )
            return {"ticker": ticker, "action": "SELL", "shares": shares,
                    "price": price, "status": fill["status"]}

    except Exception as e:
        logger.error(f"[trader] SELL ERROR {ticker}: {e}")
        return {"ticker": ticker, "action": "ERROR", "reason": str(e)}


def _queue_sell(ticker: str, conviction: float, verdict_id, rationale: str) -> dict:
    position = get_position(ticker)
    if not position:
        logger.info(f"[trader] SKIP QUEUE SELL {ticker}: not held")
        insert_trade_decision(
            ticker=ticker, action="SKIP", quantity=0, price=0,
            conviction=conviction, rationale="Queued SELL signal but not held — cannot queue sell",
            verdict_id=verdict_id, alpaca_id=None, status="skipped"
        )
        return {"ticker": ticker, "action": "SKIP", "reason": "not held"}

    existing_queue = next(
        (
            d for d in get_recent_trade_decisions(minutes=24 * 60)
            if d["ticker"] == ticker and d["action"] == "SELL" and d["status"] == "queued"
        ),
        None,
    )
    if existing_queue:
        logger.info("[trader] Existing queued SELL for %s found — skipping duplicate queue", ticker)
        return {
            "ticker": ticker,
            "action": "SELL",
            "shares": existing_queue["quantity"],
            "price": existing_queue["price"],
            "status": "queued",
        }

    try:
        price = t.get_latest_price(ticker)
    except Exception:
        price = position["purchasePrice"]

    insert_trade_decision(
        ticker=ticker, action="SELL", quantity=position["quantity"], price=price,
        conviction=conviction, rationale=rationale,
        verdict_id=verdict_id, alpaca_id=None, status="queued"
    )
    logger.info("[trader] QUEUED SELL %s×%s @ ~$%.2f for next open", position["quantity"], ticker, price)
    return {
        "ticker": ticker,
        "action": "SELL",
        "shares": position["quantity"],
        "price": price,
        "status": "queued",
    }


# ── Main entry point ──────────────────────────────────────────────────────────


# Minimum cash needed before we bother trying to buy
MIN_CASH_TO_BUY = 500   # $500 — enough for at least a few shares of most stocks

# When rebalancing, target freeing up this much of portfolio value
REBALANCE_TARGET_PCT = 0.20   # sell enough to free 20% of portfolio value


def _rebalance_if_needed(buy_tickers: set[str]) -> list[dict]:
    """
    If cash is too low to meaningfully buy anything, sell held positions
    that are NOT in the current BUY list to free up capital.

    Rotation logic:
      1. If cash >= MIN_CASH_TO_BUY — no rebalancing needed.
      2. Otherwise: look at held positions not in buy_tickers.
         Sort by P/L % descending (sell winners first — lock in profits).
         Sell enough to reach REBALANCE_TARGET_PCT of portfolio value.
      3. If all held positions ARE in buy_tickers (full overlap),
         sell the lowest-conviction held positions to rotate into higher ones.
    """
    results = []

    try:
        account   = t.get_account()
        cash      = float(account.cash)
        port_val  = float(account.portfolio_value)
    except Exception as e:
        logger.error(f"[trader] Could not fetch account for rebalance: {e}")
        return results

    if cash >= MIN_CASH_TO_BUY:
        logger.info(f"[trader] Cash ${cash:,.0f} is sufficient — no rebalancing needed")
        return results

    target_cash = port_val * REBALANCE_TARGET_PCT
    logger.info(
        f"[trader] Cash ${cash:,.0f} below ${MIN_CASH_TO_BUY} minimum. "
        f"Rebalancing to free ~${target_cash:,.0f} (20% of ${port_val:,.0f} portfolio)"
    )

    positions = get_portfolio()
    if not positions:
        logger.info("[trader] No positions to sell for rebalancing")
        return results

    # Get current prices for all held positions
    held_symbols = [p.symbol for p in positions]
    try:
        prices = t.get_latest_prices(held_symbols)
    except Exception:
        prices = {}

    # Score each position for selling:
    # Prefer selling positions NOT in the current buy list,
    # then sort by P/L % descending (sell best performers first)
    candidates = []
    for p in positions:
        cur_price = prices.get(p.symbol, p.purchasePrice)
        pl_pct    = ((cur_price - p.purchasePrice) / p.purchasePrice * 100) if p.purchasePrice else 0
        mkt_value = cur_price * p.quantity
        in_buy    = p.symbol in buy_tickers

        candidates.append({
            "symbol":    p.symbol,
            "quantity":  p.quantity,
            "avg_price": p.purchasePrice,
            "cur_price": cur_price,
            "pl_pct":    pl_pct,
            "mkt_value": mkt_value,
            "in_buy":    in_buy,
        })

    # Sort: non-buy positions first (rotate out), then by P/L descending
    candidates.sort(key=lambda x: (x["in_buy"], -x["pl_pct"]))

    freed = 0.0
    for c in candidates:
        if freed >= target_cash:
            break

        logger.info(
            f"[trader] REBALANCE selling {c['symbol']} "
            f"(P/L {c['pl_pct']:+.1f}%, {'in buy list' if c['in_buy'] else 'not in buy list'})"
        )
        result = _execute_sell(
            ticker     = c["symbol"],
            conviction = 0.5,
            verdict_id = None,
            rationale  = (
                f"Portfolio rebalance: cash ${cash:,.0f} below ${MIN_CASH_TO_BUY} minimum. "
                f"Selling to free capital for higher-conviction opportunities. "
                f"P/L on this position: {c['pl_pct']:+.1f}%."
            ),
        )
        results.append(result)
        if result.get("status") == "filled":
            freed += c["mkt_value"]

    if freed > 0:
        logger.info(f"[trader] Rebalance complete — freed ~${freed:,.0f}")
    else:
        logger.warning("[trader] Rebalance attempted but no positions sold")

    return results


def _select_buy_candidates(buys: list[dict]) -> list[dict]:
    """
    Prioritize conviction and avoid over-seeding too many new names in one run.
    Existing holdings may be topped up only if they are among the strongest ideas.
    """
    if not buys:
        return []

    held = sorted([b for b in buys if b.get("_is_held")], key=lambda x: x["conviction"], reverse=True)
    new  = sorted([b for b in buys if not b.get("_is_held")], key=lambda x: x["conviction"], reverse=True)

    selected_new  = new[:MAX_NEW_BUYS_PER_RUN]
    remaining_cap = max(0, MAX_TOTAL_BUY_IDEAS - len(selected_new))
    selected_held = held[:remaining_cap]
    selected      = sorted(selected_new + selected_held, key=lambda x: x["conviction"], reverse=True)

    logger.info(
        "[trader] selected %s buy idea(s): %s",
        len(selected),
        ", ".join(f"{item['ticker']}({item['conviction']:.0%})" for item in selected),
    )
    return selected


def run_trader() -> dict:
    """
    Deterministic execution of reviewed, trade-ready verdicts.
    No LLM — just math and market orders.
    """
    eligible = get_eligible_verdicts()
    if not eligible:
        logger.info("[trader] No eligible verdicts.")
        return {"trades_executed": 0, "skipped": 0, "error": None,
                "message": "No verdicts met the threshold.", "decisions": []}

    logger.info(f"[trader] {len(eligible)} eligible verdict(s) — executing all...")

    # ── Sell pass first (frees up cash before buying) ─────────────────────────
    sells = [v for v in eligible if "SELL" in v.get("_direction", v.get("verdict", ""))]
    buys  = [v for v in eligible if "BUY"  in v.get("_direction", v.get("verdict", ""))]
    market_open = t.is_market_open()

    results = []
    for v in sells:
        rationale = f"SELL signal: {v['verdict']} ({v['conviction']:.0%} conviction). {v.get('final_reasoning','')[:100]}"
        if market_open:
            result = _execute_sell(v["ticker"], v["conviction"], v.get("id"), rationale)
        else:
            result = _queue_sell(v["ticker"], v["conviction"], v.get("id"), rationale)
        results.append(result)

    # ── Rebalance pass — sell non-buy positions if cash is too low ───────────
    buy_ticker_set = {v["ticker"] for v in buys}
    if market_open:
        rebalance_results = _rebalance_if_needed(buy_ticker_set)
        results.extend(rebalance_results)

    # ── Buy pass — split available cash across all BUY tickers ───────────────
    buys = _select_buy_candidates(buys)

    if buys:
        account      = t.get_account()
        cash         = float(account.cash)
        investable   = cash * (1 - CASH_RESERVE_PCT)
        planning_cash = investable

        # Weight each ticker by conviction so higher-conviction gets more capital
        total_conviction = sum(v["conviction"] for v in buys)
        allocations      = {
            v["ticker"]: investable * (v["conviction"] / total_conviction)
            for v in buys
        }

        logger.info(
            f"[trader] Cash: ${cash:,.0f}  Investable: ${investable:,.0f}  "
            f"Split across {len(buys)} BUY ticker(s)"
        )
        queued_or_filled = 0
        for v in buys:
            alloc     = allocations[v["ticker"]]
            rationale = (
                f"BUY signal: {v['verdict']} ({v['conviction']:.0%} conviction). "
                f"Allocated ${alloc:,.0f} of ${investable:,.0f} investable cash "
                f"({v['conviction']/total_conviction:.0%} weight). "
                f"{v.get('final_reasoning','')[:80]}"
            )
            if market_open:
                result = _execute_buy(v["ticker"], v["conviction"], alloc, v.get("id"), rationale)
            else:
                result = _queue_buy(v["ticker"], v["conviction"], alloc, v.get("id"), rationale, planning_cash)
            results.append(result)
            if result.get("status") in {"filled", "queued"}:
                queued_or_filled += 1
                if not market_open:
                    planning_cash = max(0.0, planning_cash - float(result.get("total", 0.0)))

        if queued_or_filled == 0:
            logger.info("[trader] Weighted sizing produced no executable buy — retrying with a single best affordable idea")
            for v in buys:
                rationale = (
                    f"Fallback buy: prioritizing at least one actionable rotation from the strongest idea "
                    f"{v['ticker']} ({v['conviction']:.0%}). {v.get('final_reasoning','')[:80]}"
                )
                if market_open:
                    result = _execute_buy(
                        v["ticker"], v["conviction"], investable, v.get("id"), rationale, allow_cap_override=True
                    )
                else:
                    result = _queue_buy(
                        v["ticker"], v["conviction"], investable, v.get("id"), rationale, planning_cash, allow_cap_override=True
                    )
                results.append(result)
                if result.get("status") in {"filled", "queued"}:
                    break

    decisions   = get_recent_trade_decisions(minutes=10)
    executed    = [r for r in results if r.get("action") in ("BUY", "SELL") and r.get("status") == "filled"]
    queued      = [r for r in results if r.get("action") in ("BUY", "SELL") and r.get("status") == "queued"]
    skipped     = [r for r in results if r.get("action") == "SKIP"]
    errors      = [r for r in results if r.get("action") == "ERROR"]

    msg = f"{len(executed)} trade(s) filled, {len(queued)} queued, {len(skipped)} skipped, {len(errors)} errors."
    logger.info(f"[trader] {msg}")

    return {
        "trades_executed": len(executed),
        "trades_queued":   len(queued),
        "skipped":         len(skipped),
        "error":           None,
        "message":         msg,
        "decisions":       decisions,
    }
