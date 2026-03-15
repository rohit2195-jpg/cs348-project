"""
database.py — SQLite persistence layer
Stores portfolio positions and order history locally.
get_portfolio_for_chart() returns a React-ready list for the frontend.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum

DATABASE_URL = "sqlite:///my_database.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Portfolio(Base):
    __tablename__ = "Portfolio"
    symbol = Column(String(10), primary_key=True)
    purchasePrice = Column(Float)
    quantity = Column(Integer)
    purchaseDate = Column(String(10))


class OrderStatus(enum.Enum):
    pending = "pending"
    filled = "filled"
    canceled = "canceled"


class TradeType(enum.Enum):
    buy = "buy"
    sell = "sell"


class OrderHistory(Base):
    __tablename__ = "order_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    trade_type = Column(Enum(TradeType), nullable=False)
    alpaca_order_id = Column(String(64), nullable=True)  # Alpaca UUID, set after submission


Base.metadata.create_all(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


# ── Portfolio ────────────────────────────────────────────────────────────────

def get_portfolio():
    """Return raw ORM rows (used internally by the terminal UI)."""
    session = SessionLocal()
    try:
        return session.query(Portfolio).all()
    finally:
        session.close()


def get_portfolio_for_chart() -> list:
    """
    React/chart-ready export of current portfolio.
    Returns list of {"symbol", "purchasePrice", "quantity", "purchaseDate"}
    — pass directly to trading.get_portfolio_vs_spy().
    """
    session = SessionLocal()
    try:
        rows = session.query(Portfolio).all()
        return [
            {
                "symbol": r.symbol,
                "purchasePrice": r.purchasePrice,
                "quantity": r.quantity,
                "purchaseDate": r.purchaseDate,
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
                "symbol": row.symbol,
                "quantity": row.quantity,
                "purchasePrice": row.purchasePrice,
                "purchaseDate": row.purchaseDate,
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
                row.quantity = quantity
                row.purchasePrice = price
        else:
            row = Portfolio(
                symbol=symbol.upper(),
                purchasePrice=price,
                quantity=quantity,
                purchaseDate=date,
            )
            session.add(row)
        session.commit()
    finally:
        session.close()


# ── Orders ───────────────────────────────────────────────────────────────────

def create_order(symbol: str, price: float, quantity: int, trade_type: str,
                 alpaca_order_id: str = None) -> int:
    session = SessionLocal()
    try:
        order = OrderHistory(
            symbol=symbol.upper(),
            price=price,
            quantity=quantity,
            trade_type=TradeType(trade_type),
            status=OrderStatus.pending,
            alpaca_order_id=alpaca_order_id,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id
    finally:
        session.close()


def set_alpaca_order_id(order_id: int, alpaca_order_id: str):
    """Store the Alpaca UUID against a local order record."""
    session = SessionLocal()
    try:
        order = session.query(OrderHistory).get(order_id)
        if order:
            order.alpaca_order_id = alpaca_order_id
            session.commit()
    finally:
        session.close()


def get_alpaca_order_id(order_id: int):
    """Retrieve the Alpaca UUID for a local order."""
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
    """Returns list of plain dicts — safe outside session, React-ready."""
    session = SessionLocal()
    try:
        orders = (
            session.query(OrderHistory)
            .order_by(OrderHistory.timestamp.desc())
            .all()
        )
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


# ── Filter & Report ──────────────────────────────────────────────────────────

def get_symbols() -> list:
    """Return all unique symbols from both portfolio and order history.
    Used to build dynamic dropdowns in the frontend — never hardcoded."""
    session = SessionLocal()
    try:
        portfolio_syms = [r.symbol for r in session.query(Portfolio.symbol).distinct()]
        order_syms     = [r.symbol for r in session.query(OrderHistory.symbol).distinct()]
        return sorted(set(portfolio_syms + order_syms))
    finally:
        session.close()


def filter_orders(
    symbols:    list  = None,   # [] means all
    trade_type: str   = None,   # "buy" | "sell" | None = both
    status:     str   = None,   # "filled" | "pending" | "canceled" | None = all
    date_from:  str   = None,   # "YYYY-MM-DD"
    date_to:    str   = None,   # "YYYY-MM-DD"
    price_min:  float = None,
    price_max:  float = None,
) -> list:
    """
    Filtered order history — all params optional.
    Returns list of plain dicts (React-ready, safe outside session).
    This query is built dynamically so the frontend drives the filters.
    """
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
            # inclusive — add 1 day so "to 2024-03-01" includes that whole day
            from datetime import timedelta
            q = q.filter(OrderHistory.timestamp < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        if price_min is not None:
            q = q.filter(OrderHistory.price >= price_min)
        if price_max is not None:
            q = q.filter(OrderHistory.price <= price_max)

        orders = q.order_by(OrderHistory.timestamp.desc()).all()
        return [
            {
                "id":         o.id,
                "symbol":     o.symbol,
                "price":      o.price,
                "quantity":   o.quantity,
                "trade_type": o.trade_type.value,
                "status":     o.status.value,
                "timestamp":  o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "total_value": round(o.price * o.quantity, 2),
            }
            for o in orders
        ]
    finally:
        session.close()


def filter_portfolio(
    symbols:   list  = None,
    pl_min:    float = None,   # P/L % min
    pl_max:    float = None,   # P/L % max
    val_min:   float = None,   # market value min
    val_max:   float = None,   # market value max
    prices:    dict  = None,   # {symbol: current_price} — injected by server
) -> list:
    """
    Filtered portfolio — P/L and value filters require live prices
    which are injected by the server layer (keeps DB layer clean).
    Returns plain dicts with full P/L data.
    """
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
        current    = prices.get(r.symbol, 0.0)
        pl_val     = (current - r.purchasePrice) * r.quantity
        pl_pct     = ((current - r.purchasePrice) / r.purchasePrice * 100) if r.purchasePrice else 0
        mkt_value  = round(current * r.quantity, 2)

        # Apply numeric filters (post-query since they need live prices)
        if pl_min  is not None and pl_pct  < pl_min:  continue
        if pl_max  is not None and pl_pct  > pl_max:  continue
        if val_min is not None and mkt_value < val_min: continue
        if val_max is not None and mkt_value > val_max: continue

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
    """Fetch a single order as a plain dict — used for before/after reports."""
    session = SessionLocal()
    try:
        o = session.query(OrderHistory).get(order_id)
        if not o:
            return None
        return {
            "id":         o.id,
            "symbol":     o.symbol,
            "price":      o.price,
            "quantity":   o.quantity,
            "trade_type": o.trade_type.value,
            "status":     o.status.value,
            "timestamp":  o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "total_value": round(o.price * o.quantity, 2),
        }
    finally:
        session.close()


def get_portfolio_snapshot() -> list:
    """Full portfolio snapshot as plain dicts — used for before/after diff reports."""
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


# ── Watchlist ─────────────────────────────────────────────────────────────────

class TargetDirection(enum.Enum):
    above = "above"   # alert when price rises ABOVE target
    below = "below"   # alert when price falls BELOW target

class Watchlist(Base):
    __tablename__ = "watchlist"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    symbol          = Column(String(10), nullable=False, unique=True)
    added_date      = Column(String(10), nullable=False)   # YYYY-MM-DD
    target_price    = Column(Float, nullable=True)         # None = watch only, no alert
    target_direction= Column(Enum(TargetDirection), nullable=True)
    notes           = Column(String(500), nullable=True)
    triggered       = Column(Integer, default=0)           # 0=pending, 1=triggered, 2=dismissed
    triggered_at    = Column(DateTime, nullable=True)
    triggered_price = Column(Float, nullable=True)


def add_to_watchlist(symbol: str, target_price: float = None,
                     target_direction: str = None, notes: str = None) -> dict:
    """Add a symbol to the watchlist. Returns the new row as a dict."""
    session = SessionLocal()
    try:
        existing = session.query(Watchlist).filter(
            Watchlist.symbol == symbol.upper()
        ).first()
        if existing:
            # Update instead of duplicate
            if target_price    is not None: existing.target_price     = target_price
            if target_direction is not None: existing.target_direction = TargetDirection(target_direction)
            if notes           is not None: existing.notes            = notes
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
        row = session.query(Watchlist).filter(
            Watchlist.symbol == symbol.upper()
        ).first()
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
    """Only rows with untriggered targets — used by the settler."""
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
        row = session.query(Watchlist).filter(
            Watchlist.symbol == symbol.upper()
        ).first()
        if row:
            row.triggered       = 1
            row.triggered_at    = datetime.utcnow()
            row.triggered_price = price
            session.commit()
    finally:
        session.close()


def dismiss_watchlist_alert(symbol: str):
    """Mark alert as seen/dismissed (triggered=2) without removing the entry."""
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(
            Watchlist.symbol == symbol.upper()
        ).first()
        if row:
            row.triggered = 2
            session.commit()
    finally:
        session.close()


def update_watchlist_entry(symbol: str, target_price=None,
                           target_direction=None, notes=None):
    session = SessionLocal()
    try:
        row = session.query(Watchlist).filter(
            Watchlist.symbol == symbol.upper()
        ).first()
        if not row:
            return None
        if target_price     is not None: row.target_price     = target_price if target_price != "" else None
        if target_direction is not None: row.target_direction = TargetDirection(target_direction) if target_direction else None
        if notes            is not None: row.notes            = notes
        # Reset trigger state when target changes
        row.triggered       = 0
        row.triggered_at    = None
        row.triggered_price = None
        session.commit()
        return _watchlist_dict(row)
    finally:
        session.close()


def get_unread_alerts() -> list:
    """Triggered but not yet dismissed."""
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