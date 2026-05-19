# STAN — Stock Trading on Active News

STAN is a self-hosted financial intelligence dashboard. It continuously collects
OHLCV stock prices for 100 curated tickers (top 50 by market cap on NASDAQ and
NYSE) and headlines from major financial news feeds, stores everything locally in
a SQLite database, and presents the data through a dark-themed web dashboard
featuring interactive candlestick charts with colour-coded news event markers
pinned directly on the timeline.

---

## Features

- **Continuous data collection** — polls yfinance (stocks) and RSS feeds (news) every 5 minutes via a background scheduler
- **100 curated tickers** — top 50 by market cap on NASDAQ and NYSE; configurable in `stan/config.py`
- **Interactive candlestick chart** — powered by TradingView Lightweight Charts; supports 1D / 5D / 1M / 3M views with volume histogram
- **Colour-coded news markers** — 8 categories (Fed, Earnings, Economic, Tech, Geopolitical, Energy, Merger, General), each with a distinct colour and letter label; click any marker to read the headline and description
- **News impact tracking** — price snapshots captured at 5 / 15 / 30 / 60 / 120 / 240 / 480 / 1440 minutes after each article to measure market reaction
- **Live stocks table** — sortable, filterable table of all tracked tickers with current price, % change (green/red), and volume
- **News feed** — scrollable list of the latest headlines with source badges, relative timestamps, and linked ticker tags
- **Automatic data archival** — data older than `DB_RETENTION_MONTHS` is exported to a zip of CSVs and pruned from the database on the 1st of each month
- **Zero API keys required** — all data comes from Yahoo Finance and public RSS feeds
- **Single-file database** — everything goes into `stan.db` (SQLite); no server setup needed

---

## Quick start

### Prerequisites

- Python 3.11 or newer
- `pip`

### Install

```bash
git clone https://github.com/your-org/stan.git
cd stan
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure (optional)

```bash
cp .env.example .env
# Edit .env to change port, poll interval, etc.
```

### Run

```bash
python run.py
```

Open your browser at **http://127.0.0.1:8000**.

The first data collection starts immediately in the background. The stocks table
and news feed will populate within 1–3 minutes (depending on network speed).
Enter any ticker symbol in the search box to load its candlestick chart.

---

## Configuration

All settings are read from environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `stan.db` | Path to the SQLite database file |
| `POLL_INTERVAL_SECONDS` | `300` | Seconds between each collection cycle |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `HOST` | `127.0.0.1` | Bind address for the web server |
| `PORT` | `8000` | Port for the web server |
| `DB_RETENTION_MONTHS` | `3` | Months of live data to keep in the database |
| `ARCHIVE_RETENTION_COUNT` | `12` | Maximum number of monthly archive zip files to retain |
| `ARCHIVE_DIR` | `archives/` | Directory where monthly archive zips are written |

---

## Project structure

```
STAN/
├── stan/
│   ├── config.py              # All tunable settings + TRACKED_TICKERS (100 curated)
│   ├── database/
│   │   ├── db.py              # SQLAlchemy engine + session factory (WAL mode)
│   │   └── models.py          # ORM models: Ticker, PriceSnapshot, NewsArticle, NewsTicker, NewsImpact
│   ├── collectors/
│   │   ├── stocks.py          # yfinance OHLCV collector (chunked, 50 per batch)
│   │   ├── news.py            # feedparser RSS collector with ticker extraction
│   │   ├── impact.py          # fills price-change snapshots after each article
│   │   └── archive.py         # monthly data export to zip + DB pruning
│   ├── scheduler.py           # APScheduler: 3 interval jobs + 1 monthly cron
│   └── api/
│       ├── main.py            # FastAPI app + lifespan (DB init, scheduler start)
│       └── routes/
│           ├── stocks.py      # GET /api/stocks, GET /api/stocks/{symbol}/candles
│           └── news.py        # news endpoints + category classifier
├── frontend/
│   ├── templates/index.html   # Jinja2 dashboard template
│   └── static/
│       ├── css/style.css      # Dark financial theme
│       └── js/app.js          # Chart, autocomplete, table, feed, auto-refresh
├── tests/
│   ├── test_collectors.py
│   ├── test_api.py
│   └── test_archive.py
├── run.py                     # Entry point
├── requirements.txt
└── requirements-dev.txt
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stocks` | Latest price snapshot per ticker. Query params: `sector`, `limit`, `offset` |
| `GET` | `/api/stocks/{symbol}/candles` | OHLCV candle series. Query params: `period` (`1d`·`5d`·`1mo`·`3mo`) |
| `GET` | `/api/news` | Recent news articles. Query params: `limit`, `offset` |
| `GET` | `/api/news/markers` | Ticker-scoped news markers for the chart. Query params: `symbol`, `period` |
| `GET` | `/api/news/market-markers` | All news events colour-coded by category. Query param: `period` |
| `GET` | `/api/news/{id}/impact` | Price-change captures at 5–1440 min intervals after an article |
| `GET` | `/api/news/{id}` | Single article detail |

Interactive API docs are available at **http://127.0.0.1:8000/docs** while the server is running.

---

## Development

```bash
pip install -r requirements-dev.txt

# Run tests
pytest

# Lint
ruff check .
ruff format .
```

---

## Limitations & notes

- **yfinance rate limits** — if you see download errors, try lowering `STOCK_CHUNK_SIZE` in `stan/config.py` (default: 50 tickers per batch).
- **Data is not financial advice** — STAN is a personal research tool. Do not make investment decisions based solely on its output.
- **Market hours** — stock price updates are only meaningful when US markets are open. Outside of trading hours the most recent close prices are shown.
- **RSS feed availability** — feed URLs are configured in `stan/config.py` and can be updated if a publisher changes their feed address.
- **News impact data** — impact intervals (5–1440 min) are filled gradually by the background collector; rows appear as `null` until each interval elapses.
- **Archive directory** — the `archives/` directory is created automatically on first run; set `ARCHIVE_DIR` to redirect it elsewhere.

---

## License

MIT — see [LICENSE](LICENSE).

Chart rendering powered by [TradingView Lightweight Charts](https://www.tradingview.com) (Apache 2.0).
