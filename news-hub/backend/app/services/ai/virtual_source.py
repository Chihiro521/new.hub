"""
Virtual Source Manager

Creates and manages system-level "virtual" sources for external search results.
Virtual sources are auto-created per user+provider, skip scheduled collection,
and allow external content to be persisted with proper source_id references.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from pymongo.errors import BulkWriteError

from app.db.mongo import mongodb


class VirtualSourceManager:
    """Manages virtual sources for external search result ingestion."""

    # Cache to avoid repeated DB lookups within a request
    _source_cache: Dict[str, str] = {}

    @classmethod
    async def get_or_create(
        cls,
        user_id: str,
        provider: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get or create a virtual source for a user+provider pair.

        Args:
            user_id: Owner user ID.
            provider: External provider key (e.g. "tavily", "bing").
            display_name: Human-readable name, defaults to provider title.

        Returns:
            Source document dict with at least _id, name, source_type.
        """
        cache_key = f"{user_id}:{provider}"
        if cache_key in cls._source_cache:
            doc = await mongodb.db.sources.find_one(
                {"_id": cls._source_cache[cache_key]}
            )
            if doc:
                return doc

        # Try to find existing
        doc = await mongodb.db.sources.find_one(
            {
                "user_id": user_id,
                "source_type": "virtual",
                "metadata.provider": provider,
            }
        )
        if doc:
            cls._source_cache[cache_key] = doc["_id"]
            return doc

        # Create new virtual source
        name = display_name or f"{provider.title()} 外部搜索"
        now = datetime.utcnow()
        new_doc = {
            "user_id": user_id,
            "name": name,
            "url": f"virtual://{provider}",
            "source_type": "virtual",
            "description": f"系统自动创建的虚拟源，用于存储 {name} 的外部搜索结果",
            "status": "active",
            "refresh_interval_minutes": 0,
            "tags": [],
            "metadata": {"provider": provider},
            "last_fetched_at": None,
            "last_error": None,
            "fetch_count": 0,
            "item_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = await mongodb.db.sources.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id
        cls._source_cache[cache_key] = result.inserted_id
        logger.info(
            f"Created virtual source '{name}' for user {user_id}, provider={provider}"
        )
        return new_doc

    @classmethod
    async def ingest_results(
        cls,
        user_id: str,
        provider: str,
        items: List[Dict[str, Any]],
    ) -> int:
        """Persist external search results as news items under a virtual source.

        Args:
            user_id: Owner user ID.
            provider: External provider key.
            items: List of dicts with at least {title, url}. Optional: description,
                   content, image_url, published_at.

        Returns:
            Number of new items stored (after dedup by URL).
        """
        if not items:
            return 0

        source_doc = await cls.get_or_create(user_id, provider)
        source_id = str(source_doc["_id"])
        source_name = source_doc["name"]

        # Dedup against existing URLs for this source
        urls = [item["url"] for item in items if item.get("url")]
        existing = await mongodb.db.news.find(
            {"user_id": user_id, "source_id": source_id, "url": {"$in": urls}},
            {"url": 1},
        ).to_list(length=len(urls))
        existing_urls = {doc["url"] for doc in existing}

        now = datetime.utcnow()
        docs = []
        for item in items:
            url = item.get("url", "")
            if not url or url in existing_urls:
                continue
            existing_urls.add(url)

            item_metadata = item.get("metadata") or {}
            merged_extra = {
                "provider": provider,
                "engine": item.get("engine"),
                "raw_score": item.get("score"),
                **item_metadata,
            }

            docs.append(
                {
                    "user_id": user_id,
                    "source_id": source_id,
                    "source_name": source_name,
                    "source_type": "virtual",
                    "title": item.get("title", ""),
                    "url": url,
                    "description": item.get("description", ""),
                    "content": item.get("content", ""),
                    "image_url": item.get("image_url"),
                    "published_at": item.get("published_at"),
                    "tags": [],
                    "metadata": {
                        "author": item.get("author", ""),
                        "hot_score": 0.0,
                        "view_count": 0,
                        "like_count": 0,
                        "comment_count": 0,
                        "language": "zh",
                        "extra": merged_extra,
                    },
                    "is_read": False,
                    "is_starred": False,
                    "read_at": None,
                    "embedding": None,
                    "crawled_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        if not docs:
            return 0

        try:
            result = await mongodb.db.news.insert_many(docs, ordered=False)
            stored = len(result.inserted_ids)

            # Update source stats
            await mongodb.db.sources.update_one(
                {"_id": source_doc["_id"]},
                {
                    "$inc": {"item_count": stored},
                    "$set": {"updated_at": now},
                },
            )

            # Index to ES (best-effort)
            await cls._index_to_es(user_id, docs, result.inserted_ids)

            logger.info(f"Ingested {stored} items via virtual source '{source_name}'")
            return stored
        except BulkWriteError as e:
            details = e.details or {}
            stored = int(details.get("nInserted", 0) or 0)
            if stored > 0:
                await mongodb.db.sources.update_one(
                    {"_id": source_doc["_id"]},
                    {
                        "$inc": {"item_count": stored},
                        "$set": {"updated_at": now},
                    },
                )
            logger.warning(
                f"Virtual source ingestion partially succeeded: inserted={stored}, errors={len(details.get('writeErrors', []))}"
            )
            return stored
        except Exception as e:
            logger.error(f"Virtual source ingestion failed: {e}")
            return 0

    @classmethod
    async def _index_to_es(
        cls,
        user_id: str,
        docs: List[Dict[str, Any]],
        inserted_ids: list,
    ) -> None:
        """Best-effort ES indexing for ingested items."""
        try:
            from app.db.es import es_client
            from app.services.search.indexer import ESIndexer

            if not es_client.is_connected:
                return

            for i, doc in enumerate(docs):
                if i < len(inserted_ids):
                    doc["_id"] = inserted_ids[i]

            indexer = ESIndexer(es_client.client)
            await indexer.index_batch(user_id, docs, generate_embeddings=True)
        except Exception as e:
            logger.warning(f"ES indexing for virtual source failed: {e}")
