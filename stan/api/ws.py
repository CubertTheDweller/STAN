"""WebSocket connection manager — broadcasts live collection events to browsers.

Collectors run in plain threads; they call broadcast_sync() which uses
asyncio.run_coroutine_threadsafe() to enqueue the async send without
blocking the collector thread.
"""

import asyncio
import logging

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)

_connections: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store a reference to the running event loop (call from lifespan)."""
    global _loop
    _loop = loop


async def connect(ws: WebSocket) -> None:
    """Accept a new WebSocket connection and register it."""
    await ws.accept()
    _connections.add(ws)
    logger.debug("WS client connected (%d total)", len(_connections))


def disconnect(ws: WebSocket) -> None:
    """Remove a WebSocket connection from the registry."""
    _connections.discard(ws)
    logger.debug("WS client disconnected (%d remaining)", len(_connections))


async def _broadcast(msg: dict) -> None:
    """Send msg to every connected client; silently drop dead connections."""
    dead: set[WebSocket] = set()
    for ws in list(_connections):
        try:
            await ws.send_json(msg)
        except (WebSocketDisconnect, Exception):
            dead.add(ws)
    for ws in dead:
        _connections.discard(ws)


def broadcast_sync(msg: dict) -> None:
    """Thread-safe broadcast — safe to call from sync collector threads."""
    if _loop is None or not _connections:
        return
    try:
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)
    except Exception as exc:
        logger.debug("WS broadcast failed: %s", exc)
