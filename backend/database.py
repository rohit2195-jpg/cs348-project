from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///my_database.db"

engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Portfolio(Base):
    __tablename__ = "Portfolio"

    transaction_id = Column(Integer, primary_key=True)
    symbol = Column(String(4))
    currentPrice = Column(Integer)
    purchasePrice = Column(Integer)
    quantity = Column(Integer)
    totalValue = Column(Integer)
    totalGain = Column(Integer)




def init_db():
    Base.metadata.create_all(bind=engine)


def add_test_entry(trans_id, symbol, currentPrice, purchasePrice, quantity, totalValue, totalGain):
    session = SessionLocal()
    try:
        entry = Portfolio(trans_id, symbol, currentPrice, purchasePrice, quantity, totalValue, totalGain)
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry
    finally:
        session.close()


def get_all_test_entries():
    session = SessionLocal()
    try:
        return session.query(Portfolio).all()
    finally:
        session.close()
