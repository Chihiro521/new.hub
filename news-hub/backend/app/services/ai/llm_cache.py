"""MongoDB-backed LLM response cache for LangChain.

Implements langchain_core.caches.BaseCache with async MongoDB storage.
Uses SHA256 hash of (model + prompt) as cache key with configurable TTL.
MongoDB TTL index auto-deletes expired entries.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Sequence

from langchain_core.caches import BaseCache
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb

COLLECTION = "llm_cache"


class MongoDBLLMCache(BaseCache):
    """Async-compatible MongoDB cache for LangChain LLM responses."""

    def __init__(self, ttl_hours: Optional[int] = None):
        self.ttl_hours = ttl_hours or settings.llm_cache_ttl_hours

    @staticmethod
    def _hash_key(prompt: str, llm_string: str) -> str:
        raw = f"{llm_string}::{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # --- Sync interface (required by BaseCache, not used in async app) ---

    def lookup(self, prompt: str, llm_string: str) -> Optional[Sequence[Generation]]:
        return None

    def update(self, prompt: str, llm_string: str, return_val: Sequence[Generation]) -> None:
        pass

    def clear(self, **kwargs) -> None:
        pass

    # --- Async interface ---

    async def alookup(self, prompt: str, llm_string: str) -> Optional[Sequence[Generation]]:
        key = self._hash_key(prompt, llm_string)
        try:
            doc = await mongodb.db[COLLECTION].find_one({"prompt_hash": key})
            if doc:
                await mongodb.db[COLLECTION].update_one(
                    {"_id": doc["_id"]}, {"$inc": {"hit_count": 1}}
                )
                logger.debug(f"LLM cache HIT: {key[:12]}... (hits: {doc.get('hit_count', 0) + 1})")
                text = str(doc.get("response", "") or "")
                if not text:
                    return None
                return [ChatGeneration(message=AIMessage(content=text))]
        except Exception as e:
            logger.warning(f"LLM cache lookup failed: {e}")
        return None

    async def aupdate(self, prompt: str, llm_string: str, return_val: Sequence[Generation]) -> None:
        key = self._hash_key(prompt, llm_string)
        text = ""
        if return_val:
            first = return_val[0]
            # Chat models usually return ChatGeneration(message=AIMessage(...))
            message = getattr(first, "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str):
                text = content
            elif content is not None:
                text = str(content)
            if not text:
                text = getattr(first, "text", "") or ""
        if not text:
            return
        try:
            await mongodb.db[COLLECTION].update_one(
                {"prompt_hash": key},
                {"$set": {
                    "model": llm_string[:200],
                    "response": text,
                    "created_at": datetime.utcnow(),
                    "ttl_expires_at": datetime.utcnow() + timedelta(hours=self.ttl_hours),
                }, "$setOnInsert": {
                    "hit_count": 0,
                }},
                upsert=True,
            )
            logger.debug(f"LLM cache STORE: {key[:12]}... ({len(text)} chars)")
        except Exception as e:
            logger.warning(f"LLM cache update failed: {e}")

    async def aclear(self, **kwargs) -> None:
        try:
            result = await mongodb.db[COLLECTION].delete_many({})
            logger.info(f"LLM cache cleared: {result.deleted_count} entries")
        except Exception as e:
            logger.warning(f"LLM cache clear failed: {e}")
