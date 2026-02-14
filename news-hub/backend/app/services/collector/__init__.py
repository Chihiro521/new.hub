"""
Collector Services Package

Provides content collection from various source types (RSS, API, HTML).
"""

from app.services.collector.base import BaseCollector, CollectedItem, CollectionResult
from app.services.collector.factory import CollectorFactory
from app.services.collector.rss_collector import RSSCollector
from app.services.collector.api_collector import APICollector


__all__ = [
    "BaseCollector",
    "CollectedItem",
    "CollectionResult",
    "CollectorFactory",
    "RSSCollector",
    "APICollector",
]
