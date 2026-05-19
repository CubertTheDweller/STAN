# Changelog

All notable changes to STAN will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Initial project structure and full implementation
- Continuous stock price collection from Yahoo Finance (yfinance) for S&P 500 tickers
- Continuous news collection from Yahoo Finance, Reuters, CNBC, MarketWatch, and Google News RSS feeds
- SQLite database with four tables: `tickers`, `price_snapshots`, `news_articles`, `news_tickers`
- FastAPI REST API: `/api/stocks`, `/api/stocks/{symbol}/candles`, `/api/news`, `/api/news/markers`, `/api/news/{id}`
- TradingView Lightweight Charts candlestick chart with 1D / 5D / 1M / 3M period views
- Volume histogram overlay on the candlestick chart
- News event markers (orange circles) pinned on the chart timeline with click-to-detail panel
- Dark-themed web dashboard with live stocks table and news feed
- Ticker autocomplete search
- 60-second client-side auto-refresh
- APScheduler background scheduler with configurable poll interval (default: 5 minutes)
- Lazy backfill of candle history from yfinance when a new ticker is first requested
- `.env`-based configuration for all tuneable settings
- GitHub Actions CI workflow (lint + test)
- Full repository documentation: README, CONTRIBUTING, CHANGELOG, CODE_OF_CONDUCT, SECURITY
