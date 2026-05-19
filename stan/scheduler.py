"""APScheduler background scheduler — fires stock and news collectors every N seconds."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from stan.collectors.archive import archive_old_data
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

    scheduler.add_job(
        archive_old_data,
        trigger=CronTrigger(day=1, hour=3, minute=0, timezone="UTC"),
        id="archive_old_data",
        name="Archive and remove data older than DB_RETENTION_MONTHS",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler configured: stock + news + impact collection every %ds; archive job on 1st of each month",
        POLL_INTERVAL_SECONDS,
    )
    return scheduler
