"""APScheduler background scheduler — fires stock and news collectors every N seconds."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from stan.collectors.impact import fill_news_impact
from stan.collectors.news import collect_news
from stan.collectors.stocks import collect_stocks
from stan.config import POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        collect_stocks,
        trigger=IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
        id="collect_stocks",
        name="Collect stock price snapshots",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        collect_news,
        trigger=IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
        id="collect_news",
        name="Collect news articles from RSS feeds",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        fill_news_impact,
        trigger=IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
        id="fill_news_impact",
        name="Fill news-impact price captures",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )

    logger.info(
        "Scheduler configured: stock + news + impact collection every %ds",
        POLL_INTERVAL_SECONDS,
    )
    return scheduler
