"""
News Processing Pipeline

Handles storage, deduplication, and source stats updates for collected news items.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.collector.base import CollectedItem, CollectionResult
from app.services.tagging import RuleMatcher


class NewsPipeline:
    """
    Pipeline for processing and storing collected news items.

    Responsibilities:
    - Deduplicate items by URL
    - Store new items to MongoDB
    - Update source statistics
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize pipeline with database connection.

        Args:
            db: Async MongoDB database instance
        """
        self.db = db
        self._tag_rules_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def process(
        self,
        source_doc: Dict[str, Any],
        result: CollectionResult,
    ) -> Tuple[int, int]:
        """
        Process collection result and store new items.

        Args:
            source_doc: Source document from database
            result: CollectionResult from collector

        Returns:
            Tuple of (items_stored, items_duplicated)
        """
        source_id = str(source_doc["_id"])
        user_id = source_doc["user_id"]
        source_name = source_doc["name"]
        source_type = source_doc["source_type"]

        if not result.success:
            # Update source with error status
            await self._update_source_error(source_doc, result.error_message)
            return 0, 0

        if not result.items:
            # No items but success (empty feed)
            await self._update_source_success(source_doc, 0)
            return 0, 0

        # Get existing URLs for deduplication
        existing_urls = await self._get_existing_urls(user_id, source_id)

        # Filter out duplicates and prepare documents
        new_items = []
        duplicates = 0

        for item in result.items:
            if item.url in existing_urls:
                duplicates += 1
                continue

            doc = self._item_to_document(
                item=item,
                user_id=user_id,
                source_id=source_id,
                source_name=source_name,
                source_type=source_type,
            )
            new_items.append(doc)
            existing_urls.add(item.url)  # Prevent duplicates within batch

        # Bulk insert new items
        stored = 0
        stored_docs = []
        if new_items:
            # Apply auto-tagging before insert
            await self._apply_auto_tags(user_id, new_items)

            try:
                result_insert = await self.db.news.insert_many(new_items, ordered=False)
                stored = len(result_insert.inserted_ids)
                # Add IDs to docs for ES indexing
                for i, doc in enumerate(new_items):
                    if i < len(result_insert.inserted_ids):
                        doc["_id"] = result_insert.inserted_ids[i]
                        stored_docs.append(doc)
                logger.info(f"Stored {stored} new items for source '{source_name}'")
            except Exception as e:
                logger.error(f"Error inserting news items: {e}")
                # Partial success is still possible with ordered=False

        # Index to Elasticsearch (async, non-blocking)
        if stored_docs:
            await self._index_to_elasticsearch(user_id, stored_docs)

        # Update source statistics
        await self._update_source_success(source_doc, stored)

        return stored, duplicates

    async def _get_existing_urls(self, user_id: str, source_id: str) -> set:
        """
        Get set of existing news URLs for deduplication.

        Args:
            user_id: User ID
            source_id: Source ID

        Returns:
            Set of URL strings
        """
        cursor = self.db.news.find(
            {"user_id": user_id, "source_id": source_id}, {"url": 1}
        )
        docs = await cursor.to_list(length=10000)
        return {doc["url"] for doc in docs}

    def _item_to_document(
        self,
        item: CollectedItem,
        user_id: str,
        source_id: str,
        source_name: str,
        source_type: str,
    ) -> Dict[str, Any]:
        """
        Convert CollectedItem to MongoDB document.

        Args:
            item: Collected news item
            user_id: Owner user ID
            source_id: Source ID
            source_name: Source display name
            source_type: Source type (rss/api/html)

        Returns:
            Document ready for insertion
        """
        now = datetime.utcnow()

        return {
            "user_id": user_id,
            "source_id": source_id,
            "source_name": source_name,
            "source_type": source_type,
            "title": item.title,
            "url": item.url,
            "description": item.description,
            "content": item.content,
            "image_url": item.image_url,
            "published_at": item.published_at,
            "tags": [],  # Auto-tagging applied after insertion
            "metadata": {
                "author": item.author,
                "hot_score": 0.0,
                "view_count": 0,
                "like_count": 0,
                "comment_count": 0,
                "language": "zh",
                "extra": item.extra or {},
            },
            "is_read": False,
            "is_starred": False,
            "read_at": None,
            "embedding": None,  # Will be populated by search service in Slice 4
            "crawled_at": now,
            "created_at": now,
            "updated_at": now,
        }

    async def _update_source_success(
        self,
        source_doc: Dict[str, Any],
        new_items_count: int,
    ) -> None:
        """
        Update source document after successful collection.

        Args:
            source_doc: Source document
            new_items_count: Number of new items stored
        """
        source_id = source_doc["_id"]
        now = datetime.utcnow()

        await self.db.sources.update_one(
            {"_id": source_id},
            {
                "$set": {
                    "status": "active",
                    "last_fetched_at": now,
                    "last_error": None,
                    "updated_at": now,
                },
                "$inc": {
                    "fetch_count": 1,
                    "item_count": new_items_count,
                },
            },
        )

        logger.debug(f"Updated source '{source_doc['name']}' status to active")

    async def _get_user_tag_rules(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get cached tag rules for a user.

        Args:
            user_id: User ID

        Returns:
            List of active tag rule documents
        """
        cursor = self.db.tag_rules.find({"user_id": user_id, "is_active": True}).sort(
            "priority", -1
        )
        return await cursor.to_list(length=100)

    async def _apply_auto_tags(
        self,
        user_id: str,
        items: List[Dict[str, Any]],
    ) -> None:
        """
        Apply auto-tagging to items based on user's tag rules.

        Args:
            user_id: User ID
            items: List of news item documents to tag
        """
        # Get user's tag rules
        rules = await self._get_user_tag_rules(user_id)

        if not rules:
            return

        # Create matcher
        matcher = RuleMatcher(rules)

        # Apply tags to each item
        for item in items:
            matched_tags, _ = matcher.match(
                title=item.get("title", ""),
                description=item.get("description", ""),
                content=item.get("content", ""),
            )
            if matched_tags:
                item["tags"] = matched_tags

    async def _index_to_elasticsearch(
        self,
        user_id: str,
        docs: List[Dict[str, Any]],
    ) -> None:
        """
        Index news items to Elasticsearch for search.

        Args:
            user_id: User ID
            docs: List of news documents with _id
        """
        try:
            from app.db.es import es_client
            from app.services.search.indexer import ESIndexer

            # Check if ES is available
            if not es_client.is_connected:
                logger.debug("Elasticsearch not available, skipping indexing")
                return

            indexer = ESIndexer(es_client.client)
            indexed = await indexer.index_batch(user_id, docs, generate_embeddings=True)
            logger.debug(f"Indexed {indexed} items to Elasticsearch")
        except Exception as e:
            # Non-critical, just log the error
            logger.warning(f"Failed to index to Elasticsearch: {e}")

    async def _update_source_error(
        self,
        source_doc: Dict[str, Any],
        error_message: Optional[str],
    ) -> None:
        """
        Update source document after failed collection.

        Args:
            source_doc: Source document
            error_message: Error description
        """
        source_id = source_doc["_id"]
        now = datetime.utcnow()

        await self.db.sources.update_one(
            {"_id": source_id},
            {
                "$set": {
                    "status": "error",
                    "last_fetched_at": now,
                    "last_error": error_message or "Unknown error",
                    "updated_at": now,
                },
                "$inc": {
                    "fetch_count": 1,
                },
            },
        )

        logger.warning(
            f"Source '{source_doc['name']}' marked as error: {error_message}"
        )


class CollectionService:
    """
    High-level service for running collection tasks.

    Combines collector and pipeline for end-to-end collection.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize collection service.

        Args:
            db: Async MongoDB database instance
        """
        self.db = db
        self.pipeline = NewsPipeline(db)

    async def collect_source(self, source_id: str) -> Dict[str, Any]:
        """
        Run collection for a single source.

        Args:
            source_id: Source ID to collect

        Returns:
            Result summary dict
        """
        from app.services.collector import CollectorFactory

        # Get source document
        try:
            oid = ObjectId(source_id)
        except Exception:
            return {"success": False, "error": "Invalid source ID"}

        source_doc = await self.db.sources.find_one({"_id": oid})
        if not source_doc:
            return {"success": False, "error": "Source not found"}

        logger.info(f"Starting collection for source: {source_doc['name']}")

        # Run collector
        result = await CollectorFactory.collect(source_doc)

        # Process results
        stored, duplicates = await self.pipeline.process(source_doc, result)

        return {
            "success": result.success,
            "source_id": source_id,
            "source_name": source_doc["name"],
            "items_fetched": result.items_fetched,
            "items_stored": stored,
            "items_duplicated": duplicates,
            "duration_seconds": result.duration_seconds,
            "error": result.error_message,
        }

    async def collect_user_sources(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Run collection for all active sources of a user.

        Args:
            user_id: User ID

        Returns:
            List of result summaries
        """
        cursor = self.db.sources.find(
            {
                "user_id": user_id,
                "status": {"$in": ["active", "pending"]},
                "source_type": {"$ne": "virtual"},
            }
        )
        sources = await cursor.to_list(length=100)

        results = []
        for source in sources:
            result = await self.collect_source(str(source["_id"]))
            results.append(result)

        return results

    async def collect_due_sources(self) -> List[Dict[str, Any]]:
        """
        Collect all sources that are due for refresh.

        This is intended to be called by the scheduler.

        Returns:
            List of result summaries
        """
        now = datetime.utcnow()

        # Find sources where:
        # - status is active or pending
        # - last_fetched_at + refresh_interval < now
        # OR last_fetched_at is None
        pipeline = [
            {
                "$match": {
                    "status": {"$in": ["active", "pending"]},
                    "source_type": {"$ne": "virtual"},
                }
            },
            {
                "$addFields": {
                    "refresh_interval_ms": {
                        "$multiply": ["$refresh_interval_minutes", 60000]
                    },
                    "next_fetch_at": {
                        "$add": [
                            {"$ifNull": ["$last_fetched_at", datetime(1970, 1, 1)]},
                            {"$multiply": ["$refresh_interval_minutes", 60000]},
                        ]
                    },
                }
            },
            {"$match": {"next_fetch_at": {"$lte": now}}},
            {"$limit": 50},  # Process in batches
        ]

        cursor = self.db.sources.aggregate(pipeline)
        sources = await cursor.to_list(length=50)

        results = []
        for source in sources:
            result = await self.collect_source(str(source["_id"]))
            results.append(result)

        if results:
            logger.info(f"Collected {len(results)} due sources")

        return results
