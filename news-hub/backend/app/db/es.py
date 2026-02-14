"""
Elasticsearch Connection and Index Management

Provides async Elasticsearch client with index lifecycle management.
Supports vector search with dense_vector fields.
"""

from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from loguru import logger

from app.core.config import settings


class ElasticsearchClient:
    """
    Elasticsearch connection manager.

    Handles connection lifecycle and provides index management methods.
    """

    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        """Establish connection to Elasticsearch."""
        logger.info(f"Connecting to Elasticsearch: {settings.elasticsearch_url}")

        # Build connection kwargs
        es_kwargs: Dict[str, Any] = {
            "hosts": [settings.elasticsearch_url],
            "request_timeout": 30,
            "max_retries": 3,
            "retry_on_timeout": True,
        }

        # Add authentication if configured
        if settings.elasticsearch_username and settings.elasticsearch_password:
            es_kwargs["basic_auth"] = (
                settings.elasticsearch_username,
                settings.elasticsearch_password,
            )

        self._client = AsyncElasticsearch(**es_kwargs)

        # Verify connection
        try:
            info = await self._client.info()
            logger.info(
                f"Elasticsearch connected: {info['cluster_name']} "
                f"(version {info['version']['number']})"
            )
        except Exception as e:
            logger.error(f"Elasticsearch connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Elasticsearch connection."""
        if self._client:
            await self._client.close()
            logger.info("Elasticsearch disconnected")

    @property
    def client(self) -> AsyncElasticsearch:
        """Get Elasticsearch client instance."""
        if self._client is None:
            raise RuntimeError("Elasticsearch not connected. Call connect() first.")
        return self._client

    def index_name(self, suffix: str) -> str:
        """Generate prefixed index name."""
        return f"{settings.elasticsearch_index_prefix}_{suffix}"

    async def create_news_index(self, user_id: str) -> None:
        """
        Create news index for a specific user with proper mappings.

        Includes:
        - IK analyzer for Chinese text
        - Completion suggester for autocomplete
        - Dense vector for semantic search
        """
        index_name = self.index_name(f"news_{user_id}")

        if await self._client.indices.exists(index=index_name):
            logger.debug(f"Index already exists: {index_name}")
            return

        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "ik_smart_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_smart",
                        },
                        "ik_max_analyzer": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                        },
                    }
                },
            },
            "mappings": {
                "properties": {
                    # Core fields
                    "user_id": {"type": "keyword"},
                    "source_id": {"type": "keyword"},
                    "source_name": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "url": {"type": "keyword"},
                    # Text fields with Chinese analysis
                    "title": {
                        "type": "text",
                        "analyzer": "ik_max_analyzer",
                        "search_analyzer": "ik_smart_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "suggest": {
                                "type": "completion",
                                "analyzer": "ik_max_analyzer",
                            },
                        },
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "ik_max_analyzer",
                        "search_analyzer": "ik_smart_analyzer",
                    },
                    "content": {"type": "text", "analyzer": "ik_smart_analyzer"},
                    # Tags and metadata
                    "tags": {"type": "keyword"},
                    "image_url": {"type": "keyword", "index": False},
                    # Dates
                    "published_at": {"type": "date"},
                    "crawled_at": {"type": "date"},
                    # Scores
                    "hot_score": {"type": "float"},
                    "view_count": {"type": "integer"},
                    # State
                    "is_read": {"type": "boolean"},
                    "is_starred": {"type": "boolean"},
                    # Vector embedding for semantic search
                    "embedding": {
                        "type": "dense_vector",
                        "dims": settings.embedding_dimension,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        }

        await self._client.indices.create(index=index_name, body=mapping)
        logger.info(f"Created news index: {index_name}")

    async def ensure_user_index(self, user_id: str) -> str:
        """
        Ensure user's news index exists, create if needed.

        Returns:
            str: The index name for the user
        """
        await self.create_news_index(user_id)
        return self.index_name(f"news_{user_id}")


# Global instance
es_client = ElasticsearchClient()


async def get_es() -> AsyncElasticsearch:
    """
    Dependency injection for Elasticsearch client.

    Usage:
        @router.get("/search")
        async def search(es: AsyncElasticsearch = Depends(get_es)):
            ...
    """
    return es_client.client
