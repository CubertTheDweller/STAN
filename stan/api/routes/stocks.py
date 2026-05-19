"""REST endpoints for stock price data and candlestick charts."""

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from stan.config import CANDLE_BACKFILL_THRESHOLD
from stan.database.db import SessionLocal, get_db
from stan.database.models import PriceSnapshot, Ticker

router = APIRouter(prefix="/api/stocks", tags=["stocks"])
logger = logging.getLogger(__name__)

_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90}


# ── Stock list ────────────────────────────────────────────────────────────────


@router.get("")
def list_stocks(
    sector: str | None = None,
    limit: int = Query(default=500, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return the most recent price snapshot for each tracked ticker."""
    # Subquery: latest timestamp per symbol
    subq = (
        db.query(
            PriceSnapshot.symbol,
            func.max(PriceSnapshot.timestamp).label("max_ts"),
        )
        .group_by(PriceSnapshot.symbol)
        .subquery()
    )

    query = (
        db.query(PriceSnapshot, Ticker)
        .join(
            subq,
            (PriceSnapshot.symbol == subq.c.symbol)
            & (PriceSnapshot.timestamp == subq.c.max_ts),
        )
        .outerjoin(Ticker, PriceSnapshot.symbol == Ticker.symbol)
    )

    if sector:
        query = query.filter(Ticker.sector == sector)

    total: int = query.count()
    rows = query.order_by(PriceSnapshot.symbol).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "symbol": snap.symbol,
                "name": ticker.name if ticker else None,
                "sector": ticker.sector if ticker else None,
                "exchange": ticker.exchange if ticker else None,
                "timestamp": snap.timestamp.isoformat() + "Z",
                "open": snap.open,
                "high": snap.high,
                "low": snap.low,
                "close": snap.close,
                "volume": snap.volume,
                "change_pct": snap.change_pct,
            }
            for snap, ticker in rows
        ],
    }


# ── Candle history ────────────────────────────────────────────────────────────


def _backfill_history(symbol: str, period: str) -> None:
    """Fetch daily candle history from yfinance and store it in the DB."""
    yf_period = period if period in ("1mo", "3mo") else "1mo"
    try:
        raw = yf.download(
            symbol,
            period=yf_period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        logger.error("yfinance backfill failed for %s: %s", symbol, exc)
        return

    if raw is None or raw.empty:
        return

    rows = []
    for ts, row in raw.iterrows():
        dt = ts.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        def sf(v):
            try:
                return None if pd.isna(v) else float(v)
            except Exception:
                return None

        rows.append(
            {
                "symbol": symbol,
                "timestamp": dt,
                "open": sf(row["Open"]),
                "high": sf(row["High"]),
                "low": sf(row["Low"]),
                "close": sf(row["Close"]),
                "volume": sf(row["Volume"]),
                "change_pct": None,
            }
        )

    if not rows:
        return

    db = SessionLocal()
    try:
        stmt = sqlite_insert(PriceSnapshot).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timestamp"])
        db.execute(stmt)
        db.commit()
        logger.info("Backfilled %d daily candles for %s", len(rows), symbol)
    except Exception as exc:
        logger.error("Backfill DB write error for %s: %s", symbol, exc)
        db.rollback()
    finally:
        db.close()


@router.get("/{symbol}/candles")
def get_candles(
    symbol: str,
    period: str = Query(default="1d", pattern="^(1d|5d|1mo|3mo)$"),
    db: Session = Depends(get_db),
):
    """Return OHLCV candle data formatted for TradingView Lightweight Charts."""
    symbol = symbol.upper()
    days = _PERIOD_DAYS.get(period, 1)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    rows = (
        db.query(PriceSnapshot)
        .filter(PriceSnapshot.symbol == symbol, PriceSnapshot.timestamp >= cutoff)
        .order_by(PriceSnapshot.timestamp)
        .all()
    )

    # Lazy backfill: if we don't have enough local data, fetch from yfinance
    if len(rows) < CANDLE_BACKFILL_THRESHOLD:
        _backfill_history(symbol, period)
        rows = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol == symbol, PriceSnapshot.timestamp >= cutoff)
            .order_by(PriceSnapshot.timestamp)
            .all()
        )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No candle data found for {symbol!r}")

    candles = []
    for row in rows:
        ts = row.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        candles.append(
            {
                "time": int(ts.timestamp()),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
        )

    return {"symbol": symbol, "period": period, "candles": candles}
