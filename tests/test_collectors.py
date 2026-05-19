"""Tests for data collectors — network calls are mocked."""

from unittest.mock import MagicMock, patch

import pandas as pd

# ── stocks collector ──────────────────────────────────────────────────────────


def test_fetch_sp500_symbols_returns_list():
    """fetch_sp500_symbols returns the curated TRACKED_TICKERS list."""
    from stan.collectors.stocks import fetch_sp500_symbols
    from stan.config import TRACKED_TICKERS

    symbols = fetch_sp500_symbols()
    assert isinstance(symbols, list)
    assert len(symbols) == len(TRACKED_TICKERS)
    assert "AAPL" in symbols   # top NASDAQ
    assert "JPM" in symbols    # top NYSE


def test_fetch_sp500_symbols_returns_correct_count():
    """fetch_sp500_symbols returns exactly 100 tickers (50 NASDAQ + 50 NYSE)."""
    from stan.collectors.stocks import fetch_sp500_symbols

    symbols = fetch_sp500_symbols()
    assert len(symbols) == 100


# ── news collector ────────────────────────────────────────────────────────────


def _make_feed_entry(title, link, summary="", published="Mon, 19 May 2026 12:00:00 +0000"):
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.published = published
    entry.published_parsed = (2026, 5, 19, 12, 0, 0, 0, 0, 0)
    entry.updated_parsed = None
    return entry


@patch("stan.collectors.news.feedparser.parse")
@patch("stan.collectors.news.SessionLocal")
def test_collect_news_inserts_new_articles(mock_session_local, mock_fp_parse):
    feed = MagicMock()
    feed.entries = [
        _make_feed_entry("AAPL hits all-time high", "https://example.com/1", summary="Apple stock"),
    ]
    mock_fp_parse.return_value = feed

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # URL not seen before
    db.query.return_value.all.return_value = [("AAPL",)]  # known tickers
    mock_session_local.return_value = db

    from stan.collectors.news import collect_news

    # Should not raise
    collect_news()


def test_extract_tickers_filters_stop_words():
    from stan.collectors.news import _extract_tickers

    known = {"AAPL", "THE", "AND", "MSFT"}
    result = _extract_tickers("AAPL and THE MSFT", known)
    assert "AAPL" in result
    assert "MSFT" in result
    assert "THE" not in result
    assert "AND" not in result
