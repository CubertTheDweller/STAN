"""SQLAlchemy ORM models for STAN."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    """Known ticker symbols seeded from the S&P 500 list."""

    __tablename__ = "tickers"

    symbol = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=True)
    exchange = Column(String(50), nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceSnapshot(Base):
    """One OHLCV record per ticker per 5-minute poll cycle — each row is one candle."""

    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), ForeignKey("tickers.symbol", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_price_symbol_timestamp"),
    )


class NewsArticle(Base):
    """A single news article fetched from an RSS feed."""

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=True)
    headline = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(2048), nullable=False, unique=True)
    published_at = Column(DateTime, nullable=True, index=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    tickers = relationship(
        "NewsTicker",
        back_populates="article",
        cascade="all, delete-orphan",
        lazy="select",
    )


class NewsTicker(Base):
    """Many-to-many link between a news article and mentioned ticker symbols."""

    __tablename__ = "news_tickers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    article = relationship("NewsArticle", back_populates="tickers")

    __table_args__ = (
        UniqueConstraint("article_id", "symbol", name="uq_news_article_symbol"),
    )
