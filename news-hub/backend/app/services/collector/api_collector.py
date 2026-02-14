"""
API JSON Collector

Collects news items from JSON API endpoints.
"""

import time
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from app.services.collector.base import BaseCollector, CollectedItem, CollectionResult


class APICollector(BaseCollector):
    """
    Collector for JSON API endpoints.

    Parses JSON responses using configurable field mappings.
    """

    async def fetch(self) -> CollectionResult:
        """
        Fetch and parse JSON API response.

        Returns:
            CollectionResult with parsed news items.
        """
        start_time = time.time()
        items = []

        try:
            logger.info(f"Fetching API: {self.url}")

            # Get custom headers from config
            headers = self.headers.copy()
            api_config = self.parser_config.get("api", {})
            if api_config.get("headers"):
                headers.update(api_config["headers"])

            # Fetch JSON
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(self.url, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Extract list of items
            list_path = api_config.get("list_path", "")
            item_list = self._extract_by_path(data, list_path)

            if not isinstance(item_list, list):
                logger.warning(f"API response is not a list at path '{list_path}'")
                return CollectionResult(
                    success=False,
                    items=[],
                    error_message=f"Expected list at path '{list_path}'",
                    duration_seconds=time.time() - start_time,
                )

            # Parse each item
            fields = api_config.get("fields", {})
            for raw_item in item_list:
                item = self._parse_item(raw_item, fields)
                if item:
                    items.append(item)

            duration = time.time() - start_time
            logger.info(
                f"API collection complete: {len(items)} items from {self.source_name}"
            )

            return CollectionResult(
                success=True,
                items=items,
                items_fetched=len(items),
                duration_seconds=duration,
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching API: {self.url}")
            return CollectionResult(
                success=False,
                items=[],
                error_message="Request timeout",
                duration_seconds=time.time() - start_time,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching API: {e}")
            return CollectionResult(
                success=False,
                items=[],
                error_message=f"HTTP {e.response.status_code}",
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error(f"Error fetching API {self.url}: {e}")
            return CollectionResult(
                success=False,
                items=[],
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _extract_by_path(self, data: Any, path: str) -> Any:
        """
        Extract value from nested dict using dot-notation path.

        Examples:
            - "" or "@" -> return data as-is
            - "items" -> data["items"]
            - "data.articles" -> data["data"]["articles"]
        """
        if not path or path == "@":
            return data

        current = data
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current

    def _parse_item(
        self, raw_item: Dict[str, Any], fields: Dict[str, str]
    ) -> CollectedItem | None:
        """
        Parse a single API item using field mappings.

        Args:
            raw_item: Raw JSON object
            fields: Mapping of target field names to source field paths

        Returns:
            CollectedItem or None if required fields missing
        """
        # Extract title (required)
        title_path = fields.get("title", "title")
        title = self._extract_by_path(raw_item, title_path)
        if not title:
            return None

        # Extract link (required)
        link_path = fields.get("link", fields.get("url", "url"))
        link = self._extract_by_path(raw_item, link_path)
        if not link:
            # Try common alternatives
            for alt in ["href", "uri", "permalink"]:
                link = raw_item.get(alt)
                if link:
                    break

        if not link:
            return None

        # Extract optional fields
        description_path = fields.get(
            "description", fields.get("content", "description")
        )
        description = self._extract_by_path(raw_item, description_path)
        if description and isinstance(description, str):
            description = self._clean_html(description)
            if description:
                description = description[:2000]

        content_path = fields.get("content", fields.get("body", ""))
        content = (
            self._extract_by_path(raw_item, content_path) if content_path else None
        )

        image_path = fields.get(
            "image", fields.get("image_url", fields.get("thumbnail", ""))
        )
        image_url = self._extract_by_path(raw_item, image_path) if image_path else None

        # Try common image fields
        if not image_url:
            for img_field in ["image", "thumbnail", "cover", "thumb", "pic", "img"]:
                image_url = raw_item.get(img_field)
                if image_url:
                    break

        published_path = fields.get("published_at", fields.get("date", ""))
        published_str = (
            self._extract_by_path(raw_item, published_path) if published_path else None
        )
        published_at = self._parse_datetime(published_str) if published_str else None

        author_path = fields.get("author", "")
        author = self._extract_by_path(raw_item, author_path) if author_path else None

        return CollectedItem(
            title=str(title).strip(),
            url=str(link),
            description=description,
            content=content,
            image_url=image_url,
            published_at=published_at,
            author=author,
            extra={"raw_id": raw_item.get("id")},
        )
