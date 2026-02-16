"""LLM client initialization and caching."""

from functools import lru_cache
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from app.core.config import settings


@lru_cache(maxsize=1)
def get_llm_client() -> Optional[AsyncOpenAI]:
    """Get a process-wide cached AsyncOpenAI client."""
    if not settings.openai_api_key:
        logger.info("OPENAI_API_KEY not configured, AI assistant runs in fallback mode")
        return None

    logger.info("Initializing OpenAI async client")
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries,
    )
