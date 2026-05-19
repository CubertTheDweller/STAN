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

# Number of months of data to keep live in the database (older data is archived)
DB_RETENTION_MONTHS: int = int(os.getenv("DB_RETENTION_MONTHS", "3"))

# Maximum number of monthly archive zip files to keep (12 = 1 year of history)
ARCHIVE_RETENTION_COUNT: int = int(os.getenv("ARCHIVE_RETENTION_COUNT", "12"))

# Directory where monthly archive zip files are written
ARCHIVE_DIR: str = os.getenv("ARCHIVE_DIR", str(BASE_DIR / "archives"))

# Minutes after article collection at which to snapshot each mentioned stock's price
IMPACT_INTERVALS: list[int] = [5, 15, 30, 60, 120, 240, 480, 1440]

# ── Curated ticker universe: top 50 by market-cap per exchange ────────────────

TOP_NASDAQ: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AVGO",
    "COST",
    "NFLX",
    "QCOM",
    "AMD",
    "CSCO",
    "INTC",
    "CMCSA",
    "TXN",
    "INTU",
    "AMAT",
    "MU",
    "ADI",
    "KLAC",
    "LRCX",
    "MCHP",
    "CDNS",
    "SNPS",
    "NXPI",
    "WDAY",
    "ROST",
    "PAYX",
    "FAST",
    "BIIB",
    "IDXX",
    "DLTR",
    "PCAR",
    "VRSK",
    "ANSS",
    "TTWO",
    "PANW",
    "CRWD",
    "DDOG",
    "FTNT",
    "SBUX",
    "PYPL",
    "GILD",
    "AMGN",
    "REGN",
    "VRTX",
    "ISRG",
    "ILMN",
    "ZS",
]

TOP_NYSE: list[str] = [
    "BRK-B",
    "LLY",
    "JPM",
    "V",
    "UNH",
    "XOM",
    "MA",
    "PG",
    "JNJ",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "KO",
    "BAC",
    "PEP",
    "WMT",
    "TMO",
    "ABT",
    "ACN",
    "MCD",
    "PM",
    "IBM",
    "GE",
    "HON",
    "RTX",
    "CAT",
    "UPS",
    "BA",
    "GS",
    "MS",
    "BLK",
    "SPGI",
    "AXP",
    "C",
    "WFC",
    "MCO",
    "COF",
    "CRM",
    "ORCL",
    "NOW",
    "UBER",
    "T",
    "VZ",
    "NEE",
    "DUK",
    "SO",
    "MMM",
    "DE",
    "SHW",
]

# Combined universe tracked at runtime (100 tickers total)
TRACKED_TICKERS: list[str] = TOP_NASDAQ + TOP_NYSE

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
