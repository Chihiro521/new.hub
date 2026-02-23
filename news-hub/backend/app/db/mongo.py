"""
MongoDB Connection and Collection Management

Provides async MongoDB client using Motor and collection accessors.
"""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from loguru import logger

from app.core.config import settings


class MongoDB:
    """
    MongoDB connection manager.

    Provides lazy initialization and collection access.
    """

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        """Get the MongoDB client instance."""
        return self._client

    async def connect(self) -> None:
        """Establish connection to MongoDB."""
        logger.info(f"Connecting to MongoDB: {settings.mongodb_url}")
        self._client = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=5000,
        )
        self._db = self._client[settings.mongodb_db_name]

        # Verify connection
        try:
            await self._client.admin.command("ping")
            logger.info(f"MongoDB connected: {settings.mongodb_db_name}")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            logger.info("MongoDB disconnected")

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if self._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return self._db

    def get_database(self) -> AsyncIOMotorDatabase:
        """Alias for db property, useful for scheduler."""
        return self.db

    # === Collection Accessors ===

    @property
    def users(self):
        """Users collection."""
        return self.db.users

    @property
    def sources(self):
        """News sources collection."""
        return self.db.sources

    @property
    def news(self):
        """News items collection."""
        return self.db.news

    @property
    def tag_rules(self):
        """Tag rules collection."""
        return self.db.tag_rules

    @property
    def external_search_sessions(self):
        """External search staging sessions collection."""
        return self.db.external_search_sessions

    @property
    def ingest_jobs(self):
        """Asynchronous ingestion job tracking collection."""
        return self.db.ingest_jobs

    @property
    def conversation_threads(self):
        """Conversation thread metadata collection."""
        return self.db.conversation_threads

    @property
    def llm_cache(self):
        """LLM response cache collection."""
        return self.db.llm_cache

    async def create_indexes(self) -> None:
        """
        Create database indexes for optimal query performance.
        Should be called on application startup.
        """
        logger.info("Creating MongoDB indexes...")

        # Users indexes
        await self.users.create_index("username", unique=True)
        await self.users.create_index("email", unique=True)

        # Sources indexes
        await self.sources.create_index("user_id")
        await self.sources.create_index([("user_id", 1), ("url", 1)], unique=True)
        await self.sources.create_index("status")

        # News indexes
        await self.news.create_index("user_id")
        await self.news.create_index("source_id")
        await self.news.create_index([("user_id", 1), ("url", 1)], unique=True)
        await self.news.create_index([("user_id", 1), ("published_at", -1)])
        await self.news.create_index([("user_id", 1), ("crawled_at", -1)])
        await self.news.create_index([("user_id", 1), ("is_starred", 1)])
        await self.news.create_index(
            [("user_id", 1), ("metadata.extra.url_hash", 1)],
            unique=True,
            partialFilterExpression={"metadata.extra.url_hash": {"$type": "string"}},
        )
        await self.news.create_index([("user_id", 1), ("metadata.extra.provider", 1)])
        await self.news.create_index("tags")

        # Tag rules indexes
        await self.tag_rules.create_index("user_id")
        await self.tag_rules.create_index(
            [("user_id", 1), ("tag_name", 1)], unique=True
        )

        # External search session indexes
        await self.external_search_sessions.create_index(
            [("user_id", 1), ("created_at", -1)]
        )

        # Ingest job indexes
        await self.ingest_jobs.create_index([("user_id", 1), ("created_at", -1)])
        await self.ingest_jobs.create_index([("status", 1), ("updated_at", -1)])

        # Conversation thread indexes
        await self.conversation_threads.create_index(
            [("user_id", 1), ("last_message_at", -1)]
        )
        await self.conversation_threads.create_index("thread_id", unique=True)
        await self.conversation_threads.create_index(
            [("user_id", 1), ("is_archived", 1)]
        )

        # LLM cache indexes
        await self.llm_cache.create_index("prompt_hash", unique=True)
        await self.llm_cache.create_index(
            "ttl_expires_at", expireAfterSeconds=0
        )

        logger.info("MongoDB indexes created")


# Global instance
mongodb = MongoDB()


async def get_db() -> AsyncIOMotorDatabase:
    """
    Dependency injection for database access.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncIOMotorDatabase = Depends(get_db)):
            ...
    """
    return mongodb.db
