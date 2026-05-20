"""Shared collection state — timestamps and error/run counters.

All reads and writes are protected by a threading.Lock so collector threads
and the FastAPI request handlers can access state safely.
"""

import threading

_lock = threading.Lock()

_state: dict = {
    "last_stock_ts": None,   # ISO string of last successful stock collection
    "last_news_ts":  None,   # ISO string of last successful news collection
    "stock_runs":    0,
    "stock_errors":  0,
    "news_runs":     0,
    "news_errors":   0,
}


def update(key: str, value) -> None:
    """Set a state value by key."""
    with _lock:
        _state[key] = value


def increment(key: str) -> None:
    """Increment a numeric counter by 1."""
    with _lock:
        _state[key] = _state.get(key, 0) + 1


def get_state() -> dict:
    """Return a snapshot copy of the current state."""
    with _lock:
        return dict(_state)
