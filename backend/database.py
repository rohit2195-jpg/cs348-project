"""
database.py — SQLite persistence layer
Stores portfolio positions, order history, analyst reports, and research verdicts.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import enum
import json


DATABASE_URL = "sqlite:///my_database.db"
engine       = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},   # allow use across threads
)

# Enable WAL mode so concurrent thread writes don't block each other.
# Must be set at the connection level, not the engine level.
from sqlalchemy import event as _sa_event
@_sa_event.listens_for(engine, "connect")
def _set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA busy_timeout=5000")   # wait up to 5s on lock
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


# ══════════════════════════════════════════════════════════════════════════════
# ORM Models
# ══════════════════════════════════════════════════════════════════════════════

class Portfolio(Base):
    __tablename__ = "Portfolio"
    symbol        = Column(String(10), primary_key=True)
    purchasePrice = Column(Float)
    quantity      = Column(Integer)
    purchaseDate  = Column(String(10))


class OrderStatus(enum.Enum):
    pending  = "pending"
    filled   = "filled"
    canceled = "canceled"


class TradeType(enum.Enum):
    buy  = "buy"
    sell = "sell"


class OrderHistory(Base):
    __tablename__    = "order_history"
    id               = Column(Integer,  primary_key=True, autoincrement=True)
    symbol           = Column(String(10),  nullable=False)
    price            = Column(Float,       nullable=False)
    quantity         = Column(Integer,     nullable=False)
    timestamp        = Column(DateTime,    default=datetime.utcnow)
    status           = Column(Enum(OrderStatus), default=OrderStatus.pending)
    trade_type       = Column(Enum(TradeType),   nullable=False)
    alpaca_order_id  = Column(String(64),  nullable=True)


class RawNews(Base):
    __tablename__ = "raw_news"
    id           = Column(Integer,      primary_key=True, autoincrement=True)
    ticker       = Column(String(10),   nullable=False)
    source       = Column(String(50),   nullable=False)
    title        = Column(String(500),  nullable=False)
    url          = Column(String(1000), nullable=True)
    published    = Column(String(50),   nullable=True)
    body_summary = Column(Text,         nullable=True)
    collected_at = Column(DateTime,     default=datetime.utcnow)

Index("ix_raw_news_ticker_time", RawNews.ticker, RawNews.collected_at)


class AnalystSignal(enum.Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AnalystReport(Base):
    __tablename__ = "analyst_reports"
    id            = Column(Integer,     primary_key=True, autoincrement=True)
    ticker        = Column(String(10),  nullable=False)
    analyst_type  = Column(String(30),  nullable=False)
    signal        = Column(Enum(AnalystSignal), nullable=False)
    confidence    = Column(Float,       nullable=False)
    summary       = Column(Text,        nullable=False)
    key_points    = Column(Text,        nullable=True)
    sources_used  = Column(Text,        nullable=True)
    article_count = Column(Integer,     nullable=True)
    model_used    = Column(String(50),  nullable=True)
    created_at    = Column(DateTime,    default=datetime.utcnow)

Index("ix_analyst_reports_ticker_type", AnalystReport.ticker, AnalystReport.analyst_type)
Index("ix_analyst_reports_created",     AnalystReport.created_at)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id             = Column(Integer,     primary_key=True, autoincrement=True)
    ticker         = Column(String(10),  nullable=False)
    price          = Column(Float,       nullable=True)
    prev_close     = Column(Float,       nullable=True)
    day_change_pct = Column(Float,       nullable=True)
    volume         = Column(Float,       nullable=True)
    avg_volume     = Column(Float,       nullable=True)
    market_cap     = Column(Float,       nullable=True)
    pe_ratio       = Column(Float,       nullable=True)
    forward_pe     = Column(Float,       nullable=True)
    week_52_high   = Column(Float,       nullable=True)
    week_52_low    = Column(Float,       nullable=True)
    sector         = Column(String(100), nullable=True)
    snapshot_at    = Column(DateTime,    default=datetime.utcnow)

Index("ix_price_snapshots_ticker", PriceSnapshot.ticker)


class NewsEvent(Base):
    __tablename__ = "news_events"
    id            = Column(Integer,      primary_key=True, autoincrement=True)
    raw_news_id    = Column(Integer,     nullable=False, unique=True)
    ticker         = Column(String(10),  nullable=False)
    source         = Column(String(50),  nullable=False)
    source_tier    = Column(String(20),  nullable=False, default="standard")
    title          = Column(String(500), nullable=False)
    url            = Column(String(1000), nullable=True)
    published      = Column(String(50),  nullable=True)
    body_summary   = Column(Text,        nullable=True)
    event_tags     = Column(Text,        nullable=True)   # JSON list
    novelty_key    = Column(String(64),  nullable=False)
    collected_at   = Column(DateTime,    default=datetime.utcnow)

Index("ix_news_events_ticker_time", NewsEvent.ticker, NewsEvent.collected_at)
Index("ix_news_events_ticker_novelty", NewsEvent.ticker, NewsEvent.novelty_key)


class TickerFeatureSnapshot(Base):
    __tablename__ = "ticker_feature_snapshots"
    id                      = Column(Integer,     primary_key=True, autoincrement=True)
    run_date                = Column(String(10),  nullable=False)
    ticker                  = Column(String(10),  nullable=False)
    is_held                 = Column(Integer,     nullable=False, default=0)
    article_count           = Column(Integer,     nullable=False, default=0)
    unique_source_count     = Column(Integer,     nullable=False, default=0)
    high_signal_source_count = Column(Integer,    nullable=False, default=0)
    dominant_event_tags     = Column(Text,        nullable=True)   # JSON list
    signal_quality          = Column(String(20),  nullable=False, default="weak")
    evidence_score          = Column(Float,       nullable=False, default=0.0)
    triage_score            = Column(Float,       nullable=False, default=0.0)
    block_reasons           = Column(Text,        nullable=True)   # JSON list
    candidate_sources       = Column(Text,        nullable=True)   # JSON list
    price                   = Column(Float,       nullable=True)
    day_change_pct          = Column(Float,       nullable=True)
    avg_volume_ratio        = Column(Float,       nullable=True)
    market_cap              = Column(Float,       nullable=True)
    sector                  = Column(String(100), nullable=True)
    history_context         = Column(Text,        nullable=True)   # JSON object
    feature_json            = Column(Text,        nullable=True)   # JSON object
    created_at              = Column(DateTime,    default=datetime.utcnow)

Index("ix_feature_snapshots_run_ticker", TickerFeatureSnapshot.run_date, TickerFeatureSnapshot.ticker)
Index("ix_feature_snapshots_ticker_created", TickerFeatureSnapshot.ticker, TickerFeatureSnapshot.created_at)


class UniverseCandidate(Base):
    __tablename__ = "universe_candidates"
    id               = Column(Integer,     primary_key=True, autoincrement=True)
    run_date         = Column(String(10),  nullable=False)
    ticker           = Column(String(10),  nullable=False)
    candidate_source = Column(String(30),  nullable=False)
    score            = Column(Float,       nullable=False, default=0.0)
    reason           = Column(Text,        nullable=True)
    is_held          = Column(Integer,     nullable=False, default=0)
    triage_status    = Column(String(20),  nullable=False, default="filtered")
    llm_reviewed     = Column(Integer,     nullable=False, default=0)
    trade_ready      = Column(Integer,     nullable=False, default=0)
    skip_reason      = Column(Text,        nullable=True)
    created_at       = Column(DateTime,    default=datetime.utcnow)

Index("ix_universe_candidates_run_ticker", UniverseCandidate.run_date, UniverseCandidate.ticker)
Index("ix_universe_candidates_run_status", UniverseCandidate.run_date, UniverseCandidate.triage_status, UniverseCandidate.trade_ready)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id            = Column(Integer,     primary_key=True, autoincrement=True)
    start_date    = Column(String(10),  nullable=False)
    end_date      = Column(String(10),  nullable=False)
    initial_cash  = Column(Float,       nullable=False)
    ending_cash   = Column(Float,       nullable=False, default=0.0)
    ending_equity = Column(Float,       nullable=False, default=0.0)
    metrics_json  = Column(Text,        nullable=True)
    created_at    = Column(DateTime,    default=datetime.utcnow)


class SimulationPosition(Base):
    __tablename__ = "simulation_positions"
    id                = Column(Integer,     primary_key=True, autoincrement=True)
    simulation_run_id = Column(Integer,     nullable=False)
    trade_date        = Column(String(10),  nullable=False)
    ticker            = Column(String(10),  nullable=False)
    action            = Column(String(10),  nullable=False)
    quantity          = Column(Integer,     nullable=False, default=0)
    price             = Column(Float,       nullable=False, default=0.0)
    cash_after        = Column(Float,       nullable=False, default=0.0)
    equity_after      = Column(Float,       nullable=False, default=0.0)
    notes             = Column(Text,        nullable=True)
    created_at        = Column(DateTime,    default=datetime.utcnow)

Index("ix_simulation_positions_run_date", SimulationPosition.simulation_run_id, SimulationPosition.trade_date)


# ── NEW: Researcher Team output ───────────────────────────────────────────────

class ResearchVerdict(enum.Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    HOLD        = "HOLD"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"


class ResearchVerdictRow(Base):
    __tablename__   = "research_verdicts"
    id              = Column(Integer,     primary_key=True, autoincrement=True)
    ticker          = Column(String(10),  nullable=False)
    verdict         = Column(Enum(ResearchVerdict), nullable=False)
    conviction      = Column(Float,       nullable=False)   # 0.0 – 1.0
    bull_case       = Column(Text,        nullable=False)
    bear_case       = Column(Text,        nullable=False)
    final_reasoning = Column(Text,        nullable=False)
    key_risks       = Column(Text,        nullable=True)    # JSON list
    key_catalysts   = Column(Text,        nullable=True)    # JSON list
    analyst_signals = Column(Text,        nullable=True)    # JSON snapshot of inputs
    model_used      = Column(String(50),  nullable=True)
    created_at      = Column(DateTime,    default=datetime.utcnow)

Index("ix_research_verdicts_ticker",  ResearchVerdictRow.ticker)
Index("ix_research_verdicts_created", ResearchVerdictRow.created_at)


# ── Watchlist ─────────────────────────────────────────────────────────────────

class TargetDirection(enum.Enum):
    above = "above"
    below = "below"


class Watchlist(Base):
    __tablename__    = "watchlist"
    id               = Column(Integer,     primary_key=True, autoincrement=True)
    symbol           = Column(String(10),  nullable=False, unique=True)
    added_date       = Column(String(10),  nullable=False)
    target_price     = Column(Float,       nullable=True)
    target_direction = Column(Enum(TargetDirection), nullable=True)
    notes            = Column(String(500), nullable=True)
    triggered        = Column(Integer,     default=0)
    triggered_at     = Column(DateTime,    nullable=True)
    triggered_price  = Column(Float,       nullable=True)


Base.metadata.create_all(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio
# ══════════════════════════════════════════════════════════════════════════════

def get_portfolio():
    """Return raw ORM rows (used internally by the terminal UI and ticker_universe)."""
    session = SessionLocal()
    try:
        return session.query(Portfolio).all()
    finally:
        session.close()


def get_portfolio_for_chart() -> list:
    session = SessionLocal()
    try:
        rows = session.query(Portfolio).all()
        return [
            {
                "symbol":        r.symbol,
                "purchasePrice": r.purchasePrice,
                "quantity":      r.quantity,
                "purchaseDate":  r.purchaseDate,
            }
            for r in rows
        ]
    finally:
        session.close()


def get_position(symbol: str):
    session = SessionLocal()
    try:
        row = session.query(Portfolio).filter(Portfolio.symbol == symbol.upper()).first()
        if row:
            return {
                "symbol":        row.symbol,
                "quantity":      row.quantity,
                "purchasePrice": row.purchasePrice,
                "purchaseDate":  row.purchaseDate,
            }
        return None
    finally:
        session.close()


def upsert_position(symbol: str, price: float, quantity: int, date: str):
    session = SessionLocal()
    try:
        row = session.query(Portfolio).filter(Portfolio.symbol == symbol.upper()).first()
        if row:
            if quantity == 0:
                session.delete(row)
            else:
                row.quantity      = quantity
                row.purchasePrice = price
        else:
            row = Portfolio(
                symbol        = symbol.upper(),
                purchasePrice = price,
                quantity      = quantity,
                purchaseDate  = date,
            )
            session.add(row)
        session.commit()
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# Orders
# ══════════════════════════════════════════════════════════════════════════════

def create_order(symbol: str, price: float, quantity: int, trade_type: str,
                 alpaca_order_id: str = None) -> int:
    session = SessionLocal()
    try:
        order = OrderHistory(
            symbol          = symbol.upper(),
            price           = price,
            quantity        = quantity,
            trade_type      = TradeType(trade_type),
            status          = OrderStatus.pending,
            alpaca_order_id = alpaca_order_id,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id
    finally:
        session.close()


def set_alpaca_order_id(order_id: int, alpaca_order_id: str):
    session = SessionLocal()
    try:
        order = session.query(OrderHistory).get(order_id)
        if order:
            order.alpaca_order_id = alpaca_order_id
            session.commit()
    finally:
        session.close()


def get_alpaca_order_id(order_id: int):
    session = SessionLocal()
    try:
        order = session.query(OrderHistory).get(order_id)
        return order.alpaca_order_id if order else None
    finally:
        session.close()


def fill_order(order_id: int):
    session = SessionLocal()
    try:
        order = session.query(OrderHistory).get(order_id)
        if order:
            order.status = OrderStatus.filled
            session.commit()
    finally:
        session.close()


def cancel_order_db(order_id: int):
    session = SessionLocal()
    try:
        order = session.query(OrderHistory).get(order_id)
        if order:
            order.status = OrderStatus.canceled
            session.commit()
    finally:
        session.close()


def get_all_orders() -> list:
    session = SessionLocal()
    try:
        orders = session.query(OrderHistory).order_by(OrderHistory.timestamp.desc()).all()
        return [
            {
                "id":              o.id,
                "symbol":          o.symbol,
                "price":           o.price,
                "quantity":        o.quantity,
                "trade_type":      o.trade_type.value,
                "status":          o.status.value,
                "timestamp":       o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "alpaca_order_id": o.alpaca_order_id,
            }
            for o in orders
        ]
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# Filter & Report
# ══════════════════════════════════════════════════════════════════════════════

def get_symbols() -> list:
    session = SessionLocal()
    try:
        portfolio_syms = [r.symbol for r in session.query(Portfolio.symbol).distinct()]
        order_syms     = [r.symbol for r in session.query(OrderHistory.symbol).distinct()]
        return sorted(set(portfolio_syms + order_syms))
    finally:
        session.close()


def filter_orders(
    symbols:    list  = None,
    trade_type: str   = None,
    status:     str   = None,
    date_from:  str   = None,
    date_to:    str   = None,
    price_min:  float = None,
    price_max:  float = None,
) -> list:
    from sqlalchemy import and_
    session = SessionLocal()
    try:
        q = session.query(OrderHistory)
        if symbols:
            q = q.filter(OrderHistory.symbol.in_([s.upper() for s in symbols]))
        if trade_type:
            q = q.filter(OrderHistory.trade_type == TradeType(trade_type))
        if status:
            q = q.filter(OrderHistory.status == OrderStatus(status))
        if date_from:
            q = q.filter(OrderHistory.timestamp >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            q = q.filter(OrderHistory.timestamp < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        if price_min is not None:
            q = q.filter(OrderHistory.price >= price_min)
        if price_max is not None:
            q = q.filter(OrderHistory.price <= price_max)
        orders = q.order_by(OrderHistory.timestamp.desc()).all()
        return [
            {
                "id":          o.id,
                "symbol":      o.symbol,
                "price":       o.price,
                "quantity":    o.quantity,
                "trade_type":  o.trade_type.value,
                "status":      o.status.value,
                "timestamp":   o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "total_value": round(o.price * o.quantity, 2),
            }
            for o in orders
        ]
    finally:
        session.close()


def filter_portfolio(
    symbols:  list  = None,
    pl_min:   float = None,
    pl_max:   float = None,
    val_min:  float = None,
    val_max:  float = None,
    prices:   dict  = None,
) -> list:
    session = SessionLocal()
    try:
        q = session.query(Portfolio)
        if symbols:
            q = q.filter(Portfolio.symbol.in_([s.upper() for s in symbols]))
        rows = q.all()
    finally:
        session.close()

    prices = prices or {}
    result = []
    for r in rows:
        current   = prices.get(r.symbol, 0.0)
        pl_val    = (current - r.purchasePrice) * r.quantity
        pl_pct    = ((current - r.purchasePrice) / r.purchasePrice * 100) if r.purchasePrice else 0
        mkt_value = round(current * r.quantity, 2)
        if pl_min  is not None and pl_pct    < pl_min:   continue
        if pl_max  is not None and pl_pct    > pl_max:   continue
        if val_min is not None and mkt_value < val_min:  continue
        if val_max is not None and mkt_value > val_max:  continue
        result.append({
            "symbol":        r.symbol,
            "quantity":      r.quantity,
            "avg_price":     r.purchasePrice,
            "current_price": current,
            "market_value":  mkt_value,
            "pl":            round(pl_val, 2),
            "pl_pct":        round(pl_pct, 2),
            "purchase_date": r.purchaseDate,
        })
    return result


def get_order_by_id(order_id: int) -> dict:
    session = SessionLocal()
    try:
        o = session.query(OrderHistory).get(order_id)
        if not o:
            return None
        return {
            "id":          o.id,
            "symbol":      o.symbol,
            "price":       o.price,
            "quantity":    o.quantity,
            "trade_type":  o.trade_type.value,
            "status":      o.status.value,
            "timestamp":   o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "total_value": round(o.price * o.quantity, 2),
        }
    finally:
        session.close()


def get_portfolio_snapshot() -> list:
    session = SessionLocal()
    try:
        rows = session.query(Portfolio).order_by(Portfolio.symbol).all()
        return [
            {
                "symbol":        r.symbol,
                "quantity":      r.quantity,
                "avg_price":     r.purchasePrice,
                "purchase_date": r.purchaseDate,
            }
            for r in rows
        ]
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# Watchlist
# ══════════════════════════════════════════════════════════════════════════════

def add_to_watchlist(symbol: str, target_price: float = None,
                     target_direction: str = None, notes: str = None) -> dict:
    session = SessionLocal()
    try:
        existing = session.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
        if existing:
            if target_price     is not None: existing.target_price     = target_price
            if target_direction is not None: existing.target_direction = TargetDirection(target_direction)
            if notes            is not None: existing.notes            = notes
            existing.triggered       = 0
            existing.triggered_at    = None
            existing.triggered_price = None
            session.commit()
            return _watchlist_dict(existing)
        row = Watchlist(
            symbol           = symbol.upper(),
            added_date       = datetime.now().strftime("%Y-%m-%d"),
            target_price     = target_price,
            target_direction = TargetDirection(target_direction) if target_direction else None,
            notes            = notes,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _watchlist_dict(row)
    finally:
        session.close()


def remove_from_watchlist(symbol: str) -> bool:
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
        if row:
            session.delete(row)
            session.commit()
            return True
        return False
    finally:
        session.close()


def get_watchlist() -> list:
    session = SessionLocal()
    try:
        rows = session.query(Watchlist).order_by(Watchlist.added_date.desc()).all()
        return [_watchlist_dict(r) for r in rows]
    finally:
        session.close()


def get_watchlist_active() -> list:
    session = SessionLocal()
    try:
        rows = session.query(Watchlist).filter(
            Watchlist.target_price != None,
            Watchlist.triggered == 0,
        ).all()
        return [_watchlist_dict(r) for r in rows]
    finally:
        session.close()


def mark_watchlist_triggered(symbol: str, price: float):
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
        if row:
            row.triggered       = 1
            row.triggered_at    = datetime.utcnow()
            row.triggered_price = price
            session.commit()
    finally:
        session.close()


def dismiss_watchlist_alert(symbol: str):
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
        if row:
            row.triggered = 2
            session.commit()
    finally:
        session.close()


def update_watchlist_entry(symbol: str, target_price=None,
                           target_direction=None, notes=None):
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
        if not row:
            return None
        if target_price     is not None: row.target_price     = target_price if target_price != "" else None
        if target_direction is not None: row.target_direction = TargetDirection(target_direction) if target_direction else None
        if notes            is not None: row.notes            = notes
        row.triggered       = 0
        row.triggered_at    = None
        row.triggered_price = None
        session.commit()
        return _watchlist_dict(row)
    finally:
        session.close()


def get_unread_alerts() -> list:
    session = SessionLocal()
    try:
        rows = session.query(Watchlist).filter(Watchlist.triggered == 1).all()
        return [_watchlist_dict(r) for r in rows]
    finally:
        session.close()


def _watchlist_dict(row) -> dict:
    return {
        "id":               row.id,
        "symbol":           row.symbol,
        "added_date":       row.added_date,
        "target_price":     row.target_price,
        "target_direction": row.target_direction.value if row.target_direction else None,
        "notes":            row.notes or "",
        "triggered":        row.triggered,
        "triggered_at":     row.triggered_at.strftime("%Y-%m-%d %H:%M") if row.triggered_at else None,
        "triggered_price":  row.triggered_price,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analyst Team — raw news + reports + price snapshots
# ══════════════════════════════════════════════════════════════════════════════

def insert_raw_news(ticker: str, source: str, articles: list[dict]) -> int:
    """Bulk-insert raw news articles, skipping exact title duplicates. Returns inserted count."""
    session  = SessionLocal()
    inserted = 0
    try:
        for a in articles:
            title = (a.get("title") or "").strip()
            if not title:
                continue
            exists = (
                session.query(RawNews)
                .filter(RawNews.ticker == ticker.upper(), RawNews.title == title)
                .first()
            )
            if not exists:
                session.add(RawNews(
                    ticker       = ticker.upper(),
                    source       = source,
                    title        = title,
                    url          = a.get("url"),
                    published    = a.get("published"),
                    body_summary = (a.get("body_summary") or "")[:400],
                ))
                inserted += 1
        session.commit()
        return inserted
    finally:
        session.close()


def insert_analyst_report(
    ticker:        str,
    analyst_type:  str,
    signal:        str,
    confidence:    float,
    summary:       str,
    key_points:    list[str] | None = None,
    sources_used:  list[dict] | None = None,
    article_count: int | None = None,
    model_used:    str | None = None,
) -> int:
    session = SessionLocal()
    try:
        row = AnalystReport(
            ticker        = ticker.upper(),
            analyst_type  = analyst_type,
            signal        = AnalystSignal[signal.upper()],
            confidence    = round(max(0.0, min(1.0, confidence)), 4),
            summary       = summary,
            key_points    = json.dumps(key_points   or []),
            sources_used  = json.dumps(sources_used or []),
            article_count = article_count,
            model_used    = model_used,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def insert_price_snapshot(ticker: str, data: dict) -> None:
    session = SessionLocal()
    try:
        session.add(PriceSnapshot(
            ticker         = ticker.upper(),
            price          = data.get("price"),
            prev_close     = data.get("prev_close"),
            day_change_pct = data.get("day_change_pct"),
            volume         = data.get("volume"),
            avg_volume     = data.get("avg_volume"),
            market_cap     = data.get("market_cap"),
            pe_ratio       = data.get("pe_ratio"),
            forward_pe     = data.get("forward_pe"),
            week_52_high   = data.get("week_52_high"),
            week_52_low    = data.get("week_52_low"),
            sector         = data.get("sector"),
        ))
        session.commit()
    finally:
        session.close()


def get_recent_raw_news_rows_for_ticker(ticker: str, hours: int = 48, limit: int = 50) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    session = SessionLocal()
    try:
        rows = (
            session.query(RawNews)
            .filter(RawNews.ticker == ticker.upper(), RawNews.collected_at >= cutoff)
            .order_by(RawNews.collected_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":           r.id,
                "ticker":       r.ticker,
                "source":       r.source,
                "title":        r.title,
                "url":          r.url,
                "published":    r.published,
                "body_summary": r.body_summary,
                "collected_at": r.collected_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        session.close()


def insert_or_ignore_news_event(
    raw_news_id: int,
    ticker: str,
    source: str,
    source_tier: str,
    title: str,
    url: str | None,
    published: str | None,
    body_summary: str | None,
    event_tags: list[str],
    novelty_key: str,
    collected_at: str | None = None,
) -> int | None:
    session = SessionLocal()
    try:
        exists = session.query(NewsEvent).filter(NewsEvent.raw_news_id == raw_news_id).first()
        if exists:
            return exists.id

        row = NewsEvent(
            raw_news_id  = raw_news_id,
            ticker       = ticker.upper(),
            source       = source,
            source_tier  = source_tier,
            title        = title,
            url          = url,
            published    = published,
            body_summary = body_summary,
            event_tags   = json.dumps(event_tags or []),
            novelty_key  = novelty_key,
            collected_at = datetime.fromisoformat(collected_at) if collected_at else datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def get_recent_news_events_for_ticker(ticker: str, hours: int = 72, limit: int = 30) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    session = SessionLocal()
    try:
        rows = (
            session.query(NewsEvent)
            .filter(NewsEvent.ticker == ticker.upper(), NewsEvent.collected_at >= cutoff)
            .order_by(NewsEvent.collected_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":           r.id,
                "ticker":       r.ticker,
                "source":       r.source,
                "source_tier":  r.source_tier,
                "title":        r.title,
                "url":          r.url,
                "published":    r.published,
                "body_summary": r.body_summary,
                "event_tags":   json.loads(r.event_tags or "[]"),
                "novelty_key":  r.novelty_key,
                "collected_at": r.collected_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        session.close()


def get_latest_reports(
    ticker:       str,
    analyst_type: str | None = None,
    limit:        int = 5,
) -> list[dict]:
    session = SessionLocal()
    try:
        q = session.query(AnalystReport).filter(AnalystReport.ticker == ticker.upper())
        if analyst_type:
            q = q.filter(AnalystReport.analyst_type == analyst_type)
        rows = q.order_by(AnalystReport.created_at.desc()).limit(limit).all()
        return [_report_to_dict(r) for r in rows]
    finally:
        session.close()


def get_all_latest_reports_for_ticker(ticker: str) -> dict[str, dict]:
    """
    Returns the most recent report per analyst_type for a ticker.
    e.g. { "news": {...}, "sentiment": {...}, "technical": {...} }
    """
    session = SessionLocal()
    try:
        rows = (
            session.query(AnalystReport)
            .filter(AnalystReport.ticker == ticker.upper())
            .order_by(AnalystReport.created_at.desc())
            .all()
        )
        seen = {}
        for r in rows:
            if r.analyst_type not in seen:
                seen[r.analyst_type] = _report_to_dict(r)
        return seen
    finally:
        session.close()


def get_recent_news_for_ticker(ticker: str, hours: int = 24, limit: int = 30) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    session = SessionLocal()
    try:
        rows = (
            session.query(RawNews)
            .filter(RawNews.ticker == ticker.upper(), RawNews.collected_at >= cutoff)
            .order_by(RawNews.collected_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "title":        r.title,
                "source":       r.source,
                "url":          r.url,
                "published":    r.published,
                "body_summary": r.body_summary,
            }
            for r in rows
        ]
    finally:
        session.close()


def get_latest_price_snapshot(ticker: str) -> dict | None:
    session = SessionLocal()
    try:
        row = (
            session.query(PriceSnapshot)
            .filter(PriceSnapshot.ticker == ticker.upper())
            .order_by(PriceSnapshot.snapshot_at.desc())
            .first()
        )
        if not row:
            return None
        return {
            "ticker":         row.ticker,
            "price":          row.price,
            "prev_close":     row.prev_close,
            "day_change_pct": row.day_change_pct,
            "volume":         row.volume,
            "avg_volume":     row.avg_volume,
            "market_cap":     row.market_cap,
            "pe_ratio":       row.pe_ratio,
            "forward_pe":     row.forward_pe,
            "week_52_high":   row.week_52_high,
            "week_52_low":    row.week_52_low,
            "sector":         row.sector,
            "snapshot_at":    row.snapshot_at.isoformat(),
        }
    finally:
        session.close()


def upsert_feature_snapshot(
    run_date: str,
    ticker: str,
    *,
    is_held: bool,
    article_count: int,
    unique_source_count: int,
    high_signal_source_count: int,
    dominant_event_tags: list[str],
    signal_quality: str,
    evidence_score: float,
    triage_score: float,
    block_reasons: list[str],
    candidate_sources: list[str],
    price: float | None,
    day_change_pct: float | None,
    avg_volume_ratio: float | None,
    market_cap: float | None,
    sector: str | None,
    history_context: dict | None,
    feature_json: dict | None,
) -> int:
    session = SessionLocal()
    try:
        row = (
            session.query(TickerFeatureSnapshot)
            .filter(
                TickerFeatureSnapshot.run_date == run_date,
                TickerFeatureSnapshot.ticker == ticker.upper(),
            )
            .order_by(TickerFeatureSnapshot.created_at.desc())
            .first()
        )
        if not row:
            row = TickerFeatureSnapshot(run_date=run_date, ticker=ticker.upper())
            session.add(row)

        row.is_held                  = 1 if is_held else 0
        row.article_count            = article_count
        row.unique_source_count      = unique_source_count
        row.high_signal_source_count = high_signal_source_count
        row.dominant_event_tags      = json.dumps(dominant_event_tags or [])
        row.signal_quality           = signal_quality
        row.evidence_score           = round(float(evidence_score), 4)
        row.triage_score             = round(float(triage_score), 4)
        row.block_reasons            = json.dumps(block_reasons or [])
        row.candidate_sources        = json.dumps(candidate_sources or [])
        row.price                    = price
        row.day_change_pct           = day_change_pct
        row.avg_volume_ratio         = avg_volume_ratio
        row.market_cap               = market_cap
        row.sector                   = sector
        row.history_context          = json.dumps(history_context or {})
        row.feature_json             = json.dumps(feature_json or {})
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def get_latest_feature_snapshot(ticker: str, run_date: str | None = None) -> dict | None:
    session = SessionLocal()
    try:
        q = session.query(TickerFeatureSnapshot).filter(TickerFeatureSnapshot.ticker == ticker.upper())
        if run_date:
            q = q.filter(TickerFeatureSnapshot.run_date == run_date)
        row = q.order_by(TickerFeatureSnapshot.created_at.desc()).first()
        return _feature_snapshot_to_dict(row) if row else None
    finally:
        session.close()


def get_feature_snapshots_for_run(run_date: str) -> list[dict]:
    session = SessionLocal()
    try:
        rows = (
            session.query(TickerFeatureSnapshot)
            .filter(TickerFeatureSnapshot.run_date == run_date)
            .order_by(TickerFeatureSnapshot.triage_score.desc(), TickerFeatureSnapshot.ticker.asc())
            .all()
        )
        return [_feature_snapshot_to_dict(r) for r in rows]
    finally:
        session.close()


def _feature_snapshot_to_dict(row: TickerFeatureSnapshot) -> dict:
    return {
        "id":                      row.id,
        "run_date":                row.run_date,
        "ticker":                  row.ticker,
        "is_held":                 bool(row.is_held),
        "article_count":           row.article_count,
        "unique_source_count":     row.unique_source_count,
        "high_signal_source_count": row.high_signal_source_count,
        "dominant_event_tags":     json.loads(row.dominant_event_tags or "[]"),
        "signal_quality":          row.signal_quality,
        "evidence_score":          row.evidence_score,
        "triage_score":            row.triage_score,
        "block_reasons":           json.loads(row.block_reasons or "[]"),
        "candidate_sources":       json.loads(row.candidate_sources or "[]"),
        "price":                   row.price,
        "day_change_pct":          row.day_change_pct,
        "avg_volume_ratio":        row.avg_volume_ratio,
        "market_cap":              row.market_cap,
        "sector":                  row.sector,
        "history_context":         json.loads(row.history_context or "{}"),
        "feature_json":            json.loads(row.feature_json or "{}"),
        "created_at":              row.created_at.isoformat(),
    }


def replace_universe_candidates(run_date: str, candidates: list[dict]) -> None:
    session = SessionLocal()
    try:
        session.query(UniverseCandidate).filter(UniverseCandidate.run_date == run_date).delete()
        for item in candidates:
            session.add(UniverseCandidate(
                run_date         = run_date,
                ticker           = item["ticker"].upper(),
                candidate_source = item.get("candidate_source", "feature_store"),
                score            = round(float(item.get("score", 0.0)), 4),
                reason           = item.get("reason"),
                is_held          = 1 if item.get("is_held") else 0,
                triage_status    = item.get("triage_status", "filtered"),
                llm_reviewed     = 1 if item.get("llm_reviewed") else 0,
                trade_ready      = 1 if item.get("trade_ready") else 0,
                skip_reason      = item.get("skip_reason"),
            ))
        session.commit()
    finally:
        session.close()


def mark_universe_candidate_reviewed(run_date: str, ticker: str, *, trade_ready: bool = True) -> None:
    session = SessionLocal()
    try:
        row = (
            session.query(UniverseCandidate)
            .filter(
                UniverseCandidate.run_date == run_date,
                UniverseCandidate.ticker == ticker.upper(),
            )
            .order_by(UniverseCandidate.created_at.desc())
            .first()
        )
        if row:
            row.llm_reviewed = 1
            row.trade_ready  = 1 if trade_ready else 0
            session.commit()
    finally:
        session.close()


def get_latest_universe_run_date() -> str | None:
    session = SessionLocal()
    try:
        row = (
            session.query(UniverseCandidate.run_date)
            .order_by(UniverseCandidate.run_date.desc())
            .first()
        )
        return row.run_date if row else None
    finally:
        session.close()


def get_trade_ready_tickers(run_date: str | None = None) -> set[str]:
    session = SessionLocal()
    try:
        target_run = run_date or get_latest_universe_run_date()
        if not target_run:
            return set()
        rows = (
            session.query(UniverseCandidate.ticker)
            .filter(
                UniverseCandidate.run_date == target_run,
                UniverseCandidate.trade_ready == 1,
                UniverseCandidate.llm_reviewed == 1,
            )
            .all()
        )
        return {r.ticker for r in rows}
    finally:
        session.close()


def _report_to_dict(r: AnalystReport) -> dict:
    return {
        "id":            r.id,
        "ticker":        r.ticker,
        "analyst_type":  r.analyst_type,
        "signal":        r.signal.value,
        "confidence":    r.confidence,
        "summary":       r.summary,
        "key_points":    json.loads(r.key_points   or "[]"),
        "sources_used":  json.loads(r.sources_used or "[]"),
        "article_count": r.article_count,
        "model_used":    r.model_used,
        "created_at":    r.created_at.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Researcher Team — research_verdicts
# ══════════════════════════════════════════════════════════════════════════════

def insert_research_verdict(
    ticker:          str,
    verdict:         str,
    conviction:      float,
    bull_case:       str,
    bear_case:       str,
    final_reasoning: str,
    key_risks:       list | None = None,
    key_catalysts:   list | None = None,
    analyst_signals: dict | None = None,
    model_used:      str  | None = None,
) -> int:
    session = SessionLocal()
    try:
        row = ResearchVerdictRow(
            ticker          = ticker.upper(),
            verdict         = ResearchVerdict[verdict.upper()],
            conviction      = round(max(0.0, min(1.0, conviction)), 4),
            bull_case       = bull_case,
            bear_case       = bear_case,
            final_reasoning = final_reasoning,
            key_risks       = json.dumps(key_risks       or []),
            key_catalysts   = json.dumps(key_catalysts   or []),
            analyst_signals = json.dumps(analyst_signals or {}),
            model_used      = model_used,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def get_latest_verdict(ticker: str) -> dict | None:
    session = SessionLocal()
    try:
        row = (
            session.query(ResearchVerdictRow)
            .filter(ResearchVerdictRow.ticker == ticker.upper())
            .order_by(ResearchVerdictRow.created_at.desc())
            .first()
        )
        return _verdict_to_dict(row) if row else None
    finally:
        session.close()


def get_latest_verdict_since(
    ticker: str,
    created_at_or_after: datetime,
    previous_id: int | None = None,
) -> dict | None:
    session = SessionLocal()
    try:
        q = (
            session.query(ResearchVerdictRow)
            .filter(
                ResearchVerdictRow.ticker == ticker.upper(),
                ResearchVerdictRow.created_at >= created_at_or_after,
            )
            .order_by(ResearchVerdictRow.created_at.desc(), ResearchVerdictRow.id.desc())
        )
        if previous_id is not None:
            q = q.filter(ResearchVerdictRow.id != previous_id)
        row = q.first()
        return _verdict_to_dict(row) if row else None
    finally:
        session.close()


def get_actionable_verdicts(min_conviction: float = 0.6, hours: int = 48) -> list[dict]:
    """
    Returns BUY/STRONG_BUY/SELL/STRONG_SELL verdicts with conviction >= threshold.
    Default window is 48 hours so verdicts from yesterday's run still trade today.
    """
    cutoff        = datetime.utcnow() - timedelta(hours=hours)
    action_values = [
        ResearchVerdict.STRONG_BUY,
        ResearchVerdict.BUY,
        ResearchVerdict.SELL,
        ResearchVerdict.STRONG_SELL,
    ]
    session = SessionLocal()
    try:
        rows = (
            session.query(ResearchVerdictRow)
            .filter(
                ResearchVerdictRow.conviction >= min_conviction,
                ResearchVerdictRow.verdict.in_(action_values),
                ResearchVerdictRow.created_at >= cutoff,
            )
            .order_by(ResearchVerdictRow.conviction.desc())
            .all()
        )
        return [_verdict_to_dict(r) for r in rows]
    finally:
        session.close()


def _verdict_to_dict(r: ResearchVerdictRow) -> dict:
    return {
        "id":               r.id,
        "ticker":           r.ticker,
        "verdict":          r.verdict.value,
        "conviction":       r.conviction,
        "bull_case":        r.bull_case,
        "bear_case":        r.bear_case,
        "final_reasoning":  r.final_reasoning,
        "key_risks":        json.loads(r.key_risks       or "[]"),
        "key_catalysts":    json.loads(r.key_catalysts   or "[]"),
        "analyst_signals":  json.loads(r.analyst_signals or "{}"),
        "model_used":       r.model_used,
        "created_at":       r.created_at.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Trader Team — trade_decisions
# Full audit trail of every action the trader agent takes (buy, sell, or skip).
# ══════════════════════════════════════════════════════════════════════════════

class TradeDecision(Base):
    __tablename__ = "trade_decisions"
    id          = Column(Integer,     primary_key=True, autoincrement=True)
    ticker      = Column(String(10),  nullable=False)
    action      = Column(String(10),  nullable=False)   # "BUY" | "SELL" | "SKIP"
    quantity    = Column(Integer,     nullable=False, default=0)
    price       = Column(Float,       nullable=False, default=0.0)
    conviction  = Column(Float,       nullable=True)    # verdict conviction at time of trade
    rationale   = Column(Text,        nullable=False)   # LLM's stated reasoning
    verdict_id  = Column(Integer,     nullable=True)    # FK to research_verdicts.id
    alpaca_id   = Column(String(64),  nullable=True)    # Alpaca order UUID
    status      = Column(String(20),  nullable=False, default="pending")
    created_at  = Column(DateTime,    default=datetime.utcnow)

Index("ix_trade_decisions_ticker",  TradeDecision.ticker)
Index("ix_trade_decisions_created", TradeDecision.created_at)

# Ensure new table is created automatically
Base.metadata.create_all(bind=engine)


class SignalEvaluation(Base):
    __tablename__ = "signal_evaluations"
    id                     = Column(Integer,     primary_key=True, autoincrement=True)
    source_type            = Column(String(20),  nullable=False)   # "verdict" | "trade"
    source_id              = Column(Integer,     nullable=False)
    ticker                 = Column(String(10),  nullable=False)
    direction              = Column(String(10),  nullable=False)   # "BUY" | "SELL"
    horizon_days           = Column(Integer,     nullable=False)
    reference_date         = Column(String(10),  nullable=False)
    reference_price        = Column(Float,       nullable=False)
    evaluation_date        = Column(String(10),  nullable=False)
    evaluation_price       = Column(Float,       nullable=False)
    raw_return_pct         = Column(Float,       nullable=False)
    benchmark_return_pct   = Column(Float,       nullable=False)
    thesis_return_pct      = Column(Float,       nullable=False)
    excess_return_pct      = Column(Float,       nullable=False)
    outcome                = Column(String(20),  nullable=False)   # "win" | "loss" | "flat"
    notes                  = Column(Text,        nullable=True)
    evaluated_at           = Column(DateTime,    default=datetime.utcnow)

Index("ix_signal_evaluations_source", SignalEvaluation.source_type, SignalEvaluation.source_id, SignalEvaluation.horizon_days)
Index("ix_signal_evaluations_ticker", SignalEvaluation.ticker, SignalEvaluation.evaluated_at)

Base.metadata.create_all(bind=engine)


def insert_trade_decision(
    ticker:     str,
    action:     str,
    quantity:   int,
    price:      float,
    conviction: float,
    rationale:  str,
    verdict_id: int   | None = None,
    alpaca_id:  str   | None = None,
    status:     str          = "pending",
) -> int:
    """Insert a trade decision record. Returns row id."""
    session = SessionLocal()
    try:
        row = TradeDecision(
            ticker     = ticker.upper(),
            action     = action.upper(),
            quantity   = quantity,
            price      = price,
            conviction = conviction,
            rationale  = rationale,
            verdict_id = verdict_id,
            alpaca_id  = alpaca_id,
            status     = status,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def get_trade_decisions_for_evaluation(days: int = 30) -> list[dict]:
    """Returns filled BUY/SELL trade decisions for evaluation."""
    cutoff  = datetime.utcnow() - timedelta(days=days)
    session = SessionLocal()
    try:
        rows = (
            session.query(TradeDecision)
            .filter(
                TradeDecision.created_at >= cutoff,
                TradeDecision.status == "filled",
                TradeDecision.action.in_(["BUY", "SELL"]),
            )
            .order_by(TradeDecision.created_at.desc())
            .all()
        )
        return [_decision_to_dict(r) for r in rows]
    finally:
        session.close()


def get_recent_trade_decisions(minutes: int = 60) -> list[dict]:
    """Returns trade decisions from the last N minutes — used by run_trader() summary."""
    cutoff  = datetime.utcnow() - timedelta(minutes=minutes)
    session = SessionLocal()
    try:
        rows = (
            session.query(TradeDecision)
            .filter(TradeDecision.created_at >= cutoff)
            .order_by(TradeDecision.created_at.desc())
            .all()
        )
        return [_decision_to_dict(r) for r in rows]
    finally:
        session.close()


def get_all_trade_decisions(ticker: str | None = None, limit: int = 50) -> list[dict]:
    """Returns trade decisions, optionally filtered by ticker. Used for reporting."""
    session = SessionLocal()
    try:
        q = session.query(TradeDecision)
        if ticker:
            q = q.filter(TradeDecision.ticker == ticker.upper())
        rows = q.order_by(TradeDecision.created_at.desc()).limit(limit).all()
        return [_decision_to_dict(r) for r in rows]
    finally:
        session.close()


def _decision_to_dict(r: TradeDecision) -> dict:
    return {
        "id":         r.id,
        "ticker":     r.ticker,
        "action":     r.action,
        "quantity":   r.quantity,
        "price":      r.price,
        "conviction": r.conviction,
        "rationale":  r.rationale,
        "verdict_id": r.verdict_id,
        "alpaca_id":  r.alpaca_id,
        "status":     r.status,
        "created_at": r.created_at.isoformat(),
    }


def get_research_verdicts_for_evaluation(days: int = 30) -> list[dict]:
    """Returns recent non-HOLD research verdicts for ex-post evaluation."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    session = SessionLocal()
    try:
        rows = (
            session.query(ResearchVerdictRow)
            .filter(
                ResearchVerdictRow.created_at >= cutoff,
                ResearchVerdictRow.verdict != ResearchVerdict.HOLD,
            )
            .order_by(ResearchVerdictRow.created_at.desc())
            .all()
        )
        return [_verdict_to_dict(r) for r in rows]
    finally:
        session.close()


def get_existing_signal_evaluations(source_type: str) -> set[tuple[int, int]]:
    """
    Returns {(source_id, horizon_days)} for the given source type.
    Used to avoid inserting duplicate evaluations.
    """
    session = SessionLocal()
    try:
        rows = (
            session.query(SignalEvaluation.source_id, SignalEvaluation.horizon_days)
            .filter(SignalEvaluation.source_type == source_type)
            .all()
        )
        return {(row.source_id, row.horizon_days) for row in rows}
    finally:
        session.close()


def insert_signal_evaluation(
    source_type: str,
    source_id: int,
    ticker: str,
    direction: str,
    horizon_days: int,
    reference_date: str,
    reference_price: float,
    evaluation_date: str,
    evaluation_price: float,
    raw_return_pct: float,
    benchmark_return_pct: float,
    thesis_return_pct: float,
    excess_return_pct: float,
    outcome: str,
    notes: str | None = None,
) -> int:
    session = SessionLocal()
    try:
        row = SignalEvaluation(
            source_type          = source_type,
            source_id            = source_id,
            ticker               = ticker.upper(),
            direction            = direction.upper(),
            horizon_days         = horizon_days,
            reference_date       = reference_date,
            reference_price      = reference_price,
            evaluation_date      = evaluation_date,
            evaluation_price     = evaluation_price,
            raw_return_pct       = raw_return_pct,
            benchmark_return_pct = benchmark_return_pct,
            thesis_return_pct    = thesis_return_pct,
            excess_return_pct    = excess_return_pct,
            outcome              = outcome,
            notes                = notes,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def get_recent_signal_evaluations(days: int = 30) -> list[dict]:
    cutoff  = datetime.utcnow() - timedelta(days=days)
    session = SessionLocal()
    try:
        rows = (
            session.query(SignalEvaluation)
            .filter(SignalEvaluation.evaluated_at >= cutoff)
            .order_by(SignalEvaluation.evaluated_at.desc())
            .all()
        )
        return [
            {
                "id":                   r.id,
                "source_type":          r.source_type,
                "source_id":            r.source_id,
                "ticker":               r.ticker,
                "direction":            r.direction,
                "horizon_days":         r.horizon_days,
                "reference_date":       r.reference_date,
                "reference_price":      r.reference_price,
                "evaluation_date":      r.evaluation_date,
                "evaluation_price":     r.evaluation_price,
                "raw_return_pct":       r.raw_return_pct,
                "benchmark_return_pct": r.benchmark_return_pct,
                "thesis_return_pct":    r.thesis_return_pct,
                "excess_return_pct":    r.excess_return_pct,
                "outcome":              r.outcome,
                "notes":                r.notes,
                "evaluated_at":         r.evaluated_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        session.close()


def get_feature_snapshots_between_dates(start_date: str, end_date: str) -> list[dict]:
    session = SessionLocal()
    try:
        rows = (
            session.query(TickerFeatureSnapshot)
            .filter(
                TickerFeatureSnapshot.run_date >= start_date,
                TickerFeatureSnapshot.run_date <= end_date,
            )
            .order_by(TickerFeatureSnapshot.run_date.asc(), TickerFeatureSnapshot.triage_score.desc())
            .all()
        )
        return [_feature_snapshot_to_dict(r) for r in rows]
    finally:
        session.close()


def get_actionable_verdicts_for_date(run_date: str, min_conviction: float = 0.68) -> list[dict]:
    start_dt = datetime.fromisoformat(run_date)
    end_dt = start_dt + timedelta(days=1)
    action_values = [
        ResearchVerdict.STRONG_BUY,
        ResearchVerdict.BUY,
        ResearchVerdict.SELL,
        ResearchVerdict.STRONG_SELL,
    ]
    session = SessionLocal()
    try:
        rows = (
            session.query(ResearchVerdictRow)
            .filter(
                ResearchVerdictRow.created_at >= start_dt,
                ResearchVerdictRow.created_at < end_dt,
                ResearchVerdictRow.conviction >= min_conviction,
                ResearchVerdictRow.verdict.in_(action_values),
            )
            .order_by(ResearchVerdictRow.conviction.desc())
            .all()
        )
        return [_verdict_to_dict(r) for r in rows]
    finally:
        session.close()


def insert_simulation_run(start_date: str, end_date: str, initial_cash: float) -> int:
    session = SessionLocal()
    try:
        row = SimulationRun(
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            ending_cash=initial_cash,
            ending_equity=initial_cash,
            metrics_json=json.dumps({}),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def update_simulation_run(simulation_run_id: int, ending_cash: float, ending_equity: float, metrics: dict) -> None:
    session = SessionLocal()
    try:
        row = session.query(SimulationRun).filter(SimulationRun.id == simulation_run_id).first()
        if row:
            row.ending_cash = ending_cash
            row.ending_equity = ending_equity
            row.metrics_json = json.dumps(metrics or {})
            session.commit()
    finally:
        session.close()


def insert_simulation_position(
    simulation_run_id: int,
    trade_date: str,
    ticker: str,
    action: str,
    quantity: int,
    price: float,
    cash_after: float,
    equity_after: float,
    notes: str | None = None,
) -> int:
    session = SessionLocal()
    try:
        row = SimulationPosition(
            simulation_run_id=simulation_run_id,
            trade_date=trade_date,
            ticker=ticker.upper(),
            action=action.upper(),
            quantity=quantity,
            price=price,
            cash_after=cash_after,
            equity_after=equity_after,
            notes=notes,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()
