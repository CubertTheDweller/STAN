"""Centralised configuration — all tuneable values live here."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "stan.db"))
POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))

# Number of tickers fetched per yfinance batch call — lower this if you hit rate limits
STOCK_CHUNK_SIZE: int = 50

# Minimum number of DB rows before we backfill from yfinance on candle requests
CANDLE_BACKFILL_THRESHOLD: int = 10

NEWS_FEEDS: list[dict] = [
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/rss/topstories",
    },
    {
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
    },
    {
        "name": "CNBC Markets",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
    },
    {
        "name": "MarketWatch",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
    },
    {
        "name": "Google Finance News",
        "url": "https://news.google.com/rss/search?q=stock+market+financial+news&hl=en-US&gl=US&ceid=US:en",
    },
]
