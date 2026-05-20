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
- FastAPI REST API (13 endpoints):
  - `GET /api/stocks` — paginated latest snapshots with sector filter
  - `GET /api/stocks/sectors` — avg % change, ticker count, and top movers per sector
  - `GET /api/stocks/{symbol}/candles` — OHLCV candle series
  - `GET /api/stocks/{symbol}/indicators` — SMA calculation (20 / 50 / 200 or custom periods)
  - `GET /api/news` — paginated news feed
  - `GET /api/news/markers` — ticker-scoped chart markers
  - `GET /api/news/market-markers` — all events colour-coded by category
  - `GET /api/news/trending` — most news-mentioned tickers over a configurable time window
  - `GET /api/news/{id}/impact` — price-change captures at 5–1440 min intervals
  - `GET /api/news/{id}` — single article detail
  - `GET /api/status` — last collection timestamps, error counts, DB row counts
  - `GET /api/metrics` — detailed operational metrics (impact fill rate, DB size)
  - `WS /ws` — WebSocket live push after each collection cycle
- TradingView Lightweight Charts candlestick chart with 1D / 5D / 1M / 3M period views
- Volume histogram overlay on the candlestick chart
- SMA overlays: toggleable 20 / 50 / 200-period moving averages
- Comparison mode: overlay a second ticker on the same chart
- Colour-coded news markers on the chart timeline: 8 categories (Fed, Earnings, Economic, Tech, Geopolitical, Energy, Merger, General), each with a distinct colour and letter label; click any marker to open the detail panel
- Market-overview markers endpoint returning all events across all tickers
- News impact tracking: price snapshots captured at 5 / 15 / 30 / 60 / 120 / 240 / 480 / 1440 minutes after each article; impact sparklines shown in detail panel (`fill_news_impact` collector)
- Sector heatmap powered by `/api/stocks/sectors`
- Trending tickers sidebar powered by `/api/news/trending`
- Favorites: star any ticker to pin it; persisted in `localStorage`
- Price alerts: set a % change threshold per ticker; browser notification on trigger
- CSV export: download the current candle series as a `.csv` file
- Sentiment badges on the stocks table
- Category filters for news markers and the news feed
- Light / dark theme toggle; preference persisted in `localStorage`
- WebSocket live push: server broadcasts a refresh event to all browser tabs after each collection cycle; 60-second polling fallback when WebSocket is unavailable
- Thread-safe collection state module (`stan/collectors/state.py`) tracking run counts and last timestamps
- WebSocket connection manager (`stan/api/ws.py`) with thread-safe `broadcast_sync()`
- Automatic monthly data archival: data older than `DB_RETENTION_MONTHS` exported to a zip of CSVs and pruned from the database on the 1st of each month (`archive_old_data` collector)
- Dark-themed web dashboard with live stocks table and news feed
- Ticker autocomplete search
- APScheduler: three interval jobs (stocks, news, impact) every `POLL_INTERVAL_SECONDS` + one monthly cron job (archive)
- Lazy backfill of candle history from yfinance when a new ticker is first requested
- `.env`-based configuration for all tuneable settings (`DB_PATH`, `POLL_INTERVAL_SECONDS`, `LOG_LEVEL`, `HOST`, `PORT`, `DB_RETENTION_MONTHS`, `ARCHIVE_RETENTION_COUNT`, `ARCHIVE_DIR`)
- GitHub Actions CI workflow (lint + test)
- Full repository documentation: README, CONTRIBUTING, CHANGELOG, CODE_OF_CONDUCT, SECURITY
