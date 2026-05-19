"""Tests for the monthly data archival collector."""

import os
import time
import zipfile
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from stan.collectors.archive import archive_old_data
from stan.database.models import Base, NewsArticle, NewsImpact, NewsTicker, PriceSnapshot, Ticker

# ── In-memory test database ───────────────────────────────────────────────────

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
ArchiveTestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def reset_db():
    """Recreate all tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _seed_february_data() -> int:
    """Insert one Ticker, PriceSnapshot, NewsArticle, NewsTicker, and NewsImpact row
    all dated within February 2026 — the target month when 'today' is mocked to May 2026."""
    db = ArchiveTestSession()
    try:
        db.add(Ticker(symbol="AAPL", name="Apple Inc"))
        db.flush()

        db.add(
            PriceSnapshot(
                symbol="AAPL",
                timestamp=datetime(2026, 2, 15, 12, 0),
                open=180.0,
                high=185.0,
                low=179.0,
                close=183.0,
                volume=5_000_000,
                change_pct=1.2,
            )
        )

        article = NewsArticle(
            source="Test Feed",
            headline="AAPL hits record high",
            url="https://example.com/feb-article",
            fetched_at=datetime(2026, 2, 15, 10, 0),
        )
        db.add(article)
        db.flush()

        db.add(NewsTicker(article_id=article.id, symbol="AAPL"))
        db.add(
            NewsImpact(
                article_id=article.id,
                symbol="AAPL",
                interval_minutes=5,
                base_price=180.0,
                interval_price=183.0,
            )
        )
        db.commit()
        return article.id
    finally:
        db.close()


def _patch_archive(tmp_path, retention_count=12):
    """Return a context-manager stack that redirects the archive module to the test DB and tmp dir."""
    return (
        patch("stan.collectors.archive.ARCHIVE_DIR", str(tmp_path)),
        patch("stan.collectors.archive.SessionLocal", ArchiveTestSession),
        patch("stan.collectors.archive.DB_RETENTION_MONTHS", 3),
        patch("stan.collectors.archive.ARCHIVE_RETENTION_COUNT", retention_count),
    )


def _mock_datetime():
    """Patch the datetime class in the archive module so .now() returns 2026-05-01."""
    p = patch("stan.collectors.archive.datetime")
    mock_dt = p.start()
    mock_dt.side_effect = datetime  # make datetime(...) constructor calls work
    mock_dt.now.return_value = datetime(2026, 5, 1)
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_archive_creates_zip(tmp_path):
    """Archive job writes a correctly named zip with all 6 CSVs and deletes DB rows."""
    _seed_february_data()

    patches = _patch_archive(tmp_path)
    dt_patch = _mock_datetime()
    try:
        for p in patches:
            p.start()

        archive_old_data()
    finally:
        dt_patch.stop()
        for p in reversed(patches):
            p.stop()

    expected_zip = tmp_path / "february_2026.zip"
    assert expected_zip.exists(), "Zip file was not created"

    with zipfile.ZipFile(expected_zip) as zf:
        assert set(zf.namelist()) == {
            "news_articles.csv",
            "news_tickers.csv",
            "news_impact.csv",
            "price_nyse.csv",
            "price_nasdaq.csv",
            "price_sp500.csv",
        }

    db = ArchiveTestSession()
    try:
        feb_news = (
            db.query(NewsArticle)
            .filter(
                NewsArticle.fetched_at >= datetime(2026, 2, 1),
                NewsArticle.fetched_at < datetime(2026, 3, 1),
            )
            .count()
        )
        assert feb_news == 0, "February news articles were not deleted"

        feb_snaps = (
            db.query(PriceSnapshot)
            .filter(
                PriceSnapshot.timestamp >= datetime(2026, 2, 1),
                PriceSnapshot.timestamp < datetime(2026, 3, 1),
            )
            .count()
        )
        assert feb_snaps == 0, "February price snapshots were not deleted"
    finally:
        db.close()


def test_archive_skips_if_exists(tmp_path):
    """If the zip for the target month already exists, no DB rows are deleted."""
    _seed_february_data()

    # Pre-create the zip so the job should bail out early
    with zipfile.ZipFile(tmp_path / "february_2026.zip", "w"):
        pass

    patches = _patch_archive(tmp_path)
    dt_patch = _mock_datetime()
    try:
        for p in patches:
            p.start()
        archive_old_data()
    finally:
        dt_patch.stop()
        for p in reversed(patches):
            p.stop()

    db = ArchiveTestSession()
    try:
        assert db.query(NewsArticle).count() == 1, "Article should not have been deleted"
        assert db.query(PriceSnapshot).count() == 1, "Snapshot should not have been deleted"
    finally:
        db.close()


def test_archive_enforces_retention(tmp_path):
    """After archiving, the oldest zips are removed so only ARCHIVE_RETENTION_COUNT remain."""
    _seed_february_data()

    # Create 12 existing dummy zips with staggered mtimes (oldest first)
    base_time = time.time() - 12 * 3600
    for i in range(12):
        dummy = tmp_path / f"dummy_{i:02d}.zip"
        with zipfile.ZipFile(dummy, "w"):
            pass
        os.utime(dummy, (base_time + i * 60, base_time + i * 60))

    # archive_old_data creates 1 more (february_2026.zip) → 13 total → enforce to 12
    patches = _patch_archive(tmp_path, retention_count=12)
    dt_patch = _mock_datetime()
    try:
        for p in patches:
            p.start()
        archive_old_data()
    finally:
        dt_patch.stop()
        for p in reversed(patches):
            p.stop()

    remaining = list(tmp_path.glob("*.zip"))
    assert len(remaining) == 12, f"Expected 12 zips, got {len(remaining)}"
    # The oldest dummy (dummy_00.zip) should have been removed
    assert not (tmp_path / "dummy_00.zip").exists(), "Oldest zip was not removed"
    assert (tmp_path / "february_2026.zip").exists(), "New archive zip should be kept"
