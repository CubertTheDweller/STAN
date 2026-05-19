"""News-impact collector — fills in price captures at fixed intervals after articles."""

import logging
from datetime import UTC, datetime, timedelta

from stan.database.db import SessionLocal
from stan.database.models import NewsArticle, NewsImpact, PriceSnapshot

logger = logging.getLogger(__name__)


def fill_news_impact() -> None:
    """Scan for pending NewsImpact rows whose interval has elapsed and fill them in.

    Called every poll cycle (5 min).  For each unfilled row, if
    ``article.fetched_at + interval_minutes`` is in the past, we look up
    the closest PriceSnapshot at or after the due time and record it.
    """
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        # Load all unfilled rows together with their parent article's fetched_at
        pending = (
            db.query(NewsImpact, NewsArticle.fetched_at)
            .join(NewsArticle, NewsImpact.article_id == NewsArticle.id)
            .filter(NewsImpact.interval_price.is_(None))
            .all()
        )

        if not pending:
            return

        filled = 0
        for impact, fetched_at in pending:
            if fetched_at is None:
                continue
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)

            due_at = fetched_at + timedelta(minutes=impact.interval_minutes)
            if due_at > now:
                continue  # interval hasn't elapsed yet

            # Prefer the first snapshot at or after the due time (closest real
            # price to the target moment); fall back to the most recent overall.
            snapshot = (
                db.query(PriceSnapshot)
                .filter(
                    PriceSnapshot.symbol == impact.symbol,
                    PriceSnapshot.timestamp >= due_at,
                )
                .order_by(PriceSnapshot.timestamp)
                .first()
            )
            if snapshot is None:
                snapshot = (
                    db.query(PriceSnapshot)
                    .filter(PriceSnapshot.symbol == impact.symbol)
                    .order_by(PriceSnapshot.timestamp.desc())
                    .first()
                )

            if snapshot and snapshot.close is not None:
                impact.interval_price = snapshot.close
                impact.captured_at = (
                    snapshot.timestamp.replace(tzinfo=UTC)
                    if snapshot.timestamp.tzinfo is None
                    else snapshot.timestamp
                )
                filled += 1

        if filled:
            db.commit()
            logger.info("Filled %d news-impact price captures", filled)

    except Exception as exc:
        logger.error("fill_news_impact error: %s", exc)
        db.rollback()
    finally:
        db.close()
