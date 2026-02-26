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

def create_order(symbol: str, price: float, quantity: int, trade_type: str) -> int:
    session = SessionLocal()
    try:
        order = OrderHistory(
            symbol=symbol.upper(),
            price=price,
            quantity=quantity,
            trade_type=TradeType(trade_type),
            status=OrderStatus.pending,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id
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
                "id": o.id,
                "symbol": o.symbol,
                "price": o.price,
                "quantity": o.quantity,
                "trade_type": o.trade_type.value,
                "status": o.status.value,
                "timestamp": o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for o in orders
        ]
    finally:
        session.close()