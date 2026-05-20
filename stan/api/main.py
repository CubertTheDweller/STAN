"""FastAPI application — DB init, scheduler startup, static files, and routes."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stan.api import ws as ws_manager
from stan.api.routes import news, stocks, system
from stan.collectors.news import collect_news
from stan.collectors.stocks import collect_stocks
from stan.config import LOG_LEVEL
from stan.database.db import init_db
from stan.scheduler import create_scheduler

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"
STATIC_DIR = BASE_DIR / "frontend" / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database…")
    init_db()

    # Store the running event loop so sync collector threads can broadcast WS events
    ws_manager.set_loop(asyncio.get_event_loop())

    scheduler = create_scheduler()
    scheduler.start()

    # Kick off an immediate first collection in background threads so the
    # dashboard has data as soon as the server is ready.
    threading.Thread(target=collect_stocks, daemon=True, name="initial-stocks").start()
    threading.Thread(target=collect_news, daemon=True, name="initial-news").start()

    yield  # server is running

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped — goodbye")


app = FastAPI(
    title="STAN — Stock Trading on Active News",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(stocks.router)
app.include_router(news.router)
app.include_router(system.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint — pushes a message to the client after each collection cycle."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; we only send server→client messages
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        ws_manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")
