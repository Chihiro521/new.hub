"""MongoDB-backed LangGraph checkpointer using Motor (async).

Stores agent conversation state in MongoDB so sessions can persist
across HTTP requests. Uses the existing Motor client from app.db.mongo.
"""

import json
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from loguru import logger

from app.db.mongo import mongodb

COLLECTION_NAME = "langgraph_checkpoints"
WRITES_COLLECTION = "langgraph_writes"


class MongoDBCheckpointer(BaseCheckpointSaver):
    """Async MongoDB checkpointer for LangGraph using Motor."""

    async def _get_collection(self):
        return mongodb.db[COLLECTION_NAME]

    async def _get_writes_collection(self):
        return mongodb.db[WRITES_COLLECTION]

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint to MongoDB."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]

        doc = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "checkpoint": self.serde.dumps_typed(checkpoint),
            "metadata": self.serde.dumps_typed(metadata),
        }

        col = await self._get_collection()
        await col.update_one(
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id},
            {"$set": doc},
            upsert=True,
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Save pending writes to MongoDB."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        col = await self._get_writes_collection()
        for idx, (channel, value) in enumerate(writes):
            doc = {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "task_path": task_path,
                "idx": idx,
                "channel": channel,
                "value": self.serde.dumps_typed(value),
            }
            await col.update_one(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "idx": idx,
                },
                {"$set": doc},
                upsert=True,
            )

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Load a checkpoint from MongoDB."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        col = await self._get_collection()

        query: Dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
        if checkpoint_id:
            query["checkpoint_id"] = checkpoint_id

        doc = await col.find_one(query, sort=[("checkpoint_id", -1)])
        if not doc:
            return None

        checkpoint = self.serde.loads_typed(doc["checkpoint"])
        metadata = self.serde.loads_typed(doc["metadata"])
        stored_id = doc["checkpoint_id"]

        # Load pending writes
        writes_col = await self._get_writes_collection()
        write_docs = await writes_col.find(
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": stored_id}
        ).sort("idx", 1).to_list(length=100)

        pending_writes = [
            (w["task_id"], w["channel"], self.serde.loads_typed(w["value"]))
            for w in write_docs
        ]

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": stored_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            pending_writes=pending_writes,
        )

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints from MongoDB."""
        query: Dict[str, Any] = {}
        if config:
            query["thread_id"] = config["configurable"]["thread_id"]
            checkpoint_ns = config["configurable"].get("checkpoint_ns")
            if checkpoint_ns is not None:
                query["checkpoint_ns"] = checkpoint_ns

        if before:
            query["checkpoint_id"] = {"$lt": before["configurable"]["checkpoint_id"]}

        col = await self._get_collection()
        cursor = col.find(query).sort("checkpoint_id", -1)
        if limit:
            cursor = cursor.limit(limit)

        async for doc in cursor:
            checkpoint = self.serde.loads_typed(doc["checkpoint"])
            metadata = self.serde.loads_typed(doc["metadata"])
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": doc["thread_id"],
                        "checkpoint_ns": doc["checkpoint_ns"],
                        "checkpoint_id": doc["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
            )

    # Sync methods — not used in our async FastAPI app, but required by the interface
    def put(self, config, checkpoint, metadata, new_versions):
        raise NotImplementedError("Use aput() in async context")

    def put_writes(self, config, writes, task_id, task_path=""):
        raise NotImplementedError("Use aput_writes() in async context")

    def get_tuple(self, config):
        raise NotImplementedError("Use aget_tuple() in async context")

    def list(self, config, *, filter=None, before=None, limit=None):
        raise NotImplementedError("Use alist() in async context")
