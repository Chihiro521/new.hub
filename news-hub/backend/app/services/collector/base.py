"""
Base Collector Interface

Abstract base class for all content collectors (RSS, API, HTML).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class CollectedItem:
    """Standardized news item from any source type."""

    title: str
    url: str
    description: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "content": self.content,
            "image_url": self.image_url,
            "published_at": self.published_at,
            "author": self.author,
            "extra": self.extra or {},
        }


@dataclass
class CollectionResult:
    """Result of a collection operation."""

    success: bool
    items: List[CollectedItem]
    error_message: Optional[str] = None
    items_fetched: int = 0
    items_new: int = 0
    duration_seconds: float = 0.0

    @property
    def summary(self) -> str:
        """Human-readable summary."""
        if self.success:
            return f"Fetched {self.items_fetched} items, {self.items_new} new"
        return f"Failed: {self.error_message}"


class BaseCollector(ABC):
    """
    Abstract base class for content collectors.

    Each collector type (RSS, API, HTML) implements this interface
    to provide standardized news item collection.
    """

    def __init__(self, source_config: Dict[str, Any]):
        """
        Initialize collector with source configuration.

        Args:
            source_config: Source document from database including URL,
                           parser_config, and other settings.
        """
        self.source_id = source_config.get("_id", source_config.get("id", "unknown"))
        self.user_id = source_config.get("user_id", "unknown")
        self.url = source_config.get("url", "")
        self.source_name = source_config.get("name", "Unknown Source")
        self.source_type = source_config.get("source_type", "unknown")
        self.parser_config = source_config.get("parser_config", {})
        self.timeout = 30.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    @abstractmethod
    async def fetch(self) -> CollectionResult:
        """
        Fetch and parse content from the source.

        Returns:
            CollectionResult with collected items or error information.
        """
        pass

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse various date string formats to datetime.

        Handles ISO 8601, RFC 2822 (RSS), and common formats.
        """
        if not date_str:
            return None

        from email.utils import parsedate_to_datetime
        import dateutil.parser

        try:
            # Try RFC 2822 first (common in RSS)
            return parsedate_to_datetime(date_str)
        except (TypeError, ValueError):
            pass

        try:
            # Try ISO 8601 and other formats with dateutil
            return dateutil.parser.parse(date_str)
        except (ValueError, TypeError):
            pass

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _clean_html(self, html: Optional[str]) -> Optional[str]:
        """Strip HTML tags and clean text."""
        if not html:
            return None

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # Collapse multiple spaces
        import re

        return re.sub(r"\s+", " ", text).strip()

    def _extract_image_from_content(self, html: Optional[str]) -> Optional[str]:
        """Extract first image URL from HTML content."""
        if not html:
            return None

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        img = soup.find("img", src=True)
        if img:
            return img.get("src")
        return None
