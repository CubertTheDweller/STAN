# STAN — Agent Instructions

Self-hosted financial intelligence dashboard. Continuously collects OHLCV prices + RSS news for 100 curated tickers (50 NASDAQ + 50 NYSE), stores everything in SQLite, and serves an interactive TradingView chart with colour-coded news markers. See [README.md](README.md) for full feature description and setup.

## Commands

```bash
# Run server (initialises DB automatically)
.venv/bin/python run.py                    # http://127.0.0.1:8000

# Tests (in-memory SQLite, all network mocked)
pytest tests/ -v                           # 17 tests expected

# Lint / format
.venv/bin/ruff check .                     # rules: E, F, I, UP (line-length=100)
.venv/bin/ruff format .

# Wipe DB and restart (safe for dev — DB auto-recreates on startup)
kill $(lsof -ti:8000) 2>/dev/null; rm -f stan.db stan.db-wal stan.db-shm && .venv/bin/python run.py &
```

## Architecture

```
stan/config.py          ← all tunable settings, TRACKED_TICKERS (100 curated)
stan/database/          ← SQLAlchemy models + session factory (WAL mode SQLite)
stan/collectors/        ← stocks.py · news.py · impact.py · archive.py · state.py
stan/scheduler.py       ← APScheduler 4 jobs (3 interval + 1 monthly cron)
stan/api/main.py        ← FastAPI lifespan: init_db → start scheduler → immediate collect
stan/api/ws.py          ← WebSocket connection manager (broadcast_sync)
stan/api/routes/        ← stocks.py · news.py · system.py  (REST + WS endpoints)
frontend/               ← templates/index.html · static/js/app.js · static/css/style.css
tests/                  ← test_api.py · test_collectors.py · test_archive.py
```

## Non-obvious Conventions

### WebSocket live push
- Collectors run in plain threads; call `broadcast_sync(msg)` from `stan/api/ws.py` to push JSON to all browser tabs without blocking the collector.
- `ws_manager.set_loop(loop)` must be called from the FastAPI lifespan before any collector thread fires.
- The frontend connects on load and falls back to 60-second `setInterval` polling if the WebSocket closes or is unavailable.

### FastAPI / Starlette
- `TemplateResponse` takes `(request, template_name, context)` — **request is first arg** (Starlette 1.x breaking change).
- Router route order matters: static paths (`/markers`, `/market-markers`) **must be declared before** `/{article_id}` or FastAPI will match the dynamic route first.

### yfinance
- Multi-ticker downloads return a MultiIndex DataFrame. Flatten per-symbol via `raw.xs(symbol, level=1, axis=1)` with a `KeyError` fallback (index symbols like `^NYA` may use a different key).
- Always wrap float conversions with `_safe_float()` (handles `NaN → None`).
- Batch downloads in chunks of 50 (`STOCK_CHUNK_SIZE`) to avoid rate limits.
- Index symbols (`^NYA`, `^IXIC`, `^GSPC`) are fetched the same way — handle KeyError fallback in backfill logic.

### Database / SQLAlchemy
- All `datetime` values are stored **naive UTC** (no `tzinfo`). Compare with naive cutoff: `datetime.now(UTC).replace(tzinfo=None)` or strip tzinfo before querying.
- WAL mode + `check_same_thread=False` are set in `db.py` — don't remove them.
- Use `db.merge()` for upsert-style inserts (news impact seeding); use `sqlite_insert().on_conflict_do_nothing()` for idempotent bulk price inserts.
- `DeclarativeBase` (SQLAlchemy 2.0 style) — no `Base = declarative_base()`.

### TradingView Lightweight Charts v5
- CDN import used; v4/v5 compat shim is in `app.js`.
- Add overlays via `addSeries(LC.LineSeries, opts)` — **not** `addLineSeries()` (v5 API).
- Place markers via `createSeriesMarkers(series, markers)` — **not** `series.setMarkers()`.
- Marker `time` must exactly match a candle bar timestamp or the marker is silently dropped. Use `snapToCandle(t, candleTimes)` (defined in `app.js`) before calling `createSeriesMarkers`.
- Left price scale for overlays: `priceScaleId: 'left'`; toggle visibility with `chart.applyOptions({ leftPriceScale: { visible: true } })`.

### News category classification
- `classify_article(headline)` in `stan/api/routes/news.py` — first-match wins across 7 keyword lists (fed, earnings, economic, tech, geopolitical, energy, merger); falls back to "general" (8 categories total).
- `MARKER_CATEGORIES` in `app.js` maps category → `{ label, color, key }` for legend rendering.

### Tests
- Use `StaticPool` + `connect_args={"check_same_thread": False}` for in-memory SQLite in tests.
- Replace the FastAPI lifespan with a no-op to prevent the scheduler from running during tests.
- Mock `yfinance.download` and `feedparser.parse` — never make real network calls in tests.
