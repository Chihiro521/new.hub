"""
Elasticsearch Indexer Service

Handles indexing news items to Elasticsearch for search functionality.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from loguru import logger

from app.db.es import es_client
from app.services.search.embedding import embedding_service


class ESIndexer:
    """
    Indexes news items to Elasticsearch.

    Handles:
    - Single document indexing
    - Batch indexing
    - Embedding generation
    - Document updates
    """

    def __init__(self, es: AsyncElasticsearch):
        """
        Initialize indexer.

        Args:
            es: Elasticsearch async client
        """
        self.es = es

    def _get_index_name(self, user_id: str) -> str:
        """Get ES index name for user."""
        return es_client.index_name(f"news_{user_id}")

    async def index_news_item(
        self,
        user_id: str,
        news_id: str,
        doc: Dict[str, Any],
        generate_embedding: bool = True,
    ) -> bool:
        """
        Index a single news item.

        Args:
            user_id: User ID
            news_id: News item ID
            doc: News document from MongoDB
            generate_embedding: Whether to generate embedding

        Returns:
            True if successful
        """
        try:
            # Ensure index exists
            await es_client.ensure_user_index(user_id)
            index_name = self._get_index_name(user_id)

            # Prepare document for ES
            es_doc = self._prepare_document(doc)

            # Generate embedding if enabled
            if generate_embedding and embedding_service.is_available:
                text_for_embedding = self._get_text_for_embedding(doc)
                embedding = embedding_service.encode(text_for_embedding)
                if embedding:
                    es_doc["embedding"] = embedding

            # Index document
            await self.es.index(
                index=index_name,
                id=news_id,
                document=es_doc,
            )

            return True
        except Exception as e:
            logger.error(f"Error indexing news item {news_id}: {e}")
            return False

    async def index_batch(
        self,
        user_id: str,
        items: List[Dict[str, Any]],
        generate_embeddings: bool = True,
    ) -> int:
        """
        Index multiple news items in batch.

        Args:
            user_id: User ID
            items: List of (news_id, doc) tuples
            generate_embeddings: Whether to generate embeddings

        Returns:
            Number of successfully indexed items
        """
        if not items:
            return 0

        try:
            # Ensure index exists
            await es_client.ensure_user_index(user_id)
            index_name = self._get_index_name(user_id)

            # Prepare documents
            docs = []
            texts_for_embedding = []

            for item in items:
                news_id = str(item.get("_id", item.get("id", "")))
                es_doc = self._prepare_document(item)
                es_doc["_id"] = news_id
                docs.append(es_doc)
                texts_for_embedding.append(self._get_text_for_embedding(item))

            # Generate embeddings in batch
            if generate_embeddings and embedding_service.is_available:
                embeddings = embedding_service.encode_batch(texts_for_embedding)
                for i, embedding in enumerate(embeddings):
                    if embedding:
                        docs[i]["embedding"] = embedding

            # Build bulk request
            operations = []
            for doc in docs:
                doc_id = doc.pop("_id")
                operations.append({"index": {"_index": index_name, "_id": doc_id}})
                operations.append(doc)

            # Execute bulk request
            response = await self.es.bulk(operations=operations)

            # Count successes
            success_count = 0
            for item in response.get("items", []):
                if item.get("index", {}).get("status") in [200, 201]:
                    success_count += 1

            logger.info(f"Indexed {success_count}/{len(items)} items to ES")
            return success_count

        except Exception as e:
            logger.error(f"Error batch indexing: {e}")
            return 0

    async def update_state(
        self,
        user_id: str,
        news_id: str,
        is_read: Optional[bool] = None,
        is_starred: Optional[bool] = None,
    ) -> bool:
        """
        Update read/starred state in ES.

        Args:
            user_id: User ID
            news_id: News item ID
            is_read: New read state
            is_starred: New starred state

        Returns:
            True if successful
        """
        index_name = self._get_index_name(user_id)

        update_doc: Dict[str, Any] = {}
        if is_read is not None:
            update_doc["is_read"] = is_read
        if is_starred is not None:
            update_doc["is_starred"] = is_starred

        if not update_doc:
            return True

        try:
            await self.es.update(
                index=index_name,
                id=news_id,
                doc=update_doc,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating ES document {news_id}: {e}")
            return False

    async def delete_news_item(self, user_id: str, news_id: str) -> bool:
        """
        Delete a news item from ES.

        Args:
            user_id: User ID
            news_id: News item ID

        Returns:
            True if successful
        """
        index_name = self._get_index_name(user_id)

        try:
            await self.es.delete(index=index_name, id=news_id)
            return True
        except Exception as e:
            logger.error(f"Error deleting ES document {news_id}: {e}")
            return False

    async def delete_by_source(self, user_id: str, source_id: str) -> int:
        """
        Delete all news items from a source.

        Args:
            user_id: User ID
            source_id: Source ID

        Returns:
            Number of deleted items
        """
        index_name = self._get_index_name(user_id)

        try:
            response = await self.es.delete_by_query(
                index=index_name,
                query={"term": {"source_id": source_id}},
            )
            deleted = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} ES documents for source {source_id}")
            return deleted
        except Exception as e:
            logger.error(f"Error deleting ES documents by source: {e}")
            return 0

    def _prepare_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare MongoDB document for ES indexing."""
        return {
            "user_id": doc.get("user_id", ""),
            "source_id": doc.get("source_id", ""),
            "source_name": doc.get("source_name", ""),
            "source_type": doc.get("source_type", ""),
            "title": doc.get("title", ""),
            "url": doc.get("url", ""),
            "description": doc.get("description"),
            "content": doc.get("content"),
            "image_url": doc.get("image_url"),
            "tags": doc.get("tags", []),
            "published_at": doc.get("published_at"),
            "crawled_at": doc.get("crawled_at", datetime.utcnow()),
            "hot_score": doc.get("metadata", {}).get("hot_score", 0.0),
            "view_count": doc.get("metadata", {}).get("view_count", 0),
            "is_read": doc.get("is_read", False),
            "is_starred": doc.get("is_starred", False),
        }

    def _get_text_for_embedding(self, doc: Dict[str, Any]) -> str:
        """Extract text for embedding generation."""
        parts = [doc.get("title", "")]

        if doc.get("description"):
            parts.append(doc["description"])

        # Include tags
        if doc.get("tags"):
            parts.append(" ".join(doc["tags"]))

        return " ".join(parts)


async def get_es_indexer() -> ESIndexer:
    """Get ES indexer instance."""
    return ESIndexer(es_client.client)
