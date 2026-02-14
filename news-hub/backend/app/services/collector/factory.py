"""
Collector Factory

Creates the appropriate collector based on source type.
"""

from typing import Any, Dict

from loguru import logger

from app.services.collector.base import BaseCollector, CollectionResult
from app.services.collector.rss_collector import RSSCollector
from app.services.collector.api_collector import APICollector


class CollectorFactory:
    """
    Factory for creating source collectors.

    Selects the appropriate collector class based on source_type.
    """

    _collectors = {
        "rss": RSSCollector,
        "api": APICollector,
        # "html": HTMLCollector,  # TODO: Implement with Scrapy in Slice 3+
    }

    @classmethod
    def create(cls, source_config: Dict[str, Any]) -> BaseCollector:
        """
        Create a collector instance for the given source configuration.

        Args:
            source_config: Source document from database

        Returns:
            Appropriate collector instance

        Raises:
            ValueError: If source_type is not supported
        """
        source_type = source_config.get("source_type", "").lower()

        if source_type not in cls._collectors:
            raise ValueError(f"Unsupported source type: {source_type}")

        collector_class = cls._collectors[source_type]
        logger.debug(
            f"Creating {collector_class.__name__} for source: {source_config.get('name')}"
        )

        return collector_class(source_config)

    @classmethod
    async def collect(cls, source_config: Dict[str, Any]) -> CollectionResult:
        """
        Convenience method to create collector and fetch in one call.

        Args:
            source_config: Source document from database

        Returns:
            CollectionResult from the fetch operation
        """
        try:
            collector = cls.create(source_config)
            return await collector.fetch()
        except ValueError as e:
            return CollectionResult(
                success=False,
                items=[],
                error_message=str(e),
            )
