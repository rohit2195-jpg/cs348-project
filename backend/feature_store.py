"""
feature_store.py
Builds replayable event and feature snapshots from live raw data.

The live pipeline and future historical simulation should both read the same
stored feature packets instead of reconstructing them ad hoc per ticker.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from math import sqrt

import trading as t
from database import (
    get_all_latest_reports_for_ticker,
    get_latest_price_snapshot,
    get_position,
    get_recent_news_events_for_ticker,
    get_recent_raw_news_rows_for_ticker,
    insert_or_ignore_news_event,
    replace_universe_candidates,
    upsert_feature_snapshot,
)

logger = logging.getLogger(__name__)

HIGH_SIGNAL_SOURCES = {"reuters", "benzinga", "marketwatch", "yfinance_news", "finviz"}
SOURCE_TIERS = {
    "reuters": "high",
    "benzinga": "high",
    "marketwatch": "high",
    "yfinance_news": "high",
    "finviz": "high",
}
EVENT_TAG_KEYWORDS = {
    "earnings":   ["earnings", "guidance", "revenue", "eps", "outlook", "forecast"],
    "deal":       ["merger", "acquisition", "takeover", "partnership", "contract"],
    "regulatory": ["antitrust", "lawsuit", "regulator", "fda", "investigation", "ban", "tariff"],
    "macro":      ["oil", "rates", "inflation", "fed", "sanctions", "war", "export", "trade"],
    "product":    ["launch", "approval", "drug", "ai", "chip", "factory", "production"],
    "analyst":    ["upgrade", "downgrade", "price target", "rating"],
}

MAX_NEW_CANDIDATE_LLM_REVIEWS_PER_RUN = 5
MAX_TOTAL_LLM_REVIEWS_PER_RUN = 8
LIQUIDITY_FLOOR = 750_000
MAX_CHASE_MOVE_PCT = 9.0
MIN_TRIAGE_SCORE_NEW = 5.0


def _run_date(value: str | None = None) -> str:
    return value or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _source_tier(source: str) -> str:
    return SOURCE_TIERS.get((source or "").lower(), "standard")


def _event_tags(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    tags = [tag for tag, keywords in EVENT_TAG_KEYWORDS.items() if any(keyword in text for keyword in keywords)]
    return tags or ["general"]


def _novelty_key(title: str) -> str:
    normalized = " ".join((title or "").lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _pct_changes(closes: list[float]) -> list[float]:
    changes = []
    for prev, cur in zip(closes, closes[1:]):
        if prev:
            changes.append((cur - prev) / prev)
    return changes


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return sqrt(variance)


def _build_history_context(ticker: str) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=90)
    try:
        bars = t.get_daily_bars_between(ticker, start, end)
    except Exception as exc:
        logger.warning("[feature_store] failed loading bars for %s: %s", ticker, exc)
        return {}

    closes = [bar["close"] for bar in bars]
    if len(closes) < 5:
        return {"bar_count": len(closes)}

    daily_changes = _pct_changes(closes)
    ctx = {
        "bar_count": len(closes),
        "return_5d_pct": round(((closes[-1] - closes[-6]) / closes[-6]) * 100, 3) if len(closes) >= 6 and closes[-6] else None,
        "return_20d_pct": round(((closes[-1] - closes[-21]) / closes[-21]) * 100, 3) if len(closes) >= 21 and closes[-21] else None,
        "return_60d_pct": round(((closes[-1] - closes[-61]) / closes[-61]) * 100, 3) if len(closes) >= 61 and closes[-61] else None,
        "volatility_20d_pct": round(_stdev(daily_changes[-20:]) * 100, 3) if len(daily_changes) >= 20 else None,
    }
    return ctx


def normalize_news_events_for_ticker(ticker: str, hours: int = 72) -> list[dict]:
    raw_rows = get_recent_raw_news_rows_for_ticker(ticker, hours=hours, limit=50)
    for row in raw_rows:
        insert_or_ignore_news_event(
            raw_news_id=row["id"],
            ticker=row["ticker"],
            source=row["source"],
            source_tier=_source_tier(row["source"]),
            title=row["title"],
            url=row.get("url"),
            published=row.get("published"),
            body_summary=row.get("body_summary"),
            event_tags=_event_tags(row["title"], row.get("body_summary") or ""),
            novelty_key=_novelty_key(row["title"]),
            collected_at=row["collected_at"],
        )
    return get_recent_news_events_for_ticker(ticker, hours=hours, limit=30)


def build_feature_snapshot(ticker: str, run_date: str | None = None, candidate_sources: list[str] | None = None) -> dict:
    run_date = _run_date(run_date)
    ticker = ticker.upper()
    events = normalize_news_events_for_ticker(ticker)
    snapshot = get_latest_price_snapshot(ticker) or {}
    reports = get_all_latest_reports_for_ticker(ticker)
    macro = reports.get("macro")
    is_held = get_position(ticker) is not None

    unique_sources = sorted({e["source"] for e in events if e.get("source")})
    high_signal_source_count = sum(1 for src in unique_sources if src.lower() in HIGH_SIGNAL_SOURCES)
    tag_counter = Counter(tag for event in events for tag in event.get("event_tags", []))
    dominant_tags = [tag for tag, _ in tag_counter.most_common(4)]
    abs_move_pct = abs(snapshot.get("day_change_pct") or 0.0)
    avg_volume = snapshot.get("avg_volume") or 0.0
    avg_volume_ratio = round((snapshot.get("volume") or 0.0) / avg_volume, 3) if avg_volume else None
    history_context = _build_history_context(ticker)

    evidence_score = 0.0
    if len(events) >= 3:
        evidence_score += 2.0
    elif len(events) >= 2:
        evidence_score += 1.0
    if len(unique_sources) >= 3:
        evidence_score += 2.0
    elif len(unique_sources) >= 2:
        evidence_score += 1.0
    if high_signal_source_count >= 2:
        evidence_score += 1.0
    if abs_move_pct >= 5:
        evidence_score += 2.0
    elif abs_move_pct >= 3:
        evidence_score += 1.0
    if avg_volume_ratio and avg_volume_ratio >= 1.5:
        evidence_score += 1.0
    if macro and macro.get("confidence", 0.0) >= 0.70:
        evidence_score += 1.5

    signal_quality = "weak"
    if evidence_score >= 6:
        signal_quality = "strong"
    elif evidence_score >= 3:
        signal_quality = "moderate"

    block_reasons = []
    if not events and not macro:
        block_reasons.append("no fresh catalyst")
    if not is_held and (snapshot.get("volume") or 0) < LIQUIDITY_FLOOR:
        block_reasons.append("low liquidity")
    if not is_held and abs_move_pct >= MAX_CHASE_MOVE_PCT and len(events) < 2:
        block_reasons.append("already moved too far")
    if not is_held and signal_quality == "weak":
        block_reasons.append("weak signal quality")
    if not is_held and not dominant_tags:
        block_reasons.append("no classified catalyst")

    triage_score = evidence_score
    triage_score += min(3.0, len(events) * 0.6)
    triage_score += min(2.0, len(unique_sources) * 0.5)
    triage_score += 1.2 if is_held else 0.0
    triage_score += 0.8 if macro and macro.get("confidence", 0.0) >= 0.7 else 0.0
    triage_score += 1.0 if any(tag in {"earnings", "deal", "regulatory"} for tag in dominant_tags) else 0.0
    triage_score -= 1.5 * len(block_reasons)

    feature_json = {
        "macro_signal": {
            "signal": macro["signal"],
            "confidence": macro["confidence"],
            "summary": macro["summary"],
        } if macro else None,
        "supporting_events": events[:8],
        "event_tag_counts": dict(tag_counter),
    }

    snapshot_id = upsert_feature_snapshot(
        run_date=run_date,
        ticker=ticker,
        is_held=is_held,
        article_count=len(events),
        unique_source_count=len(unique_sources),
        high_signal_source_count=high_signal_source_count,
        dominant_event_tags=dominant_tags,
        signal_quality=signal_quality,
        evidence_score=evidence_score,
        triage_score=triage_score,
        block_reasons=block_reasons,
        candidate_sources=candidate_sources or ["stage_queue"],
        price=snapshot.get("price"),
        day_change_pct=snapshot.get("day_change_pct"),
        avg_volume_ratio=avg_volume_ratio,
        market_cap=snapshot.get("market_cap"),
        sector=snapshot.get("sector"),
        history_context=history_context,
        feature_json=feature_json,
    )

    return {
        "id": snapshot_id,
        "run_date": run_date,
        "ticker": ticker,
        "is_held": is_held,
        "article_count": len(events),
        "unique_source_count": len(unique_sources),
        "high_signal_source_count": high_signal_source_count,
        "dominant_event_tags": dominant_tags,
        "signal_quality": signal_quality,
        "evidence_score": round(evidence_score, 3),
        "triage_score": round(triage_score, 3),
        "block_reasons": block_reasons,
        "candidate_sources": candidate_sources or ["stage_queue"],
        "price": snapshot.get("price"),
        "day_change_pct": snapshot.get("day_change_pct"),
        "avg_volume_ratio": avg_volume_ratio,
        "market_cap": snapshot.get("market_cap"),
        "sector": snapshot.get("sector"),
        "history_context": history_context,
        "feature_json": feature_json,
    }


def build_feature_store_for_tickers(tickers: list[str], run_date: str | None = None, source_map: dict[str, list[str]] | None = None) -> list[dict]:
    run_date = _run_date(run_date)
    snapshots = []
    for ticker in dict.fromkeys(t.upper() for t in tickers):
        sources = (source_map or {}).get(ticker, ["stage_queue"])
        snapshots.append(build_feature_snapshot(ticker, run_date=run_date, candidate_sources=sources))
    return snapshots


def shortlist_candidates(snapshots: list[dict], run_date: str | None = None) -> dict:
    run_date = _run_date(run_date)
    held = []
    new = []
    candidate_rows = []

    for snap in sorted(snapshots, key=lambda row: row["triage_score"], reverse=True):
        should_shortlist = False
        skip_reason = ", ".join(snap["block_reasons"]) if snap["block_reasons"] else ""
        if snap["is_held"]:
            should_shortlist = snap["article_count"] > 0 or bool(snap["feature_json"].get("macro_signal"))
            if not should_shortlist:
                skip_reason = skip_reason or "held with no fresh catalyst"
        else:
            should_shortlist = not snap["block_reasons"] and snap["triage_score"] >= MIN_TRIAGE_SCORE_NEW
            if not should_shortlist and not skip_reason:
                skip_reason = "triage score below threshold"

        if should_shortlist:
            (held if snap["is_held"] else new).append(snap)

    held = sorted(held, key=lambda row: row["triage_score"], reverse=True)
    new = sorted(new, key=lambda row: row["triage_score"], reverse=True)

    selected_held = held
    remaining_cap = max(0, MAX_TOTAL_LLM_REVIEWS_PER_RUN - len(selected_held))
    selected_new = new[:min(MAX_NEW_CANDIDATE_LLM_REVIEWS_PER_RUN, remaining_cap)]
    shortlist = sorted(selected_held + selected_new, key=lambda row: row["triage_score"], reverse=True)
    shortlisted_tickers = {row["ticker"] for row in shortlist}

    for snap in snapshots:
        candidate_rows.append({
            "ticker": snap["ticker"],
            "candidate_source": snap["candidate_sources"][0] if snap["candidate_sources"] else "feature_store",
            "score": snap["triage_score"],
            "reason": (
                f"quality={snap['signal_quality']} tags={','.join(snap['dominant_event_tags']) or 'none'} "
                f"articles={snap['article_count']} sources={snap['unique_source_count']}"
            ),
            "is_held": snap["is_held"],
            "triage_status": "shortlisted" if snap["ticker"] in shortlisted_tickers else "filtered",
            "llm_reviewed": 0,
            "trade_ready": 1 if snap["ticker"] in shortlisted_tickers else 0,
            "skip_reason": None if snap["ticker"] in shortlisted_tickers else (", ".join(snap["block_reasons"]) or "not selected"),
        })

    replace_universe_candidates(run_date, candidate_rows)
    return {"run_date": run_date, "snapshots": snapshots, "shortlist": shortlist, "candidate_rows": candidate_rows}
