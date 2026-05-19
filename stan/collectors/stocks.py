"""Stock price collector — fetches OHLCV data via yfinance every poll cycle."""

import logging
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from stan.config import STOCK_CHUNK_SIZE, TOP_NASDAQ, TOP_NYSE, TRACKED_TICKERS
from stan.database.db import SessionLocal
from stan.database.models import PriceSnapshot, Ticker

logger = logging.getLogger(__name__)

# Module-level cache so we only resolve symbols once per process
_ticker_cache: list[str] = []


# ── Ticker bootstrap ─────────────────────────────────────────────────────────


def fetch_sp500_symbols() -> list[str]:
    """Return the curated top-50-per-exchange ticker list from config."""
    logger.info(
        "Using %d curated tickers (%d NASDAQ + %d NYSE)",
        len(TRACKED_TICKERS),
        len(TOP_NASDAQ),
        len(TOP_NYSE),
    )
    return list(TRACKED_TICKERS)


def seed_tickers(symbols: list[str]) -> None:
    """Insert any unknown symbols into the tickers table."""
    db = SessionLocal()
    try:
        existing: set[str] = {row[0] for row in db.query(Ticker.symbol).all()}
        new_tickers = [Ticker(symbol=s) for s in symbols if s not in existing]
        if new_tickers:
            db.bulk_save_objects(new_tickers)
            db.commit()
            logger.info("Seeded %d new ticker records", len(new_tickers))
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _safe_float(val) -> float | None:
    try:
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


# ── Main collector ────────────────────────────────────────────────────────────


def collect_stocks() -> None:
    """Fetch the latest 5-minute OHLCV bar for every tracked ticker and store it."""
    global _ticker_cache

    if not _ticker_cache:
        _ticker_cache = fetch_sp500_symbols()
        if not _ticker_cache:
            logger.warning("No tickers available — skipping stock collection cycle")
            return
        seed_tickers(_ticker_cache)

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    snapshots: list[dict] = []

    for chunk in _chunks(_ticker_cache, STOCK_CHUNK_SIZE):
        try:
            raw: pd.DataFrame = yf.download(
                tickers=chunk,
                period="2d",
                interval="5m",
                group_by="column",  # MultiIndex: (PriceType, Symbol)
                progress=False,
                threads=True,
                auto_adjust=True,
            )
        except Exception as exc:
            logger.error("yfinance batch download error: %s", exc)
            continue

        if raw is None or raw.empty:
            continue

        is_multi = isinstance(raw.columns, pd.MultiIndex)

        for symbol in chunk:
            try:
                if is_multi:
                    sym_df = raw.xs(symbol, level=1, axis=1).dropna(how="all")
                else:
                    # Single-ticker edge case — columns are flat
                    sym_df = raw.dropna(how="all")

                if sym_df.empty:
                    continue

                last = sym_df.iloc[-1]
                prev_close: float | None = (
                    _safe_float(sym_df.iloc[-2]["Close"]) if len(sym_df) >= 2 else None
                )
                close = _safe_float(last["Close"])
                change_pct: float | None = None
                if close is not None and prev_close and prev_close != 0:
                    change_pct = round(((close - prev_close) / prev_close) * 100, 4)

                snapshots.append(
                    {
                        "symbol": symbol,
                        "timestamp": now,
                        "open": _safe_float(last["Open"]),
                        "high": _safe_float(last["High"]),
                        "low": _safe_float(last["Low"]),
                        "close": close,
                        "volume": _safe_float(last["Volume"]),
                        "change_pct": change_pct,
                    }
                )
            except Exception as exc:
                logger.debug("Skipping %s: %s", symbol, exc)

    if not snapshots:
        logger.warning("No snapshot data collected this cycle")
        return

    db = SessionLocal()
    try:
        stmt = sqlite_insert(PriceSnapshot).values(snapshots)
        stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
        db.execute(stmt)
        db.commit()
        logger.info("Stored %d price snapshots at %s", len(snapshots), now.isoformat())
    except Exception as exc:
        logger.error("DB write error (stocks): %s", exc)
        db.rollback()
    finally:
        db.close()
