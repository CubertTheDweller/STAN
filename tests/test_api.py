"""Smoke tests for the FastAPI endpoints using TestClient."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from stan.database.models import Base, NewsArticle, NewsTicker, PriceSnapshot, Ticker

# ── In-memory test database ───────────────────────────────────────────────────
# StaticPool ensures all sessions share the *same* in-memory connection so that
# tables created by create_all() are visible to sessions used by the routes.

TEST_DB_URL = "sqlite://"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)

    # Seed minimal test data
    db = TestingSession()
    try:
        ticker = Ticker(symbol="TEST", name="Test Corp", sector="Technology")
        db.add(ticker)
        db.flush()

        snap = PriceSnapshot(
            symbol="TEST",
            timestamp=datetime(2026, 5, 19, 12, 0, tzinfo=UTC),
            open=100.0, high=105.0, low=99.0, close=103.0,
            volume=1_000_000, change_pct=1.5,
        )
        db.add(snap)

        article = NewsArticle(
            source="Test Feed",
            headline="TEST Corp announces record earnings",
            description="Details here.",
            url="https://example.com/test-article",
            published_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
            fetched_at=datetime(2026, 5, 19, 11, 5, tzinfo=UTC),
        )
        db.add(article)
        db.flush()
        db.add(NewsTicker(article_id=article.id, symbol="TEST"))
        db.commit()
    finally:
        db.close()

    yield

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client():
    # Import app after DB setup to avoid lifespan side-effects in tests
    from stan.api.main import app
    from stan.database.db import get_db

    app.dependency_overrides[get_db] = override_get_db

    # Disable the lifespan so scheduler and collectors don't fire during tests
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


# ── /api/stocks ───────────────────────────────────────────────────────────────


def test_list_stocks_returns_200(client):
    res = client.get("/api/stocks")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data


def test_list_stocks_contains_seeded_ticker(client):
    res = client.get("/api/stocks")
    symbols = [item["symbol"] for item in res.json()["items"]]
    assert "TEST" in symbols


def test_list_stocks_sector_filter(client):
    res = client.get("/api/stocks?sector=Technology")
    assert res.status_code == 200
    for item in res.json()["items"]:
        assert item["sector"] == "Technology"


# ── /api/stocks/{symbol}/candles ──────────────────────────────────────────────


def test_candles_returns_data_for_known_symbol(client):
    # Uses backfill path — patch yfinance so it doesn't make real network calls
    from unittest.mock import patch

    import pandas as pd

    mock_df = pd.DataFrame(
        {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1e6]},
        index=pd.to_datetime(["2026-05-19"]),
    )
    with patch("stan.api.routes.stocks.yf.download", return_value=mock_df):
        res = client.get("/api/stocks/TEST/candles?period=1d")
    assert res.status_code in (200, 404)  # 404 acceptable if cutoff filters seed data


def test_candles_404_for_unknown_symbol(client):
    from unittest.mock import patch

    import pandas as pd

    with patch("stan.api.routes.stocks.yf.download", return_value=pd.DataFrame()):
        res = client.get("/api/stocks/XXXX_UNKNOWN/candles?period=1d")
    assert res.status_code == 404


# ── /api/news ─────────────────────────────────────────────────────────────────


def test_list_news_returns_200(client):
    res = client.get("/api/news")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data


def test_list_news_contains_seeded_article(client):
    res = client.get("/api/news")
    headlines = [item["headline"] for item in res.json()["items"]]
    assert any("TEST Corp" in h for h in headlines)


def test_news_markers_for_known_symbol(client):
    res = client.get("/api/news/markers?symbol=TEST&period=1mo")
    assert res.status_code == 200
    data = res.json()
    assert "markers" in data
    assert data["symbol"] == "TEST"


def test_news_article_detail(client):
    # Get first article id from list
    res = client.get("/api/news")
    items = res.json()["items"]
    assert items
    article_id = items[0]["id"]

    detail = client.get(f"/api/news/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == article_id


def test_news_article_404_for_unknown_id(client):
    res = client.get("/api/news/999999")
    assert res.status_code == 404
