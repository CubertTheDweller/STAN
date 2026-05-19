"""News collector — parses RSS feeds and links articles to known ticker symbols."""

import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
from sqlalchemy.exc import IntegrityError

from stan.config import NEWS_FEEDS
from stan.database.db import SessionLocal
from stan.database.models import NewsArticle, NewsTicker, Ticker

logger = logging.getLogger(__name__)

# Matches uppercase words of 1-5 characters (potential ticker symbols)
_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")

# Common English words that look like tickers — excluded from matching
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
        "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US",
        "WE", "THE", "AND", "FOR", "ARE", "NOT", "BUT", "ITS", "NEW", "NOW",
        "ONE", "OUT", "SAY", "TWO", "WAY", "WHO", "ALL", "CAN", "HAD", "HAS",
        "HER", "HIM", "HIS", "HOW", "OUR", "TOO", "WAS", "DID", "LET", "MAY",
        "OLD", "OWN", "PUT", "SET", "USE", "YET", "GET", "GOT", "HAS", "HIV",
        "CEO", "CFO", "COO", "IPO", "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ",
        "ETF", "S&P", "DOW", "US", "EU", "UK", "UN", "AI", "EV",
    }
)


def _known_symbols(db) -> set[str]:
    return {row[0] for row in db.query(Ticker.symbol).all()}


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            return datetime(*struct[:6], tzinfo=UTC)
    raw = getattr(entry, "published", None)
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(UTC).replace(tzinfo=UTC)
        except Exception:
            pass
    return None


def _extract_tickers(text: str, known: set[str]) -> list[str]:
    candidates = _TICKER_PATTERN.findall(text.upper())
    return list({c for c in candidates if c in known and c not in _STOP_WORDS})


def collect_news() -> None:
    """Parse all configured RSS feeds and persist new articles with ticker links."""
    db = SessionLocal()
    try:
        known = _known_symbols(db)
        inserted = 0

        for feed_cfg in NEWS_FEEDS:
            source_name: str = feed_cfg["name"]
            try:
                feed = feedparser.parse(feed_cfg["url"])
            except Exception as exc:
                logger.error("Failed to parse feed '%s': %s", source_name, exc)
                continue

            for entry in feed.entries:
                url: str | None = getattr(entry, "link", None)
                if not url:
                    continue

                # Fast dedup by URL before touching the ORM
                if db.query(NewsArticle.id).filter(NewsArticle.url == url).first():
                    continue

                headline: str = getattr(entry, "title", "").strip()
                if not headline:
                    continue

                description: str | None = getattr(entry, "summary", "").strip() or None
                published_at = _parse_date(entry)

                article = NewsArticle(
                    source=source_name,
                    headline=headline,
                    description=description,
                    url=url,
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                )
                db.add(article)
                try:
                    db.flush()  # get article.id without committing
                except IntegrityError:
                    db.rollback()
                    continue

                # Link to any mentioned tickers
                text = f"{headline} {description or ''}"
                for sym in _extract_tickers(text, known):
                    db.add(NewsTicker(article_id=article.id, symbol=sym))

                try:
                    db.commit()
                    inserted += 1
                except IntegrityError:
                    db.rollback()

        logger.info("Inserted %d new news articles", inserted)
    finally:
        db.close()
