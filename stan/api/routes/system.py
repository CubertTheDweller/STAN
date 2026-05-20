"""System health (/api/status) and metrics (/api/metrics) endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from stan.collectors.state import get_state
from stan.config import DB_PATH
from stan.database.db import get_db
from stan.database.models import NewsArticle, NewsImpact, PriceSnapshot, Ticker

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Return last collection timestamps, error counts, and DB row counts."""
    state = get_state()
    return {
        "last_stock_collection": state["last_stock_ts"],
        "last_news_collection":  state["last_news_ts"],
        "stock_error_count":     state["stock_errors"],
        "news_error_count":      state["news_errors"],
        "db_counts": {
            "tickers":        db.query(func.count(Ticker.symbol)).scalar(),
            "price_snapshots": db.query(func.count(PriceSnapshot.id)).scalar(),
            "news_articles":  db.query(func.count(NewsArticle.id)).scalar(),
        },
    }


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """Return detailed operational metrics including impact fill rate and DB size."""
    state = get_state()
    filled  = db.query(func.count(NewsImpact.id)).filter(NewsImpact.interval_price.isnot(None)).scalar()
    pending = db.query(func.count(NewsImpact.id)).filter(NewsImpact.interval_price.is_(None)).scalar()
    db_path = Path(DB_PATH)
    db_size = db_path.stat().st_size if db_path.exists() else 0
    return {
        "collection": {
            "stock_runs":    state["stock_runs"],
            "stock_errors":  state["stock_errors"],
            "news_runs":     state["news_runs"],
            "news_errors":   state["news_errors"],
            "last_stock_ts": state["last_stock_ts"],
            "last_news_ts":  state["last_news_ts"],
        },
        "database": {
            "price_snapshots":     db.query(func.count(PriceSnapshot.id)).scalar(),
            "news_articles":       db.query(func.count(NewsArticle.id)).scalar(),
            "news_impact_filled":  filled,
            "news_impact_pending": pending,
            "db_size_bytes":       db_size,
        },
    }
