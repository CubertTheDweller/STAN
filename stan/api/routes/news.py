"""REST endpoints for news articles and chart markers."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from stan.database.db import get_db
from stan.database.models import NewsArticle, NewsTicker

router = APIRouter(prefix="/api/news", tags=["news"])

_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _article_dict(article: NewsArticle, db: Session) -> dict:
    tickers = [nt.symbol for nt in db.query(NewsTicker).filter_by(article_id=article.id).all()]
    return {
        "id": article.id,
        "source": article.source,
        "headline": article.headline,
        "description": article.description,
        "url": article.url,
        "published_at": article.published_at.isoformat() + "Z" if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat() + "Z" if article.fetched_at else None,
        "tickers": tickers,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
def list_news(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return recent news articles, newest first."""
    total = db.query(NewsArticle).count()
    articles = (
        db.query(NewsArticle)
        .order_by(desc(NewsArticle.published_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_article_dict(a, db) for a in articles],
    }


@router.get("/markers")
def get_news_markers(
    symbol: str = Query(..., description="Ticker symbol"),
    period: str = Query(default="1d", pattern="^(1d|5d|1mo|3mo)$"),
    db: Session = Depends(get_db),
):
    """Return news events as TradingView Lightweight Charts marker objects."""
    symbol = symbol.upper()
    days = _PERIOD_DAYS.get(period, 1)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    articles = (
        db.query(NewsArticle)
        .join(NewsTicker, NewsArticle.id == NewsTicker.article_id)
        .filter(
            NewsTicker.symbol == symbol,
            NewsArticle.published_at >= cutoff,
        )
        .order_by(NewsArticle.published_at)
        .all()
    )

    markers = []
    for article in articles:
        ts = article.published_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        markers.append(
            {
                "time": int(ts.timestamp()),
                "position": "aboveBar",
                "color": "#f68410",
                "shape": "circle",
                "text": "N",
                "id": str(article.id),
                # Extra fields used by the UI detail panel — not part of Lightweight Charts spec
                "headline": article.headline,
                "description": article.description,
                "url": article.url,
                "source": article.source,
            }
        )

    return {"symbol": symbol, "period": period, "markers": markers}


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    """Return a single news article by ID."""
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return _article_dict(article, db)
