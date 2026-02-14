"""
RSS/Atom Feed Collector

Collects news items from RSS and Atom feeds using feedparser.
"""

import time
from typing import Any

import feedparser
import httpx
from loguru import logger

from app.services.collector.base import BaseCollector, CollectedItem, CollectionResult


class RSSCollector(BaseCollector):
    """
    Collector for RSS and Atom feeds.

    Uses feedparser to handle various feed formats automatically.
    """

    async def fetch(self) -> CollectionResult:
        """
        Fetch and parse RSS/Atom feed.

        Returns:
            CollectionResult with parsed news items.
        """
        start_time = time.time()
        items = []

        try:
            logger.info(f"Fetching RSS feed: {self.url}")

            # Fetch feed content
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(self.url, headers=self.headers)
                response.raise_for_status()
                content = response.text

            # Parse with feedparser
            feed = feedparser.parse(content)

            if feed.bozo and feed.bozo_exception:
                # Feed has errors but may still be partially parseable
                logger.warning(
                    f"Feed parsing warning for {self.url}: {feed.bozo_exception}"
                )

            # Extract items
            for entry in feed.entries:
                item = self._parse_entry(entry)
                if item:
                    items.append(item)

            duration = time.time() - start_time
            logger.info(
                f"RSS collection complete: {len(items)} items from {self.source_name}"
            )

            return CollectionResult(
                success=True,
                items=items,
                items_fetched=len(items),
                duration_seconds=duration,
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching RSS feed: {self.url}")
            return CollectionResult(
                success=False,
                items=[],
                error_message="Request timeout",
                duration_seconds=time.time() - start_time,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching RSS feed: {e}")
            return CollectionResult(
                success=False,
                items=[],
                error_message=f"HTTP {e.response.status_code}",
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error(f"Error fetching RSS feed {self.url}: {e}")
            return CollectionResult(
                success=False,
                items=[],
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _parse_entry(self, entry: Any) -> CollectedItem | None:
        """
        Parse a single feed entry into a CollectedItem.

        Args:
            entry: feedparser entry object

        Returns:
            CollectedItem or None if entry is invalid
        """
        # Title is required
        title = getattr(entry, "title", None)
        if not title:
            return None

        # Get link (required)
        link = getattr(entry, "link", None)
        if not link:
            # Try alternate links
            links = getattr(entry, "links", [])
            for l in links:
                if l.get("rel") == "alternate":
                    link = l.get("href")
                    break

        if not link:
            return None

        # Get description/summary
        description = None
        if hasattr(entry, "summary"):
            description = self._clean_html(entry.summary)
        elif hasattr(entry, "description"):
            description = self._clean_html(entry.description)

        # Get full content if available
        content = None
        if hasattr(entry, "content") and entry.content:
            # content is usually a list of content objects
            content_obj = entry.content[0] if entry.content else None
            if content_obj and hasattr(content_obj, "value"):
                content = content_obj.value

        # Get published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import datetime

            try:
                published_at = datetime.datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass

        if (
            not published_at
            and hasattr(entry, "updated_parsed")
            and entry.updated_parsed
        ):
            import datetime

            try:
                published_at = datetime.datetime(*entry.updated_parsed[:6])
            except (TypeError, ValueError):
                pass

        if not published_at:
            published_str = getattr(entry, "published", None) or getattr(
                entry, "updated", None
            )
            published_at = self._parse_datetime(published_str)

        # Get author
        author = getattr(entry, "author", None)
        if not author and hasattr(entry, "authors") and entry.authors:
            author = entry.authors[0].get("name")

        # Get image
        image_url = None

        # Check media_thumbnail (common in RSS)
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            image_url = entry.media_thumbnail[0].get("url")

        # Check media_content
        if not image_url and hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                if media.get("medium") == "image" or media.get("type", "").startswith(
                    "image/"
                ):
                    image_url = media.get("url")
                    break

        # Check enclosures
        if not image_url and hasattr(entry, "enclosures") and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image/"):
                    image_url = enc.get("href")
                    break

        # Try to extract from content
        if not image_url:
            image_url = self._extract_image_from_content(content or description)

        return CollectedItem(
            title=title.strip(),
            url=link,
            description=description[:2000] if description else None,
            content=content,
            image_url=image_url,
            published_at=published_at,
            author=author,
            extra={
                "feed_id": getattr(entry, "id", None),
                "tags": [
                    tag.get("term")
                    for tag in getattr(entry, "tags", [])
                    if tag.get("term")
                ],
            },
        )
