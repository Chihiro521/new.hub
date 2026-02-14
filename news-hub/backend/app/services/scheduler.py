"""
Task Scheduler Service

Manages periodic background tasks using APScheduler.
"""

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class TaskScheduler:
    """
    Singleton scheduler for background tasks.

    Uses APScheduler with AsyncIO for non-blocking execution.
    """

    _instance: Optional["TaskScheduler"] = None
    _scheduler: Optional[AsyncIOScheduler] = None

    def __new__(cls) -> "TaskScheduler":
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._scheduler = AsyncIOScheduler()
        return cls._instance

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """Get the underlying scheduler instance."""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
        return self._scheduler

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Task scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("Task scheduler shutdown")

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        minutes: int = 5,
        **kwargs: Any,
    ) -> None:
        """
        Add a job that runs at fixed intervals.

        Args:
            func: Async function to call
            job_id: Unique job identifier
            minutes: Interval in minutes
            **kwargs: Additional arguments passed to func
        """
        # Remove existing job if present
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func,
            trigger=IntervalTrigger(minutes=minutes),
            id=job_id,
            name=job_id,
            kwargs=kwargs,
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
        )
        logger.info(f"Added interval job '{job_id}' (every {minutes} min)")

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        hour: int = 0,
        minute: int = 0,
        **kwargs: Any,
    ) -> None:
        """
        Add a job that runs at a specific time daily.

        Args:
            func: Async function to call
            job_id: Unique job identifier
            hour: Hour (0-23)
            minute: Minute (0-59)
            **kwargs: Additional arguments passed to func
        """
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            name=job_id,
            kwargs=kwargs,
            replace_existing=True,
        )
        logger.info(f"Added cron job '{job_id}' (at {hour:02d}:{minute:02d})")

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_id: Job identifier

        Returns:
            True if job was removed, False if not found
        """
        job = self.scheduler.get_job(job_id)
        if job:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job '{job_id}'")
            return True
        return False

    def get_jobs(self) -> list:
        """Get list of all scheduled jobs."""
        return self.scheduler.get_jobs()


# Global scheduler instance
scheduler = TaskScheduler()


async def collection_task() -> None:
    """
    Background task to collect due sources.

    Called periodically by the scheduler.
    """
    from app.db.mongo import mongodb
    from app.services.pipeline import CollectionService

    if mongodb.client is None:
        logger.warning("MongoDB not connected, skipping collection task")
        return

    db = mongodb.get_database()
    service = CollectionService(db)

    try:
        results = await service.collect_due_sources()
        if results:
            success_count = sum(1 for r in results if r["success"])
            logger.info(
                f"Collection task complete: {success_count}/{len(results)} sources succeeded"
            )
    except Exception as e:
        logger.error(f"Collection task error: {e}")


def setup_scheduler() -> None:
    """
    Initialize and configure the scheduler with default jobs.

    Call this during application startup.
    """
    # Add periodic collection job (every 5 minutes)
    scheduler.add_interval_job(
        func=collection_task,
        job_id="collect_due_sources",
        minutes=5,
    )

    # Start the scheduler
    scheduler.start()


def shutdown_scheduler() -> None:
    """
    Shutdown the scheduler gracefully.

    Call this during application shutdown.
    """
    scheduler.shutdown(wait=True)
