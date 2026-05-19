"""Monthly data archival — exports the oldest retained month to a zip of CSVs then removes it from the DB."""

import calendar
import csv
import io
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from stan.config import (
    ARCHIVE_DIR,
    ARCHIVE_RETENTION_COUNT,
    DB_RETENTION_MONTHS,
    TOP_NASDAQ,
    TOP_NYSE,
)
from stan.database.db import SessionLocal
from stan.database.models import NewsArticle, NewsImpact, NewsTicker, PriceSnapshot

logger = logging.getLogger(__name__)

# Index symbols collected on-demand via backfill; may or may not be present in DB.
_INDEX_SYMBOLS: list[str] = ["^GSPC", "^NYA", "^IXIC"]


def archive_old_data() -> None:
    """Archive one calendar month of data and remove it from the database.

    The target month is DB_RETENTION_MONTHS months prior to the current month
    (e.g. running in May 2026 with DB_RETENTION_MONTHS=3 archives February 2026).
    Writes a zip file to ARCHIVE_DIR named ``<month>_<year>.zip`` and enforces
    the ARCHIVE_RETENTION_COUNT cap by deleting the oldest zip when exceeded.
    """
    now = datetime.now(UTC).replace(tzinfo=None)

    # Calculate the calendar month to archive
    target_month = now.month - DB_RETENTION_MONTHS
    target_year = now.year
    while target_month <= 0:
        target_month += 12
        target_year -= 1

    start = datetime(target_year, target_month, 1)
    next_month = target_month + 1 if target_month < 12 else 1
    next_year = target_year if target_month < 12 else target_year + 1
    end = datetime(next_year, next_month, 1)

    month_label = f"{calendar.month_name[target_month].lower()}_{target_year}"
    archive_path = Path(ARCHIVE_DIR) / f"{month_label}.zip"

    if archive_path.exists():
        logger.info("Archive for %s already exists — skipping", month_label)
        return

    db = SessionLocal()
    try:
        exports = _export_month(db, start, end)

        total_rows = sum(len(rows) for rows in exports.values())
        if total_rows == 0:
            logger.info("No data found for %s — nothing to archive", month_label)
            return

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        _write_zip(archive_path, exports)

        row_summary = ", ".join(f"{name}: {len(rows)}" for name, rows in exports.items())
        logger.info("Archived %s → %s (%s)", month_label, archive_path, row_summary)

        _delete_month(db, start, end)
        logger.info("Removed %s data from database", month_label)

    finally:
        db.close()

    _enforce_retention(archive_path.parent)


def _export_month(db, start: datetime, end: datetime) -> dict[str, list[dict]]:
    """Query all data for the given month window and return as named CSV row lists."""

    # ── News articles ─────────────────────────────────────────────────────────
    articles = (
        db.query(NewsArticle)
        .filter(NewsArticle.fetched_at >= start, NewsArticle.fetched_at < end)
        .all()
    )
    article_ids = [a.id for a in articles]

    news_rows = [
        {
            "id": a.id,
            "source": a.source,
            "headline": a.headline,
            "description": a.description,
            "url": a.url,
            "published_at": a.published_at.isoformat() if a.published_at else "",
            "fetched_at": a.fetched_at.isoformat() if a.fetched_at else "",
        }
        for a in articles
    ]

    # ── News ticker associations ──────────────────────────────────────────────
    if article_ids:
        tickers = db.query(NewsTicker).filter(NewsTicker.article_id.in_(article_ids)).all()
        ticker_rows = [{"article_id": t.article_id, "symbol": t.symbol} for t in tickers]

        impact = db.query(NewsImpact).filter(NewsImpact.article_id.in_(article_ids)).all()
        impact_rows = [
            {
                "article_id": i.article_id,
                "symbol": i.symbol,
                "interval_minutes": i.interval_minutes,
                "base_price": i.base_price,
                "interval_price": i.interval_price,
                "captured_at": i.captured_at.isoformat() if i.captured_at else "",
            }
            for i in impact
        ]
    else:
        ticker_rows = []
        impact_rows = []

    # ── Price snapshots ───────────────────────────────────────────────────────
    def _price_rows(symbols: list[str]) -> list[dict]:
        snaps = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.symbol.in_(symbols),
                PriceSnapshot.timestamp >= start,
                PriceSnapshot.timestamp < end,
            )
            .order_by(PriceSnapshot.symbol, PriceSnapshot.timestamp)
            .all()
        )
        return [
            {
                "symbol": s.symbol,
                "timestamp": s.timestamp.isoformat(),
                "open": s.open,
                "high": s.high,
                "low": s.low,
                "close": s.close,
                "volume": s.volume,
                "change_pct": s.change_pct,
            }
            for s in snaps
        ]

    return {
        "news_articles.csv": news_rows,
        "news_tickers.csv": ticker_rows,
        "news_impact.csv": impact_rows,
        "price_nyse.csv": _price_rows(TOP_NYSE),
        "price_nasdaq.csv": _price_rows(TOP_NASDAQ),
        "price_sp500.csv": _price_rows(_INDEX_SYMBOLS),
    }


def _write_zip(archive_path: Path, exports: dict[str, list[dict]]) -> None:
    """Write a zip file containing one CSV per export entry."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, rows in exports.items():
            buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            # Write the file even when empty so the zip structure is always consistent
            zf.writestr(filename, buf.getvalue())


def _delete_month(db, start: datetime, end: datetime) -> None:
    """Remove all data for the given month window from the database.

    Deleting NewsArticle rows cascades to NewsTicker and NewsImpact via the
    database-level ON DELETE CASCADE foreign keys.
    """
    deleted_news = (
        db.query(NewsArticle)
        .filter(NewsArticle.fetched_at >= start, NewsArticle.fetched_at < end)
        .delete(synchronize_session=False)
    )

    all_symbols = list(TOP_NYSE) + list(TOP_NASDAQ) + _INDEX_SYMBOLS
    deleted_prices = (
        db.query(PriceSnapshot)
        .filter(
            PriceSnapshot.symbol.in_(all_symbols),
            PriceSnapshot.timestamp >= start,
            PriceSnapshot.timestamp < end,
        )
        .delete(synchronize_session=False)
    )

    db.commit()
    logger.debug("Deleted %d news articles and %d price snapshots", deleted_news, deleted_prices)


def _enforce_retention(archive_dir: Path) -> None:
    """Delete the oldest zip files if the archive count exceeds ARCHIVE_RETENTION_COUNT."""
    zips = sorted(archive_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    excess = len(zips) - ARCHIVE_RETENTION_COUNT
    for old_zip in zips[:excess]:
        old_zip.unlink()
        logger.info("Removed old archive: %s", old_zip.name)
