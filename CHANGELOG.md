# Changelog

All notable changes to STAN will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Initial project structure and full implementation
- Curated ticker universe: top 50 by market cap on NASDAQ (`TOP_NASDAQ`) and top 50 on NYSE (`TOP_NYSE`) — 100 tickers total; configurable in `stan/config.py`
- Continuous stock price collection from Yahoo Finance (yfinance) in batches of 50 (`STOCK_CHUNK_SIZE`)
- Continuous news collection from Yahoo Finance, Reuters, CNBC, MarketWatch, and Google News RSS feeds
- SQLite database with five tables: `tickers`, `price_snapshots`, `news_articles`, `news_tickers`, `news_impact`
- FastAPI REST API: `/api/stocks`, `/api/stocks/{symbol}/candles`, `/api/news`, `/api/news/markers`, `/api/news/market-markers`, `/api/news/{id}/impact`, `/api/news/{id}`
- TradingView Lightweight Charts candlestick chart with 1D / 5D / 1M / 3M period views
- Volume histogram overlay on the candlestick chart
- Colour-coded news markers on the chart timeline: 8 categories (Fed, Earnings, Economic, Tech, Geopolitical, Energy, Merger, General), each with a distinct colour and letter label; click any marker to open the detail panel
- Market-overview markers endpoint (`/api/news/market-markers`) returning all events across all tickers
- News impact tracking: price snapshots captured at 5 / 15 / 30 / 60 / 120 / 240 / 480 / 1440 minutes after each article to measure market reaction (`fill_news_impact` collector)
- Automatic monthly data archival: data older than `DB_RETENTION_MONTHS` exported to a zip of CSVs and pruned from the database on the 1st of each month (`archive_old_data` collector)
- Dark-themed web dashboard with live stocks table and news feed
- Ticker autocomplete search
- 60-second client-side auto-refresh
- APScheduler: three interval jobs (stocks, news, impact) every `POLL_INTERVAL_SECONDS` + one monthly cron job (archive)
- Lazy backfill of candle history from yfinance when a new ticker is first requested
- `.env`-based configuration for all tuneable settings (`DB_PATH`, `POLL_INTERVAL_SECONDS`, `LOG_LEVEL`, `HOST`, `PORT`, `DB_RETENTION_MONTHS`, `ARCHIVE_RETENTION_COUNT`, `ARCHIVE_DIR`)
- GitHub Actions CI workflow (lint + test)
- Full repository documentation: README, CONTRIBUTING, CHANGELOG, CODE_OF_CONDUCT, SECURITY
