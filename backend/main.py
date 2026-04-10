"""
main.py  —  backend/main.py
══════════════════════════════════════════════════════════════════════════════
Master orchestrator. Run from the backend/ directory.

  python main.py                        full pipeline
  python main.py --stage analyst        analyst only (collect + analyse)
  python main.py --stage researcher     researcher only (uses existing DB data)
  python main.py --stage trader         trader only (uses existing DB verdicts)
  python main.py --tickers AAPL MSFT    force specific tickers
  python main.py --portfolio-only       held stocks only, skip market candidates
  python main.py --dry-run              print plan, zero LLM calls

Pipeline:
  Stage 1  Build ticker queue    held stocks + watchlist + fallback market candidates
  Stage 2  Analyst Team          news + macro collection → raw_news / analyst_reports
  Stage 3  Feature Store         normalize events + build replayable feature snapshots
  Stage 4  Researcher Team       LLM debate on a capped shortlist only
  Stage 5  Evaluation            score prior verdicts and filled trades vs SPY
  Stage 6  Trader Agent          execute reviewed trade-ready names
══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import Base, engine, get_latest_reports, get_actionable_verdicts

# Analyst Team
from Analyst_Team.ticker_universe     import build_ticker_queue, print_queue, TickerItem, get_held_tickers
from Analyst_Team.news_collector      import collect_news_for_ticker
from Analyst_Team.macro_collector     import collect_macro_news
from Analyst_Team.analyst             import run_news_analyst
from Analyst_Team.analyst_macro_agent import run_macro_analyst

# Researcher Team
from Researcher_Team.researcher_team import run_researcher_batch, is_worth_researching

# Trader Team
from Trader_Team.trader_agent import run_trader, get_eligible_verdicts
from evaluator import run_evaluation_cycle
from feature_store import build_feature_store_for_tickers, shortlist_candidates


# ── Macro ticker extraction ────────────────────────────────────────────────────

def get_macro_flagged_tickers(min_confidence: float = 0.65) -> list[str]:
    """
    Returns tickers that the macro analyst flagged with a non-HOLD signal
    above the confidence threshold.
    These are merged into the researcher stage so macro events actually
    flow through the full pipeline → researcher → trader.
    """
    from database import SessionLocal, AnalystReport, AnalystSignal
    from datetime import timedelta
    cutoff  = datetime.now() - timedelta(hours=24)
    session = SessionLocal()
    try:
        rows = (
            session.query(AnalystReport.ticker)
            .filter(
                AnalystReport.analyst_type == "macro",
                AnalystReport.confidence   >= min_confidence,
                AnalystReport.signal       != AnalystSignal.HOLD,
                AnalystReport.created_at   >= cutoff,
            )
            .distinct()
            .all()
        )
        tickers = [r.ticker for r in rows]
        if tickers:
            logger.info(f"[macro] {len(tickers)} macro-flagged tickers to pass to researcher: {tickers}")
        return tickers
    finally:
        session.close()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Colours (safe to disable if your terminal doesn't support ANSI) ───────────
C_GREEN  = "\033[92m"
C_RED    = "\033[91m"
C_YELLOW = "\033[93m"
C_CYAN   = "\033[96m"
C_BOLD   = "\033[1m"
C_RESET  = "\033[0m"

SIGNAL_COLOUR  = {"BUY": C_GREEN,  "SELL": C_RED,  "HOLD": C_YELLOW}
VERDICT_COLOUR = {
    "STRONG_BUY": C_GREEN, "BUY": C_GREEN,
    "HOLD": C_YELLOW,
    "SELL": C_RED,  "STRONG_SELL": C_RED,
}

def _c(text, colour):  return f"{colour}{text}{C_RESET}"
def _header(title):    print(f"\n{C_BOLD}{'═'*60}\n  {title}\n{'═'*60}{C_RESET}")
def _section(title):   print(f"\n{C_CYAN}── {title}{C_RESET}")


# ── Stage 1: Build queue ──────────────────────────────────────────────────────

def stage_build_queue(args) -> list[TickerItem]:
    _header("STAGE 1 — Ticker queue")
    queue = build_ticker_queue(
        include_candidates = not args.portfolio_only,
        extra_tickers      = args.tickers or [],
    )
    print_queue(queue)
    return queue


# ── Stage 2: Analyst team ─────────────────────────────────────────────────────

# Max tickers running in parallel. 5 is the sweet spot:
#   - Browser instances: each ticker opens its own Chromium (5 at once is fine on Mac)
#   - DeepSeek API: no rate limit issues at this concurrency
#   - SQLite WAL mode: handles concurrent writes safely
#   - RAM: ~200MB per browser instance, 5 = ~1GB peak
ANALYST_WORKERS = 5

# Thread-safe print lock so concurrent output doesn't interleave
_print_lock = threading.Lock()

def _tprint(*args, **kwargs):
    """Thread-safe print."""
    with _print_lock:
        print(*args, **kwargs)


def _collect_one(item: TickerItem) -> dict:
    """
    Collects news + price for one ticker. Runs in a thread pool.
    Returns a result dict with ticker, summary, and any error.
    """
    ticker = item.ticker
    try:
        t0      = time.time()
        summary = collect_news_for_ticker(ticker)
        elapsed = time.time() - t0

        snap    = summary.get("price_snapshot") or {}
        chg     = f"{snap['day_change_pct']:+.2f}%" if snap.get("day_change_pct") is not None else "N/A"
        _tprint(
            f"  [collect] {ticker:<8} "
            f"yf:{summary['yf_news_count']} fv:{summary['finviz_count']} "
            f"mw:{summary['marketwatch_count']} rt:{summary['reuters_count']} "
            f"bz:{summary['benzinga_count']} new:{summary['total_inserted']}  "
            f"${snap.get('price','?')} {chg}  ({elapsed:.1f}s)"
        )
        return {"ticker": ticker, "summary": summary, "error": None}
    except Exception as e:
        _tprint(f"  [collect] {ticker:<8} ERROR: {e}")
        return {"ticker": ticker, "summary": None, "error": str(e)}


def _analyse_one(ticker: str) -> dict:
    """
    Analyst stage is now pure data collection — no LLM call.
    run_news_analyst() just confirms articles are in DB and returns.
    """
    try:
        report = run_news_analyst(ticker)
        return {"ticker": ticker, "report": report, "error": None}
    except Exception as e:
        _tprint(f"  [analyst] {ticker:<8} ERROR: {e}")
        return {"ticker": ticker, "report": None, "error": str(e)}


def stage_analyst(queue: list[TickerItem], dry_run: bool = False) -> list[str]:
    _header(f"STAGE 2 — Analyst Team  ({len(queue)} ticker(s), {ANALYST_WORKERS} parallel)")

    # 2a — Macro collection: runs ONCE, not per ticker
    _section("Collecting macro/geopolitical news")
    if dry_run:
        print("  DRY RUN — would collect macro news")
    else:
        t0      = time.time()
        macro   = collect_macro_news()
        elapsed = time.time() - t0
        active  = {k: v for k, v in macro["by_source"].items() if v > 0}
        print(
            f"  Fetched:{macro['total_fetched']}  "
            f"New rows:{macro['total_inserted']}  ({elapsed:.1f}s)"
        )
        if active:
            print(f"  Sources: {', '.join(f'{k}:{v}' for k, v in active.items())}")

    # 2b — Macro analyst: runs ONCE, maps events → tickers
    _section("Running macro analyst (geopolitical → ticker mapping)")
    if dry_run:
        print("  DRY RUN — would run macro analyst")
    else:
        t0            = time.time()
        macro_reports = run_macro_analyst()
        elapsed       = time.time() - t0
        if macro_reports:
            print(f"  {_c('✓', C_GREEN)} {len(macro_reports)} ticker(s) flagged  ({elapsed:.1f}s)")
            for r in macro_reports:
                col = SIGNAL_COLOUR.get(r["signal"], "")
                print(f"    {r['ticker']:<8} {_c(r['signal'], col)}  ({r['confidence']:.0%})  {r['summary'][:65]}...")
        else:
            print(f"  No macro impacts today  ({elapsed:.1f}s)")

    if dry_run:
        _section("Per-ticker collection + analysis  (DRY RUN)")
        for item in queue:
            print(f"  would collect + analyse {item.ticker}")
        return [item.ticker for item in queue]

    tickers = [item.ticker for item in queue]

    # 2c — PARALLEL news collection (all tickers at once, up to ANALYST_WORKERS)
    # Browser instances are I/O-bound — running 5 in parallel is the main speedup.
    _section(f"Collecting news  ({ANALYST_WORKERS} at a time)")
    t0 = time.time()
    collect_results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=ANALYST_WORKERS, thread_name_prefix="collect") as pool:
        futures = {pool.submit(_collect_one, item): item.ticker for item in queue}
        for future in as_completed(futures):
            result = future.result()
            collect_results[result["ticker"]] = result
    print(f"  Collection complete in {time.time()-t0:.1f}s  "
          f"(was ~{len(tickers)*60:.0f}s sequential)")

    # 2d — Mark tickers as collected (no LLM call — researcher reads raw articles)
    _section("Confirming collection  (no LLM calls in analyst stage)")
    t0 = time.time()
    analyse_results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=ANALYST_WORKERS, thread_name_prefix="analyst") as pool:
        futures = {pool.submit(_analyse_one, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            result = future.result()
            analyse_results[result["ticker"]] = result
    print(f"  Collection confirmed in {time.time()-t0:.1f}s")

    processed = [t for t in tickers if not analyse_results.get(t, {}).get("error")]
    failed    = [t for t in tickers if analyse_results.get(t, {}).get("error")]
    if failed:
        print(f"  {_c('✗', C_RED)} Failed tickers: {', '.join(failed)}")

    return processed


# ── Stage 3: Feature store + Researcher team ──────────────────────────────────

def stage_researcher(tickers: list[str], dry_run: bool = False) -> list[dict]:
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    _header("STAGE 3 — Feature Store")

    feature_snapshots = build_feature_store_for_tickers(tickers, run_date=run_date)
    shortlist_result = shortlist_candidates(feature_snapshots, run_date=run_date)
    shortlisted = shortlist_result["shortlist"]
    filtered = [row for row in shortlist_result["candidate_rows"] if row["triage_status"] != "shortlisted"]

    print(f"\n  Built feature snapshots: {len(feature_snapshots)}")
    print(f"  LLM shortlist:           {len(shortlisted)}")
    print(f"  Filtered before LLM:     {len(filtered)}")
    for row in filtered[:12]:
        print(f"    {row['ticker']}: {row.get('skip_reason') or 'filtered'}")

    if not shortlisted:
        print("\n  No names survived deterministic triage — researcher stage skipped.")
        return []

    _header("STAGE 4 — Researcher Team")

    eligible   = []
    ineligible = []
    for t in [row["ticker"] for row in shortlisted]:
        ok, reason = is_worth_researching(t)
        (eligible if ok else ineligible).append((t, reason))

    print(f"\n  Eligible for debate:   {len(eligible)}")
    print(f"  Skipped (weak signal): {len(ineligible)}")
    for t, r in ineligible:
        print(f"    {t}: {r}")

    if not eligible:
        print("\n  No actionable signals — researcher stage skipped.")
        return []

    if dry_run:
        print(f"\n  DRY RUN — would debate: {', '.join(t for t, _ in eligible)}")
        return []

    _section(f"Debating {len(eligible)} shortlisted ticker(s)...")
    results = run_researcher_batch([t for t, _ in eligible], run_date=run_date)
    return results


# ── Stage 5: Evaluation ───────────────────────────────────────────────────────

def stage_evaluation(dry_run: bool = False) -> dict:
    _header("STAGE 5 — Evaluation")
    if dry_run:
        print("  DRY RUN — would evaluate prior verdicts and filled trades")
        return {"new_verdict_evaluations": 0, "new_trade_evaluations": 0, "summary": {}}

    result = run_evaluation_cycle()
    print(
        f"  Added {result['new_verdict_evaluations']} verdict evaluation(s) and "
        f"{result['new_trade_evaluations']} trade evaluation(s)"
    )
    summary = result.get("summary") or {}
    if summary:
        print(f"  {'Bucket':<18} {'Count':>5} {'Win%':>6} {'Thesis%':>9} {'Excess%':>9}")
        print(f"  {'─'*54}")
        for bucket, row in sorted(summary.items()):
            print(
                f"  {bucket:<18} {row.get('count', 0):>5} "
                f"{row.get('win_rate', 0.0):>6.0%} "
                f"{row.get('avg_thesis_return_pct', 0.0):>8.2f}% "
                f"{row.get('avg_excess_return_pct', 0.0):>8.2f}%"
            )
    else:
        print("  No mature evaluations available yet.")
    return result


# ── Stage 6: Summary ──────────────────────────────────────────────────────────

def stage_summary(analyst_tickers: list[str]) -> None:
    _header("STAGE 6 — Summary")

    _section("Analyst signals")
    print(f"  {'Ticker':<8}  {'Signal':<6}  {'Conf':>5}  Analyst")
    print(f"  {'─'*48}")
    for ticker in analyst_tickers:
        for r in get_latest_reports(ticker, limit=10):
            sig    = r["signal"]
            colour = SIGNAL_COLOUR.get(sig, "")
            print(f"  {r['ticker']:<8}  {_c(sig, colour):<6}  {r['confidence']:>4.0%}  {r['analyst_type']}")

    _section("Research verdicts  (conviction ≥ 68%)")
    verdicts = get_actionable_verdicts(min_conviction=0.68, hours=30)
    if not verdicts:
        print("  None this run.")
    else:
        print(f"  {'Ticker':<8}  {'Verdict':<12}  {'Conv':>5}  Reasoning")
        print(f"  {'─'*60}")
        for v in verdicts:
            col = VERDICT_COLOUR.get(v["verdict"], "")
            print(
                f"  {v['ticker']:<8}  "
                f"{_c(v['verdict'], col):<12}  "
                f"{v['conviction']:>4.0%}  "
                f"{v['final_reasoning'][:55].replace(chr(10),' ')}..."
            )


# ── Stage 7: Trader ───────────────────────────────────────────────────────────

def stage_trader(dry_run: bool = False) -> dict:
    _header("STAGE 7 — Trader Agent")
    print(f"{C_CYAN}Checking for eligible verdicts...{C_RESET}")

    eligible = get_eligible_verdicts()
    if not eligible:
        print(f"\n  No verdicts met the trigger threshold — nothing to trade.")
        return {"trades_executed": 0, "skipped": 0}

    print(f"\n  {len(eligible)} eligible trade opportunity/opportunities:")
    for v in eligible:
        col       = VERDICT_COLOUR.get(v["verdict"], "")
        analysts  = ", ".join(v.get("_agreeing_analysts", []))
        held_flag = "  [HELD]" if v.get("_is_held") else ""
        print(
            f"    {v['ticker']:<8}  {_c(v['verdict'], col):<12}  "
            f"conviction {v['conviction']:.0%}  "
            f"analysts: {analysts}{held_flag}"
        )

    if dry_run:
        print(f"\n  DRY RUN — would execute trader agent on {len(eligible)} opportunity/opportunities")
        return {"trades_executed": 0, "skipped": 0}

    print(f"\n  Invoking trader agent...")
    t0     = time.time()
    result = run_trader()
    elapsed = time.time() - t0

    if result.get("error"):
        print(f"  {_c('✗ Agent error:', C_RED)} {result['error']}")
        return result

    print(f"  {_c('✓', C_GREEN)} {result['message']}  ({elapsed:.1f}s)")

    decisions = result.get("decisions", [])
    if decisions:
        print(f"\n  {'Action':<6}  {'Ticker':<8}  {'Qty':>5}  {'Price':>8}  {'Status':<12}  Note")
        print(f"  {'─'*72}")
        for d in decisions:
            if d["action"] == "SKIP":
                continue
            action_col = C_GREEN if d["action"] == "BUY" else (C_RED if d["action"] == "SELL" else C_YELLOW)
            total = d.get("price", 0) * d.get("quantity", 0)
            print(
                f"  {_c(d['action'], action_col):<6}  "
                f"{d['ticker']:<8}  "
                f"{d['quantity']:>5}  "
                f"${d['price']:>7.2f}  "
                f"{d['status']:<12}  "
                f"total=${total:,.0f}"
            )

    return result


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Trading bot — master orchestrator")
    p.add_argument(
        "--stage",
        choices=["all", "analyst", "researcher", "evaluate", "trader", "from-researcher"],
        default="all",
        help=(
            "Which stage(s) to run (default: all). "
            "Use 'from-researcher' to skip analyst and run researcher+trader "
            "using existing DB data from a previous analyst run."
        ),
    )
    p.add_argument(
        "--tickers", nargs="+", metavar="TICKER",
        help="Override ticker list  e.g. --tickers AAPL MSFT TSLA",
    )
    p.add_argument(
        "--portfolio-only", action="store_true",
        help="Only analyse held stocks — skip market candidate screeners",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print queue and plan without making any LLM or Alpaca calls",
    )
    return p.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args  = parse_args()
    start = datetime.now()

    Base.metadata.create_all(bind=engine)

    print(f"\n{C_BOLD}Trading Bot  ·  {start.strftime('%Y-%m-%d %H:%M:%S')}{C_RESET}")
    if args.dry_run:
        print(f"{C_YELLOW}  DRY RUN — no LLM or Alpaca calls{C_RESET}")

    analyst_tickers = []

    # ── Analyst stage ──────────────────────────────────────────────────────────
    if args.stage in ("all", "analyst"):
        if args.tickers:
            queue = [
                TickerItem(priority=2, score=0.0, ticker=t.upper(), reason="CLI arg")
                for t in args.tickers
            ]
            _header("STAGE 1 — Ticker queue  (CLI override)")
            print_queue(queue)
        else:
            queue = stage_build_queue(args)

        analyst_tickers = stage_analyst(queue, dry_run=args.dry_run)

    # ── Researcher stage ───────────────────────────────────────────────────────
    if args.stage in ("all", "researcher", "from-researcher"):
        if not analyst_tickers:
            analyst_tickers = [t.ticker for t in get_held_tickers()]

        # Merge in macro-flagged tickers so geopolitical signals flow through
        # the full pipeline — researcher debates them, trader acts on verdicts.
        macro_tickers   = get_macro_flagged_tickers(min_confidence=0.65)
        all_for_research = list(dict.fromkeys(analyst_tickers + macro_tickers))

        new_macro = [t for t in macro_tickers if t not in analyst_tickers]
        if new_macro:
            _section(f"Adding {len(new_macro)} macro-only ticker(s) to researcher stage")
            print(f"  {', '.join(new_macro)}")

        stage_researcher(all_for_research, dry_run=args.dry_run)

    # ── Evaluation stage ───────────────────────────────────────────────────────
    if args.stage in ("all", "evaluate", "trader", "from-researcher"):
        stage_evaluation(dry_run=args.dry_run)

    # ── Summary (printed before trader so you can see what triggers it) ────────
    if not args.dry_run and analyst_tickers and args.stage not in ("trader", "from-researcher"):
        stage_summary(analyst_tickers)

    # ── Trader stage ───────────────────────────────────────────────────────────
    if args.stage in ("all", "trader", "from-researcher"):
        stage_trader(dry_run=args.dry_run)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{C_BOLD}Done in {elapsed:.1f}s{C_RESET}\n")


if __name__ == "__main__":
    main()
