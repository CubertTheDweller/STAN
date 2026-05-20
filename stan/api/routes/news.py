"""REST endpoints for news articles and chart markers."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from stan.database.db import get_db
from stan.database.models import NewsArticle, NewsImpact, NewsTicker, PriceSnapshot, Ticker

router = APIRouter(prefix="/api/news", tags=["news"])

_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90}

# ── News category classifier ──────────────────────────────────────────────────

# Each entry: (category_name, hex_color, marker_text, keyword_list)
# Evaluated in order — first match wins.
_CATEGORIES: list[tuple[str, str, str, list[str]]] = [
    (
        "fed",
        "#ef5350",
        "F",
        [
            "federal reserve",
            "the fed ",
            " fed ",
            "fomc",
            "interest rate",
            "rate hike",
            "rate cut",
            "inflation",
            "cpi",
            "ppi",
            "powell",
            "treasury yield",
            "monetary policy",
            "quantitative",
            "basis point",
        ],
    ),
    (
        "earnings",
        "#26a69a",
        "E",
        [
            "earnings",
            "revenue",
            "quarterly",
            " eps",
            "beat estimates",
            "missed estimates",
            "guidance",
            "dividend",
            "buyback",
            "q1 ",
            "q2 ",
            "q3 ",
            "q4 ",
        ],
    ),
    (
        "economic",
        "#00bcd4",
        "D",
        [
            "gdp",
            "unemployment",
            "jobs report",
            "nonfarm payroll",
            "retail sales",
            "housing",
            "consumer confidence",
            "manufacturing",
            "pmi ",
            "ism ",
            "recession",
            "labor market",
        ],
    ),
    (
        "tech",
        "#2196f3",
        "T",
        [
            "artificial intelligence",
            " ai ",
            "machine learning",
            "semiconductor",
            " chip",
            "software",
            "cloud",
            "cybersecurity",
            "data center",
            "blockchain",
            "crypto",
            "bitcoin",
        ],
    ),
    (
        "geopolitical",
        "#9c27b0",
        "G",
        [
            "war",
            "conflict",
            "sanction",
            "tariff",
            "trade war",
            "geopolitical",
            "military",
            "ukraine",
            "russia",
            "iran",
            "north korea",
            "taiwan",
            "nato",
            "missile",
            "diplomacy",
        ],
    ),
    (
        "energy",
        "#ff9800",
        "O",
        [
            "crude oil",
            "oil price",
            "opec",
            "natural gas",
            "energy prices",
            "solar",
            "wind power",
            "electric vehicle",
            "petroleum",
            "refinery",
            "pipeline",
            "lng",
        ],
    ),
    (
        "merger",
        "#e040fb",
        "M",
        [
            "merger",
            "acquisition",
            "takeover",
            "buyout",
            "acquires",
            "acquired by",
            "merges with",
            "spin-off",
        ],
    ),
]


def classify_article(headline: str) -> tuple[str, str, str]:
    """Return (category, color, marker_text) based on headline keywords."""
    lower = headline.lower()
    for name, color, marker_txt, keywords in _CATEGORIES:
        if any(kw in lower for kw in keywords):
            return name, color, marker_txt
    return "general", "#9b9ea3", "N"


# Positive / negative keyword lists for sentiment scoring
_POS_WORDS = [
    "gains", "rises", "surges", "beats", "rallies", "climbs", "upgrades",
    "record", "growth", "profit", "exceeds", "stronger", "recovery",
    "jumps", "soars", "breakthrough", "expansion", "outperforms",
]
_NEG_WORDS = [
    "drops", "falls", "misses", "cuts", "declines", "slumps", "downgrades",
    "loss", "layoffs", "recall", "ban", "fears", "concern", "crisis",
    "plunges", "collapses", "warning", "weak", "disappoints", "tumbles",
]


def _score_sentiment(headline: str) -> str:
    """Return 'positive', 'negative', or 'neutral' based on keyword scoring."""
    lower = headline.lower()
    pos = sum(1 for kw in _POS_WORDS if kw in lower)
    neg = sum(1 for kw in _NEG_WORDS if kw in lower)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _article_dict(article: NewsArticle, db: Session) -> dict:
    tickers = [nt.symbol for nt in db.query(NewsTicker).filter_by(article_id=article.id).all()]
    category, _, _ = classify_article(article.headline or "")
    return {
        "id": article.id,
        "source": article.source,
        "headline": article.headline,
        "description": article.description,
        "url": article.url,
        "published_at": article.published_at.isoformat() + "Z" if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat() + "Z" if article.fetched_at else None,
        "tickers": tickers,
        "category": category,
        "sentiment": _score_sentiment(article.headline or ""),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
def list_news(
    q: str | None = Query(default=None, description="Full-text search query"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return recent news articles, newest first. Supports full-text search via ?q=."""
    if q and q.strip():
        # Sanitise the query: strip punctuation that confuses FTS5 syntax
        safe_q = " OR ".join(
            f'"{w}"*'
            for w in q.replace('"', "").replace("'", "").split()
            if w
        )
        try:
            total = db.execute(
                text("SELECT COUNT(*) FROM news_fts WHERE news_fts MATCH :q"),
                {"q": safe_q},
            ).scalar() or 0
            id_rows = db.execute(
                text(
                    "SELECT rowid FROM news_fts WHERE news_fts MATCH :q "
                    "ORDER BY rank LIMIT :lim OFFSET :off"
                ),
                {"q": safe_q, "lim": limit, "off": offset},
            ).fetchall()
            ids = [r[0] for r in id_rows]
            articles = (
                db.query(NewsArticle)
                .filter(NewsArticle.id.in_(ids))
                .order_by(desc(NewsArticle.published_at))
                .all()
            )
        except Exception:
            # FTS table unavailable or bad query — fall back to normal
            total = db.query(NewsArticle).count()
            articles = (
                db.query(NewsArticle)
                .order_by(desc(NewsArticle.published_at))
                .offset(offset)
                .limit(limit)
                .all()
            )
    else:
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
        category, color, marker_text = classify_article(article.headline or "")
        markers.append(
            {
                "time": int(ts.timestamp()),
                "position": "aboveBar",
                "color": color,
                "shape": "arrowDown",
                "text": marker_text,
                "id": str(article.id),
                "category": category,
                # Extra fields used by the UI detail panel
                "headline": article.headline,
                "description": article.description,
                "url": article.url,
                "source": article.source,
            }
        )

    return {"symbol": symbol, "period": period, "markers": markers}


@router.get("/market-markers")
def get_market_markers(
    period: str = Query(default="1d", pattern="^(1d|5d|1mo|3mo)$"),
    db: Session = Depends(get_db),
):
    """Return all news events colour-coded by category for the market overview chart."""
    days = _PERIOD_DAYS.get(period, 1)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    articles = (
        db.query(NewsArticle)
        .filter(NewsArticle.published_at >= cutoff)
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
        category, color, marker_text = classify_article(article.headline or "")
        markers.append(
            {
                "time": int(ts.timestamp()),
                "position": "aboveBar",
                "color": color,
                "shape": "arrowDown",
                "text": marker_text,
                "id": str(article.id),
                "category": category,
                "headline": article.headline,
                "description": article.description,
                "url": article.url,
                "source": article.source,
            }
        )

    return {"period": period, "markers": markers}


# ── Trending tickers ─────────────────────────────────────────────────────────
# MUST be declared before /{article_id} (static path before dynamic)


@router.get("/trending")
def get_trending(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return the most news-mentioned tickers in the last N hours."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)

    # Subquery: latest snapshot per symbol for change_pct
    snap_subq = (
        db.query(
            PriceSnapshot.symbol,
            func.max(PriceSnapshot.timestamp).label("max_ts"),
        )
        .group_by(PriceSnapshot.symbol)
        .subquery()
    )

    mention_rows = (
        db.query(
            NewsTicker.symbol,
            func.count(NewsTicker.symbol).label("mentions"),
        )
        .join(NewsArticle, NewsTicker.article_id == NewsArticle.id)
        .filter(NewsArticle.fetched_at >= cutoff)
        .group_by(NewsTicker.symbol)
        .order_by(desc("mentions"))
        .limit(limit)
        .all()
    )

    result = []
    for sym, count in mention_rows:
        ticker = db.query(Ticker).filter(Ticker.symbol == sym).first()
        snap = (
            db.query(PriceSnapshot)
            .join(
                snap_subq,
                (PriceSnapshot.symbol == snap_subq.c.symbol)
                & (PriceSnapshot.timestamp == snap_subq.c.max_ts),
            )
            .filter(PriceSnapshot.symbol == sym)
            .first()
        )
        result.append(
            {
                "symbol": sym,
                "mentions": count,
                "name": ticker.name if ticker else None,
                "change_pct": snap.change_pct if snap else None,
            }
        )

    return {"hours": hours, "items": result}


@router.get("/{article_id}/impact")
def get_article_impact(article_id: int, db: Session = Depends(get_db)):
    """Return the price-change captures for all tickers mentioned in an article.

    Each ticker has a ``base_price`` (close at collection time) and one entry
    per interval (5 / 15 / 30 / 60 / 120 / 240 / 480 / 1440 min).  The
    ``interval_price`` is ``null`` until that interval has elapsed and the
    background collector has filled it in.
    """
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    impacts = (
        db.query(NewsImpact)
        .filter(NewsImpact.article_id == article_id)
        .order_by(NewsImpact.symbol, NewsImpact.interval_minutes)
        .all()
    )

    by_symbol: dict[str, dict] = {}
    for imp in impacts:
        if imp.symbol not in by_symbol:
            by_symbol[imp.symbol] = {
                "symbol": imp.symbol,
                "base_price": imp.base_price,
                "intervals": [],
            }

        change_pct = None
        if imp.base_price and imp.interval_price and imp.base_price != 0:
            change_pct = round(((imp.interval_price - imp.base_price) / imp.base_price) * 100, 4)

        by_symbol[imp.symbol]["intervals"].append(
            {
                "minutes": imp.interval_minutes,
                "interval_price": imp.interval_price,
                "change_pct": change_pct,
                "captured_at": (imp.captured_at.isoformat() + "Z" if imp.captured_at else None),
            }
        )

    return {
        "article_id": article_id,
        "headline": article.headline,
        "fetched_at": article.fetched_at.isoformat() + "Z" if article.fetched_at else None,
        "tickers": list(by_symbol.values()),
    }


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    """Return a single news article by ID."""
    article = db.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return _article_dict(article, db)
